import logging

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlmodel import col

from Backend.models.maintenance import MaintenanceRequest
from Backend.models.property import Property
from Backend.models.user import User
from Backend.models.enums import UserType

logger = logging.getLogger(__name__)


async def validate_file_content(upload_file: UploadFile) -> bool:
    """
    Validates uploaded file content by signature (magic bytes).

    Supported formats:
    - JPEG (.jpg, .jpeg)
    - PNG (.png)
    - GIF (.gif)
    - WebP (.webp)
    - HEIC/HEIF (.heic, .heif) - Apple's default iPhone format
    - BMP (.bmp)
    - TIFF (.tif, .tiff)
    - PDF (.pdf)
    """
    # Read a larger header to accommodate HEIC/HEIF which needs more bytes
    await upload_file.seek(0)
    header = await upload_file.read(32)
    await upload_file.seek(0)

    if not header:
        return False

    # PNG: 8-byte fixed signature
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return True

    # PDF: starts with %PDF-
    if header.startswith(b"%PDF-"):
        return True

    # JPEG: starts with SOI 0xFFD8 and commonly followed by 0xFF
    if len(header) >= 3 and header[0:2] == b"\xFF\xD8" and header[2] == 0xFF:
        return True

    # GIF: starts with GIF87a or GIF89a
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return True

    # WebP: starts with RIFF....WEBP
    if len(header) >= 12 and header[0:4] == b"RIFF" and header[8:12] == b"WEBP":
        return True

    # BMP: starts with BM
    if header.startswith(b"BM"):
        return True

    # TIFF: starts with II (little-endian) or MM (big-endian) followed by 42
    if len(header) >= 4:
        if header[0:2] == b"II" and header[2:4] == b"\x2a\x00":  # Little-endian
            return True
        if header[0:2] == b"MM" and header[2:4] == b"\x00\x2a":  # Big-endian
            return True

    # HEIC/HEIF: ISO Base Media File Format with 'ftyp' box
    # Format: [4-byte size][ftyp][brand]
    # Common brands: heic, heix, hevc, hevx, mif1, msf1
    if len(header) >= 12:
        # Check for 'ftyp' at offset 4
        if header[4:8] == b"ftyp":
            brand = header[8:12]
            heic_brands = [b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif"]
            if brand in heic_brands:
                return True

    return False


async def validate_file_size(upload_file: UploadFile, max_size_bytes: int) -> int:
    """
    Asynchronously validates that an uploaded file does not exceed a specified size limit.
    
    Reads the file in chunks to efficiently calculate its size. Raises an HTTP 413 error if the file exceeds the maximum allowed size.
    
    Args:
        upload_file: The file to validate.
        max_size_bytes: The maximum allowed file size in bytes.
    
    Returns:
        The actual size of the file in bytes.
    """
    await upload_file.seek(0)
    
    size = 0
    chunk_size = 8192  # 8 KB chunks
    
    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break
        size += len(chunk)
        
        if size > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum allowed size is {max_size_bytes // (1024 * 1024)} MB."
            )
    
    await upload_file.seek(0)
    return size


async def check_permission(request: MaintenanceRequest, user: User, session: AsyncSession) -> None:
    """
    Verifies that the user has permission to access or modify a maintenance request.
    
    Raises an HTTP 403 error if the user is not an admin and does not own the property associated with the request.
    Raises HTTP 404 if the property is not found, or HTTP 500 if the property relationship cannot be loaded.
    """
    logger.info(f"Checking permissions for user {user.id} on request {request.id}")
    if user.is_admin:
        logger.info(f"User {user.id} is an admin, permission granted.")
        return

    prop = getattr(request, "property", None)

    if prop is None:
        logger.info(f"Property not loaded for request {request.id}, fetching from database.")
        try:
            result = await session.execute(
                select(Property)
                .where(col(Property.id) == request.property_id)
            )
            prop = result.scalar_one_or_none()

            if prop is None:
                logger.error(f"Property not found for maintenance request {request.id}")
                raise HTTPException(
                    status_code=404,
                    detail="Property not found for this maintenance request."
                )

            setattr(request, "property", prop)
            logger.info(f"Property {prop.id} loaded for request {request.id}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to load property relationship for request {request.id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load property relationship: {str(e)}"
            )

    if hasattr(prop, "user_id") and prop.user_id == user.id:
        logger.info(f"User {user.id} owns property {prop.id}, permission granted.")
        return

    if user.user_type == UserType.TENANT and request.user_id == user.id:
        logger.info(f"User {user.id} is a tenant and created the request, permission granted.")
        return
    
    logger.warning(f"User {user.id} does not have permission to access request {request.id}")
    raise HTTPException(
        status_code=403,
        detail="You do not have permission to access this maintenance request."
    )
