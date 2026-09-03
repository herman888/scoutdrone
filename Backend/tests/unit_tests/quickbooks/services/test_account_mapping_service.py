"""
Unit tests for AccountMappingService class.

Tests account mapping CRUD operations, auto-detection of Canadian tax accounts,
and tax account ID mapping for expense sync operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.quickbooks.services.account_mapping_service import (
    AccountMappingService,
    CANADIAN_TAX_ACCOUNT_PATTERNS,
    TAX_ACCOUNT_TYPES
)
from Backend.models.user import User
from Backend.models.enums import UserType
from Backend.models.accounting.integration import Integration, IntegrationStatus, IntegrationType
from Backend.models.accounting.quickbooks_account_mapping import QuickBooksAccountMapping

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


def create_mock_integration():
    """Helper to create a mock integration."""
    mock_integration = MagicMock(spec=Integration)
    mock_integration.id = uuid4()
    mock_integration.user_id = uuid4()
    mock_integration.integration_type = IntegrationType.QUICKBOOKS
    mock_integration.status = IntegrationStatus.CONNECTED
    mock_integration.connected_at = FIXED_DATETIME
    return mock_integration


@pytest.fixture
def mock_session():
    """Mock AsyncSession for database operations."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.refresh = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    return session


@pytest.fixture
def mock_integration():
    """Create a properly configured mock integration."""
    integration = MagicMock(spec=Integration)
    integration.id = uuid4()
    integration.user_id = uuid4()
    integration.integration_type = IntegrationType.QUICKBOOKS
    integration.status = IntegrationStatus.CONNECTED
    integration.connected_at = FIXED_DATETIME
    return integration


@pytest.fixture
def service(mock_session, mock_integration):
    """Create AccountMappingService with mocked dependencies."""
    user = create_test_user()
    service = AccountMappingService(user, mock_session)
    # Pre-initialize the service to skip the initialize() call
    service._initialized = True
    service.integration = mock_integration
    service._quickbooks_cache = {}
    # Mock the initialize method to be a no-op
    service.initialize = AsyncMock()
    return service


class TestCanadianTaxPatterns:
    """Test that tax pattern constants are correctly defined."""

    def test_gst_patterns_exist(self):
        """Test GST patterns are defined."""
        assert "GST" in CANADIAN_TAX_ACCOUNT_PATTERNS
        assert len(CANADIAN_TAX_ACCOUNT_PATTERNS["GST"]) > 0
        assert "gst" in CANADIAN_TAX_ACCOUNT_PATTERNS["GST"]

    def test_hst_patterns_exist(self):
        """Test HST patterns are defined."""
        assert "HST" in CANADIAN_TAX_ACCOUNT_PATTERNS
        assert "hst" in CANADIAN_TAX_ACCOUNT_PATTERNS["HST"]

    def test_pst_patterns_exist(self):
        """Test PST patterns are defined."""
        assert "PST" in CANADIAN_TAX_ACCOUNT_PATTERNS
        assert "pst" in CANADIAN_TAX_ACCOUNT_PATTERNS["PST"]

    def test_qst_patterns_exist(self):
        """Test QST patterns are defined."""
        assert "QST" in CANADIAN_TAX_ACCOUNT_PATTERNS
        assert "qst" in CANADIAN_TAX_ACCOUNT_PATTERNS["QST"]
        assert "tvq" in CANADIAN_TAX_ACCOUNT_PATTERNS["QST"]

    def test_tax_account_types(self):
        """Test valid account types for tax accounts."""
        assert "Expense" in TAX_ACCOUNT_TYPES
        assert "OtherCurrentAsset" in TAX_ACCOUNT_TYPES
        assert "OtherExpense" in TAX_ACCOUNT_TYPES


class TestFetchAllAccountsFromQB:
    """Test fetch_all_accounts_from_qb method."""

    @pytest.mark.asyncio
    async def test_fetch_accounts_success(self, service):
        """Test successful account fetch from QuickBooks."""
        mock_accounts = [
            {"Id": "1", "Name": "GST Paid", "AccountType": "Expense", "Active": True},
            {"Id": "2", "Name": "Office Supplies", "AccountType": "Expense", "Active": True},
        ]

        # Mock client
        mock_client = AsyncMock()
        mock_client.list_accounts = AsyncMock(return_value={
            "QueryResponse": {"Account": mock_accounts}
        })
        service._client = mock_client

        result = await service.fetch_all_accounts_from_qb()

        assert len(result) == 2
        assert result[0]["Name"] == "GST Paid"

    @pytest.mark.asyncio
    async def test_fetch_accounts_empty_response(self, service):
        """Test fetch with empty QuickBooks response."""
        mock_client = AsyncMock()
        mock_client.list_accounts = AsyncMock(return_value={
            "QueryResponse": {}
        })
        service._client = mock_client

        result = await service.fetch_all_accounts_from_qb()

        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_accounts_uses_cache(self, service):
        """Test that repeated calls use cache."""
        cached_accounts = [{"Id": "cached", "Name": "Cached Account"}]
        # The cache uses _session_cache, not _quickbooks_cache
        # We need to also mock the _client property to avoid the client property check
        mock_client = AsyncMock()
        service._client = mock_client
        service._session_cache = {"all_qb_accounts": cached_accounts}

        result = await service.fetch_all_accounts_from_qb()

        assert result == cached_accounts


class TestGetTaxAccounts:
    """Test get_tax_accounts method."""

    @pytest.mark.asyncio
    async def test_get_tax_accounts_filters_correctly(self, service):
        """Test tax account filtering by account type."""
        all_accounts = [
            {"Id": "1", "Name": "GST Paid", "AccountType": "Expense", "Active": True},
            {"Id": "2", "Name": "Bank Account", "AccountType": "Bank", "Active": True},
            {"Id": "3", "Name": "PST Paid", "AccountType": "OtherCurrentAsset", "Active": True},
            {"Id": "4", "Name": "Inactive Tax", "AccountType": "Expense", "Active": False},
        ]

        mock_client = AsyncMock()
        mock_client.list_accounts = AsyncMock(return_value={
            "QueryResponse": {"Account": all_accounts}
        })
        service._client = mock_client

        result = await service.get_tax_accounts()

        # Should only include active expense-type accounts
        assert len(result) == 2
        assert all(acc["account_type"] in TAX_ACCOUNT_TYPES for acc in result)
        assert all(acc["active"] for acc in result)


class TestAutoDetectTaxAccounts:
    """Test auto_detect_tax_accounts method."""

    @pytest.mark.asyncio
    async def test_auto_detect_gst(self, service):
        """Test auto-detection of GST account."""
        all_accounts = [
            {"Id": "101", "Name": "GST Paid on Purchases", "AccountType": "Expense", "Active": True},
            {"Id": "102", "Name": "Office Supplies", "AccountType": "Expense", "Active": True},
        ]

        mock_client = AsyncMock()
        mock_client.list_accounts = AsyncMock(return_value={
            "QueryResponse": {"Account": all_accounts}
        })
        service._client = mock_client

        result = await service.auto_detect_tax_accounts()

        assert "GST" in result
        assert result["GST"]["id"] == "101"
        assert result["GST"]["name"] == "GST Paid on Purchases"

    @pytest.mark.asyncio
    async def test_auto_detect_multiple_taxes(self, service):
        """Test auto-detection of multiple tax accounts."""
        all_accounts = [
            {"Id": "101", "Name": "GST/HST Paid", "AccountType": "Expense", "Active": True},
            {"Id": "102", "Name": "PST Paid BC", "AccountType": "OtherCurrentAsset", "Active": True},
            {"Id": "103", "Name": "QST TVQ Paid", "AccountType": "Expense", "Active": True},
        ]

        mock_client = AsyncMock()
        mock_client.list_accounts = AsyncMock(return_value={
            "QueryResponse": {"Account": all_accounts}
        })
        service._client = mock_client

        result = await service.auto_detect_tax_accounts()

        # GST and HST share patterns, so both may match same account
        assert len(result) >= 2
        assert "PST" in result
        assert "QST" in result

    @pytest.mark.asyncio
    async def test_auto_detect_skips_inactive(self, service):
        """Test that inactive accounts are skipped."""
        all_accounts = [
            {"Id": "101", "Name": "GST Paid", "AccountType": "Expense", "Active": False},
        ]

        mock_client = AsyncMock()
        mock_client.list_accounts = AsyncMock(return_value={
            "QueryResponse": {"Account": all_accounts}
        })
        service._client = mock_client

        result = await service.auto_detect_tax_accounts()

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_auto_detect_skips_non_expense_types(self, service):
        """Test that non-expense account types are skipped."""
        all_accounts = [
            {"Id": "101", "Name": "GST Paid", "AccountType": "Bank", "Active": True},
        ]

        mock_client = AsyncMock()
        mock_client.list_accounts = AsyncMock(return_value={
            "QueryResponse": {"Account": all_accounts}
        })
        service._client = mock_client

        result = await service.auto_detect_tax_accounts()

        assert len(result) == 0


class TestSaveAccountMapping:
    """Test save_account_mapping method."""

    @pytest.mark.asyncio
    async def test_save_new_mapping(self, service, mock_session):
        """Test saving a new account mapping."""
        # No existing mapping
        mock_session.scalar.return_value = None

        result = await service.save_account_mapping(
            mapping_type="tax_account",
            brikli_key="GST",
            quickbooks_account_id="101",
            quickbooks_account_name="GST Paid"
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_existing_mapping(self, service, mock_session):
        """Test updating an existing account mapping."""
        # Existing mapping - use a plain object not MagicMock to avoid spec issues
        existing_mapping = MagicMock()
        existing_mapping.id = 1
        existing_mapping.quickbooks_account_id = "old_id"
        existing_mapping.quickbooks_account_name = "Old Name"
        existing_mapping.quickbooks_account_type = None
        mock_session.scalar.return_value = existing_mapping

        result = await service.save_account_mapping(
            mapping_type="tax_account",
            brikli_key="GST",
            quickbooks_account_id="new_id",
            quickbooks_account_name="New GST Account"
        )

        # Should update existing, not create new
        assert existing_mapping.quickbooks_account_id == "new_id"
        assert existing_mapping.quickbooks_account_name == "New GST Account"
        mock_session.add.assert_called_with(existing_mapping)


class TestDeleteAccountMapping:
    """Test delete_account_mapping method."""

    @pytest.mark.asyncio
    async def test_delete_existing_mapping(self, service, mock_session):
        """Test deleting an existing mapping."""
        existing_mapping = MagicMock()
        existing_mapping.id = 1
        mock_session.scalar.return_value = existing_mapping

        result = await service.delete_account_mapping(1)

        assert result is True
        mock_session.delete.assert_called_once_with(existing_mapping)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_non_existent_mapping(self, service, mock_session):
        """Test deleting a non-existent mapping."""
        mock_session.scalar.return_value = None

        result = await service.delete_account_mapping(999)

        assert result is False
        mock_session.delete.assert_not_called()


class TestGetAllMappings:
    """Test get_all_mappings method."""

    @pytest.mark.asyncio
    async def test_get_all_mappings(self, service, mock_session):
        """Test retrieving all mappings."""
        mapping1 = MagicMock()
        mapping1.brikli_key = "GST"
        mapping2 = MagicMock()
        mapping2.brikli_key = "PST"

        mock_result = MagicMock()
        mock_result.all.return_value = [mapping1, mapping2]
        mock_session.scalars.return_value = mock_result

        result = await service.get_all_mappings()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_all_mappings_empty(self, service, mock_session):
        """Test retrieving mappings when none exist."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.scalars.return_value = mock_result

        result = await service.get_all_mappings()

        assert result == []


class TestGetTaxAccountIdMapping:
    """Test get_tax_account_id_mapping method."""

    @pytest.mark.asyncio
    async def test_get_tax_account_id_mapping(self, service, mock_session):
        """Test getting tax account ID mapping dict."""
        mapping1 = MagicMock()
        mapping1.brikli_key = "GST"
        mapping1.quickbooks_account_id = "101"

        mapping2 = MagicMock()
        mapping2.brikli_key = "PST"
        mapping2.quickbooks_account_id = "102"

        mock_result = MagicMock()
        mock_result.all.return_value = [mapping1, mapping2]
        mock_session.scalars.return_value = mock_result

        result = await service.get_tax_account_id_mapping()

        assert result == {"GST": "101", "PST": "102"}

    @pytest.mark.asyncio
    async def test_get_tax_account_id_mapping_empty(self, service, mock_session):
        """Test getting tax account ID mapping when empty."""
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.scalars.return_value = mock_result

        result = await service.get_tax_account_id_mapping()

        assert result == {}


class TestGetReverseTaxMapping:
    """Test get_reverse_tax_mapping method."""

    @pytest.mark.asyncio
    async def test_get_reverse_mapping(self, service, mock_session):
        """Test getting reverse tax mapping (account ID -> tax code)."""
        mapping1 = MagicMock()
        mapping1.brikli_key = "GST"
        mapping1.quickbooks_account_id = "101"

        mapping2 = MagicMock()
        mapping2.brikli_key = "HST"
        mapping2.quickbooks_account_id = "102"

        mock_result = MagicMock()
        mock_result.all.return_value = [mapping1, mapping2]
        mock_session.scalars.return_value = mock_result

        result = await service.get_reverse_tax_mapping()

        assert result == {"101": "GST", "102": "HST"}


class TestSaveAutoDetectedMappings:
    """Test save_auto_detected_mappings method."""

    @pytest.mark.asyncio
    async def test_save_auto_detected(self, service):
        """Test saving auto-detected mappings."""
        # Mock auto_detect to return mappings
        service.auto_detect_tax_accounts = AsyncMock(return_value={
            "GST": {"id": "101", "name": "GST Paid", "account_type": "Expense"},
            "PST": {"id": "102", "name": "PST Paid", "account_type": "Expense"}
        })

        # Mock save_account_mapping
        saved_mappings = []

        async def mock_save(*args, **kwargs):
            mock_mapping = MagicMock()
            mock_mapping.brikli_key = kwargs.get("brikli_key")
            saved_mappings.append(mock_mapping)
            return mock_mapping

        service.save_account_mapping = mock_save

        result = await service.save_auto_detected_mappings()

        assert len(result) == 2


class TestClientProperty:
    """Test client property."""

    def test_client_not_initialized_raises(self, service):
        """Test that accessing client before init raises error."""
        service._client = None

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = service.client

    def test_client_initialized_returns_client(self, service):
        """Test that client returns the client when initialized."""
        mock_client = MagicMock()
        service._client = mock_client

        assert service.client == mock_client
