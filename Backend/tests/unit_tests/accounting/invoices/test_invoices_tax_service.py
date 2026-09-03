"""
Unit tests for invoice service layer tax functionality.

Tests the new tax calculation and amount determination functions
added for Phase 2 tax preferences integration.
"""

import pytest
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, patch

from Backend.api.accounting.invoices.calculations import (
    calculate_invoice_taxes_legacy as calculate_invoice_taxes,
    determine_invoice_amounts_legacy as determine_invoice_amounts
)
from Backend.api.accounting.invoices.service import (
    get_smart_tax_for_invoice_creation
)
from Backend.api.accounting.invoices.schemas import InvoiceCreate
from Backend.models.accounting.invoice_tax_detail import (
    InvoiceTaxDetail, InvoiceTaxDetailCreate
)
from Backend.utils.tax_utils import quantize_2dp


class TestCalculateInvoiceTaxes:
    """Test invoice tax calculation functionality."""

    def test_calculate_invoice_taxes_no_taxes(self):
        """Test tax calculation with no taxes provided."""
        # Arrange
        subtotal = Decimal('1000.00')
        
        # Act
        tax_objects, total_tax = calculate_invoice_taxes(None, subtotal)
        
        # Assert
        assert tax_objects == []
        assert total_tax == Decimal('0.00')

    def test_calculate_invoice_taxes_empty_list(self):
        """Test tax calculation with empty tax list."""
        # Arrange
        subtotal = Decimal('1000.00')
        
        # Act
        tax_objects, total_tax = calculate_invoice_taxes([], subtotal)
        
        # Assert
        assert tax_objects == []
        assert total_tax == Decimal('0.00')

    def test_calculate_invoice_taxes_with_rate_only(self):
        """Test tax calculation using only tax rate."""
        # Arrange
        tax_detail = InvoiceTaxDetailCreate(
            tax_name="HST",
            tax_rate=Decimal('13.00'),
            tax_amount=None  # Will be calculated
        )
        subtotal = Decimal('1000.00')
        
        # Act
        tax_objects, total_tax = calculate_invoice_taxes([tax_detail], subtotal)
        
        # Assert
        assert len(tax_objects) == 1
        tax_obj = tax_objects[0]
        assert isinstance(tax_obj, InvoiceTaxDetail)
        assert tax_obj.tax_name == "HST"
        assert tax_obj.tax_rate == Decimal('13.00')
        assert tax_obj.tax_amount == Decimal('130.00')  # 1000 * 13%
        assert total_tax == Decimal('130.00')

    def test_calculate_invoice_taxes_with_amount_provided(self):
        """Test tax calculation when tax amount is explicitly provided."""
        # Arrange
        tax_detail = InvoiceTaxDetailCreate(
            tax_name="HST",
            tax_rate=Decimal('13.00'),
            tax_amount=Decimal('150.00')  # Explicit amount
        )
        subtotal = Decimal('1000.00')
        
        # Act
        tax_objects, total_tax = calculate_invoice_taxes([tax_detail], subtotal)
        
        # Assert
        assert len(tax_objects) == 1
        tax_obj = tax_objects[0]
        assert tax_obj.tax_name == "HST"
        assert tax_obj.tax_rate == Decimal('13.00')
        assert tax_obj.tax_amount == Decimal('150.00')  # Uses provided amount
        assert total_tax == Decimal('150.00')

    def test_calculate_invoice_taxes_multiple_taxes(self):
        """Test tax calculation with multiple tax entries."""
        # Arrange
        tax_details = [
            InvoiceTaxDetailCreate(
                tax_name="GST",
                tax_rate=Decimal('5.00'),
                tax_amount=None
            ),
            InvoiceTaxDetailCreate(
                tax_name="PST",
                tax_rate=Decimal('7.00'),
                tax_amount=None
            )
        ]
        subtotal = Decimal('1000.00')
        
        # Act
        tax_objects, total_tax = calculate_invoice_taxes(tax_details, subtotal)
        
        # Assert
        assert len(tax_objects) == 2
        
        # Check GST
        gst_obj = tax_objects[0]
        assert gst_obj.tax_name == "GST"
        assert gst_obj.tax_rate == Decimal('5.00')
        assert gst_obj.tax_amount == Decimal('50.00')  # 1000 * 5%
        
        # Check PST
        pst_obj = tax_objects[1]
        assert pst_obj.tax_name == "PST"
        assert pst_obj.tax_rate == Decimal('7.00')
        assert pst_obj.tax_amount == Decimal('70.00')  # 1000 * 7%
        
        assert total_tax == Decimal('120.00')  # 50 + 70

    def test_calculate_invoice_taxes_zero_rate(self):
        """Test tax calculation with zero tax rate."""
        # Arrange
        tax_detail = InvoiceTaxDetailCreate(
            tax_name="NO TAX",
            tax_rate=Decimal('0.00'),
            tax_amount=None
        )
        subtotal = Decimal('1000.00')
        
        # Act
        tax_objects, total_tax = calculate_invoice_taxes([tax_detail], subtotal)
        
        # Assert
        assert len(tax_objects) == 1
        tax_obj = tax_objects[0]
        assert tax_obj.tax_name == "NO TAX"
        assert tax_obj.tax_rate == Decimal('0.00')
        assert tax_obj.tax_amount == Decimal('0.00')
        assert total_tax == Decimal('0.00')


class TestDetermineInvoiceAmounts:
    """Test invoice amount determination logic."""

    def test_determine_amounts_subtotal_only(self):
        """Test amount determination with only subtotal provided."""
        # Arrange
        tax_detail = InvoiceTaxDetailCreate(
            tax_name="HST",
            tax_rate=Decimal('13.00'),
            tax_amount=None
        )
        amount = Decimal('1000.00')
        subtotal_amount = Decimal('1000.00')
        taxes = [tax_detail]
        
        # Act
        subtotal, tax_amount, total = determine_invoice_amounts(
            amount, subtotal_amount, None, taxes
        )
        
        # Assert
        assert subtotal == Decimal('1000.00')
        assert tax_amount == Decimal('130.00')  # 13% of 1000
        assert total == Decimal('1130.00')  # 1000 + 130

    def test_determine_amounts_both_subtotal_and_total_tax(self):
        """Test amount determination with both subtotal and total_tax_amount provided."""
        # Arrange
        amount = Decimal('1130.00')
        subtotal_amount = Decimal('1000.00')
        total_tax_amount = Decimal('130.00')
        
        # Act
        subtotal, tax_amount, total = determine_invoice_amounts(
            amount, subtotal_amount, total_tax_amount, None
        )
        
        # Assert
        assert subtotal == Decimal('1000.00')
        assert tax_amount == Decimal('130.00')
        assert total == Decimal('1130.00')

    def test_determine_amounts_inconsistent_totals_error(self):
        """Test amount determination with inconsistent amounts raises error."""
        # Arrange
        amount = Decimal('1200.00')  # Inconsistent with subtotal + tax
        subtotal_amount = Decimal('1000.00')
        total_tax_amount = Decimal('130.00')  # Should total 1130, not 1200
        
        # Act & Assert
        with pytest.raises(ValueError, match="Inconsistent amounts"):
            determine_invoice_amounts(amount, subtotal_amount, total_tax_amount, None)

    def test_determine_amounts_total_only_no_taxes(self):
        """Test amount determination with only total, no taxes."""
        # Arrange
        amount = Decimal('1000.00')
        # No subtotal_amount, no taxes
        
        # Act
        subtotal, tax_amount, total = determine_invoice_amounts(
            amount, None, None, None
        )
        
        # Assert
        assert subtotal == Decimal('1000.00')  # Total treated as subtotal
        assert tax_amount == Decimal('0.00')
        assert total == Decimal('1000.00')

    def test_determine_amounts_total_with_taxes_back_calculation(self):
        """Test amount determination with total and taxes - back-calculates subtotal."""
        # Arrange
        tax_detail = InvoiceTaxDetailCreate(
            tax_name="HST",
            tax_rate=Decimal('13.00'),
            tax_amount=None
        )
        amount = Decimal('1130.00')  # Tax-inclusive total
        taxes = [tax_detail]
        # No subtotal_amount provided
        
        # Act
        subtotal, tax_amount, total = determine_invoice_amounts(
            amount, None, None, taxes
        )
        
        # Assert
        # Back-calculated: 1130 / (1 + 0.13) = 1000
        assert subtotal == Decimal('1000.00')
        assert tax_amount == Decimal('130.00')
        assert total == Decimal('1130.00')

    def test_determine_amounts_back_calculation_accuracy_error(self):
        """Test back-calculation error when amounts don't align properly."""
        # Arrange - create a scenario with inconsistent rounding that will fail accuracy check
        tax_detail = InvoiceTaxDetailCreate(
            tax_name="INVALID TAX",
            tax_rate=Decimal('0.01'),  # Very small rate
            tax_amount=Decimal('999.99')  # Impossible amount for the rate
        )
        amount = Decimal('100.00')  # Total much less than tax amount
        taxes = [tax_detail]
        
        # This should raise the accuracy error
        with pytest.raises(ValueError, match="Cannot accurately back-calculate"):
            determine_invoice_amounts(amount, None, None, taxes)


class TestSmartTaxIntegration:
    """Test smart tax auto-population for invoice creation."""

    @pytest.mark.asyncio
    async def test_get_smart_tax_with_existing_taxes(self):
        """Test that existing taxes are preserved."""
        # Arrange
        existing_tax = InvoiceTaxDetailCreate(
            tax_name="HST",
            tax_rate=Decimal('13.00'),
            tax_amount=None
        )
        invoice_data = InvoiceCreate(
            invoice_number="INV-001",
            amount=Decimal('1130.00'),
            description="Test invoice",
            issue_date="2024-08-15T10:30:00Z",
            due_date="2024-09-15T10:30:00Z",
            taxes=[existing_tax]
        )
        mock_session = AsyncMock()
        user_id = "test-user"
        property_id = 1
        
        # Act
        result = await get_smart_tax_for_invoice_creation(
            mock_session, user_id, property_id, invoice_data
        )
        
        # Assert
        assert result == invoice_data  # Unchanged
        assert len(result.taxes) == 1
        assert result.taxes[0].tax_name == "HST"

    @pytest.mark.asyncio
    async def test_get_smart_tax_no_recommendation(self):
        """Test when no smart tax recommendation is available."""
        # Arrange
        invoice_data = InvoiceCreate(
            invoice_number="INV-001",
            amount=Decimal('1000.00'),
            description="Test invoice",
            issue_date="2024-08-15T10:30:00Z",
            due_date="2024-09-15T10:30:00Z"
            # No taxes
        )
        mock_session = AsyncMock()
        user_id = "test-user"
        property_id = 1
        
        with patch('Backend.api.accounting.tax_preferences.service.get_smart_tax_for_invoice') as mock_get_smart:
            mock_get_smart.return_value = None  # No recommendation
            
            # Act
            result = await get_smart_tax_for_invoice_creation(
                mock_session, user_id, property_id, invoice_data
            )
            
            # Assert
            assert result == invoice_data  # Unchanged
            assert result.taxes is None or result.taxes == []

    @pytest.mark.asyncio
    async def test_get_smart_tax_with_recommendation(self):
        """Test when smart tax recommendation is available."""
        # Arrange
        invoice_data = InvoiceCreate(
            invoice_number="INV-001",
            amount=Decimal('1000.00'),
            description="Test invoice",
            issue_date="2024-08-15T10:30:00Z",
            due_date="2024-09-15T10:30:00Z"
            # No taxes
        )
        mock_session = AsyncMock()
        user_id = "test-user" 
        property_id = 1
        
        with patch('Backend.api.accounting.tax_preferences.service.get_smart_tax_for_invoice') as mock_get_smart:
            mock_get_smart.return_value = ("HST", Decimal('13.00'))  # Smart recommendation
            
            # Act
            result = await get_smart_tax_for_invoice_creation(
                mock_session, user_id, property_id, invoice_data
            )
            
            # Assert
            assert result != invoice_data  # Changed
            assert len(result.taxes) == 1
            tax = result.taxes[0]
            assert tax.tax_name == "HST"
            assert tax.tax_rate == Decimal('13.00')
            assert tax.tax_amount is None  # Will be calculated later

    @pytest.mark.asyncio
    async def test_get_smart_tax_none_property(self):
        """Test smart tax with None property_id."""
        # Arrange
        invoice_data = InvoiceCreate(
            invoice_number="INV-001",
            amount=Decimal('1000.00'),
            description="Test invoice",
            issue_date="2024-08-15T10:30:00Z",
            due_date="2024-09-15T10:30:00Z"
        )
        mock_session = AsyncMock()
        user_id = "test-user"
        property_id = None
        
        with patch('Backend.api.accounting.tax_preferences.service.get_smart_tax_for_invoice') as mock_get_smart:
            mock_get_smart.return_value = ("GST", Decimal('5.00'))
            
            # Act
            result = await get_smart_tax_for_invoice_creation(
                mock_session, user_id, property_id, invoice_data
            )
            
            # Assert
            mock_get_smart.assert_called_once_with(mock_session, user_id, None)
            assert len(result.taxes) == 1
            assert result.taxes[0].tax_name == "GST"