"""
Image Conversion Utility

Handles server-side conversion of HEIC/HEIF images to web-compatible formats (JPEG).
Uses pillow-heif for HEIC support and Pillow for image processing.

Industry best practice: Accept HEIC uploads, convert server-side to JPEG for web display.
This follows the approach used by WordPress 6.7+, Facebook, and other major platforms.
"""

import io
import logging
from typing import BinaryIO

from PIL import Image

# Register HEIC opener with Pillow (must be done before opening HEIC files)
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT_AVAILABLE = True
except ImportError:
    HEIC_SUPPORT_AVAILABLE = False
    logging.warning("pillow-heif not installed - HEIC conversion disabled")

logger = logging.getLogger(__name__)

# Supported HEIC/HEIF MIME types
HEIC_MIME_TYPES = {"image/heic", "image/heif"}

# HEIC magic bytes check (ftyp box with heic/heif brands)
HEIC_BRANDS = [b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif"]


def is_heic_file(file_data: bytes) -> bool:
    """
    Check if file data represents a HEIC/HEIF image by examining magic bytes.

    HEIC uses ISO Base Media File Format with 'ftyp' box at offset 4.

    Args:
        file_data: First 12+ bytes of the file

    Returns:
        True if file is HEIC/HEIF format
    """
    if len(file_data) < 12:
        return False

    # Check for 'ftyp' at offset 4
    if file_data[4:8] != b"ftyp":
        return False

    # Check brand at offset 8
    brand = file_data[8:12]
    return brand in HEIC_BRANDS


async def convert_heic_to_jpeg(
    file_content: bytes,
    quality: int = 85,
    max_dimension: int | None = None
) -> tuple[bytes, str]:
    """
    Convert HEIC/HEIF image to JPEG format.

    Args:
        file_content: Raw bytes of the HEIC file
        quality: JPEG quality (1-100), default 85 for good quality/size balance
        max_dimension: Optional max width/height to resize (maintains aspect ratio)

    Returns:
        Tuple of (jpeg_bytes, new_content_type)

    Raises:
        ValueError: If pillow-heif is not available or conversion fails
    """
    if not HEIC_SUPPORT_AVAILABLE:
        raise ValueError("HEIC conversion not available - pillow-heif not installed")

    try:
        # Open HEIC image from bytes
        with Image.open(io.BytesIO(file_content)) as img:
            # Convert to RGB (required for JPEG - removes alpha channel if present)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Optional resize for very large images
            if max_dimension and (img.width > max_dimension or img.height > max_dimension):
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                logger.info(f"Resized image from original to {img.width}x{img.height}")

            # Preserve EXIF orientation if available
            # Pillow automatically handles this with newer versions

            # Save as JPEG to bytes buffer
            output_buffer = io.BytesIO()
            img.save(
                output_buffer,
                format="JPEG",
                quality=quality,
                optimize=True,
                # Preserve EXIF data
                exif=img.info.get("exif", b"")
            )
            output_buffer.seek(0)

            logger.info(
                f"Converted HEIC to JPEG: "
                f"original={len(file_content)} bytes, "
                f"converted={output_buffer.getbuffer().nbytes} bytes, "
                f"dimensions={img.width}x{img.height}"
            )

            return output_buffer.getvalue(), "image/jpeg"

    except Exception as e:
        logger.error(f"Failed to convert HEIC to JPEG: {e}", exc_info=True)
        raise ValueError(f"HEIC conversion failed: {str(e)}")


async def maybe_convert_image(
    file_content: bytes,
    content_type: str,
    original_filename: str
) -> tuple[bytes, str, str]:
    """
    Convert image to web-compatible format if necessary.

    Currently converts:
    - HEIC/HEIF → JPEG (browsers don't support HEIC natively except Safari)

    Args:
        file_content: Raw file bytes
        content_type: MIME type of the file
        original_filename: Original filename for extension handling

    Returns:
        Tuple of (file_bytes, content_type, new_filename)
        Returns original values if no conversion needed.
    """
    # Check if this is a HEIC file that needs conversion
    needs_conversion = False

    # Check by MIME type
    if content_type.lower() in HEIC_MIME_TYPES:
        needs_conversion = True

    # Check by file extension
    lower_filename = original_filename.lower()
    if lower_filename.endswith((".heic", ".heif")):
        needs_conversion = True

    # Double-check by magic bytes
    if needs_conversion or is_heic_file(file_content[:32]):
        needs_conversion = True

    if not needs_conversion:
        # Return original unchanged
        return file_content, content_type, original_filename

    if not HEIC_SUPPORT_AVAILABLE:
        logger.warning(
            f"HEIC file detected but pillow-heif not available. "
            f"Storing original HEIC file: {original_filename}"
        )
        return file_content, content_type, original_filename

    try:
        # Convert HEIC to JPEG
        converted_bytes, new_content_type = await convert_heic_to_jpeg(file_content)

        # Update filename extension
        new_filename = original_filename
        for ext in [".heic", ".heif", ".HEIC", ".HEIF"]:
            if new_filename.endswith(ext):
                new_filename = new_filename[:-len(ext)] + ".jpg"
                break

        logger.info(f"Converted {original_filename} → {new_filename}")

        return converted_bytes, new_content_type, new_filename

    except Exception as e:
        logger.error(
            f"HEIC conversion failed for {original_filename}, storing original: {e}"
        )
        # Fall back to storing original on conversion failure
        return file_content, content_type, original_filename
