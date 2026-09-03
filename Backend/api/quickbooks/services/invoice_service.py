import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select, col, desc

from ....models.user import User
from ....models.tenant import Tenant
from ....models.property import Property
from ....models.lease import Lease, LeaseStatus
from ....models.accounting.invoice import Invoice
from ..schemas.invoice import InvoiceSchema
from .base_service import TenantLeaseService, SyncAction, SyncPreview

logger = logging.getLogger(__name__)


class InvoiceService(TenantLeaseService):
    """Service for QuickBooks Invoice operations."""

    async def sync_invoices(self) -> Dict[str, Any]:
        """Perform bidirectional invoice synchronization."""
        return await self.sync_invoices_internal()

    async def sync_single_invoice_from_quickbooks(self, qb_invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sync a single invoice from QuickBooks webhook event.

        This is more efficient than a full sync when processing webhooks,
        as it only processes the specific entity that changed.

        Args:
            qb_invoice_data: The Invoice object from QuickBooks API

        Returns:
            Dict with sync result (synced_count, errors)
        """
        await self.initialize()
        errors: list[str] = []

        qb_invoice_id = qb_invoice_data.get("Id")
        if not qb_invoice_id:
            return {"synced_count": 0, "errors": ["Invoice data missing ID"]}

        try:
            # Check if invoice already exists in our system
            # SECURITY: Join through Tenant and verify landlord_id to prevent cross-tenant data access
            existing_invoice = await self.session.scalar(
                select(Invoice)
                .join(Tenant, col(Invoice.tenant_id) == col(Tenant.id))
                .where(
                    col(Invoice.quickbooks_id) == qb_invoice_id,
                    col(Tenant.landlord_id) == self.user.id  # SECURITY: Verify ownership
                )
            )

            if existing_invoice:
                # Update existing invoice
                return await self._update_single_invoice(existing_invoice, qb_invoice_data)
            else:
                # Create new invoice
                return await self._create_single_invoice(qb_invoice_data)

        except Exception as e:
            error_msg = f"Error syncing single invoice {qb_invoice_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"synced_count": 0, "errors": [error_msg]}

    async def _update_single_invoice(self, invoice: Invoice, qb_invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing invoice with QuickBooks data."""
        try:
            # Update fields from QB data
            invoice.amount = InvoiceSchema.parse_amount(qb_invoice_data.get("TotalAmt"))
            parsed_due_date = InvoiceSchema.parse_date(qb_invoice_data.get("DueDate"))
            if parsed_due_date is not None:
                invoice.due_date = parsed_due_date
            invoice.last_synced_at = datetime.now(UTC)

            # Update status based on Balance
            from ....models.accounting.common import PaymentStatus
            balance = InvoiceSchema.parse_amount(qb_invoice_data.get("Balance", 0))
            if balance == 0 and invoice.amount and invoice.amount > 0:
                invoice.status = PaymentStatus.PAID
            elif balance and balance > 0:
                invoice.status = PaymentStatus.PENDING  # Outstanding balance = pending payment

            self.session.add(invoice)
            await self.session.commit()

            logger.info(f"Updated invoice {invoice.id} from QB invoice {qb_invoice_data.get('Id')}")
            return {"synced_count": 1, "errors": []}

        except Exception as e:
            error_msg = f"Error updating invoice: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"synced_count": 0, "errors": [error_msg]}

    async def _create_single_invoice(self, qb_invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new invoice from QuickBooks data."""
        qb_invoice_id = qb_invoice_data.get("Id")

        try:
            # Prefetch tenants and leases
            tenants_with_leases = await self._prefetch_tenants_and_leases()

            # Resolve tenant and lease
            tenant, lease = self._resolve_from_cache(
                qb_invoice_data, tenants_with_leases, InvoiceSchema.get_customer_id
            )

            if not tenant or not lease:
                logger.warning(f"Skipping invoice {qb_invoice_id} - could not resolve tenant/lease")
                return {"synced_count": 0, "errors": [f"Could not resolve tenant/lease for invoice {qb_invoice_id}"]}

            # Check for duplicate invoice_number
            doc_number = qb_invoice_data.get("DocNumber", f"QB-{qb_invoice_id}")
            existing_number = await self.session.scalar(
                select(Invoice.id).where(col(Invoice.invoice_number) == doc_number)
            )
            if existing_number:
                doc_number = f"QB-{qb_invoice_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                qb_invoice_data["DocNumber"] = doc_number

            # Create the invoice
            new_invoice, tax_details = InvoiceSchema.from_quickbooks(qb_invoice_data, lease, tenant)
            self.session.add(new_invoice)
            await self.session.flush()

            # Add tax details if present
            if tax_details:
                # Ensure invoice ID was assigned after flush
                if new_invoice.id is None:
                    raise ValueError("Invoice ID was not assigned after database flush")
                
                for tax_detail in tax_details:
                    tax_detail.invoice_id = new_invoice.id
                    self.session.add(tax_detail)

            await self.session.commit()

            logger.info(f"Created invoice from QB invoice {qb_invoice_id}")
            return {"synced_count": 1, "errors": []}

        except Exception as e:
            error_msg = f"Error creating invoice from QB {qb_invoice_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"synced_count": 0, "errors": [error_msg]}

    async def preview_invoices(self) -> SyncPreview:
        """Preview what would happen during invoice synchronization."""
        # Create a preview-mode service
        preview_service = InvoiceService(self.user, self.session, preview_mode=True)
        await preview_service.initialize()
        await preview_service.sync_invoices_internal()
        return preview_service._generate_preview()

    async def sync_invoices_internal(self) -> Dict[str, Any]:
        """Perform bidirectional invoice synchronization."""
        await self.initialize()

        all_errors = []
        pulled_count = 0
        pushed_count = 0
        updated_count = 0

        try:
            # Pull invoices from QuickBooks
            pull_result = await self._pull_invoices_from_quickbooks()
            pulled_count = pull_result.get("synced_count", 0)
            all_errors.extend(pull_result.get("errors", []))

            # Push NEW invoices to QuickBooks
            push_result = await self._push_invoices_to_quickbooks()
            pushed_count = push_result.get("pushed_count", 0)
            all_errors.extend(push_result.get("errors", []))

            # Update MODIFIED invoices in QuickBooks
            update_result = await self._update_invoices_in_quickbooks()
            updated_count = update_result.get("updated_count", 0)
            all_errors.extend(update_result.get("errors", []))

            total_synced = pulled_count + pushed_count + updated_count

            # Update integration sync time on success
            if total_synced > 0 and len(all_errors) == 0:
                await self._update_integration_sync_time()

            self._log_operation(
                operation="sync_invoices",
                level="info" if len(all_errors) == 0 else "warning",
                synced_count=total_synced,
                pulled_count=pulled_count,
                pushed_count=pushed_count,
                updated_count=updated_count,
                error_count=len(all_errors)
            )

            return self._create_sync_result(
                synced_count=total_synced,
                pulled_count=pulled_count,
                pushed_count=pushed_count,
                updated_count=updated_count,
                errors=all_errors
            )

        except Exception as e:
            logger.error(f"Error in invoice sync for user {self.user.id}: {e}", exc_info=True)
            return self._create_sync_result(errors=[f"Invoice sync failed: {str(e)}"])

    async def _pull_invoices_from_quickbooks(self) -> Dict[str, Any]:
        """Pull invoices from QuickBooks and sync to local database."""
        new_invoices_count = 0
        errors = []

        try:
            # Get invoices from QuickBooks
            invoices_response = await self.client.list_invoices(max_results=100)

            if not invoices_response or "QueryResponse" not in invoices_response:
                return {"synced_count": 0, "errors": ["No invoices found in QuickBooks"]}

            qb_invoices = invoices_response["QueryResponse"].get("Invoice", [])
            if not qb_invoices:
                return {"synced_count": 0, "errors": []}

            # Get existing invoice IDs and invoice_numbers to avoid duplicates
            qb_invoice_ids = [invoice.get("Id") for invoice in qb_invoices if invoice.get("Id")]
            existing_ids_result = await self.session.execute(
                select(Invoice.quickbooks_id).where(col(Invoice.quickbooks_id).in_(qb_invoice_ids))
            )
            existing_ids = {row[0] for row in existing_ids_result}

            # Also get existing invoice_numbers to avoid unique constraint violations
            qb_doc_numbers = [invoice.get("DocNumber", f"QB-{invoice.get('Id')}") for invoice in qb_invoices if invoice.get("Id")]
            existing_numbers_result = await self.session.execute(
                select(Invoice.invoice_number).where(col(Invoice.invoice_number).in_(qb_doc_numbers))
            )
            existing_invoice_numbers = {row[0] for row in existing_numbers_result}

            # Prefetch all tenants and their active leases for this user to avoid N+1 queries
            tenants_with_leases = await self._prefetch_tenants_and_leases()

            for qb_invoice in qb_invoices:
                qb_invoice_id = qb_invoice.get("Id")
                if not qb_invoice_id or qb_invoice_id in existing_ids:
                    continue

                # Check if invoice_number already exists (unique constraint)
                doc_number = qb_invoice.get("DocNumber", f"QB-{qb_invoice_id}")
                if doc_number in existing_invoice_numbers:
                    # Invoice number already exists - either link to existing or generate unique
                    logger.info(f"Invoice number {doc_number} already exists, generating unique number for QB invoice {qb_invoice_id}")
                    doc_number = f"QB-{qb_invoice_id}"
                    # If even that exists, add timestamp
                    if doc_number in existing_invoice_numbers:
                        doc_number = f"QB-{qb_invoice_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    # Update the qb_invoice dict so from_quickbooks uses the unique number
                    qb_invoice["DocNumber"] = doc_number
                    existing_invoice_numbers.add(doc_number)  # Track to avoid duplicates within this batch

                try:
                    # Resolve tenant and lease using prefetched data (uses base class method)
                    tenant, lease = self._resolve_from_cache(
                        qb_invoice, tenants_with_leases, InvoiceSchema.get_customer_id
                    )

                    if not tenant or not lease:
                        logger.warning(f"Skipping invoice {qb_invoice_id} - could not resolve tenant/lease")
                        continue

                    # Create Brikli invoice from QuickBooks data
                    new_invoice, tax_details = InvoiceSchema.from_quickbooks(qb_invoice, lease, tenant)

                    # In preview mode, collect item for preview
                    if self.preview_mode:
                        warnings: list[str] = []
                        if len(tax_details) == 0:
                            warnings.append("No tax details found")

                        self._add_preview_item(
                            entity_type="invoice",
                            entity_id=qb_invoice_id,
                            entity_name=f"Invoice for {tenant.first_name} {tenant.last_name}" if tenant else f"QB Invoice {qb_invoice_id}",
                            action=SyncAction.CREATE,
                            details={
                                "amount": float(new_invoice.amount) if new_invoice.amount else 0,
                                "due_date": new_invoice.due_date.isoformat() if new_invoice.due_date else None,
                                "tenant": f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown",
                                "tax_details_count": len(tax_details)
                            },
                            warnings=warnings
                        )
                    else:
                        # Execute the actual creation
                        self.session.add(new_invoice)

                        # Flush to get the invoice ID assigned for tax details
                        await self.session.flush()

                        # Add tax details if any
                        for tax_detail in tax_details:
                            if new_invoice.id is None:
                                raise ValueError(f"Failed to get invoice ID after flush for QB invoice {qb_invoice_id}")
                            tax_detail.invoice_id = new_invoice.id
                            self.session.add(tax_detail)

                        logger.info(f"Synced invoice {qb_invoice_id} from QuickBooks")

                    new_invoices_count += 1

                except Exception as e:
                    error_msg = f"Error processing invoice {qb_invoice_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

            if new_invoices_count > 0 and self._should_execute_action():
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error pulling invoices from QuickBooks: {e}", exc_info=True)
            errors.append(f"Pull invoices failed: {str(e)}")

        return {"synced_count": new_invoices_count, "errors": errors}

    async def _push_invoices_to_quickbooks(self) -> Dict[str, Any]:
        """Push unsynced Brikli invoices to QuickBooks."""
        pushed_count = 0
        errors = []

        try:
            # Get user's properties (uses base class method)
            property_ids = await self._get_user_property_ids()

            if not property_ids:
                return {"pushed_count": 0, "errors": ["No properties found for user"]}

            # Find invoices that haven't been synced to QuickBooks
            # SECURITY: Join through Tenant and verify landlord_id
            unsynced_invoices = await self.session.scalars(
                select(Invoice)
                .join(Tenant, col(Invoice.tenant_id) == col(Tenant.id))
                .where(
                    col(Invoice.property_id).in_(property_ids),
                    col(Tenant.landlord_id) == self.user.id,  # SECURITY: Verify ownership
                    col(Invoice.quickbooks_id).is_(None),
                    col(Tenant.quickbooks_customer_id).is_not(None)  # Tenant must be synced first
                ).limit(50)  # Limit to avoid timeout
            )
            unsynced_invoices_list = list(unsynced_invoices)

            if not unsynced_invoices_list:
                return {"pushed_count": 0, "errors": []}

            # Prefetch all tenants with ownership verification (uses base class method)
            tenant_ids = [invoice.tenant_id for invoice in unsynced_invoices_list]
            tenants_by_id = await self._prefetch_tenants_by_ids(tenant_ids)

            # Cache service item to avoid multiple API calls
            service_item_id = await self._get_or_cache_service_item()

            # Get exempt tax code for residential rent (required for Canadian QB)
            # Residential rent is typically GST/HST exempt
            exempt_tax_code = await self._get_or_cache_exempt_tax_code()

            api_call_count = 0  # Track API calls for throttling
            COMMIT_BATCH_SIZE = 10  # Commit every N items

            for idx, invoice in enumerate(unsynced_invoices_list):
                try:
                    # Get tenant from prefetched data
                    tenant = tenants_by_id.get(invoice.tenant_id)
                    if not tenant or not tenant.quickbooks_customer_id:
                        errors.append(f"Invoice {invoice.id}: Tenant not synced to QuickBooks")
                        continue

                    # Build QuickBooks invoice data with exempt tax code for residential rent
                    invoice_data = InvoiceSchema.to_quickbooks(
                        invoice, tenant, service_item_id,
                        default_tax_code=exempt_tax_code
                    )

                    # In preview mode, collect item for preview
                    if self.preview_mode:
                        warnings: list[str] = []
                        if not tenant.quickbooks_customer_id:
                            warnings.append("Tenant not synced to QuickBooks")

                        self._add_preview_item(
                            entity_type="invoice",
                            entity_id=str(invoice.id),
                            entity_name=f"Invoice for {tenant.first_name} {tenant.last_name}" if tenant else f"Invoice {invoice.id}",
                            action=SyncAction.CREATE,
                            details={
                                "amount": float(invoice.amount) if invoice.amount else 0,
                                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                                "tenant": f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown",
                                "destination": "QuickBooks"
                            },
                            warnings=warnings
                        )
                        pushed_count += 1
                    else:
                        # Create invoice in QuickBooks with retry
                        async def create_operation():
                            return await self.client.create_invoice(invoice_data)

                        response = await self._retry_operation(
                            create_operation,
                            f"create_invoice_{invoice.id}",
                            max_retries=2
                        )

                        if response and "Invoice" in response:
                            qb_invoice = response["Invoice"]
                            qb_invoice_id = qb_invoice.get("Id")

                            if qb_invoice_id:
                                invoice.quickbooks_id = qb_invoice_id
                                invoice.last_synced_at = datetime.now(UTC)
                                self.session.add(invoice)
                                pushed_count += 1
                                api_call_count += 1
                                logger.info(f"Successfully pushed invoice {invoice.id} to QuickBooks with ID {qb_invoice_id}")
                                
                                # Throttle API calls to respect rate limits
                                await self._throttle_api_call(api_call_count)
                            else:
                                errors.append(f"Invoice {invoice.id}: QuickBooks response missing ID")
                        else:
                            errors.append(f"Invoice {invoice.id}: Invalid QuickBooks response")

                    # Batch commit every COMMIT_BATCH_SIZE items
                    if (idx + 1) % COMMIT_BATCH_SIZE == 0 and pushed_count > 0 and self._should_execute_action():
                        await self.session.commit()
                        logger.info(f"Committed batch progress: {pushed_count} invoices synced so far")

                except Exception as e:
                    error_msg = f"Error pushing invoice {invoice.id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

            # Final commit for remaining items (only in non-preview mode)
            if pushed_count > 0 and self._should_execute_action():
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error pushing invoices to QuickBooks: {e}", exc_info=True)
            errors.append(f"Push invoices failed: {str(e)}")

        return {"pushed_count": pushed_count, "errors": errors}

    async def _update_invoices_in_quickbooks(self) -> Dict[str, Any]:
        """Update modified Brikli invoices in QuickBooks."""
        updated_count = 0
        errors = []

        try:
            # Get user's properties (uses base class method)
            property_ids = await self._get_user_property_ids()

            if not property_ids:
                return {"updated_count": 0, "errors": []}

            # Find invoices that have been synced but modified locally
            # SECURITY: Join through Tenant and verify landlord_id
            # Use coalesce to handle NULL last_synced_at values (epoch fallback)
            modified_invoices = await self.session.scalars(
                select(Invoice)
                .join(Tenant, col(Invoice.tenant_id) == col(Tenant.id))
                .where(
                    col(Invoice.property_id).in_(property_ids),
                    col(Tenant.landlord_id) == self.user.id,  # SECURITY: Verify ownership
                    col(Invoice.quickbooks_id).is_not(None),  # Must be already synced
                    col(Invoice.updated_at) > func.coalesce(col(Invoice.last_synced_at), datetime(1970, 1, 1, tzinfo=UTC)),
                    col(Tenant.quickbooks_customer_id).is_not(None)
                ).limit(25)  # Lower limit for updates to avoid timeouts
            )
            modified_invoices_list = list(modified_invoices)

            if not modified_invoices_list:
                return {"updated_count": 0, "errors": []}

            # Prefetch all tenants with ownership verification (uses base class method)
            tenant_ids = [invoice.tenant_id for invoice in modified_invoices_list]
            tenants_by_id = await self._prefetch_tenants_by_ids(tenant_ids)

            # Cache service item to avoid multiple API calls
            service_item_id = await self._get_or_cache_service_item()

            # Get exempt tax code for residential rent (required for Canadian QB)
            exempt_tax_code = await self._get_or_cache_exempt_tax_code()

            for invoice in modified_invoices_list:
                try:
                    # Get tenant from prefetched data
                    tenant = tenants_by_id.get(invoice.tenant_id)
                    if not tenant or not tenant.quickbooks_customer_id:
                        errors.append(f"Invoice {invoice.id}: Tenant not synced to QuickBooks")
                        continue

                    if not invoice.quickbooks_id:
                        continue  # Skip if no QB ID (shouldn't happen due to query filter)

                    # Fetch current invoice from QB to get the SyncToken
                    qb_invoice_response = await self.client.get_invoice(invoice.quickbooks_id)
                    if not qb_invoice_response or "Invoice" not in qb_invoice_response:
                        errors.append(f"Invoice {invoice.id}: Could not fetch QuickBooks invoice")
                        continue

                    qb_invoice = qb_invoice_response["Invoice"]
                    sync_token = qb_invoice.get("SyncToken")
                    if not sync_token:
                        errors.append(f"Invoice {invoice.id}: QuickBooks invoice missing SyncToken")
                        continue

                    # In preview mode, collect item for preview
                    if self.preview_mode:
                        warnings: list[str] = []

                        self._add_preview_item(
                            entity_type="invoice",
                            entity_id=str(invoice.id),
                            entity_name=f"Invoice for {tenant.first_name} {tenant.last_name}" if tenant else f"Invoice {invoice.id}",
                            action=SyncAction.UPDATE,
                            details={
                                "amount": float(invoice.amount) if invoice.amount else 0,
                                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                                "tenant": f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown",
                                "destination": "QuickBooks",
                                "quickbooks_id": invoice.quickbooks_id
                            },
                            warnings=warnings
                        )
                        updated_count += 1
                    else:
                        # Build update data with SyncToken and exempt tax code
                        update_data = InvoiceSchema.to_quickbooks_update(
                            invoice, tenant, invoice.quickbooks_id, sync_token, service_item_id,
                            default_tax_code=exempt_tax_code
                        )

                        # Update invoice in QuickBooks with retry
                        async def update_operation():
                            return await self.client.update_invoice(update_data)

                        response = await self._retry_operation(
                            update_operation,
                            f"update_invoice_{invoice.id}",
                            max_retries=2
                        )

                        if response and "Invoice" in response:
                            invoice.last_synced_at = datetime.now(UTC)
                            self.session.add(invoice)
                            updated_count += 1
                            logger.info(f"Successfully updated invoice {invoice.id} in QuickBooks")
                        else:
                            errors.append(f"Invoice {invoice.id}: Invalid QuickBooks update response")

                except Exception as e:
                    error_msg = f"Error updating invoice {invoice.id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

            # Commit all successful updates (only in non-preview mode)
            if updated_count > 0 and self._should_execute_action():
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error updating invoices in QuickBooks: {e}", exc_info=True)
            errors.append(f"Update invoices failed: {str(e)}")

        return {"updated_count": updated_count, "errors": errors}

    # NOTE: _prefetch_tenants_and_leases() and _resolve_from_cache() are inherited from TenantLeaseService

    async def _get_or_cache_service_item(self) -> str:
        """Get or cache service item ID to avoid multiple API calls."""
        async def fetch_service_item():
            return await self._get_or_create_default_service_item()

        return await self._get_or_cache_quickbooks_data("default_service_item_id", fetch_service_item)

    async def _get_or_create_default_service_item(self) -> str:
        """Get or create a default service item for invoices."""
        # Check integration metadata for cached service item
        cached_item_id = await self._get_cached_metadata("default_service_item_id")
        if cached_item_id:
            return cached_item_id

        try:
            # Search for existing service items
            items_response = await self.client.query_items(
                where_clause="Active=true AND Type='Service'",
                max_results=50
            )

            if items_response and "QueryResponse" in items_response:
                items = items_response["QueryResponse"].get("Item", [])

                # Look for a service item suitable for rent/property management
                for item in items:
                    item_name = item.get("Name", "").lower()
                    if any(keyword in item_name for keyword in ["rent", "service", "property", "income"]):
                        item_id = item.get("Id")
                        if item_id:
                            await self._cache_metadata("default_service_item_id", item_id)
                            return item_id

                # Use the first service item if no specific one found
                if items and items[0].get("Id"):
                    item_id = items[0]["Id"]
                    await self._cache_metadata("default_service_item_id", item_id)
                    return item_id

            # Create a new service item if none found
            service_item_data = {
                "Item": {
                    "Name": "Property Management Service",
                    "Type": "Service",
                    "IncomeAccountRef": {
                        "value": await self._get_default_income_account_id()
                    },
                    "Active": True,
                    "Description": "Property management and rental services"
                }
            }

            create_response = await self.client.create_item(service_item_data)

            if create_response and "Item" in create_response:
                new_item_id = create_response["Item"].get("Id")
                if new_item_id:
                    await self._cache_metadata("default_service_item_id", new_item_id)
                    logger.info(f"Created new service item {new_item_id} for user {self.user.id}")
                    return new_item_id

            # Fallback: return "1" (common default in sandbox)
            logger.warning(f"Unable to find or create service item for user {self.user.id}, using fallback ID '1'")
            return "1"

        except Exception as e:
            logger.error(f"Error getting/creating service item: {e}", exc_info=True)
            return "1"

    async def _get_default_income_account_id(self) -> str:
        """Get a default income account ID for the service item."""
        try:
            accounts_response = await self.client.query_accounts(
                where_clause="Active=true AND Classification='Revenue'",
                max_results=20
            )

            if accounts_response and "QueryResponse" in accounts_response:
                accounts = accounts_response["QueryResponse"].get("Account", [])

                for account in accounts:
                    account_type = account.get("AccountType", "").upper()
                    if account_type in ["INCOME", "OTHER_INCOME"]:
                        account_id = account.get("Id")
                        if account_id:
                            return account_id

                # Use first account if no specific income account found
                if accounts and accounts[0].get("Id"):
                    return accounts[0]["Id"]
        except Exception as e:
            logger.error(f"Error finding income account: {e}")

        # Fallback to commonly used income account ID in QuickBooks
        return "1"

    async def _get_or_cache_exempt_tax_code(self) -> Optional[str]:
        """
        Get or cache the exempt/no-tax code ID.

        Canadian QuickBooks accounts with GST/HST enabled require a TaxCodeRef
        on every invoice line item. Residential rent is typically exempt from
        GST/HST, so we need to use the "NON" or exempt tax code.

        Returns:
            The tax code ID for exempt items, or None if not found
        """
        async def fetch_exempt_tax_code() -> Optional[str]:
            try:
                # Query for tax codes - look for exempt/NON codes
                response = await self.client.query(
                    "SELECT * FROM TaxCode WHERE Active = true MAXRESULTS 100"
                )

                if response and "QueryResponse" in response:
                    tax_codes = response["QueryResponse"].get("TaxCode", [])

                    # Priority order for exempt codes
                    exempt_patterns = ["NON", "EXEMPT", "OUT", "E", "Z"]

                    for pattern in exempt_patterns:
                        for tax_code in tax_codes:
                            code_name = tax_code.get("Name", "").upper()
                            if code_name == pattern or code_name.startswith(pattern):
                                code_id = tax_code.get("Id")
                                if code_id:
                                    logger.info(f"Found exempt tax code: {code_name} (ID: {code_id})")
                                    return code_id

                    # If no exempt code found, log available codes for debugging
                    available_codes = [f"{tc.get('Name')} (ID: {tc.get('Id')})" for tc in tax_codes[:10]]
                    logger.warning(f"No exempt tax code found. Available: {available_codes}")

            except Exception as e:
                logger.error(f"Error fetching exempt tax code: {e}")

            return None

        return await self._get_or_cache_quickbooks_data("exempt_tax_code_id", fetch_exempt_tax_code)