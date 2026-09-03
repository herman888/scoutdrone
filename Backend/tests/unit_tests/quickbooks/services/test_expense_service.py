"""
Unit tests for QuickBooks ExpenseService class.

Tests expense synchronization functionality including pulling from QuickBooks,
pushing to QuickBooks, and bidirectional sync operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, UTC
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.quickbooks.services.expense_service import ExpenseService
from Backend.api.quickbooks.services.base_service import SyncPreview
from Backend.models.user import User
from Backend.models.property import Property, PropertyType
from Backend.models.accounting.expense import Expense
from Backend.models.accounting.payment import PaymentMethod
from Backend.models.enums import UserType, PropertyStatus

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


def create_test_expense(expense_id=None, property_id=None, quickbooks_id=None):
    """Helper function to create a test expense."""
    return Expense(
        id=expense_id or uuid4(),
        description="Test Expense",
        expense_date=FIXED_DATETIME,
        subtotal_amount=Decimal("100.00"),
        total_tax_amount=Decimal("0.00"),
        category="maintenance",
        payment_method=PaymentMethod.CREDIT_CARD,
        property_id=property_id or 1,
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
def expense_service(test_user, mock_session, mock_client):
    """Create ExpenseService instance with mocked dependencies."""
    service = ExpenseService(test_user, mock_session)
    service._client = mock_client
    service.initialize = AsyncMock()
    return service


class TestExpenseServiceInitialization:
    """Test ExpenseService initialization."""

    def test_expense_service_creation(self, test_user, mock_session):
        """Test ExpenseService can be created."""
        service = ExpenseService(test_user, mock_session)
        assert service.user == test_user
        assert service.session == mock_session
        assert service._client is None

    def test_expense_service_preview_mode(self, test_user, mock_session):
        """Test ExpenseService in preview mode."""
        service = ExpenseService(test_user, mock_session, preview_mode=True)
        assert service.preview_mode is True


class TestSyncExpenses:
    """Test the main sync_expenses method."""

    @pytest.mark.asyncio
    async def test_sync_expenses_calls_internal(self, expense_service):
        """Test that sync_expenses calls the internal method."""
        expense_service.sync_expenses_internal = AsyncMock(return_value={
            "success": True,
            "synced_count": 5,
            "errors": []
        })

        result = await expense_service.sync_expenses()

        expense_service.sync_expenses_internal.assert_called_once()
        assert result["success"] is True
        assert result["synced_count"] == 5


class TestPreviewExpenses:
    """Test expense preview functionality."""

    @pytest.mark.asyncio
    async def test_preview_expenses_creates_preview_service(self, expense_service):
        """Test that preview creates a separate service instance."""
        with patch.object(ExpenseService, '__init__', return_value=None), \
             patch.object(ExpenseService, 'initialize', new_callable=AsyncMock), \
             patch.object(ExpenseService, 'sync_expenses_internal', new_callable=AsyncMock), \
             patch.object(ExpenseService, '_generate_preview') as mock_gen:

            mock_gen.return_value = SyncPreview(
                items=[],
                summary={"total": 0},
                warnings=[]
            )

            result = await expense_service.preview_expenses()

            assert isinstance(result, SyncPreview)


class TestSyncExpensesInternal:
    """Test the internal expense synchronization logic."""

    @pytest.mark.asyncio
    async def test_sync_expenses_internal_success(self, expense_service):
        """Test successful internal expense synchronization."""
        expense_service._pull_expenses_from_quickbooks = AsyncMock(return_value={
            "synced_count": 3,
            "errors": []
        })
        expense_service._push_expenses_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 2,
            "errors": []
        })
        expense_service._update_integration_sync_time = AsyncMock()
        expense_service._log_operation = MagicMock()

        result = await expense_service.sync_expenses_internal()

        assert result["success"] is True
        assert result["synced_count"] == 5
        assert result["pulled_count"] == 3
        assert result["pushed_count"] == 2
        expense_service._update_integration_sync_time.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_expenses_internal_with_errors(self, expense_service):
        """Test internal synchronization with errors."""
        expense_service._pull_expenses_from_quickbooks = AsyncMock(return_value={
            "synced_count": 1,
            "errors": ["Pull error"]
        })
        expense_service._push_expenses_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 0,
            "errors": ["Push error"]
        })
        expense_service._update_integration_sync_time = AsyncMock()
        expense_service._log_operation = MagicMock()

        result = await expense_service.sync_expenses_internal()

        assert result["success"] is False
        assert result["synced_count"] == 1
        assert len(result["errors"]) == 2
        expense_service._update_integration_sync_time.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_expenses_internal_exception_handling(self, expense_service):
        """Test exception handling in internal sync."""
        expense_service._pull_expenses_from_quickbooks = AsyncMock(
            side_effect=Exception("Test error")
        )

        result = await expense_service.sync_expenses_internal()

        assert result["success"] is False
        assert "Expense sync failed: Test error" in result["errors"]


class TestSyncSingleExpense:
    """Test single expense sync from webhook."""

    @pytest.mark.asyncio
    async def test_sync_single_expense_new(self, expense_service, mock_session):
        """Test syncing a new expense from webhook."""
        qb_expense = {
            "Id": "qb_123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 150.00,
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 150.00,
                "Description": "Office supplies"
            }],
            "PaymentType": "CreditCard"
        }

        # No existing expense
        mock_session.scalar = AsyncMock(return_value=None)

        # Mock _create_single_expense
        expense_service._create_single_expense = AsyncMock(return_value={
            "synced_count": 1,
            "errors": []
        })

        result = await expense_service.sync_single_expense_from_quickbooks(qb_expense)

        assert result["synced_count"] == 1
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_sync_single_expense_update_existing(self, expense_service, mock_session):
        """Test updating an existing expense from webhook."""
        qb_expense = {
            "Id": "qb_123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 200.00,
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 200.00
            }],
            "PaymentType": "CreditCard"
        }

        existing_expense = create_test_expense(quickbooks_id="qb_123")
        mock_session.scalar = AsyncMock(return_value=existing_expense)

        # Mock _update_single_expense
        expense_service._update_single_expense = AsyncMock(return_value={
            "synced_count": 1,
            "errors": []
        })

        result = await expense_service.sync_single_expense_from_quickbooks(qb_expense)

        assert result["synced_count"] == 1

    @pytest.mark.asyncio
    async def test_sync_single_expense_missing_id(self, expense_service):
        """Test handling expense with missing ID."""
        qb_expense = {"TotalAmt": 100.00}  # Missing Id

        result = await expense_service.sync_single_expense_from_quickbooks(qb_expense)

        assert result["synced_count"] == 0
        assert "Expense data missing ID" in result["errors"]


class TestPullExpensesFromQuickBooks:
    """Test pulling expenses from QuickBooks."""

    @pytest.mark.asyncio
    async def test_pull_expenses_no_purchases(self, expense_service):
        """Test when no purchases exist in QuickBooks."""
        # Use _client instead of client property
        expense_service._client.list_purchases = AsyncMock(return_value=None)

        result = await expense_service._pull_expenses_from_quickbooks()

        assert result["synced_count"] == 0
        assert "No purchases found in QuickBooks" in result["errors"]

    @pytest.mark.asyncio
    async def test_pull_expenses_empty_response(self, expense_service):
        """Test when QuickBooks returns empty purchase list."""
        expense_service._client.list_purchases = AsyncMock(return_value={
            "QueryResponse": {"Purchase": []}
        })

        result = await expense_service._pull_expenses_from_quickbooks()

        assert result["synced_count"] == 0
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_pull_expenses_exception_handling(self, expense_service):
        """Test exception handling in pull expenses."""
        expense_service._client.list_purchases = AsyncMock(side_effect=Exception("API error"))

        result = await expense_service._pull_expenses_from_quickbooks()

        assert result["synced_count"] == 0
        assert "Pull expenses failed: API error" in result["errors"]


class TestPushExpensesToQuickBooks:
    """Test pushing expenses to QuickBooks."""

    @pytest.mark.asyncio
    async def test_push_expenses_no_properties(self, expense_service, mock_session):
        """Test when user has no properties."""
        # Mock empty property list
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        result = await expense_service._push_expenses_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "No properties found" in str(result["errors"])

    @pytest.mark.asyncio
    async def test_push_expenses_no_unsynced(self, expense_service, mock_session):
        """Test when no unsynced expenses exist."""
        # Mock property IDs
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock empty unsynced expenses
        mock_session.scalars = AsyncMock(return_value=[])

        result = await expense_service._push_expenses_to_quickbooks()

        assert result["pushed_count"] == 0
        assert result["errors"] == []


class TestExpenseServiceHelperMethods:
    """Test helper methods in ExpenseService."""

    @pytest.mark.asyncio
    async def test_get_or_cache_default_accounts(self, expense_service):
        """Test account caching."""
        expense_service._get_session_cache = MagicMock(return_value=None)
        expense_service._set_session_cache = MagicMock()
        expense_service._get_default_accounts = AsyncMock(return_value=("1", "2"))

        result = await expense_service._get_or_cache_default_accounts()

        assert result == ("1", "2")
        expense_service._set_session_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_cache_default_accounts_uses_cache(self, expense_service):
        """Test that cached accounts are returned."""
        expense_service._get_session_cache = MagicMock(return_value=("cached_1", "cached_2"))

        result = await expense_service._get_or_cache_default_accounts()

        assert result == ("cached_1", "cached_2")


class TestExpenseServiceLogging:
    """Test logging functionality in ExpenseService."""

    @pytest.mark.asyncio
    async def test_operation_logging(self, expense_service):
        """Test that operations are properly logged."""
        expense_service._pull_expenses_from_quickbooks = AsyncMock(return_value={
            "synced_count": 2,
            "errors": []
        })
        expense_service._push_expenses_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 1,
            "errors": []
        })
        expense_service._update_integration_sync_time = AsyncMock()
        expense_service._log_operation = MagicMock()

        await expense_service.sync_expenses_internal()

        expense_service._log_operation.assert_called_once_with(
            operation="sync_expenses",
            level="info",
            synced_count=3,
            pulled_count=2,
            pushed_count=1,
            error_count=0
        )

    @pytest.mark.asyncio
    async def test_error_logging(self, expense_service):
        """Test error logging functionality."""
        expense_service._pull_expenses_from_quickbooks = AsyncMock(return_value={
            "synced_count": 0,
            "errors": ["Test error"]
        })
        expense_service._push_expenses_to_quickbooks = AsyncMock(return_value={
            "pushed_count": 0,
            "errors": []
        })
        expense_service._log_operation = MagicMock()

        await expense_service.sync_expenses_internal()

        expense_service._log_operation.assert_called_once_with(
            operation="sync_expenses",
            level="warning",
            synced_count=0,
            pulled_count=0,
            pushed_count=0,
            error_count=1
        )


class TestCreateExpenseInQuickBooks:
    """Test creating expense directly in QuickBooks."""

    @pytest.mark.asyncio
    async def test_create_expense_success(self, expense_service, mock_client):
        """Test successful expense creation."""
        expense_data = {
            "total_amount": 100.00,
            "expense_date": "2024-06-01",
            "description": "Test expense",
            "category": "office"
        }

        expense_service._get_default_accounts = AsyncMock(return_value=("1", "2"))
        expense_service._retry_operation = AsyncMock(return_value={
            "Purchase": {"Id": "new_qb_id"}
        })
        expense_service._log_operation = MagicMock()

        result = await expense_service.create_expense_in_quickbooks(expense_data)

        assert result["success"] is True
        assert result["quickbooks_id"] == "new_qb_id"

    @pytest.mark.asyncio
    async def test_create_expense_invalid_amount(self, expense_service):
        """Test expense creation with invalid amount."""
        expense_data = {
            "total_amount": 0,
            "description": "Zero amount expense"
        }

        result = await expense_service.create_expense_in_quickbooks(expense_data)

        assert result["success"] is False
        assert "Invalid expense amount" in result["message"]

    @pytest.mark.asyncio
    async def test_create_expense_api_failure(self, expense_service):
        """Test expense creation with API failure."""
        expense_data = {
            "total_amount": 100.00,
            "description": "Test expense"
        }

        expense_service._get_default_accounts = AsyncMock(return_value=("1", "2"))
        expense_service._retry_operation = AsyncMock(return_value=None)
        expense_service._log_operation = MagicMock()

        result = await expense_service.create_expense_in_quickbooks(expense_data)

        assert result["success"] is False
        assert result["quickbooks_id"] is None


class TestPreviewMode:
    """Test preview mode functionality."""

    @pytest.mark.asyncio
    async def test_preview_mode_no_commit(self, test_user, mock_session, mock_client):
        """Test that preview mode doesn't commit changes."""
        service = ExpenseService(test_user, mock_session, preview_mode=True)
        service._client = mock_client
        service.initialize = AsyncMock()

        # Mock QB response
        mock_client.list_purchases = AsyncMock(return_value={
            "QueryResponse": {
                "Purchase": [{
                    "Id": "1",
                    "TxnDate": "2024-06-01",
                    "TotalAmt": 100.00,
                    "Line": [{"DetailType": "AccountBasedExpenseLineDetail", "Amount": 100.00}]
                }]
            }
        })

        # Mock existing expense check
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock tax account mapping
        service._get_or_cache_tax_account_mapping = AsyncMock(return_value={})

        result = await service._pull_expenses_from_quickbooks()

        # In preview mode, should not commit
        mock_session.commit.assert_not_called()
        # But should count the expense
        assert result["synced_count"] == 1


class TestCreateSingleExpense:
    """Test _create_single_expense method."""

    @pytest.mark.asyncio
    async def test_create_single_expense_success(self, expense_service, mock_session, test_user):
        """Test successful expense creation from QuickBooks data."""
        from unittest.mock import patch
        from Backend.api.quickbooks.services.account_mapping_service import AccountMappingService

        qb_expense_data = {
            "Id": "qb_exp_123",
            "TxnDate": "2024-06-01",
            "TotalAmt": 150.00,
            "PaymentType": "CreditCard",
            "Line": [{
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": 150.00,
                "Description": "Office supplies"
            }]
        }

        # Mock AccountMappingService
        with patch.object(AccountMappingService, 'get_tax_account_id_mapping', new_callable=AsyncMock) as mock_mapping:
            mock_mapping.return_value = {}
            result = await expense_service._create_single_expense(qb_expense_data)

        assert result["synced_count"] == 1
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_create_single_expense_exception(self, expense_service, mock_session):
        """Test exception handling during expense creation."""
        from unittest.mock import patch
        from Backend.api.quickbooks.services.account_mapping_service import AccountMappingService

        qb_expense_data = {"Id": "qb_exp_123", "TotalAmt": 100.00}

        # Mock AccountMappingService to raise exception
        with patch.object(AccountMappingService, 'get_tax_account_id_mapping', new_callable=AsyncMock) as mock_mapping:
            mock_mapping.side_effect = Exception("Mapping error")
            result = await expense_service._create_single_expense(qb_expense_data)

        assert result["synced_count"] == 0
        assert "Error creating expense" in result["errors"][0]


class TestUpdateSingleExpense:
    """Test _update_single_expense method."""

    @pytest.mark.asyncio
    async def test_update_single_expense_success(self, expense_service, mock_session):
        """Test successful expense update from QuickBooks data."""
        existing_expense = create_test_expense(quickbooks_id="qb_123")
        # Ensure total_tax_amount is set to avoid subtraction with None
        existing_expense.total_tax_amount = Decimal("0")
        qb_expense_data = {
            "Id": "qb_123",
            "TotalAmt": 200.00,
            "TxnDate": "2024-07-15"
        }

        result = await expense_service._update_single_expense(existing_expense, qb_expense_data)

        assert result["synced_count"] == 1
        assert result["errors"] == []
        mock_session.add.assert_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_single_expense_exception(self, expense_service, mock_session):
        """Test exception handling during expense update."""
        existing_expense = create_test_expense(quickbooks_id="qb_123")
        existing_expense.total_tax_amount = Decimal("0")
        mock_session.commit = AsyncMock(side_effect=Exception("DB error"))
        qb_expense_data = {"Id": "qb_123", "TotalAmt": 200.00}

        result = await expense_service._update_single_expense(existing_expense, qb_expense_data)

        assert result["synced_count"] == 0
        assert "Error updating expense" in result["errors"][0]


class TestPullExpensesWithData:
    """Test _pull_expenses_from_quickbooks with actual data."""

    @pytest.mark.asyncio
    async def test_pull_expenses_skips_existing(self, expense_service, mock_session, test_user):
        """Test that existing expenses are skipped."""
        qb_purchases = [
            {"Id": "qb_1", "TotalAmt": 100.00, "TxnDate": "2024-06-01"},
            {"Id": "qb_2", "TotalAmt": 200.00, "TxnDate": "2024-06-02"}
        ]

        expense_service._client.list_purchases = AsyncMock(return_value={
            "QueryResponse": {"Purchase": qb_purchases}
        })

        # Mock existing IDs check - qb_1 already exists
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([("qb_1",)]))

        # Mock property IDs
        mock_property_result = MagicMock()
        mock_property_result.__iter__ = MagicMock(return_value=iter([(1,)]))

        mock_session.execute = AsyncMock(side_effect=[mock_execute_result, mock_property_result])

        expense_service._get_or_cache_tax_account_mapping = AsyncMock(return_value={})

        result = await expense_service._pull_expenses_from_quickbooks()

        # Only qb_2 should be synced (qb_1 exists)
        assert result["synced_count"] == 1

    @pytest.mark.asyncio
    async def test_pull_expenses_with_tax_mapping(self, expense_service, mock_session, test_user):
        """Test pull expenses applies tax account mapping."""
        qb_purchases = [
            {
                "Id": "qb_1",
                "TotalAmt": 105.00,
                "TxnDate": "2024-06-01",
                "Line": [
                    {"Amount": 100.00, "DetailType": "AccountBasedExpenseLineDetail"},
                    {"Amount": 5.00, "DetailType": "AccountBasedExpenseLineDetail",
                     "AccountBasedExpenseLineDetail": {"AccountRef": {"value": "999"}}}
                ]
            }
        ]

        expense_service._client.list_purchases = AsyncMock(return_value={
            "QueryResponse": {"Purchase": qb_purchases}
        })

        # Mock no existing
        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([]))
        mock_property_result = MagicMock()
        mock_property_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(side_effect=[mock_execute_result, mock_property_result])

        # Tax account mapping
        expense_service._get_or_cache_tax_account_mapping = AsyncMock(return_value={"999": "GST"})

        result = await expense_service._pull_expenses_from_quickbooks()

        assert result["synced_count"] == 1


class TestPushExpensesWithData:
    """Test _push_expenses_to_quickbooks with actual data."""

    @pytest.mark.asyncio
    async def test_push_expenses_success(self, expense_service, mock_session, test_user):
        """Test successful expense push to QuickBooks."""
        expense = create_test_expense(quickbooks_id=None)

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([expense]))

        expense_service._get_or_cache_default_accounts = AsyncMock(return_value=("1", "2"))
        expense_service._get_or_cache_tax_account_mapping = AsyncMock(return_value={})
        expense_service._retry_operation = AsyncMock(return_value={
            "Purchase": {"Id": "new_qb_id"}
        })

        result = await expense_service._push_expenses_to_quickbooks()

        assert result["pushed_count"] == 1
        assert expense.quickbooks_id == "new_qb_id"

    @pytest.mark.asyncio
    async def test_push_expenses_api_error(self, expense_service, mock_session, test_user):
        """Test handling API error during push."""
        expense = create_test_expense(quickbooks_id=None)

        mock_execute_result = MagicMock()
        mock_execute_result.__iter__ = MagicMock(return_value=iter([(1,)]))
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.scalars = AsyncMock(return_value=iter([expense]))

        expense_service._get_or_cache_default_accounts = AsyncMock(return_value=("1", "2"))
        expense_service._get_or_cache_tax_account_mapping = AsyncMock(return_value={})
        expense_service._retry_operation = AsyncMock(return_value=None)  # Failed

        result = await expense_service._push_expenses_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "Invalid QuickBooks response" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_push_expenses_exception(self, expense_service, mock_session):
        """Test exception handling during push."""
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))

        result = await expense_service._push_expenses_to_quickbooks()

        assert result["pushed_count"] == 0
        assert "Push expenses failed" in result["errors"][0]


class TestGetDefaultAccounts:
    """Test _get_default_accounts method."""

    @pytest.mark.asyncio
    async def test_get_default_accounts_from_metadata(self, expense_service):
        """Test returning accounts from integration metadata."""
        expense_service._get_cached_metadata = AsyncMock(side_effect=["bank_1", "expense_2"])

        result = await expense_service._get_default_accounts()

        assert result == ("bank_1", "expense_2")

    @pytest.mark.asyncio
    async def test_get_default_accounts_from_qb(self, expense_service):
        """Test finding accounts from QuickBooks."""
        expense_service._get_cached_metadata = AsyncMock(return_value=None)
        expense_service._client.list_accounts = AsyncMock(return_value={
            "QueryResponse": {
                "Account": [
                    {"Id": "1", "AccountType": "Bank", "Name": "Checking"},
                    {"Id": "2", "AccountType": "Expense", "Name": "Office Expenses"}
                ]
            }
        })
        expense_service._cache_metadata = AsyncMock()

        result = await expense_service._get_default_accounts()

        assert result[0] == "1"  # Bank account
        assert result[1] == "2"  # Expense account

    @pytest.mark.asyncio
    async def test_get_default_accounts_fallback(self, expense_service):
        """Test fallback when accounts not found."""
        expense_service._get_cached_metadata = AsyncMock(return_value=None)
        expense_service._client.list_accounts = AsyncMock(side_effect=Exception("API error"))

        result = await expense_service._get_default_accounts()

        assert result == ("1", "1")  # Default fallback


class TestGetOrCacheTaxAccountMapping:
    """Test _get_or_cache_tax_account_mapping method."""

    @pytest.mark.asyncio
    async def test_get_tax_mapping_cached(self, expense_service):
        """Test returning cached tax mapping."""
        # The method checks for "reverse_tax_mapping" in session cache
        expense_service._get_session_cache = MagicMock(return_value={"101": "GST"})

        result = await expense_service._get_or_cache_tax_account_mapping()

        # Should return the cached value
        assert result == {"101": "GST"}

    @pytest.mark.asyncio
    async def test_get_tax_mapping_from_service(self, expense_service, mock_session):
        """Test getting tax mapping from AccountMappingService."""
        from unittest.mock import patch
        from Backend.api.quickbooks.services.account_mapping_service import AccountMappingService

        expense_service._get_session_cache = MagicMock(return_value=None)
        expense_service._set_session_cache = MagicMock()

        # Mock AccountMappingService
        with patch.object(AccountMappingService, 'get_reverse_tax_mapping', new_callable=AsyncMock) as mock_reverse:
            mock_reverse.return_value = {"101": "GST"}
            result = await expense_service._get_or_cache_tax_account_mapping()

        assert result == {"101": "GST"}
        expense_service._set_session_cache.assert_called()

    @pytest.mark.asyncio
    async def test_get_tax_mapping_auto_detection(self, expense_service, mock_session):
        """Test tax mapping auto-detection when none found."""
        from unittest.mock import patch
        from Backend.api.quickbooks.services.account_mapping_service import AccountMappingService

        expense_service._get_session_cache = MagicMock(return_value=None)
        expense_service._set_session_cache = MagicMock()

        # Mock AccountMappingService - first call returns empty, after auto-detect returns mapping
        with patch.object(AccountMappingService, 'get_reverse_tax_mapping', new_callable=AsyncMock) as mock_reverse, \
             patch.object(AccountMappingService, 'save_auto_detected_mappings', new_callable=AsyncMock) as mock_auto:
            mock_reverse.side_effect = [{}, {"102": "HST"}]
            result = await expense_service._get_or_cache_tax_account_mapping()

        assert result == {"102": "HST"}
        mock_auto.assert_called_once()
