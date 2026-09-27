import csv
import json
from dataclasses import replace

import pytest

from scraper import service
from scraper.models import Photo
from scraper.service import NoResultsError, ScrapeRequest, ValidationError, run_scrape
from scraper.storage.local_storage import place_key
from tests.conftest import FakeSource, make_place

BASE = "http://10.0.0.5:8000"
JOB = "a" * 32


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(service, "enrich_from_website", lambda place: place)
    monkeypatch.setattr(service.images, "download_image", lambda url: f"jpeg:{url}".encode())


def _run(request, tmp_path, places):
    return run_scrape(request, tmp_path / JOB, BASE, JOB, source=FakeSource(places))


@pytest.mark.parametrize("args", [
    ("", "Jakarta Selatan", 20),
    ("salon", "<script>", 20),
    ("salon", "Jakarta Selatan", 0),
    ("salon", "Jakarta Selatan", 61),
    ("salon", "Jakarta Selatan", "abc"),
    ("salon", "Jakarta Selatan", 5, 100000, 50000),
    ("salon", "Jakarta Selatan", 5, "murah", None),
    ("salon", "Jakarta Selatan", 5, -1, None),
])
def test_request_validation(args):
    with pytest.raises(ValidationError):
        ScrapeRequest.create(*args)


def test_request_normalizes_input():
    request = ScrapeRequest.create("  salon   kecantikan ", " Jakarta   Selatan", "5", "", "150000")
    assert request.query == "salon kecantikan di Jakarta Selatan"
    assert (request.max_results, request.price_min, request.price_max) == (5, None, 150000)
    assert request.has_price_filter


def test_rows_gallery_and_csv(tmp_path):
    photos = tuple(Photo(f"https://a.id/{i}.jpg", is_menu=i < 2) for i in range(8))
    formula_name = "=HYPERLINK(evil)"
    places = [
        make_place("osm:node/1", "Salon A", photos=photos, prices=(50000, 120000)),
        make_place("osm:node/1", "Salon A dup"),
        make_place("osm:way/2", formula_name, phone=None, website=None),
    ]
    result = _run(ScrapeRequest.create("salon", "Jakarta Selatan", 5), tmp_path, places)

    key = place_key("Salon A", "osm:node/1")
    first, second = result.rows
    assert first["Gambar"] == f"{BASE}/galeri/{JOB}/{key}"
    assert len(first["Foto"]) == service.MAX_PHOTOS_PER_PLACE
    assert first["Foto"][0] == {"src": f"/api/jobs/{JOB}/images/{key}_1.jpg", "menu": True}
    assert first["Alasan"] == "6 foto (2 menu/layanan); harga Rp 50.000 sampai Rp 120.000 (dari website)"
    assert second["Gambar"] == ""
    assert second["Alasan"] == "tanpa nomor telepon; IG belum ditemukan (link pencarian); tanpa foto"

    manifest = json.loads((tmp_path / JOB / service.GALLERY_FILE).read_text(encoding="utf-8"))
    assert list(manifest["places"]) == [key]
    assert len(manifest["places"][key]["photos"]) == 6

    with result.files["csv"].open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == ["Nama", "Der Treffpunkt", "Sosmed", "Kontak", "Gambar", "Alasan"]
    assert rows[1]["Nama"] == "'" + formula_name


def test_duplicate_and_broken_photos_are_skipped(tmp_path, monkeypatch):
    def download(url):
        if "broken" in url:
            raise service.images.InvalidImageError("logo")
        return b"same-bytes"

    monkeypatch.setattr(service.images, "download_image", download)
    photos = (Photo("https://a.id/broken.png"), Photo("https://a.id/1.jpg"), Photo("https://a.id/2.jpg"))
    result = _run(ScrapeRequest.create("cafe", "Bandung", 1), tmp_path, [make_place("osm:node/7", "Kopi", photos=photos)])
    assert len(result.rows[0]["Foto"]) == 1
    assert result.warnings == []


def test_place_whose_photos_all_fail_gets_warning(tmp_path, monkeypatch):
    def broken(url):
        raise service.images.InvalidImageError("rusak")

    monkeypatch.setattr(service.images, "download_image", broken)
    result = _run(ScrapeRequest.create("cafe", "Bandung", 1), tmp_path,
                  [make_place("osm:node/7", "Kopi", photos=(Photo("https://a.id/x.jpg"),))])
    assert result.rows[0]["Gambar"] == ""
    assert result.warnings == ["Foto Kopi tidak ada yang bisa diunduh"]


def test_price_filter_is_strict(tmp_path, monkeypatch):
    prices = {"Murah": (20000, 30000), "Pas": (45000, 90000), "Tanpa harga": ()}
    monkeypatch.setattr(service, "enrich_from_website", lambda place: replace(place, prices=prices.get(place.name, ())))
    places = [
        make_place("osm:node/1", "Murah", website="https://murah.id"),
        make_place("osm:node/2", "Tanpa website", website=None),
        make_place("osm:node/3", "Pas", website="https://pas.id"),
        make_place("osm:node/4", "Tanpa harga", website="https://kosong.id"),
        make_place("osm:node/5", "Hanya IG", website="https://instagram.com/x"),
    ]
    request = ScrapeRequest.create("cafe", "Jakarta Selatan", 10, 40000, 100000)
    result = _run(request, tmp_path, places)
    assert [row["Nama"] for row in result.rows] == ["Pas"]
    assert "harga Rp 45.000 sampai Rp 90.000" in result.rows[0]["Alasan"]


def test_price_filter_no_match_explains_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "enrich_from_website", lambda place: replace(place, prices=(20000,)))
    request = ScrapeRequest.create("cafe", "Jakarta Selatan", 5, 100000, None)
    with pytest.raises(NoResultsError, match="minimal Rp 100.000. 1 website dicek, 1 di antaranya mencantumkan harga"):
        _run(request, tmp_path, [make_place("osm:node/1", "Kopi", website="https://kopi.id")])


def test_xlsx_does_not_store_formulas(tmp_path):
    from openpyxl import load_workbook

    result = _run(ScrapeRequest.create("salon", "Jakarta Selatan", 1), tmp_path, [make_place("osm:node/9", "=1+1")])
    sheet = load_workbook(result.files["xlsx"]).active
    assert sheet["A2"].data_type == "s"
    assert sheet["B2"].hyperlink.target.startswith("https://www.google.com/maps/")


def test_run_scrape_no_results(tmp_path):
    with pytest.raises(NoResultsError, match="Coba keyword lain"):
        _run(ScrapeRequest.create("salon", "Jakarta Selatan", 5), tmp_path, [])
