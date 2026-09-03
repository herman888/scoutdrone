"""
Stripe Customer Management

Centralized customer creation and management for all Stripe operations.
Reusable across:
- Invoice system (tenants, vendors, ownership entities)
- Rent payments (future enhancement)
- Subscription billing (users)

Architecture:
- Lazy initialization pattern (create only when first needed)
- Idempotent operations (safe to call multiple times)
- Metadata tracking for Brikli context
"""

import logging
from typing import Union

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.stripe.client import get_stripe_client
from Backend.models.tenant import Tenant
from Backend.models.vendor import Vendor
from Backend.models.ownership_entity import OwnershipEntity

logger = logging.getLogger(__name__)

# Type alias for recipient models
RecipientModel = Union[Tenant, Vendor, OwnershipEntity]


async def get_or_create_stripe_customer(
    recipient: RecipientModel,
    session: AsyncSession
) -> str:
    """
    Get existing Stripe Customer ID or create new customer (lazy initialization).
    
    This function implements the lazy-initialization pattern:
    - If recipient already has stripe_customer_id, return it
    - Otherwise, create Stripe Customer and store ID in database
    
    Reusable across:
    - Invoice system (this module)
    - Rent payment system (future enhancement)
    - Any payment collection that needs customer records
    
    Args:
        recipient: Tenant, Vendor, or OwnershipEntity instance
        session: Database session for saving stripe_customer_id
        
    Returns:
        Stripe Customer ID (cus_xxx)
        
    Raises:
        HTTPException: If Stripe API call fails
        
    Example:
        tenant = await session.get(Tenant, tenant_id)
        customer_id = await get_or_create_stripe_customer(tenant, session)
        # customer_id = "cus_xxx123"
    """
    # Check if customer already exists
    if recipient.stripe_customer_id:
        logger.info(f"Using existing Stripe Customer: {recipient.stripe_customer_id}")
        return recipient.stripe_customer_id
    
    # Determine recipient type and extract info
    recipient_type = type(recipient).__name__.lower()
    
    # Extract email and name based on recipient type
    if isinstance(recipient, Tenant):
        email = recipient.email
        if recipient.company_name:
            name = recipient.company_name
        else:
            name = f"{recipient.first_name or ''} {recipient.last_name or ''}".strip()
        description = f"Tenant: {name}"
        
    elif isinstance(recipient, Vendor):
        email = recipient.email
        name = recipient.company_name
        description = f"Vendor: {name} ({recipient.trade_category})"
        
    elif isinstance(recipient, OwnershipEntity):
        email = recipient.contact_email
        name = recipient.name
        description = f"Ownership Entity: {name} ({recipient.entity_type})"
        
    else:
        raise ValueError(f"Unsupported recipient type: {type(recipient)}")
    
    # Validate required fields
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create Stripe Customer: {recipient_type} has no email address"
        )
    
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create Stripe Customer: {recipient_type} has no name"
        )
    
    # Create Stripe Customer
    try:
        stripe_client = get_stripe_client()
        
        logger.info(f"Creating Stripe Customer for {recipient_type} ID {recipient.id}")
        
        customer = await stripe_client.customers.create(
            email=email,
            name=name,
            description=description,
            metadata={
                "brikli_recipient_id": str(recipient.id),
                "brikli_recipient_type": recipient_type,
                "brikli_platform": "true"
            }
        )
        
        logger.info(f"✅ Created Stripe Customer: {customer.id} for {recipient_type} {recipient.id}")
        
        # Save stripe_customer_id to database
        recipient.stripe_customer_id = customer.id
        session.add(recipient)
        await session.commit()
        await session.refresh(recipient)
        
        return customer.id
        
    except Exception as e:
        logger.error(f"Failed to create Stripe Customer for {recipient_type} {recipient.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Stripe Customer: {str(e)}"
        )
