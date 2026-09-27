from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import requests

from ..models import Photo, Place, SourceError
from ..normalize import canonical_area, google_maps_link, instagram_url, is_instagram, is_safe_url
from ..safe_http import USER_AGENT

log = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_TIMEOUT = (5, 45)
_BUSY_MESSAGE = "Server OpenStreetMap sedang sibuk. Coba lagi 1-2 menit lagi."
CACHE_TTL_SECONDS = 24 * 3600
_AROUND_METERS = 3000
_MAX_ELEMENTS = 1500
_HAS_WEBSITE = '[~"^(website|contact:website|url)$"~"."]'
_POI_KEYS = ("amenity", "shop", "leisure", "tourism", "office", "craft", "healthcare")
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)

_RESTAURANT = ('amenity', 'restaurant')
_CAFE = ('amenity', 'cafe')
_SALON = ('shop', 'hairdresser|beauty')
KEYWORD_TAGS: dict[str, tuple[tuple[str, str], ...]] = {
    "restoran": (_RESTAURANT,),
    "restaurant": (_RESTAURANT,),
    "rumah makan": (_RESTAURANT,),
    "warung": (_RESTAURANT, ("amenity", "fast_food")),
    "fast food": (("amenity", "fast_food"),),
    "cafe": (_CAFE,),
    "kafe": (_CAFE,),
    "kopi": (_CAFE,),
    "coffee": (_CAFE,),
    "coffee shop": (_CAFE,),
    "salon": (_SALON,),
    "barbershop": (("shop", "hairdresser"),),
    "barber": (("shop", "hairdresser"),),
    "spa": (("leisure", "spa"), ("shop", "beauty"), ("shop", "massage")),
    "gym": (("leisure", "fitness_centre"),),
    "fitness": (("leisure", "fitness_centre"),),
    "hotel": (("tourism", "hotel"),),
    "penginapan": (("tourism", "hotel|guest_house|hostel"),),
    "klinik gigi": (("amenity", "dentist"),),
    "dokter gigi": (("amenity", "dentist"),),
    "klinik": (("amenity", "clinic|doctors"),),
    "apotek": (("amenity", "pharmacy"),),
    "rumah sakit": (("amenity", "hospital"),),
    "bengkel": (("shop", "car_repair|motorcycle_repair"),),
    "laundry": (("shop", "laundry|dry_cleaning"),),
    "bakery": (("shop", "bakery|pastry"),),
    "toko roti": (("shop", "bakery|pastry"),),
    "toko kue": (("shop", "bakery|pastry|confectionery"),),
    "minimarket": (("shop", "convenience"),),
    "supermarket": (("shop", "supermarket"),),
    "bar": (("amenity", "bar|pub"),),
    "toko bunga": (("shop", "florist"),),
    "florist": (("shop", "florist"),),
    "pet shop": (("shop", "pet"),),
    "petshop": (("shop", "pet"),),
    "fotokopi": (("shop", "copyshop"),),
    "optik": (("shop", "optician"),),
    "coworking": (("amenity", "coworking_space"), ("office", "coworking")),
}


@dataclass(frozen=True)
class AreaFilter:
    statement: str
    label: str


def _name_pattern(keyword: str) -> str:
    return " ".join(_NON_WORD.sub(" ", keyword).split())


def build_query(keyword: str, area: AreaFilter, require_website: bool = False) -> str:
    scope = "(area.a)" if area.statement.startswith("area") else area.statement
    extra = _HAS_WEBSITE if require_website else ""
    tags = KEYWORD_TAGS.get(" ".join(keyword.lower().split()), ())
    lines = [f'  nwr["{key}"~"^({value})$"]["name"]{extra}{scope};' for key, value in tags]
    pattern = _name_pattern(keyword)
    if not tags and len(pattern) >= 2:
        lines.extend(f'  nwr["{key}"]["name"~"{pattern}",i]{extra}{scope};' for key in _POI_KEYS)
    header = f"{area.statement};\n" if area.statement.startswith("area") else ""
    return f"[out:json][timeout:40];\n{header}(\n" + "\n".join(lines) + f"\n);\nout center tags {_MAX_ELEMENTS};"


def _first(tags: dict, *keys: str) -> str | None:
    for key in keys:
        value = (tags.get(key) or "").split(";")[0].strip()
        if value:
            return value
    return None


def _address(tags: dict, fallback: str) -> str:
    street = " ".join(filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")]))
    parts = [street, tags.get("addr:suburb") or tags.get("addr:subdistrict"), tags.get("addr:city")]
    joined = ", ".join(p for p in parts if p)
    return joined or fallback


def element_to_place(element: dict, area_label: str) -> Place | None:
    tags = element.get("tags") or {}
    name = (tags.get("name") or "").strip()
    if not name:
        return None
    website = _first(tags, "website", "contact:website", "url")
    image = _first(tags, "image")
    address = _address(tags, area_label)
    return Place(
        place_id=f"osm:{element.get('type')}/{element.get('id')}",
        name=name,
        address=address,
        maps_url=google_maps_link(name, ", ".join(filter(None, [tags.get("addr:street"), area_label]))),
        phone=_first(tags, "phone", "contact:phone", "contact:mobile", "contact:whatsapp"),
        website=website if is_safe_url(website) else None,
        instagram=instagram_url(_first(tags, "contact:instagram", "instagram"))
        or (instagram_url(website) if is_instagram(website) else None),
        photos=(Photo(image),) if is_safe_url(image) else (),
    )


def _dedupe_by_name(places: list[Place]) -> list[Place]:
    seen: set[str] = set()
    unique = []
    for place in places:
        key = place.name.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(place)
    return unique


def completeness(place: Place) -> int:
    return 3 * bool(place.phone) + 2 * bool(place.instagram) + 2 * bool(place.website) + bool(place.photos)


class OsmClient:
    label = "OpenStreetMap"

    def __init__(self, session: requests.Session | None = None, cache_dir: Path | None = None) -> None:
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        self._cache_dir = cache_dir

    def _cached(self, namespace: str, key: str, fetch):
        if not self._cache_dir:
            return fetch()
        path = self._cache_dir / f"{namespace}-{hashlib.sha1(key.encode()).hexdigest()}.json"
        cached = None
        if path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cached = None
        if cached is not None and time.time() - path.stat().st_mtime < CACHE_TTL_SECONDS:
            log.info("Cache %s dipakai (%s)", namespace, path.name)
            return cached
        try:
            data = fetch()
        except SourceError:
            if cached is None:
                raise
            log.warning("Server gagal, memakai cache %s lama (%s)", namespace, path.name)
            return cached
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def _get_json(self, method: str, url: str, **kwargs) -> dict | list:
        try:
            response = self._session.request(method, url, timeout=_TIMEOUT, **kwargs)
        except requests.Timeout as exc:
            raise SourceError(_BUSY_MESSAGE, f"{url}: {exc}") from exc
        except requests.RequestException as exc:
            raise SourceError("Tidak bisa terhubung ke server OpenStreetMap. Cek koneksi internet.", str(exc)) from exc
        if response.status_code in {429, 502, 503, 504}:
            raise SourceError(_BUSY_MESSAGE, f"{url}: HTTP {response.status_code}")
        if not response.ok:
            raise SourceError(f"OpenStreetMap error (HTTP {response.status_code}).", response.text[:300])
        try:
            return response.json()
        except ValueError as exc:
            raise SourceError("Respons OpenStreetMap tidak valid.", response.text[:300]) from exc

    def _resolve_area(self, area: str) -> AreaFilter:
        query = canonical_area(area)
        results = self._cached("nominatim", query.lower(), lambda: self._get_json(
            "GET", NOMINATIM_URL,
            params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "id", "accept-language": "id"},
        ))
        if not results:
            raise SourceError(f"Area \"{area}\" tidak ditemukan. Coba nama lengkap, mis. \"Jakarta Selatan\".")

        match = results[0]
        label = match.get("name") or query
        osm_type, osm_id = match.get("osm_type"), int(match.get("osm_id", 0))
        log.info("Area %r -> %s/%s (%s)", area, osm_type, osm_id, match.get("display_name", "")[:120])
        if osm_type == "relation":
            return AreaFilter(f"area({3_600_000_000 + osm_id})->.a", label)
        if osm_type == "way" and match.get("class") in {"boundary", "place", "landuse"}:
            return AreaFilter(f"area({2_400_000_000 + osm_id})->.a", label)
        lat, lon = float(match["lat"]), float(match["lon"])
        return AreaFilter(f"(around:{_AROUND_METERS},{lat},{lon})", label)

    def _overpass(self, query: str) -> list[dict]:
        last_error: SourceError | None = None
        for url in OVERPASS_URLS:
            try:
                return self._get_json("POST", url, data={"data": query}).get("elements", [])
            except SourceError as exc:
                log.warning("Overpass gagal, coba mirror berikutnya: %s", exc.detail or exc.user_message)
                last_error = exc
        raise last_error

    def search(self, request) -> Iterator[Place]:
        area = self._resolve_area(request.area)
        query = build_query(request.keyword, area, require_website=request.has_price_filter)
        log.debug("Overpass query:\n%s", query)
        elements = self._cached("overpass", query, lambda: self._overpass(query))
        places = [p for p in (element_to_place(e, area.label) for e in elements) if p]
        places.sort(key=completeness, reverse=True)
        unique = _dedupe_by_name(places)
        log.info("OSM: %d elemen, %d tempat unik", len(elements), len(unique))
        yield from unique
