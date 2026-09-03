"""
Unit tests for QuickBooks InvoiceService class.

Tests invoice synchronization functionality including pulling from QuickBooks,
pushing to QuickBooks, and bidirectional sync operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, UTC, timedelta, date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.quickbooks.services.invoice_service import InvoiceService
from Backend.api.quickbooks.services.base_service import SyncPreview
from Backend.models.user import User
from Backend.models.property import Property, PropertyType
from Backend.models.tenant import Tenant
from Backend.models.accounting.invoice import Invoice
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


def create_test_invoice(invoice_id=None, lease_id=None, tenant_id=None, quickbooks_id=None):
    """Helper function to create a test invoice."""
    return Invoice(
        id=invoice_id or uuid4(),
        lease_id=lease_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        invoice_number="INV-001",
        invoice_date=FIXED_DATE,
        due_date=FIXED_DATE + timedelta(days=30),
        amount=Decimal("1200.00"),
        description="Monthly Rent",
        status=PaymentStatus.PENDING,
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
    session.flush = AsyncMock()
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
def invoice_service(test_user, mock_session, mock_client):
    """Create InvoiceService instance with mocked dependencies."""
    service = InvoiceService(test_user, mock_session)
    service._client = mock_client
    service.initialize = AsyncMock()
    return service


class TestInvoiceServiceInitialization:
    """Test InvoiceService initialization."""

    def test_invoice_service_creation(self, test_user, mock_session):
        """Test InvoiceService can be created."""
        service = InvoiceService(test_user, mock_session)
        assert service.user == test_user
        assert service.session == mock_session
        assert service._client is None

    def test_invoice_service_preview_mode(self, test_user, mock_session):
        """Test InvoiceService in preview mode."""
        service = InvoiceService(test_user, mock_session, preview_mode=True)
        assert service.preview_mode is True


class TestSyncInvoices:
    """Test the main sync_invoices method."""

    @pytest.mark.asyncio
    async def test_sync_invoices_calls_internal(self, invoice_service):
        """Test that sync_invoices calls the internal method."""
        invoice_service.sync_invoices_internal = AsyncMock(return_value={
            "success": True,
            "synced_count": 3,
            "errors": []
        })

        result = await invoice_service.sync_invoices()

        invoice_service.sync_invoices_internal.assert_called_once()
        assert result["success"] is True
        assert result["synced_count"] == 3


class TestPreviewInvoices:
    """Test invoice preview functionality."""

    @pytest.mark.asyncio
    async def test_preview_invoices_creates_preview_service(self, invoice_service):
        """Test that preview creates a separate service instance."""
        with patch.object(InvoiceService, '__init__', return_value=None), \
             patch.object(InvoiceService, 'initialize', new_callable=AsyncMock), \
             patch.object(InvoiceService, 'sync_invoices_internal', new_callable=AsyncMock), \
             patch.object(InvoiceService, '_generate_preview') as mock_gen:

            mock_gen.return_value = SyncPreview(
                items=[],
                summary={"total": 0},
                warnings=[]
            )

            result = await invoice_service.preview_invoices()

            assert isinstance(result, SyncPreview)


class TestSyncInvoicesInternal:
    """Test the internal invoice synchronization logic."""

    @pytest.mark.asyncio
    async def test_sync_invoices_internal_success(self, invoice_service):
        """Test successful internal invoice synchronization."""
        invoice_service._pull_invoices_from_quickbooks = AsyncMock(return_value={
            "synced_count": 2,
            "errors": []
        })
        invoice_service._push_invoices_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 1,
            "updated_count": 0,
            "errors": []
        })
        invoice_service._update_integration_sync_time = AsyncMock()

        result = await invoice_service.sync_invoices_internal()

        assert result["success"] is True
        assert result["synced_count"] == 3
        assert result["pulled_count"] == 2
        assert result["pushed_count"] == 1
        invoice_service._update_integration_sync_time.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_invoices_internal_with_errors(self, invoice_service):
        """Test internal synchronization with errors."""
        invoice_service._pull_invoices_from_quickbooks = AsyncMock(return_value={
            "synced_count": 1,
            "errors": ["Pull error"]
        })
        invoice_service._push_invoices_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 0,
            "updated_count": 0,
            "errors": ["Push error"]
        })
        invoice_service._update_integration_sync_time = AsyncMock()

        result = await invoice_service.sync_invoices_internal()

        assert result["success"] is False
        assert result["synced_count"] == 1
        assert len(result["errors"]) == 2
        invoice_service._update_integration_sync_time.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_invoices_internal_exception_handling(self, invoice_service):
        """Test exception handling in internal sync."""
        invoice_service._pull_invoices_from_quickbooks = AsyncMock(side_effect=Exception("Test error"))

        result = await invoice_service.sync_invoices_internal()

        assert result["success"] is False
        assert "Invoice sync failed: Test error" in result["errors"]


class TestSyncSingleInvoice:
    """Test single invoice sync from webhook."""

    @pytest.mark.asyncio
    async def test_sync_single_invoice_new(self, invoice_service, mock_session):
        """Test syncing a new invoice from webhook."""
        qb_invoice = {
            "Id": "qb_123",
            "DocNumber": "INV-001",
            "TxnDate": "2024-06-01",
            "DueDate": "2024-07-01",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "cust_1"}
        }

        # No existing invoice
        mock_session.scalar = AsyncMock(return_value=None)

        # Mock _create_single_invoice
        invoice_service._create_single_invoice = AsyncMock(return_value={
            "synced_count": 1,
            "errors": []
        })

        result = await invoice_service.sync_single_invoice_from_quickbooks(qb_invoice)

        assert result["synced_count"] == 1
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_sync_single_invoice_update_existing(self, invoice_service, mock_session):
        """Test updating an existing invoice from webhook."""
        qb_invoice = {
            "Id": "qb_123",
            "DocNumber": "INV-001",
            "TxnDate": "2024-06-01",
            "DueDate": "2024-07-01",
            "TotalAmt": 1500.00,  # Updated amount
            "CustomerRef": {"value": "cust_1"}
        }

        existing_invoice = create_test_invoice(quickbooks_id="qb_123")
        mock_session.scalar = AsyncMock(return_value=existing_invoice)

        # Mock _update_single_invoice
        invoice_service._update_single_invoice = AsyncMock(return_value={
            "synced_count": 1,
            "errors": []
        })

        result = await invoice_service.sync_single_invoice_from_quickbooks(qb_invoice)

        assert result["synced_count"] == 1

    @pytest.mark.asyncio
    async def test_sync_single_invoice_missing_id(self, invoice_service):
        """Test handling invoice with missing ID."""
        qb_invoice = {"DocNumber": "INV-001"}  # Missing Id

        result = await invoice_service.sync_single_invoice_from_quickbooks(qb_invoice)

        assert result["synced_count"] == 0
        assert "Invoice data missing ID" in result["errors"]


class TestInvoiceServiceHelperMethods:
    """Test helper methods in InvoiceService."""

    def test_resolve_from_cache_missing_customer(self, invoice_service):
        """Test _resolve_from_cache with missing QB customer ID."""
        from Backend.api.quickbooks.schemas.invoice import InvoiceSchema

        qb_invoice = {
            "Id": "inv123",
            "TotalAmt": 1200.00
            # Missing CustomerRef
        }

        tenant_cache = {}

        tenant, lease = invoice_service._resolve_from_cache(
            qb_invoice, tenant_cache, InvoiceSchema.get_customer_id
        )

        assert tenant is None
        assert lease is None

    def test_resolve_from_cache_customer_not_in_cache(self, invoice_service):
        """Test _resolve_from_cache when customer not in cache."""
        from Backend.api.quickbooks.schemas.invoice import InvoiceSchema

        qb_invoice = {
            "Id": "inv123",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "QB_NOT_IN_CACHE"}
        }

        tenant_cache = {}

        tenant, lease = invoice_service._resolve_from_cache(
            qb_invoice, tenant_cache, InvoiceSchema.get_customer_id
        )

        assert tenant is None
        assert lease is None

    def test_resolve_from_cache_customer_found(self, invoice_service, test_user):
        """Test _resolve_from_cache when customer is in cache."""
        from Backend.api.quickbooks.schemas.invoice import InvoiceSchema
        from Backend.models.lease import Lease

        tenant = create_test_tenant(quickbooks_customer_id="QB_CUSTOMER_123")
        tenant.landlord_id = test_user.id
        lease = MagicMock(spec=Lease)
        lease.tenant_id = tenant.id

        qb_invoice = {
            "Id": "inv123",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "QB_CUSTOMER_123"}
        }

        tenant_cache = {"QB_CUSTOMER_123": (tenant, lease)}

        result_tenant, result_lease = invoice_service._resolve_from_cache(
            qb_invoice, tenant_cache, InvoiceSchema.get_customer_id
        )

        assert result_tenant == tenant
        assert result_lease == lease


class TestInvoiceServiceLogging:
    """Test logging functionality in InvoiceService."""

    @pytest.mark.asyncio
    async def test_operation_logging(self, invoice_service):
        """Test that operations are properly logged."""
        invoice_service._pull_invoices_from_quickbooks = AsyncMock(return_value={
            "synced_count": 2,
            "errors": []
        })
        invoice_service._push_invoices_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 1,
            "updated_count": 0,
            "errors": []
        })
        invoice_service._update_integration_sync_time = AsyncMock()
        invoice_service._log_operation = MagicMock()

        await invoice_service.sync_invoices_internal()

        invoice_service._log_operation.assert_called_once_with(
            operation="sync_invoices",
            level="info",
            synced_count=3,
            pulled_count=2,
            pushed_count=1,
            updated_count=0,
            error_count=0
        )

    @pytest.mark.asyncio
    async def test_error_logging(self, invoice_service):
        """Test error logging functionality."""
        invoice_service._pull_invoices_from_quickbooks = AsyncMock(return_value={
            "synced_count": 0,
            "errors": ["Test error"]
        })
        invoice_service._push_invoices_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 0,
            "updated_count": 0,
            "errors": []
        })
        invoice_service._log_operation = MagicMock()

        await invoice_service.sync_invoices_internal()

        invoice_service._log_operation.assert_called_once_with(
            operation="sync_invoices",
            level="warning",
            synced_count=0,
            pulled_count=0,
            pushed_count=0,
            updated_count=0,
            error_count=1
        )


class TestUpdateSingleInvoice:
    """Test _update_single_invoice method."""

    @pytest.mark.asyncio
    async def test_update_single_invoice_success(self, invoice_service, mock_session):
        """Test successful invoice update from QuickBooks data."""
        existing_invoice = create_test_invoice(quickbooks_id="qb_123")
        qb_invoice_data = {
            "Id": "qb_123",
            "TotalAmt": 1500.00,
            "DueDate": "2024-07-15",
            "Balance": 0  # Fully paid
        }

        result = await invoice_service._update_single_invoice(existing_invoice, qb_invoice_data)

        assert result["synced_count"] == 1
        assert result["errors"] == []
        mock_session.add.assert_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_single_invoice_with_balance(self, invoice_service, mock_session):
        """Test invoice update sets PENDING status when balance > 0."""
        existing_invoice = create_test_invoice(quickbooks_id="qb_123")
        qb_invoice_data = {
            "Id": "qb_123",
            "TotalAmt": 1500.00,
            "Balance": 500.00  # Partial payment
        }

        result = await invoice_service._update_single_invoice(existing_invoice, qb_invoice_data)

        assert result["synced_count"] == 1
        assert existing_invoice.status == PaymentStatus.PENDING

    @pytest.mark.asyncio
    async def test_update_single_invoice_exception(self, invoice_service, mock_session):
        """Test exception handling during invoice update."""
        existing_invoice = create_test_invoice(quickbooks_id="qb_123")
        mock_session.commit = AsyncMock(side_effect=Exception("DB error"))
        qb_invoice_data = {"Id": "qb_123", "TotalAmt": 1500.00}

        result = await invoice_service._update_single_invoice(existing_invoice, qb_invoice_data)

        assert result["synced_count"] == 0
        assert "Error updating invoice" in result["errors"][0]


class TestCreateSingleInvoice:
    """Test _create_single_invoice method."""

    @pytest.mark.asyncio
    async def test_create_single_invoice_success(self, invoice_service, mock_session, test_user):
        """Test successful invoice creation from QuickBooks data."""
        from Backend.models.lease import Lease, LeaseStatus

        tenant = create_test_tenant(quickbooks_customer_id="qb_cust_123")
        tenant.landlord_id = test_user.id
        lease = MagicMock(spec=Lease)
        lease.id = uuid4()
        lease.tenant_id = tenant.id
        lease.status = LeaseStatus.ACTIVE

        qb_invoice_data = {
            "Id": "qb_inv_123",
            "DocNumber": "INV-001",
            "TxnDate": "2024-06-01",
            "DueDate": "2024-07-01",
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "qb_cust_123"}
        }

        # Mock prefetch
        invoice_service._prefetch_tenants_and_leases = AsyncMock(
            return_value={"qb_cust_123": (tenant, lease)}
        )
        # Mock no duplicate invoice number
        mock_session.scalar = AsyncMock(return_value=None)

        result = await invoice_service._create_single_invoice(qb_invoice_data)

        assert result["synced_count"] == 1
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_create_single_invoice_no_tenant(self, invoice_service):
        """Test invoice creation fails when tenant not found."""
        qb_invoice_data = {
            "Id": "qb_inv_123",
            "CustomerRef": {"value": "unknown_cust"}
        }

        # No tenant found
        invoice_service._prefetch_tenants_and_leases = AsyncMock(return_value={})

        result = await invoice_service._create_single_invoice(qb_invoice_data)

        assert result["synced_count"] == 0
        assert "Could not resolve tenant/lease" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_create_single_invoice_duplicate_number(self, invoice_service, mock_session, test_user):
        """Test invoice creation generates unique number for duplicates."""
        from Backend.models.lease import Lease, LeaseStatus

        tenant = create_test_tenant(quickbooks_customer_id="qb_cust_123")
        tenant.landlord_id = test_user.id
        lease = MagicMock(spec=Lease)
        lease.id = uuid4()
        lease.tenant_id = tenant.id

        qb_invoice_data = {
            "Id": "qb_inv_123",
            "DocNumber": "INV-001",  # Duplicate
            "TotalAmt": 1200.00,
            "CustomerRef": {"value": "qb_cust_123"}
        }

        invoice_service._prefetch_tenants_and_leases = AsyncMock(
            return_value={"qb_cust_123": (tenant, lease)}
        )
        # First call returns existing ID (duplicate exists), second returns None
        mock_session.scalar = AsyncMock(side_effect=[1, None])

        result = await invoice_service._create_single_invoice(qb_invoice_data)

        # Should still succeed with generated unique number
        assert result["synced_count"] == 1

    @pytest.mark.asyncio
    async def test_create_single_invoice_exception(self, invoice_service, mock_session):
        """Test exception handling during invoice creation."""
        qb_invoice_data = {"Id": "qb_inv_123", "CustomerRef": {"value": "cust_1"}}
        invoice_service._prefetch_tenants_and_leases = AsyncMock(side_effect=Exception("DB error"))

        result = await invoice_service._create_single_invoice(qb_invoice_data)

        assert result["synced_count"] == 0
        assert "Error creating invoice" in result["errors"][0]


class TestPullInvoicesFromQuickBooks:
    """Test _pull_invoices_from_quickbooks method."""

    @pytest.mark.asyncio
    async def test_pull_invoices_no_response(self, invoice_service):
        """Test handling no response from QuickBooks."""
        invoice_service._client.list_invoices = AsyncMock(return_value=None)

        result = await invoice_service._pull_invoices_from_quickbooks()

        assert result["synced_count"] == 0
        assert "No invoices found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_pull_invoices_empty_list(self, invoice_service):
        """Test handling empty invoice list."""
        invoice_service._client.list_invoices = AsyncMock(return_value={
            "QueryResponse": {"Invoice": []}
        })

        result = await invoice_service._pull_invoices_from_quickbooks()

        assert result["synced_count"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_pull_invoices_skips_existing(self, invoice_service, mock_session, test_user):
        """Test that existing invoices are skipped."""
        from Backend.models.lease import Lease

        qb_invoices = [
            {"Id": "qb_1", "DocNumber": "INV-001", "CustomerRef": {"value": "cust_1"}, "TotalAmt": 100.00},
            {"Id": "qb_2", "DocNumber": "INV-002", "CustomerRef": {"value": "cust_2"}, "TotalAmt": 200.00}
        ]

        invoice_service._client.list_invoices = AsyncMock(return_value={
            "QueryResponse": {"Invoice": qb_invoices}
        })

        # Mock existing IDs check - qb_1 already exists
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([("qb_1",)]))

        # Mock invoice numbers check
        mock_numbers_result = MagicMock()
        mock_numbers_result.__iter__ = MagicMock(return_value=iter([]))

        mock_session.execute = AsyncMock(side_effect=[mock_execute_result, mock_numbers_result])

        # Mock tenant/lease prefetch
        tenant = create_test_tenant(quickbooks_customer_id="cust_2")
        tenant.landlord_id = test_user.id
        lease = MagicMock(spec=Lease)
        lease.id = uuid4()
        lease.tenant_id = tenant.id
        invoice_service._prefetch_tenants_and_leases = AsyncMock(
            return_value={"cust_2": (tenant, lease)}
        )

        result = await invoice_service._pull_invoices_from_quickbooks()

        # Only qb_2 should be synced (qb_1 exists)
        assert result["synced_count"] == 1

    @pytest.mark.asyncio
    async def test_pull_invoices_exception(self, invoice_service):
        """Test exception handling in pull invoices."""
        invoice_service._client.list_invoices = AsyncMock(side_effect=Exception("API error"))

        result = await invoice_service._pull_invoices_from_quickbooks()

        assert result["synced_count"] == 0
        assert "Pull invoices failed" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_pull_invoices_preview_mode(self, test_user, mock_session, mock_client):
        """Test pull invoices in preview mode."""
        from Backend.models.lease import Lease

        service = InvoiceService(test_user, mock_session, preview_mode=True)
        service._client = mock_client
        service.initialize = AsyncMock()

        tenant = create_test_tenant(quickbooks_customer_id="cust_1")
        tenant.landlord_id = test_user.id
        lease = MagicMock(spec=Lease)
        lease.id = uuid4()

        mock_client.list_invoices = AsyncMock(return_value={
            "QueryResponse": {"Invoice": [
                {"Id": "qb_1", "DocNumber": "INV-001", "CustomerRef": {"value": "cust_1"}, "TotalAmt": 100.00}
            ]}
        })

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        service._prefetch_tenants_and_leases = AsyncMock(
            return_value={"cust_1": (tenant, lease)}
        )

        result = await service._pull_invoices_from_quickbooks()

        # Preview mode should count but not commit
        assert result["synced_count"] == 1
        mock_session.commit.assert_not_called()


class TestPushInvoicesToQuickBooks:
    """Test _push_invoices_to_quickbooks method."""

    @pytest.mark.asyncio
    async def test_push_invoices_no_properties(self, invoice_service, mock_session):
        """Test when user has no properties."""
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        result = await invoice_service._push_invoices_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "No properties found" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_push_invoices_no_unsynced(self, invoice_service, mock_session):
        """Test when no unsynced invoices exist."""
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([]))

        result = await invoice_service._push_invoices_to_quickbooks()

        assert result["pushed_count"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_push_invoices_success(self, invoice_service, mock_session, test_user):
        """Test successful invoice push to QuickBooks."""
        invoice = create_test_invoice(quickbooks_id=None)
        tenant = create_test_tenant(quickbooks_customer_id="qb_cust_123")
        tenant.landlord_id = test_user.id

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([invoice]))

        invoice_service._prefetch_tenants_by_ids = AsyncMock(
            return_value={invoice.tenant_id: tenant}
        )
        invoice_service._get_or_cache_service_item = AsyncMock(return_value="1")
        invoice_service._get_or_cache_exempt_tax_code = AsyncMock(return_value="NON")
        invoice_service._retry_operation = AsyncMock(return_value={
            "Invoice": {"Id": "new_qb_id"}
        })

        result = await invoice_service._push_invoices_to_quickbooks()

        assert result["pushed_count"] == 1
        assert invoice.quickbooks_id == "new_qb_id"

    @pytest.mark.asyncio
    async def test_push_invoices_tenant_not_synced(self, invoice_service, mock_session, test_user):
        """Test push fails when tenant not synced."""
        invoice = create_test_invoice(quickbooks_id=None)
        tenant = create_test_tenant(quickbooks_customer_id=None)  # Not synced
        tenant.landlord_id = test_user.id

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([invoice]))

        invoice_service._prefetch_tenants_by_ids = AsyncMock(
            return_value={invoice.tenant_id: tenant}
        )
        invoice_service._get_or_cache_service_item = AsyncMock(return_value="1")
        invoice_service._get_or_cache_exempt_tax_code = AsyncMock(return_value="NON")

        result = await invoice_service._push_invoices_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "Tenant not synced" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_push_invoices_api_error(self, invoice_service, mock_session, test_user):
        """Test handling API error during push."""
        invoice = create_test_invoice(quickbooks_id=None)
        tenant = create_test_tenant(quickbooks_customer_id="qb_cust_123")
        tenant.landlord_id = test_user.id

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([invoice]))

        invoice_service._prefetch_tenants_by_ids = AsyncMock(
            return_value={invoice.tenant_id: tenant}
        )
        invoice_service._get_or_cache_service_item = AsyncMock(return_value="1")
        invoice_service._get_or_cache_exempt_tax_code = AsyncMock(return_value="NON")
        invoice_service._retry_operation = AsyncMock(return_value=None)  # Failed

        result = await invoice_service._push_invoices_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "Invalid QuickBooks response" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_push_invoices_exception(self, invoice_service, mock_session):
        """Test exception handling during push."""
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))

        result = await invoice_service._push_invoices_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "Push invoices failed" in result["errors"][0]


class TestUpdateInvoicesInQuickBooks:
    """Test _update_invoices_in_quickbooks method."""

    @pytest.mark.asyncio
    async def test_update_invoices_no_properties(self, invoice_service, mock_session):
        """Test when user has no properties."""
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        result = await invoice_service._update_invoices_in_quickbooks()

        assert result["updated_count"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_update_invoices_no_modified(self, invoice_service, mock_session):
        """Test when no invoices need updating."""
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([]))

        result = await invoice_service._update_invoices_in_quickbooks()

        assert result["updated_count"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_update_invoices_success(self, invoice_service, mock_session, test_user):
        """Test successful invoice update in QuickBooks."""
        invoice = create_test_invoice(quickbooks_id="qb_123")
        invoice.updated_at = FIXED_DATETIME + timedelta(hours=1)  # Modified after sync
        tenant = create_test_tenant(quickbooks_customer_id="qb_cust_123")
        tenant.landlord_id = test_user.id

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([invoice]))

        invoice_service._prefetch_tenants_by_ids = AsyncMock(
            return_value={invoice.tenant_id: tenant}
        )
        invoice_service._get_or_cache_service_item = AsyncMock(return_value="1")
        invoice_service._get_or_cache_exempt_tax_code = AsyncMock(return_value="NON")
        invoice_service._client.get_invoice = AsyncMock(return_value={
            "Invoice": {"Id": "qb_123", "SyncToken": "1"}
        })
        invoice_service._retry_operation = AsyncMock(return_value={
            "Invoice": {"Id": "qb_123"}
        })

        result = await invoice_service._update_invoices_in_quickbooks()

        assert result["updated_count"] == 1

    @pytest.mark.asyncio
    async def test_update_invoices_missing_sync_token(self, invoice_service, mock_session, test_user):
        """Test handling missing SyncToken."""
        invoice = create_test_invoice(quickbooks_id="qb_123")
        invoice.updated_at = FIXED_DATETIME + timedelta(hours=1)
        tenant = create_test_tenant(quickbooks_customer_id="qb_cust_123")
        tenant.landlord_id = test_user.id

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([invoice]))

        invoice_service._prefetch_tenants_by_ids = AsyncMock(
            return_value={invoice.tenant_id: tenant}
        )
        invoice_service._get_or_cache_service_item = AsyncMock(return_value="1")
        invoice_service._get_or_cache_exempt_tax_code = AsyncMock(return_value="NON")
        invoice_service._client.get_invoice = AsyncMock(return_value={
            "Invoice": {"Id": "qb_123"}  # Missing SyncToken
        })

        result = await invoice_service._update_invoices_in_quickbooks()

        assert result["updated_count"] == 0
        assert "missing SyncToken" in result["errors"][0]


class TestGetOrCacheServiceItem:
    """Test _get_or_cache_service_item method."""

    @pytest.mark.asyncio
    async def test_get_service_item_cached(self, invoice_service):
        """Test returning cached service item."""
        invoice_service._get_or_cache_quickbooks_data = AsyncMock(return_value="cached_item_id")

        result = await invoice_service._get_or_cache_service_item()

        assert result == "cached_item_id"


class TestGetOrCreateDefaultServiceItem:
    """Test _get_or_create_default_service_item method."""

    @pytest.mark.asyncio
    async def test_get_service_item_from_metadata(self, invoice_service):
        """Test returning service item from integration metadata."""
        invoice_service._get_cached_metadata = AsyncMock(return_value="metadata_item_id")

        result = await invoice_service._get_or_create_default_service_item()

        assert result == "metadata_item_id"

    @pytest.mark.asyncio
    async def test_find_existing_service_item(self, invoice_service):
        """Test finding existing service item in QuickBooks."""
        invoice_service._get_cached_metadata = AsyncMock(return_value=None)
        invoice_service._client.query_items = AsyncMock(return_value={
            "QueryResponse": {
                "Item": [
                    {"Id": "1", "Name": "Rent Service", "Type": "Service"},
                    {"Id": "2", "Name": "Other", "Type": "Service"}
                ]
            }
        })
        invoice_service._cache_metadata = AsyncMock()

        result = await invoice_service._get_or_create_default_service_item()

        assert result == "1"  # Should find "rent" item
        invoice_service._cache_metadata.assert_called()

    @pytest.mark.asyncio
    async def test_create_new_service_item(self, invoice_service):
        """Test creating new service item when none exists."""
        invoice_service._get_cached_metadata = AsyncMock(return_value=None)
        invoice_service._client.query_items = AsyncMock(return_value={
            "QueryResponse": {"Item": []}
        })
        invoice_service._get_default_income_account_id = AsyncMock(return_value="1")
        invoice_service._client.create_item = AsyncMock(return_value={
            "Item": {"Id": "new_item_id"}
        })
        invoice_service._cache_metadata = AsyncMock()

        result = await invoice_service._get_or_create_default_service_item()

        assert result == "new_item_id"

    @pytest.mark.asyncio
    async def test_fallback_to_default(self, invoice_service):
        """Test fallback to '1' on error."""
        invoice_service._get_cached_metadata = AsyncMock(return_value=None)
        invoice_service._client.query_items = AsyncMock(side_effect=Exception("API error"))

        result = await invoice_service._get_or_create_default_service_item()

        assert result == "1"


class TestGetDefaultIncomeAccountId:
    """Test _get_default_income_account_id method."""

    @pytest.mark.asyncio
    async def test_find_income_account(self, invoice_service):
        """Test finding income account."""
        invoice_service._client.query_accounts = AsyncMock(return_value={
            "QueryResponse": {
                "Account": [
                    {"Id": "5", "AccountType": "Income", "Name": "Rental Income"}
                ]
            }
        })

        result = await invoice_service._get_default_income_account_id()

        assert result == "5"

    @pytest.mark.asyncio
    async def test_fallback_to_first_account(self, invoice_service):
        """Test fallback to first account."""
        invoice_service._client.query_accounts = AsyncMock(return_value={
            "QueryResponse": {
                "Account": [
                    {"Id": "3", "AccountType": "Expense", "Name": "Operating"}
                ]
            }
        })

        result = await invoice_service._get_default_income_account_id()

        assert result == "3"

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, invoice_service):
        """Test fallback to '1' on error."""
        invoice_service._client.query_accounts = AsyncMock(side_effect=Exception("API error"))

        result = await invoice_service._get_default_income_account_id()

        assert result == "1"


class TestGetOrCacheExemptTaxCode:
    """Test _get_or_cache_exempt_tax_code method."""

    @pytest.mark.asyncio
    async def test_find_non_tax_code(self, invoice_service):
        """Test finding NON tax code."""
        async def mock_cache(key, func):
            return await func()

        invoice_service._get_or_cache_quickbooks_data = mock_cache
        invoice_service._client.query = AsyncMock(return_value={
            "QueryResponse": {
                "TaxCode": [
                    {"Id": "1", "Name": "TAX"},
                    {"Id": "2", "Name": "NON"}
                ]
            }
        })

        result = await invoice_service._get_or_cache_exempt_tax_code()

        assert result == "2"

    @pytest.mark.asyncio
    async def test_find_exempt_tax_code(self, invoice_service):
        """Test finding EXEMPT tax code when NON not available."""
        async def mock_cache(key, func):
            return await func()

        invoice_service._get_or_cache_quickbooks_data = mock_cache
        invoice_service._client.query = AsyncMock(return_value={
            "QueryResponse": {
                "TaxCode": [
                    {"Id": "1", "Name": "TAX"},
                    {"Id": "3", "Name": "EXEMPT"}
                ]
            }
        })

        result = await invoice_service._get_or_cache_exempt_tax_code()

        assert result == "3"

    @pytest.mark.asyncio
    async def test_no_exempt_code_found(self, invoice_service):
        """Test when no exempt tax code is found."""
        async def mock_cache(key, func):
            return await func()

        invoice_service._get_or_cache_quickbooks_data = mock_cache
        invoice_service._client.query = AsyncMock(return_value={
            "QueryResponse": {
                "TaxCode": [
                    {"Id": "1", "Name": "TAX"}
                ]
            }
        })

        result = await invoice_service._get_or_cache_exempt_tax_code()

        assert result is None
