import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, UTC
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select, col, desc

from ....models.user import User
from ....models.tenant import Tenant
from ....models.property import Property
from ....models.lease import Lease, LeaseStatus
from ....models.accounting.payment import Payment, PaymentStatus
from ....models.accounting.invoice import Invoice
from ....models.accounting.payment_allocation import PaymentAllocation
from ....models.accounting.common import PaymentStatus as CommonPaymentStatus
from ..schemas.payment import PaymentSchema
from .base_service import TenantLeaseService, SyncAction, SyncPreview

logger = logging.getLogger(__name__)


class PaymentService(TenantLeaseService):
    """Service for QuickBooks Payment operations."""

    async def sync_payments(self) -> Dict[str, Any]:
        """Perform bidirectional payment synchronization."""
        return await self.sync_payments_internal()

    async def sync_single_payment_from_quickbooks(self, qb_payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sync a single payment from QuickBooks webhook event.

        This is more efficient than a full sync when processing webhooks,
        as it only processes the specific entity that changed.

        Args:
            qb_payment_data: The Payment object from QuickBooks API

        Returns:
            Dict with sync result (synced_count, errors)
        """
        await self.initialize()

        qb_payment_id = qb_payment_data.get("Id")
        if not qb_payment_id:
            return {"synced_count": 0, "errors": ["Payment data missing ID"]}

        try:
            # Check if payment already exists in our system (with ownership check)
            existing_payment = await self.session.scalar(
                select(Payment)
                .join(Lease, col(Payment.lease_id) == col(Lease.id))
                .join(Tenant, col(Lease.tenant_id) == col(Tenant.id))
                .where(
                    col(Payment.quickbooks_id) == qb_payment_id,
                    col(Tenant.landlord_id) == self.user.id  # SECURITY: Verify ownership
                )
            )

            if existing_payment:
                # Update existing payment
                return await self._update_single_payment(existing_payment, qb_payment_data)
            else:
                # Create new payment
                return await self._create_single_payment(qb_payment_data)

        except Exception as e:
            error_msg = f"Error syncing single payment {qb_payment_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"synced_count": 0, "errors": [error_msg]}

    async def _update_single_payment(self, payment: Payment, qb_payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing payment with QuickBooks data."""
        try:
            # Update fields from QB data
            payment.amount = PaymentSchema.parse_amount(qb_payment_data.get("TotalAmt"))
            payment.payment_date = PaymentSchema.parse_date(qb_payment_data.get("TxnDate"))
            payment.last_synced_at = datetime.now(UTC)

            self.session.add(payment)
            await self.session.commit()

            logger.info(f"Updated payment {payment.id} from QB payment {qb_payment_data.get('Id')}")
            return {"synced_count": 1, "errors": []}

        except Exception as e:
            error_msg = f"Error updating payment: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"synced_count": 0, "errors": [error_msg]}

    async def _create_single_payment(self, qb_payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new payment from QuickBooks data."""
        qb_payment_id = qb_payment_data.get("Id")

        try:
            # Prefetch tenants and leases
            tenants_with_leases = await self._prefetch_tenants_and_leases()

            # Resolve tenant and lease
            tenant, lease = self._resolve_from_cache(
                qb_payment_data, tenants_with_leases, PaymentSchema.get_customer_id
            )

            if not tenant or not lease:
                logger.warning(f"Skipping payment {qb_payment_id} - could not resolve tenant/lease")
                return {"synced_count": 0, "errors": [f"Could not resolve tenant/lease for payment {qb_payment_id}"]}

            # Prefetch linked invoices with their amounts
            linked_invoices_with_amounts = PaymentSchema.get_linked_invoices_with_amounts(qb_payment_data)
            invoices_by_qb_id: Dict[str, Invoice] = {}
            if linked_invoices_with_amounts:
                # SECURITY: Only fetch invoices belonging to this tenant to prevent cross-tenant linking
                invoices = await self.session.scalars(
                    select(Invoice).where(
                        col(Invoice.quickbooks_id).in_(list(linked_invoices_with_amounts.keys())),
                        col(Invoice.tenant_id) == tenant.id  # SECURITY: Verify tenant ownership
                    )
                )
                for invoice in invoices:
                    if invoice.quickbooks_id:
                        invoices_by_qb_id[invoice.quickbooks_id] = invoice

            # Create the payment
            new_payment = PaymentSchema.from_quickbooks(qb_payment_data, lease, tenant)
            self.session.add(new_payment)
            await self.session.flush()

            # Create payment allocations with validation
            if new_payment.id and linked_invoices_with_amounts:
                # Validate allocation totals before creating
                total_applied = sum(linked_invoices_with_amounts.values())
                if total_applied <= Decimal("0"):
                    logger.warning(f"Skipping allocations for QB payment {qb_payment_id}: total_applied={total_applied} is invalid")
                elif new_payment.amount and total_applied > new_payment.amount:
                    logger.warning(f"Skipping allocations for QB payment {qb_payment_id}: total_applied={total_applied} exceeds payment_amount={new_payment.amount}")
                else:
                    await self._create_allocations_for_linked_invoices(
                        new_payment, linked_invoices_with_amounts, invoices_by_qb_id
                    )

            await self.session.commit()

            logger.info(f"Created payment from QB payment {qb_payment_id}")
            return {"synced_count": 1, "errors": []}

        except Exception as e:
            error_msg = f"Error creating payment from QB {qb_payment_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"synced_count": 0, "errors": [error_msg]}

    async def preview_payments(self) -> SyncPreview:
        """Preview what would happen during payment synchronization."""
        # Create a preview-mode service
        preview_service = PaymentService(self.user, self.session, preview_mode=True)
        await preview_service.initialize()
        await preview_service.sync_payments_internal()
        return preview_service._generate_preview()

    async def sync_payments_internal(self) -> Dict[str, Any]:
        """Perform bidirectional payment synchronization."""
        await self.initialize()

        all_errors = []
        pulled_count = 0
        pushed_count = 0
        updated_count = 0

        try:
            # Pull payments from QuickBooks
            pull_result = await self._pull_payments_from_quickbooks()
            pulled_count = pull_result.get("synced_count", 0)
            all_errors.extend(pull_result.get("errors", []))

            # Push NEW payments to QuickBooks
            push_result = await self._push_payments_to_quickbooks()
            pushed_count = push_result.get("pushed_count", 0)
            all_errors.extend(push_result.get("errors", []))

            # Update MODIFIED payments in QuickBooks
            update_result = await self._update_payments_in_quickbooks()
            updated_count = update_result.get("updated_count", 0)
            all_errors.extend(update_result.get("errors", []))

            total_synced = pulled_count + pushed_count + updated_count

            # Update integration sync time on success
            if total_synced > 0 and len(all_errors) == 0:
                await self._update_integration_sync_time()

            self._log_operation(
                operation="sync_payments",
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
            logger.error(f"Error in payment sync for user {self.user.id}: {e}", exc_info=True)
            return self._create_sync_result(errors=[f"Payment sync failed: {str(e)}"])

    async def _pull_payments_from_quickbooks(self) -> Dict[str, Any]:
        """Pull payments from QuickBooks and sync to local database with invoice linking."""
        new_payments_count = 0
        allocations_count = 0
        errors = []

        try:
            # Get payments from QuickBooks
            payments_response = await self.client.list_payments(max_results=100)

            if not payments_response or "QueryResponse" not in payments_response:
                return {"synced_count": 0, "errors": ["No payments found in QuickBooks"]}

            qb_payments = payments_response["QueryResponse"].get("Payment", [])
            if not qb_payments:
                return {"synced_count": 0, "errors": []}

            # Get existing payment IDs to avoid duplicates
            qb_payment_ids = [payment.get("Id") for payment in qb_payments if payment.get("Id")]
            existing_ids_result = await self.session.execute(
                select(Payment.quickbooks_id).where(col(Payment.quickbooks_id).in_(qb_payment_ids))
            )
            existing_ids = {row[0] for row in existing_ids_result}

            # Prefetch all tenants and their active leases for this user to avoid N+1 queries
            tenants_with_leases = await self._prefetch_tenants_and_leases()

            # Collect all QB invoice IDs from payments to prefetch
            all_linked_qb_invoice_ids: List[str] = []
            for qb_payment in qb_payments:
                linked_ids = PaymentSchema.get_linked_invoice_ids(qb_payment)
                all_linked_qb_invoice_ids.extend(linked_ids)

            # Prefetch invoices by QuickBooks ID for efficient linking
            invoices_by_qb_id: Dict[str, Invoice] = {}
            if all_linked_qb_invoice_ids:
                invoices = await self.session.scalars(
                    select(Invoice).where(
                        col(Invoice.quickbooks_id).in_(all_linked_qb_invoice_ids)
                    )
                )
                for invoice in invoices:
                    if invoice.quickbooks_id:
                        invoices_by_qb_id[invoice.quickbooks_id] = invoice

            for qb_payment in qb_payments:
                qb_payment_id = qb_payment.get("Id")
                if not qb_payment_id or qb_payment_id in existing_ids:
                    continue

                try:
                    # Resolve tenant and lease using prefetched data (uses base class method)
                    tenant, lease = self._resolve_from_cache(
                        qb_payment, tenants_with_leases, PaymentSchema.get_customer_id
                    )

                    if not tenant or not lease:
                        logger.warning(f"Skipping payment {qb_payment_id} - could not resolve tenant/lease")
                        continue

                    # Create Brikli payment from QuickBooks data with linked invoice IDs
                    new_payment, linked_qb_invoice_ids = PaymentSchema.from_quickbooks_with_links(
                        qb_payment, lease, tenant
                    )

                    # Get precise amounts for each linked invoice
                    linked_invoices_with_amounts = PaymentSchema.get_linked_invoices_with_amounts(qb_payment)

                    # In preview mode, collect item for preview
                    if self.preview_mode:
                        warnings: list[str] = []
                        linked_invoices_info: List[str] = []

                        # Check which linked invoices exist in our system
                        for qb_inv_id, amount in linked_invoices_with_amounts.items():
                            if qb_inv_id in invoices_by_qb_id:
                                inv = invoices_by_qb_id[qb_inv_id]
                                linked_invoices_info.append(f"#{inv.invoice_number} (${amount})")
                            else:
                                warnings.append(f"Linked invoice QB-{qb_inv_id} not found in Brikli")

                        self._add_preview_item(
                            entity_type="payment",
                            entity_id=qb_payment_id,
                            entity_name=f"Payment from {tenant.first_name} {tenant.last_name}" if tenant else f"QB Payment {qb_payment_id}",
                            action=SyncAction.CREATE,
                            details={
                                "amount": float(new_payment.amount) if new_payment.amount else 0,
                                "payment_date": new_payment.payment_date.isoformat() if new_payment.payment_date else None,
                                "tenant": f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown",
                                "payment_method": new_payment.payment_method.value if new_payment.payment_method else None,
                                "linked_invoices": ", ".join(linked_invoices_info) if linked_invoices_info else None
                            },
                            warnings=warnings
                        )
                    else:
                        # Execute the actual creation
                        self.session.add(new_payment)

                        # Flush to get the payment ID
                        await self.session.flush()

                        # Create allocations for linked invoices with precise amounts
                        if new_payment.id and linked_invoices_with_amounts:
                            allocations = await self._create_allocations_for_linked_invoices(
                                new_payment, linked_invoices_with_amounts, invoices_by_qb_id
                            )
                            allocations_count += len(allocations)

                        logger.info(f"Synced payment {qb_payment_id} from QuickBooks with {len(linked_invoices_with_amounts)} linked invoices")

                    new_payments_count += 1

                except Exception as e:
                    error_msg = f"Error processing payment {qb_payment_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

            if new_payments_count > 0 and self._should_execute_action():
                await self.session.commit()

            if allocations_count > 0:
                logger.info(f"Created {allocations_count} payment allocations during sync")

        except Exception as e:
            logger.error(f"Error pulling payments from QuickBooks: {e}", exc_info=True)
            errors.append(f"Pull payments failed: {str(e)}")

        return {"synced_count": new_payments_count, "allocations_count": allocations_count, "errors": errors}

    async def _create_allocations_for_linked_invoices(
        self,
        payment: Payment,
        linked_invoices_with_amounts: Dict[str, Decimal],
        invoices_by_qb_id: Dict[str, Invoice]
    ) -> List[PaymentAllocation]:
        """
        Create PaymentAllocation records for invoices linked to this payment.

        Uses the precise amounts from QuickBooks payment data rather than
        distributing the total payment equally.

        Args:
            payment: The Brikli Payment object (must have id set)
            linked_invoices_with_amounts: Dict mapping QB invoice ID -> amount applied
            invoices_by_qb_id: Prefetched map of QB invoice ID -> Invoice

        Returns:
            List of created PaymentAllocation objects
        """
        allocations: List[PaymentAllocation] = []

        if not payment.id:
            logger.warning("Cannot create allocations - payment has no ID")
            return allocations

        if not linked_invoices_with_amounts:
            return allocations

        for qb_invoice_id, amount_applied in linked_invoices_with_amounts.items():
            invoice = invoices_by_qb_id.get(qb_invoice_id)
            if not invoice or not invoice.id:
                logger.warning(f"Skipping allocation - invoice QB-{qb_invoice_id} not found in Brikli")
                continue

            allocation = PaymentAllocation(
                payment_id=payment.id,
                invoice_id=invoice.id,
                amount_applied=amount_applied
            )
            self.session.add(allocation)
            allocations.append(allocation)

            logger.info(f"Created allocation: Payment {payment.id} -> Invoice {invoice.id} for ${amount_applied}")

        return allocations

    async def _push_payments_to_quickbooks(self) -> Dict[str, Any]:
        """Push unsynced Brikli payments to QuickBooks."""
        pushed_count = 0
        errors = []

        try:
            # Get user's properties (uses base class method)
            property_ids = await self._get_user_property_ids()

            if not property_ids:
                return {"pushed_count": 0, "errors": ["No properties found for user"]}

            # Find payments that haven't been synced to QuickBooks
            # SECURITY: Join through Tenant and verify landlord_id
            unsynced_payments = await self.session.scalars(
                select(Payment).join(Lease).join(Tenant).where(
                    col(Tenant.landlord_id) == self.user.id,  # SECURITY: Verify ownership
                    col(Tenant.current_property_id).in_(property_ids),
                    col(Payment.quickbooks_id).is_(None),
                    col(Tenant.quickbooks_customer_id).is_not(None),  # Tenant must be synced first
                    col(Payment.status) == PaymentStatus.PAID  # Only push confirmed payments
                ).limit(50)  # Limit to avoid timeout
            )
            unsynced_payments_list = list(unsynced_payments)

            if not unsynced_payments_list:
                return {"pushed_count": 0, "errors": []}

            # Prefetch all tenants with ownership verification (uses base class method)
            tenant_ids = [payment.tenant_id for payment in unsynced_payments_list]
            tenants_by_id = await self._prefetch_tenants_by_ids(tenant_ids)

            # Prefetch latest unpaid invoice per tenant using DISTINCT ON for Postgres
            # Ensures we always link to the most recent unpaid invoice if any
            unpaid_invoices = await self.session.scalars(
                select(Invoice)
                .where(
                    col(Invoice.tenant_id).in_(tenant_ids),
                    col(Invoice.quickbooks_id).is_not(None),
                    col(Invoice.status).in_([CommonPaymentStatus.PENDING, CommonPaymentStatus.DRAFT])
                )
                .distinct(col(Invoice.tenant_id))
                .order_by(col(Invoice.tenant_id), desc(col(Invoice.issue_date)))
            )
            unpaid_invoices_by_tenant = {}
            for invoice in unpaid_invoices:
                unpaid_invoices_by_tenant[invoice.tenant_id] = invoice

            api_call_count = 0  # Track API calls for throttling
            COMMIT_BATCH_SIZE = 10  # Commit every N items

            for idx, payment in enumerate(unsynced_payments_list):
                try:
                    # Get tenant from prefetched data
                    tenant = tenants_by_id.get(payment.tenant_id)
                    if not tenant or not tenant.quickbooks_customer_id:
                        errors.append(f"Payment {payment.id}: Tenant not synced to QuickBooks")
                        continue

                    # Build QuickBooks payment data
                    payment_data = PaymentSchema.to_quickbooks(payment, tenant)

                    # Try to link to unpaid invoice if available
                    unpaid_invoice = unpaid_invoices_by_tenant.get(tenant.id)
                    if unpaid_invoice and unpaid_invoice.quickbooks_id:
                        payment_data = PaymentSchema.add_invoice_link(payment_data, unpaid_invoice.quickbooks_id)

                    # In preview mode, collect item for preview
                    if self.preview_mode:
                        warnings = []
                        if not tenant.quickbooks_customer_id:
                            warnings.append("Tenant not synced to QuickBooks")

                        self._add_preview_item(
                            entity_type="payment",
                            entity_id=str(payment.id),
                            entity_name=f"Payment from {tenant.first_name} {tenant.last_name}" if tenant else f"Payment {payment.id}",
                            action=SyncAction.CREATE,
                            details={
                                "amount": float(payment.amount) if payment.amount else 0,
                                "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
                                "tenant": f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown",
                                "payment_method": payment.payment_method.value if payment.payment_method else None,
                                "linked_invoice": f"Invoice {unpaid_invoice.id}" if unpaid_invoice else None,
                                "destination": "QuickBooks"
                            },
                            warnings=warnings
                        )
                        pushed_count += 1
                    else:
                        # Create payment in QuickBooks with retry
                        async def create_operation():
                            return await self.client.create_payment(payment_data)

                        response = await self._retry_operation(
                            create_operation,
                            f"create_payment_{payment.id}",
                            max_retries=2
                        )

                        if response and "Payment" in response:
                            qb_payment = response["Payment"]
                            qb_payment_id = qb_payment.get("Id")

                            if qb_payment_id:
                                payment.quickbooks_id = qb_payment_id
                                payment.last_synced_at = datetime.now(UTC)
                                self.session.add(payment)
                                pushed_count += 1
                                api_call_count += 1
                                logger.info(f"Successfully pushed payment {payment.id} to QuickBooks with ID {qb_payment_id}")
                                
                                # Throttle API calls to respect rate limits
                                await self._throttle_api_call(api_call_count)
                            else:
                                errors.append(f"Payment {payment.id}: QuickBooks response missing ID")
                        else:
                            errors.append(f"Payment {payment.id}: Invalid QuickBooks response")

                    # Batch commit every COMMIT_BATCH_SIZE items
                    if (idx + 1) % COMMIT_BATCH_SIZE == 0 and pushed_count > 0 and self._should_execute_action():
                        await self.session.commit()
                        logger.info(f"Committed batch progress: {pushed_count} payments synced so far")

                except Exception as e:
                    error_msg = f"Error pushing payment {payment.id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

            # Final commit for remaining items (only in non-preview mode)
            if pushed_count > 0 and self._should_execute_action():
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error pushing payments to QuickBooks: {e}", exc_info=True)
            errors.append(f"Push payments failed: {str(e)}")

        return {"pushed_count": pushed_count, "errors": errors}

    async def _update_payments_in_quickbooks(self) -> Dict[str, Any]:
        """Update modified Brikli payments in QuickBooks."""
        updated_count = 0
        errors = []

        try:
            # Get user's properties (uses base class method)
            property_ids = await self._get_user_property_ids()

            if not property_ids:
                return {"updated_count": 0, "errors": []}

            # Find payments that have been synced but modified locally
            # SECURITY: Join through Tenant and verify landlord_id
            # NOTE: Use coalesce to handle NULL last_synced_at (newly synced records not yet updated)
            epoch = datetime(1970, 1, 1, tzinfo=UTC)
            modified_payments = await self.session.scalars(
                select(Payment).join(Lease).join(Tenant).where(
                    col(Tenant.landlord_id) == self.user.id,  # SECURITY: Verify ownership
                    col(Tenant.current_property_id).in_(property_ids),
                    col(Payment.quickbooks_id).is_not(None),  # Must be already synced
                    col(Payment.updated_at) > func.coalesce(col(Payment.last_synced_at), epoch),  # Modified since last sync
                    col(Tenant.quickbooks_customer_id).is_not(None)
                ).limit(25)  # Lower limit for updates to avoid timeouts
            )
            modified_payments_list = list(modified_payments)

            if not modified_payments_list:
                return {"updated_count": 0, "errors": []}

            # Prefetch all tenants with ownership verification (uses base class method)
            tenant_ids = [payment.tenant_id for payment in modified_payments_list]
            tenants_by_id = await self._prefetch_tenants_by_ids(tenant_ids)

            for payment in modified_payments_list:
                try:
                    # Get tenant from prefetched data
                    tenant = tenants_by_id.get(payment.tenant_id)
                    if not tenant or not tenant.quickbooks_customer_id:
                        errors.append(f"Payment {payment.id}: Tenant not synced to QuickBooks")
                        continue

                    if not payment.quickbooks_id:
                        continue  # Skip if no QB ID (shouldn't happen due to query filter)

                    # Fetch current payment from QB to get the SyncToken
                    qb_payment_response = await self.client.get_payment(payment.quickbooks_id)
                    if not qb_payment_response or "Payment" not in qb_payment_response:
                        errors.append(f"Payment {payment.id}: Could not fetch QuickBooks payment")
                        continue

                    qb_payment = qb_payment_response["Payment"]
                    sync_token = qb_payment.get("SyncToken")
                    if not sync_token:
                        errors.append(f"Payment {payment.id}: QuickBooks payment missing SyncToken")
                        continue

                    # In preview mode, collect item for preview
                    if self.preview_mode:
                        warnings: list[str] = []

                        self._add_preview_item(
                            entity_type="payment",
                            entity_id=str(payment.id),
                            entity_name=f"Payment from {tenant.first_name} {tenant.last_name}" if tenant else f"Payment {payment.id}",
                            action=SyncAction.UPDATE,
                            details={
                                "amount": float(payment.amount) if payment.amount else 0,
                                "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
                                "tenant": f"{tenant.first_name} {tenant.last_name}" if tenant else "Unknown",
                                "destination": "QuickBooks",
                                "quickbooks_id": payment.quickbooks_id
                            },
                            warnings=warnings
                        )
                        updated_count += 1
                    else:
                        # Build update data with SyncToken
                        update_data = PaymentSchema.to_quickbooks_update(
                            payment, tenant, payment.quickbooks_id, sync_token
                        )

                        # Update payment in QuickBooks with retry
                        async def update_operation():
                            return await self.client.update_payment(update_data)

                        response = await self._retry_operation(
                            update_operation,
                            f"update_payment_{payment.id}",
                            max_retries=2
                        )

                        if response and "Payment" in response:
                            payment.last_synced_at = datetime.now(UTC)
                            self.session.add(payment)
                            updated_count += 1
                            logger.info(f"Successfully updated payment {payment.id} in QuickBooks")
                        else:
                            errors.append(f"Payment {payment.id}: Invalid QuickBooks update response")

                except Exception as e:
                    error_msg = f"Error updating payment {payment.id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)

            # Commit all successful updates (only in non-preview mode)
            if updated_count > 0 and self._should_execute_action():
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error updating payments in QuickBooks: {e}", exc_info=True)
            errors.append(f"Update payments failed: {str(e)}")

        return {"updated_count": updated_count, "errors": errors}

    # NOTE: _prefetch_tenants_and_leases() and _resolve_from_cache() are inherited from TenantLeaseService

    async def _find_unpaid_invoice_for_tenant(self, tenant_id: int | None) -> Optional[Invoice]:
        """Find an unpaid invoice for this tenant to apply the payment to."""
        return await self.session.scalar(
            select(Invoice).where(
                col(Invoice.tenant_id) == tenant_id,
                col(Invoice.quickbooks_id).is_not(None),
                col(Invoice.status).in_([CommonPaymentStatus.PENDING, CommonPaymentStatus.DRAFT])
            ).order_by(desc(col(Invoice.issue_date))).limit(1)
        )