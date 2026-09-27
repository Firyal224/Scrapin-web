from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import requests

from . import images, safe_http
from .enrich import enrich_from_website
from .models import Place, Source
from .normalize import build_alasan, instagram_search_link, is_instagram, social_link, to_contact
from .output_writer import COLUMNS, write_outputs
from .prices import MAX_PRICE, any_in_range, describe_range
from .sources.osm import OsmClient
from .storage import local_storage

log = logging.getLogger(__name__)

MAX_RESULTS_LIMIT = 60
MAX_PHOTOS_PER_PLACE = 6
GALLERY_FILE = "gallery.json"
_MAX_PRICE_CHECKS = 80
_WORKERS = 5
_TEXT_PATTERN = re.compile(r"^[\w\s&'.,/()-]{2,80}$", re.UNICODE)

ProgressFn = Callable[[int, int, str], None]


class ValidationError(ValueError):
    pass


class NoResultsError(RuntimeError):
    pass


def _optional_price(value, label: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        price = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} harus berupa angka Rupiah.") from exc
    if not 0 <= price <= MAX_PRICE:
        raise ValidationError(f"{label} harus antara 0 dan {MAX_PRICE:,}.".replace(",", "."))
    return price


@dataclass(frozen=True)
class ScrapeRequest:
    keyword: str
    area: str
    max_results: int
    price_min: int | None = None
    price_max: int | None = None

    @classmethod
    def create(cls, keyword, area, max_results, price_min=None, price_max=None) -> "ScrapeRequest":
        keyword = " ".join(str(keyword).split())
        area = " ".join(str(area).split())
        if not _TEXT_PATTERN.match(keyword):
            raise ValidationError("Keyword wajib 2-80 karakter (huruf, angka, spasi, & ' . , / - ( )).")
        if not _TEXT_PATTERN.match(area):
            raise ValidationError("Area wajib 2-80 karakter (huruf, angka, spasi, & ' . , / - ( )).")
        try:
            max_results = int(max_results)
        except (TypeError, ValueError):
            max_results = 0
        if not 1 <= max_results <= MAX_RESULTS_LIMIT:
            raise ValidationError(f"Maks hasil harus antara 1 dan {MAX_RESULTS_LIMIT}.")
        price_min = _optional_price(price_min, "Harga minimum")
        price_max = _optional_price(price_max, "Harga maksimum")
        if price_min is not None and price_max is not None and price_min > price_max:
            raise ValidationError("Harga minimum tidak boleh lebih besar dari harga maksimum.")
        return cls(keyword, area, max_results, price_min or None, price_max)

    @property
    def query(self) -> str:
        return f"{self.keyword} di {self.area}"

    @property
    def has_price_filter(self) -> bool:
        return self.price_min is not None or self.price_max is not None


@dataclass
class ScrapeResult:
    rows: list[dict]
    files: dict[str, Path]
    scanned: int
    source: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class _SavedPhoto:
    file: str
    is_menu: bool


def _parallel(func: Callable, items: Iterable) -> list:
    context = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix="place") as pool:
        return list(pool.map(lambda item: context.copy().run(func, item), items))


def _unique(places: Iterable[Place]) -> Iterable[Place]:
    seen: set[str] = set()
    for place in places:
        if place.place_id not in seen:
            seen.add(place.place_id)
            yield place


def _has_real_website(place: Place) -> bool:
    return bool(place.website) and not is_instagram(place.website)


def _select_by_price(candidates: Iterable[Place], request: ScrapeRequest, progress: ProgressFn) -> tuple[list[Place], int, int]:
    pool = [place for place in candidates if _has_real_website(place)][:_MAX_PRICE_CHECKS]
    selected: list[Place] = []
    checked = with_price = 0
    batch_size = _WORKERS * 2
    for start in range(0, len(pool), batch_size):
        progress(len(selected), request.max_results,
                 f"Mengecek harga di website ({checked}/{len(pool)}), cocok {len(selected)} tempat...")
        for place in _parallel(enrich_from_website, pool[start:start + batch_size]):
            checked += 1
            with_price += bool(place.prices)
            if any_in_range(place.prices, request.price_min, request.price_max):
                selected.append(place)
            else:
                log.info("Lewati (harga %s tidak cocok): %s", list(place.prices[:5]) or "tidak ada", place.name)
        if len(selected) >= request.max_results:
            break
    return selected[: request.max_results], checked, with_price


def _save_photos(place: Place, output_dir: Path) -> list[_SavedPhoto]:
    saved: list[_SavedPhoto] = []
    digests: set[str] = set()
    key = local_storage.place_key(place.name, place.place_id)
    for photo in place.photos:
        if len(saved) >= MAX_PHOTOS_PER_PLACE:
            break
        try:
            data = images.download_image(photo.url)
        except (images.InvalidImageError, safe_http.UnsafeUrlError, requests.RequestException, ValueError) as exc:
            log.info("Foto dilewati untuk %s (%s): %s", place.name, photo.url[:100], exc)
            continue
        digest = hashlib.sha1(data).hexdigest()
        if digest in digests:
            continue
        digests.add(digest)
        saved.append(_SavedPhoto(local_storage.save_image(data, f"{key}_{len(saved) + 1}", output_dir), photo.is_menu))
    return saved


def _build_row(place: Place, request: ScrapeRequest, photos: list[_SavedPhoto], base_url: str, job_id: str) -> dict:
    kontak = to_contact(place.phone)
    sosmed = place.instagram or social_link(place.website)
    key = local_storage.place_key(place.name, place.place_id)
    return {
        "Nama": place.name,
        "Der Treffpunkt": place.maps_url,
        "Sosmed": sosmed or instagram_search_link(place.name, request.area),
        "Kontak": kontak,
        "Gambar": f"{base_url}/galeri/{job_id}/{key}" if photos else "",
        "Alasan": build_alasan(
            has_contact=bool(kontak),
            social_found=bool(sosmed),
            photo_count=len(photos),
            menu_count=sum(p.is_menu for p in photos),
            prices=place.prices,
        ),
        "Alamat": place.address,
        "Foto": [{"src": f"/api/jobs/{job_id}/images/{p.file}", "menu": p.is_menu} for p in photos],
    }


def _write_gallery(output_dir: Path, places: list[Place], photos: list[list[_SavedPhoto]], request: ScrapeRequest) -> None:
    manifest = {
        "keyword": request.keyword,
        "area": request.area,
        "places": {
            local_storage.place_key(place.name, place.place_id): {
                "name": place.name,
                "address": place.address,
                "photos": [{"file": p.file, "menu": p.is_menu} for p in saved],
            }
            for place, saved in zip(places, photos)
            if saved
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / GALLERY_FILE).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _no_results_message(request: ScrapeRequest, checked: int, with_price: int) -> str:
    if request.has_price_filter:
        return (
            f"Tidak ada \"{request.keyword}\" di \"{request.area}\" dengan harga "
            f"{describe_range(request.price_min, request.price_max)}. {checked} website dicek, "
            f"{with_price} di antaranya mencantumkan harga. Coba perlebar range harga atau kosongkan filter harga."
        )
    return (
        f"Tidak ada hasil untuk \"{request.keyword}\" di \"{request.area}\". "
        "Coba keyword lain (mis. restoran, cafe, salon) atau area yang lebih luas."
    )


def run_scrape(
    request: ScrapeRequest,
    output_dir: Path,
    base_url: str,
    job_id: str,
    progress: ProgressFn = lambda *_: None,
    source: Source | None = None,
) -> ScrapeResult:
    source = source or OsmClient(cache_dir=output_dir.parent / ".cache")
    log.info("Mulai scraping via %s: query=%r max=%d harga=%s sampai %s",
             source.label, request.query, request.max_results, request.price_min, request.price_max)
    progress(0, request.max_results, f"Mencari \"{request.keyword}\" di {request.area}...")

    candidates = list(_unique(source.search(request)))
    checked = with_price = 0
    if request.has_price_filter:
        places, checked, with_price = _select_by_price(candidates, request, progress)
        log.info("Filter harga: %d cocok dari %d website (%d mencantumkan harga)", len(places), checked, with_price)
    else:
        places = candidates[: request.max_results]
        progress(0, len(places), f"Membaca website {len(places)} tempat untuk mencari IG, WhatsApp, foto, dan harga...")
        places = _parallel(enrich_from_website, places)

    if not places:
        raise NoResultsError(_no_results_message(request, checked, with_price))

    total = len(places)
    progress(0, total, f"Mengunduh foto dari {total} tempat...")
    photos = _parallel(lambda place: _save_photos(place, output_dir), places)
    warnings = [f"Foto {place.name} tidak ada yang bisa diunduh" for place, saved in zip(places, photos)
                if place.photos and not saved]

    rows = [_build_row(place, request, saved, base_url, job_id) for place, saved in zip(places, photos)]
    _write_gallery(output_dir, places, photos, request)
    files = write_outputs(rows, output_dir)
    progress(total, total, "Selesai")
    log.info("Selesai: %d baris, %d foto ditulis ke %s", len(rows), sum(map(len, photos)), output_dir)
    return ScrapeResult(rows=rows, files=files, scanned=len(candidates), source=source.label, warnings=warnings)


__all__ = ["COLUMNS", "NoResultsError", "ScrapeRequest", "ScrapeResult", "ValidationError", "run_scrape"]
