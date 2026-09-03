"""
Unit tests for BaseQuickBooksService and TenantLeaseService classes.

Tests the base service functionality including:
- Initialization and integration validation
- Retry mechanism with circuit breaker
- Session caching
- Preview mode functionality
- TenantLeaseService tenant/lease prefetching
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, UTC

import aiohttp
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from Backend.api.quickbooks.services.base_service import (
    BaseQuickBooksService,
    TenantLeaseService,
    SyncAction,
    SyncItem,
    SyncPreview,
)
from Backend.models.user import User
from Backend.models.enums import UserType
from Backend.models.accounting.integration import Integration, IntegrationStatus, IntegrationType
from Backend.models.tenant import Tenant
from Backend.models.lease import Lease, LeaseStatus

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
    mock_integration.connection_metadata = {}
    mock_integration.last_sync_at = None
    return mock_integration


@pytest.fixture
def mock_session():
    """Mock AsyncSession for database operations."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_integration():
    """Create a properly configured mock integration."""
    return create_mock_integration()


@pytest.fixture
def base_service(mock_session, mock_integration):
    """Create BaseQuickBooksService with mocked dependencies."""
    user = create_test_user()
    service = BaseQuickBooksService(user, mock_session)
    service.integration = mock_integration
    service._client = MagicMock()
    service._circuit_breaker = None  # Will use direct execution fallback
    return service


@pytest.fixture
def tenant_lease_service(mock_session, mock_integration):
    """Create TenantLeaseService with mocked dependencies."""
    user = create_test_user()
    service = TenantLeaseService(user, mock_session)
    service.integration = mock_integration
    service._client = MagicMock()
    service._circuit_breaker = None
    return service


class TestSyncItemDataclass:
    """Test SyncItem dataclass."""

    def test_sync_item_creation(self):
        """Test creating a SyncItem."""
        item = SyncItem(
            entity_type="tenant",
            entity_id="123",
            entity_name="John Doe",
            action=SyncAction.CREATE,
            details={"email": "john@example.com"}
        )

        assert item.entity_type == "tenant"
        assert item.entity_id == "123"
        assert item.entity_name == "John Doe"
        assert item.action == SyncAction.CREATE
        assert item.details == {"email": "john@example.com"}
        assert item.warnings == []  # Default empty list

    def test_sync_item_with_warnings(self):
        """Test SyncItem with warnings."""
        item = SyncItem(
            entity_type="invoice",
            entity_id="456",
            entity_name="Invoice #1",
            action=SyncAction.UPDATE,
            details={},
            warnings=["Amount changed", "Date differs"]
        )

        assert len(item.warnings) == 2
        assert "Amount changed" in item.warnings


class TestSyncPreviewDataclass:
    """Test SyncPreview dataclass."""

    def test_sync_preview_creation(self):
        """Test creating a SyncPreview."""
        items = [
            SyncItem("tenant", "1", "Tenant 1", SyncAction.CREATE, {}),
            SyncItem("tenant", "2", "Tenant 2", SyncAction.SKIP, {}),
        ]
        preview = SyncPreview(
            items=items,
            summary={"create": 1, "skip": 1, "total": 2}
        )

        assert len(preview.items) == 2
        assert preview.summary["total"] == 2
        assert preview.warnings == []

    def test_sync_preview_with_warnings(self):
        """Test SyncPreview with global warnings."""
        preview = SyncPreview(
            items=[],
            summary={},
            warnings=["Some items need attention"]
        )

        assert len(preview.warnings) == 1


class TestBaseQuickBooksServiceInit:
    """Test BaseQuickBooksService initialization."""

    def test_init_creates_service(self, mock_session):
        """Test that init creates service with correct attributes."""
        user = create_test_user()
        service = BaseQuickBooksService(user, mock_session)

        assert service.user == user
        assert service.session == mock_session
        assert service.preview_mode is False
        assert service.integration is None
        assert service._client is None
        assert service._session_cache == {}

    def test_init_with_preview_mode(self, mock_session):
        """Test initialization with preview mode enabled."""
        user = create_test_user()
        service = BaseQuickBooksService(user, mock_session, preview_mode=True)

        assert service.preview_mode is True
        assert service._preview_items == []


class TestClientProperty:
    """Test client property."""

    def test_client_not_initialized_raises(self, mock_session):
        """Test that accessing client before init raises error."""
        user = create_test_user()
        service = BaseQuickBooksService(user, mock_session)

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = service.client

    def test_client_initialized_returns_client(self, base_service):
        """Test that client returns the client when initialized."""
        mock_client = MagicMock()
        base_service._client = mock_client

        assert base_service.client == mock_client


class TestIntegrationIdProperty:
    """Test integration_id property."""

    def test_integration_id_not_initialized_raises(self, mock_session):
        """Test that accessing integration_id before init raises error."""
        user = create_test_user()
        service = BaseQuickBooksService(user, mock_session)

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = service.integration_id

    def test_integration_id_returns_id(self, base_service, mock_integration):
        """Test that integration_id returns the integration ID."""
        expected_id = mock_integration.id
        assert base_service.integration_id == expected_id

    def test_integration_id_none_raises(self, base_service, mock_integration):
        """Test that None integration ID raises error."""
        mock_integration.id = None

        with pytest.raises(RuntimeError, match="Integration ID is None"):
            _ = base_service.integration_id


class TestSessionCache:
    """Test session caching functionality."""

    def test_get_session_cache_returns_default(self, base_service):
        """Test getting non-existent cache key returns default."""
        result = base_service._get_session_cache("nonexistent")
        assert result is None

        result = base_service._get_session_cache("nonexistent", default="default")
        assert result == "default"

    def test_set_and_get_session_cache(self, base_service):
        """Test setting and getting cache values."""
        base_service._set_session_cache("key1", {"data": "value"})

        result = base_service._get_session_cache("key1")
        assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_get_or_cache_uses_cached_data(self, base_service):
        """Test that get_or_cache returns cached data without calling fetch."""
        cached_data = [{"id": 1}, {"id": 2}]
        base_service._set_session_cache("test_key", cached_data)

        fetch_func = AsyncMock(return_value=[{"id": 3}])
        result = await base_service._get_or_cache_quickbooks_data("test_key", fetch_func)

        assert result == cached_data
        fetch_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_cache_fetches_when_not_cached(self, base_service):
        """Test that get_or_cache fetches and caches new data."""
        fetch_data = [{"id": 1}, {"id": 2}]
        fetch_func = AsyncMock(return_value=fetch_data)

        result = await base_service._get_or_cache_quickbooks_data("new_key", fetch_func)

        assert result == fetch_data
        fetch_func.assert_called_once()
        # Verify it's now cached
        assert base_service._get_session_cache("new_key") == fetch_data


class TestSyncResultCreation:
    """Test sync result creation."""

    def test_create_sync_result_success(self, base_service):
        """Test creating successful sync result."""
        result = base_service._create_sync_result(synced_count=10)

        assert result["success"] is True
        assert result["synced_count"] == 10
        assert result["errors"] is None

    def test_create_sync_result_with_errors(self, base_service):
        """Test creating sync result with errors."""
        errors = ["Error 1", "Error 2"]
        result = base_service._create_sync_result(synced_count=5, errors=errors)

        assert result["success"] is False
        assert result["synced_count"] == 5
        assert result["errors"] == errors

    def test_create_sync_result_with_extra_kwargs(self, base_service):
        """Test creating sync result with extra fields."""
        result = base_service._create_sync_result(
            synced_count=10,
            message="Sync completed",
            additional_info={"extra": "data"}
        )

        assert result["success"] is True
        assert result["message"] == "Sync completed"
        assert result["additional_info"] == {"extra": "data"}


class TestPreviewMode:
    """Test preview mode functionality."""

    def test_add_preview_item_in_preview_mode(self, mock_session):
        """Test adding preview item when in preview mode."""
        user = create_test_user()
        service = BaseQuickBooksService(user, mock_session, preview_mode=True)

        service._add_preview_item(
            entity_type="tenant",
            entity_id="123",
            entity_name="John Doe",
            action=SyncAction.CREATE,
            details={"email": "john@example.com"}
        )

        assert len(service._preview_items) == 1
        assert service._preview_items[0].entity_type == "tenant"

    def test_add_preview_item_not_in_preview_mode(self, base_service):
        """Test that preview items are not added when not in preview mode."""
        base_service.preview_mode = False

        base_service._add_preview_item(
            entity_type="tenant",
            entity_id="123",
            entity_name="John Doe",
            action=SyncAction.CREATE,
            details={}
        )

        assert len(base_service._preview_items) == 0

    def test_generate_preview(self, mock_session):
        """Test generating preview from collected items."""
        user = create_test_user()
        service = BaseQuickBooksService(user, mock_session, preview_mode=True)

        # Add multiple items with different actions
        service._add_preview_item("tenant", "1", "T1", SyncAction.CREATE, {})
        service._add_preview_item("tenant", "2", "T2", SyncAction.CREATE, {})
        service._add_preview_item("tenant", "3", "T3", SyncAction.UPDATE, {})
        service._add_preview_item("tenant", "4", "T4", SyncAction.SKIP, {})
        service._add_preview_item("tenant", "5", "T5", SyncAction.ERROR, {}, warnings=["Warning 1"])

        preview = service._generate_preview()

        assert preview.summary["create"] == 2
        assert preview.summary["update"] == 1
        assert preview.summary["skip"] == 1
        assert preview.summary["error"] == 1
        assert preview.summary["total"] == 5
        assert len(preview.warnings) == 1  # One global warning about items with warnings

    def test_should_execute_action(self, base_service):
        """Test should_execute_action returns correct value."""
        base_service.preview_mode = False
        assert base_service._should_execute_action() is True

        base_service.preview_mode = True
        assert base_service._should_execute_action() is False


class TestBatchCreateWithErrors:
    """Test batch create with error aggregation."""

    @pytest.mark.asyncio
    async def test_batch_create_all_success(self, base_service):
        """Test batch create when all items succeed."""
        entities = [{"name": "Entity 1"}, {"name": "Entity 2"}]

        async def create_func(entity):
            return {"created": True}

        result = await base_service._batch_create_with_errors(entities, create_func, "test_entity")

        assert result["created_count"] == 2
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_batch_create_some_failures(self, base_service):
        """Test batch create with some failures."""
        entities = [{"name": "Entity 1"}, {"name": "Entity 2"}, {"name": "Entity 3"}]

        call_count = 0

        async def create_func(entity):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return None  # Simulate failure
            return {"created": True}

        result = await base_service._batch_create_with_errors(entities, create_func, "test_entity")

        assert result["created_count"] == 2
        assert len(result["errors"]) == 1
        assert "Failed to create test_entity" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_batch_create_with_exception(self, base_service):
        """Test batch create when exception is raised."""
        entities = [{"name": "Entity 1"}]

        async def create_func(entity):
            raise ValueError("Test error")

        result = await base_service._batch_create_with_errors(entities, create_func, "test_entity")

        assert result["created_count"] == 0
        assert len(result["errors"]) == 1
        assert "Error creating test_entity" in result["errors"][0]


class TestLogging:
    """Test logging functionality."""

    def test_log_operation_info(self, base_service):
        """Test info level logging."""
        # Should not raise
        base_service._log_operation("test_operation", level="info", extra_context="value")

    def test_log_operation_warning(self, base_service):
        """Test warning level logging."""
        base_service._log_operation("test_operation", level="warning", warning_context="value")

    def test_log_operation_error(self, base_service):
        """Test error level logging."""
        base_service._log_operation("test_operation", level="error", error_context="value")


class TestCachedMetadata:
    """Test integration metadata caching."""

    @pytest.mark.asyncio
    async def test_get_cached_metadata_returns_value(self, base_service, mock_integration):
        """Test getting cached metadata value."""
        mock_integration.connection_metadata = {"key1": "value1"}

        result = await base_service._get_cached_metadata("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_cached_metadata_returns_default(self, base_service, mock_integration):
        """Test getting cached metadata returns default when not found."""
        mock_integration.connection_metadata = {}

        result = await base_service._get_cached_metadata("nonexistent", default="default_val")
        assert result == "default_val"

    @pytest.mark.asyncio
    async def test_get_cached_metadata_no_integration(self, mock_session):
        """Test getting cached metadata when integration is None."""
        user = create_test_user()
        service = BaseQuickBooksService(user, mock_session)

        result = await service._get_cached_metadata("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_metadata(self, base_service, mock_integration, mock_session):
        """Test caching metadata value."""
        mock_integration.connection_metadata = {}

        await base_service._cache_metadata("new_key", "new_value")

        assert mock_integration.connection_metadata["new_key"] == "new_value"
        mock_session.add.assert_called_with(mock_integration)
        mock_session.commit.assert_called_once()


class TestRetryOperation:
    """Test retry operation with circuit breaker."""

    @pytest.mark.asyncio
    async def test_retry_operation_success_first_try(self, base_service):
        """Test successful operation on first try."""
        async def success_operation():
            return {"success": True}

        result = await base_service._retry_operation(success_operation, "test_operation")
        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_retry_operation_success_after_retries(self, base_service):
        """Test successful operation after retries."""
        call_count = 0

        async def eventual_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise aiohttp.ClientError("Temporary error")
            return {"success": True}

        # Mock sleep to speed up test
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await base_service._retry_operation(eventual_success, "test_operation", max_retries=3)

        assert result == {"success": True}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_operation_503_not_retried(self, base_service):
        """Test that 503 errors from circuit breaker are not retried."""
        async def circuit_breaker_error():
            raise HTTPException(status_code=503, detail="Service unavailable")

        with pytest.raises(HTTPException) as exc_info:
            await base_service._retry_operation(circuit_breaker_error, "test_operation")

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_retry_operation_auth_error_not_retried(self, base_service):
        """Test that auth errors (401, 403) are not retried."""
        async def auth_error():
            raise HTTPException(status_code=401, detail="Unauthorized")

        with pytest.raises(HTTPException) as exc_info:
            await base_service._retry_operation(auth_error, "test_operation")

        assert exc_info.value.status_code == 401


# ============================================================================
# TenantLeaseService Tests
# ============================================================================


class TestTenantLeaseServicePrefetch:
    """Test TenantLeaseService prefetch functionality."""

    @pytest.mark.asyncio
    async def test_prefetch_tenants_and_leases_empty(self, tenant_lease_service, mock_session):
        """Test prefetch when no tenants exist."""
        # Mock scalars to return empty iterator
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_session.scalars.return_value = mock_result

        result = await tenant_lease_service._prefetch_tenants_and_leases()

        assert result == {}

    @pytest.mark.asyncio
    async def test_prefetch_tenants_and_leases_with_data(self, tenant_lease_service, mock_session):
        """Test prefetch with tenants and active leases."""
        tenant1_id = uuid4()
        tenant2_id = uuid4()

        # Create mock tenants
        tenant1 = MagicMock(spec=Tenant)
        tenant1.id = tenant1_id
        tenant1.quickbooks_customer_id = "qb_cust_1"
        tenant1.landlord_id = tenant_lease_service.user.id

        tenant2 = MagicMock(spec=Tenant)
        tenant2.id = tenant2_id
        tenant2.quickbooks_customer_id = "qb_cust_2"
        tenant2.landlord_id = tenant_lease_service.user.id

        # Create mock leases
        lease1 = MagicMock(spec=Lease)
        lease1.tenant_id = tenant1_id
        lease1.status = LeaseStatus.ACTIVE

        lease2 = MagicMock(spec=Lease)
        lease2.tenant_id = tenant2_id
        lease2.status = LeaseStatus.ACTIVE

        # Setup mock to return tenants first, then leases
        call_count = 0

        def mock_scalars_side_effect(query):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # First call returns tenants
                mock_result.__iter__ = lambda self: iter([tenant1, tenant2])
                mock_result.__len__ = lambda self: 2
            else:
                # Second call returns leases
                mock_result.__iter__ = lambda self: iter([lease1, lease2])
            return mock_result

        mock_session.scalars.side_effect = mock_scalars_side_effect

        result = await tenant_lease_service._prefetch_tenants_and_leases()

        # Should have 2 entries
        assert len(result) == 2
        assert "qb_cust_1" in result
        assert "qb_cust_2" in result
        # Each entry should be a tuple of (tenant, lease)
        assert result["qb_cust_1"][0] == tenant1
        assert result["qb_cust_1"][1] == lease1

    @pytest.mark.asyncio
    async def test_prefetch_tenants_and_leases_tenant_without_id(self, tenant_lease_service, mock_session):
        """Test handling tenants where id is None (edge case)."""
        # Create mock tenant with QB customer ID but None internal id
        tenant = MagicMock(spec=Tenant)
        tenant.id = None  # Edge case: tenant has None id
        tenant.quickbooks_customer_id = "qb_cust_1"
        tenant.landlord_id = tenant_lease_service.user.id

        # Setup mock to return tenant first, then no leases
        call_count = 0

        def mock_scalars_side_effect(query):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # First call returns tenant with None id
                mock_result.__iter__ = lambda self: iter([tenant])
            else:
                # Second call returns no leases
                mock_result.__iter__ = lambda self: iter([])
            return mock_result

        mock_session.scalars.side_effect = mock_scalars_side_effect

        result = await tenant_lease_service._prefetch_tenants_and_leases()

        # Tenant with None id should be excluded from result
        assert len(result) == 0


class TestResolveFromCache:
    """Test _resolve_from_cache method."""

    def test_resolve_from_cache_found(self, tenant_lease_service):
        """Test resolving tenant and lease from cache."""
        tenant = MagicMock(spec=Tenant)
        lease = MagicMock(spec=Lease)
        cache = {"qb_cust_123": (tenant, lease)}

        def get_customer_id(qb_item):
            return qb_item.get("CustomerRef", {}).get("value")

        qb_item = {"CustomerRef": {"value": "qb_cust_123"}}

        result_tenant, result_lease = tenant_lease_service._resolve_from_cache(
            qb_item, cache, get_customer_id
        )

        assert result_tenant == tenant
        assert result_lease == lease

    def test_resolve_from_cache_not_found(self, tenant_lease_service):
        """Test resolving when customer not in cache."""
        cache = {"qb_cust_123": (MagicMock(), MagicMock())}

        def get_customer_id(qb_item):
            return qb_item.get("CustomerRef", {}).get("value")

        qb_item = {"CustomerRef": {"value": "qb_cust_999"}}  # Not in cache

        result_tenant, result_lease = tenant_lease_service._resolve_from_cache(
            qb_item, cache, get_customer_id
        )

        assert result_tenant is None
        assert result_lease is None

    def test_resolve_from_cache_no_customer_ref(self, tenant_lease_service):
        """Test resolving when QB item has no customer reference."""
        cache = {"qb_cust_123": (MagicMock(), MagicMock())}

        def get_customer_id(qb_item):
            return qb_item.get("CustomerRef", {}).get("value")

        qb_item = {}  # No CustomerRef

        result_tenant, result_lease = tenant_lease_service._resolve_from_cache(
            qb_item, cache, get_customer_id
        )

        assert result_tenant is None
        assert result_lease is None


class TestGetUserPropertyIds:
    """Test _get_user_property_ids method."""

    @pytest.mark.asyncio
    async def test_get_user_property_ids(self, tenant_lease_service, mock_session):
        """Test getting property IDs for user."""
        prop_id_1 = uuid4()
        prop_id_2 = uuid4()

        # Mock execute to return property IDs
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([(prop_id_1,), (prop_id_2,)])
        mock_session.execute.return_value = mock_result

        result = await tenant_lease_service._get_user_property_ids()

        assert len(result) == 2
        assert prop_id_1 in result
        assert prop_id_2 in result

    @pytest.mark.asyncio
    async def test_get_user_property_ids_empty(self, tenant_lease_service, mock_session):
        """Test getting property IDs when user has none."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_session.execute.return_value = mock_result

        result = await tenant_lease_service._get_user_property_ids()

        assert result == []


class TestPrefetchTenantsByIds:
    """Test _prefetch_tenants_by_ids method."""

    @pytest.mark.asyncio
    async def test_prefetch_tenants_by_ids_empty_list(self, tenant_lease_service, mock_session):
        """Test prefetching with empty ID list."""
        result = await tenant_lease_service._prefetch_tenants_by_ids([])

        assert result == {}
        mock_session.scalars.assert_not_called()

    @pytest.mark.asyncio
    async def test_prefetch_tenants_by_ids_with_data(self, tenant_lease_service, mock_session):
        """Test prefetching tenants by IDs."""
        tenant_id_1 = uuid4()
        tenant_id_2 = uuid4()

        tenant1 = MagicMock(spec=Tenant)
        tenant1.id = tenant_id_1

        tenant2 = MagicMock(spec=Tenant)
        tenant2.id = tenant_id_2

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([tenant1, tenant2])
        mock_session.scalars.return_value = mock_result

        result = await tenant_lease_service._prefetch_tenants_by_ids([tenant_id_1, tenant_id_2])

        assert len(result) == 2
        assert result[tenant_id_1] == tenant1
        assert result[tenant_id_2] == tenant2


class TestUpdateIntegrationSyncTime:
    """Test updating integration sync time."""

    @pytest.mark.asyncio
    async def test_update_integration_sync_time(self, base_service, mock_integration, mock_session):
        """Test updating last sync time."""
        await base_service._update_integration_sync_time()

        assert mock_integration.last_sync_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_integration_sync_time_no_integration(self, mock_session):
        """Test update sync time when integration is None."""
        user = create_test_user()
        service = BaseQuickBooksService(user, mock_session)
        service.integration = None

        # Should not raise, just do nothing
        await service._update_integration_sync_time()
        mock_session.commit.assert_not_called()


class TestCircuitBreakerExecution:
    """Test circuit breaker execution."""

    @pytest.mark.asyncio
    async def test_execute_without_circuit_breaker(self, base_service):
        """Test execution without circuit breaker (fallback)."""
        async def test_operation():
            return "success"

        result = await base_service._execute_with_circuit_breaker(test_operation, "test_op")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_execute_with_circuit_breaker(self, base_service):
        """Test execution with circuit breaker."""
        mock_circuit_breaker = MagicMock()
        mock_circuit_breaker.call = AsyncMock(return_value="cb_success")
        base_service._circuit_breaker = mock_circuit_breaker

        async def test_operation():
            return "success"

        result = await base_service._execute_with_circuit_breaker(test_operation, "test_op")
        assert result == "cb_success"
        mock_circuit_breaker.call.assert_called_once()
