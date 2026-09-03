"""
QuickBooks Webhook Service

Handles incoming webhook notifications from QuickBooks Online.
Webhooks provide real-time notifications when data changes in QuickBooks,
enabling automatic synchronization without polling.

Webhook Flow:
1. QuickBooks sends a POST request with event notifications
2. We verify the signature using HMAC-SHA256 with the verifier token
3. We process each event by fetching the full entity from QuickBooks API
4. We sync the entity to Brikli's database

Supported Entities:
- Customer: Syncs to Tenant
- Invoice: Syncs to Invoice
- Payment: Syncs to Payment
- Purchase: Syncs to Expense

Reference: https://developer.intuit.com/app/developer/qbo/docs/develop/webhooks
"""

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

import sentry_sdk
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col

from Backend.config import settings
from Backend.models.accounting.integration import Integration
from Backend.models.accounting.common import IntegrationType, IntegrationStatus
from Backend.models.accounting.quickbooks_integration import QuickBooksIntegration
from Backend.models.user import User
from Backend.api.notifications.service import NotificationService

logger = logging.getLogger(__name__)


class WebhookEvent:
    """Represents a single QuickBooks webhook event."""

    def __init__(self, data: Dict[str, Any]):
        self.realm_id: str = data.get("realmId", "")
        self.name: str = data.get("name", "")  # Entity type (e.g., "Customer", "Invoice")
        self.id: str = data.get("id", "")  # Entity ID in QuickBooks
        self.operation: str = data.get("operation", "")  # "Create", "Update", "Delete", "Merge", "Void"
        self.last_updated: str = data.get("lastUpdated", "")

    def __repr__(self) -> str:
        return f"WebhookEvent({self.name}:{self.id} - {self.operation})"


class WebhookPayload:
    """Represents a QuickBooks webhook payload containing multiple events."""

    def __init__(self, data: Dict[str, Any]):
        self.event_notifications: List[Dict[str, Any]] = data.get("eventNotifications", [])

    def get_events(self) -> List[WebhookEvent]:
        """Extract all events from the payload."""
        events = []
        for notification in self.event_notifications:
            realm_id = notification.get("realmId", "")
            data_change_event = notification.get("dataChangeEvent", {})
            entities = data_change_event.get("entities", [])

            for entity in entities:
                entity["realmId"] = realm_id
                events.append(WebhookEvent(entity))

        return events


class QuickBooksWebhookService:
    """
    Service for handling QuickBooks webhook notifications.

    Responsibilities:
    - Verify webhook signature for security
    - Parse webhook payloads
    - Route events to appropriate sync handlers
    - Handle errors gracefully with retry logic
    """

    # Entity types we handle
    SUPPORTED_ENTITIES = {"Customer", "Invoice", "Payment", "Purchase"}

    # Operations we process
    SUPPORTED_OPERATIONS = {"Create", "Update", "Delete", "Void", "Merge"}

    def __init__(self, session: AsyncSession):
        self.session = session
        self._verifier_token = settings.INTUIT_WEBHOOK_VERIFIER_TOKEN

    @staticmethod
    def verify_signature(payload_body: bytes, signature_header: str) -> bool:
        """
        Verify the webhook signature using HMAC-SHA256.

        QuickBooks signs each webhook payload with the verifier token.
        We must verify this signature to ensure the webhook is authentic.

        Args:
            payload_body: Raw request body bytes
            signature_header: Value of the 'intuit-signature' header

        Returns:
            True if signature is valid, False otherwise
        """
        if not settings.INTUIT_WEBHOOK_VERIFIER_TOKEN:
            logger.warning("INTUIT_WEBHOOK_VERIFIER_TOKEN not configured, skipping verification")
            return False

        try:
            # Create HMAC-SHA256 hash of the payload using verifier token
            expected_signature = hmac.new(
                key=settings.INTUIT_WEBHOOK_VERIFIER_TOKEN.encode("utf-8"),
                msg=payload_body,
                digestmod=hashlib.sha256
            ).digest()

            # Base64 encode the hash
            expected_signature_b64 = base64.b64encode(expected_signature).decode("utf-8")

            # Compare with provided signature (constant-time comparison)
            return hmac.compare_digest(expected_signature_b64, signature_header)

        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False

    async def process_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a webhook payload and sync affected entities.

        Args:
            payload: The parsed JSON webhook payload

        Returns:
            Dict with processing results including counts and errors
        """
        webhook_payload = WebhookPayload(payload)
        events = webhook_payload.get_events()

        logger.info(f"Processing webhook with {len(events)} events")

        results: Dict[str, Any] = {
            "processed": 0,
            "skipped": 0,
            "errors": [],
            "events": []
        }

        for event in events:
            try:
                event_result = await self._process_event(event)
                results["events"].append(event_result)

                if event_result.get("status") == "processed":
                    results["processed"] += 1
                elif event_result.get("status") == "skipped":
                    results["skipped"] += 1

            except Exception as e:
                # Log full error for debugging but return sanitized message to caller
                error_msg = f"Error processing event {event}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                sentry_sdk.capture_exception(e)
                # Return sanitized error without internal details
                results["errors"].append(f"Failed to process {event.name} event ({event.id})")

        logger.info(
            f"Webhook processing complete: {results['processed']} processed, "
            f"{results['skipped']} skipped, {len(results['errors'])} errors"
        )

        return results

    async def _process_event(self, event: WebhookEvent) -> Dict[str, Any]:
        """
        Process a single webhook event.

        Args:
            event: The webhook event to process

        Returns:
            Dict with event processing result
        """
        result = {
            "entity_type": event.name,
            "entity_id": event.id,
            "operation": event.operation,
            "realm_id": event.realm_id,
            "status": "unknown"
        }

        # Check if we support this entity type
        if event.name not in self.SUPPORTED_ENTITIES:
            result["status"] = "skipped"
            result["reason"] = f"Unsupported entity type: {event.name}"
            logger.debug(f"Skipping unsupported entity type: {event.name}")
            return result

        # Check if we support this operation
        if event.operation not in self.SUPPORTED_OPERATIONS:
            result["status"] = "skipped"
            result["reason"] = f"Unsupported operation: {event.operation}"
            logger.debug(f"Skipping unsupported operation: {event.operation}")
            return result

        # Find the user and integration associated with this realm_id
        user, integration = await self._find_user_and_integration_by_realm_id(event.realm_id)
        if not user:
            result["status"] = "skipped"
            result["reason"] = f"No user found for realm_id: {event.realm_id}"
            logger.warning(f"No user found for realm_id: {event.realm_id}")
            return result

        # Get user's QuickBooks settings
        settings = self._get_settings(integration)

        # Check if auto-sync is enabled
        if not settings.get('auto_sync_enabled', True):
            result["status"] = "skipped"
            result["reason"] = "Auto-sync disabled by user settings"
            logger.info(f"Skipping {event.name}:{event.id} - auto-sync disabled for user {user.id}")
            return result

        # Check if this entity type is enabled
        entity_settings_map = {
            "Customer": "sync_customers",
            "Invoice": "sync_invoices",
            "Payment": "sync_payments",
            "Purchase": "sync_expenses"
        }

        setting_key = entity_settings_map.get(event.name)
        if setting_key and not settings.get(setting_key, True):
            result["status"] = "skipped"
            result["reason"] = f"Sync for {event.name} disabled by user settings"
            logger.info(f"Skipping {event.name}:{event.id} - {setting_key} disabled for user {user.id}")
            return result

        # Process based on entity type
        try:
            if event.name == "Customer":
                await self._sync_customer(user, event)
            elif event.name == "Invoice":
                await self._sync_invoice(user, event)
            elif event.name == "Payment":
                await self._sync_payment(user, event)
            elif event.name == "Purchase":
                await self._sync_expense(user, event)

            result["status"] = "processed"
            logger.info(f"Successfully processed {event.name}:{event.id} ({event.operation})")

            # Send in-app notification to the landlord (if enabled)
            if settings.get('notify_on_sync', True):
                await self._send_sync_notification(user, event, success=True)

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error(f"Error syncing {event.name}:{event.id}: {e}", exc_info=True)

            # Send error notification to the landlord (always notify on errors)
            if settings.get('notify_on_sync', True):
                await self._send_sync_notification(user, event, success=False, error=str(e))
            raise

        return result

    def _get_settings(self, integration: Optional[Integration]) -> Dict[str, Any]:
        """
        Extract QuickBooks settings from integration with defaults.

        Args:
            integration: The Integration object (may be None)

        Returns:
            Dict with settings, using defaults for any missing values
        """
        defaults = {
            'auto_sync_enabled': True,
            'sync_customers': True,
            'sync_invoices': True,
            'sync_payments': True,
            'sync_expenses': True,
            'notify_on_sync': True
        }

        if not integration or not integration.connection_metadata:
            return defaults

        settings = integration.connection_metadata.get('settings', {})
        return {**defaults, **settings}

    async def _find_user_and_integration_by_realm_id(
        self, realm_id: str
    ) -> tuple[Optional[User], Optional[Integration]]:
        """
        Find the user and integration associated with a QuickBooks realm ID.

        Args:
            realm_id: The QuickBooks company realm ID

        Returns:
            Tuple of (User, Integration) if found, (None, None) otherwise
        """
        result = await self.session.execute(
            select(QuickBooksIntegration, Integration, User)
            .join(Integration, col(QuickBooksIntegration.integration_id) == Integration.id)
            .join(User, col(Integration.user_id) == col(User.id))
            .where(
                col(QuickBooksIntegration.realm_id) == realm_id,
                col(Integration.status) == IntegrationStatus.CONNECTED,
                col(Integration.integration_type) == IntegrationType.QUICKBOOKS
            )
        )
        row = result.first()

        if row:
            return row[2], row[1]  # User, Integration

        return None, None

    async def _find_user_by_realm_id(self, realm_id: str) -> Optional[User]:
        """
        Find the user associated with a QuickBooks realm ID.

        Args:
            realm_id: The QuickBooks company realm ID

        Returns:
            User object if found, None otherwise
        """
        # Query QuickBooksIntegration to find the matching realm_id
        result = await self.session.execute(
            select(QuickBooksIntegration, Integration, User)
            .join(Integration, col(QuickBooksIntegration.integration_id) == Integration.id)
            .join(User, col(Integration.user_id) == col(User.id))
            .where(
                col(QuickBooksIntegration.realm_id) == realm_id,
                col(Integration.status) == IntegrationStatus.CONNECTED,
                col(Integration.integration_type) == IntegrationType.QUICKBOOKS
            )
        )
        row = result.first()

        if row:
            return row[2]  # User is the third element

        return None

    async def _sync_customer(self, user: User, event: WebhookEvent) -> None:
        """
        Sync a Customer event from QuickBooks.

        For Customer changes, we update the linked Tenant if one exists.
        """
        from .customer_service import CustomerService
        from ..intuit_client import get_intuit_client_for_user

        logger.info(f"Syncing Customer {event.id} for user {user.id} (operation: {event.operation})")

        if event.operation == "Delete":
            # Handle customer deletion - unlink from tenant
            from Backend.models.tenant import Tenant
            tenant = await self.session.scalar(
                select(Tenant).where(
                    col(Tenant.landlord_id) == user.id,
                    col(Tenant.quickbooks_customer_id) == event.id
                )
            )
            if tenant:
                tenant.quickbooks_customer_id = None
                tenant.last_synced_at = datetime.now(UTC)
                self.session.add(tenant)
                await self.session.commit()
                logger.info(f"Unlinked tenant {tenant.id} from deleted QB customer {event.id}")
            return

        # For Create/Update, fetch the customer and update tenant if linked
        client = await get_intuit_client_for_user(user.id, self.session)
        customer_response = await client.get_customer(event.id)

        if not customer_response:
            logger.warning(f"Could not fetch customer {event.id} from QuickBooks")
            return

        customer = customer_response.get("Customer", {})

        # Find linked tenant
        from Backend.models.tenant import Tenant
        tenant = await self.session.scalar(
            select(Tenant).where(
                col(Tenant.landlord_id) == user.id,
                col(Tenant.quickbooks_customer_id) == event.id
            )
        )

        if tenant:
            # Update tenant with latest customer data
            tenant.first_name = customer.get("GivenName", tenant.first_name)
            tenant.last_name = customer.get("FamilyName", tenant.last_name)

            email_obj = customer.get("PrimaryEmailAddr", {})
            if email_obj and email_obj.get("Address"):
                tenant.email = email_obj.get("Address")

            phone_obj = customer.get("PrimaryPhone", {})
            if phone_obj and phone_obj.get("FreeFormNumber"):
                tenant.phone = phone_obj.get("FreeFormNumber")

            tenant.last_synced_at = datetime.now(UTC)
            self.session.add(tenant)
            await self.session.commit()
            logger.info(f"Updated tenant {tenant.id} from QB customer {event.id}")

    async def _sync_invoice(self, user: User, event: WebhookEvent) -> None:
        """
        Sync an Invoice event from QuickBooks.
        """
        from .invoice_service import InvoiceService
        from ..intuit_client import get_intuit_client_for_user

        logger.info(f"Syncing Invoice {event.id} for user {user.id} (operation: {event.operation})")

        if event.operation in ("Delete", "Void"):
            # Handle invoice deletion/void - update status
            from Backend.models.accounting.invoice import Invoice
            from Backend.models.accounting.common import PaymentStatus

            invoice = await self.session.scalar(
                select(Invoice).where(col(Invoice.quickbooks_id) == event.id)
            )
            if invoice:
                invoice.status = PaymentStatus.VOID
                invoice.last_synced_at = datetime.now(UTC)
                self.session.add(invoice)
                await self.session.commit()
                logger.info(f"Voided invoice {invoice.id} from QB invoice {event.id}")
            return

        # For Create/Update, sync only the specific invoice from the event
        # This is more efficient than a full sync
        if not event.id:
            logger.warning("Webhook invoice event missing entity id; skipping")
            return

        client = await get_intuit_client_for_user(user.id, self.session)
        qb_invoice_data = await client.get_invoice(event.id)

        # Check for QuickBooks API fault response
        if qb_invoice_data and "Fault" in qb_invoice_data:
            raise RuntimeError(f"QuickBooks returned Fault for invoice {event.id}: {qb_invoice_data['Fault']}")

        if not qb_invoice_data or "Invoice" not in qb_invoice_data:
            logger.warning(f"Could not fetch invoice {event.id} from QuickBooks for webhook sync")
            return

        invoice_service = InvoiceService(user, self.session)
        result = await invoice_service.sync_single_invoice_from_quickbooks(qb_invoice_data["Invoice"])
        logger.info(f"Single invoice sync result: {result}")

    async def _sync_payment(self, user: User, event: WebhookEvent) -> None:
        """
        Sync a Payment event from QuickBooks.
        """
        from .payment_service import PaymentService
        from ..intuit_client import get_intuit_client_for_user

        logger.info(f"Syncing Payment {event.id} for user {user.id} (operation: {event.operation})")

        if event.operation in ("Delete", "Void"):
            # Handle payment deletion/void
            from Backend.models.accounting.payment import Payment
            from Backend.models.accounting.common import PaymentStatus

            payment = await self.session.scalar(
                select(Payment).where(col(Payment.quickbooks_id) == event.id)
            )
            if payment:
                payment.status = PaymentStatus.VOID
                payment.last_synced_at = datetime.now(UTC)
                self.session.add(payment)
                await self.session.commit()
                logger.info(f"Voided payment {payment.id} from QB payment {event.id}")
            return

        # For Create/Update, sync only the specific payment from the event
        # This is more efficient than a full sync
        client = await get_intuit_client_for_user(user.id, self.session)
        qb_payment_data = await client.get_payment(event.id)

        if not qb_payment_data or "Payment" not in qb_payment_data:
            logger.warning(f"Could not fetch payment {event.id} from QuickBooks for webhook sync")
            return

        payment_service = PaymentService(user, self.session)
        result = await payment_service.sync_single_payment_from_quickbooks(qb_payment_data["Payment"])
        logger.info(f"Single payment sync result: {result}")

    async def _sync_expense(self, user: User, event: WebhookEvent) -> None:
        """
        Sync a Purchase (expense) event from QuickBooks.
        """
        from .expense_service import ExpenseService
        from ..intuit_client import get_intuit_client_for_user

        logger.info(f"Syncing Purchase/Expense {event.id} for user {user.id} (operation: {event.operation})")

        if event.operation == "Delete":
            # Handle expense deletion - soft delete or mark as deleted
            from Backend.models.accounting.expense import Expense

            expense = await self.session.scalar(
                select(Expense).where(col(Expense.quickbooks_id) == event.id)
            )
            if expense:
                # For now, just unlink from QuickBooks
                expense.quickbooks_id = None
                expense.last_synced_at = datetime.now(UTC)
                self.session.add(expense)
                await self.session.commit()
                logger.info(f"Unlinked expense {expense.id} from deleted QB purchase {event.id}")
            return

        # For Create/Update, sync only the specific expense from the event
        # This is more efficient than a full sync
        client = await get_intuit_client_for_user(user.id, self.session)
        qb_expense_data = await client.get_purchase(event.id)

        if not qb_expense_data or "Purchase" not in qb_expense_data:
            logger.warning(f"Could not fetch purchase {event.id} from QuickBooks for webhook sync")
            return

        expense_service = ExpenseService(user, self.session)
        result = await expense_service.sync_single_expense_from_quickbooks(qb_expense_data["Purchase"])
        logger.info(f"Single expense sync result: {result}")

    async def _send_sync_notification(
        self,
        user: User,
        event: WebhookEvent,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """
        Send an in-app notification to the landlord about a QuickBooks sync event.

        Args:
            user: The landlord user to notify
            event: The webhook event that was processed
            success: Whether the sync was successful
            error: Error message if sync failed
        """
        try:
            # Map entity types to human-readable names
            entity_display_names = {
                "Customer": "customer",
                "Invoice": "invoice",
                "Payment": "payment",
                "Purchase": "expense"
            }

            # Map operations to human-readable descriptions
            operation_descriptions = {
                "Create": "created",
                "Update": "updated",
                "Delete": "deleted",
                "Void": "voided",
                "Merge": "merged"
            }

            entity_name = entity_display_names.get(event.name, event.name.lower())
            operation_desc = operation_descriptions.get(event.operation, event.operation.lower())

            if success:
                title = f"QuickBooks Sync: {entity_name.title()} {operation_desc}"
                message = f"A {entity_name} was {operation_desc} in QuickBooks and has been synced to Brikli."
                priority = "normal"
            else:
                title = f"QuickBooks Sync Failed: {entity_name.title()}"
                message = f"Failed to sync {entity_name} from QuickBooks. Please try a manual sync."
                if error:
                    # Truncate error message if too long
                    error_preview = error[:100] + "..." if len(error) > 100 else error
                    message += f" Error: {error_preview}"
                priority = "high"

            # Build the link based on entity type
            link_mapping = {
                "Customer": "/tenants",
                "Invoice": "/accounting/invoices",
                "Payment": "/accounting/payments",
                "Purchase": "/accounting/expenses"
            }
            link = link_mapping.get(event.name, "/integrations")

            # Create the notification
            await NotificationService.create_notification(
                user_id=user.id,
                type="quickbooks_sync",
                title=title,
                message=message,
                session=self.session,
                link=link,
                metadata={
                    "entity_type": event.name,
                    "entity_id": event.id,
                    "operation": event.operation,
                    "realm_id": event.realm_id,
                    "success": success,
                    "error": error if not success else None,
                    "source": "webhook"
                },
                priority=priority,
                group_key=f"quickbooks_sync_{user.id}"
            )

            logger.info(f"Sent QuickBooks sync notification to user {user.id} for {event.name}:{event.id}")

        except Exception as e:
            # Don't fail the webhook processing if notification fails
            logger.exception(f"Failed to send QuickBooks sync notification: {e}")
            sentry_sdk.capture_exception(e)
