from __future__ import annotations

import re
from pathlib import Path

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize(name: str) -> str:
    return _SAFE_CHARS.sub("_", name).strip("._")


def place_key(place_name: str, place_id: str) -> str:
    return f"{_sanitize(place_name)[:60] or 'tempat'}_{_sanitize(place_id)[-8:]}".strip("._")


def save_image(image_bytes: bytes, stem: str, output_dir: Path) -> str:
    images_dir = (output_dir / "images").resolve()
    images_dir.mkdir(parents=True, exist_ok=True)

    target_path = (images_dir / f"{_sanitize(stem)[:100] or 'image'}.jpg").resolve()
    if target_path.parent != images_dir:
        raise ValueError("Path gambar keluar dari direktori output yang diizinkan")

    target_path.write_bytes(image_bytes)
    return target_path.name
