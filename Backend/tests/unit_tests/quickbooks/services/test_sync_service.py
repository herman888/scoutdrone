"""
Unit tests for QuickBooksSyncService class.

Tests the sync service wrapper that provides high-level sync operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.quickbooks.services.sync_service import QuickBooksSyncService
from Backend.models.user import User
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


@pytest.fixture
def mock_session():
    """Mock AsyncSession for database operations."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_qb_service():
    """Mock QuickBooksService."""
    with patch('Backend.api.quickbooks.services.sync_service.QuickBooksService') as mock:
        mock_instance = AsyncMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def sync_service(mock_session, mock_qb_service):
    """Create QuickBooksSyncService with mocked dependencies."""
    user = create_test_user()
    service = QuickBooksSyncService(user, mock_session)
    service.qb_service = mock_qb_service
    return service


class TestQuickBooksSyncServiceInit:
    """Test QuickBooksSyncService initialization."""

    def test_init_creates_qb_service(self, mock_session):
        """Test that init creates QuickBooksService instance."""
        user = create_test_user()

        with patch('Backend.api.quickbooks.services.sync_service.QuickBooksService') as mock_qb:
            service = QuickBooksSyncService(user, mock_session)

            mock_qb.assert_called_once_with(user, mock_session)

    def test_init_stores_user_and_session(self, mock_session):
        """Test that init stores user and session."""
        user = create_test_user()

        with patch('Backend.api.quickbooks.services.sync_service.QuickBooksService'):
            service = QuickBooksSyncService(user, mock_session)

            assert service.user == user
            assert service.session == mock_session


class TestSyncCustomers:
    """Test sync_customers method."""

    @pytest.mark.asyncio
    async def test_sync_customers_delegates_to_qb_service(self, sync_service, mock_qb_service):
        """Test that sync_customers delegates to QuickBooksService."""
        expected_result = {"success": True, "synced_count": 5}
        mock_qb_service.sync_customers = AsyncMock(return_value=expected_result)

        result = await sync_service.sync_customers()

        mock_qb_service.sync_customers.assert_called_once()
        assert result == expected_result


class TestSyncPayments:
    """Test sync_payments method."""

    @pytest.mark.asyncio
    async def test_sync_payments_delegates_to_qb_service(self, sync_service, mock_qb_service):
        """Test that sync_payments delegates to QuickBooksService."""
        expected_result = {"success": True, "synced_count": 10}
        mock_qb_service.sync_payments = AsyncMock(return_value=expected_result)

        result = await sync_service.sync_payments()

        mock_qb_service.sync_payments.assert_called_once()
        assert result == expected_result


class TestSyncInvoices:
    """Test sync_invoices method."""

    @pytest.mark.asyncio
    async def test_sync_invoices_delegates_to_qb_service(self, sync_service, mock_qb_service):
        """Test that sync_invoices delegates to QuickBooksService."""
        expected_result = {"success": True, "synced_count": 15}
        mock_qb_service.sync_invoices = AsyncMock(return_value=expected_result)

        result = await sync_service.sync_invoices()

        mock_qb_service.sync_invoices.assert_called_once()
        assert result == expected_result


class TestSyncExpenses:
    """Test sync_expenses method."""

    @pytest.mark.asyncio
    async def test_sync_expenses_delegates_to_qb_service(self, sync_service, mock_qb_service):
        """Test that sync_expenses delegates to QuickBooksService."""
        expected_result = {"success": True, "synced_count": 8}
        mock_qb_service.sync_expenses = AsyncMock(return_value=expected_result)

        result = await sync_service.sync_expenses()

        mock_qb_service.sync_expenses.assert_called_once()
        assert result == expected_result


class TestPerformInitialSync:
    """Test perform_initial_sync method."""

    @pytest.mark.asyncio
    async def test_perform_initial_sync_delegates_to_sync_all(self, sync_service, mock_qb_service):
        """Test that perform_initial_sync delegates to perform_sync_all."""
        expected_result = {
            "success": True,
            "message": "Initial sync completed",
            "items_synced": 50
        }
        mock_qb_service.perform_sync_all = AsyncMock(return_value=expected_result)

        result = await sync_service.perform_initial_sync()

        mock_qb_service.perform_sync_all.assert_called_once()
        assert result == expected_result


class TestPerformSyncAll:
    """Test perform_sync_all method."""

    @pytest.mark.asyncio
    async def test_perform_sync_all_delegates_to_qb_service(self, sync_service, mock_qb_service):
        """Test that perform_sync_all delegates to QuickBooksService."""
        expected_result = {
            "success": True,
            "message": "Full sync completed",
            "items_synced": 100,
            "errors": []
        }
        mock_qb_service.perform_sync_all = AsyncMock(return_value=expected_result)

        result = await sync_service.perform_sync_all()

        mock_qb_service.perform_sync_all.assert_called_once()
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_perform_sync_all_with_errors(self, sync_service, mock_qb_service):
        """Test perform_sync_all when there are errors."""
        expected_result = {
            "success": False,
            "message": "Sync completed with errors",
            "items_synced": 80,
            "errors": ["Failed to sync 2 invoices"]
        }
        mock_qb_service.perform_sync_all = AsyncMock(return_value=expected_result)

        result = await sync_service.perform_sync_all()

        assert result["success"] is False
        assert len(result["errors"]) == 1


class TestPerformSyncTransactions:
    """Test perform_sync_transactions method."""

    @pytest.mark.asyncio
    async def test_perform_sync_transactions_delegates_to_qb_service(self, sync_service, mock_qb_service):
        """Test that perform_sync_transactions delegates to QuickBooksService."""
        expected_result = {
            "success": True,
            "message": "Transaction sync completed",
            "items_synced": 30,
            "errors": []
        }
        mock_qb_service.perform_sync_transactions = AsyncMock(return_value=expected_result)

        result = await sync_service.perform_sync_transactions()

        mock_qb_service.perform_sync_transactions.assert_called_once()
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_perform_sync_transactions_skips_customers(self, sync_service, mock_qb_service):
        """Test that transaction sync doesn't call customer sync."""
        expected_result = {
            "success": True,
            "message": "Transaction sync completed",
            "items_synced": 25
        }
        mock_qb_service.perform_sync_transactions = AsyncMock(return_value=expected_result)
        mock_qb_service.sync_customers = AsyncMock()

        result = await sync_service.perform_sync_transactions()

        # sync_customers should NOT be called
        mock_qb_service.sync_customers.assert_not_called()
        # perform_sync_transactions should be called
        mock_qb_service.perform_sync_transactions.assert_called_once()

    @pytest.mark.asyncio
    async def test_perform_sync_transactions_with_errors(self, sync_service, mock_qb_service):
        """Test transaction sync when there are errors."""
        expected_result = {
            "success": False,
            "message": "Transaction sync completed with errors",
            "items_synced": 20,
            "errors": ["Failed to sync expense 123", "Invoice 456 invalid"]
        }
        mock_qb_service.perform_sync_transactions = AsyncMock(return_value=expected_result)

        result = await sync_service.perform_sync_transactions()

        assert result["success"] is False
        assert len(result["errors"]) == 2


class TestSyncServiceErrorHandling:
    """Test error handling in sync service."""

    @pytest.mark.asyncio
    async def test_sync_customers_propagates_exception(self, sync_service, mock_qb_service):
        """Test that exceptions from QB service are propagated."""
        mock_qb_service.sync_customers = AsyncMock(
            side_effect=Exception("QuickBooks API error")
        )

        with pytest.raises(Exception, match="QuickBooks API error"):
            await sync_service.sync_customers()

    @pytest.mark.asyncio
    async def test_sync_invoices_propagates_exception(self, sync_service, mock_qb_service):
        """Test that exceptions from invoice sync are propagated."""
        mock_qb_service.sync_invoices = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        with pytest.raises(Exception, match="Connection timeout"):
            await sync_service.sync_invoices()

    @pytest.mark.asyncio
    async def test_sync_all_propagates_exception(self, sync_service, mock_qb_service):
        """Test that exceptions from full sync are propagated."""
        mock_qb_service.perform_sync_all = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(Exception, match="Database error"):
            await sync_service.perform_sync_all()
