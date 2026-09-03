"""
Unit tests for image_converter utility module.

Tests HEIC/HEIF to JPEG conversion functionality used for processing
iPhone photos uploaded to maintenance requests.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import io

from Backend.utils.image_converter import (
    is_heic_file,
    convert_heic_to_jpeg,
    maybe_convert_image,
    HEIC_MIME_TYPES,
    HEIC_BRANDS,
)

# Mark all tests as unit tests
pytestmark = pytest.mark.unit


# =============================================================================
# is_heic_file TESTS
# =============================================================================

class TestIsHeicFile:
    """Tests for is_heic_file function."""

    def test_is_heic_file_with_heic_brand(self):
        """Test detection of HEIC file with heic brand."""
        # HEIC format: [4-byte size][ftyp][brand]
        heic_data = b'\x00\x00\x00\x18' + b'ftyp' + b'heic' + b'\x00' * 20
        assert is_heic_file(heic_data) is True

    def test_is_heic_file_with_heix_brand(self):
        """Test detection of HEIC file with heix brand."""
        heic_data = b'\x00\x00\x00\x18' + b'ftyp' + b'heix' + b'\x00' * 20
        assert is_heic_file(heic_data) is True

    def test_is_heic_file_with_hevc_brand(self):
        """Test detection of HEIC file with hevc brand."""
        heic_data = b'\x00\x00\x00\x18' + b'ftyp' + b'hevc' + b'\x00' * 20
        assert is_heic_file(heic_data) is True

    def test_is_heic_file_with_hevx_brand(self):
        """Test detection of HEIC file with hevx brand."""
        heic_data = b'\x00\x00\x00\x18' + b'ftyp' + b'hevx' + b'\x00' * 20
        assert is_heic_file(heic_data) is True

    def test_is_heic_file_with_mif1_brand(self):
        """Test detection of HEIF file with mif1 brand."""
        heif_data = b'\x00\x00\x00\x18' + b'ftyp' + b'mif1' + b'\x00' * 20
        assert is_heic_file(heif_data) is True

    def test_is_heic_file_with_msf1_brand(self):
        """Test detection of HEIF file with msf1 brand."""
        heif_data = b'\x00\x00\x00\x18' + b'ftyp' + b'msf1' + b'\x00' * 20
        assert is_heic_file(heif_data) is True

    def test_is_heic_file_with_avif_brand(self):
        """Test detection of AVIF file."""
        avif_data = b'\x00\x00\x00\x18' + b'ftyp' + b'avif' + b'\x00' * 20
        assert is_heic_file(avif_data) is True

    def test_is_heic_file_too_short(self):
        """Test rejection of data too short to be HEIC (< 12 bytes)."""
        short_data = b'\x00\x00\x00\x18ftyp'  # Only 8 bytes
        assert is_heic_file(short_data) is False

    def test_is_heic_file_no_ftyp(self):
        """Test rejection of file without ftyp box."""
        no_ftyp = b'\x00\x00\x00\x18' + b'xxxx' + b'heic' + b'\x00' * 20
        assert is_heic_file(no_ftyp) is False

    def test_is_heic_file_unknown_brand(self):
        """Test rejection of ftyp with unknown brand."""
        unknown_brand = b'\x00\x00\x00\x18' + b'ftyp' + b'unkn' + b'\x00' * 20
        assert is_heic_file(unknown_brand) is False

    def test_is_heic_file_jpeg(self):
        """Test rejection of JPEG file."""
        jpeg_data = b'\xFF\xD8\xFF\xE0' + b'\x00' * 28
        assert is_heic_file(jpeg_data) is False

    def test_is_heic_file_png(self):
        """Test rejection of PNG file."""
        png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 24
        assert is_heic_file(png_data) is False

    def test_is_heic_file_empty(self):
        """Test rejection of empty data."""
        assert is_heic_file(b'') is False


# =============================================================================
# convert_heic_to_jpeg TESTS
# =============================================================================

class TestConvertHeicToJpeg:
    """Tests for convert_heic_to_jpeg function."""

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', False)
    async def test_convert_heic_no_pillow_heif(self):
        """Test error when pillow-heif is not installed."""
        with pytest.raises(ValueError) as exc_info:
            await convert_heic_to_jpeg(b'fake_heic_data')
        assert "pillow-heif not installed" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True)
    @patch('Backend.utils.image_converter.Image')
    async def test_convert_heic_success_rgb_mode(self, mock_image_class):
        """Test successful HEIC to JPEG conversion with RGB mode."""
        # Create mock image
        mock_img = MagicMock()
        mock_img.mode = "RGB"
        mock_img.width = 1920
        mock_img.height = 1080
        mock_img.info = {}

        # Mock context manager
        mock_image_class.open.return_value.__enter__ = MagicMock(return_value=mock_img)
        mock_image_class.open.return_value.__exit__ = MagicMock(return_value=None)

        # Mock save method to write to buffer
        def mock_save(buffer, format, **kwargs):
            buffer.write(b'fake_jpeg_data')
        mock_img.save = mock_save

        result_bytes, content_type = await convert_heic_to_jpeg(b'fake_heic_data')

        assert content_type == "image/jpeg"
        assert result_bytes == b'fake_jpeg_data'

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True)
    @patch('Backend.utils.image_converter.Image')
    async def test_convert_heic_success_rgba_mode(self, mock_image_class):
        """Test HEIC conversion with RGBA mode (converts to RGB)."""
        mock_img = MagicMock()
        mock_img.mode = "RGBA"
        mock_img.width = 800
        mock_img.height = 600
        mock_img.info = {}

        # Mock convert method
        converted_img = MagicMock()
        converted_img.mode = "RGB"
        converted_img.width = 800
        converted_img.height = 600
        converted_img.info = {}
        mock_img.convert.return_value = converted_img

        mock_image_class.open.return_value.__enter__ = MagicMock(return_value=mock_img)
        mock_image_class.open.return_value.__exit__ = MagicMock(return_value=None)

        def mock_save(buffer, format, **kwargs):
            buffer.write(b'converted_jpeg')
        converted_img.save = mock_save

        result_bytes, content_type = await convert_heic_to_jpeg(b'fake_heic_data')

        mock_img.convert.assert_called_with("RGB")
        assert content_type == "image/jpeg"

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True)
    @patch('Backend.utils.image_converter.Image')
    async def test_convert_heic_success_p_mode(self, mock_image_class):
        """Test HEIC conversion with P (palette) mode."""
        mock_img = MagicMock()
        mock_img.mode = "P"
        mock_img.width = 640
        mock_img.height = 480
        mock_img.info = {}

        converted_img = MagicMock()
        converted_img.mode = "RGB"
        converted_img.width = 640
        converted_img.height = 480
        converted_img.info = {}
        mock_img.convert.return_value = converted_img

        mock_image_class.open.return_value.__enter__ = MagicMock(return_value=mock_img)
        mock_image_class.open.return_value.__exit__ = MagicMock(return_value=None)

        def mock_save(buffer, format, **kwargs):
            buffer.write(b'palette_converted')
        converted_img.save = mock_save

        result_bytes, _ = await convert_heic_to_jpeg(b'fake_heic_data')

        mock_img.convert.assert_called_with("RGB")

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True)
    @patch('Backend.utils.image_converter.Image')
    async def test_convert_heic_success_other_mode(self, mock_image_class):
        """Test HEIC conversion with other mode (like L for grayscale)."""
        mock_img = MagicMock()
        mock_img.mode = "L"  # Grayscale
        mock_img.width = 400
        mock_img.height = 300
        mock_img.info = {}

        converted_img = MagicMock()
        converted_img.mode = "RGB"
        converted_img.width = 400
        converted_img.height = 300
        converted_img.info = {}
        mock_img.convert.return_value = converted_img

        mock_image_class.open.return_value.__enter__ = MagicMock(return_value=mock_img)
        mock_image_class.open.return_value.__exit__ = MagicMock(return_value=None)

        def mock_save(buffer, format, **kwargs):
            buffer.write(b'grayscale_converted')
        converted_img.save = mock_save

        await convert_heic_to_jpeg(b'fake_heic_data')

        mock_img.convert.assert_called_with("RGB")

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True)
    @patch('Backend.utils.image_converter.Image')
    async def test_convert_heic_with_resize(self, mock_image_class):
        """Test HEIC conversion with max_dimension resize."""
        mock_img = MagicMock()
        mock_img.mode = "RGB"
        mock_img.width = 4000  # Large image
        mock_img.height = 3000
        mock_img.info = {}
        mock_img.thumbnail = MagicMock()

        mock_image_class.open.return_value.__enter__ = MagicMock(return_value=mock_img)
        mock_image_class.open.return_value.__exit__ = MagicMock(return_value=None)
        mock_image_class.Resampling.LANCZOS = "LANCZOS"

        def mock_save(buffer, format, **kwargs):
            buffer.write(b'resized_jpeg')
        mock_img.save = mock_save

        await convert_heic_to_jpeg(b'fake_heic_data', max_dimension=2000)

        mock_img.thumbnail.assert_called_once_with((2000, 2000), "LANCZOS")

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True)
    @patch('Backend.utils.image_converter.Image')
    async def test_convert_heic_no_resize_small_image(self, mock_image_class):
        """Test that small images are not resized."""
        mock_img = MagicMock()
        mock_img.mode = "RGB"
        mock_img.width = 800  # Small image
        mock_img.height = 600
        mock_img.info = {}
        mock_img.thumbnail = MagicMock()

        mock_image_class.open.return_value.__enter__ = MagicMock(return_value=mock_img)
        mock_image_class.open.return_value.__exit__ = MagicMock(return_value=None)

        def mock_save(buffer, format, **kwargs):
            buffer.write(b'not_resized')
        mock_img.save = mock_save

        await convert_heic_to_jpeg(b'fake_heic_data', max_dimension=2000)

        mock_img.thumbnail.assert_not_called()

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True)
    @patch('Backend.utils.image_converter.Image')
    async def test_convert_heic_preserves_exif(self, mock_image_class):
        """Test that EXIF data is preserved during conversion."""
        mock_img = MagicMock()
        mock_img.mode = "RGB"
        mock_img.width = 1920
        mock_img.height = 1080
        mock_img.info = {"exif": b'fake_exif_data'}

        mock_image_class.open.return_value.__enter__ = MagicMock(return_value=mock_img)
        mock_image_class.open.return_value.__exit__ = MagicMock(return_value=None)

        save_kwargs = {}
        def mock_save(buffer, format, **kwargs):
            save_kwargs.update(kwargs)
            buffer.write(b'with_exif')
        mock_img.save = mock_save

        await convert_heic_to_jpeg(b'fake_heic_data')

        assert save_kwargs.get('exif') == b'fake_exif_data'

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True)
    @patch('Backend.utils.image_converter.Image')
    async def test_convert_heic_conversion_failure(self, mock_image_class):
        """Test handling of conversion failure."""
        mock_image_class.open.side_effect = Exception("Corrupt HEIC file")

        with pytest.raises(ValueError) as exc_info:
            await convert_heic_to_jpeg(b'corrupt_heic_data')

        assert "HEIC conversion failed" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True)
    @patch('Backend.utils.image_converter.Image')
    async def test_convert_heic_custom_quality(self, mock_image_class):
        """Test HEIC conversion with custom quality setting."""
        mock_img = MagicMock()
        mock_img.mode = "RGB"
        mock_img.width = 800
        mock_img.height = 600
        mock_img.info = {}

        mock_image_class.open.return_value.__enter__ = MagicMock(return_value=mock_img)
        mock_image_class.open.return_value.__exit__ = MagicMock(return_value=None)

        save_kwargs = {}
        def mock_save(buffer, format, **kwargs):
            save_kwargs.update(kwargs)
            buffer.write(b'custom_quality')
        mock_img.save = mock_save

        await convert_heic_to_jpeg(b'fake_heic_data', quality=95)

        assert save_kwargs.get('quality') == 95


# =============================================================================
# maybe_convert_image TESTS
# =============================================================================

class TestMaybeConvertImage:
    """Tests for maybe_convert_image function."""

    @pytest.mark.asyncio
    async def test_maybe_convert_no_conversion_needed_jpeg(self):
        """Test that JPEG files are returned unchanged."""
        jpeg_content = b'\xFF\xD8\xFF\xE0' + b'\x00' * 100

        result_bytes, result_type, result_name = await maybe_convert_image(
            jpeg_content, "image/jpeg", "photo.jpg"
        )

        assert result_bytes == jpeg_content
        assert result_type == "image/jpeg"
        assert result_name == "photo.jpg"

    @pytest.mark.asyncio
    async def test_maybe_convert_no_conversion_needed_png(self):
        """Test that PNG files are returned unchanged."""
        png_content = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100

        result_bytes, result_type, result_name = await maybe_convert_image(
            png_content, "image/png", "photo.png"
        )

        assert result_bytes == png_content
        assert result_type == "image/png"
        assert result_name == "photo.png"

    @pytest.mark.asyncio
    async def test_maybe_convert_heic_by_mime_type(self):
        """Test conversion triggered by HEIC MIME type."""
        heic_content = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100

        with patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True):
            with patch('Backend.utils.image_converter.convert_heic_to_jpeg') as mock_convert:
                mock_convert.return_value = (b'jpeg_result', "image/jpeg")

                result_bytes, result_type, result_name = await maybe_convert_image(
                    heic_content, "image/heic", "photo.heic"
                )

                assert result_bytes == b'jpeg_result'
                assert result_type == "image/jpeg"
                assert result_name == "photo.jpg"

    @pytest.mark.asyncio
    async def test_maybe_convert_heif_by_mime_type(self):
        """Test conversion triggered by HEIF MIME type."""
        heif_content = b'\x00\x00\x00\x18ftypmif1' + b'\x00' * 100

        with patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True):
            with patch('Backend.utils.image_converter.convert_heic_to_jpeg') as mock_convert:
                mock_convert.return_value = (b'jpeg_result', "image/jpeg")

                result_bytes, result_type, result_name = await maybe_convert_image(
                    heif_content, "image/heif", "photo.heif"
                )

                assert result_bytes == b'jpeg_result'
                assert result_type == "image/jpeg"
                assert result_name == "photo.jpg"

    @pytest.mark.asyncio
    async def test_maybe_convert_heic_by_extension(self):
        """Test conversion triggered by .heic file extension."""
        heic_content = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100

        with patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True):
            with patch('Backend.utils.image_converter.convert_heic_to_jpeg') as mock_convert:
                mock_convert.return_value = (b'jpeg_result', "image/jpeg")

                # Unknown MIME type but .heic extension
                result_bytes, result_type, result_name = await maybe_convert_image(
                    heic_content, "application/octet-stream", "photo.heic"
                )

                assert result_bytes == b'jpeg_result'
                assert result_name == "photo.jpg"

    @pytest.mark.asyncio
    async def test_maybe_convert_heif_by_extension(self):
        """Test conversion triggered by .heif file extension."""
        heif_content = b'\x00\x00\x00\x18ftypmif1' + b'\x00' * 100

        with patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True):
            with patch('Backend.utils.image_converter.convert_heic_to_jpeg') as mock_convert:
                mock_convert.return_value = (b'jpeg_result', "image/jpeg")

                result_bytes, result_type, result_name = await maybe_convert_image(
                    heif_content, "application/octet-stream", "photo.heif"
                )

                assert result_bytes == b'jpeg_result'
                assert result_name == "photo.jpg"

    @pytest.mark.asyncio
    async def test_maybe_convert_heic_by_magic_bytes(self):
        """Test conversion triggered by HEIC magic bytes."""
        heic_content = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100

        with patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True):
            with patch('Backend.utils.image_converter.convert_heic_to_jpeg') as mock_convert:
                mock_convert.return_value = (b'jpeg_result', "image/jpeg")

                # Neither MIME type nor extension, but magic bytes indicate HEIC
                result_bytes, result_type, result_name = await maybe_convert_image(
                    heic_content, "application/octet-stream", "photo.bin"
                )

                assert result_bytes == b'jpeg_result'

    @pytest.mark.asyncio
    async def test_maybe_convert_no_heic_support(self):
        """Test fallback when pillow-heif is not available."""
        heic_content = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100

        with patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', False):
            result_bytes, result_type, result_name = await maybe_convert_image(
                heic_content, "image/heic", "photo.heic"
            )

            # Should return original unchanged
            assert result_bytes == heic_content
            assert result_type == "image/heic"
            assert result_name == "photo.heic"

    @pytest.mark.asyncio
    async def test_maybe_convert_conversion_error_fallback(self):
        """Test fallback to original when conversion fails."""
        heic_content = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100

        with patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True):
            with patch('Backend.utils.image_converter.convert_heic_to_jpeg') as mock_convert:
                mock_convert.side_effect = Exception("Conversion failed")

                result_bytes, result_type, result_name = await maybe_convert_image(
                    heic_content, "image/heic", "photo.heic"
                )

                # Should return original on error
                assert result_bytes == heic_content
                assert result_type == "image/heic"
                assert result_name == "photo.heic"

    @pytest.mark.asyncio
    async def test_maybe_convert_uppercase_extension(self):
        """Test conversion with uppercase file extension."""
        heic_content = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 100

        with patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True):
            with patch('Backend.utils.image_converter.convert_heic_to_jpeg') as mock_convert:
                mock_convert.return_value = (b'jpeg_result', "image/jpeg")

                result_bytes, result_type, result_name = await maybe_convert_image(
                    heic_content, "application/octet-stream", "PHOTO.HEIC"
                )

                assert result_name == "PHOTO.jpg"

    @pytest.mark.asyncio
    async def test_maybe_convert_heif_uppercase_extension(self):
        """Test conversion with uppercase HEIF extension."""
        heif_content = b'\x00\x00\x00\x18ftypmif1' + b'\x00' * 100

        with patch('Backend.utils.image_converter.HEIC_SUPPORT_AVAILABLE', True):
            with patch('Backend.utils.image_converter.convert_heic_to_jpeg') as mock_convert:
                mock_convert.return_value = (b'jpeg_result', "image/jpeg")

                result_bytes, result_type, result_name = await maybe_convert_image(
                    heif_content, "application/octet-stream", "PHOTO.HEIF"
                )

                assert result_name == "PHOTO.jpg"


# =============================================================================
# CONSTANTS TESTS
# =============================================================================

class TestConstants:
    """Tests for module constants."""

    def test_heic_mime_types(self):
        """Test HEIC MIME types constant."""
        assert "image/heic" in HEIC_MIME_TYPES
        assert "image/heif" in HEIC_MIME_TYPES

    def test_heic_brands(self):
        """Test HEIC brands constant."""
        expected_brands = [b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif"]
        for brand in expected_brands:
            assert brand in HEIC_BRANDS
