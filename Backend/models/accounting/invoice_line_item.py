"""Invoice Line Item ORM model and schemas"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, field_validator, ConfigDict
from sqlalchemy import DateTime, Numeric, Column, String, Boolean, Integer, Index, Text
from sqlmodel import Field, Relationship, SQLModel

from Backend.utils.datetime_utils import create_audit_datetime

if TYPE_CHECKING:
    from Backend.models.accounting.invoice import Invoice


# ============================================================================
# Pydantic Schemas
# ============================================================================

class InvoiceLineItemBase(BaseModel):
    """Base schema for invoice line items"""
    description: str
    quantity: Decimal
    unit_price: Decimal
    is_taxable: bool = True
    expense_category: Optional[str] = None
    sort_order: int = 0
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v: Decimal) -> Decimal:
        if v <= Decimal('0'):
            raise ValueError('Quantity must be greater than 0')
        return v
    
    @field_validator('unit_price')
    @classmethod
    def validate_unit_price(cls, v: Decimal) -> Decimal:
        if v < Decimal('0'):
            raise ValueError('Unit price must be non-negative')
        return v


class InvoiceLineItemCreate(InvoiceLineItemBase):
    """Schema for creating a line item"""
    line_total: Optional[Decimal] = None  # Auto-calculated if not provided
    
    @field_validator('line_total')
    @classmethod
    def validate_line_total(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < Decimal('0'):
            raise ValueError('Line total must be non-negative')
        return v


class InvoiceLineItemResponse(InvoiceLineItemBase):
    """Schema for returning a line item"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    invoice_id: int
    line_total: Decimal
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Database ORM Model
# ============================================================================

class InvoiceLineItem(SQLModel, table=True):
    """
    Represents a single line item on an invoice.
    
    Each line item contains:
    - Description (what is being charged)
    - Quantity (how many units)
    - Unit price (price per unit)
    - Line total (quantity × unit_price, auto-calculated by trigger)
    - Tax applicability flag
    - Expense category for accounting mapping
    - Sort order for display
    """
    
    __tablename__ = "invoice_line_items"  # type: ignore
    __table_args__ = (
        Index("idx_invoice_line_items_invoice_id", "invoice_id"),
        Index("idx_invoice_line_items_expense_category", "expense_category"),
        Index("idx_invoice_line_items_sort_order", "invoice_id", "sort_order"),
    )
    
    # Primary Key
    id: int | None = Field(default=None, primary_key=True)
    
    # Foreign Key to Invoice
    invoice_id: int = Field(foreign_key="invoices.id", index=True)
    
    # Line Item Details
    description: str = Field(sa_column=Column(Text, nullable=False))
    quantity: Decimal = Field(
        sa_column=Column(Numeric(12, 3), nullable=False),
        default=Decimal('1.0'),
        ge=0.001,
        description="Quantity (must be greater than 0)"
    )
    unit_price: Decimal = Field(
        sa_column=Column(Numeric(12, 2), nullable=False),
        ge=0,
        description="Price per unit"
    )
    line_total: Decimal = Field(
        sa_column=Column(Numeric(12, 2), nullable=False),
        ge=0,
        description="Total for this line (quantity × unit_price). Auto-calculated by DB trigger."
    )
    
    # Tax Applicability
    is_taxable: bool = Field(
        sa_column=Column(Boolean, nullable=False, server_default='true'),
        default=True,
        description="Whether taxes should be applied to this line item"
    )
    
    # Accounting Mapping
    expense_category: str | None = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
        description="Expense category for accounting (e.g., 'rent', 'maintenance')"
    )
    
    # Ordering
    sort_order: int = Field(
        sa_column=Column(Integer, nullable=False, server_default='0'),
        default=0,
        description="Display order (lower numbers appear first)"
    )
    
    # Audit Timestamps
    created_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    
    # Relationships
    invoice: "Invoice" = Relationship(back_populates="line_items")
