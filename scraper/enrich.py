from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

import requests

from . import safe_http
from .models import Photo, Place
from .normalize import instagram_url, is_instagram
from .prices import extract_prices

log = logging.getLogger(__name__)

MAX_PHOTO_CANDIDATES = 20
_MIN_DECLARED_SIDE = 150
_MAX_HTML_BYTES = 1_500_000
_MAX_MENU_PAGES = 2
_WA_PATTERN = re.compile(r"(?:wa\.me/|whatsapp\.com/send/?\?phone=)\+?(\d{9,15})", re.I)
_TEL_PATTERN = re.compile(r"^tel:\+?([\d\s().-]{8,20})$", re.I)
_MENU_WORDS = re.compile(
    r"menu|pricelist|price[-_ ]?list|harga|daftar[-_ ]?harga|layanan|services?|treatments?|paket|katalog|catalog|food|drinks?",
    re.I,
)
_SKIP_IMAGE = re.compile(
    r"logo|icon|favicon|sprite|avatar|placeholder|loader|spinner|pixel|badge|flag|arrow|button|marker|"
    r"facebook|instagram|youtube|twitter|linkedin|whatsapp|tiktok|gofood|grabfood|shopeefood|"
    r"/tr\?|\.svg|\.gif",
    re.I,
)
_SKIP_TEXT_TAGS = {"script", "style", "noscript", "template"}


@dataclass
class PageInfo:
    instagram: str | None = None
    phone: str | None = None
    menu_links: list[str] = field(default_factory=list)
    photos: list[Photo] = field(default_factory=list)
    prices: list[int] = field(default_factory=list)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.images: list[tuple[str, str]] = []
        self.og_image: str | None = None
        self.text: list[str] = []
        self._skip_depth = 0
        self._anchor: list[str] | None = None
        self._anchor_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "").strip() for key, value in attrs}
        if tag in _SKIP_TEXT_TAGS:
            self._skip_depth += 1
        elif tag == "a" and values.get("href"):
            self._anchor, self._anchor_href = [], values["href"]
        elif tag == "img":
            src = values.get("data-src") or values.get("data-lazy-src") or values.get("src") or ""
            declared = [int(v) for v in (values.get("width", ""), values.get("height", "")) if v.isdigit()]
            if declared and min(declared) < _MIN_DECLARED_SIDE:
                return
            if src and not src.startswith("data:"):
                self.images.append((src, f"{values.get('alt', '')} {values.get('title', '')}"))
        elif tag == "meta" and not self.og_image:
            prop = (values.get("property") or values.get("name") or "").lower()
            if prop in {"og:image", "og:image:url", "twitter:image"} and values.get("content"):
                self.og_image = values["content"]

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TEXT_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "a" and self._anchor is not None:
            self.links.append((self._anchor_href, " ".join(self._anchor)))
            self._anchor = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.text.append(data)
        if self._anchor is not None:
            self._anchor.append(data.strip())


def _same_site(url: str, base_url: str) -> bool:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return bool(host) and host == (urlparse(base_url).hostname or "").removeprefix("www.")


def parse_page(html: str, base_url: str, is_menu_page: bool = False) -> PageInfo:
    parser = _PageParser()
    parser.feed(html)
    info = PageInfo(prices=extract_prices(" ".join(parser.text)))

    for href, label in parser.links:
        absolute = urldefrag(urljoin(base_url, href)).url
        if not info.instagram and is_instagram(absolute):
            info.instagram = instagram_url(absolute)
        if not info.phone:
            wa, tel = _WA_PATTERN.search(href), _TEL_PATTERN.match(href)
            if wa:
                info.phone = wa.group(1)
            elif tel:
                info.phone = tel.group(1)
        if (
            _same_site(absolute, base_url)
            and absolute.rstrip("/") != base_url.rstrip("/")
            and _MENU_WORDS.search(f"{urlparse(absolute).path} {label}")
            and absolute not in info.menu_links
        ):
            info.menu_links.append(absolute)

    candidates = [(parser.og_image, "", False)] if parser.og_image else []
    candidates += [(src, alt, is_menu_page) for src, alt in parser.images]
    seen: set[str] = set()
    for src, alt, from_menu_page in candidates:
        absolute = urljoin(base_url, src)
        if urlparse(absolute).scheme not in {"http", "https"} or absolute in seen or _SKIP_IMAGE.search(absolute):
            continue
        seen.add(absolute)
        is_menu = from_menu_page or bool(_MENU_WORDS.search(f"{urlparse(absolute).path} {alt}"))
        info.photos.append(Photo(absolute, is_menu))
    return info


def _fetch_page(url: str) -> tuple[str, str] | None:
    try:
        body, final_url = safe_http.fetch(url, _MAX_HTML_BYTES, accept="text/html")
    except (requests.RequestException, safe_http.UnsafeUrlError) as exc:
        log.info("Halaman %s tidak bisa dibaca: %s", url, exc)
        return None
    return body.decode("utf-8", errors="replace"), final_url


def _merge_photos(*groups: list[Photo] | tuple[Photo, ...]) -> tuple[Photo, ...]:
    merged: dict[str, Photo] = {}
    for group in groups:
        for photo in group:
            if photo.url not in merged or photo.is_menu:
                merged[photo.url] = photo
    ordered = sorted(merged.values(), key=lambda p: not p.is_menu)
    return tuple(ordered[:MAX_PHOTO_CANDIDATES])


def enrich_from_website(place: Place) -> Place:
    if not place.website or is_instagram(place.website):
        return place

    home = _fetch_page(place.website)
    if not home:
        return place
    info = parse_page(*home)

    menu_infos = []
    for link in info.menu_links[:_MAX_MENU_PAGES]:
        page = _fetch_page(link)
        if page:
            menu_infos.append(parse_page(*page, is_menu_page=True))

    everything = [info, *menu_infos]
    prices = sorted({p for page in everything for p in page.prices})
    photos = _merge_photos(place.photos, *(page.photos for page in menu_infos), info.photos)
    log.info(
        "Enrichment %s: %d halaman menu, %d foto (%d menu), %d harga",
        place.name, len(menu_infos), len(photos), sum(p.is_menu for p in photos), len(prices),
    )
    return replace(
        place,
        phone=place.phone or next((page.phone for page in everything if page.phone), None),
        instagram=place.instagram or next((page.instagram for page in everything if page.instagram), None),
        photos=photos,
        prices=tuple(prices),
    )
