"""
Unit tests for QuickBooks WebhookService class.

Tests webhook signature verification, payload parsing, event processing,
and entity synchronization from QuickBooks webhooks.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, UTC
import base64
import hashlib
import hmac

from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.quickbooks.services.webhook_service import (
    QuickBooksWebhookService,
    WebhookEvent,
    WebhookPayload
)
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


def create_test_webhook_payload(
    realm_id: str = "1234567890",
    entity_type: str = "Customer",
    entity_id: str = "123",
    operation: str = "Update"
):
    """Create a test webhook payload."""
    return {
        "eventNotifications": [
            {
                "realmId": realm_id,
                "dataChangeEvent": {
                    "entities": [
                        {
                            "name": entity_type,
                            "id": entity_id,
                            "operation": operation,
                            "lastUpdated": "2024-06-01T12:00:00.000Z"
                        }
                    ]
                }
            }
        ]
    }


def create_webhook_signature(payload_body: bytes, verifier_token: str) -> str:
    """Create a valid webhook signature for testing."""
    expected_signature = hmac.new(
        key=verifier_token.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(expected_signature).decode("utf-8")


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
def webhook_service(mock_session):
    """Create WebhookService instance with mocked dependencies."""
    return QuickBooksWebhookService(mock_session)


class TestWebhookEvent:
    """Test WebhookEvent class."""

    def test_webhook_event_creation(self):
        """Test WebhookEvent can be created from data."""
        data = {
            "realmId": "1234567890",
            "name": "Customer",
            "id": "123",
            "operation": "Update",
            "lastUpdated": "2024-06-01T12:00:00.000Z"
        }

        event = WebhookEvent(data)

        assert event.realm_id == "1234567890"
        assert event.name == "Customer"
        assert event.id == "123"
        assert event.operation == "Update"
        assert event.last_updated == "2024-06-01T12:00:00.000Z"

    def test_webhook_event_missing_fields(self):
        """Test WebhookEvent with missing fields uses defaults."""
        data = {}

        event = WebhookEvent(data)

        assert event.realm_id == ""
        assert event.name == ""
        assert event.id == ""
        assert event.operation == ""
        assert event.last_updated == ""

    def test_webhook_event_repr(self):
        """Test WebhookEvent string representation."""
        data = {
            "name": "Invoice",
            "id": "456",
            "operation": "Create"
        }

        event = WebhookEvent(data)

        assert "Invoice" in repr(event)
        assert "456" in repr(event)
        assert "Create" in repr(event)


class TestWebhookPayload:
    """Test WebhookPayload class."""

    def test_webhook_payload_get_events_single(self):
        """Test extracting single event from payload."""
        payload_data = create_test_webhook_payload()

        payload = WebhookPayload(payload_data)
        events = payload.get_events()

        assert len(events) == 1
        assert events[0].name == "Customer"
        assert events[0].id == "123"
        assert events[0].operation == "Update"
        assert events[0].realm_id == "1234567890"

    def test_webhook_payload_get_events_multiple(self):
        """Test extracting multiple events from payload."""
        payload_data = {
            "eventNotifications": [
                {
                    "realmId": "realm1",
                    "dataChangeEvent": {
                        "entities": [
                            {"name": "Customer", "id": "1", "operation": "Create"},
                            {"name": "Invoice", "id": "2", "operation": "Update"}
                        ]
                    }
                },
                {
                    "realmId": "realm2",
                    "dataChangeEvent": {
                        "entities": [
                            {"name": "Payment", "id": "3", "operation": "Delete"}
                        ]
                    }
                }
            ]
        }

        payload = WebhookPayload(payload_data)
        events = payload.get_events()

        assert len(events) == 3
        assert events[0].name == "Customer"
        assert events[0].realm_id == "realm1"
        assert events[1].name == "Invoice"
        assert events[1].realm_id == "realm1"
        assert events[2].name == "Payment"
        assert events[2].realm_id == "realm2"

    def test_webhook_payload_empty(self):
        """Test empty webhook payload."""
        payload_data = {"eventNotifications": []}

        payload = WebhookPayload(payload_data)
        events = payload.get_events()

        assert len(events) == 0

    def test_webhook_payload_missing_events(self):
        """Test payload with missing event notifications."""
        payload_data = {}

        payload = WebhookPayload(payload_data)
        events = payload.get_events()

        assert len(events) == 0


class TestWebhookServiceSignatureVerification:
    """Test webhook signature verification."""

    def test_verify_signature_valid(self):
        """Test valid signature verification."""
        verifier_token = "test_verifier_token"
        payload_body = b'{"test": "data"}'

        # Create valid signature
        signature = create_webhook_signature(payload_body, verifier_token)

        with patch('Backend.api.quickbooks.services.webhook_service.settings') as mock_settings:
            mock_settings.INTUIT_WEBHOOK_VERIFIER_TOKEN = verifier_token

            result = QuickBooksWebhookService.verify_signature(payload_body, signature)

            assert result is True

    def test_verify_signature_invalid(self):
        """Test invalid signature verification."""
        verifier_token = "test_verifier_token"
        payload_body = b'{"test": "data"}'

        # Create invalid signature
        invalid_signature = "invalid_signature_base64=="

        with patch('Backend.api.quickbooks.services.webhook_service.settings') as mock_settings:
            mock_settings.INTUIT_WEBHOOK_VERIFIER_TOKEN = verifier_token

            result = QuickBooksWebhookService.verify_signature(payload_body, invalid_signature)

            assert result is False

    def test_verify_signature_missing_token(self):
        """Test signature verification with missing verifier token."""
        payload_body = b'{"test": "data"}'
        signature = "some_signature"

        with patch('Backend.api.quickbooks.services.webhook_service.settings') as mock_settings:
            mock_settings.INTUIT_WEBHOOK_VERIFIER_TOKEN = None

            result = QuickBooksWebhookService.verify_signature(payload_body, signature)

            assert result is False

    def test_verify_signature_exception_handling(self):
        """Test signature verification exception handling."""
        payload_body = b'{"test": "data"}'
        # Invalid base64 signature
        signature = "not_valid_base64!!!"

        with patch('Backend.api.quickbooks.services.webhook_service.settings') as mock_settings:
            mock_settings.INTUIT_WEBHOOK_VERIFIER_TOKEN = "token"

            # Should not raise, returns False
            result = QuickBooksWebhookService.verify_signature(payload_body, signature)

            assert result is False


class TestWebhookServiceProcessWebhook:
    """Test process_webhook method."""

    @pytest.mark.asyncio
    async def test_process_webhook_success(self, webhook_service, mock_session):
        """Test successful webhook processing."""
        payload = create_test_webhook_payload(
            entity_type="Customer",
            entity_id="123",
            operation="Update"
        )

        # Mock _process_event to return success
        webhook_service._process_event = AsyncMock(return_value={
            "entity_type": "Customer",
            "entity_id": "123",
            "operation": "Update",
            "status": "processed"
        })

        result = await webhook_service.process_webhook(payload)

        assert result["processed"] == 1
        assert result["skipped"] == 0
        assert len(result["errors"]) == 0
        assert len(result["events"]) == 1

    @pytest.mark.asyncio
    async def test_process_webhook_skipped(self, webhook_service):
        """Test webhook processing with skipped events."""
        payload = create_test_webhook_payload(
            entity_type="UnsupportedEntity",
            entity_id="123"
        )

        # Mock _process_event to return skipped
        webhook_service._process_event = AsyncMock(return_value={
            "entity_type": "UnsupportedEntity",
            "entity_id": "123",
            "status": "skipped",
            "reason": "Unsupported entity type"
        })

        result = await webhook_service.process_webhook(payload)

        assert result["processed"] == 0
        assert result["skipped"] == 1
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_process_webhook_error(self, webhook_service):
        """Test webhook processing with errors returns sanitized message."""
        payload = create_test_webhook_payload()

        # Mock _process_event to raise exception
        webhook_service._process_event = AsyncMock(side_effect=Exception("Sync error"))

        result = await webhook_service.process_webhook(payload)

        assert result["processed"] == 0
        assert len(result["errors"]) == 1
        # Error message should be sanitized - doesn't expose internal error details
        assert "Failed to process Customer event" in result["errors"][0]
        assert "Sync error" not in result["errors"][0]  # Internal error not exposed

    @pytest.mark.asyncio
    async def test_process_webhook_multiple_events(self, webhook_service):
        """Test processing multiple events in one webhook."""
        payload = {
            "eventNotifications": [
                {
                    "realmId": "realm1",
                    "dataChangeEvent": {
                        "entities": [
                            {"name": "Customer", "id": "1", "operation": "Create"},
                            {"name": "Invoice", "id": "2", "operation": "Update"}
                        ]
                    }
                }
            ]
        }

        # Mock _process_event with different results
        call_count = 0

        async def mock_process_event(event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"status": "processed"}
            return {"status": "skipped"}

        webhook_service._process_event = mock_process_event

        result = await webhook_service.process_webhook(payload)

        assert result["processed"] == 1
        assert result["skipped"] == 1


class TestWebhookServiceProcessEvent:
    """Test _process_event method."""

    @pytest.mark.asyncio
    async def test_process_event_unsupported_entity(self, webhook_service):
        """Test processing unsupported entity type."""
        event = WebhookEvent({
            "name": "UnsupportedType",
            "id": "123",
            "operation": "Update",
            "realmId": "realm1"
        })

        result = await webhook_service._process_event(event)

        assert result["status"] == "skipped"
        assert "Unsupported entity type" in result["reason"]

    @pytest.mark.asyncio
    async def test_process_event_unsupported_operation(self, webhook_service):
        """Test processing unsupported operation."""
        event = WebhookEvent({
            "name": "Customer",
            "id": "123",
            "operation": "UnsupportedOp",
            "realmId": "realm1"
        })

        result = await webhook_service._process_event(event)

        assert result["status"] == "skipped"
        assert "Unsupported operation" in result["reason"]

    @pytest.mark.asyncio
    async def test_process_event_no_user_found(self, webhook_service):
        """Test processing when no user is found for realm_id."""
        event = WebhookEvent({
            "name": "Customer",
            "id": "123",
            "operation": "Update",
            "realmId": "unknown_realm"
        })

        # Mock _find_user_and_integration_by_realm_id to return None
        webhook_service._find_user_and_integration_by_realm_id = AsyncMock(
            return_value=(None, None)
        )

        result = await webhook_service._process_event(event)

        assert result["status"] == "skipped"
        assert "No user found" in result["reason"]

    @pytest.mark.asyncio
    async def test_process_event_auto_sync_disabled(self, webhook_service):
        """Test processing when auto-sync is disabled."""
        event = WebhookEvent({
            "name": "Customer",
            "id": "123",
            "operation": "Update",
            "realmId": "realm1"
        })

        user = create_test_user()
        mock_integration = MagicMock()
        mock_integration.connection_metadata = {
            "settings": {"auto_sync_enabled": False}
        }

        webhook_service._find_user_and_integration_by_realm_id = AsyncMock(
            return_value=(user, mock_integration)
        )

        result = await webhook_service._process_event(event)

        assert result["status"] == "skipped"
        assert "Auto-sync disabled" in result["reason"]

    @pytest.mark.asyncio
    async def test_process_event_entity_sync_disabled(self, webhook_service):
        """Test processing when specific entity sync is disabled."""
        event = WebhookEvent({
            "name": "Invoice",
            "id": "123",
            "operation": "Update",
            "realmId": "realm1"
        })

        user = create_test_user()
        mock_integration = MagicMock()
        mock_integration.connection_metadata = {
            "settings": {
                "auto_sync_enabled": True,
                "sync_invoices": False
            }
        }

        webhook_service._find_user_and_integration_by_realm_id = AsyncMock(
            return_value=(user, mock_integration)
        )

        result = await webhook_service._process_event(event)

        assert result["status"] == "skipped"
        assert "disabled" in result["reason"]

    @pytest.mark.asyncio
    async def test_process_event_customer_success(self, webhook_service):
        """Test successful customer event processing."""
        event = WebhookEvent({
            "name": "Customer",
            "id": "123",
            "operation": "Update",
            "realmId": "realm1"
        })

        user = create_test_user()
        mock_integration = MagicMock()
        mock_integration.connection_metadata = {"settings": {}}

        webhook_service._find_user_and_integration_by_realm_id = AsyncMock(
            return_value=(user, mock_integration)
        )
        webhook_service._sync_customer = AsyncMock()
        webhook_service._send_sync_notification = AsyncMock()

        result = await webhook_service._process_event(event)

        assert result["status"] == "processed"
        webhook_service._sync_customer.assert_called_once_with(user, event)

    @pytest.mark.asyncio
    async def test_process_event_invoice_success(self, webhook_service):
        """Test successful invoice event processing."""
        event = WebhookEvent({
            "name": "Invoice",
            "id": "456",
            "operation": "Create",
            "realmId": "realm1"
        })

        user = create_test_user()
        mock_integration = MagicMock()
        mock_integration.connection_metadata = {"settings": {}}

        webhook_service._find_user_and_integration_by_realm_id = AsyncMock(
            return_value=(user, mock_integration)
        )
        webhook_service._sync_invoice = AsyncMock()
        webhook_service._send_sync_notification = AsyncMock()

        result = await webhook_service._process_event(event)

        assert result["status"] == "processed"
        webhook_service._sync_invoice.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_event_payment_success(self, webhook_service):
        """Test successful payment event processing."""
        event = WebhookEvent({
            "name": "Payment",
            "id": "789",
            "operation": "Update",
            "realmId": "realm1"
        })

        user = create_test_user()
        mock_integration = MagicMock()
        mock_integration.connection_metadata = {"settings": {}}

        webhook_service._find_user_and_integration_by_realm_id = AsyncMock(
            return_value=(user, mock_integration)
        )
        webhook_service._sync_payment = AsyncMock()
        webhook_service._send_sync_notification = AsyncMock()

        result = await webhook_service._process_event(event)

        assert result["status"] == "processed"
        webhook_service._sync_payment.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_event_purchase_success(self, webhook_service):
        """Test successful purchase/expense event processing."""
        event = WebhookEvent({
            "name": "Purchase",
            "id": "101",
            "operation": "Create",
            "realmId": "realm1"
        })

        user = create_test_user()
        mock_integration = MagicMock()
        mock_integration.connection_metadata = {"settings": {}}

        webhook_service._find_user_and_integration_by_realm_id = AsyncMock(
            return_value=(user, mock_integration)
        )
        webhook_service._sync_expense = AsyncMock()
        webhook_service._send_sync_notification = AsyncMock()

        result = await webhook_service._process_event(event)

        assert result["status"] == "processed"
        webhook_service._sync_expense.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_event_sync_error(self, webhook_service):
        """Test event processing with sync error."""
        event = WebhookEvent({
            "name": "Customer",
            "id": "123",
            "operation": "Update",
            "realmId": "realm1"
        })

        user = create_test_user()
        mock_integration = MagicMock()
        mock_integration.connection_metadata = {"settings": {}}

        webhook_service._find_user_and_integration_by_realm_id = AsyncMock(
            return_value=(user, mock_integration)
        )
        webhook_service._sync_customer = AsyncMock(side_effect=Exception("Sync failed"))
        webhook_service._send_sync_notification = AsyncMock()

        with pytest.raises(Exception):
            await webhook_service._process_event(event)


class TestWebhookServiceGetSettings:
    """Test _get_settings method."""

    def test_get_settings_with_defaults(self, webhook_service):
        """Test getting settings with defaults when no integration."""
        result = webhook_service._get_settings(None)

        assert result["auto_sync_enabled"] is True
        assert result["sync_customers"] is True
        assert result["sync_invoices"] is True
        assert result["sync_payments"] is True
        assert result["sync_expenses"] is True
        assert result["notify_on_sync"] is True

    def test_get_settings_with_custom_values(self, webhook_service):
        """Test getting settings with custom values."""
        mock_integration = MagicMock()
        mock_integration.connection_metadata = {
            "settings": {
                "auto_sync_enabled": False,
                "sync_customers": False,
                "notify_on_sync": False
            }
        }

        result = webhook_service._get_settings(mock_integration)

        assert result["auto_sync_enabled"] is False
        assert result["sync_customers"] is False
        assert result["notify_on_sync"] is False
        # Defaults should still apply for unset values
        assert result["sync_invoices"] is True
        assert result["sync_payments"] is True

    def test_get_settings_empty_metadata(self, webhook_service):
        """Test getting settings with empty connection_metadata."""
        mock_integration = MagicMock()
        mock_integration.connection_metadata = None

        result = webhook_service._get_settings(mock_integration)

        # All defaults
        assert result["auto_sync_enabled"] is True


class TestWebhookServiceSyncCustomer:
    """Test _sync_customer method."""

    @pytest.mark.asyncio
    async def test_sync_customer_delete(self, webhook_service, mock_session):
        """Test customer delete operation."""
        event = WebhookEvent({
            "name": "Customer",
            "id": "qb_123",
            "operation": "Delete",
            "realmId": "realm1"
        })
        user = create_test_user()

        # Mock finding a tenant with this QB customer ID
        mock_tenant = MagicMock()
        mock_tenant.id = uuid4()
        mock_tenant.quickbooks_customer_id = "qb_123"
        mock_session.scalar = AsyncMock(return_value=mock_tenant)

        await webhook_service._sync_customer(user, event)

        # Tenant should be unlinked
        assert mock_tenant.quickbooks_customer_id is None
        mock_session.add.assert_called_with(mock_tenant)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_customer_update(self, webhook_service, mock_session):
        """Test customer update operation."""
        event = WebhookEvent({
            "name": "Customer",
            "id": "qb_123",
            "operation": "Update",
            "realmId": "realm1"
        })
        user = create_test_user()

        # Mock finding a linked tenant
        mock_tenant = MagicMock()
        mock_tenant.id = uuid4()
        mock_tenant.quickbooks_customer_id = "qb_123"
        mock_tenant.first_name = "Old"
        mock_tenant.last_name = "Name"
        mock_session.scalar = AsyncMock(return_value=mock_tenant)

        # Mock QB client response - patch at the import location
        with patch('Backend.api.quickbooks.intuit_client.get_intuit_client_for_user') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_customer = AsyncMock(return_value={
                "Customer": {
                    "Id": "qb_123",
                    "GivenName": "John",
                    "FamilyName": "Doe",
                    "PrimaryEmailAddr": {"Address": "john@example.com"},
                    "PrimaryPhone": {"FreeFormNumber": "555-1234"}
                }
            })
            mock_get_client.return_value = mock_client

            await webhook_service._sync_customer(user, event)

            # Tenant should be updated
            assert mock_tenant.first_name == "John"
            assert mock_tenant.last_name == "Doe"
            mock_session.add.assert_called()
            mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_sync_customer_no_linked_tenant(self, webhook_service, mock_session):
        """Test customer update when no linked tenant exists."""
        event = WebhookEvent({
            "name": "Customer",
            "id": "qb_123",
            "operation": "Update",
            "realmId": "realm1"
        })
        user = create_test_user()

        # No linked tenant
        mock_session.scalar = AsyncMock(return_value=None)

        # Mock QB client response - patch at the import location
        with patch('Backend.api.quickbooks.intuit_client.get_intuit_client_for_user') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_customer = AsyncMock(return_value={
                "Customer": {"Id": "qb_123", "GivenName": "John"}
            })
            mock_get_client.return_value = mock_client

            # Should not raise, just skip
            await webhook_service._sync_customer(user, event)

            # No commit should happen for unlinked customer
            mock_session.commit.assert_not_called()


class TestWebhookServiceSyncInvoice:
    """Test _sync_invoice method."""

    @pytest.mark.asyncio
    async def test_sync_invoice_void(self, webhook_service, mock_session):
        """Test invoice void operation."""
        event = WebhookEvent({
            "name": "Invoice",
            "id": "qb_456",
            "operation": "Void",
            "realmId": "realm1"
        })
        user = create_test_user()

        # Mock finding an invoice
        mock_invoice = MagicMock()
        mock_invoice.id = uuid4()
        mock_invoice.quickbooks_id = "qb_456"
        mock_session.scalar = AsyncMock(return_value=mock_invoice)

        await webhook_service._sync_invoice(user, event)

        # Invoice should be voided
        mock_session.add.assert_called_with(mock_invoice)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_invoice_create(self, webhook_service, mock_session):
        """Test invoice create operation."""
        event = WebhookEvent({
            "name": "Invoice",
            "id": "qb_456",
            "operation": "Create",
            "realmId": "realm1"
        })
        user = create_test_user()

        # Mock QB client and InvoiceService - patch at import locations
        with patch('Backend.api.quickbooks.intuit_client.get_intuit_client_for_user') as mock_get_client, \
             patch('Backend.api.quickbooks.services.invoice_service.InvoiceService') as mock_invoice_service_class:

            mock_client = AsyncMock()
            mock_client.get_invoice = AsyncMock(return_value={
                "Invoice": {"Id": "qb_456", "TotalAmt": 100.00}
            })
            mock_get_client.return_value = mock_client

            mock_invoice_service = AsyncMock()
            mock_invoice_service.sync_single_invoice_from_quickbooks = AsyncMock(return_value={
                "synced_count": 1
            })
            mock_invoice_service_class.return_value = mock_invoice_service

            await webhook_service._sync_invoice(user, event)

            mock_invoice_service.sync_single_invoice_from_quickbooks.assert_called_once()


class TestWebhookServiceSyncPayment:
    """Test _sync_payment method."""

    @pytest.mark.asyncio
    async def test_sync_payment_delete(self, webhook_service, mock_session):
        """Test payment delete operation."""
        event = WebhookEvent({
            "name": "Payment",
            "id": "qb_789",
            "operation": "Delete",
            "realmId": "realm1"
        })
        user = create_test_user()

        # Mock finding a payment
        mock_payment = MagicMock()
        mock_payment.id = uuid4()
        mock_payment.quickbooks_id = "qb_789"
        mock_session.scalar = AsyncMock(return_value=mock_payment)

        await webhook_service._sync_payment(user, event)

        mock_session.add.assert_called_with(mock_payment)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_payment_update(self, webhook_service, mock_session):
        """Test payment update operation."""
        event = WebhookEvent({
            "name": "Payment",
            "id": "qb_789",
            "operation": "Update",
            "realmId": "realm1"
        })
        user = create_test_user()

        # Mock QB client and PaymentService - patch at import locations
        with patch('Backend.api.quickbooks.intuit_client.get_intuit_client_for_user') as mock_get_client, \
             patch('Backend.api.quickbooks.services.payment_service.PaymentService') as mock_payment_service_class:

            mock_client = AsyncMock()
            mock_client.get_payment = AsyncMock(return_value={
                "Payment": {"Id": "qb_789", "TotalAmt": 500.00}
            })
            mock_get_client.return_value = mock_client

            mock_payment_service = AsyncMock()
            mock_payment_service.sync_single_payment_from_quickbooks = AsyncMock(return_value={
                "synced_count": 1
            })
            mock_payment_service_class.return_value = mock_payment_service

            await webhook_service._sync_payment(user, event)

            mock_payment_service.sync_single_payment_from_quickbooks.assert_called_once()


class TestWebhookServiceSyncExpense:
    """Test _sync_expense method."""

    @pytest.mark.asyncio
    async def test_sync_expense_delete(self, webhook_service, mock_session):
        """Test expense delete operation."""
        event = WebhookEvent({
            "name": "Purchase",
            "id": "qb_101",
            "operation": "Delete",
            "realmId": "realm1"
        })
        user = create_test_user()

        # Mock finding an expense
        mock_expense = MagicMock()
        mock_expense.id = uuid4()
        mock_expense.quickbooks_id = "qb_101"
        mock_session.scalar = AsyncMock(return_value=mock_expense)

        await webhook_service._sync_expense(user, event)

        # Expense should be unlinked
        assert mock_expense.quickbooks_id is None
        mock_session.add.assert_called_with(mock_expense)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_expense_create(self, webhook_service, mock_session):
        """Test expense create operation."""
        event = WebhookEvent({
            "name": "Purchase",
            "id": "qb_101",
            "operation": "Create",
            "realmId": "realm1"
        })
        user = create_test_user()

        # Mock QB client and ExpenseService - patch at import locations
        with patch('Backend.api.quickbooks.intuit_client.get_intuit_client_for_user') as mock_get_client, \
             patch('Backend.api.quickbooks.services.expense_service.ExpenseService') as mock_expense_service_class:

            mock_client = AsyncMock()
            mock_client.get_purchase = AsyncMock(return_value={
                "Purchase": {"Id": "qb_101", "TotalAmt": 75.00}
            })
            mock_get_client.return_value = mock_client

            mock_expense_service = AsyncMock()
            mock_expense_service.sync_single_expense_from_quickbooks = AsyncMock(return_value={
                "synced_count": 1
            })
            mock_expense_service_class.return_value = mock_expense_service

            await webhook_service._sync_expense(user, event)

            mock_expense_service.sync_single_expense_from_quickbooks.assert_called_once()


class TestWebhookServiceFindUser:
    """Test _find_user_and_integration_by_realm_id method."""

    @pytest.mark.asyncio
    async def test_find_user_found(self, webhook_service, mock_session):
        """Test finding user by realm_id."""
        user = create_test_user()
        mock_integration = MagicMock()

        # Mock the query result
        mock_row = (MagicMock(), mock_integration, user)
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        mock_session.execute = AsyncMock(return_value=mock_result)

        found_user, found_integration = await webhook_service._find_user_and_integration_by_realm_id("realm123")

        assert found_user == user
        assert found_integration == mock_integration

    @pytest.mark.asyncio
    async def test_find_user_not_found(self, webhook_service, mock_session):
        """Test finding user when realm_id doesn't exist."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        found_user, found_integration = await webhook_service._find_user_and_integration_by_realm_id("unknown_realm")

        assert found_user is None
        assert found_integration is None


class TestWebhookServiceSendNotification:
    """Test _send_sync_notification method."""

    @pytest.mark.asyncio
    async def test_send_notification_success(self, webhook_service):
        """Test sending success notification."""
        user = create_test_user()
        event = WebhookEvent({
            "name": "Invoice",
            "id": "123",
            "operation": "Create",
            "realmId": "realm1"
        })

        with patch('Backend.api.quickbooks.services.webhook_service.NotificationService') as mock_ns:
            mock_ns.create_notification = AsyncMock()

            await webhook_service._send_sync_notification(user, event, success=True)

            mock_ns.create_notification.assert_called_once()
            call_kwargs = mock_ns.create_notification.call_args[1]
            assert call_kwargs["user_id"] == user.id
            assert call_kwargs["type"] == "quickbooks_sync"
            assert "created" in call_kwargs["title"]
            assert call_kwargs["priority"] == "normal"

    @pytest.mark.asyncio
    async def test_send_notification_error(self, webhook_service):
        """Test sending error notification."""
        user = create_test_user()
        event = WebhookEvent({
            "name": "Payment",
            "id": "456",
            "operation": "Update",
            "realmId": "realm1"
        })

        with patch('Backend.api.quickbooks.services.webhook_service.NotificationService') as mock_ns:
            mock_ns.create_notification = AsyncMock()

            await webhook_service._send_sync_notification(
                user, event, success=False, error="Connection timeout"
            )

            mock_ns.create_notification.assert_called_once()
            call_kwargs = mock_ns.create_notification.call_args[1]
            assert call_kwargs["priority"] == "high"
            assert "Failed" in call_kwargs["title"]
            assert "Connection timeout" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_send_notification_exception_handling(self, webhook_service):
        """Test notification sending doesn't fail webhook processing."""
        user = create_test_user()
        event = WebhookEvent({
            "name": "Customer",
            "id": "789",
            "operation": "Delete",
            "realmId": "realm1"
        })

        with patch('Backend.api.quickbooks.services.webhook_service.NotificationService') as mock_ns:
            mock_ns.create_notification = AsyncMock(side_effect=Exception("Notification error"))

            # Should not raise
            await webhook_service._send_sync_notification(user, event, success=True)


class TestSupportedEntitiesAndOperations:
    """Test SUPPORTED_ENTITIES and SUPPORTED_OPERATIONS constants."""

    def test_supported_entities(self):
        """Test supported entity types."""
        assert "Customer" in QuickBooksWebhookService.SUPPORTED_ENTITIES
        assert "Invoice" in QuickBooksWebhookService.SUPPORTED_ENTITIES
        assert "Payment" in QuickBooksWebhookService.SUPPORTED_ENTITIES
        assert "Purchase" in QuickBooksWebhookService.SUPPORTED_ENTITIES

    def test_supported_operations(self):
        """Test supported operations."""
        assert "Create" in QuickBooksWebhookService.SUPPORTED_OPERATIONS
        assert "Update" in QuickBooksWebhookService.SUPPORTED_OPERATIONS
        assert "Delete" in QuickBooksWebhookService.SUPPORTED_OPERATIONS
        assert "Void" in QuickBooksWebhookService.SUPPORTED_OPERATIONS
        assert "Merge" in QuickBooksWebhookService.SUPPORTED_OPERATIONS
