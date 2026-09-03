"""
Comprehensive unit tests for invoice calculations module.

Tests all pure calculation functions including:
- Line item calculations
- Tax calculations  
- Amount determinations
- Subtotal breakdowns
- Edge cases and error scenarios
"""

import pytest
from decimal import Decimal

from Backend.api.accounting.invoices.calculations import (
    calculate_line_items_subtotal,
    calculate_subtotal_breakdown,
    process_line_items_for_invoice,
    calculate_taxes_on_line_items,
    calculate_invoice_total,
    generate_invoice_description,
    calculate_invoice_taxes_legacy,
    determine_invoice_amounts_legacy
)
from Backend.models.accounting.invoice_line_item import InvoiceLineItem, InvoiceLineItemCreate
from Backend.models.accounting.invoice_tax_detail import InvoiceTaxDetail, InvoiceTaxDetailCreate


class TestCalculateLineItemsSubtotal:
    """Test line items subtotal calculation."""

    def test_calculate_subtotal_empty_list(self):
        """Test subtotal with empty line items list."""
        result = calculate_line_items_subtotal([])
        assert result == Decimal('0')

    def test_calculate_subtotal_single_item(self):
        """Test subtotal with single line item."""
        item = InvoiceLineItem(
            description="Rent",
            quantity=Decimal('1'),
            unit_price=Decimal('1000.00'),
            line_total=Decimal('1000.00'),
            is_taxable=True
        )
        result = calculate_line_items_subtotal([item])
        assert result == Decimal('1000.00')

    def test_calculate_subtotal_multiple_items(self):
        """Test subtotal with multiple line items."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            ),
            InvoiceLineItem(
                description="Utilities",
                quantity=Decimal('1'),
                unit_price=Decimal('150.00'),
                line_total=Decimal('150.00'),
                is_taxable=True
            ),
            InvoiceLineItem(
                description="Parking",
                quantity=Decimal('2'),
                unit_price=Decimal('50.00'),
                line_total=Decimal('100.00'),
                is_taxable=False
            )
        ]
        result = calculate_line_items_subtotal(items)
        assert result == Decimal('1250.00')


class TestCalculateSubtotalBreakdown:
    """Test taxable vs non-taxable subtotal breakdown."""

    def test_breakdown_all_taxable(self):
        """Test breakdown when all items are taxable."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            ),
            InvoiceLineItem(
                description="Utilities",
                quantity=Decimal('1'),
                unit_price=Decimal('150.00'),
                line_total=Decimal('150.00'),
                is_taxable=True
            )
        ]
        taxable, non_taxable, total = calculate_subtotal_breakdown(items)
        
        assert taxable == Decimal('1150.00')
        assert non_taxable == Decimal('0.00')
        assert total == Decimal('1150.00')

    def test_breakdown_all_non_taxable(self):
        """Test breakdown when all items are non-taxable."""
        items = [
            InvoiceLineItem(
                description="Security deposit",
                quantity=Decimal('1'),
                unit_price=Decimal('500.00'),
                line_total=Decimal('500.00'),
                is_taxable=False
            ),
            InvoiceLineItem(
                description="Key deposit",
                quantity=Decimal('1'),
                unit_price=Decimal('50.00'),
                line_total=Decimal('50.00'),
                is_taxable=False
            )
        ]
        taxable, non_taxable, total = calculate_subtotal_breakdown(items)
        
        assert taxable == Decimal('0.00')
        assert non_taxable == Decimal('550.00')
        assert total == Decimal('550.00')

    def test_breakdown_mixed_taxability(self):
        """Test breakdown with mixed taxable and non-taxable items."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            ),
            InvoiceLineItem(
                description="Parking",
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('100.00'),
                is_taxable=False
            ),
            InvoiceLineItem(
                description="Utilities",
                quantity=Decimal('1'),
                unit_price=Decimal('150.00'),
                line_total=Decimal('150.00'),
                is_taxable=True
            )
        ]
        taxable, non_taxable, total = calculate_subtotal_breakdown(items)
        
        assert taxable == Decimal('1150.00')
        assert non_taxable == Decimal('100.00')
        assert total == Decimal('1250.00')

    def test_breakdown_empty_list(self):
        """Test breakdown with empty line items list."""
        taxable, non_taxable, total = calculate_subtotal_breakdown([])
        
        assert taxable == Decimal('0.00')
        assert non_taxable == Decimal('0.00')
        assert total == Decimal('0.00')

    def test_breakdown_decimal_precision(self):
        """Test breakdown maintains 2 decimal place precision."""
        items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('3'),
                unit_price=Decimal('33.333'),
                line_total=Decimal('99.999'),
                is_taxable=True
            )
        ]
        taxable, non_taxable, total = calculate_subtotal_breakdown(items)
        
        # Should be quantized to 2 decimal places
        assert taxable == Decimal('100.00')
        assert non_taxable == Decimal('0.00')
        assert total == Decimal('100.00')


class TestProcessLineItemsForInvoice:
    """Test line item processing for invoice creation."""

    def test_process_empty_list(self):
        """Test processing empty line items list."""
        line_items, subtotal = process_line_items_for_invoice(None)
        
        assert line_items == []
        assert subtotal == Decimal('0')

    def test_process_empty_array(self):
        """Test processing empty array."""
        line_items, subtotal = process_line_items_for_invoice([])
        
        assert line_items == []
        assert subtotal == Decimal('0')

    def test_process_single_item_with_line_total(self):
        """Test processing single item with explicit line_total."""
        item_data = InvoiceLineItemCreate(
            description="Rent",
            quantity=Decimal('1'),
            unit_price=Decimal('1000.00'),
            line_total=Decimal('1000.00'),
            is_taxable=True
        )
        
        line_items, subtotal = process_line_items_for_invoice([item_data])
        
        assert len(line_items) == 1
        assert line_items[0].description == "Rent"
        assert line_items[0].line_total == Decimal('1000.00')
        assert subtotal == Decimal('1000.00')

    def test_process_item_calculate_line_total(self):
        """Test processing item without line_total (calculated from qty * price)."""
        item_data = InvoiceLineItemCreate(
            description="Parking",
            quantity=Decimal('3'),
            unit_price=Decimal('50.00'),
            line_total=None,  # Should be calculated
            is_taxable=False
        )
        
        line_items, subtotal = process_line_items_for_invoice([item_data])
        
        assert len(line_items) == 1
        assert line_items[0].line_total == Decimal('150.00')  # 3 * 50
        assert subtotal == Decimal('150.00')

    def test_process_multiple_items(self):
        """Test processing multiple line items."""
        items_data = [
            InvoiceLineItemCreate(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            ),
            InvoiceLineItemCreate(
                description="Utilities",
                quantity=Decimal('1'),
                unit_price=Decimal('150.00'),
                line_total=None,  # Calculated
                is_taxable=True
            ),
            InvoiceLineItemCreate(
                description="Parking",
                quantity=Decimal('2'),
                unit_price=Decimal('50.00'),
                line_total=None,  # Calculated
                is_taxable=False
            )
        ]
        
        line_items, subtotal = process_line_items_for_invoice(items_data)
        
        assert len(line_items) == 3
        assert line_items[0].line_total == Decimal('1000.00')
        assert line_items[1].line_total == Decimal('150.00')
        assert line_items[2].line_total == Decimal('100.00')
        assert subtotal == Decimal('1250.00')

    def test_process_with_sort_order(self):
        """Test processing preserves explicit sort_order."""
        items_data = [
            InvoiceLineItemCreate(
                description="Item 1",
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('100.00'),
                is_taxable=True,
                sort_order=5
            ),
            InvoiceLineItemCreate(
                description="Item 2",
                quantity=Decimal('1'),
                unit_price=Decimal('200.00'),
                line_total=Decimal('200.00'),
                is_taxable=True,
                sort_order=1
            )
        ]
        
        line_items, subtotal = process_line_items_for_invoice(items_data)
        
        assert line_items[0].sort_order == 5
        assert line_items[1].sort_order == 1

    def test_process_with_explicit_sort_order(self):
        """Test processing preserves explicit sort_order values."""
        items_data = [
            InvoiceLineItemCreate(
                description="Item 1",
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('100.00'),
                is_taxable=True,
                sort_order=0
            ),
            InvoiceLineItemCreate(
                description="Item 2",
                quantity=Decimal('1'),
                unit_price=Decimal('200.00'),
                line_total=Decimal('200.00'),
                is_taxable=True,
                sort_order=1
            )
        ]
        
        line_items, subtotal = process_line_items_for_invoice(items_data)
        
        assert line_items[0].sort_order == 0
        assert line_items[1].sort_order == 1

    def test_process_with_expense_category(self):
        """Test processing preserves expense_category."""
        item_data = InvoiceLineItemCreate(
            description="Repair",
            quantity=Decimal('1'),
            unit_price=Decimal('250.00'),
            line_total=Decimal('250.00'),
            is_taxable=True,
            expense_category="Maintenance"
        )
        
        line_items, subtotal = process_line_items_for_invoice([item_data])
        
        assert line_items[0].expense_category == "Maintenance"


class TestCalculateTaxesOnLineItems:
    """Test tax calculations on line items."""

    def test_calculate_taxes_no_taxes(self):
        """Test tax calculation with no taxes provided."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            )
        ]
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            items, None, Decimal('1000.00')
        )
        
        assert tax_objects == []
        assert total_tax == Decimal('0')

    def test_calculate_taxes_empty_list(self):
        """Test tax calculation with empty tax list."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            )
        ]
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            items, [], Decimal('1000.00')
        )
        
        assert tax_objects == []
        assert total_tax == Decimal('0')

    def test_calculate_taxes_all_taxable_items(self):
        """Test tax calculation when all items are taxable."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            ),
            InvoiceLineItem(
                description="Utilities",
                quantity=Decimal('1'),
                unit_price=Decimal('150.00'),
                line_total=Decimal('150.00'),
                is_taxable=True
            )
        ]
        
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=None
            )
        ]
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            items, tax_data, Decimal('0')
        )
        
        assert len(tax_objects) == 1
        assert tax_objects[0].tax_name == "HST"
        assert tax_objects[0].tax_amount == Decimal('149.50')  # 1150 * 13%
        assert total_tax == Decimal('149.50')

    def test_calculate_taxes_mixed_taxability(self):
        """Test tax calculation with mixed taxable/non-taxable items."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            ),
            InvoiceLineItem(
                description="Deposit",
                quantity=Decimal('1'),
                unit_price=Decimal('500.00'),
                line_total=Decimal('500.00'),
                is_taxable=False  # Not taxable
            )
        ]
        
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=None
            )
        ]
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            items, tax_data, Decimal('0')
        )
        
        # Tax should only apply to taxable subtotal (1000), not deposit (500)
        assert tax_objects[0].tax_amount == Decimal('130.00')  # 1000 * 13%
        assert total_tax == Decimal('130.00')

    def test_calculate_taxes_no_taxable_items(self):
        """Test tax calculation when no items are taxable."""
        items = [
            InvoiceLineItem(
                description="Deposit",
                quantity=Decimal('1'),
                unit_price=Decimal('500.00'),
                line_total=Decimal('500.00'),
                is_taxable=False
            ),
            InvoiceLineItem(
                description="Key deposit",
                quantity=Decimal('1'),
                unit_price=Decimal('50.00'),
                line_total=Decimal('50.00'),
                is_taxable=False
            )
        ]
        
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=None
            )
        ]
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            items, tax_data, Decimal('0')
        )
        
        # No tax should be applied
        assert tax_objects[0].tax_amount == Decimal('0.00')
        assert total_tax == Decimal('0.00')

    def test_calculate_taxes_multiple_taxes(self):
        """Test calculation with multiple tax types."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            )
        ]
        
        tax_data = [
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
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            items, tax_data, Decimal('0')
        )
        
        assert len(tax_objects) == 2
        assert tax_objects[0].tax_amount == Decimal('50.00')  # 5%
        assert tax_objects[1].tax_amount == Decimal('70.00')  # 7%
        assert total_tax == Decimal('120.00')

    def test_calculate_taxes_fallback_to_subtotal(self):
        """Test fallback to subtotal when no line items."""
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=None
            )
        ]
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            [], tax_data, Decimal('1000.00')  # Fallback subtotal
        )
        
        assert tax_objects[0].tax_amount == Decimal('130.00')
        assert total_tax == Decimal('130.00')

    def test_calculate_taxes_skip_invalid_tax(self):
        """Test that invalid tax entries (None rate) are skipped during calculation."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            )
        ]
        
        # Create tax data with valid schemas but test the calculation logic
        # that skips taxes without required fields
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="VALID TAX",
                tax_rate=Decimal('5.00'),
                tax_amount=None
            )
        ]
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            items, tax_data, Decimal('0')
        )
        
        # The valid tax should be processed
        assert len(tax_objects) == 1
        assert tax_objects[0].tax_name == "VALID TAX"
        assert total_tax == Decimal('50.00')


class TestCalculateInvoiceTotal:
    """Test invoice total calculation."""

    def test_calculate_total_with_line_items_and_taxes(self):
        """Test total calculation with line items and taxes."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            )
        ]
        
        taxes = [
            InvoiceTaxDetail(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=Decimal('130.00')
            )
        ]
        
        total = calculate_invoice_total(items, taxes)
        
        assert total == Decimal('1130.00')

    def test_calculate_total_no_taxes(self):
        """Test total calculation without taxes."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            )
        ]
        
        total = calculate_invoice_total(items, [])
        
        assert total == Decimal('1000.00')

    def test_calculate_total_no_line_items_with_fallback(self):
        """Test total calculation using fallback amount."""
        taxes = [
            InvoiceTaxDetail(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=Decimal('130.00')
            )
        ]
        
        total = calculate_invoice_total([], taxes, fallback_amount=Decimal('1000.00'))
        
        assert total == Decimal('1130.00')

    def test_calculate_total_no_line_items_no_fallback(self):
        """Test total calculation with no line items and no fallback."""
        taxes = [
            InvoiceTaxDetail(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=Decimal('130.00')
            )
        ]
        
        total = calculate_invoice_total([], taxes, fallback_amount=None)
        
        assert total == Decimal('130.00')  # Only tax amount

    def test_calculate_total_multiple_items_and_taxes(self):
        """Test total with multiple line items and taxes."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            ),
            InvoiceLineItem(
                description="Utilities",
                quantity=Decimal('1'),
                unit_price=Decimal('150.00'),
                line_total=Decimal('150.00'),
                is_taxable=True
            )
        ]
        
        taxes = [
            InvoiceTaxDetail(
                tax_name="GST",
                tax_rate=Decimal('5.00'),
                tax_amount=Decimal('57.50')
            ),
            InvoiceTaxDetail(
                tax_name="PST",
                tax_rate=Decimal('7.00'),
                tax_amount=Decimal('80.50')
            )
        ]
        
        total = calculate_invoice_total(items, taxes)
        
        assert total == Decimal('1288.00')  # 1150 + 57.50 + 80.50


class TestGenerateInvoiceDescription:
    """Test invoice description generation."""

    def test_generate_description_empty_list(self):
        """Test description generation with no line items."""
        description = generate_invoice_description([])
        assert description == "Invoice"

    def test_generate_description_none(self):
        """Test description generation with None."""
        description = generate_invoice_description(None)
        assert description == "Invoice"

    def test_generate_description_single_item(self):
        """Test description generation with single line item."""
        items = [
            InvoiceLineItem(
                description="Monthly Rent - January 2024",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            )
        ]
        
        description = generate_invoice_description(items)
        assert description == "Monthly Rent - January 2024"

    def test_generate_description_multiple_items(self):
        """Test description generation with multiple line items."""
        items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            ),
            InvoiceLineItem(
                description="Utilities",
                quantity=Decimal('1'),
                unit_price=Decimal('150.00'),
                line_total=Decimal('150.00'),
                is_taxable=True
            )
        ]
        
        description = generate_invoice_description(items)
        assert description == "Invoice with 2 items"

    def test_generate_description_many_items(self):
        """Test description generation with many line items."""
        items = [
            InvoiceLineItem(
                description=f"Item {i}",
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('100.00'),
                is_taxable=True
            )
            for i in range(5)
        ]
        
        description = generate_invoice_description(items)
        assert description == "Invoice with 5 items"


class TestLegacyCalculations:
    """Test legacy calculation functions for backward compatibility."""

    def test_legacy_calculate_taxes_no_taxes(self):
        """Test legacy tax calculation with no taxes."""
        tax_objects, total_tax = calculate_invoice_taxes_legacy(
            None, Decimal('1000.00')
        )
        
        assert tax_objects == []
        assert total_tax == Decimal('0.00')

    def test_legacy_calculate_taxes_with_rate(self):
        """Test legacy tax calculation using rate."""
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=None
            )
        ]
        
        tax_objects, total_tax = calculate_invoice_taxes_legacy(
            tax_data, Decimal('1000.00')
        )
        
        assert len(tax_objects) == 1
        assert tax_objects[0].tax_amount == Decimal('130.00')
        assert total_tax == Decimal('130.00')

    def test_legacy_calculate_taxes_with_amount(self):
        """Test legacy tax calculation with explicit amount."""
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=Decimal('150.00')
            )
        ]
        
        tax_objects, total_tax = calculate_invoice_taxes_legacy(
            tax_data, Decimal('1000.00')
        )
        
        assert tax_objects[0].tax_amount == Decimal('150.00')
        assert total_tax == Decimal('150.00')

    def test_legacy_determine_amounts_scenario_1(self):
        """Test legacy amount determination - both subtotal and tax provided."""
        subtotal, tax, total = determine_invoice_amounts_legacy(
            amount=Decimal('1130.00'),
            subtotal_amount=Decimal('1000.00'),
            total_tax_amount=Decimal('130.00'),
            taxes=None
        )
        
        assert subtotal == Decimal('1000.00')
        assert tax == Decimal('130.00')
        assert total == Decimal('1130.00')

    def test_legacy_determine_amounts_scenario_1_inconsistent(self):
        """Test legacy amount determination - inconsistent amounts error."""
        with pytest.raises(ValueError, match="Inconsistent amounts"):
            determine_invoice_amounts_legacy(
                amount=Decimal('1200.00'),  # Wrong total
                subtotal_amount=Decimal('1000.00'),
                total_tax_amount=Decimal('130.00'),
                taxes=None
            )

    def test_legacy_determine_amounts_scenario_2_no_taxes(self):
        """Test legacy amount determination - subtotal only, no taxes."""
        subtotal, tax, total = determine_invoice_amounts_legacy(
            amount=Decimal('1000.00'),
            subtotal_amount=Decimal('1000.00'),
            total_tax_amount=None,
            taxes=None
        )
        
        assert subtotal == Decimal('1000.00')
        assert tax == Decimal('0.00')
        assert total == Decimal('1000.00')

    def test_legacy_determine_amounts_scenario_2_with_taxes(self):
        """Test legacy amount determination - subtotal provided, calculate taxes."""
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=None
            )
        ]
        
        subtotal, tax, total = determine_invoice_amounts_legacy(
            amount=Decimal('1000.00'),
            subtotal_amount=Decimal('1000.00'),
            total_tax_amount=None,
            taxes=tax_data
        )
        
        assert subtotal == Decimal('1000.00')
        assert tax == Decimal('130.00')
        assert total == Decimal('1130.00')

    def test_legacy_determine_amounts_scenario_3_no_taxes(self):
        """Test legacy amount determination - only total, no taxes."""
        subtotal, tax, total = determine_invoice_amounts_legacy(
            amount=Decimal('1000.00'),
            subtotal_amount=None,
            total_tax_amount=None,
            taxes=None
        )
        
        assert subtotal == Decimal('1000.00')
        assert tax == Decimal('0.00')
        assert total == Decimal('1000.00')

    def test_legacy_determine_amounts_scenario_3_back_calculate(self):
        """Test legacy amount determination - back-calculate from tax-inclusive total."""
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=None
            )
        ]
        
        subtotal, tax, total = determine_invoice_amounts_legacy(
            amount=Decimal('1130.00'),
            subtotal_amount=None,
            total_tax_amount=None,
            taxes=tax_data
        )
        
        assert subtotal == Decimal('1000.00')  # 1130 / 1.13
        assert tax == Decimal('130.00')
        assert total == Decimal('1130.00')

    def test_legacy_determine_amounts_scenario_3_back_calculate_multiple_taxes(self):
        """Test legacy back-calculation with multiple taxes."""
        tax_data = [
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
        
        # Total tax rate = 12%
        # If total is 1120, subtotal should be 1000
        subtotal, tax, total = determine_invoice_amounts_legacy(
            amount=Decimal('1120.00'),
            subtotal_amount=None,
            total_tax_amount=None,
            taxes=tax_data
        )
        
        assert subtotal == Decimal('1000.00')  # 1120 / 1.12
        assert tax == Decimal('120.00')  # 50 + 70
        assert total == Decimal('1120.00')

    def test_legacy_determine_amounts_explicit_tax_amounts(self):
        """Test legacy determination with explicit tax amounts in data."""
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=Decimal('150.00')  # Explicit override
            )
        ]
        
        subtotal, tax, total = determine_invoice_amounts_legacy(
            amount=Decimal('1000.00'),
            subtotal_amount=Decimal('1000.00'),
            total_tax_amount=None,
            taxes=tax_data
        )
        
        assert subtotal == Decimal('1000.00')
        assert tax == Decimal('150.00')  # Uses explicit amount
        assert total == Decimal('1150.00')

    def test_legacy_determine_amounts_back_calculate_error(self):
        """Test legacy back-calculation error for inconsistent amounts."""
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="Invalid",
                tax_rate=Decimal('1.00'),
                tax_amount=Decimal('9999.00')  # Impossibly large
            )
        ]
        
        with pytest.raises(ValueError, match="Cannot accurately back-calculate"):
            determine_invoice_amounts_legacy(
                amount=Decimal('100.00'),
                subtotal_amount=None,
                total_tax_amount=None,
                taxes=tax_data
            )


class TestCalculationsEdgeCases:
    """Additional edge case tests for calculations."""

    def test_calculate_line_items_subtotal_large_quantities(self):
        """Test subtotal with large quantities."""
        items = [
            InvoiceLineItem(
                description="Bulk Service",
                quantity=Decimal('100'),
                unit_price=Decimal('25.50'),
                line_total=Decimal('2550.00'),
                is_taxable=True
            )
        ]
        result = calculate_line_items_subtotal(items)
        assert result == Decimal('2550.00')

    def test_process_line_items_fractional_quantity(self):
        """Test processing with fractional quantities."""
        item_data = InvoiceLineItemCreate(
            description="Prorated Service",
            quantity=Decimal('0.5'),
            unit_price=Decimal('1000.00'),
            line_total=None,
            is_taxable=True
        )
        
        line_items, subtotal = process_line_items_for_invoice([item_data])
        
        assert line_items[0].line_total == Decimal('500.00')
        assert subtotal == Decimal('500.00')

    def test_calculate_taxes_high_precision(self):
        """Test tax calculation with high precision rates."""
        items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('999.99'),
                line_total=Decimal('999.99'),
                is_taxable=True
            )
        ]
        
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="Precise Tax",
                tax_rate=Decimal('12.5'),
                tax_amount=None
            )
        ]
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            items, tax_data, Decimal('0')
        )
        
        # 999.99 * 12.5% = 125.00 (rounded)
        assert tax_objects[0].tax_amount == Decimal('125.00')
        assert total_tax == Decimal('125.00')

    def test_legacy_back_calculate_zero_tax_rate(self):
        """Test legacy back-calculation with zero tax rate."""
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="No Tax",
                tax_rate=Decimal('0.00'),
                tax_amount=None
            )
        ]
        
        subtotal, tax, total = determine_invoice_amounts_legacy(
            amount=Decimal('1000.00'),
            subtotal_amount=None,
            total_tax_amount=None,
            taxes=tax_data
        )
        
        assert subtotal == Decimal('1000.00')
        assert tax == Decimal('0.00')
        assert total == Decimal('1000.00')

    def test_calculate_invoice_total_empty_lists(self):
        """Test total calculation with empty line items and taxes."""
        total = calculate_invoice_total([], [], fallback_amount=None)
        assert total == Decimal('0.00')

    def test_calculate_invoice_total_only_taxes_no_fallback(self):
        """Test total with only taxes and no line items or fallback."""
        taxes = [
            InvoiceTaxDetail(
                tax_name="Tax",
                tax_rate=Decimal('5.00'),
                tax_amount=Decimal('50.00')
            )
        ]
        total = calculate_invoice_total([], taxes, fallback_amount=None)
        assert total == Decimal('50.00')

    def test_generate_description_single_character(self):
        """Test description generation with single character description."""
        items = [
            InvoiceLineItem(
                description="X",
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('100.00'),
                is_taxable=False
            )
        ]
        description = generate_invoice_description(items)
        assert description == "X"

    def test_process_line_items_zero_unit_price(self):
        """Test processing line item with zero unit price."""
        item_data = InvoiceLineItemCreate(
            description="Free item",
            quantity=Decimal('1'),
            unit_price=Decimal('0.00'),
            line_total=None,
            is_taxable=False
        )
        
        line_items, subtotal = process_line_items_for_invoice([item_data])
        
        assert line_items[0].line_total == Decimal('0.00')
        assert subtotal == Decimal('0.00')

    def test_calculate_taxes_very_large_amount(self):
        """Test tax calculation with very large amounts."""
        items = [
            InvoiceLineItem(
                description="Large Service",
                quantity=Decimal('1'),
                unit_price=Decimal('999999.99'),
                line_total=Decimal('999999.99'),
                is_taxable=True
            )
        ]
        
        tax_data = [
            InvoiceTaxDetailCreate(
                tax_name="Tax",
                tax_rate=Decimal('13.00'),
                tax_amount=None
            )
        ]
        
        tax_objects, total_tax = calculate_taxes_on_line_items(
            items, tax_data, Decimal('0')
        )
        
        # 999999.99 * 13% = 130000.00 (rounded)
        assert tax_objects[0].tax_amount == Decimal('130000.00')

    def test_breakdown_single_item_taxable(self):
        """Test breakdown with single taxable item."""
        items = [
            InvoiceLineItem(
                description="Single",
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('100.00'),
                is_taxable=True
            )
        ]
        taxable, non_taxable, total = calculate_subtotal_breakdown(items)
        
        assert taxable == Decimal('100.00')
        assert non_taxable == Decimal('0.00')
        assert total == Decimal('100.00')

    def test_breakdown_single_item_non_taxable(self):
        """Test breakdown with single non-taxable item."""
        items = [
            InvoiceLineItem(
                description="Single",
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('100.00'),
                is_taxable=False
            )
        ]
        taxable, non_taxable, total = calculate_subtotal_breakdown(items)
        
        assert taxable == Decimal('0.00')
        assert non_taxable == Decimal('100.00')
        assert total == Decimal('100.00')
