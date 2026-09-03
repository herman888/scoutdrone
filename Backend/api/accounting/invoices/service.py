"""
Service layer for invoice operations.

This module contains the core business logic for creating and retrieving invoices,
handling property ownership validation, and applying role-based access control.
"""

import logging
from datetime import date, datetime, UTC
from typing import Optional
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from Backend.api.accounting.helpers import check_property_ownership
from Backend.config import settings
from Backend.models.accounting.common import PaymentStatus
from Backend.models.accounting.invoice import Invoice, InvoiceDeliveryMethod
from Backend.models.accounting.invoice_line_item import InvoiceLineItem
from Backend.models.enums import UserType
from Backend.models.lease import Lease
from Backend.models.property import Property
from Backend.models.tenant import Tenant
from Backend.models.user import User
from Backend.utils.datetime_utils import (
    date_to_utc_range, validate_business_datetime, validate_date_range
)

from .helpers import (
    infer_property_for_invoice,
    apply_tenant_invoice_filters,
    apply_landlord_invoice_filters,
    apply_admin_invoice_filters,
    build_invoice_response
)
from .schemas import InvoiceCreate, InvoiceResponse, InvoiceUpdate, CSVImportRequest, CSVImportResult
from Backend.models.accounting.invoice_tax_detail import InvoiceTaxDetail
from Backend.utils.tax_utils import quantize_2dp

# Import refactored modules
from .calculations import (
    calculate_line_items_subtotal,
    process_line_items_for_invoice,
    calculate_taxes_on_line_items,
    generate_invoice_description,
    calculate_invoice_taxes_legacy,
    determine_invoice_amounts_legacy
)
from .recipients import resolve_recipient_snapshot


logger = logging.getLogger(__name__)


async def _handle_invoice_delivery(
    invoice: Invoice,
    session: AsyncSession,
    current_user: User
) -> None:
    """
    Handle invoice delivery based on delivery_method.
    
    Delivery methods:
    - SAVE_LOCALLY: No action needed (invoice already in DB)
    - SEND_INVOICE: Send branded PDF invoice email (no payment required)
    - REQUEST_PAYMENT: Create Stripe invoice with payment link (requires Connect)
    
    Args:
        invoice: The finalized invoice
        session: Database session
        current_user: User finalizing the invoice
        
    Raises:
        HTTPException: If delivery fails or requirements not met
    """
    from Backend.api.stripe.client import get_stripe_client
    from Backend.api.rent_payments.connect_service import get_connected_account_for_landlord
    from decimal import Decimal
    
    delivery_method = invoice.delivery_method
    
    if delivery_method == InvoiceDeliveryMethod.SAVE_LOCALLY:
        # Generate and store PDF for later download (no email sent)
        logger.info(f"Invoice {invoice.invoice_number} saved locally - generating PDF for storage")
        
        try:
            from .pdf_service import generate_invoice_pdf, upload_invoice_pdf_to_storage
            
            # Generate PDF
            pdf_bytes = await generate_invoice_pdf(invoice, session)
            
            # Upload PDF to Azure Blob Storage for permanent storage
            blob_url = await upload_invoice_pdf_to_storage(
                pdf_bytes=pdf_bytes,
                invoice=invoice,
                user_id=current_user.id
            )
            
            # Save blob URL to database
            from Backend.utils.datetime_utils import utc_now
            invoice.pdf_blob_url = blob_url
            invoice.pdf_generated_at = utc_now()
            await session.commit()
            
            logger.info(f"📦 PDF generated and stored for local invoice: {invoice.invoice_number}")
            
        except Exception as e:
            # Log error but don't fail finalization - user can still download PDF later
            logger.error(f"Failed to generate/store PDF for local invoice {invoice.invoice_number}: {str(e)}")
        
        return
    
    # For email-based delivery methods, validate recipient email
    if not invoice.recipient_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot {delivery_method.value.replace('_', ' ')}: recipient email is required"
        )
    
    # Get Stripe client
    stripe_client = get_stripe_client()
    
    if delivery_method == InvoiceDeliveryMethod.SEND_INVOICE:
        # Send branded Brikli invoice via email with PDF attachment
        logger.info(f"Sending branded invoice email with PDF for {invoice.invoice_number}")
        
        try:
            from Backend.api.notifications.email_templates import (
                BrikliEmailTemplate,
                EmailSection,
                EmailCTA,
                EmailMetadataRow,
            )
            from Backend.api.notifications.sendgrid_service import SendGridService
            from .pdf_service import generate_invoice_pdf, upload_invoice_pdf_to_storage
            
            # Format invoice amount
            amount_str = f"${float(invoice.amount):,.2f}"
            
            # Build email content
            sections = [
                EmailSection(text=f"Please find your invoice {invoice.invoice_number} attached as a PDF."),
            ]
            
            metadata_rows = [
                EmailMetadataRow(label="Invoice Number", value=invoice.invoice_number, emoji="📄"),
                EmailMetadataRow(label="Amount", value=amount_str, emoji="💰"),
                EmailMetadataRow(label="Issue Date", value=invoice.issue_date.strftime("%B %d, %Y"), emoji="📅"),
                EmailMetadataRow(label="Due Date", value=invoice.due_date.strftime("%B %d, %Y"), emoji="⏰"),
            ]
            
            if invoice.description:
                sections.append(EmailSection(text=f"Description: {invoice.description}"))
            
            # Generate email HTML
            html_body = BrikliEmailTemplate.create_email(
                title=f"Invoice {invoice.invoice_number}",
                greeting=f"Hi {invoice.recipient_name or 'there'},",
                sections=sections,
                metadata=metadata_rows,
                cta=None,
                footer_note="Thank you for your business. If you have any questions, please contact us."
            )
            
            # Generate PDF
            logger.info(f"Generating PDF for invoice {invoice.invoice_number}")
            pdf_bytes = await generate_invoice_pdf(invoice, session)
            pdf_filename = f"Invoice-{invoice.invoice_number}.pdf"
            
            # Upload PDF to Azure Blob Storage for permanent storage
            try:
                blob_url = await upload_invoice_pdf_to_storage(
                    pdf_bytes=pdf_bytes,
                    invoice=invoice,
                    user_id=current_user.id
                )
                
                # Save blob URL to database
                from Backend.utils.datetime_utils import utc_now
                invoice.pdf_blob_url = blob_url
                invoice.pdf_generated_at = utc_now()
                await session.commit()
                
                logger.info(f"📦 PDF stored in blob storage: {invoice.invoice_number}")
            except Exception as blob_error:
                # Don't fail delivery if blob upload fails - PDF still sent via email
                logger.warning(f"Failed to upload PDF to blob storage (email will still be sent): {str(blob_error)}")
            
            # Build sender name for email subject
            landlord_name = f"{current_user.first_name} {current_user.last_name}".strip()
            if not landlord_name:
                landlord_name = "Brikli"
            
            # Send email with PDF attachment
            success = await SendGridService.send_email_with_attachment(
                to_email=invoice.recipient_email,
                to_name=invoice.recipient_name or invoice.recipient_company or "Customer",
                subject=f"Invoice {invoice.invoice_number} from {landlord_name}",
                html_content=html_body,
                attachment_bytes=pdf_bytes,
                attachment_filename=pdf_filename,
                metadata={
                    'invoice_id': str(invoice.id),
                    'invoice_number': invoice.invoice_number,
                    'delivery_method': 'send_invoice'
                }
            )
            
            if not success:
                raise Exception("Failed to send email via SendGrid")
            
            # Update invoice status to SENT and mark as finalized (no longer draft)
            from Backend.models.accounting.common import PaymentStatus
            invoice.status = PaymentStatus.SENT
            invoice.is_draft = False
            await session.commit()
            
            logger.info(f"✉️ Invoice email with PDF sent for {invoice.invoice_number}")
            
        except Exception as e:
            logger.error(f"Failed to send invoice email with PDF: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send invoice email: {str(e)}"
            )
    
    elif delivery_method == InvoiceDeliveryMethod.REQUEST_PAYMENT:
        # Create Stripe invoice with payment enabled (requires Connect)
        logger.info(f"Creating Stripe payment invoice for {invoice.invoice_number}")
        
        # Check if user has Stripe Connect account
        connect_account = await get_connected_account_for_landlord(str(current_user.id), session)
        if not connect_account or not connect_account.stripe_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stripe Connect account required for payment requests. Please connect your Stripe account first."
            )
        
        if not connect_account.charges_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your Stripe account is not yet enabled for charges. Please complete your Stripe onboarding."
            )
        
        try:
            # Find existing customer by email in the connected account
            existing_customers = await stripe_client.customers.list(
                email=invoice.recipient_email,
                limit=1,
                stripe_account=connect_account.stripe_account_id
            )
            
            if existing_customers.data:
                customer = existing_customers.data[0]
                logger.info(f"Found existing Stripe customer {customer.id} for email {invoice.recipient_email}")
            else:
                # Create Stripe customer if not found
                customer = await stripe_client.customers.create(
                    email=invoice.recipient_email,
                    name=invoice.recipient_name or invoice.recipient_company,
                    description=f"Customer for invoice {invoice.invoice_number}",
                    metadata={
                        'brikli_tenant_id': str(invoice.tenant_id) if invoice.tenant_id else None,
                        'brikli_invoice_id': str(invoice.id),
                    },
                    stripe_account=connect_account.stripe_account_id,
                )
                logger.info(f"Created new Stripe customer {customer.id} for email {invoice.recipient_email}")
            
            # Use the connected account's default currency for consistency
            currency = connect_account.default_currency.lower()
            
            # Create Stripe invoice with payment enabled
            stripe_invoice = await stripe_client.invoices.create(
                customer=customer.id,
                collection_method='charge_automatically',  # Enable online payments
                days_until_due=None,  # Immediate payment
                auto_advance=True,  # Automatically finalize
                currency=currency,  # Explicit currency to match invoice items
                description=invoice.description or f"Invoice {invoice.invoice_number}",
                metadata={
                    'invoice_type': 'accounting',  # CRITICAL: Routes webhook to accounting handler
                    'brikli_invoice_id': str(invoice.id),
                    'brikli_invoice_number': invoice.invoice_number,
                    'delivery_method': 'request_payment'
                },
                # Connect to landlord's Stripe account
                stripe_account=connect_account.stripe_account_id,
            )
            
            # Add line items to Stripe invoice
            if invoice.line_items:
                for line_item in invoice.line_items:
                    await stripe_client.invoice_items.create(
                        customer=customer.id,
                        invoice=stripe_invoice.id,
                        description=line_item.description,
                        amount=int(Decimal(str(line_item.unit_price)) * Decimal(str(line_item.quantity)) * 100),  # Convert to cents
                        currency=currency,  # Use connected account's currency
                        stripe_account=connect_account.stripe_account_id,
                    )
            
            # Add taxes if present
            if invoice.taxes:
                for tax_detail in invoice.taxes:
                    # Use the pre-calculated tax amount, do not recalculate on the total
                    tax_amount = int(Decimal(str(tax_detail.tax_amount)) * 100)  # Convert to cents
                    
                    await stripe_client.invoice_items.create(
                        customer=customer.id,
                        invoice=stripe_invoice.id,
                        description=f"{tax_detail.tax_name} ({tax_detail.tax_rate}%)",
                        amount=tax_amount,
                        currency=currency,  # Use connected account's currency
                        stripe_account=connect_account.stripe_account_id,
                    )
            
            # Finalize the invoice (auto-sends for charge_automatically collection method)
            finalized_invoice = await stripe_client.invoices.finalize_invoice(stripe_invoice.id, stripe_account=connect_account.stripe_account_id)
            
            # Store Stripe invoice reference, update status to SENT, and mark as finalized
            from Backend.models.accounting.common import PaymentStatus
            invoice.stripe_invoice_id = finalized_invoice.id
            invoice.hosted_invoice_url = finalized_invoice.hosted_invoice_url
            invoice.stripe_invoice_pdf = finalized_invoice.invoice_pdf
            invoice.status = PaymentStatus.SENT
            invoice.is_draft = False
            await session.commit()
            
            logger.info(f"💳 Stripe payment invoice created and sent for {invoice.invoice_number} (Stripe ID: {finalized_invoice.id})")
            
            # Optional: Also send branded Brikli PDF alongside Stripe invoice
            # This gives customers both Stripe's hosted payment page AND a professional PDF
            try:
                from Backend.api.notifications.email_templates import (
                    BrikliEmailTemplate,
                    EmailSection,
                    EmailCTA,
                    EmailMetadataRow,
                )
                from Backend.api.notifications.sendgrid_service import SendGridService
                from .pdf_service import generate_invoice_pdf, upload_invoice_pdf_to_storage
                
                amount_str = f"${float(invoice.amount):,.2f}"
                
                sections = [
                    EmailSection(text=f"Your invoice {invoice.invoice_number} is ready for payment."),
                    EmailSection(text="Click the button below to pay securely online, or view the attached PDF for details."),
                ]
                
                metadata_rows = [
                    EmailMetadataRow(label="Invoice Number", value=invoice.invoice_number, emoji="📄"),
                    EmailMetadataRow(label="Amount Due", value=amount_str, emoji="💰"),
                    EmailMetadataRow(label="Due Date", value=invoice.due_date.strftime("%B %d, %Y"), emoji="⏰"),
                ]
                
                # Create payment CTA with Stripe hosted invoice URL
                hosted_url = invoice.hosted_invoice_url
                cta = None
                if hosted_url:
                    cta = EmailCTA(
                        text=f"Pay {amount_str} Now",
                        url=hosted_url
                    )
                
                html_body = BrikliEmailTemplate.create_email(
                    title=f"Payment Required: Invoice {invoice.invoice_number}",
                    greeting=f"Hi {invoice.recipient_name or 'there'},",
                    sections=sections,
                    metadata=metadata_rows,
                    cta=cta,
                    footer_note="Secure payment powered by Stripe. Your payment information is encrypted and secure."
                )
                
                # Generate PDF
                pdf_bytes = await generate_invoice_pdf(invoice, session)
                pdf_filename = f"Invoice-{invoice.invoice_number}.pdf"
                
                # Upload PDF to Azure Blob Storage for permanent storage
                try:
                    blob_url = await upload_invoice_pdf_to_storage(
                        pdf_bytes=pdf_bytes,
                        invoice=invoice,
                        user_id=current_user.id
                    )
                    
                    # Save blob URL to database
                    from Backend.utils.datetime_utils import utc_now
                    invoice.pdf_blob_url = blob_url
                    invoice.pdf_generated_at = utc_now()
                    await session.commit()
                    
                    logger.info(f"📦 PDF stored in blob storage: {invoice.invoice_number}")
                except Exception as blob_error:
                    # Don't fail delivery if blob upload fails
                    logger.warning(f"Failed to upload PDF to blob storage (email will still be sent): {str(blob_error)}")
                
                # Build sender name for email subject
                landlord_name = f"{current_user.first_name} {current_user.last_name}".strip()
                if not landlord_name:
                    landlord_name = "Brikli"
                
                # Send branded email with PDF (in addition to Stripe's email)
                await SendGridService.send_email_with_attachment(
                    to_email=invoice.recipient_email,
                    to_name=invoice.recipient_name or invoice.recipient_company or "Customer",
                    subject=f"Payment Required: Invoice {invoice.invoice_number} from {landlord_name}",
                    html_content=html_body,
                    attachment_bytes=pdf_bytes,
                    attachment_filename=pdf_filename,
                    metadata={
                        'invoice_id': str(invoice.id),
                        'invoice_number': invoice.invoice_number,
                        'delivery_method': 'request_payment',
                        'stripe_invoice_id': finalized_invoice.id
                    }
                )
                
                logger.info(f"📧 Branded payment invoice with PDF sent for {invoice.invoice_number}")
                
            except Exception as email_error:
                # Don't fail the whole operation if branded email fails
                # Stripe already sent its own invoice email
                logger.warning(f"Failed to send branded payment email (Stripe invoice still sent): {str(email_error)}")
            
        except Exception as e:
            logger.error(f"Failed to create Stripe payment invoice: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create payment invoice: {str(e)}"
            )


async def get_smart_tax_for_invoice_creation(
    session: AsyncSession,
    user_id: str,
    property_id: Optional[int],
    invoice_data: InvoiceCreate
) -> InvoiceCreate:
    """
    Auto-populate tax data for invoice creation if none provided.
    
    Uses smart tax selection if invoice has no tax details specified.
    Returns the invoice_data with tax details populated if applicable.
    """
    from Backend.api.accounting.tax_preferences.service import get_smart_tax_for_invoice
    
    # If tax details are already provided, don't override
    if invoice_data.taxes and len(invoice_data.taxes) > 0:
        return invoice_data
    
    # Get smart tax recommendation
    smart_tax = await get_smart_tax_for_invoice(session, user_id, property_id)
    if not smart_tax:
        return invoice_data  # No smart recommendation available
    
    tax_name, tax_rate = smart_tax
    
    # Create tax detail from smart recommendation
    from Backend.models.accounting.invoice_tax_detail import InvoiceTaxDetailCreate
    smart_tax_detail = InvoiceTaxDetailCreate(
        tax_name=tax_name,
        tax_rate=tax_rate,
        # tax_amount will be calculated by the tax calculation logic
    )
    
    # Create new invoice data with smart tax applied
    invoice_with_tax = invoice_data.model_copy()
    invoice_with_tax.taxes = [smart_tax_detail]
    
    logger.info(f"Auto-populated smart tax for invoice: {tax_name} {tax_rate}%")
    return invoice_with_tax


async def create_invoice(
    invoice_data: InvoiceCreate,
    session: AsyncSession,
    current_user: User
) -> InvoiceResponse:
    """
    Creates a new invoice with tax support.
    
    Auto-populates smart tax data if none provided, allows admin and landlord users 
    to create invoices. Invoices can be created with or without tenant/property 
    associations, supporting imports from external systems like QuickBooks or Stripe.

    Args:
        invoice_data: The invoice creation data.
        session: The database session.
        current_user: The user creating the invoice.

    Returns:
        The created invoice as an InvoiceResponse.

    Raises:
        HTTPException: For authorization, validation, or processing errors.
    """
    if current_user.user_type not in [UserType.ADMIN, UserType.LANDLORD]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create invoices")

    # If tenant_id is provided without property_id, try to infer property
    final_property_id = invoice_data.property_id
    if invoice_data.tenant_id and not final_property_id:
        tenant_query = select(Tenant).options(
            selectinload(getattr(Tenant, "leases")).selectinload(getattr(Lease, "property")),
            selectinload(getattr(Tenant, "current_property"))
        ).where(col(Tenant.id) == invoice_data.tenant_id)
        tenant = (await session.execute(tenant_query)).scalar_one_or_none()

        if tenant:
            inferred_property_id = await infer_property_for_invoice(tenant, current_user)
            if inferred_property_id:
                final_property_id = inferred_property_id

    # If property_id is set (original or inferred), verify ownership
    if final_property_id:
        await check_property_ownership(final_property_id, session, current_user)
        
    # Update invoice_data with final property_id if it was inferred
    if final_property_id != invoice_data.property_id:
        invoice_data = invoice_data.model_copy(update={"property_id": final_property_id})

    # Auto-populate smart tax if no tax details provided
    invoice_data = await get_smart_tax_for_invoice_creation(
        session=session,
        user_id=str(current_user.id),
        property_id=final_property_id,
        invoice_data=invoice_data
    )

    try:
        # Process line items if provided (NEW invoice system)
        line_item_objects, line_items_subtotal = process_line_items_for_invoice(invoice_data.line_items)
        
        # Determine subtotal:
        # - If line items exist: use line items subtotal
        # - Else: use legacy amount field
        if line_items_subtotal > 0:
            subtotal = line_items_subtotal
        else:
            # Backward compatibility: use amount as subtotal if no line items
            subtotal = quantize_2dp(invoice_data.amount)
        
        # Calculate taxes (applies only to taxable line items)
        tax_orm_objects, total_tax = calculate_taxes_on_line_items(
            line_items=line_item_objects,
            tax_details=invoice_data.taxes or [],
            fallback_subtotal=subtotal
        )
        
        # Calculate final amount (grand total)
        final_amount = quantize_2dp(subtotal + total_tax)
        
        # Resolve recipient snapshot if recipient provided
        recipient_snapshot = await resolve_recipient_snapshot(session, invoice_data)
        
        # Prepare invoice data
        invoice_data_dict = invoice_data.model_dump(
            mode='python',
            exclude={'taxes', 'line_items', 'recipient_snapshot'}
        )
        
        # Respect is_draft from request (defaults to True for backward compatibility)
        is_draft = invoice_data.is_draft if invoice_data.is_draft is not None else True
        
        # Generate invoice number if not provided
        if not invoice_data_dict.get('invoice_number'):
            from .invoice_number_generator import generate_unique_invoice_number
            invoice_data_dict['invoice_number'] = await generate_unique_invoice_number(
                session=session,
                issue_date=invoice_data_dict.get('issue_date', datetime.now(UTC))
            )
        
        invoice_data_dict.update({
            'amount': final_amount,
            'created_by_user_id': current_user.id,
            'is_draft': is_draft,
            **recipient_snapshot  # Merge recipient snapshot fields
        })
        
        # Validate dates
        if invoice_data_dict.get('issue_date') and isinstance(invoice_data_dict['issue_date'], datetime):
            invoice_data_dict['issue_date'] = validate_business_datetime(invoice_data_dict['issue_date'])
        if invoice_data_dict.get('due_date') and isinstance(invoice_data_dict['due_date'], datetime):
            invoice_data_dict['due_date'] = validate_business_datetime(invoice_data_dict['due_date'])
        
        issue = invoice_data_dict.get('issue_date')
        due = invoice_data_dict.get('due_date')
        if issue and due and due < issue:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Due date cannot be earlier than issue date."
            )
        
        # Auto-generate description from line items if not provided
        if not invoice_data_dict.get('description') and line_item_objects:
            invoice_data_dict['description'] = generate_invoice_description(line_item_objects)
        
        # Create invoice with relationships
        new_invoice = Invoice(**invoice_data_dict)
        
        # Add line items
        if line_item_objects:
            new_invoice.line_items = line_item_objects
        
        # Add taxes
        if tax_orm_objects:
            new_invoice.taxes = tax_orm_objects
        
        session.add(new_invoice)
        
        # For draft invoices, commit immediately (no delivery needed)
        if is_draft:
            await session.commit()
            
            # Refresh with relationships loaded
            await session.refresh(new_invoice, attribute_names=['taxes', 'line_items'])
            if new_invoice.property_id:
                await session.refresh(new_invoice, ["property"])
            if new_invoice.tenant_id:
                await session.refresh(new_invoice, ["tenant"])
            
            return InvoiceResponse(**build_invoice_response(new_invoice))
        
        # For finalized invoices: flush to get ID, but don't commit until delivery succeeds
        await session.flush()
        
        # Refresh with relationships loaded (uses flush, not commit)
        await session.refresh(new_invoice, attribute_names=['taxes', 'line_items'])
        if new_invoice.property_id:
            await session.refresh(new_invoice, ["property"])
        if new_invoice.tenant_id:
            await session.refresh(new_invoice, ["tenant"])
        
        logger.info(f"Invoice {new_invoice.invoice_number} created as finalized, triggering delivery")
        from Backend.utils.datetime_utils import utc_now
        
        # Mark as issued
        new_invoice.issued_at = utc_now()
        new_invoice.issued_by_user_id = current_user.id
        
        # Handle delivery (PDF generation + email/payment)
        # If this fails, the rollback in except block will undo everything
        await _handle_invoice_delivery(new_invoice, session, current_user)
        
        # Commit ONLY after successful delivery
        await session.commit()
        await session.refresh(new_invoice)
        
        return InvoiceResponse(**build_invoice_response(new_invoice))
        
    except ValueError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        await session.rollback()
        logger.exception("Error creating invoice with tax support")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to create invoice."
        ) from e


async def get_invoices(
    session: AsyncSession,
    current_user: User,
    tenant_id: int | None = None,
    property_id: int | None = None,
    payment_status_filter: PaymentStatus | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
    offset: int = 0
) -> list[InvoiceResponse]:
    """
    Retrieves a list of invoices filtered by user role and various criteria.

    Args:
        session: The database session.
        current_user: The user making the request.
        tenant_id: Optional tenant ID to filter invoices.
        property_id: Optional property ID to filter invoices.
        payment_status_filter: Optional payment status to filter invoices.
        start_date: Optional start date for filtering by issue date.
        end_date: Optional end date for filtering by issue date.
        limit: Maximum number of results to return.
        offset: Number of results to skip for pagination.

    Returns:
        A list of invoices matching the applied filters.
    """
    validate_date_range(start_date, end_date)

    query = select(Invoice).options(
        selectinload(getattr(Invoice, "property")),
        selectinload(getattr(Invoice, "tenant")),
        selectinload(getattr(Invoice, "ownership_entity")),
        selectinload(getattr(Invoice, "vendor")),
        selectinload(getattr(Invoice, "line_items")),
        selectinload(getattr(Invoice, "taxes"))
    )
    filters = []

    if payment_status_filter:
        filters.append(col(Invoice.status) == payment_status_filter)
    if start_date:
        start_datetime, _ = date_to_utc_range(start_date, start_date)
        filters.append(col(Invoice.issue_date) >= start_datetime)
    if end_date:
        _, end_datetime = date_to_utc_range(end_date, end_date)
        filters.append(col(Invoice.issue_date) <= end_datetime)

    if current_user.user_type == UserType.TENANT:
        await apply_tenant_invoice_filters(filters, tenant_id, property_id, current_user, session)
    elif current_user.user_type == UserType.LANDLORD:
        can_proceed = await apply_landlord_invoice_filters(filters, property_id, tenant_id, current_user, session)
        if not can_proceed:
            return []
    elif current_user.user_type == UserType.ADMIN:
        apply_admin_invoice_filters(filters, property_id, tenant_id)
    else:
        raise HTTPException(status_code=403, detail="Not authorized to access these invoices.")

    if filters:
        query = query.where(and_(*filters))
    
    query = query.order_by(col(Invoice.issue_date).desc())
    query = query.limit(limit).offset(offset)
    
    invoices_orm = (await session.execute(query)).scalars().all()
    return [InvoiceResponse(**build_invoice_response(inv)) for inv in invoices_orm]


async def get_invoice_by_id(
    invoice_id: int,
    session: AsyncSession,
    current_user: User
) -> InvoiceResponse:
    """
    Retrieves a specific invoice by ID.

    Args:
        invoice_id: The ID of the invoice to retrieve.
        session: The database session.
        current_user: The user making the request.

    Returns:
        The invoice details.

    Raises:
        HTTPException: If invoice not found or user not authorized.
    """
    query = select(Invoice).options(
        selectinload(getattr(Invoice, "property")),
        selectinload(getattr(Invoice, "tenant")),
        selectinload(getattr(Invoice, "line_items")),
        selectinload(getattr(Invoice, "taxes"))
    ).where(col(Invoice.id) == invoice_id)
    
    invoice = (await session.execute(query)).scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    # Check authorization
    if current_user.user_type == UserType.TENANT:
        tenant_query = select(Tenant).where(col(Tenant.user_id) == current_user.id)
        user_tenant = await session.scalar(tenant_query)
        if not user_tenant or invoice.tenant_id != user_tenant.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this invoice")
    elif current_user.user_type == UserType.LANDLORD:
        if invoice.property_id:
            await check_property_ownership(invoice.property_id, session, current_user)
        # Allow landlords to access invoices with NULL property_id (unassigned invoices)
        # No else clause needed - if property_id is NULL, access is allowed
    
    return InvoiceResponse(**build_invoice_response(invoice))


async def update_invoice(
    invoice_id: int,
    invoice_data: InvoiceUpdate,
    session: AsyncSession,
    current_user: User
) -> InvoiceResponse:
    """
    Updates an existing invoice (ONLY DRAFTS CAN BE UPDATED).
    
    Once an invoice is finalized (is_draft=False), it becomes immutable.
    Use credit notes for corrections.

    Args:
        invoice_id: The ID of the invoice to update.
        invoice_data: The fields to update.
        session: The database session.
        current_user: The user making the request.

    Returns:
        The updated invoice.

    Raises:
        HTTPException: If invoice not found, user not authorized, or invoice is finalized.
    """
    if current_user.user_type not in [UserType.ADMIN, UserType.LANDLORD]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update invoices")

    # Get existing invoice with relationships
    stmt = select(Invoice).options(
        selectinload(getattr(Invoice, "line_items")),
        selectinload(getattr(Invoice, "taxes"))
    ).where(Invoice.id == invoice_id)
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    # Track if invoice was a draft before update (to detect draft-to-finalized transitions)
    was_draft = invoice.is_draft
    
    # IMMUTABILITY CHECK: Cannot update finalized invoices
    if not invoice.is_draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update finalized invoice. Use credit notes for corrections."
        )

    # Check ownership
    if current_user.user_type == UserType.LANDLORD:
        if invoice.property_id:
            await check_property_ownership(invoice.property_id, session, current_user)
        elif invoice.created_by_user_id and invoice.created_by_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this invoice")

    # Extract updates
    update_dict = invoice_data.model_dump(exclude_unset=True, exclude={'line_items', 'taxes'})

    # Validate dates if provided
    if 'issue_date' in update_dict and update_dict['issue_date']:
        update_dict['issue_date'] = validate_business_datetime(update_dict['issue_date'])
    if 'due_date' in update_dict and update_dict['due_date']:
        update_dict['due_date'] = validate_business_datetime(update_dict['due_date'])

    # Check date logic
    issue_date = update_dict.get('issue_date', invoice.issue_date)
    due_date = update_dict.get('due_date', invoice.due_date)
    if issue_date and due_date and due_date < issue_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Due date cannot be earlier than issue date."
        )
    
    # Handle line items update (replace all)
    if invoice_data.line_items is not None:
        # Delete existing line items
        for old_item in invoice.line_items:
            await session.delete(old_item)
        
        # Flush deletes before adding new items to avoid unique constraint violations
        await session.flush()
        
        # Create new line items
        new_line_items, line_items_subtotal = process_line_items_for_invoice(invoice_data.line_items)
        invoice.line_items = new_line_items
        subtotal = line_items_subtotal
    else:
        # Use existing line items subtotal or amount
        if invoice.line_items:
            subtotal = calculate_line_items_subtotal(invoice.line_items)
        else:
            subtotal = invoice.amount
    
    # Handle taxes update (replace all)
    if invoice_data.taxes is not None:
        # Delete existing taxes
        for old_tax in invoice.taxes:
            await session.delete(old_tax)
        
        # Flush deletes before adding new taxes to avoid unique constraint violations
        await session.flush()
        
        # Calculate new taxes
        tax_orm_objects, total_tax = calculate_taxes_on_line_items(
            line_items=invoice.line_items,
            tax_details=invoice_data.taxes,
            fallback_subtotal=subtotal
        )
        invoice.taxes = tax_orm_objects
    else:
        # Recalculate existing taxes if line items changed
        if invoice_data.line_items is not None and invoice.taxes:
            # Recalculate taxes on new line items
            taxable_subtotal = sum(
                (item.line_total for item in invoice.line_items if item.is_taxable),
                Decimal('0')
            )
            total_tax = Decimal('0')
            for tax in invoice.taxes:
                tax.tax_amount = quantize_2dp(taxable_subtotal * tax.tax_rate / Decimal('100'))
                total_tax += tax.tax_amount
        else:
            total_tax = sum((t.tax_amount for t in invoice.taxes), Decimal('0'))
    
    # Recalculate amount if line_items or taxes changed
    if invoice_data.line_items is not None or invoice_data.taxes is not None:
        update_dict['amount'] = quantize_2dp(subtotal + total_tax)
    
    # Apply field updates
    for key, value in update_dict.items():
        setattr(invoice, key, value)
    
    invoice.updated_at = datetime.now(UTC)
    
    # Check if invoice is being finalized (draft -> finalized transition)
    is_being_finalized = was_draft and update_dict.get('is_draft') is False
    
    if is_being_finalized:
        # Validate invoice has line items before finalizing
        if not invoice.line_items or len(invoice.line_items) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invoice must have at least one line item before finalizing"
            )
        
        # Set finalization metadata
        invoice.issued_at = datetime.now(UTC)
        invoice.issued_by_user_id = current_user.id
        
        logger.info(f"Invoice {invoice.invoice_number} being finalized during update by user {current_user.id}")
    
    await session.commit()
    
    # Refresh with relationships loaded
    await session.refresh(invoice, attribute_names=['line_items', 'taxes'])
    if invoice.property_id:
        await session.refresh(invoice, ["property"])
    if invoice.tenant_id:
        await session.refresh(invoice, ["tenant"])
    if invoice.ownership_entity_id:
        await session.refresh(invoice, ["ownership_entity"])
    if invoice.vendor_id:
        await session.refresh(invoice, ["vendor"])
    
    # If invoice was finalized during this update, handle delivery
    if is_being_finalized:
        try:
            await _handle_invoice_delivery(invoice, session, current_user)
        except Exception as e:
            logger.error(f"Failed to deliver invoice {invoice.invoice_number} after finalization: {str(e)}")
            # Don't rollback the finalization - invoice is still valid
            # Just log the error and let the user retry delivery later
    
    return InvoiceResponse(**build_invoice_response(invoice))


async def finalize_invoice(
    invoice_id: int,
    session: AsyncSession,
    current_user: User
) -> InvoiceResponse:
    """
    Finalize an invoice (mark as issued and make immutable).
    
    Once finalized:
    - is_draft changes to False
    - issued_at timestamp is set
    - issued_by_user_id is recorded
    - Invoice becomes immutable (cannot be edited)
    
    Args:
        invoice_id: The ID of the invoice to finalize.
        session: The database session.
        current_user: The user finalizing the invoice.
    
    Returns:
        The finalized invoice.
    
    Raises:
        HTTPException: If invoice not found, user not authorized, or already finalized.
    """
    if current_user.user_type not in [UserType.ADMIN, UserType.LANDLORD]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to finalize invoices")
    
    # Get invoice with relationships
    stmt = select(Invoice).options(
        selectinload(getattr(Invoice, "line_items")),
        selectinload(getattr(Invoice, "taxes"))
    ).where(Invoice.id == invoice_id)
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    # Check if already finalized
    if not invoice.is_draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is already finalized"
        )
    
    # Check ownership
    if current_user.user_type == UserType.LANDLORD:
        if invoice.property_id:
            await check_property_ownership(invoice.property_id, session, current_user)
        elif invoice.created_by_user_id and invoice.created_by_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to finalize this invoice")
    
    # Validate invoice is ready for finalization
    if not invoice.line_items or len(invoice.line_items) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice must have at least one line item before finalizing"
        )
    
    # Finalize the invoice
    invoice.is_draft = False
    invoice.issued_at = datetime.now(UTC)
    invoice.issued_by_user_id = current_user.id
    invoice.updated_at = datetime.now(UTC)
    
    await session.commit()
    
    # Refresh with relationships
    await session.refresh(invoice, attribute_names=['line_items', 'taxes'])
    if invoice.property_id:
        await session.refresh(invoice, ["property"])
    if invoice.tenant_id:
        await session.refresh(invoice, ["tenant"])
    
    logger.info(f"Invoice {invoice.invoice_number} finalized by user {current_user.id}")
    
    # Handle invoice delivery based on delivery_method
    try:
        await _handle_invoice_delivery(invoice, session, current_user)
    except Exception as e:
        logger.error(f"Failed to deliver invoice {invoice.invoice_number}: {str(e)}")
        # Don't rollback the finalization - invoice is still valid
        # Just log the error and let the user retry delivery later
        # Could add a `delivery_status` field in the future to track this
    
    return InvoiceResponse(**build_invoice_response(invoice))


async def delete_invoice(
    invoice_id: int,
    session: AsyncSession,
    current_user: User
) -> None:
    """
    Deletes an invoice (ONLY DRAFTS CAN BE DELETED).
    
    Finalized invoices cannot be deleted. Use credit notes instead.

    Args:
        invoice_id: The ID of the invoice to delete.
        session: The database session.
        current_user: The user making the request.

    Raises:
        HTTPException: If invoice not found, user not authorized, or invoice is finalized.
    """
    if current_user.user_type not in [UserType.ADMIN, UserType.LANDLORD]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete invoices")
    
    # Get existing invoice
    invoice = await session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    # IMMUTABILITY CHECK: Cannot delete finalized invoices
    if not invoice.is_draft:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete finalized invoice"
        )
    
    # Check ownership
    if current_user.user_type == UserType.LANDLORD:
        if invoice.property_id:
            await check_property_ownership(invoice.property_id, session, current_user)
        elif invoice.created_by_user_id and invoice.created_by_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this invoice")
    
    # Delete the invoice (cascade will delete line_items and taxes)
    await session.delete(invoice)
    await session.commit()
    
    logger.info(f"Draft invoice {invoice.invoice_number} deleted by user {current_user.id}")


async def mark_invoice_paid(
    invoice_id: int,
    session: AsyncSession,
    current_user: User
) -> InvoiceResponse:
    """
    Marks an invoice as paid.

    Args:
        invoice_id: The ID of the invoice to mark as paid.
        session: The database session.
        current_user: The user making the request.

    Returns:
        The updated invoice.

    Raises:
        HTTPException: If invoice not found or user not authorized.
    """
    if current_user.user_type not in [UserType.ADMIN, UserType.LANDLORD]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update invoice status")
    
    # Get existing invoice
    invoice = await session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    
    # Check ownership if landlord and invoice has a property
    if current_user.user_type == UserType.LANDLORD and invoice.property_id:
        await check_property_ownership(invoice.property_id, session, current_user)
    # TODO: For invoices with NULL property_id, add created_by_user_id field to Invoice model
    # to ensure landlords can only update invoices they created
    
    # Validate that invoice is not already paid
    if invoice.status == PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invoice is already marked as paid"
        )
    
    # Update status
    invoice.status = PaymentStatus.PAID
    invoice.updated_at = datetime.now(UTC)
    
    await session.commit()
    
    # Refresh with relationships loaded
    await session.refresh(invoice)
    if invoice.property_id:
        await session.refresh(invoice, ["property"])
    if invoice.tenant_id:
        await session.refresh(invoice, ["tenant"])
    
    return InvoiceResponse(**build_invoice_response(invoice))


async def import_invoices_from_csv(
    import_request: CSVImportRequest,
    session: AsyncSession,
    current_user: User
) -> CSVImportResult:
    """
    Import invoices from CSV data with batch processing.
    
    Args:
        import_request: The CSV import request containing invoice data.
        session: Database session.
        current_user: The current user making the request.
    
    Returns:
        Import results with success/failure counts and error details.
    """
    from .service_batch import prepare_invoice_batch, bulk_create_invoices, check_duplicate_invoices
    from Backend.config import settings
    
    # Validate user permissions
    if current_user.user_type not in [UserType.ADMIN, UserType.LANDLORD]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to import invoices"
        )
    
    total_rows = len(import_request.invoices)
    
    # Validate row limit
    if total_rows > settings.MAX_CSV_IMPORT_ROWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV contains {total_rows} rows, exceeding maximum of {settings.MAX_CSV_IMPORT_ROWS}"
        )
    
    # Get all properties and tenants for matching
    properties_query = select(Property)
    if current_user.user_type == UserType.LANDLORD:
        properties_query = properties_query.where(col(Property.user_id) == current_user.id)
    
    properties_result = await session.execute(properties_query)
    properties = {prop.name.lower(): prop for prop in properties_result.scalars().all()}
    
    tenants_query = select(Tenant)
    if current_user.user_type == UserType.LANDLORD:
        # Get tenants for landlord's properties only
        landlord_tenant_ids_query = select(col(Lease.tenant_id)).where(
            col(Lease.property_id).in_([prop.id for prop in properties.values()])
        )
        landlord_tenant_ids_result = await session.execute(landlord_tenant_ids_query)
        tenant_ids = [row[0] for row in landlord_tenant_ids_result.all()]
        tenants_query = tenants_query.where(col(Tenant.id).in_(tenant_ids))
    
    tenants_result = await session.execute(tenants_query)
    tenants = {}
    for tenant in tenants_result.scalars().all():
        # Build display name similar to get_tenant_display_name function
        if tenant.first_name:
            full_name = tenant.first_name
            if tenant.last_name:
                full_name += f" {tenant.last_name}"
            tenants[full_name.strip().lower()] = tenant
        elif tenant.company_name:
            tenants[tenant.company_name.strip().lower()] = tenant
    
    # Prepare invoices in batch
    valid_invoices, preparation_errors = prepare_invoice_batch(
        import_request.invoices,
        properties,
        tenants,
        str(current_user.id),
        current_user.user_type
    )
    
    # Check for duplicates
    duplicate_indices = await check_duplicate_invoices(valid_invoices, session)
    
    # Remove duplicates from valid invoices and add to errors
    if duplicate_indices:
        for idx in sorted(duplicate_indices, reverse=True):
            invoice = valid_invoices.pop(idx)
            preparation_errors.append({
                "row_number": idx + 1,
                "error_message": f"Invoice number '{invoice['invoice_number']}' already exists"
            })
    
    # Process invoices in batches with atomic transaction
    created_invoice_ids = []
    
    try:
        # Start nested transaction for atomicity
        async with session.begin_nested():
            # Process in batches
            for i in range(0, len(valid_invoices), settings.CSV_IMPORT_BATCH_SIZE):
                batch = valid_invoices[i:i + settings.CSV_IMPORT_BATCH_SIZE]
                batch_ids = await bulk_create_invoices(batch, session)
                created_invoice_ids.extend(batch_ids)
            
            # Commit the nested transaction
            await session.commit()
            
    except Exception as e:
        # Rollback will happen automatically
        logger.error(f"Failed to import invoices batch: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import invoices: {str(e)}"
        )
    
    from .schemas import CSVImportError
    return CSVImportResult(
        total_rows=total_rows,
        successful_imports=len(created_invoice_ids),
        failed_imports=len(preparation_errors),
        errors=[CSVImportError(**error) for error in preparation_errors],
        created_invoice_ids=created_invoice_ids
    )


# Export all service functions
__all__ = [
    "create_invoice",
    "get_invoices", 
    "get_invoice_by_id",
    "update_invoice",
    "finalize_invoice",
    "delete_invoice",
    "mark_invoice_paid",
    "import_invoices_from_csv"
]
