"""
Pydantic models for the Invoices API, defining the data structures for
request and response bodies.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator, Field
from Backend.models.accounting.common import PaymentStatus
from Backend.models.accounting.invoice import InvoiceDeliveryMethod
from Backend.models.accounting.invoice_tax_detail import (
    InvoiceTaxDetailCreate, InvoiceTaxDetailResponse
)
from Backend.models.accounting.invoice_line_item import (
    InvoiceLineItemCreate, InvoiceLineItemResponse
)


# === Recipient Type Support ===
RecipientType = Literal['tenant', 'ownership_entity', 'vendor']


# === Recipient Info Schemas ===
class RecipientSnapshot(BaseModel):
    """Immutable snapshot of recipient details at time of invoice creation"""
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = 'Canada'
    tax_number: Optional[str] = None

# === API Models for Invoices ===
class InvoiceBase(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    
    invoice_number: str | None = None  # Auto-generated if not provided
    amount: Decimal  # Legacy: will be deprecated in favor of subtotal_amount
    description: str
    issue_date: datetime
    due_date: datetime
    status: PaymentStatus = PaymentStatus.PENDING
    
    # Accounting context
    property_id: int | None = None
    unit_id: int | None = None
    
    # Delivery method (how invoice will be delivered)
    delivery_method: InvoiceDeliveryMethod = InvoiceDeliveryMethod.SAVE_LOCALLY
    
    # Recipient information
    recipient_type: Optional[RecipientType] = None
    tenant_id: int | None = None
    ownership_entity_id: UUID | None = None
    vendor_id: int | None = None
    
    # Recipient snapshot (optional on create, will be auto-populated)
    recipient_snapshot: Optional[RecipientSnapshot] = None
    
    # Line items (NEW - preferred over single amount/description)
    line_items: Optional[List[InvoiceLineItemCreate]] = None
    
    # Tax support fields
    taxes: Optional[List[InvoiceTaxDetailCreate]] = None

    # Note: Amount validation moved to InvoiceCreate subclass to handle draft vs finalized logic

    @field_validator('due_date')
    @classmethod
    def due_date_must_not_be_earlier_than_issue_date(cls, v, info):
        if 'issue_date' in info.data and v < info.data['issue_date']:
            raise ValueError('Due date cannot be earlier than issue date')
        return v
    
    @model_validator(mode='after')
    def validate_recipient_provided(self):
        """Ensure exactly one recipient type is provided"""
        recipients = [self.tenant_id, self.ownership_entity_id, self.vendor_id]
        non_null_recipients = [r for r in recipients if r is not None]
        
        if len(non_null_recipients) == 0:
            # Allow no recipient for backward compatibility
            pass
        elif len(non_null_recipients) > 1:
            raise ValueError('Invoice must have exactly one recipient (tenant, ownership_entity, or vendor)')
        
        # If recipient_type is provided, validate it matches the actual recipient ID
        if self.recipient_type:
            if self.recipient_type == 'tenant' and not self.tenant_id:
                raise ValueError('tenant_id required when recipient_type is "tenant"')
            if self.recipient_type == 'ownership_entity' and not self.ownership_entity_id:
                raise ValueError('ownership_entity_id required when recipient_type is "ownership_entity"')
            if self.recipient_type == 'vendor' and not self.vendor_id:
                raise ValueError('vendor_id required when recipient_type is "vendor"')
        
        return self


class InvoiceCreate(InvoiceBase):
    """Schema for creating a new invoice"""
    is_draft: bool = False  # Allow drafts to have 0 amount
    
    @model_validator(mode='after')
    def validate_amount_for_non_drafts(self):
        """Allow 0 amount for drafts, require positive for finalized invoices"""
        if not self.is_draft and self.amount <= 0:
            raise ValueError('Amount must be greater than 0 for finalized invoices')
        return self


class InvoiceUpdate(BaseModel):
    """Schema for updating an existing invoice (only allowed for drafts)"""
    model_config = ConfigDict(use_enum_values=True)
    
    invoice_number: str | None = None
    amount: Decimal | None = None  # Legacy field
    description: str | None = None
    issue_date: datetime | None = None
    due_date: datetime | None = None
    status: PaymentStatus | None = None
    
    # Property and unit context
    property_id: int | None = None
    unit_id: int | None = None
    
    # Delivery method can be updated for drafts
    delivery_method: InvoiceDeliveryMethod | None = None
    
    # Draft status - can transition from draft to finalized
    is_draft: bool | None = None
    
    # Recipient information can be updated for drafts
    recipient_type: Optional[RecipientType] = None
    tenant_id: int | None = None
    ownership_entity_id: UUID | None = None
    vendor_id: int | None = None
    
    # Line items can be updated for drafts
    line_items: Optional[List[InvoiceLineItemCreate]] = None
    
    # Taxes can be updated for drafts
    taxes: Optional[List[InvoiceTaxDetailCreate]] = None

    @field_validator('amount')
    @classmethod
    def amount_must_be_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Amount must be greater than 0')
        return v

    @field_validator('due_date')
    @classmethod
    def due_date_must_not_be_earlier_than_issue_date(cls, v, info):
        # Skip validation if due_date is None
        if v is None:
            return v
        
        # Skip validation if issue_date is not provided or is None
        if 'issue_date' not in info.data or info.data['issue_date'] is None:
            return v
        
        # Validate that due_date is not earlier than issue_date
        if v < info.data['issue_date']:
            raise ValueError('Due date cannot be earlier than issue date')
        
        return v


class PropertyInfo(BaseModel):
    """Minimal property information for invoice responses"""
    id: int
    name: str


class TenantInfo(BaseModel):
    """Minimal tenant information for invoice responses"""
    id: int
    full_name: str


class OwnershipEntityInfo(BaseModel):
    """Minimal ownership entity information for invoice responses"""
    id: UUID
    name: str
    entity_type: str


class VendorInfo(BaseModel):
    """Minimal vendor information for invoice responses"""
    id: int
    company_name: str


class UserInfo(BaseModel):
    """Minimal user information for audit trail"""
    id: UUID
    email: str
    full_name: Optional[str] = None


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    
    id: int
    invoice_number: str
    amount: Decimal
    description: str
    issue_date: datetime
    due_date: datetime
    status: PaymentStatus = PaymentStatus.PENDING
    
    # Accounting context
    property_id: int | None = None
    unit_id: int | None = None
    
    # Delivery information (defaults to save_locally for backwards compatibility)
    delivery_method: InvoiceDeliveryMethod = InvoiceDeliveryMethod.SAVE_LOCALLY
    
    # Recipient information
    recipient_type: Optional[RecipientType] = None
    tenant_id: int | None = None
    ownership_entity_id: UUID | None = None
    vendor_id: int | None = None
    
    # Recipient snapshot (immutable)
    recipient_name: Optional[str] = None
    recipient_company: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_address_line1: Optional[str] = None
    recipient_address_line2: Optional[str] = None
    recipient_city: Optional[str] = None
    recipient_province: Optional[str] = None
    recipient_postal_code: Optional[str] = None
    recipient_country: Optional[str] = None
    recipient_tax_number: Optional[str] = None
    
    # Line items (NEW)
    line_items: List[InvoiceLineItemResponse] = Field(default_factory=list)
    
    # Tax details
    taxes: List[InvoiceTaxDetailResponse] = Field(default_factory=list)
    
    # Audit and workflow
    created_by_user_id: UUID | None = None
    is_draft: bool = True
    issued_at: Optional[datetime] = None
    issued_by_user_id: UUID | None = None
    
    # Stripe integration
    stripe_invoice_id: Optional[str] = None
    hosted_invoice_url: Optional[str] = None
    stripe_invoice_pdf: Optional[str] = None
    
    # PDF Storage (Brikli-generated PDFs)
    pdf_blob_url: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    
    # Metadata
    quickbooks_id: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Related entities
    property: Optional[PropertyInfo] = None
    tenant: Optional[TenantInfo] = None
    # ownership_entity: Optional[OwnershipEntityInfo] = None  # TODO: Add when needed
    # vendor: Optional[VendorInfo] = None  # TODO: Add when needed
    created_by: Optional[UserInfo] = None
    issued_by: Optional[UserInfo] = None

    @model_validator(mode='before')
    @classmethod
    def convert_nested_objects(cls, data):
        """
        Convert SQLModel ORM objects to Pydantic schema objects for nested relationships.
        
        Handles conversion of:
        - Property ORM object → PropertyInfo schema
        - Tenant ORM object → TenantInfo schema
        - User ORM objects → UserInfo schema
        - Line items and taxes are auto-handled by Pydantic
        
        This allows seamless use of model_validate() with ORM objects from database queries.
        """
        if isinstance(data, dict):
            return data
            
        # Convert the SQLModel object to a dictionary
        result = {}
        for field in cls.model_fields:
            value = getattr(data, field, None)
            
            # Handle nested property object
            if field == 'property' and value is not None:
                result[field] = {
                    'id': value.id,
                    'name': value.name
                }
            # Handle nested tenant object
            elif field == 'tenant' and value is not None:
                # TenantInfo expects 'full_name' not first/last
                if hasattr(value, 'tenant_type'):
                    if value.tenant_type.value == 'Company':
                        full_name = value.company_name or 'Company Tenant'
                    else:
                        first = getattr(value, 'first_name', '') or ''
                        last = getattr(value, 'last_name', '') or ''
                        full_name = f"{first} {last}".strip() or 'Tenant'
                else:
                    full_name = 'Unknown Tenant'
                    
                result[field] = {
                    'id': value.id,
                    'full_name': full_name
                }
            # created_by and issued_by are not ORM relationships, just UUID fields
            # They will be loaded manually in service layer if needed
            else:
                result[field] = value
                
        return result


# === CSV Import Models ===
class CSVInvoiceData(BaseModel):
    """Schema for invoice data from CSV import"""
    invoice_number: str
    amount: Decimal
    description: str
    issue_date: str  # Will be parsed to datetime
    due_date: str    # Will be parsed to datetime
    status: str = PaymentStatus.PENDING.value
    property_name: Optional[str] = None
    tenant_name: Optional[str] = None

    @field_validator('invoice_number')
    @classmethod
    def validate_invoice_number_length(cls, v):
        if v and len(v) > 100:
            raise ValueError('Invoice number must be 100 characters or less')
        return v
    
    @field_validator('description')
    @classmethod
    def validate_description_length(cls, v):
        if v and len(v) > 500:
            raise ValueError('Description must be 500 characters or less')
        return v
    
    @field_validator('property_name', 'tenant_name')
    @classmethod
    def validate_name_length(cls, v):
        if v and len(v) > 255:
            raise ValueError('Name must be 255 characters or less')
        return v

    @field_validator('amount')
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than 0')
        return v
    
    @field_validator('issue_date', 'due_date')
    @classmethod
    def validate_date_format(cls, v):
        """Validate date string follows expected formats."""
        if not v:
            raise ValueError('Date is required')
        
        # Check for common date formats
        import re
        valid_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
            r'^\d{2}/\d{2}/\d{4}$',  # MM/DD/YYYY or DD/MM/YYYY
            r'^\d{2}-\d{2}-\d{4}$',  # MM-DD-YYYY or DD-MM-YYYY
        ]
        
        if not any(re.match(pattern, v) for pattern in valid_patterns):
            raise ValueError(f'Date format not recognized. Expected formats: YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY')
        
        return v


class CSVImportError(BaseModel):
    """Schema for CSV import error details"""
    row_number: int
    error_message: str


class CSVImportRequest(BaseModel):
    """Request schema for CSV import"""
    invoices: list[CSVInvoiceData]


class CSVImportResult(BaseModel):
    """Result schema for CSV import"""
    total_rows: int
    successful_imports: int
    failed_imports: int
    errors: list[CSVImportError]
    created_invoice_ids: list[int]


class SecureInvoicePdfUrlResponse(BaseModel):
    """Response schema for secure invoice PDF URL generation with SAS token"""
    secure_url: str = Field(description="Azure Blob URL with SAS token for secure PDF access")
    expires_at: str = Field(description="ISO datetime when the SAS token expires")
    expires_in_seconds: int = Field(description="Seconds until the SAS token expires")
