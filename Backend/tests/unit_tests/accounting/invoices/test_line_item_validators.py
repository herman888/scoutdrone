"""
Unit tests for InvoiceLineItem schema validators.
"""

import pytest
from decimal import Decimal
from pydantic import ValidationError

from Backend.models.accounting.invoice_line_item import InvoiceLineItemCreate


class TestInvoiceLineItemValidators:
    """Test Pydantic validators for line items."""

    def test_valid_line_item_creation(self):
        """Test creating valid line item."""
        # Act
        item = InvoiceLineItemCreate(
            description="Service",
            quantity=Decimal('1'),
            unit_price=Decimal('100.00'),
            is_taxable=True
        )
        
        # Assert
        assert item.description == "Service"
        assert item.quantity == Decimal('1')

    def test_quantity_must_be_positive(self):
        """Test quantity validation rejects zero."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            InvoiceLineItemCreate(
                description="Service",
                quantity=Decimal('0'),  # Invalid
                unit_price=Decimal('100.00'),
                is_taxable=True
            )
        
        assert "greater than 0" in str(exc_info.value).lower()

    def test_quantity_must_be_positive_negative(self):
        """Test quantity validation rejects negative."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            InvoiceLineItemCreate(
                description="Service",
                quantity=Decimal('-1'),  # Invalid
                unit_price=Decimal('100.00'),
                is_taxable=True
            )
        
        assert "greater than 0" in str(exc_info.value).lower()

    def test_unit_price_can_be_zero(self):
        """Test unit price can be zero."""
        # Act
        item = InvoiceLineItemCreate(
            description="Free item",
            quantity=Decimal('1'),
            unit_price=Decimal('0'),
            is_taxable=False
        )
        
        # Assert
        assert item.unit_price == Decimal('0')

    def test_unit_price_cannot_be_negative(self):
        """Test unit price validation rejects negative."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            InvoiceLineItemCreate(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('-10.00'),  # Invalid
                is_taxable=True
            )
        
        assert "non-negative" in str(exc_info.value).lower()

    def test_line_total_cannot_be_negative(self):
        """Test line_total validation rejects negative."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            InvoiceLineItemCreate(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('-100.00'),  # Invalid
                is_taxable=True
            )
        
        assert "non-negative" in str(exc_info.value).lower()

    def test_line_total_can_be_zero(self):
        """Test line_total can be zero."""
        # Act
        item = InvoiceLineItemCreate(
            description="Free item",
            quantity=Decimal('1'),
            unit_price=Decimal('0.00'),
            line_total=Decimal('0.00'),
            is_taxable=False
        )
        
        # Assert
        assert item.line_total == Decimal('0.00')

    def test_line_total_optional(self):
        """Test line_total is optional and defaults to None."""
        # Act
        item = InvoiceLineItemCreate(
            description="Service",
            quantity=Decimal('2'),
            unit_price=Decimal('50.00'),
            is_taxable=True
        )
        
        # Assert
        assert item.line_total is None  # Will be calculated

    def test_is_taxable_defaults_to_true(self):
        """Test is_taxable defaults to True."""
        # Act
        item = InvoiceLineItemCreate(
            description="Service",
            quantity=Decimal('1'),
            unit_price=Decimal('100.00')
        )
        
        # Assert
        assert item.is_taxable == True

    def test_sort_order_defaults_to_zero(self):
        """Test sort_order defaults to 0."""
        # Act
        item = InvoiceLineItemCreate(
            description="Service",
            quantity=Decimal('1'),
            unit_price=Decimal('100.00')
        )
        
        # Assert
        assert item.sort_order == 0

    def test_expense_category_optional(self):
        """Test expense_category is optional."""
        # Act
        item = InvoiceLineItemCreate(
            description="Service",
            quantity=Decimal('1'),
            unit_price=Decimal('100.00')
        )
        
        # Assert
        assert item.expense_category is None

    def test_expense_category_can_be_set(self):
        """Test expense_category can be set."""
        # Act
        item = InvoiceLineItemCreate(
            description="Repair",
            quantity=Decimal('1'),
            unit_price=Decimal('500.00'),
            expense_category="Maintenance"
        )
        
        # Assert
        assert item.expense_category == "Maintenance"
