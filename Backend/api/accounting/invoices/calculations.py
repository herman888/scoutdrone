"""
Pure calculation logic for invoice amounts, taxes, and line items.

This module contains NO database operations - only mathematical calculations.
All functions are pure (deterministic, no side effects) for easy unit testing.
"""
from decimal import Decimal
from typing import List, Optional

from Backend.models.accounting.invoice_line_item import InvoiceLineItem, InvoiceLineItemCreate
from Backend.models.accounting.invoice_tax_detail import InvoiceTaxDetail, InvoiceTaxDetailCreate
from Backend.utils.tax_utils import quantize_2dp


# ============================================================================
# Line Item Calculations
# ============================================================================

def calculate_line_items_subtotal(line_items: List[InvoiceLineItem]) -> Decimal:
    """
    Calculate subtotal from a list of line items.
    
    Args:
        line_items: List of InvoiceLineItem ORM objects
    
    Returns:
        Sum of all line_total values
    """
    return sum((item.line_total for item in line_items), Decimal('0'))


def calculate_subtotal_breakdown(line_items: List[InvoiceLineItem]) -> tuple[Decimal, Decimal, Decimal]:
    """
    Calculate taxable vs non-taxable subtotal breakdown.
    
    This provides transparency for accountants to see:
    - How much of the invoice is subject to tax
    - How much is tax-exempt
    - Total subtotal (sum of both)
    
    Args:
        line_items: List of InvoiceLineItem ORM objects
    
    Returns:
        Tuple of (taxable_subtotal, non_taxable_subtotal, total_subtotal)
    """
    taxable_subtotal = Decimal('0')
    non_taxable_subtotal = Decimal('0')
    
    for item in line_items:
        if item.is_taxable:
            taxable_subtotal += item.line_total
        else:
            non_taxable_subtotal += item.line_total
    
    total_subtotal = taxable_subtotal + non_taxable_subtotal
    
    return (
        quantize_2dp(taxable_subtotal),
        quantize_2dp(non_taxable_subtotal),
        quantize_2dp(total_subtotal)
    )


def process_line_items_for_invoice(
    line_items_data: Optional[List[InvoiceLineItemCreate]]
) -> tuple[list[InvoiceLineItem], Decimal]:
    """
    Process line items from invoice creation request.
    
    - Calculates line_total if not provided (quantity × unit_price)
    - Returns list of InvoiceLineItem ORM objects (without invoice_id)
    - Returns calculated subtotal
    
    Args:
        line_items_data: List of InvoiceLineItemCreate schemas from request
    
    Returns:
        Tuple of (line_item_orm_objects, subtotal)
    """
    if not line_items_data or len(line_items_data) == 0:
        return [], Decimal('0')
    
    line_item_objects = []
    subtotal = Decimal('0')
    
    for idx, item_data in enumerate(line_items_data):
        # Calculate line_total if not provided
        if item_data.line_total is None:
            line_total = quantize_2dp(item_data.quantity * item_data.unit_price)
        else:
            line_total = quantize_2dp(item_data.line_total)
        
        # Create ORM object (invoice_id will be set when invoice is created)
        line_item = InvoiceLineItem(
            description=item_data.description,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            line_total=line_total,
            is_taxable=item_data.is_taxable,
            expense_category=item_data.expense_category,
            sort_order=item_data.sort_order if item_data.sort_order is not None else idx
        )
        
        line_item_objects.append(line_item)
        subtotal += line_total
    
    return line_item_objects, quantize_2dp(subtotal)


# ============================================================================
# Tax Calculations
# ============================================================================

def calculate_taxes_on_line_items(
    line_items: list[InvoiceLineItem],
    tax_details: Optional[List[InvoiceTaxDetailCreate]],
    fallback_subtotal: Decimal
) -> tuple[list[InvoiceTaxDetail], Decimal]:
    """
    Calculate taxes based on taxable line items only.
    
    For each tax:
    - Sum the line_total of all taxable line items
    - Apply tax rate to that sum
    - Create InvoiceTaxDetail ORM object
    
    Args:
        line_items: List of line item ORM objects
        tax_details: List of InvoiceTaxDetailCreate from request
        fallback_subtotal: Subtotal to use if no line items (backward compat)
    
    Returns:
        Tuple of (tax_orm_objects, total_tax_amount)
    """
    if not tax_details or len(tax_details) == 0:
        return [], Decimal('0')
    
    # Calculate taxable subtotal (only from taxable line items)
    if line_items and len(line_items) > 0:
        taxable_subtotal = sum(
            (item.line_total for item in line_items if item.is_taxable),
            Decimal('0')
        )
    else:
        # Fallback for backward compatibility (old invoices without line items)
        taxable_subtotal = fallback_subtotal
    
    tax_orm_objects = []
    total_tax = Decimal('0')
    
    for tax_data in tax_details:
        if not tax_data.tax_name or tax_data.tax_rate is None:
            continue
        
        # Calculate tax amount on taxable subtotal
        tax_amount = quantize_2dp(taxable_subtotal * tax_data.tax_rate / Decimal('100'))
        
        tax_orm = InvoiceTaxDetail(
            tax_name=tax_data.tax_name,
            tax_rate=tax_data.tax_rate,
            tax_amount=tax_amount
        )
        
        tax_orm_objects.append(tax_orm)
        total_tax += tax_amount
    
    return tax_orm_objects, quantize_2dp(total_tax)


def calculate_invoice_total(
    line_items: list[InvoiceLineItem],
    taxes: list[InvoiceTaxDetail],
    fallback_amount: Optional[Decimal] = None
) -> Decimal:
    """
    Calculate the grand total for an invoice.
    
    Formula: SUM(line_items.line_total) + SUM(taxes.tax_amount)
    
    Args:
        line_items: List of line item ORM objects
        taxes: List of tax ORM objects
        fallback_amount: Amount to use if no line items (backward compat)
    
    Returns:
        Grand total (subtotal + taxes)
    """
    if line_items and len(line_items) > 0:
        subtotal = calculate_line_items_subtotal(line_items)
    elif fallback_amount is not None:
        subtotal = fallback_amount
    else:
        subtotal = Decimal('0')
    
    total_tax = sum((tax.tax_amount for tax in taxes), Decimal('0'))
    
    return quantize_2dp(subtotal + total_tax)


def generate_invoice_description(line_items: list[InvoiceLineItem]) -> str:
    """
    Auto-generate invoice description from line items.
    
    Args:
        line_items: List of line item ORM objects
    
    Returns:
        Generated description string
    """
    if not line_items or len(line_items) == 0:
        return "Invoice"
    
    count = len(line_items)
    
    if count == 1:
        # Single item: use its description
        return line_items[0].description
    else:
        # Multiple items: generic summary
        return f"Invoice with {count} items"


# ============================================================================
# Legacy Tax Calculation Functions (Backward Compatibility)
# ============================================================================

def calculate_invoice_taxes_legacy(
    tax_details: Optional[List[InvoiceTaxDetailCreate]],
    subtotal: Decimal
) -> tuple[list[InvoiceTaxDetail], Decimal]:
    """
    Legacy tax calculation for invoices without line items.
    
    Used for backward compatibility with old invoice system.
    
    Args:
        tax_details: Tax detail schemas from request
        subtotal: Subtotal amount for tax calculations
    
    Returns:
        Tuple of (tax_orm_objects, total_tax_amount)
    """
    if not tax_details:
        return [], Decimal('0.00')
    
    tax_orm_objects = []
    total_tax_amount = Decimal('0.00')
    
    for tax_detail in tax_details:
        # Calculate tax amount if not provided
        if tax_detail.tax_amount is None:
            tax_decimal = tax_detail.tax_rate / Decimal('100')
            tax_amount = quantize_2dp(subtotal * tax_decimal)
        else:
            tax_amount = quantize_2dp(tax_detail.tax_amount)
        
        # Create ORM object
        tax_orm = InvoiceTaxDetail(
            tax_name=tax_detail.tax_name,
            tax_rate=tax_detail.tax_rate,
            tax_amount=tax_amount
        )
        
        tax_orm_objects.append(tax_orm)
        total_tax_amount += tax_amount
    
    return tax_orm_objects, quantize_2dp(total_tax_amount)


def determine_invoice_amounts_legacy(
    amount: Decimal,
    subtotal_amount: Optional[Decimal],
    total_tax_amount: Optional[Decimal],
    taxes: Optional[List[InvoiceTaxDetailCreate]]
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Legacy function for determining invoice amounts from various input scenarios.
    
    This is kept for backward compatibility with old API clients.
    New invoices should use line items instead.
    
    Args:
        amount: Total amount (grand total)
        subtotal_amount: Optional subtotal
        total_tax_amount: Optional total tax
        taxes: Optional tax details
    
    Returns:
        Tuple of (subtotal, total_tax_amount, final_total)
    """
    
    # Scenario 1: Both subtotal and total provided
    if subtotal_amount is not None and total_tax_amount is not None:
        subtotal = quantize_2dp(subtotal_amount)
        tax_amount = quantize_2dp(total_tax_amount)
        calculated_total = subtotal + tax_amount
        
        # Validate against provided total
        provided_total = quantize_2dp(amount)
        if abs(calculated_total - provided_total) > Decimal('0.01'):
            raise ValueError(
                f"Inconsistent amounts: subtotal ({subtotal}) + tax ({tax_amount}) "
                f"= {calculated_total} != total ({provided_total})"
            )
        
        return subtotal, tax_amount, provided_total
    
    # Scenario 2: Subtotal provided, calculate taxes
    if subtotal_amount is not None:
        subtotal = quantize_2dp(subtotal_amount)
        
        if not taxes:
            return subtotal, Decimal('0.00'), subtotal
            
        total_tax_amount = Decimal('0.00')
        for tax_detail in taxes:
            if tax_detail.tax_amount is None:
                tax_decimal = tax_detail.tax_rate / Decimal('100')
                tax_amount = quantize_2dp(subtotal * tax_decimal)
            else:
                tax_amount = quantize_2dp(tax_detail.tax_amount)
            total_tax_amount += tax_amount
        
        total_tax_amount = quantize_2dp(total_tax_amount)
        final_total = subtotal + total_tax_amount
        
        return subtotal, total_tax_amount, final_total
    
    # Scenario 3: Only total provided (most common for old invoices)
    total_amount = quantize_2dp(amount)
    
    # If taxes are specified, back-calculate subtotal
    if taxes:
        # Calculate total tax rate
        total_tax_rate = sum(tax.tax_rate for tax in taxes) / Decimal('100')
        
        # Back-calculate subtotal: subtotal = total / (1 + tax_rate)
        subtotal = quantize_2dp(total_amount / (Decimal('1') + total_tax_rate))
        
        # Calculate actual tax amount
        actual_tax_amount = Decimal('0.00')
        for tax_detail in taxes:
            if tax_detail.tax_amount is None:
                tax_decimal = tax_detail.tax_rate / Decimal('100')
                tax_amount = quantize_2dp(subtotal * tax_decimal)
            else:
                tax_amount = quantize_2dp(tax_detail.tax_amount)
            actual_tax_amount += tax_amount
        
        actual_tax_amount = quantize_2dp(actual_tax_amount)
        
        # Verify calculation is reasonable (allow small rounding differences)
        if abs((subtotal + actual_tax_amount) - total_amount) > Decimal('0.01'):
            raise ValueError("Cannot accurately back-calculate subtotal from total and tax rates")
            
        return subtotal, actual_tax_amount, total_amount
    
    # No tax details - treat total as subtotal with zero tax
    return total_amount, Decimal('0.00'), total_amount
