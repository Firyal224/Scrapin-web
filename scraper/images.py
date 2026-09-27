from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

from . import safe_http

Image.MAX_IMAGE_PIXELS = 30_000_000
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
_MAX_SIDE = 800
MIN_SIDE = 200


class InvalidImageError(ValueError):
    pass


def looks_like_graphic(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info:
        alpha = image.convert("RGBA").getchannel("A").resize((96, 96))
        transparent = sum(alpha.histogram()[:16])
        if transparent / (96 * 96) > 0.10:
            return True
    small = image.convert("RGB").resize((96, 96)).point(lambda value: value // 24)
    buckets = small.getcolors(96 * 96) or []
    dominant = max(count for count, _ in buckets) / (96 * 96)
    return dominant >= 0.65 or (dominant >= 0.5 and len(buckets) < 60)


def to_jpeg(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if min(image.size) < MIN_SIDE:
                raise InvalidImageError(f"Gambar terlalu kecil ({image.size[0]}x{image.size[1]})")
            if looks_like_graphic(image):
                raise InvalidImageError("Gambar terdeteksi sebagai logo/grafik, bukan foto")
            image = image.convert("RGB")
            image.thumbnail((_MAX_SIDE, _MAX_SIDE))
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("Data bukan gambar yang valid") from exc
    return buffer.getvalue()


def download_image(url: str) -> bytes:
    data, _ = safe_http.fetch(url, MAX_DOWNLOAD_BYTES, accept="image/*")
    return to_jpeg(data)
