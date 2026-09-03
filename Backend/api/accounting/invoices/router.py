"""
FastAPI router for invoice endpoints.

This module defines the API endpoints for invoice operations, delegating all
business logic to the service layer.
"""
import logging
from datetime import date

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from Backend.api.auth import get_current_user
from Backend.database import get_session
from Backend.models.accounting.common import PaymentStatus
from Backend.models.accounting.invoice import Invoice
from Backend.models.user import User

from . import service
from .schemas import InvoiceCreate, InvoiceResponse, InvoiceUpdate, CSVImportRequest, CSVImportResult, SecureInvoicePdfUrlResponse
from Backend.utils.recaptcha import require_recaptcha


logger = logging.getLogger(__name__)
router = APIRouter()


# ===== CREATE =====
@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _recaptcha: None = Depends(require_recaptcha("invoice_create"))
) -> InvoiceResponse:
    """
    Creates a new invoice.
    
    Invoices can be created with or without tenant/property associations.
    This flexibility allows for importing invoices from external systems
    like QuickBooks or Stripe.

    Args:
        invoice_data: The invoice creation data.

    Returns:
        The created invoice as an InvoiceResponse.
    """
    return await service.create_invoice(invoice_data, session, current_user)


# ===== READ =====
@router.get("", response_model=list[InvoiceResponse])
async def get_invoices(
    tenant_id: int | None = None,
    property_id: int | None = None,
    payment_status_filter: PaymentStatus | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> list[InvoiceResponse]:
    """
    Retrieves a list of invoices filtered by user role and various criteria.

    Args:
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
    return await service.get_invoices(
        session=session,
        current_user=current_user,
        tenant_id=tenant_id,
        property_id=property_id,
        payment_status_filter=payment_status_filter,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> InvoiceResponse:
    """
    Retrieves a specific invoice by ID.

    Args:
        invoice_id: The ID of the invoice to retrieve.

    Returns:
        The invoice details.
    """
    return await service.get_invoice_by_id(invoice_id, session, current_user)


# ===== UPDATE =====
@router.put("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: int,
    invoice_data: InvoiceUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> InvoiceResponse:
    """
    Updates an existing invoice.

    Args:
        invoice_id: The ID of the invoice to update.
        invoice_data: The fields to update.

    Returns:
        The updated invoice.
    """
    return await service.update_invoice(invoice_id, invoice_data, session, current_user)


# ===== DELETE =====
@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> None:
    """
    Deletes an invoice.

    Args:
        invoice_id: The ID of the invoice to delete.
    """
    await service.delete_invoice(invoice_id, session, current_user)


# ===== UTILITY ENDPOINTS =====
@router.post("/finalize/{invoice_id}", response_model=InvoiceResponse)
async def finalize_invoice(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> InvoiceResponse:
    """
    Finalize an invoice (mark as issued and make immutable).
    
    Once finalized:
    - Invoice becomes read-only (cannot be edited or deleted)
    - issued_at timestamp is recorded
    - issued_by_user_id is recorded
    
    Args:
        invoice_id: The ID of the invoice to finalize.
    
    Returns:
        The finalized invoice.
    """
    return await service.finalize_invoice(invoice_id, session, current_user)


@router.post("/finalize-and-send/{invoice_id}", response_model=InvoiceResponse)
async def finalize_and_send_invoice(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> InvoiceResponse:
    """
    Finalize invoice and create Stripe Invoice with hosted payment page.
    
    This endpoint:
    1. Validates invoice is in draft state
    2. Creates/retrieves Stripe Customer for recipient
    3. Creates Stripe Invoice with line items and taxes
    4. Marks Brikli invoice as issued and immutable
    5. Returns invoice with hosted_invoice_url for payment
    
    The hosted_invoice_url should be sent to the recipient for payment.
    
    Once finalized:
    - Invoice becomes read-only (cannot be edited or deleted)
    - issued_at timestamp is recorded
    - issued_by_user_id is recorded
    - stripe_invoice_id, hosted_invoice_url, and stripe_invoice_pdf are populated
    
    Args:
        invoice_id: The ID of the invoice to finalize and send.
    
    Returns:
        The finalized invoice with Stripe integration data.
        
    Raises:
        HTTPException 404: Invoice not found
        HTTPException 400: Invoice already finalized or has no line items
        HTTPException 403: User doesn't own the invoice
        HTTPException 500: Stripe API error
    """
    from Backend.api.stripe.invoices import finalize_and_send_invoice as stripe_finalize
    from .helpers import build_invoice_response
    
    invoice = await stripe_finalize(
        invoice_id=invoice_id,
        user_id=str(current_user.id),
        session=session
    )
    
    return InvoiceResponse(**build_invoice_response(invoice))


@router.post("/mark-paid/{invoice_id}", response_model=InvoiceResponse)
async def mark_invoice_paid(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> InvoiceResponse:
    """
    Marks an invoice as paid.

    Args:
        invoice_id: The ID of the invoice to mark as paid.

    Returns:
        The updated invoice.
    """
    return await service.mark_invoice_paid(invoice_id, session, current_user)


# ===== CSV IMPORT =====
@router.post("/import-csv", response_model=CSVImportResult)
async def import_invoices_from_csv(
    import_request: CSVImportRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _recaptcha: None = Depends(require_recaptcha("invoice_import_csv"))
) -> CSVImportResult:
    """
    Import invoices from CSV data.

    Args:
        import_request: The CSV import request containing invoice data.

    Returns:
        The import results with success/failure counts and error details.
    """
    return await service.import_invoices_from_csv(import_request, session, current_user)


# ===== PDF DOWNLOAD =====
@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> Response:
    """
    Download invoice as PDF.
    
    Primary use case: SAVE_LOCALLY delivery method - allows users to download
    invoices manually instead of sending via email.
    
    Performance optimization: If PDF is already stored in Azure Blob Storage,
    redirects to the blob URL instead of regenerating (faster and more efficient).
    
    Also useful for re-downloading any finalized invoice.
    
    Args:
        invoice_id: The ID of the invoice to download as PDF.
    
    Returns:
        PDF file as application/pdf response with appropriate filename,
        or redirect to Azure Blob URL if already stored.
        
    Raises:
        HTTPException 404: Invoice not found
        HTTPException 403: User doesn't have access to this invoice
    """
    from fastapi.responses import RedirectResponse
    from sqlmodel import select
    from sqlalchemy.orm import selectinload
    from .pdf_service import generate_invoice_pdf_from_id
    from .service import get_invoice_by_id
    
    # Verify user has access to this invoice
    invoice_response = await get_invoice_by_id(invoice_id, session, current_user)
    
    # Load invoice with blob URL (if available)
    stmt = select(Invoice).where(Invoice.id == invoice_id)
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()
    
    # If PDF already stored in blob storage, redirect to it (faster)
    if invoice and invoice.pdf_blob_url:
        logger.info(f"Serving PDF from blob storage: {invoice.invoice_number}")
        return RedirectResponse(
            url=invoice.pdf_blob_url,
            status_code=302  # Temporary redirect
        )
    
    # Generate PDF on-the-fly if not in blob storage
    logger.info(f"Generating PDF on-demand for: {invoice_response.invoice_number}")
    pdf_bytes, filename = await generate_invoice_pdf_from_id(invoice_id, session)
    
    # Return as downloadable PDF
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/{invoice_id}/pdf/secure-url", response_model=SecureInvoicePdfUrlResponse)
async def get_invoice_pdf_secure_url(
    invoice_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> SecureInvoicePdfUrlResponse:
    """
    Generate time-limited secure URL for invoice PDF access with SAS token.
    
    This endpoint follows the proven pattern used for lease documents and follows
    industry-standard secure document access (Dropbox, Box, SharePoint, etc.).
    
    Flow:
    1. Verify user has access to invoice
    2. Check if PDF exists in Azure Blob Storage
    3. Generate SAS token for blob URL (1-hour expiry)
    4. Return secure URL with expiration info
    
    The returned secure URL can be opened directly in browser without additional
    authentication, as the SAS token provides temporary access.
    
    Args:
        invoice_id: The ID of the invoice PDF to access
    
    Returns:
        SecureInvoicePdfUrlResponse with:
            - secure_url: Azure Blob URL with SAS token
            - expires_at: ISO datetime string
            - expires_in_seconds: Time until expiration
    
    Raises:
        HTTPException 404: Invoice not found or no PDF available
        HTTPException 403: User doesn't have access to this invoice
        HTTPException 500: Failed to generate secure URL
    """
    from fastapi import HTTPException
    from sqlmodel import select
    from Backend.utils.azure_blob import generate_secure_document_url
    
    # Verify user has access to this invoice
    invoice_response = await service.get_invoice_by_id(invoice_id, session, current_user)
    
    # Load invoice with blob URL
    stmt = select(Invoice).where(Invoice.id == invoice_id)
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if not invoice.pdf_blob_url:
        raise HTTPException(
            status_code=404,
            detail="PDF not available for this invoice. Please generate the invoice first."
        )
    
    try:
        # Generate secure URL with SAS token (follows lease document pattern)
        url_data = await generate_secure_document_url(
            blob_url=invoice.pdf_blob_url,
            user_id=current_user.id,
            document_id=invoice_id,
            expires_in_hours=1  # 1-hour expiry (industry standard for PDFs)
        )
        
        logger.info(
            f"Generated secure PDF URL for invoice {invoice.invoice_number}",
            extra={
                'invoice_id': invoice_id,
                'user_id': str(current_user.id),
                'expires_at': url_data['expires_at']
            }
        )
        
        return SecureInvoicePdfUrlResponse(**url_data)
        
    except ValueError as e:
        logger.error(f"Invalid blob URL for invoice {invoice_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate secure URL: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Error generating secure URL for invoice {invoice_id}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate secure URL. Please try again or contact support."
        )
