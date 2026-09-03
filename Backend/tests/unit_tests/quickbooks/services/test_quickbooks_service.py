"""
Unit tests for QuickBooks QuickBooksService class.

Tests the main coordinator service that orchestrates all entity-specific services.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.quickbooks.services.quickbooks_service import QuickBooksService
from Backend.models.user import User
from Backend.models.accounting.integration import Integration, IntegrationStatus, IntegrationType
from Backend.models.enums import UserType

# Mark all tests in this module as unit tests
pytestmark = pytest.mark.unit

# Fixed datetime for deterministic testing
FIXED_DATETIME = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


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


def create_test_integration(user_id=None, status=IntegrationStatus.CONNECTED):
    """Helper function to create a test integration."""
    integration = MagicMock(spec=Integration)
    integration.id = 1
    integration.user_id = user_id or uuid4()
    integration.integration_type = IntegrationType.QUICKBOOKS
    integration.status = status
    integration.last_sync_at = FIXED_DATETIME
    integration.connected_at = FIXED_DATETIME
    integration.connection_metadata = {"company_name": "Test Company"}
    return integration


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
    session.in_transaction = MagicMock(return_value=False)
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
def quickbooks_service(test_user, mock_session, mock_client):
    """Create QuickBooksService instance with mocked dependencies."""
    service = QuickBooksService(test_user, mock_session)
    service._client = mock_client
    service.initialize = AsyncMock()
    service.integration = create_test_integration(test_user.id)
    return service


class TestQuickBooksServiceInitialization:
    """Test QuickBooksService initialization."""

    def test_quickbooks_service_creation(self, test_user, mock_session):
        """Test QuickBooksService can be created."""
        service = QuickBooksService(test_user, mock_session)
        assert service.user == test_user
        assert service.session == mock_session
        assert service.customer_service is not None
        assert service.invoice_service is not None
        assert service.payment_service is not None
        assert service.expense_service is not None


class TestGetConnectionStatus:
    """Test get_connection_status method."""

    @pytest.mark.asyncio
    async def test_get_connection_status_connected(self, quickbooks_service):
        """Test getting connected status."""
        integration = MagicMock()
        # Mock the status.value correctly
        integration.status.value = "connected"
        integration.last_sync_at = FIXED_DATETIME
        integration.connected_at = FIXED_DATETIME
        integration.connection_metadata = {"company_name": "Test Company"}
        quickbooks_service._get_user_integration = AsyncMock(return_value=integration)

        result = await quickbooks_service.get_connection_status()

        assert result["connected"] is True
        assert result["status"] == "connected"
        assert result["company_name"] == "Test Company"

    @pytest.mark.asyncio
    async def test_get_connection_status_not_configured(self, quickbooks_service):
        """Test status when integration not configured."""
        quickbooks_service._get_user_integration = AsyncMock(return_value=None)

        result = await quickbooks_service.get_connection_status()

        assert result["connected"] is False
        assert result["status"] == "not_configured"

    @pytest.mark.asyncio
    async def test_get_connection_status_disconnected(self, quickbooks_service):
        """Test status when integration is disconnected."""
        integration = MagicMock()
        integration.status.value = "disconnected"
        integration.last_sync_at = None
        integration.connected_at = None
        integration.connection_metadata = {}
        quickbooks_service._get_user_integration = AsyncMock(return_value=integration)

        result = await quickbooks_service.get_connection_status()

        assert result["connected"] is False
        assert result["status"] == "disconnected"


class TestSyncCustomers:
    """Test sync_customers method."""

    @pytest.mark.asyncio
    async def test_sync_customers_delegates_to_service(self, quickbooks_service):
        """Test that sync_customers delegates to customer_service."""
        quickbooks_service.customer_service.sync_customers = AsyncMock(return_value={
            "success": True,
            "synced_count": 5
        })

        result = await quickbooks_service.sync_customers()

        quickbooks_service.customer_service.sync_customers.assert_called_once()
        assert result["success"] is True
        assert result["synced_count"] == 5


class TestSyncInvoices:
    """Test sync_invoices method."""

    @pytest.mark.asyncio
    async def test_sync_invoices_delegates_to_service(self, quickbooks_service):
        """Test that sync_invoices delegates to invoice_service."""
        quickbooks_service.invoice_service.sync_invoices = AsyncMock(return_value={
            "success": True,
            "synced_count": 3
        })

        result = await quickbooks_service.sync_invoices()

        quickbooks_service.invoice_service.sync_invoices.assert_called_once()
        assert result["success"] is True


class TestSyncPayments:
    """Test sync_payments method."""

    @pytest.mark.asyncio
    async def test_sync_payments_delegates_to_service(self, quickbooks_service):
        """Test that sync_payments delegates to payment_service."""
        quickbooks_service.payment_service.sync_payments = AsyncMock(return_value={
            "success": True,
            "synced_count": 2
        })

        result = await quickbooks_service.sync_payments()

        quickbooks_service.payment_service.sync_payments.assert_called_once()
        assert result["success"] is True


class TestSyncExpenses:
    """Test sync_expenses method."""

    @pytest.mark.asyncio
    async def test_sync_expenses_delegates_to_service(self, quickbooks_service):
        """Test that sync_expenses delegates to expense_service."""
        quickbooks_service.expense_service.sync_expenses = AsyncMock(return_value={
            "success": True,
            "synced_count": 4
        })

        result = await quickbooks_service.sync_expenses()

        quickbooks_service.expense_service.sync_expenses.assert_called_once()
        assert result["success"] is True


class TestCreateExpense:
    """Test create_expense method."""

    @pytest.mark.asyncio
    async def test_create_expense_delegates_to_service(self, quickbooks_service):
        """Test that create_expense delegates to expense_service."""
        expense_data = {"amount": 100, "description": "Test"}
        quickbooks_service.expense_service.create_expense_in_quickbooks = AsyncMock(return_value={
            "success": True,
            "quickbooks_id": "qb_123"
        })

        result = await quickbooks_service.create_expense(expense_data)

        quickbooks_service.expense_service.create_expense_in_quickbooks.assert_called_once_with(expense_data)
        assert result["success"] is True


class TestPerformSyncAll:
    """Test perform_sync_all method."""

    @pytest.mark.asyncio
    async def test_perform_sync_all_success(self, quickbooks_service, mock_session):
        """Test successful comprehensive sync."""
        quickbooks_service.customer_service.sync_customers = AsyncMock(return_value={
            "success": True, "synced_count": 2, "errors": []
        })
        quickbooks_service.payment_service.sync_payments = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.invoice_service.sync_invoices = AsyncMock(return_value={
            "success": True, "synced_count": 3, "errors": []
        })
        quickbooks_service.expense_service.sync_expenses = AsyncMock(return_value={
            "success": True, "synced_count": 2, "errors": []
        })
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_all()

        assert result["success"] is True
        assert result["items_synced"] == 8
        assert "customers" in result["sync_details"]
        assert "payments" in result["sync_details"]
        assert "invoices" in result["sync_details"]
        assert "expenses" in result["sync_details"]

    @pytest.mark.asyncio
    async def test_perform_sync_all_customer_failure_stops_sync(self, quickbooks_service, mock_session):
        """Test that customer sync failure stops other syncs."""
        quickbooks_service.customer_service.sync_customers = AsyncMock(return_value={
            "success": False, "synced_count": 0, "errors": ["Customer sync failed"]
        })
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_all()

        assert result["success"] is False
        assert "Customer sync required" in result["message"]

    @pytest.mark.asyncio
    async def test_perform_sync_all_partial_errors(self, quickbooks_service, mock_session):
        """Test sync with partial errors."""
        quickbooks_service.customer_service.sync_customers = AsyncMock(return_value={
            "success": True, "synced_count": 2, "errors": []
        })
        quickbooks_service.payment_service.sync_payments = AsyncMock(return_value={
            "success": False, "synced_count": 0, "errors": ["Payment error"]
        })
        quickbooks_service.invoice_service.sync_invoices = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.expense_service.sync_expenses = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_all()

        assert result["success"] is False
        assert "Payment error" in result["errors"]
        assert result["items_synced"] == 4

    @pytest.mark.asyncio
    async def test_perform_sync_all_exception(self, quickbooks_service, mock_session):
        """Test sync with exception."""
        quickbooks_service.customer_service.sync_customers = AsyncMock(
            side_effect=Exception("Critical error")
        )

        result = await quickbooks_service.perform_sync_all()

        assert result["success"] is False
        assert "Sync failed" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_perform_sync_all_in_transaction(self, quickbooks_service, mock_session):
        """Test sync when already in transaction."""
        mock_session.in_transaction = MagicMock(return_value=True)
        quickbooks_service.customer_service.sync_customers = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.payment_service.sync_payments = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.invoice_service.sync_invoices = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.expense_service.sync_expenses = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_all()

        # Should still succeed
        assert result["success"] is True


class TestPerformSyncTransactions:
    """Test perform_sync_transactions method."""

    @pytest.mark.asyncio
    async def test_sync_transactions_success(self, quickbooks_service, mock_session):
        """Test successful transaction-only sync."""
        # Note: The service uses sync_payments, sync_invoices, sync_expenses which calls sub-services
        # We need to mock the service's own method that _perform_transaction_sync_operations calls
        quickbooks_service.sync_payments = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.sync_invoices = AsyncMock(return_value={
            "success": True, "synced_count": 2, "errors": []
        })
        quickbooks_service.sync_expenses = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_transactions()

        assert result["success"] is True
        assert result["items_synced"] == 4

    @pytest.mark.asyncio
    async def test_sync_transactions_with_errors(self, quickbooks_service, mock_session):
        """Test transaction sync with errors."""
        quickbooks_service.sync_payments = AsyncMock(return_value={
            "success": False, "synced_count": 0, "errors": ["Payment sync error"]
        })
        quickbooks_service.sync_invoices = AsyncMock(return_value={
            "success": True, "synced_count": 2, "errors": []
        })
        quickbooks_service.sync_expenses = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_transactions()

        assert result["success"] is False
        assert "Payment sync error" in result["errors"]

    @pytest.mark.asyncio
    async def test_sync_transactions_exception_in_payments(self, quickbooks_service, mock_session):
        """Test transaction sync when payment sync throws exception."""
        quickbooks_service.sync_payments = AsyncMock(
            side_effect=Exception("Payment API error")
        )
        quickbooks_service.sync_invoices = AsyncMock(return_value={
            "success": True, "synced_count": 2, "errors": []
        })
        quickbooks_service.sync_expenses = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_transactions()

        # Should continue with other syncs
        assert result["items_synced"] == 3
        assert any("Payment sync failed" in err for err in result["errors"])

    @pytest.mark.asyncio
    async def test_sync_transactions_exception_in_invoices(self, quickbooks_service, mock_session):
        """Test transaction sync when invoice sync throws exception."""
        quickbooks_service.sync_payments = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.sync_invoices = AsyncMock(
            side_effect=Exception("Invoice API error")
        )
        quickbooks_service.sync_expenses = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_transactions()

        assert result["items_synced"] == 2
        assert any("Invoice sync failed" in err for err in result["errors"])

    @pytest.mark.asyncio
    async def test_sync_transactions_exception_in_expenses(self, quickbooks_service, mock_session):
        """Test transaction sync when expense sync throws exception."""
        quickbooks_service.sync_payments = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.sync_invoices = AsyncMock(return_value={
            "success": True, "synced_count": 2, "errors": []
        })
        quickbooks_service.sync_expenses = AsyncMock(
            side_effect=Exception("Expense API error")
        )
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_transactions()

        assert result["items_synced"] == 3
        assert any("Expense sync failed" in err for err in result["errors"])

    @pytest.mark.asyncio
    async def test_sync_transactions_in_existing_transaction(self, quickbooks_service, mock_session):
        """Test transaction sync when already in transaction."""
        mock_session.in_transaction = MagicMock(return_value=True)
        quickbooks_service.sync_payments = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.sync_invoices = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.sync_expenses = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service._log_operation = MagicMock()

        result = await quickbooks_service.perform_sync_transactions()

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_sync_transactions_critical_exception(self, quickbooks_service, mock_session):
        """Test transaction sync with critical unhandled exception."""
        quickbooks_service.sync_payments = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.sync_invoices = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        quickbooks_service.sync_expenses = AsyncMock(return_value={
            "success": True, "synced_count": 1, "errors": []
        })
        # Simulate exception in _perform_transaction_sync_operations wrapper
        mock_session.in_transaction = MagicMock(side_effect=Exception("DB connection error"))

        result = await quickbooks_service.perform_sync_transactions()

        assert result["success"] is False
        assert "Sync failed" in result["errors"][0]


class TestLinkOrCreateCustomer:
    """Test link_or_create_customer method."""

    @pytest.mark.asyncio
    async def test_link_or_create_customer_delegates(self, quickbooks_service):
        """Test that link_or_create_customer delegates to customer_service."""
        tenant_data = {"email": "test@example.com", "first_name": "John"}
        quickbooks_service.customer_service.link_or_create_qb_customer = AsyncMock(return_value="qb_123")

        result = await quickbooks_service.link_or_create_customer(tenant_data)

        quickbooks_service.customer_service.link_or_create_qb_customer.assert_called_once_with(tenant_data)
        assert result == "qb_123"
