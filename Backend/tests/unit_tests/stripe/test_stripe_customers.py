"""
Unit tests for Stripe customer management.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi import HTTPException

from Backend.api.stripe.customers import get_or_create_stripe_customer
from Backend.models.tenant import Tenant
from Backend.models.vendor import Vendor
from Backend.models.ownership_entity import OwnershipEntity


class TestGetOrCreateStripeCustomer:
    """Test Stripe customer creation and retrieval."""

    @pytest.mark.asyncio
    async def test_get_existing_stripe_customer_tenant(self):
        """Test retrieving existing Stripe customer for tenant."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=1,
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            stripe_customer_id="cus_existing123"
        )
        
        # Act
        result = await get_or_create_stripe_customer(tenant, mock_session)
        
        # Assert
        assert result == "cus_existing123"

    @pytest.mark.asyncio
    @patch('Backend.api.stripe.customers.get_stripe_client')
    async def test_create_new_stripe_customer_tenant(self, mock_get_client):
        """Test creating new Stripe customer for tenant."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=1,
            email="newuser@example.com",
            first_name="John",
            last_name="Doe",
            stripe_customer_id=None
        )
        
        mock_customer = MagicMock()
        mock_customer.id = "cus_new456"
        
        mock_stripe_client = AsyncMock()
        mock_stripe_client.customers.create = AsyncMock(return_value=mock_customer)
        mock_get_client.return_value = mock_stripe_client
        
        # Act
        result = await get_or_create_stripe_customer(tenant, mock_session)
        
        # Assert
        assert result == "cus_new456"
        assert tenant.stripe_customer_id == "cus_new456"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch('Backend.api.stripe.customers.get_stripe_client')
    async def test_create_vendor_customer(self, mock_get_client):
        """Test creating Stripe customer for vendor."""
        # Arrange
        mock_session = AsyncMock()
        vendor = Vendor(
            id=1,
            company_name="ABC Plumbing",
            email="vendor@abc.com",
            trade_category="Plumbing",
            stripe_customer_id=None
        )
        
        mock_customer = MagicMock()
        mock_customer.id = "cus_vendor123"
        
        mock_stripe_client = AsyncMock()
        mock_stripe_client.customers.create = AsyncMock(return_value=mock_customer)
        mock_get_client.return_value = mock_stripe_client
        
        # Act
        result = await get_or_create_stripe_customer(vendor, mock_session)
        
        # Assert
        assert result == "cus_vendor123"
        call_args = mock_stripe_client.customers.create.call_args
        assert call_args.kwargs['email'] == "vendor@abc.com"
        assert call_args.kwargs['name'] == "ABC Plumbing"

    @pytest.mark.asyncio
    @patch('Backend.api.stripe.customers.get_stripe_client')
    async def test_create_ownership_entity_customer(self, mock_get_client):
        """Test creating Stripe customer for ownership entity."""
        # Arrange
        mock_session = AsyncMock()
        entity = OwnershipEntity(
            id=uuid4(),
            name="Property Holdings LLC",
            contact_email="contact@holdings.com",
            entity_type="LLC",
            stripe_customer_id=None
        )
        
        mock_customer = MagicMock()
        mock_customer.id = "cus_entity456"
        
        mock_stripe_client = AsyncMock()
        mock_stripe_client.customers.create = AsyncMock(return_value=mock_customer)
        mock_get_client.return_value = mock_stripe_client
        
        # Act
        result = await get_or_create_stripe_customer(entity, mock_session)
        
        # Assert
        assert result == "cus_entity456"

    @pytest.mark.asyncio
    async def test_error_when_tenant_missing_email(self):
        """Test error when tenant has no email."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=1,
            email=None,
            first_name="John",
            last_name="Doe",
            stripe_customer_id=None
        )
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_or_create_stripe_customer(tenant, mock_session)
        
        assert exc_info.value.status_code == 400
        assert "email" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_error_when_tenant_missing_name(self):
        """Test error when tenant has no name."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=1,
            email="test@example.com",
            first_name=None,
            last_name=None,
            stripe_customer_id=None
        )
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_or_create_stripe_customer(tenant, mock_session)
        
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_duplicate_customer_creation(self):
        """Test that existing customer ID prevents duplicate creation."""
        # Arrange
        mock_session = AsyncMock()
        existing_id = "cus_existing999"
        tenant = Tenant(
            id=1,
            email="existing@example.com",
            first_name="Jane",
            last_name="Doe",
            stripe_customer_id=existing_id
        )
        
        with patch('Backend.api.stripe.customers.get_stripe_client') as mock_get_client:
            # Act
            result = await get_or_create_stripe_customer(tenant, mock_session)
            
            # Assert
            assert result == existing_id
            mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    @patch('Backend.api.stripe.customers.get_stripe_client')
    async def test_tenant_with_company_name(self, mock_get_client):
        """Test tenant with company name uses company name."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=1,
            email="company@example.com",
            first_name="John",
            last_name="Doe",
            company_name="Acme Corp",
            stripe_customer_id=None
        )
        
        mock_customer = MagicMock()
        mock_customer.id = "cus_company123"
        
        mock_stripe_client = AsyncMock()
        mock_stripe_client.customers.create = AsyncMock(return_value=mock_customer)
        mock_get_client.return_value = mock_stripe_client
        
        # Act
        result = await get_or_create_stripe_customer(tenant, mock_session)
        
        # Assert
        call_args = mock_stripe_client.customers.create.call_args
        assert call_args.kwargs['name'] == "Acme Corp"

    @pytest.mark.asyncio
    @patch('Backend.api.stripe.customers.get_stripe_client')
    async def test_metadata_includes_brikli_info(self, mock_get_client):
        """Test that metadata includes Brikli platform info."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=5,
            email="test@example.com",
            first_name="Test",
            last_name="User",
            stripe_customer_id=None
        )
        
        mock_customer = MagicMock()
        mock_customer.id = "cus_metadata"
        
        mock_stripe_client = AsyncMock()
        mock_stripe_client.customers.create = AsyncMock(return_value=mock_customer)
        mock_get_client.return_value = mock_stripe_client
        
        # Act
        await get_or_create_stripe_customer(tenant, mock_session)
        
        # Assert
        call_args = mock_stripe_client.customers.create.call_args
        metadata = call_args.kwargs['metadata']
        assert metadata['brikli_platform'] == "true"
        assert metadata['brikli_recipient_type'] == "tenant"
        assert metadata['brikli_recipient_id'] == "5"
