import logging
import asyncio
from typing import Dict, Any, Optional, Callable, List, Union, Tuple, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col, desc
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from ....models.tenant import Tenant
    from ....models.lease import Lease

from ....models.user import User
from ....models.accounting.integration import Integration, IntegrationType, IntegrationStatus
from ....utils.datetime_utils import create_audit_datetime
from ..intuit_client import get_intuit_client_for_user, IntuitClient
from ..circuit_breaker import get_circuit_breaker, CircuitBreakerConfig, CircuitBreakerError, CircuitBreaker

logger = logging.getLogger(__name__)


class SyncAction(str, Enum):
    """Types of actions that can be performed during sync."""
    CREATE = "create"
    UPDATE = "update"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class SyncItem:
    """Represents an item to be synced with its details."""
    entity_type: str  # "tenant", "invoice", "payment", "expense"
    entity_id: str
    entity_name: str
    action: SyncAction
    details: Dict[str, Any]
    warnings: Optional[List[str]] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class SyncPreview:
    """Preview of what will happen during a sync operation."""
    items: List[SyncItem]
    summary: Dict[str, int]
    warnings: Optional[List[str]] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class BaseQuickBooksService:
    """
    Base service class for QuickBooks entity operations.

    Provides common functionality for all QuickBooks entity services including:
    - Integration validation
    - Client initialization
    - Retry mechanism
    - Error handling
    - Logging
    - Session-level caching
    """

    def __init__(self, user: User, session: AsyncSession, preview_mode: bool = False):
        self.user = user
        self.session = session
        self.preview_mode = preview_mode
        self.integration: Optional[Integration] = None
        self._client: Optional[IntuitClient] = None
        self._session_cache: Dict[str, Any] = {}  # In-memory cache for this sync session
        self._preview_items: List[SyncItem] = []  # Collect items for preview
        self._circuit_breaker: Optional[CircuitBreaker] = None  # Will be initialized lazily

    async def initialize(self) -> None:
        """Initialize service and verify QuickBooks connection."""
        self.integration = await self._get_user_integration()
        if not self.integration or self.integration.status != IntegrationStatus.CONNECTED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QuickBooks integration not found or not connected"
            )
        self._client = await get_intuit_client_for_user(self.user.id, self.session)

        # Initialize circuit breaker for this service
        circuit_breaker_name = f"quickbooks-{self.__class__.__name__.lower()}"
        circuit_config = CircuitBreakerConfig(
            failure_threshold=5,      # Open after 5 failures
            recovery_timeout=60,      # Try recovery after 60 seconds
            half_open_max_calls=3,    # Test with max 3 calls
            success_threshold=2,      # Close after 2 successes
            timeout_threshold=30.0,   # 30 second timeout
            failure_rate_threshold=0.5  # 50% failure rate
        )
        self._circuit_breaker = await get_circuit_breaker(circuit_breaker_name, circuit_config)

    async def _get_user_integration(self) -> Optional[Integration]:
        """Get user's QuickBooks integration."""
        return await self.session.scalar(
            select(Integration).where(
                Integration.user_id == self.user.id,
                Integration.integration_type == IntegrationType.QUICKBOOKS
            )
        )

    async def _execute_with_circuit_breaker(self, operation: Callable, operation_name: str) -> Any:
        """
        Execute operation with circuit breaker protection.

        Args:
            operation: Async function to execute
            operation_name: Name of operation for logging

        Returns:
            Result of the operation

        Raises:
            CircuitBreakerError: If circuit breaker is open
            Exception: Original exception if operation fails
        """
        if not self._circuit_breaker:
            # Fallback to direct execution if circuit breaker not initialized
            logger.warning("Circuit breaker not initialized, executing operation directly: %s", operation_name)
            return await operation()

        try:
            return await self._circuit_breaker.call(operation)
        except CircuitBreakerError as e:
            # Circuit breaker is open - log and re-raise
            logger.error("QuickBooks %s blocked by circuit breaker: %s", operation_name, e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"QuickBooks service temporarily unavailable. Please try again later."
            ) from e

    async def _retry_operation(self, operation: Callable, operation_name: str, max_retries: int = 3) -> Any:
        """
        Retry mechanism for QuickBooks operations with circuit breaker protection.

        Args:
            operation: Async function to retry
            operation_name: Name of operation for logging
            max_retries: Maximum number of retry attempts

        Returns:
            Result of the operation

        Raises:
            Exception: The last exception if all retries fail
        """
        last_exception: Optional[Union[HTTPException, aiohttp.ClientError, asyncio.TimeoutError]] = None

        for attempt in range(max_retries + 1):
            try:
                # Execute with circuit breaker protection
                return await self._execute_with_circuit_breaker(operation, operation_name)
            except HTTPException as e:
                # Don't retry HTTP exceptions from circuit breaker or auth errors
                if e.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
                    # Circuit breaker is open
                    raise
                elif e.status_code in [401, 403]:
                    # Auth errors - don't retry
                    logger.error(f"QuickBooks {operation_name} failed with auth error: {e}")
                    raise
                else:
                    # Other HTTP errors - retry
                    last_exception = e
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e
            except Exception as e:
                # Don't retry on unexpected errors
                logger.error(f"QuickBooks {operation_name} failed with non-retryable error: {e}")
                raise

            # Retry logic
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    f"QuickBooks {operation_name} failed (attempt {attempt + 1}/{max_retries + 1}), "
                    f"retrying in {wait_time}s: {last_exception}"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"QuickBooks {operation_name} failed after {max_retries + 1} attempts: {last_exception}")

        if last_exception:
            raise last_exception
        raise RuntimeError(f"QuickBooks {operation_name} failed with unknown error")

    async def _throttle_api_call(self, call_count: int, batch_size: int = 5, delay: float = 0.5) -> None:
        """
        Throttle API calls to respect QuickBooks rate limits.
        
        QuickBooks API limits: 500 requests/minute, 10 concurrent requests.
        This adds a small delay every N calls to stay well under limits.
        
        Args:
            call_count: Current number of API calls made
            batch_size: Add delay after every N calls (default: 5)
            delay: Delay in seconds (default: 0.5s)
        """
        if call_count > 0 and call_count % batch_size == 0:
            await asyncio.sleep(delay)
            logger.debug(f"Throttled after {call_count} API calls ({delay}s delay)")

    def _log_operation(self, operation: str, level: str = "info", **context) -> None:
        """Log QuickBooks operation with structured context."""
        log_context = {
            "operation": operation,
            "user_id": str(self.user.id),
            "level": level,
            **context
        }

        if level == "error":
            logger.error(f"QuickBooks operation failed: {operation}", extra=log_context)
        elif level == "warning":
            logger.warning(f"QuickBooks operation completed with warnings: {operation}", extra=log_context)
        else:
            logger.info(f"QuickBooks operation completed: {operation}", extra=log_context)

    async def _update_integration_sync_time(self) -> None:
        """Update integration's last sync time."""
        if self.integration:
            self.integration.last_sync_at = create_audit_datetime()
            await self.session.commit()

    async def _get_cached_metadata(self, key: str, default=None) -> Any:
        """Get cached value from integration metadata."""
        if self.integration and self.integration.connection_metadata:
            return self.integration.connection_metadata.get(key, default)
        return default

    async def _cache_metadata(self, key: str, value: Any) -> None:
        """Cache value in integration metadata."""
        if self.integration:
            metadata = self.integration.connection_metadata or {}
            metadata[key] = value
            self.integration.connection_metadata = metadata
            self.session.add(self.integration)
            await self.session.commit()

    @property
    def client(self):
        """Get the QuickBooks client (must call initialize() first)."""
        if self._client is None:
            raise RuntimeError("Service not initialized. Call initialize() first.")
        return self._client

    @property
    def integration_id(self) -> int:
        """Get the integration ID (must call initialize() first)."""
        if self.integration is None:
            raise RuntimeError("Service not initialized. Call initialize() first.")
        if self.integration.id is None:
            raise RuntimeError("Integration ID is None")
        return self.integration.id

    def _create_sync_result(self, synced_count: int = 0, errors: Optional[list] = None, **kwargs) -> Dict[str, Any]:
        """Create standardized sync result format."""
        errors = errors or []

        return {
            "success": len(errors) == 0,
            "synced_count": synced_count,
            "errors": errors if errors else None,
            **kwargs
        }

    def _get_session_cache(self, key: str, default=None) -> Any:
        """Get value from session cache."""
        return self._session_cache.get(key, default)

    def _set_session_cache(self, key: str, value: Any) -> None:
        """Set value in session cache."""
        self._session_cache[key] = value

    async def _get_or_cache_quickbooks_data(self, cache_key: str, fetch_func: Callable) -> Any:
        """Get data from session cache or fetch and cache it."""
        cached_data = self._get_session_cache(cache_key)
        if cached_data is not None:
            return cached_data

        # Fetch data and cache it
        data = await fetch_func()
        self._set_session_cache(cache_key, data)
        return data

    async def _batch_create_with_errors(self, entities: list, create_func: Callable, entity_name: str) -> Dict[str, Any]:
        """
        Create entities in batches with error aggregation.

        Returns dict with created_count and errors list.
        """
        created_count = 0
        errors = []

        for entity in entities:
            try:
                result = await create_func(entity)
                if result:
                    created_count += 1
                else:
                    errors.append(f"Failed to create {entity_name}")
            except Exception as e:
                errors.append(f"Error creating {entity_name}: {str(e)}")
                logger.error(f"Error creating {entity_name}: {e}", exc_info=True)

        return {"created_count": created_count, "errors": errors}

    def _add_preview_item(self, entity_type: str, entity_id: str, entity_name: str,
                         action: SyncAction, details: Dict[str, Any], warnings: Optional[List[str]] = None) -> None:
        """Add an item to the preview collection."""
        if self.preview_mode:
            item = SyncItem(
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                action=action,
                details=details,
                warnings=warnings or []
            )
            self._preview_items.append(item)

    def _generate_preview(self) -> SyncPreview:
        """Generate a sync preview from collected items."""
        summary = {
            "create": sum(1 for item in self._preview_items if item.action == SyncAction.CREATE),
            "update": sum(1 for item in self._preview_items if item.action == SyncAction.UPDATE),
            "skip": sum(1 for item in self._preview_items if item.action == SyncAction.SKIP),
            "error": sum(1 for item in self._preview_items if item.action == SyncAction.ERROR),
            "total": len(self._preview_items)
        }

        global_warnings = []
        warning_count = sum(len(item.warnings or []) for item in self._preview_items)
        if warning_count > 0:
            global_warnings.append(f"{warning_count} items have warnings that require attention")

        return SyncPreview(
            items=self._preview_items,
            summary=summary,
            warnings=global_warnings
        )

    def _should_execute_action(self) -> bool:
        """Check if actions should be executed (not in preview mode)."""
        return not self.preview_mode


class TenantLeaseService(BaseQuickBooksService):
    """
    Extended base service for Invoice and Payment operations.

    Provides shared functionality for:
    - Tenant and lease prefetching to avoid N+1 queries
    - QB customer to Brikli tenant resolution
    - User property scoping for security
    """

    async def _prefetch_tenants_and_leases(self) -> Dict[str, Tuple["Tenant", Optional["Lease"]]]:
        """
        Prefetch all tenants with their active leases to avoid N+1 queries.

        Returns:
            Dict mapping QB customer ID to (Tenant, Optional[Lease]) tuple
        """
        # Import here to avoid circular imports
        from ....models.tenant import Tenant
        from ....models.lease import Lease, LeaseStatus

        # Get all user's tenants with QuickBooks IDs - SECURITY: Filter by landlord_id
        tenants = await self.session.scalars(
            select(Tenant).where(
                col(Tenant.landlord_id) == self.user.id,
                col(Tenant.quickbooks_customer_id).is_not(None)
            )
        )
        tenants_list = list(tenants)

        if not tenants_list:
            return {}

        # Get tenant IDs
        tenant_ids = [tenant.id for tenant in tenants_list]

        # Prefetch active leases for all tenants
        active_leases = await self.session.scalars(
            select(Lease).where(
                col(Lease.tenant_id).in_(tenant_ids),
                col(Lease.status) == LeaseStatus.ACTIVE
            ).order_by(desc(Lease.start_date))
        )

        # Create tenant to lease mapping (first/most recent active lease per tenant)
        lease_by_tenant: Dict[Any, Lease] = {}
        for lease in active_leases:
            if lease.tenant_id not in lease_by_tenant:
                lease_by_tenant[lease.tenant_id] = lease

        # Create customer ID to tenant+lease mapping
        result: Dict[str, Tuple[Tenant, Optional[Lease]]] = {}
        for tenant in tenants_list:
            if tenant.quickbooks_customer_id and tenant.id is not None:
                active_lease = lease_by_tenant.get(tenant.id)
                result[tenant.quickbooks_customer_id] = (tenant, active_lease)

        return result

    def _resolve_from_cache(
        self,
        qb_item: Dict[str, Any],
        tenant_cache: Dict[str, Tuple["Tenant", Optional["Lease"]]],
        get_customer_id_func: Callable[[Dict[str, Any]], Optional[str]]
    ) -> Tuple[Optional["Tenant"], Optional["Lease"]]:
        """
        Resolve tenant and lease from cached data.

        Args:
            qb_item: QuickBooks invoice or payment dict
            tenant_cache: Prefetched tenant cache from _prefetch_tenants_and_leases
            get_customer_id_func: Function to extract customer ID from QB item

        Returns:
            Tuple of (Tenant, Optional[Lease]) or (None, None)
        """
        qb_customer_id = get_customer_id_func(qb_item)
        if not qb_customer_id:
            return None, None

        tenant_lease_tuple = tenant_cache.get(qb_customer_id)
        if tenant_lease_tuple:
            return tenant_lease_tuple

        return None, None

    async def _get_user_property_ids(self) -> List[Any]:
        """
        Get property IDs owned by the current user.

        Returns:
            List of property UUIDs belonging to the user
        """
        from ....models.property import Property

        property_ids_result = await self.session.execute(
            select(Property.id).where(col(Property.user_id) == self.user.id)
        )
        return [row[0] for row in property_ids_result]

    async def _prefetch_tenants_by_ids(self, tenant_ids: List[Any]) -> Dict[Any, "Tenant"]:
        """
        Prefetch tenants by their IDs with ownership verification.

        Args:
            tenant_ids: List of tenant UUIDs

        Returns:
            Dict mapping tenant_id to Tenant object
        """
        from ....models.tenant import Tenant

        if not tenant_ids:
            return {}

        # SECURITY: Only fetch tenants belonging to this user
        tenants = await self.session.scalars(
            select(Tenant).where(
                col(Tenant.id).in_(tenant_ids),
                col(Tenant.landlord_id) == self.user.id  # Security check
            )
        )
        return {tenant.id: tenant for tenant in tenants}