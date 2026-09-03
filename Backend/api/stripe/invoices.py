"""
Stripe Invoice Management for Accounting Module

Handles creation and finalization of Stripe Invoices for:
- Tenant billing
- Vendor payments
- Ownership entity invoices

Integrates with:
- Backend/api/stripe/customers.py for customer management
- Backend/api/accounting/invoices/service.py for Brikli invoice logic
- Backend/api/billing/webhook_handlers.py for payment status updates

Architecture:
- Clean separation between Stripe API calls and business logic
- Reusable invoice creation functions
- Email notifications via notification service
"""

import logging
from typing import Tuple
from datetime import datetime, UTC

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from Backend.api.stripe.client import get_stripe_client
from Backend.api.stripe.customers import get_or_create_stripe_customer, RecipientModel
from Backend.models.accounting.invoice import Invoice
from Backend.models.tenant import Tenant
from Backend.models.vendor import Vendor
from Backend.models.ownership_entity import OwnershipEntity
from Backend.models.user import User
from Backend.models.property import Property

logger = logging.getLogger(__name__)


async def get_recipient_for_invoice(
    invoice: Invoice,
    session: AsyncSession
) -> RecipientModel:
    """
    Fetch the recipient (tenant/vendor/ownership_entity) for an invoice.
    
    Args:
        invoice: Invoice instance with recipient IDs populated
        session: Database session
        
    Returns:
        Recipient model instance
        
    Raises:
        HTTPException: If no recipient found or invalid recipient type
    """
    if invoice.recipient_type == "tenant" and invoice.tenant_id:
        result = await session.execute(
            select(Tenant).where(Tenant.id == invoice.tenant_id)
        )
        recipient = result.scalar_one_or_none()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {invoice.tenant_id} not found"
            )
        return recipient
        
    elif invoice.recipient_type == "vendor" and invoice.vendor_id:
        result = await session.execute(
            select(Vendor).where(Vendor.id == invoice.vendor_id)
        )
        recipient = result.scalar_one_or_none()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Vendor {invoice.vendor_id} not found"
            )
        return recipient
        
    elif invoice.recipient_type == "ownership_entity" and invoice.ownership_entity_id:
        result = await session.execute(
            select(OwnershipEntity).where(OwnershipEntity.id == invoice.ownership_entity_id)
        )
        recipient = result.scalar_one_or_none()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ownership Entity {invoice.ownership_entity_id} not found"
            )
        return recipient
        
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invoice has no valid recipient (type: {invoice.recipient_type})"
        )


async def create_stripe_invoice_from_brikli(
    invoice: Invoice,
    customer_id: str,
    session: AsyncSession
) -> Tuple[str, str, str]:
    """
    Create Stripe Invoice from Brikli invoice data.
    
    Converts Brikli invoice with line items and taxes into Stripe Invoice API format.
    Stripe Invoice workflow:
    1. Create invoice (auto_advance=False for manual control)
    2. Add line items as InvoiceItems
    3. Add taxes as separate InvoiceItems
    4. Finalize invoice (locks it and generates hosted page)
    5. Return hosted_invoice_url and invoice_pdf
    
    Args:
        invoice: Brikli Invoice instance (with line_items and taxes loaded)
        customer_id: Stripe Customer ID
        session: Database session
        
    Returns:
        Tuple of (stripe_invoice_id, hosted_invoice_url, invoice_pdf)
        
    Raises:
        HTTPException: If Stripe API call fails
        
    Example:
        stripe_id, url, pdf = await create_stripe_invoice_from_brikli(invoice, "cus_xxx", session)
    """
    try:
        stripe_client = get_stripe_client()
        
        logger.info(f"Creating Stripe Invoice for Brikli invoice {invoice.invoice_number}")
        
        # ========================================================================
        # Step 1: Create Stripe Invoice (draft state)
        # ========================================================================
        stripe_invoice = await stripe_client.invoices.create(
            customer=customer_id,
            auto_advance=False,  # Manual finalization for control
            collection_method='send_invoice',  # Email invoice with payment link
            days_until_due=0,  # Due immediately (can customize later)
            description=invoice.description or f"Invoice {invoice.invoice_number}",
            metadata={
                "brikli_invoice_id": str(invoice.id),
                "brikli_invoice_number": invoice.invoice_number,
                "brikli_property_id": str(invoice.property_id) if invoice.property_id else None,
                "invoice_type": "accounting",  # Distinguish from subscription invoices
            },
            # Set invoice dates
            due_date=int(invoice.due_date.timestamp()),
        )
        
        logger.info(f"Created Stripe Invoice: {stripe_invoice.id}")
        
        # ========================================================================
        # Step 2: Add line items as InvoiceItems
        # ========================================================================
        for line_item in invoice.line_items:
            await stripe_client.invoice_items.create(
                customer=customer_id,
                invoice=stripe_invoice.id,
                description=line_item.description,
                quantity=int(line_item.quantity),
                unit_amount=int(float(line_item.unit_price) * 100),  # Convert to cents
                currency='cad',  # TODO: Make configurable
                metadata={
                    "brikli_line_item_id": str(line_item.id),
                    "is_taxable": str(line_item.is_taxable),
                }
            )
        
        logger.info(f"Added {len(invoice.line_items)} line items to Stripe Invoice")
        
        # ========================================================================
        # Step 3: Add taxes as separate InvoiceItems
        # ========================================================================
        for tax in invoice.taxes:
            await stripe_client.invoice_items.create(
                customer=customer_id,
                invoice=stripe_invoice.id,
                description=f"{tax.tax_name} ({tax.tax_rate}%)",
                amount=int(float(tax.tax_amount) * 100),  # Convert to cents
                currency='cad',
                metadata={
                    "brikli_tax_detail_id": str(tax.id),
                    "tax_name": tax.tax_name,
                    "tax_rate": str(tax.tax_rate),
                }
            )
        
        logger.info(f"Added {len(invoice.taxes)} tax items to Stripe Invoice")
        
        # ========================================================================
        # Step 4: Finalize Stripe Invoice
        # ========================================================================
        finalized_invoice = await stripe_client.invoices.finalize_invoice(
            stripe_invoice.id
        )
        
        logger.info(f"✅ Finalized Stripe Invoice: {finalized_invoice.id}")
        logger.info(f"   Hosted URL: {finalized_invoice.hosted_invoice_url}")
        
        return (
            finalized_invoice.id,
            finalized_invoice.hosted_invoice_url,
            finalized_invoice.invoice_pdf
        )
        
    except Exception as e:
        logger.error(f"Failed to create Stripe Invoice: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Stripe Invoice: {str(e)}"
        )


async def finalize_and_send_invoice(
    invoice_id: int,
    user_id: str,
    session: AsyncSession
) -> Invoice:
    """
    Finalize Brikli invoice and create corresponding Stripe Invoice.
    
    Complete workflow:
    1. Validate invoice is in draft state
    2. Validate user has permission to finalize
    3. Get recipient and ensure email exists
    4. Get or create Stripe Customer for recipient
    5. Create Stripe Invoice with line items and taxes
    6. Update Brikli invoice with Stripe data and mark as issued
    7. Send email notification
    
    Args:
        invoice_id: Brikli invoice ID
        user_id: User finalizing the invoice
        session: Database session
        
    Returns:
        Updated Invoice instance with Stripe fields populated
        
    Raises:
        HTTPException: If validation fails or Stripe API calls fail
        
    Example:
        invoice = await finalize_and_send_invoice(123, user_id, session)
        print(invoice.hosted_invoice_url)  # Send this to recipient
    """
    # ========================================================================
    # Step 1: Load invoice with relationships
    # ========================================================================
    stmt = select(Invoice).options(
        selectinload(getattr(Invoice, "line_items")),
        selectinload(getattr(Invoice, "taxes"))
    ).where(Invoice.id == invoice_id)
    
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found"
        )
    
    # ========================================================================
    # Step 2: Validate invoice is draft
    # ========================================================================
    if not invoice.is_draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is already finalized and cannot be modified"
        )
    
    # ========================================================================
    # Step 3: Validate user has permission (ownership check)
    # ========================================================================
    if str(invoice.created_by_user_id) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only finalize invoices you created"
        )
    
    # ========================================================================
    # Step 4: Validate invoice has line items
    # ========================================================================
    if not invoice.line_items or len(invoice.line_items) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot finalize invoice: no line items"
        )
    
    # ========================================================================
    # Step 5: Get recipient
    # ========================================================================
    recipient = await get_recipient_for_invoice(invoice, session)
    
    # ========================================================================
    # Step 6: Get or create Stripe Customer
    # ========================================================================
    customer_id = await get_or_create_stripe_customer(recipient, session)
    
    # ========================================================================
    # Step 7: Create Stripe Invoice
    # ========================================================================
    stripe_invoice_id, hosted_invoice_url, invoice_pdf = await create_stripe_invoice_from_brikli(
        invoice, customer_id, session
    )
    
    # ========================================================================
    # Step 8: Update Brikli invoice with Stripe data and mark as issued
    # ========================================================================
    from uuid import UUID
    
    invoice.stripe_invoice_id = stripe_invoice_id
    invoice.hosted_invoice_url = hosted_invoice_url
    invoice.stripe_invoice_pdf = invoice_pdf
    invoice.is_draft = False
    invoice.issued_at = datetime.now(UTC)
    invoice.issued_by_user_id = UUID(user_id)
    
    session.add(invoice)
    await session.commit()
    await session.refresh(invoice)
    
    logger.info(
        f"✅ Invoice {invoice.invoice_number} finalized and sent | "
        f"Stripe Invoice: {stripe_invoice_id} | "
        f"Hosted URL: {hosted_invoice_url}"
    )
    
    # ========================================================================
    # Step 9: Send email notification to recipient
    # ========================================================================
    try:
        await send_invoice_email(invoice, recipient, hosted_invoice_url, session)
    except Exception as e:
        # Log error but don't fail the entire operation
        logger.error(f"Failed to send invoice email: {str(e)}", exc_info=True)
    
    return invoice


async def send_invoice_email(
    invoice: Invoice,
    recipient: RecipientModel,
    hosted_invoice_url: str,
    session: AsyncSession
) -> None:
    """
    Send invoice notification email to recipient.
    
    Uses Brikli email template system to send a professional notification
    with a link to the Stripe hosted invoice page.
    
    Args:
        invoice: Invoice instance
        recipient: Recipient (Tenant/Vendor/OwnershipEntity)
        hosted_invoice_url: Stripe hosted invoice URL
        session: Database session
        
    Raises:
        Exception: If email sending fails (non-critical, logged only)
    """
    from Backend.api.notifications.email_templates import create_invoice_notification_email
    from Backend.api.notifications.sendgrid_service import SendGridService
    
    # Extract recipient email
    recipient_email = None
    recipient_name = invoice.recipient_name or "Customer"
    
    if isinstance(recipient, Tenant):
        recipient_email = recipient.email
    elif isinstance(recipient, Vendor):
        recipient_email = recipient.email
    elif isinstance(recipient, OwnershipEntity):
        recipient_email = recipient.contact_email
    
    if not recipient_email:
        logger.warning(
            f"No email address for recipient of invoice {invoice.invoice_number}. "
            "Skipping email notification."
        )
        return
    
    # Get property name for context
    property_name = None
    if invoice.property_id:
        property_result = await session.execute(
            select(Property).where(Property.id == invoice.property_id)
        )
        property = property_result.scalar_one_or_none()
        if property:
            property_name = property.name
    
    # Get landlord name
    landlord_name = None
    if invoice.created_by_user_id:
        user_result = await session.execute(
            select(User).where(User.id == invoice.created_by_user_id)
        )
        landlord_user = user_result.scalar_one_or_none()
        if landlord_user:
            # Build full name from first/last name or use email
            if landlord_user.first_name and landlord_user.last_name:
                landlord_name = f"{landlord_user.first_name} {landlord_user.last_name}"
            elif landlord_user.first_name:
                landlord_name = landlord_user.first_name
            else:
                landlord_name = landlord_user.email
    
    # Format amount
    amount = f"${float(invoice.amount):,.2f}"
    
    # Format due date
    due_date = invoice.due_date.strftime("%B %d, %Y")
    
    # Generate email HTML
    email_html = create_invoice_notification_email(
        recipient_name=recipient_name,
        invoice_number=invoice.invoice_number,
        amount=amount,
        due_date=due_date,
        hosted_invoice_url=hosted_invoice_url,
        property_name=property_name,
        landlord_name=landlord_name,
        invoice_description=invoice.description
    )
    
    # Send email
    email_service = SendGridService()
    await email_service.send_raw_email(
        to_email=recipient_email,
        to_name=recipient_name,
        subject=f"New Invoice {invoice.invoice_number}",
        html_content=email_html
    )
    
    logger.info(f"✉️ Invoice notification email sent to {recipient_email}")
