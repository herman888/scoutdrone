"""
Unit tests for Azure Blob Storage maintenance photo upload functionality.

Tests the upload_maintenance_photo_to_blob function including HEIC conversion.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from tempfile import SpooledTemporaryFile

from fastapi import UploadFile

pytestmark = pytest.mark.unit


# =============================================================================
# upload_maintenance_photo_to_blob TESTS
# =============================================================================

class TestUploadMaintenancePhotoToBlob:
    """Tests for upload_maintenance_photo_to_blob function."""

    @pytest.mark.asyncio
    async def test_upload_jpeg_no_conversion(self, mocker):
        """Test uploading JPEG file without HEIC conversion."""
        from Backend.utils.azure_blob import upload_maintenance_photo_to_blob

        # Create mock file
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "photo.jpg"
        mock_file.content_type = "image/jpeg"
        mock_file.seek = AsyncMock()
        mock_file.read = AsyncMock(return_value=b'\xFF\xD8\xFF\xE0' + b'\x00' * 100)

        user_id = uuid4()

        # Mock maybe_convert_image to return original (no conversion)
        mock_convert = mocker.patch(
            "Backend.utils.azure_blob.maybe_convert_image",
            new=AsyncMock(return_value=(
                b'\xFF\xD8\xFF\xE0' + b'\x00' * 100,
                "image/jpeg",
                "photo.jpg"
            ))
        )

        # Mock _upload_to_blob
        mock_upload = mocker.patch(
            "Backend.utils.azure_blob._upload_to_blob",
            new=AsyncMock(return_value="https://storage.blob.core.windows.net/maintenance-photos/photo.jpg")
        )

        # Act
        result = await upload_maintenance_photo_to_blob(file=mock_file, user_id=user_id)

        # Assert
        assert result == "https://storage.blob.core.windows.net/maintenance-photos/photo.jpg"
        mock_convert.assert_called_once()
        mock_upload.assert_called_once_with(
            file=mock_file,
            user_id=user_id,
            container_name="maintenance-photos",
            default_filename_prefix="maintenance_photo",
            safe_filename_suffix_limit=80
        )

    @pytest.mark.asyncio
    async def test_upload_heic_with_conversion(self, mocker):
        """Test uploading HEIC file with conversion to JPEG."""
        from Backend.utils.azure_blob import upload_maintenance_photo_to_blob

        original_content = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100
        converted_content = b'\xFF\xD8\xFF\xE0' + b'\x00' * 50  # Simulated JPEG

        # Create mock file
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "photo.heic"
        mock_file.content_type = "image/heic"
        mock_file.seek = AsyncMock()
        mock_file.read = AsyncMock(return_value=original_content)

        user_id = uuid4()

        # Mock maybe_convert_image to return converted content
        mock_convert = mocker.patch(
            "Backend.utils.azure_blob.maybe_convert_image",
            new=AsyncMock(return_value=(
                converted_content,
                "image/jpeg",
                "photo.jpg"
            ))
        )

        # Mock _upload_to_blob
        mock_upload = mocker.patch(
            "Backend.utils.azure_blob._upload_to_blob",
            new=AsyncMock(return_value="https://storage.blob.core.windows.net/maintenance-photos/photo.jpg")
        )

        # Act
        result = await upload_maintenance_photo_to_blob(file=mock_file, user_id=user_id)

        # Assert
        assert result == "https://storage.blob.core.windows.net/maintenance-photos/photo.jpg"
        mock_convert.assert_called_once()
        # Should have called _upload_to_blob with a converted file
        mock_upload.assert_called_once()
        call_args = mock_upload.call_args
        # The file passed should not be the original mock_file
        assert call_args.kwargs["user_id"] == user_id
        assert call_args.kwargs["container_name"] == "maintenance-photos"

    @pytest.mark.asyncio
    async def test_upload_heic_temp_file_cleanup(self, mocker):
        """Test that temporary file is cleaned up after HEIC conversion."""
        from Backend.utils.azure_blob import upload_maintenance_photo_to_blob

        original_content = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100
        converted_content = b'\xFF\xD8\xFF\xE0' + b'\x00' * 50

        # Create mock file
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "photo.heic"
        mock_file.content_type = "image/heic"
        mock_file.seek = AsyncMock()
        mock_file.read = AsyncMock(return_value=original_content)

        user_id = uuid4()

        # Mock maybe_convert_image
        mocker.patch(
            "Backend.utils.azure_blob.maybe_convert_image",
            new=AsyncMock(return_value=(converted_content, "image/jpeg", "photo.jpg"))
        )

        # Mock _upload_to_blob
        mocker.patch(
            "Backend.utils.azure_blob._upload_to_blob",
            new=AsyncMock(return_value="https://storage.blob.core.windows.net/maintenance-photos/photo.jpg")
        )

        # Track temp file creation
        temp_files_created = []
        original_spooled = SpooledTemporaryFile

        def track_spooled(*args, **kwargs):
            temp = original_spooled(*args, **kwargs)
            temp_files_created.append(temp)
            return temp

        mocker.patch(
            "Backend.utils.azure_blob.SpooledTemporaryFile",
            side_effect=track_spooled
        )

        # Act
        await upload_maintenance_photo_to_blob(file=mock_file, user_id=user_id)

        # Assert - temp file should have been created and closed
        assert len(temp_files_created) == 1
        # The temp file should be closed (close is called in finally block)
        assert temp_files_created[0].closed

    @pytest.mark.asyncio
    async def test_upload_with_missing_filename(self, mocker):
        """Test uploading file with no filename uses default."""
        from Backend.utils.azure_blob import upload_maintenance_photo_to_blob

        # Create mock file with no filename
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = None
        mock_file.content_type = "image/jpeg"
        mock_file.seek = AsyncMock()
        mock_file.read = AsyncMock(return_value=b'\xFF\xD8\xFF\xE0' + b'\x00' * 100)

        user_id = uuid4()

        # Mock maybe_convert_image - should receive "maintenance_photo" as filename
        mock_convert = mocker.patch(
            "Backend.utils.azure_blob.maybe_convert_image",
            new=AsyncMock(return_value=(
                b'\xFF\xD8\xFF\xE0' + b'\x00' * 100,
                "image/jpeg",
                "maintenance_photo"
            ))
        )

        mocker.patch(
            "Backend.utils.azure_blob._upload_to_blob",
            new=AsyncMock(return_value="https://storage.blob.core.windows.net/maintenance-photos/file.jpg")
        )

        # Act
        await upload_maintenance_photo_to_blob(file=mock_file, user_id=user_id)

        # Assert
        call_args = mock_convert.call_args
        assert call_args.kwargs["original_filename"] == "maintenance_photo"

    @pytest.mark.asyncio
    async def test_upload_with_missing_content_type(self, mocker):
        """Test uploading file with no content type uses default."""
        from Backend.utils.azure_blob import upload_maintenance_photo_to_blob

        # Create mock file with no content_type
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "photo.jpg"
        mock_file.content_type = None
        mock_file.seek = AsyncMock()
        mock_file.read = AsyncMock(return_value=b'\xFF\xD8\xFF\xE0' + b'\x00' * 100)

        user_id = uuid4()

        # Mock maybe_convert_image - should receive "application/octet-stream" as content_type
        mock_convert = mocker.patch(
            "Backend.utils.azure_blob.maybe_convert_image",
            new=AsyncMock(return_value=(
                b'\xFF\xD8\xFF\xE0' + b'\x00' * 100,
                "image/jpeg",
                "photo.jpg"
            ))
        )

        mocker.patch(
            "Backend.utils.azure_blob._upload_to_blob",
            new=AsyncMock(return_value="https://storage.blob.core.windows.net/maintenance-photos/photo.jpg")
        )

        # Act
        await upload_maintenance_photo_to_blob(file=mock_file, user_id=user_id)

        # Assert
        call_args = mock_convert.call_args
        assert call_args.kwargs["content_type"] == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_upload_pdf_no_conversion(self, mocker):
        """Test uploading PDF file (not an image, no conversion)."""
        from Backend.utils.azure_blob import upload_maintenance_photo_to_blob

        pdf_content = b'%PDF-1.4' + b'\x00' * 100

        # Create mock file
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "document.pdf"
        mock_file.content_type = "application/pdf"
        mock_file.seek = AsyncMock()
        mock_file.read = AsyncMock(return_value=pdf_content)

        user_id = uuid4()

        # Mock maybe_convert_image to return original (PDFs are not converted)
        mocker.patch(
            "Backend.utils.azure_blob.maybe_convert_image",
            new=AsyncMock(return_value=(pdf_content, "application/pdf", "document.pdf"))
        )

        mock_upload = mocker.patch(
            "Backend.utils.azure_blob._upload_to_blob",
            new=AsyncMock(return_value="https://storage.blob.core.windows.net/maintenance-photos/document.pdf")
        )

        # Act
        result = await upload_maintenance_photo_to_blob(file=mock_file, user_id=user_id)

        # Assert - should use original file (not create converted file)
        assert "document.pdf" in result
        mock_upload.assert_called_once_with(
            file=mock_file,
            user_id=user_id,
            container_name="maintenance-photos",
            default_filename_prefix="maintenance_photo",
            safe_filename_suffix_limit=80
        )

    @pytest.mark.asyncio
    async def test_upload_heic_conversion_error_propagates(self, mocker):
        """Test that errors during HEIC upload propagate correctly."""
        from Backend.utils.azure_blob import upload_maintenance_photo_to_blob

        original_content = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100
        converted_content = b'\xFF\xD8\xFF\xE0' + b'\x00' * 50

        # Create mock file
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "photo.heic"
        mock_file.content_type = "image/heic"
        mock_file.seek = AsyncMock()
        mock_file.read = AsyncMock(return_value=original_content)

        user_id = uuid4()

        # Mock maybe_convert_image
        mocker.patch(
            "Backend.utils.azure_blob.maybe_convert_image",
            new=AsyncMock(return_value=(converted_content, "image/jpeg", "photo.jpg"))
        )

        # Mock _upload_to_blob to raise an error
        mocker.patch(
            "Backend.utils.azure_blob._upload_to_blob",
            new=AsyncMock(side_effect=ConnectionError("Azure storage not available"))
        )

        # Act & Assert
        with pytest.raises(ConnectionError, match="Azure storage not available"):
            await upload_maintenance_photo_to_blob(file=mock_file, user_id=user_id)

    @pytest.mark.asyncio
    async def test_upload_file_seek_calls(self, mocker):
        """Test that file is properly seeked before reading."""
        from Backend.utils.azure_blob import upload_maintenance_photo_to_blob

        # Create mock file
        mock_file = AsyncMock(spec=UploadFile)
        mock_file.filename = "photo.jpg"
        mock_file.content_type = "image/jpeg"
        mock_file.seek = AsyncMock()
        mock_file.read = AsyncMock(return_value=b'\xFF\xD8\xFF\xE0' + b'\x00' * 100)

        user_id = uuid4()

        mocker.patch(
            "Backend.utils.azure_blob.maybe_convert_image",
            new=AsyncMock(return_value=(
                b'\xFF\xD8\xFF\xE0' + b'\x00' * 100,
                "image/jpeg",
                "photo.jpg"
            ))
        )

        mocker.patch(
            "Backend.utils.azure_blob._upload_to_blob",
            new=AsyncMock(return_value="https://storage.blob.core.windows.net/maintenance-photos/photo.jpg")
        )

        # Act
        await upload_maintenance_photo_to_blob(file=mock_file, user_id=user_id)

        # Assert - seek should be called to reset file position
        # First seek(0) before read, second seek(0) after read to reset for potential upload
        assert mock_file.seek.call_count >= 2
        mock_file.seek.assert_any_call(0)
