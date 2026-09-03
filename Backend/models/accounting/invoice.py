"""Invoice ORM model"""
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional
from uuid import UUID as PythonUUID

from sqlalchemy import DateTime, Numeric, Column, String, Index, Enum as PgEnum, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, Relationship, SQLModel

from Backend.utils.datetime_utils import create_audit_datetime
from .common import PaymentStatus # Import PaymentStatus from common


class InvoiceDeliveryMethod(str, PyEnum):
    """
    Invoice delivery method options.
    
    - SAVE_LOCALLY: Create invoice record only, no Stripe/email (for manual follow-up)
    - SEND_INVOICE: Send branded email via Stripe without payment collection
    - REQUEST_PAYMENT: Send branded email with Stripe payment link (requires Connect)
    """
    SAVE_LOCALLY = "save_locally"
    SEND_INVOICE = "send_invoice"
    REQUEST_PAYMENT = "request_payment"

if TYPE_CHECKING:
    from Backend.models.property import Property
    from Backend.models.tenant import Tenant
    from Backend.models.user import User
    from Backend.models.ownership_entity import OwnershipEntity
    from Backend.models.vendor import Vendor
    from Backend.models.accounting.invoice_tax_detail import InvoiceTaxDetail
    from Backend.models.accounting.invoice_line_item import InvoiceLineItem
    from Backend.models.accounting.payment_allocation import PaymentAllocation

class Invoice(SQLModel, table=True):
    """
    Invoice model for billing tenants, ownership entities, or vendors.
    
    Invoices now support:
    - Multiple line items (quantity × unit price)
    - Three recipient types: tenant, ownership_entity, vendor
    - Recipient data snapshots for immutability
    - Draft/issued workflow
    - Audit trail
    """

    __tablename__ = "invoices"  # type: ignore
    __table_args__ = (
        Index("ix_invoices_property_id", "property_id"),
        Index("ix_invoices_tenant_id", "tenant_id"),
        Index("idx_invoices_ownership_entity_id", "ownership_entity_id"),
        Index("idx_invoices_vendor_id", "vendor_id"),
        Index("idx_invoices_unit_id", "unit_id"),
        Index("idx_invoices_is_draft", "is_draft"),
        Index("idx_invoices_issued_at", "issued_at"),
        Index("idx_invoices_created_by_user_id", "created_by_user_id"),
    ) 

    id: int | None = Field(default=None, primary_key=True)
    invoice_number: str = Field(unique=True)
    amount: Decimal = Field(sa_column=Column(Numeric(precision=12, scale=2), nullable=False))
    description: str
    issue_date: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    due_date: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    status: PaymentStatus = Field(
        default=PaymentStatus.PENDING,
        sa_column=Column(PgEnum(PaymentStatus, name="paymentstatus",
                         create_constraint=True, values_callable=lambda x: [e.value for e in x]))
    )

    # ============================================================================
    # Accounting Context
    # ============================================================================
    property_id: int | None = Field(default=None, foreign_key="properties.id")
    unit_id: int | None = Field(default=None)  # FK to units table (if exists)
    
    # ============================================================================
    # Recipient Information (one of three types)
    # ============================================================================
    recipient_type: str | None = Field(
        default=None,
        sa_column=Column(String(20), nullable=True),
        description="Type: 'tenant', 'ownership_entity', or 'vendor'"
    )
    
    # Recipient IDs (only one should be populated based on recipient_type)
    tenant_id: int | None = Field(default=None, foreign_key="tenants.id")
    ownership_entity_id: PythonUUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("ownership_entities.id"), nullable=True)
    )
    vendor_id: int | None = Field(default=None, foreign_key="vendors.id")
    
    # ============================================================================
    # Recipient Snapshot (immutable copy for audit trail)
    # ============================================================================
    recipient_name: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
        description="Immutable: Full name at time of invoice creation"
    )
    recipient_company: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
        description="Immutable: Company name (if applicable)"
    )
    recipient_email: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
        description="Immutable: Email address"
    )
    recipient_address_line1: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True)
    )
    recipient_address_line2: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True)
    )
    recipient_city: str | None = Field(
        default=None,
        sa_column=Column(String(100), nullable=True)
    )
    recipient_province: str | None = Field(
        default=None,
        sa_column=Column(String(50), nullable=True)
    )
    recipient_postal_code: str | None = Field(
        default=None,
        sa_column=Column(String(20), nullable=True)
    )
    recipient_country: str | None = Field(
        default="Canada",
        sa_column=Column(String(50), nullable=True)
    )
    recipient_tax_number: str | None = Field(
        default=None,
        sa_column=Column(String(50), nullable=True),
        description="Business number, GST/HST number, etc."
    )
    
    # ============================================================================
    # Audit and Workflow
    # ============================================================================
    created_by_user_id: PythonUUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), nullable=True),
        description="User who created this invoice"
    )
    is_draft: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default='true'),
        description="True until invoice is finalized. Draft invoices are editable."
    )
    issued_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when invoice was finalized and became immutable"
    )
    issued_by_user_id: PythonUUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), nullable=True),
        description="User who finalized/issued this invoice"
    )

    # ============================================================================
    # QuickBooks Integration
    # ============================================================================
    quickbooks_id: str | None = Field(
        default=None,
        sa_column=Column(String(length=64), nullable=True, unique=True),
    )
    last_synced_at: datetime | None = Field(
        default=None, 
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True)
    )
    
    # ============================================================================
    # Stripe Integration
    # ============================================================================
    delivery_method: InvoiceDeliveryMethod = Field(
        default=InvoiceDeliveryMethod.SAVE_LOCALLY,
        sa_column=Column(
            PgEnum(InvoiceDeliveryMethod, name="invoicedeliverymethod",
                   create_constraint=True, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
            server_default="save_locally"
        ),
        description="How this invoice will be delivered to the recipient"
    )
    stripe_invoice_id: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True, unique=True),
        description="Stripe Invoice ID if created via Stripe Invoices API (e.g., inv_xxx)"
    )
    hosted_invoice_url: str | None = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Stripe-hosted payment page URL for this invoice"
    )
    stripe_invoice_pdf: str | None = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="URL to Stripe-generated PDF invoice"
    )
    
    # ============================================================================
    # PDF Storage
    # ============================================================================
    pdf_blob_url: str | None = Field(
        default=None,
        sa_column=Column(String, nullable=True),
        description="Azure Blob Storage URL for Brikli-generated invoice PDF"
    )
    pdf_generated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="Timestamp when PDF was generated and uploaded to Azure Blob"
    )

    # ============================================================================
    # Standard Timestamps
    # ============================================================================
    created_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=create_audit_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    # ============================================================================
    # Relationships
    # ============================================================================
    property: Optional["Property"] = Relationship(back_populates="invoices")
    tenant: Optional["Tenant"] = Relationship(back_populates="invoices")
    ownership_entity: Optional["OwnershipEntity"] = Relationship(back_populates="invoices")
    vendor: Optional["Vendor"] = Relationship(back_populates="invoices")
    
    # Note: User relationships commented out to avoid circular import and foreign_keys complexity
    # Access via direct queries when needed:
    # created_by_user = await session.get(User, invoice.created_by_user_id)
    # issued_by_user = await session.get(User, invoice.issued_by_user_id)
    
    line_items: list["InvoiceLineItem"] = Relationship(
        back_populates="invoice",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
            "order_by": "InvoiceLineItem.sort_order"
        },
    )
    taxes: list["InvoiceTaxDetail"] = Relationship(
        back_populates="invoice",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
            "order_by": "InvoiceTaxDetail.tax_name"
        },
    )
    payment_allocations: list["PaymentAllocation"] = Relationship(back_populates="invoice")

