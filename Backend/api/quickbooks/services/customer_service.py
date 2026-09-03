import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, UTC, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col

from Backend.models.user import User
from Backend.models.tenant import Tenant
from Backend.database import async_session
from ..schemas.customer import CustomerSchema
from .base_service import BaseQuickBooksService, SyncAction

logger = logging.getLogger(__name__)


class CustomerService(BaseQuickBooksService):
    """Service for QuickBooks Customer operations."""

    async def sync_customers(self) -> Dict[str, Any]:
        """Synchronize customers between QuickBooks and Brikli."""
        await self.initialize()

        all_errors = []
        total_synced = 0

        try:
            # Pull and link existing customers from QuickBooks
            pull_result = await self._pull_and_link_customers()
            total_synced += pull_result.get("linked_count", 0)
            all_errors.extend(pull_result.get("errors", []))

            # Push unlinked tenants to QuickBooks (creates new customers)
            push_result = await self._push_unlinked_tenants()
            total_synced += push_result.get("pushed_count", 0)
            all_errors.extend(push_result.get("errors", []))

            # Update existing linked customers that need updates
            update_result = await self._push_customer_updates()
            total_synced += update_result.get("updated_count", 0)
            all_errors.extend(update_result.get("errors", []))

            # Update integration sync time on success (skip in preview)
            if total_synced > 0 and len(all_errors) == 0 and self._should_execute_action():
                await self._update_integration_sync_time()

            self._log_operation(
                operation="sync_customers",
                level="info" if len(all_errors) == 0 else "warning",
                synced_count=total_synced,
                error_count=len(all_errors)
            )

            return self._create_sync_result(synced_count=total_synced, errors=all_errors)

        except Exception as e:
            logger.error(f"Error in customer sync for user {self.user.id}: {e}", exc_info=True)
            return self._create_sync_result(errors=[f"Customer sync failed: {str(e)}"])

    async def _pull_and_link_customers(self) -> Dict[str, Any]:
        """Pull customers from QuickBooks and link them to existing tenants."""
        linked_count = 0
        errors = []

        try:
            # Get customers from QuickBooks (cache for session)
            async def fetch_customers() -> List[Any]:
                customers_response = await self.client.list_customers(max_results=100)
                if customers_response and "QueryResponse" in customers_response:
                    return customers_response["QueryResponse"].get("Customer", [])
                return []

            qb_customers = await self._get_or_cache_quickbooks_data("qb_customers", fetch_customers)

            if not qb_customers:
                return {"linked_count": 0, "errors": ["No customers found in QuickBooks"]}

            # Get all user's tenants that don't have QuickBooks IDs in one query
            unlinked_tenants = await self.session.scalars(
                select(Tenant).where(
                    col(Tenant.landlord_id) == self.user.id,
                    col(Tenant.quickbooks_customer_id).is_(None)
                )
            )
            unlinked_tenants_list = list(unlinked_tenants)

            if not unlinked_tenants_list:
                return {"linked_count": 0, "errors": []}

            # Build a set of QB customer IDs already linked to other tenants
            linked_qb_ids = await self._get_already_linked_qb_customer_ids()

            # Track QB IDs we've claimed in this session to avoid duplicates
            claimed_qb_ids: set = set()

            # Create email lookup for QuickBooks customers
            qb_customers_by_email = {}
            for qb_customer in qb_customers:
                qb_email_obj = qb_customer.get("PrimaryEmailAddr", {})
                qb_email = qb_email_obj.get("Address", "") if qb_email_obj else ""
                if qb_email:
                    qb_customers_by_email[qb_email.lower()] = qb_customer

            # Match tenants to customers by email
            for tenant in unlinked_tenants_list:
                if not tenant.email:
                    continue

                qb_customer = qb_customers_by_email.get(tenant.email.lower())
                if qb_customer:
                    qb_id = qb_customer.get("Id")

                    # Skip if this QB customer is already linked to another tenant
                    if qb_id in linked_qb_ids or qb_id in claimed_qb_ids:
                        logger.debug(f"Skipping QB customer {qb_id} - already linked to another tenant")
                        continue

                    claimed_qb_ids.add(qb_id)
                    linked_count += 1
                    if self.preview_mode:
                        self._add_preview_item(
                            entity_type="customer_link",
                            entity_id=str(tenant.id),
                            entity_name=f"{tenant.first_name or tenant.company_name or ''} {tenant.last_name or ''}".strip() or "Tenant",
                            action=SyncAction.UPDATE,
                            details={
                                "qb_customer_id": qb_id,
                                "qb_display_name": qb_customer.get("DisplayName"),
                            },
                            warnings=[]
                        )
                    else:
                        tenant.quickbooks_customer_id = qb_id
                        tenant.last_synced_at = datetime.now(UTC)
                        self.session.add(tenant)
                        logger.info(f"Linked tenant {tenant.id} to QuickBooks customer {tenant.quickbooks_customer_id}")

            if linked_count > 0 and self._should_execute_action():
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error pulling customers from QuickBooks: {e}", exc_info=True)
            errors.append(f"Pull customers failed: {str(e)}")

        return {"linked_count": linked_count, "errors": errors}

    async def _push_unlinked_tenants(self) -> Dict[str, Any]:
        """Push unlinked tenants to QuickBooks as customers."""
        pushed_count = 0
        errors = []
        BATCH_SIZE = 50  # Limit to prevent timeout
        COMMIT_BATCH_SIZE = 10  # Commit every N items for progress checkpoints

        try:
            # Get tenants that haven't been synced to QuickBooks
            unlinked_tenants = await self.session.scalars(
                select(Tenant).where(
                    col(Tenant.landlord_id) == self.user.id,
                    col(Tenant.quickbooks_customer_id).is_(None),
                    col(Tenant.email).is_not(None)
                ).limit(BATCH_SIZE)  # Add limit to prevent overwhelming API
            )
            unlinked_tenants_list = list(unlinked_tenants)

            if not unlinked_tenants_list:
                return {"pushed_count": 0, "errors": []}

            # OPTIMIZATION: Use cached customer list instead of individual API calls per tenant
            # This reduces O(n) API calls to O(1) by reusing the list fetched in _pull_and_link_customers
            qb_customers_by_email = await self._get_cached_customers_by_email()

            # Also build a DisplayName lookup for better matching
            qb_customers_by_name = await self._get_cached_customers_by_name()

            # Build a set of QB customer IDs already linked to other tenants
            linked_qb_ids = await self._get_already_linked_qb_customer_ids()

            # Track QB IDs we've claimed in this session to avoid duplicates
            claimed_qb_ids: set = set()
            api_call_count = 0  # Track API calls for throttling

            for idx, tenant in enumerate(unlinked_tenants_list):
                try:
                    # Check for existing customer by email using cached lookup
                    if not tenant.email:
                        continue

                    qb_customer = qb_customers_by_email.get(tenant.email.lower())
                    existing_customer_id = qb_customer.get("Id") if qb_customer else None
                    qb_display_name = qb_customer.get("DisplayName") if qb_customer else None

                    # If not found by email, try matching by DisplayName
                    if not existing_customer_id:
                        tenant_display_name = f"{tenant.first_name or ''} {tenant.last_name or ''}".strip()
                        if not tenant_display_name and tenant.company_name:
                            tenant_display_name = tenant.company_name
                        if tenant_display_name:
                            qb_customer_by_name = qb_customers_by_name.get(tenant_display_name.lower())
                            if qb_customer_by_name:
                                existing_customer_id = qb_customer_by_name.get("Id")
                                qb_display_name = qb_customer_by_name.get("DisplayName")

                    if existing_customer_id:
                        # Check if this QB customer is already linked to another tenant
                        if existing_customer_id in linked_qb_ids or existing_customer_id in claimed_qb_ids:
                            logger.debug(f"Skipping QB customer {existing_customer_id} - already linked to another tenant")
                            continue

                        claimed_qb_ids.add(existing_customer_id)

                        # Link to existing customer
                        pushed_count += 1
                        if self.preview_mode:
                            self._add_preview_item(
                                entity_type="customer_link",
                                entity_id=str(tenant.id),
                                entity_name=f"{tenant.first_name or tenant.company_name or ''} {tenant.last_name or ''}".strip() or "Tenant",
                                action=SyncAction.UPDATE,
                                details={
                                    "qb_customer_id": existing_customer_id,
                                    "qb_display_name": qb_display_name,
                                },
                                warnings=[]
                            )
                        else:
                            tenant.quickbooks_customer_id = existing_customer_id
                            tenant.last_synced_at = datetime.now(UTC)
                            self.session.add(tenant)
                            logger.info(f"Linked tenant {tenant.id} to existing QuickBooks customer {existing_customer_id}")
                    else:
                        # Create new customer (synthesize in preview, real create otherwise)
                        if self.preview_mode:
                            self._add_preview_item(
                                entity_type="customer_create",
                                entity_id=str(tenant.id),
                                entity_name=f"{tenant.first_name or tenant.company_name or ''} {tenant.last_name or ''}".strip() or "Tenant",
                                action=SyncAction.CREATE,
                                details={
                                    "destination": "QuickBooks",
                                },
                                warnings=[]
                            )
                            pushed_count += 1
                        else:
                            customer_id = await self._create_customer_in_quickbooks(tenant)
                            if customer_id:
                                tenant.quickbooks_customer_id = customer_id
                                tenant.last_synced_at = datetime.now(UTC)
                                self.session.add(tenant)
                                pushed_count += 1
                                api_call_count += 1
                                logger.info(f"Created QuickBooks customer {customer_id} for tenant {tenant.id}")
                                
                                # Throttle API calls to respect rate limits
                                await self._throttle_api_call(api_call_count)
                            else:
                                errors.append(f"Failed to create QuickBooks customer for tenant {tenant.id}")

                    # Batch commit every COMMIT_BATCH_SIZE items for progress checkpoints
                    if (idx + 1) % COMMIT_BATCH_SIZE == 0 and pushed_count > 0 and self._should_execute_action():
                        await self.session.commit()
                        logger.info(f"Committed batch progress: {pushed_count} customers synced so far")

                except Exception as e:
                    error_msg = f"Error processing tenant {tenant.id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

            # Final commit for remaining items
            if pushed_count > 0 and self._should_execute_action():
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error pushing tenants to QuickBooks: {e}", exc_info=True)
            errors.append(f"Push tenants failed: {str(e)}")

        return {"pushed_count": pushed_count, "errors": errors}

    async def _push_customer_updates(self) -> Dict[str, Any]:
        """Update existing QuickBooks customers that need updates."""
        updated_count = 0
        errors = []

        try:
            # Get tenants that have QuickBooks IDs (already linked)
            linked_tenants = await self.session.scalars(
                select(Tenant).where(
                    col(Tenant.landlord_id) == self.user.id,
                    col(Tenant.quickbooks_customer_id).is_not(None)
                )
            )
            linked_tenants_list = list(linked_tenants)

            if not linked_tenants_list:
                return {"updated_count": 0, "errors": []}

            # Process tenants in batches to avoid timeout
            batch_size = 10
            for i in range(0, len(linked_tenants_list), batch_size):
                batch_tenants = linked_tenants_list[i:i + batch_size]

                for tenant in batch_tenants:
                    try:
                        # Skip if updated recently (within last hour)
                        if (tenant.last_synced_at and
                            tenant.last_synced_at > datetime.now(UTC) - timedelta(hours=1)):
                            continue

                        # Get current customer data from QuickBooks
                        current_customer = await self.client.get_customer(tenant.quickbooks_customer_id)
                        if not current_customer or "Customer" not in current_customer:
                            logger.warning(f"Could not retrieve QuickBooks customer {tenant.quickbooks_customer_id} for tenant {tenant.id}")
                            continue

                        qb_customer = current_customer["Customer"]

                        # Check if update is needed
                        if CustomerSchema.needs_update(qb_customer, tenant):
                            if self.preview_mode:
                                self._add_preview_item(
                                    entity_type="customer_update",
                                    entity_id=str(tenant.id),
                                    entity_name=f"{tenant.first_name or tenant.company_name or ''} {tenant.last_name or ''}".strip() or "Tenant",
                                    action=SyncAction.UPDATE,
                                    details={
                                        "destination": "QuickBooks",
                                    },
                                    warnings=[]
                                )
                                updated_count += 1
                            else:
                                success = await self.update_customer_in_quickbooks(tenant)
                                if success:
                                    updated_count += 1
                                    logger.info(f"Updated QuickBooks customer {tenant.quickbooks_customer_id} for tenant {tenant.id}")
                                else:
                                    errors.append(f"Failed to update QuickBooks customer for tenant {tenant.id}")
                        else:
                            # No update needed, but refresh sync timestamp
                            tenant.last_synced_at = datetime.now(UTC)
                            self.session.add(tenant)

                    except Exception as e:
                        error_msg = f"Error processing tenant {tenant.id} for update: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg, exc_info=True)

                # Commit after each batch
                if self._should_execute_action():
                    await self.session.commit()

        except Exception as e:
            logger.error(f"Error pushing customer updates to QuickBooks: {e}", exc_info=True)
            errors.append(f"Push customer updates failed: {str(e)}")

        return {"updated_count": updated_count, "errors": errors}

    async def preview_customers(self):
        """Preview what would happen during customer synchronization."""
        preview_service = CustomerService(self.user, self.session, preview_mode=True)
        await preview_service.initialize()
        await preview_service.sync_customers()
        return preview_service._generate_preview()

    async def _get_cached_customers_by_email(self) -> Dict[str, Any]:
        """
        Get a cached email-to-customer lookup dictionary.

        OPTIMIZATION: This eliminates O(n) API calls when checking for existing customers.
        Uses the same customer list fetched in _pull_and_link_customers.
        """
        async def build_email_lookup() -> Dict[str, Any]:
            # Get customers from QuickBooks (uses session cache)
            async def fetch_customers() -> List[Any]:
                customers_response = await self.client.list_customers(max_results=100)
                if customers_response and "QueryResponse" in customers_response:
                    return customers_response["QueryResponse"].get("Customer", [])
                return []

            qb_customers = await self._get_or_cache_quickbooks_data("qb_customers", fetch_customers)

            # Build email lookup dictionary
            email_lookup: Dict[str, Any] = {}
            for qb_customer in qb_customers:
                qb_email_obj = qb_customer.get("PrimaryEmailAddr", {})
                qb_email = qb_email_obj.get("Address", "") if qb_email_obj else ""
                if qb_email:
                    email_lookup[qb_email.lower()] = qb_customer
            return email_lookup

        return await self._get_or_cache_quickbooks_data("qb_customers_by_email", build_email_lookup)

    async def _get_already_linked_qb_customer_ids(self) -> set:
        """
        Get a set of QuickBooks customer IDs that are already linked to tenants.

        Used to prevent linking the same QB customer to multiple tenants.
        """
        async def build_linked_set() -> set:
            # Get all tenants that already have QB customer IDs
            linked_tenants = await self.session.scalars(
                select(Tenant).where(
                    col(Tenant.landlord_id) == self.user.id,
                    col(Tenant.quickbooks_customer_id).is_not(None)
                )
            )

            return {tenant.quickbooks_customer_id for tenant in linked_tenants.all()}

        return await self._get_or_cache_quickbooks_data("linked_qb_customer_ids", build_linked_set)

    async def _get_cached_customers_by_name(self) -> Dict[str, Any]:
        """
        Get a cached DisplayName-to-customer lookup dictionary.

        Used for matching tenants to QuickBooks customers by name when email doesn't match.
        """
        async def build_name_lookup() -> Dict[str, Any]:
            # Get customers from QuickBooks (uses session cache)
            async def fetch_customers() -> List[Any]:
                customers_response = await self.client.list_customers(max_results=100)
                if customers_response and "QueryResponse" in customers_response:
                    return customers_response["QueryResponse"].get("Customer", [])
                return []

            qb_customers = await self._get_or_cache_quickbooks_data("qb_customers", fetch_customers)

            # Build name lookup dictionary (case-insensitive)
            name_lookup: Dict[str, Any] = {}
            for qb_customer in qb_customers:
                display_name = qb_customer.get("DisplayName", "")
                if display_name:
                    name_lookup[display_name.lower()] = qb_customer
            return name_lookup

        return await self._get_or_cache_quickbooks_data("qb_customers_by_name", build_name_lookup)

    async def _find_existing_customer_by_email(self, email: str) -> Optional[str]:
        """
        Find existing QuickBooks customer by email.

        NOTE: This method is kept for backward compatibility but now uses the cached lookup.
        For bulk operations, use _get_cached_customers_by_email() directly.
        """
        try:
            # Use cached lookup instead of individual API call
            email_lookup = await self._get_cached_customers_by_email()
            qb_customer = email_lookup.get(email.lower())
            if qb_customer:
                return qb_customer.get("Id")
        except Exception as e:
            logger.warning(f"Error searching for existing customer with email {email}: {e}")

        return None

    async def _create_customer_in_quickbooks(self, tenant: Tenant) -> Optional[str]:
        """Create a customer in QuickBooks."""
        display_name = ""
        try:
            # Validate tenant data before creating customer
            validation_errors = CustomerSchema.validate_for_quickbooks(tenant)
            if validation_errors:
                error_msg = f"Validation failed for tenant {tenant.id}: {validation_errors}"
                logger.warning(error_msg)
                # Continue with creation but log warnings

            customer_data = CustomerSchema.to_quickbooks(tenant)
            display_name = customer_data.get("DisplayName", "")

            async def create_operation() -> Optional[Dict[str, Any]]:
                return await self.client.create_customer(customer_data)

            response = await self._retry_operation(
                create_operation,
                f"create_customer_{tenant.id}",
                max_retries=2
            )

            if response and "Customer" in response:
                customer_id = response["Customer"].get("Id")
                if customer_id:
                    logger.info(f"Successfully created QuickBooks customer with ID: {customer_id}")
                    return customer_id
                else:
                    logger.error("Customer creation response missing ID field")
            else:
                logger.error("Invalid customer creation response from QuickBooks")

        except Exception as e:
            error_str = str(e)
            # Handle "Duplicate Name Exists Error" (code 6240) by searching for existing customer
            if "Duplicate Name Exists" in error_str or "6240" in error_str:
                logger.info(f"Customer with name '{display_name}' already exists in QuickBooks, searching to link")
                existing_id = await self._find_customer_by_display_name(display_name)
                if existing_id:
                    logger.info(f"Found existing customer by DisplayName '{display_name}': {existing_id}")
                    return existing_id
                else:
                    logger.warning(f"Could not find existing customer by DisplayName '{display_name}'")
            else:
                logger.error(f"Failed to create customer in QuickBooks: {e}", exc_info=True)

        return None

    async def _find_customer_by_display_name(self, display_name: str) -> Optional[str]:
        """
        Search for a QuickBooks customer by DisplayName.

        Used as fallback when customer creation fails due to duplicate name.
        """
        if not display_name:
            return None

        try:
            # First check the cached customer list
            async def fetch_customers() -> List[Any]:
                customers_response = await self.client.list_customers(max_results=100)
                if customers_response and "QueryResponse" in customers_response:
                    return customers_response["QueryResponse"].get("Customer", [])
                return []

            qb_customers = await self._get_or_cache_quickbooks_data("qb_customers", fetch_customers)

            # Search in cached customers first
            for qb_customer in qb_customers:
                if qb_customer.get("DisplayName", "").lower() == display_name.lower():
                    return qb_customer.get("Id")

            # If not found in cache, do a direct query (cache might be stale)
            # Escape single quotes in display name for the query
            escaped_name = display_name.replace("'", "\\'")
            query = f"SELECT * FROM Customer WHERE DisplayName = '{escaped_name}'"
            response = await self.client.query(query)

            if response and "QueryResponse" in response:
                customers = response["QueryResponse"].get("Customer", [])
                if customers:
                    return customers[0].get("Id")

        except Exception as e:
            logger.warning(f"Error searching for customer by DisplayName '{display_name}': {e}")

        return None

    async def update_customer_in_quickbooks(self, tenant: Tenant) -> bool:
        """
        Update an existing QuickBooks customer with current tenant data.

        Args:
            tenant: Tenant object with QuickBooks ID to update

        Returns:
            True if update successful, False otherwise
        """
        if not tenant.quickbooks_customer_id:
            logger.warning(f"Cannot update customer: tenant {tenant.id} has no QuickBooks Customer ID")
            return False

        try:
            await self.initialize()

            # First, get the current customer data from QuickBooks to get the SyncToken
            current_customer = await self.client.get_customer(tenant.quickbooks_customer_id)
            if not current_customer or "Customer" not in current_customer:
                logger.error(f"Could not retrieve QuickBooks customer {tenant.quickbooks_customer_id} for update")
                return False

            qb_customer = current_customer["Customer"]
            sync_token = qb_customer.get("SyncToken")
            if not sync_token:
                logger.error(f"Missing SyncToken for QuickBooks customer {tenant.quickbooks_customer_id}")
                return False

            # Check if update is actually needed
            if not CustomerSchema.needs_update(qb_customer, tenant):
                logger.info(f"No update needed for QuickBooks customer {tenant.quickbooks_customer_id}")
                tenant.last_synced_at = datetime.now(UTC)
                self.session.add(tenant)
                await self.session.commit()
                return True

            # Prepare update data
            update_data = CustomerSchema.to_quickbooks_update(tenant, tenant.quickbooks_customer_id, sync_token)

            # Perform the update with retry
            async def update_operation() -> Optional[Dict[str, Any]]:
                return await self.client.update_customer(tenant.quickbooks_customer_id, update_data)

            response = await self._retry_operation(
                update_operation,
                f"update_customer_{tenant.id}",
                max_retries=2
            )

            if response and "Customer" in response:
                # Update successful, update sync timestamp
                tenant.last_synced_at = datetime.now(UTC)
                self.session.add(tenant)
                await self.session.commit()

                logger.info(f"Successfully updated QuickBooks customer {tenant.quickbooks_customer_id} for tenant {tenant.id}")

                self._log_operation(
                    operation="update_customer",
                    level="info",
                    status="success",
                    tenant_id=tenant.id,
                    customer_id=tenant.quickbooks_customer_id
                )
                return True
            else:
                logger.error(f"Invalid response from QuickBooks customer update for tenant {tenant.id}")
                return False

        except Exception as e:
            logger.error(f"Failed to update QuickBooks customer for tenant {tenant.id}: {e}", exc_info=True)
            self._log_operation(
                operation="update_customer",
                level="error",
                status="failed",
                tenant_id=tenant.id,
                customer_id=tenant.quickbooks_customer_id,
                error=str(e)
            )
            return False

    async def link_or_create_qb_customer(self, tenant_data: Dict[str, Any]) -> Optional[str]:
        """
        Links a tenant to an existing QuickBooks customer or creates a new one.

        This function is used by the tenants service to sync individual tenants
        with QuickBooks customers during tenant creation.

        Args:
            tenant_data: Dictionary containing tenant information including:
                - email: Required for linking/creating
                - first_name: Optional
                - last_name: Optional
                - phone: Optional
                - id: Tenant ID for logging

        Returns:
            QuickBooks customer ID if successful, None otherwise

        Raises:
            HTTPException: If QuickBooks integration is not configured
        """
        async with async_session() as session:
            service = CustomerService(self.user, session)
            await service.initialize()

            email = tenant_data.get("email")
            if not email:
                logger.warning("Cannot link/create QuickBooks customer: email is required")
                return None

            try:
                # First, search for existing customer by email
                existing_customer_id = await service._find_existing_customer_by_email(email)

                if existing_customer_id:
                    # Log successful linking to existing customer
                    service._log_operation(
                        operation="link_customer",
                        level="info",
                        status="linked_existing",
                        tenant_id=tenant_data.get("id"),
                        customer_id=existing_customer_id
                    )
                    return existing_customer_id

                # No existing customer found, create a new one
                # Create a temporary tenant object for schema transformation
                temp_tenant = Tenant(
                    first_name=tenant_data.get("first_name"),
                    last_name=tenant_data.get("last_name"),
                    email=tenant_data.get("email"),
                    phone=tenant_data.get("phone"),
                    user_id=self.user.id
                )

                customer_id = await service._create_customer_in_quickbooks(temp_tenant)

                if customer_id:
                    # Log successful customer creation
                    service._log_operation(
                        operation="create_customer",
                        level="info",
                        status="created",
                        tenant_id=tenant_data.get("id"),
                        customer_id=customer_id
                    )
                    return customer_id
                else:
                    # Log failure to create customer
                    service._log_operation(
                        operation="create_customer",
                        level="error",
                        status="failed",
                        tenant_id=tenant_data.get("id"),
                        error="Failed to create customer in QuickBooks"
                    )
                    return None

            except Exception as e:
                # Log operation failure
                service._log_operation(
                    operation="link_or_create_customer",
                    level="error",
                    status="failed",
                    tenant_id=tenant_data.get("id"),
                    error=str(e)
                )
                logger.error(f"Error linking/creating QuickBooks customer for tenant {tenant_data.get('id')}: {e}", exc_info=True)
                raise