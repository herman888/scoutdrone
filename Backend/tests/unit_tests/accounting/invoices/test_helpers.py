"""
Unit tests for invoice helper functions.

Tests authorization checks, filtering logic, and invoice response building.
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from Backend.api.accounting.invoices.helpers import (
    check_invoice_ownership,
    build_invoice_response,
    infer_property_for_invoice,
    apply_tenant_invoice_filters,
    apply_landlord_invoice_filters,
    apply_admin_invoice_filters
)
from Backend.models.accounting.invoice import Invoice, InvoiceDeliveryMethod
from Backend.models.accounting.common import PaymentStatus
from Backend.models.user import User
from Backend.models.tenant import Tenant
from Backend.models.property import Property
from Backend.models.lease import Lease, LeaseStatus
from Backend.models.ownership_entity import OwnershipEntity
from Backend.models.vendor import Vendor
from Backend.models.enums import UserType


class TestCheckInvoiceOwnership:
    """Test invoice ownership verification."""

    @pytest.mark.asyncio
    async def test_admin_can_access_any_invoice(self):
        """Test that admin users can access any invoice."""
        # Arrange
        mock_session = AsyncMock()
        admin_user = User(id=str(uuid4()), user_type=UserType.ADMIN)
        invoice = Invoice(
            id=1,
            tenant_id=5,
            property_id=10,
            amount=Decimal('1000.00'),
            invoice_number="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1)
        )
        
        # Act & Assert - should not raise exception
        await check_invoice_ownership(invoice, admin_user, mock_session)

    @pytest.mark.asyncio
    async def test_tenant_can_access_own_invoice(self):
        """Test that tenant can access their own invoice."""
        # Arrange
        mock_session = AsyncMock()
        tenant_user = User(id=str(uuid4()), user_type=UserType.TENANT)
        
        tenant = Tenant(id=5, user_id=tenant_user.id)
        invoice = Invoice(
            id=1,
            tenant_id=5,
            property_id=10,
            amount=Decimal('1000.00'),
            invoice_number="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1)
        )
        
        # Mock database query
        mock_session.scalar = AsyncMock(return_value=tenant)
        
        # Act & Assert - should not raise exception
        await check_invoice_ownership(invoice, tenant_user, mock_session)

    @pytest.mark.asyncio
    async def test_tenant_cannot_access_other_invoice(self):
        """Test that tenant cannot access another tenant's invoice."""
        # Arrange
        mock_session = AsyncMock()
        tenant_user = User(id=str(uuid4()), user_type=UserType.TENANT)
        
        tenant = Tenant(id=5, user_id=tenant_user.id)
        invoice = Invoice(
            id=1,
            tenant_id=99,  # Different tenant
            property_id=10,
            amount=Decimal('1000.00'),
            invoice_number="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1)
        )
        
        # Mock database query
        mock_session.scalar = AsyncMock(return_value=tenant)
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await check_invoice_ownership(invoice, tenant_user, mock_session)
        
        assert exc_info.value.status_code == 403
        assert "Not authorized" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_tenant_with_no_tenant_record_denied(self):
        """Test that tenant user without tenant record is denied."""
        # Arrange
        mock_session = AsyncMock()
        tenant_user = User(id=str(uuid4()), user_type=UserType.TENANT)
        
        invoice = Invoice(
            id=1,
            tenant_id=5,
            property_id=10,
            amount=Decimal('1000.00'),
            invoice_number="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1)
        )
        
        # Mock database query - no tenant found
        mock_session.scalar = AsyncMock(return_value=None)
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await check_invoice_ownership(invoice, tenant_user, mock_session)
        
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_landlord_can_access_own_property_invoice(self):
        """Test that landlord can access invoices for their properties."""
        # Arrange
        mock_session = AsyncMock()
        landlord_user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        property_obj = Property(id=10, user_id=landlord_user.id)
        invoice = Invoice(
            id=1,
            tenant_id=5,
            property_id=10,
            amount=Decimal('1000.00'),
            invoice_number="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1)
        )
        
        # Mock database query
        mock_session.scalar = AsyncMock(return_value=property_obj)
        
        # Act & Assert - should not raise exception
        await check_invoice_ownership(invoice, landlord_user, mock_session)

    @pytest.mark.asyncio
    async def test_landlord_cannot_access_other_property_invoice(self):
        """Test that landlord cannot access invoices for other properties."""
        # Arrange
        mock_session = AsyncMock()
        landlord_user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        other_user_id = str(uuid4())
        
        invoice = Invoice(
            id=1,
            tenant_id=5,
            property_id=10,
            amount=Decimal('1000.00'),
            invoice_number="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1)
        )
        
        # Mock database query - property not owned by landlord
        mock_session.scalar = AsyncMock(return_value=None)
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await check_invoice_ownership(invoice, landlord_user, mock_session)
        
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_landlord_can_access_invoice_with_null_property(self):
        """Test that landlord can access invoices with NULL property_id."""
        # Arrange
        mock_session = AsyncMock()
        landlord_user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        invoice = Invoice(
            id=1,
            tenant_id=5,
            property_id=None,  # Unassigned invoice
            amount=Decimal('1000.00'),
            invoice_number="INV-001",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1)
        )
        
        # Act & Assert - should not raise exception (no query needed for NULL property)
        await check_invoice_ownership(invoice, landlord_user, mock_session)


class TestBuildInvoiceResponse:
    """Test invoice response building."""

    def test_build_basic_invoice_response(self):
        """Test building response for basic invoice."""
        # Arrange
        invoice = Invoice(
            id=1,
            invoice_number="INV-001",
            amount=Decimal('1000.00'),
            description="Monthly rent",
            issue_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            status=PaymentStatus.PENDING,
            delivery_method=InvoiceDeliveryMethod.SEND_INVOICE,
            property_id=10,
            unit_id=5,
            tenant_id=3,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        invoice.line_items = []
        invoice.taxes = []
        invoice.property = None
        invoice.tenant = None
        
        # Act
        response = build_invoice_response(invoice)
        
        # Assert
        assert response['id'] == 1
        assert response['invoice_number'] == "INV-001"
        assert response['amount'] == Decimal('1000.00')
        assert response['description'] == "Monthly rent"
        assert response['issue_date'] == "2024-01-15"
        assert response['due_date'] == "2024-02-15"
        assert response['status'] == "Pending"
        assert response['delivery_method'] == "send_invoice"
        assert response['property_id'] == 10
        assert response['unit_id'] == 5
        assert response['tenant_id'] == 3
        assert response['line_items'] == []
        assert response['taxes'] == []

    def test_build_response_with_recipient_info(self):
        """Test building response with recipient snapshot."""
        # Arrange
        invoice = Invoice(
            id=2,
            invoice_number="INV-002",
            amount=Decimal('1500.00'),
            description="Invoice",
            issue_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            status=PaymentStatus.PENDING,
            property_id=10,
            tenant_id=3,
            recipient_type="tenant",
            recipient_name="John Doe",
            recipient_email="john@example.com",
            recipient_company="Acme Corp",
            recipient_address_line1="123 Main St",
            recipient_city="Toronto",
            recipient_province="ON",
            recipient_postal_code="M5V 1A1",
            recipient_country="Canada",
            recipient_tax_number="123456789",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        invoice.line_items = []
        invoice.taxes = []
        invoice.property = None
        invoice.tenant = None
        
        # Act
        response = build_invoice_response(invoice)
        
        # Assert
        assert response['recipient_type'] == "tenant"
        assert response['recipient_name'] == "John Doe"
        assert response['recipient_email'] == "john@example.com"
        assert response['recipient_company'] == "Acme Corp"
        assert response['recipient_address_line1'] == "123 Main St"
        assert response['recipient_city'] == "Toronto"
        assert response['recipient_province'] == "ON"
        assert response['recipient_postal_code'] == "M5V 1A1"
        assert response['recipient_country'] == "Canada"
        assert response['recipient_tax_number'] == "123456789"

    def test_build_response_with_line_items_and_taxes(self):
        """Test building response with line items and taxes."""
        # Arrange
        from Backend.models.accounting.invoice_line_item import InvoiceLineItem
        from Backend.models.accounting.invoice_tax_detail import InvoiceTaxDetail
        
        invoice = Invoice(
            id=3,
            invoice_number="INV-003",
            amount=Decimal('1130.00'),
            description="Invoice with items",
            issue_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            status=PaymentStatus.PENDING,
            property_id=10,
            tenant_id=3,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        
        line_item = InvoiceLineItem(
            id=1,
            invoice_id=3,
            description="Rent",
            quantity=Decimal('1'),
            unit_price=Decimal('1000.00'),
            line_total=Decimal('1000.00'),
            is_taxable=True,
            sort_order=0,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        
        tax = InvoiceTaxDetail(
            id=1,
            invoice_id=3,
            tax_name="HST",
            tax_rate=Decimal('13.00'),
            tax_amount=Decimal('130.00')
        )
        
        invoice.line_items = [line_item]
        invoice.taxes = [tax]
        invoice.property = None
        invoice.tenant = None
        
        # Act
        response = build_invoice_response(invoice)
        
        # Assert
        assert len(response['line_items']) == 1
        assert response['line_items'][0]['description'] == "Rent"
        assert response['line_items'][0]['line_total'] == Decimal('1000.00')
        
        assert len(response['taxes']) == 1
        assert response['taxes'][0]['tax_name'] == "HST"
        assert response['taxes'][0]['tax_amount'] == Decimal('130.00')

    def test_build_response_with_related_entities(self):
        """Test building response with property and tenant relations."""
        # Arrange
        invoice = Invoice(
            id=4,
            invoice_number="INV-004",
            amount=Decimal('1000.00'),
            description="Invoice",
            issue_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            status=PaymentStatus.PENDING,
            property_id=10,
            tenant_id=3,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        invoice.line_items = []
        invoice.taxes = []
        
        # Mock property and tenant
        invoice.property = Property(id=10, name="Main Street Apartments")
        invoice.tenant = Tenant(id=3, first_name="Jane", last_name="Smith")
        
        # Act
        response = build_invoice_response(invoice)
        
        # Assert
        assert response['property'] is not None
        assert response['property']['id'] == 10
        assert response['property']['name'] == "Main Street Apartments"
        
        assert response['tenant'] is not None
        assert response['tenant']['id'] == 3
        assert response['tenant']['full_name'] == "Jane Smith"

    def test_build_response_with_stripe_fields(self):
        """Test building response with Stripe integration fields."""
        # Arrange
        invoice = Invoice(
            id=5,
            invoice_number="INV-005",
            amount=Decimal('1000.00'),
            description="Invoice",
            issue_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            status=PaymentStatus.PENDING,
            property_id=10,
            tenant_id=3,
            stripe_invoice_id="inv_123456",
            hosted_invoice_url="https://invoice.stripe.com/i/abc",
            stripe_invoice_pdf="https://invoice.stripe.com/i/abc/pdf",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        invoice.line_items = []
        invoice.taxes = []
        invoice.property = None
        invoice.tenant = None
        
        # Act
        response = build_invoice_response(invoice)
        
        # Assert
        assert response['stripe_invoice_id'] == "inv_123456"
        assert response['hosted_invoice_url'] == "https://invoice.stripe.com/i/abc"
        assert response['stripe_invoice_pdf'] == "https://invoice.stripe.com/i/abc/pdf"

    def test_build_response_with_workflow_fields(self):
        """Test building response with workflow fields."""
        # Arrange
        user_id = str(uuid4())
        invoice = Invoice(
            id=6,
            invoice_number="INV-006",
            amount=Decimal('1000.00'),
            description="Invoice",
            issue_date=date(2024, 1, 15),
            due_date=date(2024, 2, 15),
            status=PaymentStatus.PENDING,
            property_id=10,
            tenant_id=3,
            is_draft=False,
            issued_at=datetime(2024, 1, 15, 12, 0, 0),
            issued_by_user_id=user_id,
            created_by_user_id=user_id,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0)
        )
        invoice.line_items = []
        invoice.taxes = []
        invoice.property = None
        invoice.tenant = None
        
        # Act
        response = build_invoice_response(invoice)
        
        # Assert
        assert response['is_draft'] is False
        assert response['issued_at'] == "2024-01-15T12:00:00"
        assert response['issued_by_user_id'] == user_id
        assert response['created_by_user_id'] == user_id


class TestInferPropertyForInvoice:
    """Test property inference for tenant invoices."""

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_from_current_property(self, mock_settings):
        """Test property inference from tenant's current_property."""
        # Arrange
        mock_settings.DEBUG = False
        user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        property_obj = Property(id=10, user_id=user.id)
        tenant = Tenant(id=5, current_property=property_obj, leases=[])
        
        # Mock inspection to show relationships are loaded
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, user)
            
            # Assert
            assert result == 10

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_from_active_lease(self, mock_settings):
        """Test property inference from tenant's active lease."""
        # Arrange
        mock_settings.DEBUG = False
        user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        property_obj = Property(id=15, user_id=user.id)
        lease = Lease(
            id=1,
            tenant_id=5,
            property_id=15,
            status=LeaseStatus.ACTIVE,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            property=property_obj
        )
        
        tenant = Tenant(id=5, current_property=None, leases=[lease])
        
        # Mock inspection
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, user)
            
            # Assert
            assert result == 15

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_admin_user(self, mock_settings):
        """Test property inference for admin user."""
        # Arrange
        mock_settings.DEBUG = False
        admin_user = User(id=str(uuid4()), user_type=UserType.ADMIN)
        
        property_obj = Property(id=20, user_id=str(uuid4()))  # Different owner
        tenant = Tenant(id=5, current_property=property_obj, leases=[])
        
        # Mock inspection
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, admin_user)
            
            # Assert
            assert result == 20  # Admin can access any property

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_no_property_found(self, mock_settings):
        """Test property inference when no property can be determined."""
        # Arrange
        mock_settings.DEBUG = False
        user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        tenant = Tenant(id=5, current_property=None, leases=[])
        
        # Mock inspection
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, user)
            
            # Assert
            assert result is None

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_multiple_active_leases_uses_oldest(self, mock_settings):
        """Test property inference with multiple active leases uses oldest."""
        # Arrange
        mock_settings.DEBUG = False
        user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        property1 = Property(id=10, user_id=user.id)
        property2 = Property(id=20, user_id=user.id)
        
        lease1 = Lease(
            id=1,
            tenant_id=5,
            property_id=10,
            status=LeaseStatus.ACTIVE,
            start_date=date(2023, 1, 1),  # Older
            end_date=date(2024, 12, 31),
            property=property1
        )
        
        lease2 = Lease(
            id=2,
            tenant_id=5,
            property_id=20,
            status=LeaseStatus.ACTIVE,
            start_date=date(2024, 1, 1),  # Newer
            end_date=date(2024, 12, 31),
            property=property2
        )
        
        tenant = Tenant(id=5, current_property=None, leases=[lease2, lease1])  # Unordered
        
        # Mock inspection
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, user)
            
            # Assert
            assert result == 10  # Oldest lease's property

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_ignores_inactive_leases(self, mock_settings):
        """Test property inference ignores non-active leases."""
        # Arrange
        mock_settings.DEBUG = False
        user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        property1 = Property(id=10, user_id=user.id)
        property2 = Property(id=20, user_id=user.id)
        
        # Expired lease
        lease1 = Lease(
            id=1,
            tenant_id=5,
            property_id=10,
            status=LeaseStatus.EXPIRED,
            start_date=date(2022, 1, 1),
            end_date=date(2023, 12, 31),
            property=property1
        )
        
        # Active lease
        lease2 = Lease(
            id=2,
            tenant_id=5,
            property_id=20,
            status=LeaseStatus.ACTIVE,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            property=property2
        )
        
        tenant = Tenant(id=5, current_property=None, leases=[lease1, lease2])
        
        # Mock inspection
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, user)
            
            # Assert
            assert result == 20  # Only active lease's property


class TestApplyTenantInvoiceFilters:
    """Test tenant invoice filtering logic."""

    @pytest.mark.asyncio
    async def test_apply_tenant_filters_basic(self):
        """Test basic tenant filter application."""
        # Arrange
        mock_session = AsyncMock()
        tenant_user = User(id=str(uuid4()), user_type=UserType.TENANT)
        tenant = Tenant(id=5, user_id=tenant_user.id)
        
        mock_session.scalar = AsyncMock(return_value=tenant)
        
        filters = []
        
        # Act
        await apply_tenant_invoice_filters(
            filters, tenant_id=None, property_id=None,
            current_user=tenant_user, session=mock_session
        )
        
        # Assert
        assert len(filters) == 1  # Tenant ID filter added

    @pytest.mark.asyncio
    async def test_apply_tenant_filters_with_matching_tenant_id(self):
        """Test tenant filter when tenant_id matches user's tenant."""
        # Arrange
        mock_session = AsyncMock()
        tenant_user = User(id=str(uuid4()), user_type=UserType.TENANT)
        tenant = Tenant(id=5, user_id=tenant_user.id)
        
        mock_session.scalar = AsyncMock(return_value=tenant)
        
        filters = []
        
        # Act - should not raise
        await apply_tenant_invoice_filters(
            filters, tenant_id=5, property_id=None,
            current_user=tenant_user, session=mock_session
        )
        
        # Assert
        assert len(filters) == 1

    @pytest.mark.asyncio
    async def test_apply_tenant_filters_with_mismatched_tenant_id(self):
        """Test tenant filter rejects mismatched tenant_id."""
        # Arrange
        mock_session = AsyncMock()
        tenant_user = User(id=str(uuid4()), user_type=UserType.TENANT)
        tenant = Tenant(id=5, user_id=tenant_user.id)
        
        mock_session.scalar = AsyncMock(return_value=tenant)
        
        filters = []
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await apply_tenant_invoice_filters(
                filters, tenant_id=99,  # Wrong tenant
                property_id=None,
                current_user=tenant_user,
                session=mock_session
            )
        
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_apply_tenant_filters_rejects_property_filter(self):
        """Test tenant filter rejects property_id filtering."""
        # Arrange
        mock_session = AsyncMock()
        tenant_user = User(id=str(uuid4()), user_type=UserType.TENANT)
        tenant = Tenant(id=5, user_id=tenant_user.id)
        
        mock_session.scalar = AsyncMock(return_value=tenant)
        
        filters = []
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await apply_tenant_invoice_filters(
                filters, tenant_id=None, property_id=10,
                current_user=tenant_user, session=mock_session
            )
        
        assert exc_info.value.status_code == 403
        assert "property" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_apply_tenant_filters_no_tenant_record(self):
        """Test tenant filter when user has no tenant record."""
        # Arrange
        mock_session = AsyncMock()
        tenant_user = User(id=str(uuid4()), user_type=UserType.TENANT)
        
        mock_session.scalar = AsyncMock(return_value=None)  # No tenant
        
        filters = []
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await apply_tenant_invoice_filters(
                filters, tenant_id=None, property_id=None,
                current_user=tenant_user, session=mock_session
            )
        
        assert exc_info.value.status_code == 403


class TestApplyLandlordInvoiceFilters:
    """Test landlord invoice filtering logic."""

    @pytest.mark.asyncio
    async def test_apply_landlord_filters_no_properties(self):
        """Test landlord filter when landlord has no properties."""
        # Arrange
        mock_session = AsyncMock()
        landlord_user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        mock_session.scalar = AsyncMock(return_value=None)  # No properties
        
        filters = []
        
        # Act
        result = await apply_landlord_invoice_filters(
            filters, property_id=None, tenant_id=None,
            current_user=landlord_user, session=mock_session
        )
        
        # Assert
        assert result is False  # No properties
        assert len(filters) == 0

    @pytest.mark.asyncio
    async def test_apply_landlord_filters_with_property_id(self):
        """Test landlord filter with specific property_id."""
        # Arrange
        mock_session = AsyncMock()
        landlord_user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        # Mock has_properties check
        mock_session.scalar = AsyncMock(side_effect=[10, 10])  # Has properties, owns property
        
        filters = []
        
        # Act
        result = await apply_landlord_invoice_filters(
            filters, property_id=10, tenant_id=None,
            current_user=landlord_user, session=mock_session
        )
        
        # Assert
        assert result is True
        assert len(filters) == 1  # Property filter added

    @pytest.mark.asyncio
    async def test_apply_landlord_filters_property_not_owned(self):
        """Test landlord filter rejects property_id not owned."""
        # Arrange
        mock_session = AsyncMock()
        landlord_user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        # Mock has_properties check, but doesn't own specific property
        mock_session.scalar = AsyncMock(side_effect=[10, None])
        
        filters = []
        
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await apply_landlord_invoice_filters(
                filters, property_id=99, tenant_id=None,
                current_user=landlord_user, session=mock_session
            )
        
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_apply_landlord_filters_all_invoices(self):
        """Test landlord filter for all invoices (no specific filters)."""
        # Arrange
        mock_session = AsyncMock()
        landlord_user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        mock_session.scalar = AsyncMock(return_value=10)  # Has properties
        
        filters = []
        
        # Act
        result = await apply_landlord_invoice_filters(
            filters, property_id=None, tenant_id=None,
            current_user=landlord_user, session=mock_session
        )
        
        # Assert
        assert result is True
        assert len(filters) == 1  # OR filter for NULL or owned properties


class TestApplyAdminInvoiceFilters:
    """Test admin invoice filtering logic."""

    def test_apply_admin_filters_no_filters(self):
        """Test admin filter with no specific filters."""
        # Arrange
        filters = []
        
        # Act
        apply_admin_invoice_filters(filters, property_id=None, tenant_id=None)
        
        # Assert
        assert len(filters) == 0

    def test_apply_admin_filters_with_tenant_id(self):
        """Test admin filter with tenant_id."""
        # Arrange
        filters = []
        
        # Act
        apply_admin_invoice_filters(filters, property_id=None, tenant_id=5)
        
        # Assert
        assert len(filters) == 1

    def test_apply_admin_filters_with_property_id(self):
        """Test admin filter with property_id."""
        # Arrange
        filters = []
        
        # Act
        apply_admin_invoice_filters(filters, property_id=10, tenant_id=None)
        
        # Assert
        assert len(filters) == 1

    def test_apply_admin_filters_with_both(self):
        """Test admin filter with both tenant_id and property_id."""
        # Arrange
        filters = []
        
        # Act
        apply_admin_invoice_filters(filters, property_id=10, tenant_id=5)
        
        # Assert
        assert len(filters) == 2


class TestBuildInvoiceResponseEdgeCases:
    """Test edge cases in invoice response building."""

    def test_build_response_minimal_invoice(self):
        """Test building response with minimal required fields only."""
        # Arrange
        invoice = Invoice(
            id=10,
            invoice_number="INV-010",
            amount=Decimal('100.00'),
            description="Minimal",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1),
            status=PaymentStatus.PENDING,
            created_at=datetime(2024, 1, 1, 10, 0, 0),
            updated_at=datetime(2024, 1, 1, 10, 0, 0)
        )
        invoice.line_items = []
        invoice.taxes = []
        invoice.property = None
        invoice.tenant = None
        
        # Act
        response = build_invoice_response(invoice)
        
        # Assert
        assert response['id'] == 10
        assert response['amount'] == Decimal('100.00')
        assert response['line_items'] == []
        assert response['taxes'] == []

    def test_build_response_with_quickbooks_sync(self):
        """Test response includes QuickBooks sync data."""
        # Arrange
        invoice = Invoice(
            id=11,
            invoice_number="INV-011",
            amount=Decimal('1000.00'),
            description="QB Invoice",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1),
            status=PaymentStatus.PENDING,
            quickbooks_id="QB-123",
            last_synced_at=datetime(2024, 1, 15, 14, 30, 0),
            created_at=datetime(2024, 1, 1, 10, 0, 0),
            updated_at=datetime(2024, 1, 1, 10, 0, 0)
        )
        invoice.line_items = []
        invoice.taxes = []
        invoice.property = None
        invoice.tenant = None
        
        # Act
        response = build_invoice_response(invoice)
        
        # Assert
        assert response['quickbooks_id'] == "QB-123"
        assert response['last_synced_at'] == "2024-01-15T14:30:00"

    def test_build_response_with_pdf_metadata(self):
        """Test response includes PDF generation metadata."""
        # Arrange
        invoice = Invoice(
            id=12,
            invoice_number="INV-012",
            amount=Decimal('1000.00'),
            description="PDF Invoice",
            issue_date=date(2024, 1, 1),
            due_date=date(2024, 2, 1),
            status=PaymentStatus.PENDING,
            pdf_blob_url="https://storage.azure.com/invoice.pdf",
            pdf_generated_at=datetime(2024, 1, 15, 16, 0, 0),
            created_at=datetime(2024, 1, 1, 10, 0, 0),
            updated_at=datetime(2024, 1, 1, 10, 0, 0)
        )
        invoice.line_items = []
        invoice.taxes = []
        invoice.property = None
        invoice.tenant = None
        
        # Act
        response = build_invoice_response(invoice)
        
        # Assert
        assert response['pdf_blob_url'] == "https://storage.azure.com/invoice.pdf"
        assert response['pdf_generated_at'] == "2024-01-15T16:00:00"


class TestInferPropertyEdgeCases:
    """Test additional property inference scenarios."""

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_with_null_start_date_lease(self, mock_settings):
        """Test property inference with lease having null start_date."""
        # Arrange
        mock_settings.DEBUG = False
        user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        property_obj = Property(id=15, user_id=user.id)
        lease = Lease(
            id=1,
            tenant_id=5,
            property_id=15,
            status=LeaseStatus.ACTIVE,
            start_date=None,  # Null start date
            end_date=date(2024, 12, 31),
            property=property_obj
        )
        
        tenant = Tenant(id=5, current_property=None, leases=[lease])
        
        # Mock inspection
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, user)
            
            # Assert
            assert result == 15  # Should still work

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_lease_without_property_object(self, mock_settings):
        """Test property inference with lease missing property object."""
        # Arrange
        mock_settings.DEBUG = False
        user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        lease = Lease(
            id=1,
            tenant_id=5,
            property_id=15,
            status=LeaseStatus.ACTIVE,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            property=None  # No property object loaded
        )
        
        tenant = Tenant(id=5, current_property=None, leases=[lease])
        
        # Mock inspection
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, user)
            
            # Assert
            assert result is None  # Cannot infer without property


class TestInferPropertyEdgeCases:
    """Additional edge case tests for property inference."""

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_with_null_start_date_lease(self, mock_settings):
        """Test property inference with lease having null start_date."""
        # Arrange
        mock_settings.DEBUG = False
        user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        property_obj = Property(id=15, user_id=user.id)
        lease = Lease(
            id=1,
            tenant_id=5,
            property_id=15,
            status=LeaseStatus.ACTIVE,
            start_date=None,
            end_date=date(2024, 12, 31),
            property=property_obj
        )
        
        tenant = Tenant(id=5, current_property=None, leases=[lease])
        
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, user)
            
            # Assert
            assert result == 15

    @pytest.mark.asyncio
    @patch('Backend.api.accounting.invoices.helpers.settings')
    async def test_infer_property_lease_without_property_object(self, mock_settings):
        """Test property inference with lease missing property object."""
        # Arrange
        mock_settings.DEBUG = False
        user = User(id=str(uuid4()), user_type=UserType.LANDLORD)
        
        lease = Lease(
            id=1,
            tenant_id=5,
            property_id=15,
            status=LeaseStatus.ACTIVE,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            property=None
        )
        
        tenant = Tenant(id=5, current_property=None, leases=[lease])
        
        with patch('Backend.api.accounting.invoices.helpers.inspect') as mock_inspect:
            mock_state = MagicMock()
            mock_state.unloaded = []
            mock_inspect.return_value = mock_state
            
            # Act
            result = await infer_property_for_invoice(tenant, user)
            
            # Assert
            assert result is None
