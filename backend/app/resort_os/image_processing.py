"""app/resort_os/image_processing.py — Pure image-processing helpers.

Pure Python (no FastAPI, no SQLAlchemy) — same domain-engine convention as
food_cost_engine.py / beach_engine.py. Extracted 2026-09-11 so the same
compression logic is shared between the live upload endpoint
(dining/api/router.py::upload_item_image) and any one-off script that seeds
menu photos in bulk, instead of duplicating the resize/compress logic.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps

MAX_DIMENSION = 800
JPEG_QUALITY = 82


def compress_menu_photo(raw_bytes: bytes, max_dimension: int = MAX_DIMENSION, quality: int = JPEG_QUALITY) -> bytes:
    """يصغّر أي صورة مقبولة لأقصى بُعد `max_dimension` (مع الحفاظ على النسبة)
    ويحفظها JPEG مضغوط — الصورة المخزّنة بتتحمّل في مربعات صغيرة (44-128px)
    في شاشة الكاشير، فمفيش داعي لحفظ الصورة الأصلية بحجمها الكامل.

    يحترم دوران الكاميرا (EXIF) قبل التصغير، ويوحّد PNG/WEBP الشفافة على
    خلفية بيضاء (JPEG مالوش alpha channel). Pillow نفسه بيرفض "decompression
    bomb" (صورة أبعادها ضخمة جدًا) تلقائيًا عبر Image.MAX_IMAGE_PIXELS.
    """
    image = Image.open(io.BytesIO(raw_bytes))
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()
