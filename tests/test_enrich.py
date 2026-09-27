import pytest

from scraper import enrich, safe_http
from scraper.enrich import enrich_from_website, parse_page
from scraper.models import Photo, Place

HOME = """
<html><head>
  <meta property="og:image" content="/img/cover.jpg">
  <script>var price = "Rp 999.999";</script>
</head><body>
  <img src="/img/logo.png" alt="Logo">
  <img src="/img/icon-small.jpg" width="40" height="40">
  <img data-src="/img/interior.jpg" alt="Suasana">
  <img src="/uploads/menu-kopi.jpg" alt="Kopi susu">
  <a href="https://www.instagram.com/p/abc123/">post</a>
  <a href="https://www.instagram.com/kopia/">IG</a>
  <a href="https://api.whatsapp.com/send?phone=6281211112222&text=hi">WA</a>
  <a href="/our-menu">Lihat Menu</a>
  <a href="/tentang">Pricelist</a>
  <a href="https://other-site.com/menu">Menu partner</a>
  <a href="javascript:alert(1)">x</a>
</body></html>
"""

MENU_PAGE = """
<html><body>
  <h2>Kopi Susu</h2><p>Rp 28.000</p>
  <h2>Croissant</h2><p>35k</p>
  <img src="/img/menu-board.jpg" alt="Daftar menu">
</body></html>
"""


def test_parse_page_extracts_links_photos_and_menu_pages():
    info = parse_page(HOME, "https://kopia.id/")
    assert info.instagram == "https://www.instagram.com/kopia/"
    assert info.phone == "6281211112222"
    assert info.menu_links == ["https://kopia.id/our-menu", "https://kopia.id/tentang"]
    urls = [p.url for p in info.photos]
    assert urls == ["https://kopia.id/img/cover.jpg", "https://kopia.id/img/interior.jpg", "https://kopia.id/uploads/menu-kopi.jpg"]
    assert [p.is_menu for p in info.photos] == [False, False, True]
    assert info.prices == []


def test_parse_menu_page_marks_photos_and_reads_prices():
    info = parse_page(MENU_PAGE, "https://kopia.id/our-menu", is_menu_page=True)
    assert info.prices == [28000, 35000]
    assert info.photos == [Photo("https://kopia.id/img/menu-board.jpg", True)]


def test_parse_page_tel_link():
    info = parse_page('<a href="tel:+62 21 7654321">call</a>', "https://a.id")
    assert info.phone == "62 21 7654321"


def _place(**kwargs) -> Place:
    return Place(place_id="osm:node/1", name="Kopi A", address="X", maps_url="https://maps", **kwargs)


def test_enrich_follows_menu_pages_and_puts_menu_photos_first(monkeypatch):
    pages = {"https://kopia.id": HOME, "https://kopia.id/our-menu": MENU_PAGE, "https://kopia.id/tentang": "<p>Paket 150rb</p>"}
    fetched = []

    def fake_fetch(url, max_bytes, accept):
        fetched.append(url)
        return pages[url].encode(), url

    monkeypatch.setattr(enrich.safe_http, "fetch", fake_fetch)
    place = enrich_from_website(_place(website="https://kopia.id", phone="0812"))

    assert fetched == ["https://kopia.id", "https://kopia.id/our-menu", "https://kopia.id/tentang"]
    assert place.phone == "0812"
    assert place.instagram == "https://www.instagram.com/kopia/"
    assert place.prices == (28000, 35000, 150000)
    assert [p.is_menu for p in place.photos][:2] == [True, True]
    assert place.photos[0].url == "https://kopia.id/img/menu-board.jpg"


def test_enrich_survives_unsafe_url(monkeypatch):
    def boom(*args, **kwargs):
        raise safe_http.UnsafeUrlError("private")

    monkeypatch.setattr(enrich.safe_http, "fetch", boom)
    place = _place(website="http://192.168.1.1")
    assert enrich_from_website(place) is place


@pytest.mark.parametrize("website", [None, "https://instagram.com/kopia"])
def test_enrich_skips_without_real_website(monkeypatch, website):
    monkeypatch.setattr(enrich.safe_http, "fetch", lambda *a, **k: pytest.fail("tidak boleh fetch"))
    place = _place(website=website)
    assert enrich_from_website(place) is place
