from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

from ..service import GALLERY_FILE

_KEY = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_FILE = re.compile(r"^[A-Za-z0-9._-]{1,120}\.jpg$")

_PAGE = """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Galeri foto</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #111; color: #fff; font-family: Poppins, system-ui, -apple-system, "Segoe UI", sans-serif; }}
  main {{ max-width: 1120px; margin: 0 auto; padding: 32px 16px 48px; }}
  .eyebrow {{ color: #a597ff; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
  h1 {{ margin: 8px 0 4px; font-size: 28px; font-weight: 900; letter-spacing: -.02em; }}
  p {{ margin: 0; color: #9a9a9a; font-size: 14px; }}
  .grid {{ display: grid; gap: 12px; margin-top: 24px; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }}
  figure {{ margin: 0; position: relative; border-radius: 14px; overflow: hidden; border: 1px solid #2a2a2a; background: #181818; }}
  figure a {{ display: block; }}
  img {{ display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; }}
  .badge {{ position: absolute; top: 10px; left: 10px; padding: 4px 10px; border-radius: 999px; font-size: 11.5px;
           font-weight: 700; color: #efecff; background: rgba(86, 60, 245, .85); }}
  footer {{ margin-top: 28px; font-size: 12px; color: #6f6f6f; }}
</style>
</head>
<body>
<main>
  <span class="eyebrow">Galeri foto · {count} foto</span>
  <h1>{title}</h1>
  <p>{address}</p>
  <div class="grid">{items}</div>
  <footer>Foto diambil dari website tempat usaha. Label “Menu/Layanan” ditentukan otomatis dari halaman atau nama file, jadi bisa saja keliru.</footer>
</main>
</body>
</html>"""

_ITEM = """
    <figure>
      <a href="{src}" target="_blank" rel="noopener">
        <img src="{src}" alt="{alt}" loading="lazy">
      </a>
      {badge}
    </figure>"""


def render_gallery(output_dir: Path, job_id: str, key: str) -> str | None:
    if not _KEY.match(key):
        return None
    manifest_path = output_dir / job_id / GALLERY_FILE
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entry = manifest.get("places", {}).get(key)
    if not entry:
        return None

    photos = [p for p in entry.get("photos", []) if _FILE.match(str(p.get("file", "")))]
    title = escape(str(entry.get("name", "")))
    items = "".join(
        _ITEM.format(
            src=f"/api/jobs/{job_id}/images/{photo['file']}",
            alt=title,
            badge='<span class="badge">Menu/Layanan</span>' if photo.get("menu") else "",
        )
        for photo in photos
    )
    return _PAGE.format(title=title, address=escape(str(entry.get("address", ""))), count=len(photos), items=items)
