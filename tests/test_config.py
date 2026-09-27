import pytest

from scraper import config


@pytest.mark.parametrize("value", ["ftp://x", "http://", "http://host/path", "http://host?x=1", "javascript:alert(1)"])
def test_invalid_public_base_url(monkeypatch, value):
    monkeypatch.setenv("PUBLIC_BASE_URL", value)
    with pytest.raises(config.ConfigError):
        config.load()


def test_defaults_and_fallback(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9000")
    cfg = config.load()
    assert cfg.public_base_url == ""
    assert cfg.fallback_base_url == "http://127.0.0.1:9000"


def test_public_base_url_trailing_slash_trimmed(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://scraper.kantor.id/")
    assert config.load().public_base_url == "https://scraper.kantor.id"
