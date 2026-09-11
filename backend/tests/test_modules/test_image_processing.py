from __future__ import annotations

import io

from PIL import Image

from app.resort_os.image_processing import compress_menu_photo


def _raw_jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(30, 90, 150)).save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def test_compress_menu_photo_downscales_large_image():
    raw = _raw_jpeg(1600, 1200)
    processed = compress_menu_photo(raw)

    with Image.open(io.BytesIO(processed)) as result:
        assert result.format == "JPEG"
        assert max(result.size) <= 800
        # النسبة الأصلية (4:3) محفوظة، مش تشويه للصورة
        assert abs(result.size[0] / result.size[1] - 1600 / 1200) < 0.01

    assert len(processed) < len(raw)


def test_compress_menu_photo_leaves_small_image_dimensions_untouched():
    raw = _raw_jpeg(400, 300)
    processed = compress_menu_photo(raw)

    with Image.open(io.BytesIO(processed)) as result:
        assert result.size == (400, 300)


def test_compress_menu_photo_flattens_transparent_png_onto_white():
    buffer = io.BytesIO()
    Image.new("RGBA", (200, 200), color=(10, 200, 10, 0)).save(buffer, format="PNG")
    processed = compress_menu_photo(buffer.getvalue())

    with Image.open(io.BytesIO(processed)) as result:
        assert result.mode == "RGB"
        assert result.format == "JPEG"
