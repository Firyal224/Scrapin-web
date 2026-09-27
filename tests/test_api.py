import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from scraper.output_writer import write_outputs
from scraper.service import NoResultsError
from scraper.web import jobs as jobs_module
from scraper.web.app import create_app
from scraper.web.jobs import JobManager

PAYLOAD = {"keyword": "salon", "area": "Jakarta Selatan", "max_results": 20}


def _fake_run(request, output_dir, base_url, job_id, progress):
    if request.keyword == "kosong":
        raise NoResultsError("Tidak ada hasil.")
    row = {"Nama": "Salon A", "Der Treffpunkt": "https://maps.google.com", "Sosmed": "", "Kontak": "",
           "Gambar": f"{base_url}/galeri/{job_id}/Salon_A", "Alasan": ""}
    files = write_outputs([row], output_dir)
    return SimpleNamespace(rows=[row], files=files, warnings=[], scanned=3, source="Fake")


def _wait(client, job_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in {"done", "failed"}:
            return body
        time.sleep(0.05)
    raise AssertionError("job tidak selesai")


def _client(cfg):
    manager = JobManager(cfg.output_dir)
    return TestClient(create_app(cfg, manager)), manager


@pytest.fixture
def client(cfg, monkeypatch):
    monkeypatch.setattr(jobs_module, "run_scrape", _fake_run)
    test_client, manager = _client(cfg)
    yield test_client
    manager.shutdown()


def test_happy_path_and_download(client):
    response = client.post("/api/jobs", json=PAYLOAD)
    assert response.status_code == 202
    assert response.headers["X-Frame-Options"] == "DENY"
    body = _wait(client, response.json()["id"])
    assert body["status"] == "done"
    assert body["source"] == "Fake"

    csv_response = client.get(f"/api/jobs/{body['id']}/files/csv")
    assert csv_response.status_code == 200
    assert "salon-jakarta-selatan.csv" in csv_response.headers["content-disposition"]


@pytest.mark.parametrize("host, expected", [
    ("192.168.1.10:8000", "http://192.168.1.10:8000"),
    ("scraper.kantor.local", "http://scraper.kantor.local"),
    ("evil.com/<script>", "http://127.0.0.1:8000"),
    ("", "http://127.0.0.1:8000"),
])
def test_image_links_follow_access_address(client, host, expected):
    job_id = client.post("/api/jobs", json=PAYLOAD, headers={"host": host}).json()["id"]
    body = _wait(client, job_id)
    assert body["rows"][0]["Gambar"] == f"{expected}/galeri/{job_id}/Salon_A"
    assert client.get("/api/health", headers={"host": host}).json()["base_url"] == expected


def test_public_base_url_overrides_host(cfg, monkeypatch):
    monkeypatch.setattr(jobs_module, "run_scrape", _fake_run)
    test_client, manager = _client(replace(cfg, public_base_url="https://scraper.example.com"))
    job_id = test_client.post("/api/jobs", json=PAYLOAD, headers={"host": "10.0.0.1"}).json()["id"]
    body = _wait(test_client, job_id)
    manager.shutdown()
    assert body["rows"][0]["Gambar"].startswith("https://scraper.example.com/galeri/")


def test_no_results_is_reported_as_failure(client):
    response = client.post("/api/jobs", json={**PAYLOAD, "keyword": "kosong"})
    body = _wait(client, response.json()["id"])
    assert body["status"] == "failed"
    assert body["error"] == "Tidak ada hasil."


@pytest.mark.parametrize("payload", [
    {**PAYLOAD, "max_results": 100},
    {**PAYLOAD, "keyword": "<b>"},
    {**PAYLOAD, "price_min": 100000, "price_max": 50000},
    {**PAYLOAD, "price_min": -5},
    {"keyword": "salon"},
])
def test_invalid_input(client, payload):
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"].startswith(("Input tidak valid", "Keyword", "Harga"))


def test_image_served_from_disk_without_job_in_memory(client, cfg):
    job_id = "b" * 32
    images = cfg.output_dir / job_id / "images"
    images.mkdir(parents=True)
    (images / "Kopi_A_node_123.jpg").write_bytes(b"fake-jpeg")

    response = client.get(f"/api/jobs/{job_id}/images/Kopi_A_node_123.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/jobs/{job_id}/images/missing.jpg").status_code == 404


def test_price_filter_is_passed_to_job(client):
    body = client.post("/api/jobs", json={**PAYLOAD, "price_min": 50000, "price_max": None}).json()
    assert (body["price_min"], body["price_max"]) == (50000, None)


def test_gallery_page_renders_escaped(client, cfg):
    job_id = "c" * 32
    folder = cfg.output_dir / job_id
    folder.mkdir(parents=True)
    manifest = {"places": {"Kopi_A_node_1": {
        "name": "<script>alert(1)</script>", "address": "Jl. Kemang",
        "photos": [{"file": "Kopi_A_node_1_1.jpg", "menu": True}, {"file": "../../x.jpg", "menu": False}],
    }}}
    (folder / "gallery.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")

    response = client.get(f"/galeri/{job_id}/Kopi_A_node_1")
    assert response.status_code == 200
    assert "<script>alert(1)" not in response.text
    assert "&lt;script&gt;" in response.text
    assert f"/api/jobs/{job_id}/images/Kopi_A_node_1_1.jpg" in response.text
    assert "../../x.jpg" not in response.text
    assert "Menu/Layanan" in response.text
    assert response.headers["X-Frame-Options"] == "DENY"
    assert client.get(f"/galeri/{job_id}/tidak_ada").status_code == 404
    assert client.get(f"/galeri/{job_id}/..%2F..%2Fsecret").status_code == 404


@pytest.mark.parametrize("path", [
    "/api/jobs/not-a-uuid",
    "/api/jobs/" + "0" * 32,
    "/api/jobs/" + "0" * 32 + "/files/csv",
    "/api/jobs/" + "0" * 32 + "/images/..%2F..%2Fsecret.jpg",
])
def test_unknown_or_malicious_paths_404(client, path):
    assert client.get(path).status_code == 404
