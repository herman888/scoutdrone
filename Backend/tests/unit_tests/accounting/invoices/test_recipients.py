"""
Unit tests for invoice recipient resolution logic.

Tests recipient snapshot creation for all recipient types:
- Tenants (Individual and Company)
- Ownership Entities
- Vendors
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from Backend.api.accounting.invoices.recipients import (
    resolve_recipient_snapshot,
    _resolve_tenant_snapshot,
    _resolve_ownership_entity_snapshot,
    _resolve_vendor_snapshot
)
from Backend.api.accounting.invoices.schemas import InvoiceCreate
from Backend.models.tenant import Tenant
from Backend.models.ownership_entity import OwnershipEntity
from Backend.models.vendor import Vendor
from Backend.models.enums import TenantType


class TestResolveTenantSnapshot:
    """Test tenant recipient snapshot resolution."""

    @pytest.mark.asyncio
    async def test_resolve_individual_tenant(self):
        """Test snapshot resolution for individual tenant."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=1,
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            tenant_type=TenantType.INDIVIDUAL
        )
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_tenant_snapshot(mock_session, tenant_id=1)
        
        # Assert
        assert snapshot['recipient_name'] == "John Doe"
        assert snapshot['recipient_email'] == "john.doe@example.com"
        assert 'recipient_company' not in snapshot

    @pytest.mark.asyncio
    async def test_resolve_company_tenant(self):
        """Test snapshot resolution for company tenant."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=2,
            first_name="Jane",
            last_name="Smith",
            company_name="Acme Corp",
            email="jane@acmecorp.com",
            tenant_type=TenantType.COMPANY
        )
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_tenant_snapshot(mock_session, tenant_id=2)
        
        # Assert
        assert snapshot['recipient_name'] == "Acme Corp"
        assert snapshot['recipient_company'] == "Acme Corp"
        assert snapshot['recipient_email'] == "jane@acmecorp.com"

    @pytest.mark.asyncio
    async def test_resolve_company_tenant_no_company_name(self):
        """Test snapshot resolution for company tenant without company_name."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=3,
            first_name="Bob",
            last_name="Builder",
            company_name=None,
            email="bob@example.com",
            tenant_type=TenantType.COMPANY
        )
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_tenant_snapshot(mock_session, tenant_id=3)
        
        # Assert
        assert snapshot['recipient_name'] == "Company Tenant"
        assert snapshot['recipient_company'] is None

    @pytest.mark.asyncio
    async def test_resolve_tenant_missing_names(self):
        """Test snapshot resolution for tenant with missing name fields."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=4,
            first_name=None,
            last_name=None,
            email="unknown@example.com",
            tenant_type=TenantType.INDIVIDUAL
        )
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_tenant_snapshot(mock_session, tenant_id=4)
        
        # Assert
        assert snapshot['recipient_name'] == "Tenant"  # Fallback
        assert snapshot['recipient_email'] == "unknown@example.com"

    @pytest.mark.asyncio
    async def test_resolve_tenant_not_found(self):
        """Test snapshot resolution when tenant doesn't exist."""
        # Arrange
        mock_session = AsyncMock()
        
        # Mock the database query to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_tenant_snapshot(mock_session, tenant_id=999)
        
        # Assert
        assert snapshot == {}

    @pytest.mark.asyncio
    async def test_resolve_tenant_no_email(self):
        """Test snapshot resolution for tenant without email."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=5,
            first_name="Alice",
            last_name="Wonder",
            email=None,
            tenant_type=TenantType.INDIVIDUAL
        )
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_tenant_snapshot(mock_session, tenant_id=5)
        
        # Assert
        assert snapshot['recipient_name'] == "Alice Wonder"
        assert snapshot['recipient_email'] is None


class TestResolveOwnershipEntitySnapshot:
    """Test ownership entity recipient snapshot resolution."""

    @pytest.mark.asyncio
    async def test_resolve_ownership_entity_complete(self):
        """Test snapshot resolution for ownership entity with complete data."""
        # Arrange
        mock_session = AsyncMock()
        entity_id = uuid4()
        entity = OwnershipEntity(
            id=entity_id,
            name="Main Street Properties LLC",
            legal_name="Main Street Properties Limited Liability Company",
            contact_email="contact@mainstreet.com",
            address="123 Main St, Suite 100",
            city="Toronto",
            province="ON",
            postal_code="M5V 1A1",
            country="Canada",
            tax_id="123456789RT0001"
        )
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_ownership_entity_snapshot(mock_session, entity_id)
        
        # Assert
        assert snapshot['recipient_name'] == "Main Street Properties LLC"
        assert snapshot['recipient_company'] == "Main Street Properties Limited Liability Company"
        assert snapshot['recipient_email'] == "contact@mainstreet.com"
        assert snapshot['recipient_address_line1'] == "123 Main St, Suite 100"
        assert snapshot['recipient_city'] == "Toronto"
        assert snapshot['recipient_province'] == "ON"
        assert snapshot['recipient_postal_code'] == "M5V 1A1"
        assert snapshot['recipient_country'] == "Canada"
        assert snapshot['recipient_tax_number'] == "123456789RT0001"

    @pytest.mark.asyncio
    async def test_resolve_ownership_entity_minimal(self):
        """Test snapshot resolution for ownership entity with minimal data."""
        # Arrange
        mock_session = AsyncMock()
        entity_id = uuid4()
        entity = OwnershipEntity(
            id=entity_id,
            name="Simple Holdings",
            legal_name=None,
            contact_email="info@simple.com",
            address=None,
            city=None,
            province=None,
            postal_code=None,
            country=None,
            tax_id=None
        )
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_ownership_entity_snapshot(mock_session, entity_id)
        
        # Assert
        assert snapshot['recipient_name'] == "Simple Holdings"
        assert snapshot['recipient_company'] == "Simple Holdings"  # Falls back to name
        assert snapshot['recipient_email'] == "info@simple.com"
        assert snapshot['recipient_country'] == "Canada"  # Default
        assert snapshot['recipient_address_line1'] is None
        assert snapshot['recipient_tax_number'] is None

    @pytest.mark.asyncio
    async def test_resolve_ownership_entity_not_found(self):
        """Test snapshot resolution when ownership entity doesn't exist."""
        # Arrange
        mock_session = AsyncMock()
        entity_id = uuid4()
        
        # Mock the database query to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_ownership_entity_snapshot(mock_session, entity_id)
        
        # Assert
        assert snapshot == {}

    @pytest.mark.asyncio
    async def test_resolve_ownership_entity_no_email(self):
        """Test snapshot resolution for ownership entity without email."""
        # Arrange
        mock_session = AsyncMock()
        entity_id = uuid4()
        entity = OwnershipEntity(
            id=entity_id,
            name="Property Group",
            legal_name="Property Group Inc",
            contact_email=None,
            address="456 Oak Ave",
            city="Vancouver",
            province="BC",
            postal_code="V6B 1A1",
            country="Canada",
            tax_id=None
        )
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_ownership_entity_snapshot(mock_session, entity_id)
        
        # Assert
        assert snapshot['recipient_name'] == "Property Group"
        assert snapshot['recipient_email'] is None
        assert snapshot['recipient_address_line1'] == "456 Oak Ave"


class TestResolveVendorSnapshot:
    """Test vendor recipient snapshot resolution."""

    @pytest.mark.asyncio
    async def test_resolve_vendor_complete(self):
        """Test snapshot resolution for vendor with complete data."""
        # Arrange
        mock_session = AsyncMock()
        vendor = MagicMock()
        vendor.id = 1
        vendor.company_name = "ABC Maintenance Services"
        vendor.contact_person = "Mike Johnson"
        vendor.email = "mike@abcmaintenance.com"
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = vendor
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_vendor_snapshot(mock_session, vendor_id=1)
        
        # Assert
        assert snapshot['recipient_name'] == "Mike Johnson"
        assert snapshot['recipient_company'] == "ABC Maintenance Services"
        assert snapshot['recipient_email'] == "mike@abcmaintenance.com"

    @pytest.mark.asyncio
    async def test_resolve_vendor_no_contact_person(self):
        """Test snapshot resolution for vendor without contact person."""
        # Arrange
        mock_session = AsyncMock()
        vendor = MagicMock()
        vendor.id = 2
        vendor.company_name = "XYZ Plumbing"
        vendor.contact_person = None
        vendor.email = "info@xyzplumbing.com"
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = vendor
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_vendor_snapshot(mock_session, vendor_id=2)
        
        # Assert
        assert snapshot['recipient_name'] == "XYZ Plumbing"  # Falls back to company
        assert snapshot['recipient_company'] == "XYZ Plumbing"
        assert snapshot['recipient_email'] == "info@xyzplumbing.com"

    @pytest.mark.asyncio
    async def test_resolve_vendor_not_found(self):
        """Test snapshot resolution when vendor doesn't exist."""
        # Arrange
        mock_session = AsyncMock()
        
        # Mock the database query to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_vendor_snapshot(mock_session, vendor_id=999)
        
        # Assert
        assert snapshot == {}

    @pytest.mark.asyncio
    async def test_resolve_vendor_no_email(self):
        """Test snapshot resolution for vendor without email."""
        # Arrange
        mock_session = AsyncMock()
        vendor = MagicMock()
        vendor.id = 3
        vendor.company_name = "Quick Repairs"
        vendor.contact_person = "Sarah Lee"
        vendor.email = None
        
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = vendor
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_vendor_snapshot(mock_session, vendor_id=3)
        
        # Assert
        assert snapshot['recipient_name'] == "Sarah Lee"
        assert snapshot['recipient_company'] == "Quick Repairs"
        assert snapshot['recipient_email'] is None


class TestResolveRecipientSnapshot:
    """Test main recipient snapshot resolution function."""

    @pytest.mark.asyncio
    async def test_resolve_tenant_recipient(self):
        """Test resolution for tenant recipient type."""
        # Arrange
        mock_session = AsyncMock()
        invoice_data = MagicMock(spec=InvoiceCreate)
        invoice_data.recipient_type = 'tenant'
        invoice_data.tenant_id = 1
        invoice_data.ownership_entity_id = None
        invoice_data.vendor_id = None
        
        tenant = Tenant(
            id=1,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            tenant_type=TenantType.INDIVIDUAL
        )
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await resolve_recipient_snapshot(mock_session, invoice_data)
        
        # Assert
        assert snapshot['recipient_name'] == "John Doe"
        assert snapshot['recipient_email'] == "john@example.com"

    @pytest.mark.asyncio
    async def test_resolve_ownership_entity_recipient(self):
        """Test resolution for ownership entity recipient type."""
        # Arrange
        mock_session = AsyncMock()
        entity_id = uuid4()
        invoice_data = MagicMock(spec=InvoiceCreate)
        invoice_data.recipient_type = 'ownership_entity'
        invoice_data.tenant_id = None
        invoice_data.ownership_entity_id = entity_id
        invoice_data.vendor_id = None
        
        entity = OwnershipEntity(
            id=entity_id,
            name="Property Holdings LLC",
            legal_name="Property Holdings LLC",
            contact_email="contact@holdings.com",
            address="789 Business Blvd",
            city="Calgary",
            province="AB",
            postal_code="T2P 1A1",
            country="Canada",
            tax_id="987654321RT0001"
        )
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await resolve_recipient_snapshot(mock_session, invoice_data)
        
        # Assert
        assert snapshot['recipient_name'] == "Property Holdings LLC"
        assert snapshot['recipient_company'] == "Property Holdings LLC"
        assert snapshot['recipient_email'] == "contact@holdings.com"
        assert snapshot['recipient_address_line1'] == "789 Business Blvd"
        assert snapshot['recipient_tax_number'] == "987654321RT0001"

    @pytest.mark.asyncio
    async def test_resolve_vendor_recipient(self):
        """Test resolution for vendor recipient type."""
        # Arrange
        mock_session = AsyncMock()
        invoice_data = MagicMock(spec=InvoiceCreate)
        invoice_data.recipient_type = 'vendor'
        invoice_data.tenant_id = None
        invoice_data.ownership_entity_id = None
        invoice_data.vendor_id = 5
        
        vendor = MagicMock()
        vendor.id = 5
        vendor.company_name = "Electrical Services Inc"
        vendor.contact_person = "Tom Electric"
        vendor.email = "tom@electrical.com"
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = vendor
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await resolve_recipient_snapshot(mock_session, invoice_data)
        
        # Assert
        assert snapshot['recipient_name'] == "Tom Electric"
        assert snapshot['recipient_company'] == "Electrical Services Inc"
        assert snapshot['recipient_email'] == "tom@electrical.com"

    @pytest.mark.asyncio
    async def test_resolve_no_recipient_type(self):
        """Test resolution when no recipient type is specified."""
        # Arrange
        mock_session = AsyncMock()
        invoice_data = MagicMock(spec=InvoiceCreate)
        invoice_data.recipient_type = None
        invoice_data.tenant_id = None
        invoice_data.ownership_entity_id = None
        invoice_data.vendor_id = None
        
        # Act
        snapshot = await resolve_recipient_snapshot(mock_session, invoice_data)
        
        # Assert
        assert snapshot == {}

    @pytest.mark.asyncio
    async def test_resolve_unknown_recipient_type(self):
        """Test resolution with unknown recipient type."""
        # Arrange
        mock_session = AsyncMock()
        invoice_data = MagicMock(spec=InvoiceCreate)
        invoice_data.recipient_type = 'unknown_type'
        invoice_data.tenant_id = None
        invoice_data.ownership_entity_id = None
        invoice_data.vendor_id = None
        
        # Act
        snapshot = await resolve_recipient_snapshot(mock_session, invoice_data)
        
        # Assert
        assert snapshot == {}

    @pytest.mark.asyncio
    async def test_resolve_tenant_no_tenant_id(self):
        """Test resolution for tenant type without tenant_id."""
        # Arrange
        mock_session = AsyncMock()
        invoice_data = MagicMock(spec=InvoiceCreate)
        invoice_data.recipient_type = 'tenant'
        invoice_data.tenant_id = None
        invoice_data.ownership_entity_id = None
        invoice_data.vendor_id = None
        
        # Act
        snapshot = await resolve_recipient_snapshot(mock_session, invoice_data)
        
        # Assert
        assert snapshot == {}

    @pytest.mark.asyncio
    async def test_resolve_ownership_entity_no_id(self):
        """Test resolution for ownership entity type without ID."""
        # Arrange
        mock_session = AsyncMock()
        invoice_data = MagicMock(spec=InvoiceCreate)
        invoice_data.recipient_type = 'ownership_entity'
        invoice_data.tenant_id = None
        invoice_data.ownership_entity_id = None
        invoice_data.vendor_id = None
        
        # Act
        snapshot = await resolve_recipient_snapshot(mock_session, invoice_data)
        
        # Assert
        assert snapshot == {}

    @pytest.mark.asyncio
    async def test_resolve_vendor_no_vendor_id(self):
        """Test resolution for vendor type without vendor_id."""
        # Arrange
        mock_session = AsyncMock()
        invoice_data = MagicMock(spec=InvoiceCreate)
        invoice_data.recipient_type = 'vendor'
        invoice_data.tenant_id = None
        invoice_data.ownership_entity_id = None
        invoice_data.vendor_id = None
        
        # Act
        snapshot = await resolve_recipient_snapshot(mock_session, invoice_data)
        
        # Assert
        assert snapshot == {}


class TestRecipientsEdgeCases:
    """Additional edge case tests for recipient resolution."""

    @pytest.mark.asyncio
    async def test_resolve_tenant_with_special_characters_in_name(self):
        """Test tenant name with special characters."""
        # Arrange
        mock_session = AsyncMock()
        tenant = Tenant(
            id=10,
            first_name="Jean-Pierre",
            last_name="O'Connor",
            email="jp@example.com",
            tenant_type=TenantType.INDIVIDUAL
        )
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tenant
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_tenant_snapshot(mock_session, tenant_id=10)
        
        # Assert
        assert snapshot['recipient_name'] == "Jean-Pierre O'Connor"

    @pytest.mark.asyncio
    async def test_resolve_ownership_entity_canadian_address(self):
        """Test ownership entity with complete Canadian address."""
        # Arrange
        mock_session = AsyncMock()
        entity_id = uuid4()
        entity = OwnershipEntity(
            id=entity_id,
            name="Toronto Holdings",
            legal_name="Toronto Holdings Inc.",
            contact_email="info@toronto.ca",
            address="100 Queen St W",
            city="Toronto",
            province="ON",
            postal_code="M5H 2N2",
            country="Canada",
            tax_id="123456789RT0001"
        )
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        # Act
        snapshot = await _resolve_ownership_entity_snapshot(mock_session, entity_id)
        
        # Assert
        assert snapshot['recipient_postal_code'] == "M5H 2N2"
        assert snapshot['recipient_province'] == "ON"
