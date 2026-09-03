"""
API tests for QuickBooks settings endpoints.

Tests GET /settings and PUT /settings endpoints for managing
auto-sync behavior, entity sync scope, and notification preferences.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from uuid import uuid4

from Backend.api.app import app
from Backend.models.user import User
from Backend.models.enums import UserType
from Backend.models.accounting.integration import Integration, IntegrationStatus, IntegrationType
from Backend.api.auth import get_current_user
from Backend.database import get_session

# Import helper functions from conftest.py
from ..conftest import assert_valid_json_response

# Mark all tests in this module as API tests
pytestmark = pytest.mark.api

# Fixed datetime for deterministic testing
FIXED_DATETIME = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


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


def create_test_user(user_id=None, email="test@example.com", user_type=UserType.LANDLORD, is_admin=False):
    """Helper function to create a properly initialized test user."""
    return User(
        id=user_id or uuid4(),
        email=email,
        first_name="Test",
        last_name="User",
        user_type=user_type,
        is_active=True,
        is_admin=is_admin,
        created_at=FIXED_DATETIME,
        updated_at=FIXED_DATETIME,
        is_email_verified=True
    )


def create_mock_integration(connected=True, with_settings=True):
    """Helper to create a mock QuickBooks integration with settings."""
    mock_integration = MagicMock(spec=Integration)
    mock_integration.id = uuid4()
    mock_integration.user_id = uuid4()
    mock_integration.integration_type = IntegrationType.QUICKBOOKS
    mock_integration.status = IntegrationStatus.CONNECTED if connected else IntegrationStatus.PENDING
    mock_integration.connected_at = FIXED_DATETIME if connected else None
    mock_integration.last_sync_at = FIXED_DATETIME if connected else None
    mock_integration.error_count = 0
    mock_integration.last_error = None

    if with_settings:
        mock_integration.connection_metadata = {
            'settings': {
                'auto_sync_enabled': True,
                'sync_customers': True,
                'sync_invoices': True,
                'sync_payments': True,
                'sync_expenses': True,
                'notify_on_sync': True
            }
        }
    else:
        mock_integration.connection_metadata = {}

    return mock_integration


class TestGetQuickBooksSettings:
    """Tests for GET /api/quickbooks/settings endpoint."""

    def test_get_settings_success(self):
        """Test successful retrieval of QuickBooks settings."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_integration = create_mock_integration(connected=True, with_settings=True)

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration:
            mock_get_integration.return_value = mock_integration

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/settings")

                data = assert_valid_json_response(response, dict)

                # Check settings structure
                assert "settings" in data
                assert "connection_health" in data

                settings = data["settings"]
                assert "auto_sync_enabled" in settings
                assert "sync_customers" in settings
                assert "sync_invoices" in settings
                assert "sync_payments" in settings
                assert "sync_expenses" in settings
                assert "notify_on_sync" in settings

                # Check connection health structure
                health = data["connection_health"]
                assert "last_sync_at" in health
                assert "error_count" in health

    def test_get_settings_with_defaults(self):
        """Test settings retrieval with default values when none are set."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_integration = create_mock_integration(connected=True, with_settings=False)

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration:
            mock_get_integration.return_value = mock_integration

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/settings")

                data = assert_valid_json_response(response, dict)

                # All defaults should be True
                settings = data["settings"]
                assert settings["auto_sync_enabled"] is True
                assert settings["sync_customers"] is True
                assert settings["sync_invoices"] is True
                assert settings["sync_payments"] is True
                assert settings["sync_expenses"] is True
                assert settings["notify_on_sync"] is True

    def test_get_settings_not_connected(self):
        """Test settings retrieval when QuickBooks is not connected."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration:
            mock_get_integration.return_value = None

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/settings")

                assert response.status_code == 400
                data = response.json()
                assert "not connected" in data["detail"].lower()

    def test_get_settings_permission_denied_tenant(self):
        """Test that tenants cannot access QuickBooks settings."""
        test_user = create_test_user(user_type=UserType.TENANT)
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with TestClientWithHost(app) as client:
            response = client.get("/api/quickbooks/settings")

            assert response.status_code == 403
            data = response.json()
            assert "landlord" in data["detail"].lower() or "admin" in data["detail"].lower()

    def test_get_settings_admin_allowed(self):
        """Test that admins can access QuickBooks settings."""
        test_user = create_test_user(user_type=UserType.TENANT, is_admin=True)
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_integration = create_mock_integration(connected=True, with_settings=True)

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration:
            mock_get_integration.return_value = mock_integration

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/settings")

                # Admins should be allowed
                assert response.status_code == 200


class TestUpdateQuickBooksSettings:
    """Tests for PUT /api/quickbooks/settings endpoint."""

    def test_update_settings_full(self):
        """Test full settings update."""
        test_user = create_test_user()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_integration = create_mock_integration(connected=True, with_settings=True)

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration, \
             patch('Backend.api.quickbooks.router.flag_modified') as mock_flag:
            mock_get_integration.return_value = mock_integration

            with TestClientWithHost(app) as client:
                payload = {
                    "auto_sync_enabled": False,
                    "sync_customers": False,
                    "sync_invoices": True,
                    "sync_payments": True,
                    "sync_expenses": False,
                    "notify_on_sync": False
                }

                response = client.put("/api/quickbooks/settings", json=payload)

                data = assert_valid_json_response(response, dict)

                settings = data["settings"]
                assert settings["auto_sync_enabled"] is False
                assert settings["sync_customers"] is False
                assert settings["sync_invoices"] is True
                assert settings["sync_payments"] is True
                assert settings["sync_expenses"] is False
                assert settings["notify_on_sync"] is False

    def test_update_settings_partial(self):
        """Test partial settings update (only specified fields)."""
        test_user = create_test_user()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_integration = create_mock_integration(connected=True, with_settings=True)

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration, \
             patch('Backend.api.quickbooks.router.flag_modified') as mock_flag:
            mock_get_integration.return_value = mock_integration

            with TestClientWithHost(app) as client:
                # Only update auto_sync_enabled
                payload = {
                    "auto_sync_enabled": False
                }

                response = client.put("/api/quickbooks/settings", json=payload)

                data = assert_valid_json_response(response, dict)

                settings = data["settings"]
                # Only auto_sync_enabled should be changed
                assert settings["auto_sync_enabled"] is False
                # Others should remain at their defaults (True)
                assert settings["sync_customers"] is True
                assert settings["notify_on_sync"] is True

    def test_update_settings_not_connected(self):
        """Test settings update when QuickBooks is not connected."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration:
            mock_get_integration.return_value = None

            with TestClientWithHost(app) as client:
                response = client.put("/api/quickbooks/settings", json={"auto_sync_enabled": False})

                assert response.status_code == 400
                data = response.json()
                assert "not connected" in data["detail"].lower()

    def test_update_settings_permission_denied_tenant(self):
        """Test that tenants cannot update QuickBooks settings."""
        test_user = create_test_user(user_type=UserType.TENANT)
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with TestClientWithHost(app) as client:
            response = client.put("/api/quickbooks/settings", json={"auto_sync_enabled": False})

            assert response.status_code == 403
            data = response.json()
            assert "landlord" in data["detail"].lower() or "admin" in data["detail"].lower()

    def test_update_settings_empty_payload(self):
        """Test settings update with empty payload (no changes)."""
        test_user = create_test_user()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_integration = create_mock_integration(connected=True, with_settings=True)

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration, \
             patch('Backend.api.quickbooks.router.flag_modified') as mock_flag:
            mock_get_integration.return_value = mock_integration

            with TestClientWithHost(app) as client:
                # Empty payload should preserve existing settings
                response = client.put("/api/quickbooks/settings", json={})

                data = assert_valid_json_response(response, dict)

                # All settings should remain at their original values
                settings = data["settings"]
                assert settings["auto_sync_enabled"] is True

    def test_update_settings_admin_allowed(self):
        """Test that admins can update QuickBooks settings."""
        test_user = create_test_user(user_type=UserType.TENANT, is_admin=True)
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_integration = create_mock_integration(connected=True, with_settings=True)

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration, \
             patch('Backend.api.quickbooks.router.flag_modified') as mock_flag:
            mock_get_integration.return_value = mock_integration

            with TestClientWithHost(app) as client:
                response = client.put("/api/quickbooks/settings", json={"auto_sync_enabled": False})

                # Admins should be allowed
                assert response.status_code == 200


class TestSettingsConnectionHealth:
    """Tests for connection health information in settings response."""

    def test_connection_health_with_recent_sync(self):
        """Test connection health shows recent sync information."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_integration = create_mock_integration(connected=True, with_settings=True)
        mock_integration.last_sync_at = FIXED_DATETIME
        mock_integration.error_count = 0
        mock_integration.last_error = None

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration:
            mock_get_integration.return_value = mock_integration

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/settings")

                data = assert_valid_json_response(response, dict)

                health = data["connection_health"]
                assert health["last_sync_at"] is not None
                assert health["error_count"] == 0
                assert health["last_error"] is None

    def test_connection_health_with_errors(self):
        """Test connection health shows error information."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_integration = create_mock_integration(connected=True, with_settings=True)
        mock_integration.error_count = 3
        mock_integration.last_error = "Rate limit exceeded"

        with patch('Backend.api.quickbooks.router.get_user_integration') as mock_get_integration:
            mock_get_integration.return_value = mock_integration

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/settings")

                data = assert_valid_json_response(response, dict)

                health = data["connection_health"]
                assert health["error_count"] == 3
                assert health["last_error"] == "Rate limit exceeded"
