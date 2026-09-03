"""Helper functions for invoice operations."""
import logging
from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, inspect, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from Backend.config import settings
from Backend.models.accounting.invoice import Invoice
from Backend.models.enums import UserType
from Backend.models.lease import Lease, LeaseStatus
from Backend.models.property import Property
from Backend.models.tenant import Tenant
from Backend.models.user import User


logger = logging.getLogger(__name__)


async def check_invoice_ownership(
    invoice: Invoice,
    current_user: User,
    session: AsyncSession
) -> None:
    """
    Checks if the current user has permission to access/modify an invoice.
    
    Args:
        invoice: The invoice to check ownership for
        current_user: The user making the request
        session: Database session
        
    Raises:
        HTTPException: If user doesn't have permission
    """
    if current_user.user_type == UserType.ADMIN:
        return  # Admins can access all invoices
    
    if current_user.user_type == UserType.TENANT:
        # Tenants can only access their own invoices
        tenant_query = select(Tenant).where(col(Tenant.user_id) == current_user.id)
        user_tenant = await session.scalar(tenant_query)
        if not user_tenant or invoice.tenant_id != user_tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this invoice"
            )
    
    elif current_user.user_type == UserType.LANDLORD:
        # Landlords can only access invoices for their properties
        if invoice.property_id:
            property_query = select(Property).where(
                and_(
                    col(Property.id) == invoice.property_id,
                    col(Property.user_id) == current_user.id
                )
            )
            property_owned = await session.scalar(property_query)
            if not property_owned:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to access this invoice"
                )
        # Allow access to invoices with NULL property_id (unassigned invoices)


def build_invoice_response(invoice: Invoice) -> dict:
    """
    Builds a standardized invoice response dictionary.
    
    Args:
        invoice: The invoice ORM object
        
    Returns:
        Dictionary with invoice data formatted for API response
    """
    from Backend.models.accounting.invoice import InvoiceDeliveryMethod
    
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "amount": invoice.amount,  # Keep as Decimal to preserve precision
        "description": invoice.description,
        "issue_date": invoice.issue_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "status": invoice.status.value if hasattr(invoice.status, 'value') else invoice.status,
        "delivery_method": invoice.delivery_method if hasattr(invoice, 'delivery_method') and invoice.delivery_method else InvoiceDeliveryMethod.SAVE_LOCALLY.value,
        "property_id": invoice.property_id,
        "unit_id": invoice.unit_id,
        
        # Recipient information
        "recipient_type": invoice.recipient_type.value if hasattr(invoice, 'recipient_type') and invoice.recipient_type and hasattr(invoice.recipient_type, 'value') else invoice.recipient_type if hasattr(invoice, 'recipient_type') else None,
        "tenant_id": invoice.tenant_id,
        "ownership_entity_id": str(invoice.ownership_entity_id) if hasattr(invoice, 'ownership_entity_id') and invoice.ownership_entity_id else None,
        "vendor_id": invoice.vendor_id if hasattr(invoice, 'vendor_id') else None,
        
        # Recipient snapshot (immutable)
        "recipient_name": invoice.recipient_name if hasattr(invoice, 'recipient_name') else None,
        "recipient_company": invoice.recipient_company if hasattr(invoice, 'recipient_company') else None,
        "recipient_email": invoice.recipient_email if hasattr(invoice, 'recipient_email') else None,
        "recipient_address_line1": invoice.recipient_address_line1 if hasattr(invoice, 'recipient_address_line1') else None,
        "recipient_address_line2": invoice.recipient_address_line2 if hasattr(invoice, 'recipient_address_line2') else None,
        "recipient_city": invoice.recipient_city if hasattr(invoice, 'recipient_city') else None,
        "recipient_province": invoice.recipient_province if hasattr(invoice, 'recipient_province') else None,
        "recipient_postal_code": invoice.recipient_postal_code if hasattr(invoice, 'recipient_postal_code') else None,
        "recipient_country": invoice.recipient_country if hasattr(invoice, 'recipient_country') else None,
        "recipient_tax_number": invoice.recipient_tax_number if hasattr(invoice, 'recipient_tax_number') else None,
        
        # Line items (if loaded) - must include ALL fields from InvoiceLineItemResponse
        "line_items": [
            {
                "id": item.id,
                "invoice_id": item.invoice_id,
                "description": item.description,
                "quantity": item.quantity,  # Keep as Decimal for Pydantic
                "unit_price": item.unit_price,  # Keep as Decimal
                "line_total": item.line_total,  # Keep as Decimal
                "is_taxable": item.is_taxable,
                "expense_category": item.expense_category,
                "sort_order": item.sort_order,
                "created_at": item.created_at,
                "updated_at": item.updated_at
            }
            for item in invoice.line_items
        ] if hasattr(invoice, 'line_items') and invoice.line_items else [],
        
        # Taxes (if loaded) - must include ALL fields from InvoiceTaxDetailResponse
        "taxes": [
            {
                "id": tax.id,
                "invoice_id": tax.invoice_id,
                "tax_name": tax.tax_name,
                "tax_rate": tax.tax_rate,  # Keep as Decimal
                "tax_amount": tax.tax_amount  # Keep as Decimal
            }
            for tax in invoice.taxes
        ] if hasattr(invoice, 'taxes') and invoice.taxes else [],
        
        "quickbooks_id": invoice.quickbooks_id,
        "last_synced_at": invoice.last_synced_at.isoformat() if invoice.last_synced_at else None,
        
        # Workflow fields
        "is_draft": invoice.is_draft if hasattr(invoice, 'is_draft') else True,
        "issued_at": invoice.issued_at.isoformat() if hasattr(invoice, 'issued_at') and invoice.issued_at else None,
        "issued_by_user_id": str(invoice.issued_by_user_id) if hasattr(invoice, 'issued_by_user_id') and invoice.issued_by_user_id else None,
        "created_by_user_id": str(invoice.created_by_user_id) if hasattr(invoice, 'created_by_user_id') and invoice.created_by_user_id else None,
        
        # Stripe integration
        "stripe_invoice_id": invoice.stripe_invoice_id if hasattr(invoice, 'stripe_invoice_id') else None,
        "hosted_invoice_url": invoice.hosted_invoice_url if hasattr(invoice, 'hosted_invoice_url') else None,
        "stripe_invoice_pdf": invoice.stripe_invoice_pdf if hasattr(invoice, 'stripe_invoice_pdf') else None,
        
        # PDF information
        "pdf_blob_url": invoice.pdf_blob_url if hasattr(invoice, 'pdf_blob_url') else None,
        "pdf_generated_at": invoice.pdf_generated_at.isoformat() if hasattr(invoice, 'pdf_generated_at') and invoice.pdf_generated_at else None,
        
        "created_at": invoice.created_at.isoformat(),
        "updated_at": invoice.updated_at.isoformat(),
        # Include related data if loaded (check if relationship is loaded to avoid lazy loading)
        "property": {
            "id": invoice.property.id,
            "name": invoice.property.name
        } if hasattr(invoice, '__dict__') and 'property' in invoice.__dict__ and invoice.property else None,
        "tenant": {
            "id": invoice.tenant.id,
            "full_name": f"{invoice.tenant.first_name} {invoice.tenant.last_name}".strip()
        } if hasattr(invoice, '__dict__') and 'tenant' in invoice.__dict__ and invoice.tenant else None,
        "ownership_entity": {
            "id": str(invoice.ownership_entity.id),
            "name": invoice.ownership_entity.name
        } if hasattr(invoice, '__dict__') and 'ownership_entity' in invoice.__dict__ and invoice.ownership_entity else None,
        "vendor": {
            "id": invoice.vendor.id,
            "company_name": invoice.vendor.company_name
        } if hasattr(invoice, '__dict__') and 'vendor' in invoice.__dict__ and invoice.vendor else None
    }


async def infer_property_for_invoice(tenant: Tenant, current_user: User) -> int | None:
    """
    Attempts to determine the property ID associated with a tenant for invoice creation.
    
    Checks the tenant's current property and active leases, ensuring relationships are eagerly loaded to prevent inefficient queries. Returns the property ID if accessible by the current user (admin or property owner). Raises an HTTP 500 error if inference fails due to internal issues.
    """
    try:
        # Check if required relationships are eagerly loaded to prevent N+1 queries
        tenant_state = inspect(tenant)
        if tenant_state is not None:
            # Use 'in tenant_state.unloaded' for the most reliable check
            if "current_property" in tenant_state.unloaded:
                logger.error(
                    "tenant.current_property not eagerly loaded for tenant %s, which may cause N+1 queries.",
                    tenant.id
                )
                # In debug mode, fail fast to enforce the contract
                if settings.DEBUG:
                    raise RuntimeError(
                        f"tenant.current_property not eagerly loaded for tenant {tenant.id}. "
                        "Ensure selectinload(Tenant.current_property) is used in the query."
                    )
            
            if "leases" in tenant_state.unloaded:
                logger.error(
                    "tenant.leases not eagerly loaded for tenant %s, which may cause N+1 queries.",
                    tenant.id
                )
                # In debug mode, fail fast
                if settings.DEBUG:
                    raise RuntimeError(
                        f"tenant.leases not eagerly loaded for tenant {tenant.id}. "
                        "Ensure selectinload(Tenant.leases) is used in the query."
                    )
        
        # 1. Check the tenant's currently assigned property first.
        if tenant.current_property:
            if current_user.user_type == UserType.ADMIN or tenant.current_property.user_id == current_user.id:
                return tenant.current_property.id

        # 2. If no current property, check properties from the tenant's ACTIVE leases only.
        if tenant.leases:
            # Deterministically evaluate the *oldest* active lease first
            active_leases = sorted(
                (lease for lease in tenant.leases if lease.status == LeaseStatus.ACTIVE and lease.property),
                key=lambda lease: (lease.start_date or date.min)
            )
            for lease in active_leases:
                if current_user.user_type == UserType.ADMIN or lease.property.user_id == current_user.id:
                    return lease.property.id

    except RuntimeError:
        # Re-raise RuntimeError in debug mode to preserve debugging info
        if settings.DEBUG:
            raise
        # Convert to HTTP error in production
        logger.exception("Error inferring property for tenant %s", tenant.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to infer property for tenant – internal error."
        )
    except Exception:
        logger.exception("Error inferring property for tenant %s", tenant.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to infer property for tenant – internal error."
        )
    
    # Explicit return None if no property is found
    return None


async def apply_tenant_invoice_filters(
    filters: list, tenant_id: int | None, property_id: int | None, current_user: User, session: AsyncSession
):
    """
    Applies invoice query filters to restrict results to the current tenant user.
    
    Raises:
        HTTPException: If the user is not a tenant, attempts to access another tenant's invoices, or tries to filter by property.
    """
    tenant_query = select(Tenant).where(col(Tenant.user_id) == current_user.id)
    user_tenant = await session.scalar(tenant_query)
    
    if not user_tenant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access these invoices.")
    
    if tenant_id and tenant_id != user_tenant.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access these invoices.")
    
    filters.append(col(Invoice.tenant_id) == user_tenant.id)
    
    if property_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to filter invoices by property.")


async def apply_landlord_invoice_filters(
    filters: list, property_id: int | None, tenant_id: int | None, current_user: User, session: AsyncSession
) -> bool:
    """
    Applies invoice filters to restrict results to those associated with properties owned by the landlord.
    
    Returns:
        True if the landlord owns properties and filters are applied; False if the landlord owns no properties.
        
    Raises:
        HTTPException: If a property_id is provided but the landlord does not own the specified property.
    """
    # Check if landlord has any properties at all (lightweight check)
    has_properties_query = select(Property.id).where(col(Property.user_id) == current_user.id).limit(1)
    has_properties = await session.scalar(has_properties_query)
    
    if not has_properties:
        return False

    if property_id:
        # Verify specific property ownership using subquery
        property_owned = await session.scalar(
            select(Property.id).where(
                and_(
                    col(Property.id) == property_id,
                    col(Property.user_id) == current_user.id
                )
            )
        )
        if not property_owned:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this property.")
        filters.append(col(Invoice.property_id) == property_id)
        if tenant_id:
            filters.append(col(Invoice.tenant_id) == tenant_id)
    elif tenant_id:
        filters.append(col(Invoice.tenant_id) == tenant_id)
        # Use EXISTS correlated subquery for better performance and scalability
        filters.append(exists().where(
            and_(
                col(Property.id) == col(Invoice.property_id),
                col(Property.user_id) == current_user.id
            )
        ))
    else:
        # When no specific filters, include both:
        # 1. Invoices with NULL property_id (unassigned invoices)
        # 2. Invoices with property_id matching landlord's properties
        filters.append(or_(
            col(Invoice.property_id).is_(None),
            exists().where(
                and_(
                    col(Property.id) == col(Invoice.property_id),
                    col(Property.user_id) == current_user.id
                )
            )
        ))
    
    return True


def apply_admin_invoice_filters(filters: list, property_id: int | None, tenant_id: int | None):
    """
    Appends tenant and property filters to the invoice query for admin users.
    
    If tenant_id or property_id are provided, corresponding filters are added to the filters list.
    """
    if tenant_id:
        filters.append(col(Invoice.tenant_id) == tenant_id)
    if property_id:
        filters.append(col(Invoice.property_id) == property_id)
