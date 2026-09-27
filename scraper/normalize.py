from __future__ import annotations

import re
from urllib.parse import quote_plus, urlparse

from .prices import format_rupiah

_NON_DIGIT = re.compile(r"\D")
_WHITESPACE = re.compile(r"\s+")
_SOCIAL_HOSTS = ("instagram.com", "facebook.com", "tiktok.com", "x.com", "twitter.com", "linktr.ee")
_AREA_ALIASES = {
    "jaksel": "jakarta selatan",
    "jakbar": "jakarta barat",
    "jaktim": "jakarta timur",
    "jakut": "jakarta utara",
    "jakpus": "jakarta pusat",
    "south jakarta": "jakarta selatan",
    "west jakarta": "jakarta barat",
    "east jakarta": "jakarta timur",
    "north jakarta": "jakarta utara",
    "central jakarta": "jakarta pusat",
}
_IG_HANDLE = re.compile(r"^@?([A-Za-z0-9_.]{1,30})$")
_IG_RESERVED = {
    "p", "reel", "reels", "explore", "accounts", "stories", "tv", "about", "developer", "legal", "blog",
    "web", "direct", "privacy", "help", "press", "api", "static", "terms", "directory", "oauth", "challenge",
}


def _clean(text: str) -> str:
    return _WHITESPACE.sub(" ", text.lower()).strip()


def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = _NON_DIGIT.sub("", raw)
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    if not digits.startswith("62") or not 10 <= len(digits) <= 15:
        return None
    return digits


def to_contact(raw_phone: str | None) -> str:
    digits = normalize_phone(raw_phone)
    if not digits:
        return ""
    if digits.startswith("628"):
        return f"https://wa.me/{digits}"
    return f"tel:+{digits}"


def is_safe_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _host_matches(url: str, domain: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


def is_instagram(url: str | None) -> bool:
    return bool(url) and _host_matches(url, "instagram.com")


def instagram_url(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if is_instagram(value if "://" in value else f"https://{value}"):
        path = urlparse(value if "://" in value else f"https://{value}").path.strip("/")
        value = path.split("/")[0] if path else ""
    match = _IG_HANDLE.match(value)
    if not match or match.group(1).lower() in _IG_RESERVED:
        return None
    return f"https://www.instagram.com/{match.group(1)}/"


def instagram_search_link(name: str, area: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(f'{name} {area} instagram')}"


def google_maps_link(name: str, where: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(f'{name}, {where}')}"


def social_link(website: str | None) -> str:
    return website if is_safe_url(website) else ""


def social_label(url: str, name: str) -> str:
    if _host_matches(url, "google.com"):
        return f"Cari IG {name}"
    for domain in _SOCIAL_HOSTS:
        if _host_matches(url, domain):
            prefix = "IG" if domain == "instagram.com" else domain.split(".")[0].capitalize()
            return f"{prefix} {name}"
    return f"Web {name}"


def canonical_area(area: str) -> str:
    return _AREA_ALIASES.get(_clean(area), area.strip())


def build_alasan(
    *, has_contact: bool, social_found: bool, photo_count: int, menu_count: int, prices: tuple[int, ...] = (),
) -> str:
    notes = []
    if not has_contact:
        notes.append("tanpa nomor telepon")
    if not social_found:
        notes.append("IG belum ditemukan (link pencarian)")
    if not photo_count:
        notes.append("tanpa foto")
    elif menu_count:
        notes.append(f"{photo_count} foto ({menu_count} menu/layanan)")
    else:
        notes.append(f"{photo_count} foto")
    if prices:
        low, high = format_rupiah(min(prices)), format_rupiah(max(prices))
        notes.append(f"harga {low} (dari website)" if low == high else f"harga {low} sampai {high} (dari website)")
    return "; ".join(notes)
