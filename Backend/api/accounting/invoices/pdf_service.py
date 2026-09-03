"""
PDF Generation Service for Invoices

Generates professional PDF invoices from HTML templates using WeasyPrint.
Optimized for performance with async execution and file size optimization.
Includes Azure Blob Storage integration for permanent PDF storage.
"""
import asyncio
import logging
import os
from typing import Optional
from io import BytesIO
from uuid import UUID as PythonUUID

# Set library paths for WeasyPrint on macOS (must be before weasyprint import)
if os.path.exists('/opt/homebrew'):
    # Apple Silicon Mac
    homebrew_prefix = '/opt/homebrew'
else:
    # Intel Mac
    homebrew_prefix = '/usr/local'

lib_paths = [
    f'{homebrew_prefix}/opt/cairo/lib',
    f'{homebrew_prefix}/opt/pango/lib',
    f'{homebrew_prefix}/opt/gdk-pixbuf/lib',
    f'{homebrew_prefix}/opt/gobject-introspection/lib',
    f'{homebrew_prefix}/opt/glib/lib',
    f'{homebrew_prefix}/lib',
]

# Set DYLD_LIBRARY_PATH for macOS dynamic library loading
existing_path = os.environ.get('DYLD_LIBRARY_PATH', '')
os.environ['DYLD_LIBRARY_PATH'] = ':'.join(lib_paths + ([existing_path] if existing_path else []))

# Now import WeasyPrint after setting library paths
from weasyprint import HTML, CSS
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select
from fastapi import UploadFile
from starlette.datastructures import Headers

from Backend.models.accounting.invoice import Invoice
from Backend.models.accounting.invoice_line_item import InvoiceLineItem
from Backend.models.accounting.invoice_tax_detail import InvoiceTaxDetail
from Backend.utils.datetime_utils import utc_now
from .invoice_template import BrikliInvoiceTemplate

logger = logging.getLogger(__name__)


async def generate_invoice_pdf(
    invoice: Invoice,
    session: Optional[AsyncSession] = None
) -> bytes:
    """
    Generate a PDF from an invoice.
    
    This function:
    1. Loads invoice with relationships (line_items, taxes, owner)
    2. Generates HTML using BrikliInvoiceTemplate
    3. Converts HTML to PDF using WeasyPrint (in thread pool)
    4. Returns PDF as bytes
    
    Args:
        invoice: Invoice ORM object (must have line_items and taxes loaded)
        session: Optional database session to load relationships if needed
        
    Returns:
        PDF file as bytes
        
    Raises:
        ValueError: If invoice data is invalid
        Exception: If PDF generation fails
    """
    try:
        # Ensure relationships are loaded
        line_items = invoice.line_items if invoice.line_items else []
        taxes = invoice.taxes if invoice.taxes else []
        
        # If relationships not loaded and session provided, load them
        if (not line_items or not taxes) and session:
            stmt = select(Invoice).options(
                selectinload(getattr(Invoice, "line_items")),
                selectinload(getattr(Invoice, "taxes"))
            ).where(Invoice.id == invoice.id)
            result = await session.execute(stmt)
            invoice = result.scalar_one()
            line_items = invoice.line_items
            taxes = invoice.taxes
        
        # Validate invoice has required data
        if not line_items:
            raise ValueError(f"Invoice {invoice.invoice_number} has no line items")
        
        # Load user info for "FROM" section
        company_info = None
        if session and invoice.created_by_user_id:
            from Backend.models.user import User
            user_stmt = select(User).where(User.id == invoice.created_by_user_id)
            user_result = await session.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            
            if user:
                # Build company info from user profile
                name = f"{user.first_name} {user.last_name}".strip() if user.first_name or user.last_name else user.email.split('@')[0]
                company_info = {
                    'name': name,
                    'address': user.address or 'Address not provided',
                    'address_2': f"{user.city or ''} {user.province or ''} {user.postal_code or ''}".strip() or 'City, Province Postal Code',
                    'country': 'Canada',
                    'email': user.email,
                    'phone': user.phone or 'Phone not provided'
                }
        
        logger.info(
            f"Generating PDF for invoice {invoice.invoice_number}",
            extra={
                'invoice_id': invoice.id,
                'line_items_count': len(line_items),
                'taxes_count': len(taxes)
            }
        )
        
        # Generate HTML content
        html_content = BrikliInvoiceTemplate.generate_invoice_html(
            invoice=invoice,
            line_items=line_items,
            taxes=taxes,
            company_info=company_info,  # Use user's info
            stripe_payment_url=invoice.hosted_invoice_url  # Include if available
        )
        
        # Convert HTML to PDF in thread pool (CPU-bound operation)
        loop = asyncio.get_running_loop()
        pdf_bytes = await loop.run_in_executor(
            None,
            _generate_pdf_sync,
            html_content
        )
        
        logger.info(
            f"PDF generated successfully for invoice {invoice.invoice_number}",
            extra={
                'invoice_id': invoice.id,
                'pdf_size_kb': len(pdf_bytes) / 1024
            }
        )
        
        return pdf_bytes
        
    except ValueError as e:
        logger.error(f"Validation error generating PDF: {str(e)}")
        raise
    except Exception as e:
        logger.exception(f"Failed to generate PDF for invoice {invoice.invoice_number}")
        raise Exception(f"PDF generation failed: {str(e)}") from e


def _generate_pdf_sync(html_content: str) -> bytes:
    """
    Synchronous PDF generation (runs in thread pool).
    
    Optimizations:
    - optimize_images: Reduce image sizes
    - jpeg_quality: Balance quality vs file size
    - dpi: 96 DPI is sufficient for screen/email viewing
    
    Args:
        html_content: HTML string to convert
        
    Returns:
        PDF as bytes
    """
    # Additional CSS for better print rendering
    print_css = CSS(string='''
        @page {
            margin: 0;  /* Template handles its own margins */
        }
        
        body {
            margin: 0;
            padding: 0;
        }
        
        /* Ensure colors print properly */
        * {
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }
    ''')
    
    # Generate PDF with optimizations
    pdf_bytes = HTML(string=html_content).write_pdf(
        stylesheets=[print_css],
        optimize_images=True,   # Compress embedded images
        jpeg_quality=85,        # Good quality, reasonable size
        dpi=96,                 # Screen DPI (sufficient for digital invoices)
    )
    
    return pdf_bytes


async def generate_invoice_pdf_from_id(
    invoice_id: int,
    session: AsyncSession
) -> tuple[bytes, str]:
    """
    Generate PDF for an invoice by ID.
    
    Convenience function that loads the invoice and generates PDF.
    
    Args:
        invoice_id: Invoice ID
        session: Database session
        
    Returns:
        Tuple of (pdf_bytes, filename)
        
    Raises:
        ValueError: If invoice not found
    """
    # Load invoice with relationships
    stmt = select(Invoice).options(
        selectinload(getattr(Invoice, "line_items")),
        selectinload(getattr(Invoice, "taxes"))
    ).where(Invoice.id == invoice_id)
    
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        raise ValueError(f"Invoice with ID {invoice_id} not found")
    
    # Generate PDF
    pdf_bytes = await generate_invoice_pdf(invoice, session)
    
    # Generate filename
    filename = f"Invoice-{invoice.invoice_number}.pdf"
    
    return pdf_bytes, filename


async def upload_invoice_pdf_to_storage(
    pdf_bytes: bytes,
    invoice: Invoice,
    user_id: PythonUUID
) -> str:
    """
    Upload generated invoice PDF to Azure Blob Storage.
    
    Creates a permanent record of the PDF in blob storage for:
    - Audit trail
    - Repeated downloads without regeneration
    - Legal/compliance requirements
    
    Args:
        pdf_bytes: PDF file as bytes
        invoice: Invoice ORM object (for metadata)
        user_id: User who generated the invoice
        
    Returns:
        Azure Blob Storage URL of uploaded PDF
        
    Raises:
        ConnectionError: If Azure Blob Storage is not configured
        Exception: If upload fails
    """
    from Backend.utils.azure_blob import upload_invoice_pdf_to_blob
    
    try:
        # Create filename with invoice number for easy identification
        filename = f"Invoice-{invoice.invoice_number}.pdf"
        
        # Create BytesIO for the PDF bytes (proper BinaryIO type)
        pdf_file_io = BytesIO(pdf_bytes)
        
        try:
            # Create UploadFile object for Azure Blob upload
            pdf_file = UploadFile(
                file=pdf_file_io,
                filename=filename,
                headers=Headers({"content-type": "application/pdf"})
            )
            
            # Upload to Azure Blob Storage
            blob_url = await upload_invoice_pdf_to_blob(
                file=pdf_file,
                user_id=user_id
            )
            
            logger.info(
                f"Invoice PDF uploaded to blob storage: {invoice.invoice_number}",
                extra={
                    'invoice_id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                    'blob_url': blob_url,
                    'pdf_size_kb': len(pdf_bytes) / 1024
                }
            )

            return blob_url
        finally:
            # Clean up temp file (always close, even if upload fails)
            pdf_file_io.close()
        
    except Exception as e:
        logger.error(f"Failed to upload invoice PDF to blob storage: {str(e)}")
        raise


# Export functions
__all__ = [
    "generate_invoice_pdf",
    "generate_invoice_pdf_from_id",
    "upload_invoice_pdf_to_storage"
]
