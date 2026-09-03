"""
API tests for QuickBooks webhook endpoints.

Tests webhook verification and processing with HMAC-SHA256 signature verification.
"""

import pytest
import hmac
import hashlib
import base64
import json
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from uuid import uuid4

from Backend.api.app import app
from Backend.models.user import User
from Backend.models.enums import UserType
from Backend.api.auth import get_current_user
from Backend.database import get_session

# Import helper functions from conftest.py
from ..conftest import assert_valid_json_response

# Mark all tests in this module as API tests
pytestmark = pytest.mark.api

# Fixed datetime for deterministic testing
FIXED_DATETIME = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

# Test webhook verifier token (matches what would be configured in settings)
TEST_WEBHOOK_VERIFIER_TOKEN = "test_verifier_token_12345"


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """Ensure dependency overrides are cleared after each test."""
    yield
    app.dependency_overrides.clear()


class TestClientWithHost(TestClient):
    """Custom TestClient that sets the proper host header."""
    def request(self, method: str, url, **kwargs):
        headers = kwargs.get("headers") or {}
        if "host" not in {k.lower() for k in headers.keys()}:
            headers["Host"] = "localhost"
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


def generate_valid_signature(payload: dict, verifier_token: str) -> str:
    """Generate a valid HMAC-SHA256 signature for a webhook payload."""
    payload_bytes = json.dumps(payload).encode('utf-8')
    signature = hmac.new(
        verifier_token.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode('utf-8')


def create_webhook_payload(realm_id: str = "123456789", entity_name: str = "Customer", operation: str = "Create"):
    """Create a sample QuickBooks webhook payload."""
    return {
        "eventNotifications": [
            {
                "realmId": realm_id,
                "dataChangeEvent": {
                    "entities": [
                        {
                            "name": entity_name,
                            "id": "99",
                            "operation": operation,
                            "lastUpdated": "2024-06-01T12:00:00.000Z"
                        }
                    ]
                }
            }
        ]
    }


class TestWebhookVerification:
    """Tests for GET /api/quickbooks/webhooks/verify endpoint."""

    def test_webhook_verify_endpoint(self):
        """Test webhook verification endpoint returns success."""
        with TestClientWithHost(app) as client:
            response = client.get("/api/quickbooks/webhooks/verify")

            data = assert_valid_json_response(response, dict)
            assert data["status"] == "ok"
            assert "verified" in data["message"].lower()

    def test_webhook_verify_no_auth_required(self):
        """Test that webhook verification does not require authentication."""
        # Don't set any auth overrides
        with TestClientWithHost(app) as client:
            response = client.get("/api/quickbooks/webhooks/verify")

            # Should succeed without authentication
            assert response.status_code == 200


class TestWebhookProcessing:
    """Tests for POST /api/quickbooks/webhooks endpoint."""

    def test_webhook_missing_signature(self):
        """Test webhook rejection when signature is missing."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload()

        with TestClientWithHost(app) as client:
            response = client.post(
                "/api/quickbooks/webhooks",
                json=payload
                # No intuit-signature header
            )

            assert response.status_code == 401
            data = response.json()
            assert "missing" in data["detail"].lower() or "signature" in data["detail"].lower()

    def test_webhook_invalid_signature(self):
        """Test webhook rejection with invalid signature."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload()

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService.verify_signature') as mock_verify:
            mock_verify.return_value = False

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "invalid_signature"}
                )

                assert response.status_code == 401
                data = response.json()
                assert "invalid" in data["detail"].lower()

    def test_webhook_valid_signature_success(self):
        """Test successful webhook processing with valid signature."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload()

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            # Mock static method for signature verification
            mock_service_class.verify_signature.return_value = True

            # Mock instance for processing
            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                data = assert_valid_json_response(response, dict)
                assert data["success"] is True
                assert data["processed"] == 1
                assert data["skipped"] == 0
                assert len(data["errors"]) == 0

    def test_webhook_processing_with_errors(self):
        """Test webhook processing that encounters errors."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload()

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 2,
                "skipped": 1,
                "errors": ["Failed to sync entity 99: Connection timeout"]
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                data = assert_valid_json_response(response, dict)
                assert data["success"] is False
                assert data["processed"] == 2
                assert data["skipped"] == 1
                assert len(data["errors"]) == 1

    def test_webhook_empty_notifications(self):
        """Test webhook with empty event notifications."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = {"eventNotifications": []}

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 0,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                data = assert_valid_json_response(response, dict)
                assert data["success"] is True
                assert data["processed"] == 0

    def test_webhook_multiple_notifications(self):
        """Test webhook with multiple event notifications."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = {
            "eventNotifications": [
                {
                    "realmId": "123456789",
                    "dataChangeEvent": {
                        "entities": [
                            {"name": "Customer", "id": "1", "operation": "Create", "lastUpdated": "2024-06-01T12:00:00.000Z"},
                            {"name": "Invoice", "id": "2", "operation": "Update", "lastUpdated": "2024-06-01T12:00:01.000Z"},
                        ]
                    }
                },
                {
                    "realmId": "987654321",
                    "dataChangeEvent": {
                        "entities": [
                            {"name": "Payment", "id": "3", "operation": "Create", "lastUpdated": "2024-06-01T12:00:02.000Z"}
                        ]
                    }
                }
            ]
        }

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 3,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                data = assert_valid_json_response(response, dict)
                assert data["success"] is True
                assert data["processed"] == 3

    def test_webhook_invalid_json(self):
        """Test webhook with invalid JSON payload."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    content="not valid json",
                    headers={
                        "intuit-signature": "valid_signature_here",
                        "Content-Type": "application/json"
                    }
                )

                # FastAPI returns 422 for invalid JSON body
                assert response.status_code in [400, 422]

    def test_webhook_no_auth_required(self):
        """Test that webhook endpoint does not require authentication."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload()

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            # Don't set any auth overrides - endpoint should work without auth
            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                # Should succeed without authentication (security via signature)
                assert response.status_code == 200


class TestWebhookEntityTypes:
    """Tests for different entity types in webhook processing."""

    def test_webhook_customer_entity(self):
        """Test webhook processing for Customer entity."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload(entity_name="Customer", operation="Create")

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                assert response.status_code == 200

    def test_webhook_invoice_entity(self):
        """Test webhook processing for Invoice entity."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload(entity_name="Invoice", operation="Update")

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                assert response.status_code == 200

    def test_webhook_payment_entity(self):
        """Test webhook processing for Payment entity."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload(entity_name="Payment", operation="Create")

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                assert response.status_code == 200

    def test_webhook_purchase_entity(self):
        """Test webhook processing for Purchase (expense) entity."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload(entity_name="Purchase", operation="Create")

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                assert response.status_code == 200


class TestWebhookOperationTypes:
    """Tests for different operation types in webhook processing."""

    def test_webhook_create_operation(self):
        """Test webhook processing for Create operation."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload(operation="Create")

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                assert response.status_code == 200

    def test_webhook_update_operation(self):
        """Test webhook processing for Update operation."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload(operation="Update")

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                assert response.status_code == 200

    def test_webhook_delete_operation(self):
        """Test webhook processing for Delete operation."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload(operation="Delete")

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                assert response.status_code == 200

    def test_webhook_void_operation(self):
        """Test webhook processing for Void operation."""
        mock_session = AsyncMock()
        app.dependency_overrides[get_session] = lambda: mock_session

        payload = create_webhook_payload(operation="Void")

        with patch('Backend.api.quickbooks.router.QuickBooksWebhookService') as mock_service_class:
            mock_service_class.verify_signature.return_value = True

            mock_service = AsyncMock()
            mock_service.process_webhook.return_value = {
                "processed": 1,
                "skipped": 0,
                "errors": []
            }
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post(
                    "/api/quickbooks/webhooks",
                    json=payload,
                    headers={"intuit-signature": "valid_signature_here"}
                )

                assert response.status_code == 200
