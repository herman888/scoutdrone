"""
Recipient resolution logic for invoices.

This module handles resolving and snapshotting recipient details
(tenants, ownership entities, vendors) for invoice audit trail.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from Backend.models.tenant import Tenant
from Backend.models.ownership_entity import OwnershipEntity
from Backend.models.vendor import Vendor
from .schemas import InvoiceCreate


async def resolve_recipient_snapshot(
    session: AsyncSession,
    invoice_data: InvoiceCreate
) -> dict:
    """
    Resolve recipient details and create an immutable snapshot.
    
    Fetches recipient data from DB based on recipient_type and ID,
    then returns a dictionary of snapshot fields.
    
    Args:
        session: Database session
        invoice_data: Invoice creation data with recipient info
    
    Returns:
        dict with recipient_name, recipient_company, recipient_email, etc.
    """
    snapshot = {}
    
    if invoice_data.recipient_type == 'tenant' and invoice_data.tenant_id:
        snapshot = await _resolve_tenant_snapshot(session, invoice_data.tenant_id)
    
    elif invoice_data.recipient_type == 'ownership_entity' and invoice_data.ownership_entity_id:
        snapshot = await _resolve_ownership_entity_snapshot(session, invoice_data.ownership_entity_id)
    
    elif invoice_data.recipient_type == 'vendor' and invoice_data.vendor_id:
        snapshot = await _resolve_vendor_snapshot(session, invoice_data.vendor_id)
    
    return snapshot


async def _resolve_tenant_snapshot(
    session: AsyncSession,
    tenant_id: int
) -> dict:
    """
    Resolve tenant details into recipient snapshot fields.
    
    Args:
        session: Database session
        tenant_id: Tenant ID
    
    Returns:
        dict with recipient_* fields
    """
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    tenant = (await session.execute(stmt)).scalar_one_or_none()
    
    if not tenant:
        return {}
    
    snapshot = {}
    
    # Get full name based on tenant type
    if hasattr(tenant, 'tenant_type') and tenant.tenant_type.value == 'Company':
        snapshot['recipient_name'] = tenant.company_name or 'Company Tenant'
        snapshot['recipient_company'] = tenant.company_name
    else:
        first = getattr(tenant, 'first_name', '') or ''
        last = getattr(tenant, 'last_name', '') or ''
        snapshot['recipient_name'] = f"{first} {last}".strip() or 'Tenant'
    
    # Contact info
    snapshot['recipient_email'] = getattr(tenant, 'email', None)
    
    # Address (if tenant model has these fields)
    # Note: Tenant model may not have address fields, so use getattr with None
    # In a real system, you'd fetch from associated lease/unit
    
    return snapshot


async def _resolve_ownership_entity_snapshot(
    session: AsyncSession,
    ownership_entity_id
) -> dict:
    """
    Resolve ownership entity details into recipient snapshot fields.
    
    Args:
        session: Database session
        ownership_entity_id: OwnershipEntity UUID
    
    Returns:
        dict with recipient_* fields
    """
    stmt = select(OwnershipEntity).where(OwnershipEntity.id == ownership_entity_id)
    entity = (await session.execute(stmt)).scalar_one_or_none()
    
    if not entity:
        return {}
    
    snapshot = {
        'recipient_name': entity.name,
        'recipient_company': entity.legal_name or entity.name,
        'recipient_email': entity.contact_email,
        'recipient_address_line1': entity.address,
        'recipient_city': entity.city,
        'recipient_province': entity.province,
        'recipient_postal_code': entity.postal_code,
        'recipient_country': entity.country or 'Canada',
        'recipient_tax_number': entity.tax_id
    }
    
    return snapshot


async def _resolve_vendor_snapshot(
    session: AsyncSession,
    vendor_id: int
) -> dict:
    """
    Resolve vendor details into recipient snapshot fields.
    
    Args:
        session: Database session
        vendor_id: Vendor ID
    
    Returns:
        dict with recipient_* fields
    """
    stmt = select(Vendor).where(Vendor.id == vendor_id)
    vendor = (await session.execute(stmt)).scalar_one_or_none()
    
    if not vendor:
        return {}
    
    snapshot = {
        'recipient_name': getattr(vendor, 'contact_person', None) or vendor.company_name,
        'recipient_company': vendor.company_name,
        'recipient_email': getattr(vendor, 'email', None),
        # Vendors may have address fields - add if they exist in your schema
    }
    
    return snapshot
