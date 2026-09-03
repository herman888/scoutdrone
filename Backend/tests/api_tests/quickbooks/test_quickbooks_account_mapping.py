"""
API tests for QuickBooks account mapping endpoints.

Tests CRUD operations for managing mappings between Brikli tax types
(GST, HST, PST, QST) and QuickBooks account IDs.
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


def create_mock_mapping(mapping_id=1, brikli_key="GST", qb_account_id="123"):
    """Helper to create a mock account mapping."""
    mock_mapping = MagicMock()
    mock_mapping.id = mapping_id
    mock_mapping.mapping_type = "tax_account"
    mock_mapping.brikli_key = brikli_key
    mock_mapping.quickbooks_account_id = qb_account_id
    mock_mapping.quickbooks_account_name = f"{brikli_key} Payable"
    mock_mapping.quickbooks_account_type = "Other Current Liability"
    mock_mapping.created_at = FIXED_DATETIME
    mock_mapping.updated_at = FIXED_DATETIME
    return mock_mapping


class TestGetAccountMappings:
    """Tests for GET /api/quickbooks/accounts/mappings endpoint."""

    def test_get_mappings_success(self):
        """Test successful retrieval of account mappings."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        mock_mappings = [
            create_mock_mapping(1, "GST", "101"),
            create_mock_mapping(2, "PST", "102"),
        ]

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_all_mappings.return_value = mock_mappings
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/accounts/mappings")

                data = assert_valid_json_response(response, list)
                assert len(data) == 2

                # Check first mapping structure
                mapping = data[0]
                assert "id" in mapping
                assert "mapping_type" in mapping
                assert "brikli_key" in mapping
                assert "quickbooks_account_id" in mapping
                assert "quickbooks_account_name" in mapping
                assert "created_at" in mapping
                assert "updated_at" in mapping

    def test_get_mappings_empty(self):
        """Test retrieval when no mappings exist."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_all_mappings.return_value = []
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/accounts/mappings")

                data = assert_valid_json_response(response, list)
                assert len(data) == 0

    def test_get_mappings_permission_denied_tenant(self):
        """Test that tenants cannot access account mappings."""
        test_user = create_test_user(user_type=UserType.TENANT)
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with TestClientWithHost(app) as client:
            response = client.get("/api/quickbooks/accounts/mappings")

            assert response.status_code == 403
            data = response.json()
            assert "landlord" in data["detail"].lower() or "admin" in data["detail"].lower()

    def test_get_mappings_admin_allowed(self):
        """Test that admins can access account mappings."""
        test_user = create_test_user(user_type=UserType.TENANT, is_admin=True)
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_all_mappings.return_value = []
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/accounts/mappings")

                assert response.status_code == 200


class TestSaveAccountMapping:
    """Tests for POST /api/quickbooks/accounts/mappings endpoint."""

    def test_save_mapping_success(self):
        """Test successful creation of account mapping."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        saved_mapping = create_mock_mapping(1, "GST", "101")

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.save_account_mapping.return_value = saved_mapping
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                payload = {
                    "mapping_type": "tax_account",
                    "brikli_key": "GST",
                    "quickbooks_account_id": "101",
                    "quickbooks_account_name": "GST Payable",
                    "quickbooks_account_type": "Other Current Liability"
                }

                response = client.post("/api/quickbooks/accounts/mappings", json=payload)

                data = assert_valid_json_response(response, dict)
                assert data["id"] == 1
                assert data["brikli_key"] == "GST"
                assert data["quickbooks_account_id"] == "101"

    def test_save_mapping_update_existing(self):
        """Test updating an existing account mapping."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        # Updated mapping with new account ID
        updated_mapping = create_mock_mapping(1, "GST", "999")

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.save_account_mapping.return_value = updated_mapping
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                payload = {
                    "mapping_type": "tax_account",
                    "brikli_key": "GST",
                    "quickbooks_account_id": "999",
                    "quickbooks_account_name": "GST Payable Updated",
                    "quickbooks_account_type": "Other Current Liability"
                }

                response = client.post("/api/quickbooks/accounts/mappings", json=payload)

                data = assert_valid_json_response(response, dict)
                assert data["quickbooks_account_id"] == "999"

    def test_save_mapping_permission_denied_tenant(self):
        """Test that tenants cannot create account mappings."""
        test_user = create_test_user(user_type=UserType.TENANT)
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with TestClientWithHost(app) as client:
            payload = {
                "mapping_type": "tax_account",
                "brikli_key": "GST",
                "quickbooks_account_id": "101",
                "quickbooks_account_name": "GST Payable"
            }

            response = client.post("/api/quickbooks/accounts/mappings", json=payload)

            assert response.status_code == 403

    def test_save_mapping_missing_required_fields(self):
        """Test validation error for missing required fields."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with TestClientWithHost(app) as client:
            # Missing brikli_key
            payload = {
                "mapping_type": "tax_account",
                "quickbooks_account_id": "101",
                "quickbooks_account_name": "GST Payable"
            }

            response = client.post("/api/quickbooks/accounts/mappings", json=payload)

            # Should return validation error
            assert response.status_code == 422


class TestAutoDetectMappings:
    """Tests for POST /api/quickbooks/accounts/mappings/auto-detect endpoint."""

    def test_auto_detect_success(self):
        """Test successful auto-detection of tax accounts."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        detected = {
            "GST": {"id": "101", "name": "GST Payable", "type": "Other Current Liability"},
            "PST": {"id": "102", "name": "PST Payable", "type": "Other Current Liability"},
        }

        saved_mappings = [
            create_mock_mapping(1, "GST", "101"),
            create_mock_mapping(2, "PST", "102"),
        ]

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.auto_detect_tax_accounts.return_value = detected
            mock_service.save_auto_detected_mappings.return_value = saved_mappings
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post("/api/quickbooks/accounts/mappings/auto-detect")

                data = assert_valid_json_response(response, dict)

                assert "detected" in data
                assert "saved" in data
                assert len(data["detected"]) == 2
                assert len(data["saved"]) == 2

    def test_auto_detect_no_matches(self):
        """Test auto-detection when no matching accounts are found."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.auto_detect_tax_accounts.return_value = {}
            mock_service.save_auto_detected_mappings.return_value = []
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.post("/api/quickbooks/accounts/mappings/auto-detect")

                data = assert_valid_json_response(response, dict)

                assert len(data["detected"]) == 0
                assert len(data["saved"]) == 0

    def test_auto_detect_permission_denied_tenant(self):
        """Test that tenants cannot auto-detect account mappings."""
        test_user = create_test_user(user_type=UserType.TENANT)
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with TestClientWithHost(app) as client:
            response = client.post("/api/quickbooks/accounts/mappings/auto-detect")

            assert response.status_code == 403


class TestDeleteAccountMapping:
    """Tests for DELETE /api/quickbooks/accounts/mappings/{mapping_id} endpoint."""

    def test_delete_mapping_success(self):
        """Test successful deletion of account mapping."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.delete_account_mapping.return_value = True
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.delete("/api/quickbooks/accounts/mappings/1")

                data = assert_valid_json_response(response, dict)
                assert data["status"] == "success"
                assert "deleted" in data["message"].lower()

    def test_delete_mapping_not_found(self):
        """Test deletion of non-existent mapping."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.delete_account_mapping.return_value = False
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.delete("/api/quickbooks/accounts/mappings/999")

                assert response.status_code == 404
                data = response.json()
                assert "not found" in data["detail"].lower()

    def test_delete_mapping_permission_denied_tenant(self):
        """Test that tenants cannot delete account mappings."""
        test_user = create_test_user(user_type=UserType.TENANT)
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with TestClientWithHost(app) as client:
            response = client.delete("/api/quickbooks/accounts/mappings/1")

            assert response.status_code == 403


class TestGetTaxEligibleAccounts:
    """Tests for GET /api/quickbooks/accounts/tax-eligible endpoint."""

    def test_get_tax_eligible_accounts_success(self):
        """Test successful retrieval of tax-eligible accounts."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        tax_accounts = [
            {"id": "101", "name": "GST Payable", "account_type": "Other Current Liability", "active": True},
            {"id": "102", "name": "PST Payable", "account_type": "Other Current Liability", "active": True},
        ]

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_tax_accounts.return_value = tax_accounts
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/accounts/tax-eligible")

                data = assert_valid_json_response(response, list)
                assert len(data) == 2

                account = data[0]
                assert "id" in account
                assert "name" in account
                assert "account_type" in account
                assert "active" in account

    def test_get_tax_eligible_accounts_empty(self):
        """Test retrieval when no tax-eligible accounts exist."""
        test_user = create_test_user()
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with patch('Backend.api.quickbooks.router.AccountMappingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_tax_accounts.return_value = []
            mock_service_class.return_value = mock_service

            with TestClientWithHost(app) as client:
                response = client.get("/api/quickbooks/accounts/tax-eligible")

                data = assert_valid_json_response(response, list)
                assert len(data) == 0

    def test_get_tax_eligible_accounts_permission_denied_tenant(self):
        """Test that tenants cannot access tax-eligible accounts."""
        test_user = create_test_user(user_type=UserType.TENANT)
        mock_session = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[get_session] = lambda: mock_session

        with TestClientWithHost(app) as client:
            response = client.get("/api/quickbooks/accounts/tax-eligible")

            assert response.status_code == 403
