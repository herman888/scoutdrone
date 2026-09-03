"""
Invoice number generation utility.

Generates unique invoice numbers in format: INV-YYYY-MMDD-NNN
where NNN is a zero-padded sequential number for that day.
"""
from datetime import datetime
from sqlalchemy import func, select
from sqlmodel import col
from sqlalchemy.ext.asyncio import AsyncSession

from Backend.models.accounting.invoice import Invoice


async def generate_unique_invoice_number(
    session: AsyncSession,
    issue_date: datetime
) -> str:
    """
    Generate a unique invoice number for the given issue date.
    
    Format: INV-YYYY-MMDD-NNN
    Example: INV-2026-0122-001
    
    Args:
        session: Database session
        issue_date: The invoice issue date
        
    Returns:
        Unique invoice number string
    """
    # Extract date components
    year = issue_date.year
    month = f"{issue_date.month:02d}"
    day = f"{issue_date.day:02d}"
    
    # Build date prefix
    date_prefix = f"INV-{year}-{month}{day}-"
    
    # Find the highest sequence number for this date
    query = select(func.max(Invoice.invoice_number)).where(
        col(Invoice.invoice_number).like(f"{date_prefix}%")
    )
    
    result = await session.execute(query)
    max_invoice_number = result.scalar()
    
    # Determine next sequence number
    if max_invoice_number:
        # Extract sequence number from existing invoice (e.g., "001" from "INV-2026-0122-001")
        try:
            sequence_str = max_invoice_number.split("-")[-1]
            next_sequence = int(sequence_str) + 1
        except (IndexError, ValueError):
            # Fallback if parsing fails
            next_sequence = 1
    else:
        # First invoice for this date
        next_sequence = 1
    
    # Format with zero-padding (3 digits)
    invoice_number = f"{date_prefix}{next_sequence:03d}"
    
    return invoice_number
