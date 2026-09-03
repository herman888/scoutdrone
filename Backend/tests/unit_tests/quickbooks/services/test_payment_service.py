"""
Unit tests for QuickBooks PaymentService class.

Tests payment synchronization functionality including pulling from QuickBooks,
pushing to QuickBooks, and bidirectional sync operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, UTC, date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.quickbooks.services.payment_service import PaymentService
from Backend.api.quickbooks.services.base_service import SyncPreview
from Backend.models.user import User
from Backend.models.property import Property, PropertyType
from Backend.models.tenant import Tenant
from Backend.models.accounting.payment import Payment
from Backend.models.accounting.common import PaymentStatus
from Backend.models.enums import UserType, PropertyStatus

# Mark all tests in this module as unit tests
pytestmark = pytest.mark.unit

# Fixed datetime for deterministic testing
FIXED_DATETIME = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
FIXED_DATE = date(2024, 6, 1)


def create_test_user(user_id=None):
    """Helper function to create a test user."""
    return User(
        id=user_id or uuid4(),
        email="test@example.com",
        user_type=UserType.LANDLORD,
        first_name="Test",
        last_name="User",
        created_at=FIXED_DATETIME,
        updated_at=FIXED_DATETIME,
        is_email_verified=True
    )


def create_test_property(property_id=None, user_id=None):
    """Helper function to create a test property."""
    return Property(
        id=property_id or 1,
        user_id=user_id or uuid4(),
        name="Test Property",
        property_type=PropertyType.RESIDENTIAL,
        status=PropertyStatus.ACTIVE,
        street_address="123 Test St",
        city="Test City",
        state="CA",
        zip_code="12345",
        created_at=FIXED_DATETIME,
        updated_at=FIXED_DATETIME
    )


def create_test_tenant(tenant_id=None, user_id=None, quickbooks_customer_id=None):
    """Helper function to create a test tenant."""
    return Tenant(
        id=tenant_id or uuid4(),
        user_id=user_id or uuid4(),
        email="tenant@example.com",
        first_name="John",
        last_name="Doe",
        phone="555-123-4567",
        quickbooks_customer_id=quickbooks_customer_id,
        created_at=FIXED_DATETIME,
        updated_at=FIXED_DATETIME
    )


def create_test_payment(payment_id=None, user_id=None, property_id=None, tenant_id=None, quickbooks_id=None):
    """Helper function to create a test payment."""
    return Payment(
        id=payment_id or uuid4(),
        user_id=user_id or uuid4(),
        property_id=property_id or 1,
        tenant_id=tenant_id or uuid4(),
        payment_date=FIXED_DATE,
        amount=Decimal("1200.00"),
        payment_method="bank_transfer",
        description="Monthly Rent Payment",
        payment_status=PaymentStatus.PAID,
        quickbooks_id=quickbooks_id,
        created_at=FIXED_DATETIME,
        updated_at=FIXED_DATETIME,
        last_synced_at=FIXED_DATETIME if quickbooks_id else None
    )


@pytest.fixture
def mock_session():
    """Mock AsyncSession for database operations."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    session.scalars = AsyncMock()
    session.scalar = AsyncMock()
    return session


@pytest.fixture
def mock_client():
    """Mock QuickBooks client."""
    client = AsyncMock()
    return client


@pytest.fixture
def test_user():
    """Create a test user."""
    return create_test_user()


@pytest.fixture
def payment_service(test_user, mock_session, mock_client):
    """Create PaymentService instance with mocked dependencies."""
    service = PaymentService(test_user, mock_session)
    service._client = mock_client
    service.initialize = AsyncMock()
    return service


class TestPaymentServiceInitialization:
    """Test PaymentService initialization."""

    def test_payment_service_creation(self, test_user, mock_session):
        """Test PaymentService can be created."""
        service = PaymentService(test_user, mock_session)
        assert service.user == test_user
        assert service.session == mock_session
        assert service._client is None

    def test_payment_service_preview_mode(self, test_user, mock_session):
        """Test PaymentService in preview mode."""
        service = PaymentService(test_user, mock_session, preview_mode=True)
        assert service.preview_mode is True


class TestSyncPayments:
    """Test the main sync_payments method."""

    @pytest.mark.asyncio
    async def test_sync_payments_calls_internal(self, payment_service):
        """Test that sync_payments calls the internal method."""
        payment_service.sync_payments_internal = AsyncMock(return_value={
            "success": True,
            "synced_count": 4,
            "errors": []
        })

        result = await payment_service.sync_payments()

        payment_service.sync_payments_internal.assert_called_once()
        assert result["success"] is True
        assert result["synced_count"] == 4


class TestPreviewPayments:
    """Test payment preview functionality."""

    @pytest.mark.asyncio
    async def test_preview_payments_creates_preview_service(self, payment_service):
        """Test that preview creates a separate service instance."""
        with patch.object(PaymentService, '__init__', return_value=None), \
             patch.object(PaymentService, 'initialize', new_callable=AsyncMock), \
             patch.object(PaymentService, 'sync_payments_internal', new_callable=AsyncMock), \
             patch.object(PaymentService, '_generate_preview') as mock_gen:

            mock_gen.return_value = SyncPreview(
                items=[],
                summary={"total": 0},
                warnings=[]
            )

            result = await payment_service.preview_payments()

            assert isinstance(result, SyncPreview)


class TestSyncPaymentsInternal:
    """Test the internal payment synchronization logic."""

    @pytest.mark.asyncio
    async def test_sync_payments_internal_success(self, payment_service):
        """Test successful internal payment synchronization."""
        payment_service._pull_payments_from_quickbooks = AsyncMock(return_value={
            "synced_count": 3,
            "errors": []
        })
        payment_service._push_payments_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 2,
            "updated_count": 0,
            "errors": []
        })
        payment_service._update_integration_sync_time = AsyncMock()

        result = await payment_service.sync_payments_internal()

        assert result["success"] is True
        assert result["synced_count"] == 5
        assert result["pulled_count"] == 3
        assert result["pushed_count"] == 2
        payment_service._update_integration_sync_time.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_payments_internal_with_errors(self, payment_service):
        """Test internal synchronization with errors."""
        payment_service._pull_payments_from_quickbooks = AsyncMock(return_value={
            "synced_count": 1,
            "errors": ["Pull error"]
        })
        payment_service._push_payments_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 0,
            "updated_count": 0,
            "errors": ["Push error"]
        })
        payment_service._update_integration_sync_time = AsyncMock()

        result = await payment_service.sync_payments_internal()

        assert result["success"] is False
        assert result["synced_count"] == 1
        assert len(result["errors"]) == 2
        payment_service._update_integration_sync_time.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_payments_internal_exception_handling(self, payment_service):
        """Test exception handling in internal sync."""
        payment_service._pull_payments_from_quickbooks = AsyncMock(side_effect=Exception("Test error"))

        result = await payment_service.sync_payments_internal()

        assert result["success"] is False
        assert "Payment sync failed: Test error" in result["errors"]


class TestSyncSinglePayment:
    """Test single payment sync from webhook."""

    @pytest.mark.asyncio
    async def test_sync_single_payment_new(self, payment_service, mock_session):
        """Test syncing a new payment from webhook."""
        qb_payment = {
            "Id": "qb_123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "cust_1"},
            "Line": [{"Amount": 1200.00, "LinkedTxn": [{"TxnId": "inv_1", "TxnType": "Invoice"}]}]
        }

        # No existing payment
        mock_session.scalar = AsyncMock(return_value=None)

        # Mock the internal create method
        payment_service._create_single_payment = AsyncMock(return_value={
            "synced_count": 1,
            "errors": []
        })

        result = await payment_service.sync_single_payment_from_quickbooks(qb_payment)

        assert result["synced_count"] == 1
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_sync_single_payment_update_existing(self, payment_service, mock_session):
        """Test updating an existing payment from webhook."""
        qb_payment = {
            "Id": "qb_123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 1500.00,
            "CustomerRef": {"value": "cust_1"}
        }

        existing_payment = create_test_payment(quickbooks_id="qb_123")
        mock_session.scalar = AsyncMock(return_value=existing_payment)

        # Mock the internal update method
        payment_service._update_single_payment = AsyncMock(return_value={
            "synced_count": 1,
            "errors": []
        })

        result = await payment_service.sync_single_payment_from_quickbooks(qb_payment)

        assert result["synced_count"] == 1

    @pytest.mark.asyncio
    async def test_sync_single_payment_missing_id(self, payment_service):
        """Test handling payment with missing ID."""
        qb_payment = {"TotalAmt": 1200.00}  # Missing Id

        result = await payment_service.sync_single_payment_from_quickbooks(qb_payment)

        assert result["synced_count"] == 0
        assert "Payment data missing ID" in result["errors"]


class TestPaymentServiceLogging:
    """Test logging functionality in PaymentService."""

    @pytest.mark.asyncio
    async def test_operation_logging(self, payment_service):
        """Test that operations are properly logged."""
        payment_service._pull_payments_from_quickbooks = AsyncMock(return_value={
            "synced_count": 3,
            "errors": []
        })
        payment_service._push_payments_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 2,
            "updated_count": 0,
            "errors": []
        })
        payment_service._update_integration_sync_time = AsyncMock()
        payment_service._log_operation = MagicMock()

        await payment_service.sync_payments_internal()

        payment_service._log_operation.assert_called_once_with(
            operation="sync_payments",
            level="info",
            synced_count=5,
            pulled_count=3,
            pushed_count=2,
            updated_count=0,
            error_count=0
        )

    @pytest.mark.asyncio
    async def test_error_logging(self, payment_service):
        """Test error logging functionality."""
        payment_service._pull_payments_from_quickbooks = AsyncMock(return_value={
            "synced_count": 0,
            "errors": ["Test error"]
        })
        payment_service._push_payments_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 0,
            "updated_count": 0,
            "errors": []
        })
        payment_service._log_operation = MagicMock()

        await payment_service.sync_payments_internal()

        payment_service._log_operation.assert_called_once_with(
            operation="sync_payments",
            level="warning",
            synced_count=0,
            pulled_count=0,
            pushed_count=0,
            updated_count=0,
            error_count=1
        )


class TestPaymentServiceHelperMethods:
    """Test helper methods in PaymentService."""

    def test_resolve_from_cache_missing_customer(self, payment_service):
        """Test _resolve_from_cache with missing QB customer ID."""
        from Backend.api.quickbooks.schemas.payment import PaymentSchema

        qb_payment = {
            "Id": "pay123",
            "TotalAmt": 1200.00
            # Missing CustomerRef
        }

        tenant_cache = {}

        tenant, lease = payment_service._resolve_from_cache(
            qb_payment, tenant_cache, PaymentSchema.get_customer_id
        )

        assert tenant is None
        assert lease is None

    def test_resolve_from_cache_customer_not_in_cache(self, payment_service):
        """Test _resolve_from_cache when customer not in cache."""
        from Backend.api.quickbooks.schemas.payment import PaymentSchema

        qb_payment = {
            "Id": "pay123",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "QB_NOT_IN_CACHE"}
        }

        tenant_cache = {}

        tenant, lease = payment_service._resolve_from_cache(
            qb_payment, tenant_cache, PaymentSchema.get_customer_id
        )

        assert tenant is None
        assert lease is None

    def test_resolve_from_cache_customer_in_cache(self, payment_service, test_user):
        """Test _resolve_from_cache when customer is in cache."""
        from Backend.api.quickbooks.schemas.payment import PaymentSchema
        from Backend.models.lease import Lease

        tenant = create_test_tenant(quickbooks_customer_id="QB_CUSTOMER_123")
        tenant.landlord_id = test_user.id
        lease = MagicMock(spec=Lease)
        lease.tenant_id = tenant.id

        qb_payment = {
            "Id": "pay123",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "QB_CUSTOMER_123"}
        }

        tenant_cache = {"QB_CUSTOMER_123": (tenant, lease)}

        result_tenant, result_lease = payment_service._resolve_from_cache(
            qb_payment, tenant_cache, PaymentSchema.get_customer_id
        )

        assert result_tenant == tenant
        assert result_lease == lease


class TestUpdateSinglePayment:
    """Test _update_single_payment method."""

    @pytest.mark.asyncio
    async def test_update_single_payment_success(self, payment_service, mock_session):
        """Test successful payment update from QuickBooks data."""
        existing_payment = create_test_payment(quickbooks_id="qb_123")
        qb_payment_data = {
            "Id": "qb_123",
            "TotalAmt": 1500.00,
            "TxnDate": "2024-07-15"
        }

        result = await payment_service._update_single_payment(existing_payment, qb_payment_data)

        assert result["synced_count"] == 1
        assert result["errors"] == []
        mock_session.add.assert_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_single_payment_exception(self, payment_service, mock_session):
        """Test exception handling during payment update."""
        existing_payment = create_test_payment(quickbooks_id="qb_123")
        mock_session.commit = AsyncMock(side_effect=Exception("DB error"))
        qb_payment_data = {"Id": "qb_123", "TotalAmt": 1500.00}

        result = await payment_service._update_single_payment(existing_payment, qb_payment_data)

        assert result["synced_count"] == 0
        assert "Error updating payment" in result["errors"][0]


class TestCreateSinglePayment:
    """Test _create_single_payment method."""

    @pytest.mark.asyncio
    async def test_create_single_payment_success(self, payment_service, mock_session, test_user):
        """Test successful payment creation from QuickBooks data."""
        from Backend.models.lease import Lease, LeaseStatus

        tenant = create_test_tenant(quickbooks_customer_id="qb_cust_123")
        tenant.landlord_id = test_user.id
        lease = MagicMock(spec=Lease)
        lease.id = uuid4()
        lease.tenant_id = tenant.id
        lease.status = LeaseStatus.ACTIVE

        qb_payment_data = {
            "Id": "qb_pay_123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "qb_cust_123"},
            "Line": [{"Amount": 1200.00, "LinkedTxn": [{"TxnId": "inv_1", "TxnType": "Invoice"}]}]
        }

        # Mock prefetch
        payment_service._prefetch_tenants_and_leases = AsyncMock(
            return_value={"qb_cust_123": (tenant, lease)}
        )

        result = await payment_service._create_single_payment(qb_payment_data)

        assert result["synced_count"] == 1
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_create_single_payment_no_tenant(self, payment_service):
        """Test payment creation fails when tenant not found."""
        qb_payment_data = {
            "Id": "qb_pay_123",
            "CustomerRef": {"value": "unknown_cust"}
        }

        # No tenant found
        payment_service._prefetch_tenants_and_leases = AsyncMock(return_value={})

        result = await payment_service._create_single_payment(qb_payment_data)

        assert result["synced_count"] == 0
        assert "Could not resolve tenant/lease" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_create_single_payment_exception(self, payment_service):
        """Test exception handling during payment creation."""
        qb_payment_data = {"Id": "qb_pay_123", "CustomerRef": {"value": "cust_1"}}
        payment_service._prefetch_tenants_and_leases = AsyncMock(side_effect=Exception("DB error"))

        result = await payment_service._create_single_payment(qb_payment_data)

        assert result["synced_count"] == 0
        assert "Error creating payment" in result["errors"][0]


class TestPullPaymentsFromQuickBooks:
    """Test _pull_payments_from_quickbooks method."""

    @pytest.mark.asyncio
    async def test_pull_payments_no_response(self, payment_service):
        """Test handling no response from QuickBooks."""
        payment_service._client.list_payments = AsyncMock(return_value=None)

        result = await payment_service._pull_payments_from_quickbooks()

        assert result["synced_count"] == 0
        assert "No payments found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_pull_payments_empty_list(self, payment_service):
        """Test handling empty payment list."""
        payment_service._client.list_payments = AsyncMock(return_value={
            "QueryResponse": {"Payment": []}
        })

        result = await payment_service._pull_payments_from_quickbooks()

        assert result["synced_count"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_pull_payments_skips_existing(self, payment_service, mock_session, test_user):
        """Test that existing payments are skipped."""
        from Backend.models.lease import Lease

        qb_payments = [
            {"Id": "qb_1", "CustomerRef": {"value": "cust_1"}, "TotalAmt": 100.00},
            {"Id": "qb_2", "CustomerRef": {"value": "cust_2"}, "TotalAmt": 200.00}
        ]

        payment_service._client.list_payments = AsyncMock(return_value={
            "QueryResponse": {"Payment": qb_payments}
        })

        # Mock existing IDs check - qb_1 already exists
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([("qb_1",)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock tenant/lease prefetch
        tenant = create_test_tenant(quickbooks_customer_id="cust_2")
        tenant.landlord_id = test_user.id
        lease = MagicMock(spec=Lease)
        lease.id = uuid4()
        lease.tenant_id = tenant.id
        payment_service._prefetch_tenants_and_leases = AsyncMock(
            return_value={"cust_2": (tenant, lease)}
        )

        result = await payment_service._pull_payments_from_quickbooks()

        # Only qb_2 should be synced (qb_1 exists)
        assert result["synced_count"] == 1

    @pytest.mark.asyncio
    async def test_pull_payments_exception(self, payment_service):
        """Test exception handling in pull payments."""
        payment_service._client.list_payments = AsyncMock(side_effect=Exception("API error"))

        result = await payment_service._pull_payments_from_quickbooks()

        assert result["synced_count"] == 0
        assert "Pull payments failed" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_pull_payments_preview_mode(self, test_user, mock_session, mock_client):
        """Test pull payments in preview mode."""
        from Backend.models.lease import Lease

        service = PaymentService(test_user, mock_session, preview_mode=True)
        service._client = mock_client
        service.initialize = AsyncMock()

        tenant = create_test_tenant(quickbooks_customer_id="cust_1")
        tenant.landlord_id = test_user.id
        lease = MagicMock(spec=Lease)
        lease.id = uuid4()

        mock_client.list_payments = AsyncMock(return_value={
            "QueryResponse": {"Payment": [
                {"Id": "qb_1", "CustomerRef": {"value": "cust_1"}, "TotalAmt": 100.00}
            ]}
        })

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        service._prefetch_tenants_and_leases = AsyncMock(
            return_value={"cust_1": (tenant, lease)}
        )

        result = await service._pull_payments_from_quickbooks()

        # Preview mode should count but not commit
        assert result["synced_count"] == 1
        mock_session.commit.assert_not_called()


class TestPushPaymentsToQuickBooks:
    """Test _push_payments_to_quickbooks method."""

    @pytest.mark.asyncio
    async def test_push_payments_no_properties(self, payment_service, mock_session):
        """Test when user has no properties."""
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        result = await payment_service._push_payments_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "No properties found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_push_payments_no_unsynced(self, payment_service, mock_session):
        """Test when no unsynced payments exist."""
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([]))

        result = await payment_service._push_payments_to_quickbooks()

        assert result["pushed_count"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_push_payments_success(self, payment_service, mock_session, test_user):
        """Test successful payment push to QuickBooks."""
        payment = create_test_payment(quickbooks_id=None)
        tenant = create_test_tenant(quickbooks_customer_id="qb_cust_123")
        tenant.landlord_id = test_user.id

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([payment]))

        payment_service._prefetch_tenants_by_ids = AsyncMock(
            return_value={payment.tenant_id: tenant}
        )
        payment_service._get_or_cache_deposit_account = AsyncMock(return_value="1")
        payment_service._retry_operation = AsyncMock(return_value={
            "Payment": {"Id": "new_qb_id"}
        })

        result = await payment_service._push_payments_to_quickbooks()

        assert result["pushed_count"] == 1
        assert payment.quickbooks_id == "new_qb_id"

    @pytest.mark.asyncio
    async def test_push_payments_tenant_not_synced(self, payment_service, mock_session, test_user):
        """Test push fails when tenant not synced."""
        payment = create_test_payment(quickbooks_id=None)
        tenant = create_test_tenant(quickbooks_customer_id=None)  # Not synced
        tenant.landlord_id = test_user.id

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([payment]))

        payment_service._prefetch_tenants_by_ids = AsyncMock(
            return_value={payment.tenant_id: tenant}
        )
        payment_service._get_or_cache_deposit_account = AsyncMock(return_value="1")

        result = await payment_service._push_payments_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "Tenant not synced" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_push_payments_api_error(self, payment_service, mock_session, test_user):
        """Test handling API error during push."""
        payment = create_test_payment(quickbooks_id=None)
        tenant = create_test_tenant(quickbooks_customer_id="qb_cust_123")
        tenant.landlord_id = test_user.id

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([payment]))

        payment_service._prefetch_tenants_by_ids = AsyncMock(
            return_value={payment.tenant_id: tenant}
        )
        payment_service._get_or_cache_deposit_account = AsyncMock(return_value="1")
        payment_service._retry_operation = AsyncMock(return_value=None)  # Failed

        result = await payment_service._push_payments_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "Invalid QuickBooks response" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_push_payments_exception(self, payment_service, mock_session):
        """Test exception handling during push."""
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))

        result = await payment_service._push_payments_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "Push payments failed" in result["errors"][0]


class TestCreateAllocationsForLinkedInvoices:
    """Test _create_allocations_for_linked_invoices method."""

    @pytest.mark.asyncio
    async def test_create_allocations_success(self, payment_service, mock_session):
        """Test successful allocation creation."""
        from Backend.models.accounting.invoice import Invoice

        payment = create_test_payment()
        payment.id = uuid4()

        invoice = MagicMock(spec=Invoice)
        invoice.id = uuid4()
        invoice.quickbooks_id = "qb_inv_1"
        invoice.status = PaymentStatus.PENDING

        linked_invoices_with_amounts = {"qb_inv_1": Decimal("1200.00")}
        invoices_by_qb_id = {"qb_inv_1": invoice}

        result = await payment_service._create_allocations_for_linked_invoices(
            payment, linked_invoices_with_amounts, invoices_by_qb_id
        )

        # Should add allocation and return list
        mock_session.add.assert_called()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_create_allocations_no_payment_id(self, payment_service, mock_session):
        """Test that no allocations are created when payment has no ID."""
        from Backend.models.accounting.invoice import Invoice

        payment = create_test_payment()
        payment.id = None  # No ID

        invoice = MagicMock(spec=Invoice)
        invoice.id = uuid4()
        invoice.quickbooks_id = "qb_inv_1"

        linked_invoices_with_amounts = {"qb_inv_1": Decimal("1200.00")}
        invoices_by_qb_id = {"qb_inv_1": invoice}

        result = await payment_service._create_allocations_for_linked_invoices(
            payment, linked_invoices_with_amounts, invoices_by_qb_id
        )

        # Should return empty list
        assert result == []
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_allocations_empty_linked_invoices(self, payment_service, mock_session):
        """Test that no allocations are created when no linked invoices."""
        payment = create_test_payment()
        payment.id = uuid4()

        result = await payment_service._create_allocations_for_linked_invoices(
            payment, {}, {}
        )

        # Should return empty list
        assert result == []

    @pytest.mark.asyncio
    async def test_create_allocations_invoice_not_found(self, payment_service, mock_session):
        """Test handling when invoice not found in lookup."""
        payment = create_test_payment()
        payment.id = uuid4()

        linked_invoices_with_amounts = {"qb_inv_1": Decimal("1200.00")}
        invoices_by_qb_id = {}  # Invoice not in lookup

        result = await payment_service._create_allocations_for_linked_invoices(
            payment, linked_invoices_with_amounts, invoices_by_qb_id
        )

        # Should return empty list and not add anything
        assert result == []


class TestPreviewPayments:
    """Test preview_payments method."""

    @pytest.mark.asyncio
    async def test_preview_payments_returns_sync_preview(self, payment_service):
        """Test that preview_payments returns a SyncPreview."""
        with patch.object(PaymentService, '__init__', return_value=None), \
             patch.object(PaymentService, 'initialize', new_callable=AsyncMock), \
             patch.object(PaymentService, 'sync_payments_internal', new_callable=AsyncMock), \
             patch.object(PaymentService, '_generate_preview') as mock_gen:

            mock_gen.return_value = SyncPreview(
                items=[],
                summary={"total": 0, "create": 0, "update": 0},
                warnings=[]
            )

            result = await payment_service.preview_payments()

            assert isinstance(result, SyncPreview)
