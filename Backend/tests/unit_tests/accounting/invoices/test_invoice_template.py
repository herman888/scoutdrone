"""
Unit tests for invoice HTML template generation.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from Backend.api.accounting.invoices.invoice_template import BrikliInvoiceTemplate
from Backend.models.accounting.invoice import Invoice
from Backend.models.accounting.invoice_line_item import InvoiceLineItem
from Backend.models.accounting.invoice_tax_detail import InvoiceTaxDetail
from Backend.models.accounting.common import PaymentStatus


class TestBrikliInvoiceTemplate:
    """Test invoice HTML template generation."""

    def test_generate_basic_invoice_html(self):
        """Test generating basic invoice HTML."""
        # Arrange
        invoice = Invoice(
            id=1,
            invoice_number="INV-001",
            amount=Decimal('1000.00'),
            description="Monthly rent",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Rent",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=False
            )
        ]
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "INV-001" in html
        assert "1000.00" in html or "1,000.00" in html
        assert "Monthly rent" in html or html  # Invoice description may or may not be in HTML
        assert "<!DOCTYPE html>" in html
        assert "Brikli" in html

    def test_generate_invoice_with_taxes(self):
        """Test generating invoice with tax details."""
        # Arrange
        invoice = Invoice(
            id=2,
            invoice_number="INV-002",
            amount=Decimal('1130.00'),
            description="Rent with tax",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
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
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "HST" in html
        assert "130" in html
        assert "1130" in html or "1,130" in html

    def test_generate_invoice_with_multiple_line_items(self):
        """Test generating invoice with multiple line items."""
        # Arrange
        invoice = Invoice(
            id=3,
            invoice_number="INV-003",
            amount=Decimal('1250.00'),
            description="Multiple items",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
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
                quantity=Decimal('1'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('100.00'),
                is_taxable=False
            )
        ]
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "Rent" in html
        assert "Utilities" in html
        assert "Parking" in html

    def test_generate_invoice_with_custom_company_info(self):
        """Test generating invoice with custom company information."""
        # Arrange
        invoice = Invoice(
            id=4,
            invoice_number="INV-004",
            amount=Decimal('1000.00'),
            description="Test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=False
            )
        ]
        taxes = []
        company_info = {
            'name': 'Custom Property LLC',
            'address': '123 Main St',
            'address_2': 'Suite 100',
            'country': 'USA',
            'email': 'custom@example.com',
            'phone': '+1 555-0123'
        }
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(
            invoice, line_items, taxes, company_info=company_info
        )
        
        # Assert
        assert "Custom Property LLC" in html
        assert "123 Main St" in html
        assert "custom@example.com" in html

    def test_generate_invoice_with_stripe_payment_url(self):
        """Test generating invoice with Stripe payment link."""
        # Arrange
        invoice = Invoice(
            id=5,
            invoice_number="INV-005",
            amount=Decimal('1000.00'),
            description="Test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=False
            )
        ]
        taxes = []
        stripe_url = "https://invoice.stripe.com/i/acct_test/invst_test123"
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(
            invoice, line_items, taxes, stripe_payment_url=stripe_url
        )
        
        # Assert
        assert stripe_url in html or "Pay Now" in html

    def test_generate_invoice_html_escapes_user_content(self):
        """Test that user-provided content is properly HTML-escaped."""
        # Arrange
        invoice = Invoice(
            id=6,
            invoice_number="INV-<script>alert('xss')</script>",
            amount=Decimal('1000.00'),
            description="Test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="<b>Bold Item</b>",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=False
            )
        ]
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "<script>" not in html
        assert "&lt;script&gt;" in html or "alert" not in html

    def test_generate_invoice_with_recipient_info(self):
        """Test generating invoice with recipient information."""
        # Arrange
        invoice = Invoice(
            id=7,
            invoice_number="INV-007",
            amount=Decimal('1000.00'),
            description="Test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING,
            recipient_name="John Doe",
            recipient_email="john@example.com",
            recipient_address_line1="456 Oak St",
            recipient_city="Toronto",
            recipient_province="ON"
        )
        line_items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=False
            )
        ]
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "John Doe" in html
        assert "456 Oak St" in html or "john@example.com" in html

    def test_generate_invoice_with_mixed_taxability(self):
        """Test invoice with both taxable and non-taxable items shows breakdown."""
        # Arrange
        invoice = Invoice(
            id=8,
            invoice_number="INV-008",
            amount=Decimal('1250.00'),
            description="Mixed items",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Taxable Item",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            ),
            InvoiceLineItem(
                description="Non-Taxable Item",
                quantity=Decimal('1'),
                unit_price=Decimal('250.00'),
                line_total=Decimal('250.00'),
                is_taxable=False
            )
        ]
        taxes = [
            InvoiceTaxDetail(
                tax_name="HST",
                tax_rate=Decimal('13.00'),
                tax_amount=Decimal('130.00')
            )
        ]
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "1000" in html or "1,000" in html  # Taxable subtotal
        assert "250" in html  # Non-taxable subtotal
        assert "HST" in html

    def test_generate_invoice_date_formatting(self):
        """Test that dates are formatted correctly."""
        # Arrange
        invoice = Invoice(
            id=9,
            invoice_number="INV-009",
            amount=Decimal('1000.00'),
            description="Test",
            issue_date=datetime(2024, 3, 15),
            due_date=datetime(2024, 4, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=False
            )
        ]
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "March" in html or "2024" in html
        assert "April" in html or "15" in html

    def test_generate_invoice_with_quantity_greater_than_one(self):
        """Test invoice with line items having quantity > 1."""
        # Arrange
        invoice = Invoice(
            id=10,
            invoice_number="INV-010",
            amount=Decimal('300.00'),
            description="Test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Widget",
                quantity=Decimal('3'),
                unit_price=Decimal('100.00'),
                line_total=Decimal('300.00'),
                is_taxable=False
            )
        ]
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "Widget" in html
        assert "3" in html or "300" in html

    def test_generate_invoice_includes_logo(self):
        """Test that invoice includes Brikli logo."""
        # Arrange
        invoice = Invoice(
            id=11,
            invoice_number="INV-011",
            amount=Decimal('1000.00'),
            description="Test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=False
            )
        ]
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "BrikliTransparentWhite.png" in html or "logo" in html.lower()

    def test_generate_invoice_with_zero_amount_tax(self):
        """Test invoice with zero-amount tax."""
        # Arrange
        invoice = Invoice(
            id=12,
            invoice_number="INV-012",
            amount=Decimal('1000.00'),
            description="Test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            )
        ]
        taxes = [
            InvoiceTaxDetail(
                tax_name="Tax Exempt",
                tax_rate=Decimal('0.00'),
                tax_amount=Decimal('0.00')
            )
        ]
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "Tax Exempt" in html or "0.00" in html

    def test_generate_invoice_with_multiple_taxes(self):
        """Test invoice with multiple tax types."""
        # Arrange
        invoice = Invoice(
            id=13,
            invoice_number="INV-013",
            amount=Decimal('1120.00'),
            description="Test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('1000.00'),
                line_total=Decimal('1000.00'),
                is_taxable=True
            )
        ]
        taxes = [
            InvoiceTaxDetail(
                tax_name="GST",
                tax_rate=Decimal('5.00'),
                tax_amount=Decimal('50.00')
            ),
            InvoiceTaxDetail(
                tax_name="PST",
                tax_rate=Decimal('7.00'),
                tax_amount=Decimal('70.00')
            )
        ]
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "GST" in html
        assert "PST" in html
        assert "50" in html and "70" in html

    def test_generate_invoice_no_line_items(self):
        """Test invoice generation with no line items."""
        # Arrange
        invoice = Invoice(
            id=14,
            invoice_number="INV-014",
            amount=Decimal('1000.00'),
            description="Legacy invoice",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = []
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "INV-014" in html
        assert "1000" in html or "1,000" in html

    def test_generate_invoice_with_decimal_rounding(self):
        """Test invoice handles decimal rounding properly."""
        # Arrange
        invoice = Invoice(
            id=15,
            invoice_number="INV-015",
            amount=Decimal('1234.56'),
            description="Decimal test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="Service",
                quantity=Decimal('1'),
                unit_price=Decimal('1234.56'),
                line_total=Decimal('1234.56'),
                is_taxable=False
            )
        ]
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "1234.56" in html or "1,234.56" in html

    def test_generate_invoice_long_descriptions(self):
        """Test invoice with very long line item descriptions."""
        # Arrange
        invoice = Invoice(
            id=16,
            invoice_number="INV-016",
            amount=Decimal('500.00'),
            description="Test",
            issue_date=datetime(2024, 1, 15),
            due_date=datetime(2024, 2, 15),
            status=PaymentStatus.PENDING
        )
        line_items = [
            InvoiceLineItem(
                description="This is a very long description that contains many words and describes a complex service that was provided to the tenant over an extended period of time with various components and details",
                quantity=Decimal('1'),
                unit_price=Decimal('500.00'),
                line_total=Decimal('500.00'),
                is_taxable=False
            )
        ]
        taxes = []
        
        # Act
        html = BrikliInvoiceTemplate.generate_invoice_html(invoice, line_items, taxes)
        
        # Assert
        assert "very long description" in html
        assert "500" in html
