import pytest

from scraper.normalize import (
    build_alasan, canonical_area, instagram_url, social_label, social_link, to_contact,
)


@pytest.mark.parametrize("raw, expected", [
    ("0812-3456-7890", "https://wa.me/6281234567890"),
    ("+62 812 3456 7890", "https://wa.me/6281234567890"),
    ("(021) 7201234", "tel:+62217201234"),
    ("12345", ""),
    (None, ""),
])
def test_to_contact(raw, expected):
    assert to_contact(raw) == expected


@pytest.mark.parametrize("url, expected", [
    ("https://www.instagram.com/x/", "https://www.instagram.com/x/"),
    ("javascript:alert(1)", ""),
    ("", ""),
    (None, ""),
])
def test_social_link_only_http(url, expected):
    assert social_link(url) == expected


def test_social_label_uses_real_host():
    assert social_label("https://instagram.com/a", "Kopi") == "IG Kopi"
    assert social_label("https://instagram.com.evil.io/a", "Kopi") == "Web Kopi"
    assert social_label("https://kopi.id", "Kopi") == "Web Kopi"


def test_build_alasan():
    text = build_alasan(has_contact=False, social_found=True, photo_count=3, menu_count=1, prices=(25000, 85000))
    assert text == "tanpa nomor telepon; 3 foto (1 menu/layanan); harga Rp 25.000 sampai Rp 85.000 (dari website)"


def test_build_alasan_flags_search_link():
    text = build_alasan(has_contact=True, social_found=False, photo_count=0, menu_count=0)
    assert text == "IG belum ditemukan (link pencarian); tanpa foto"


@pytest.mark.parametrize("value, expected", [
    ("@kopi.kenangan", "https://www.instagram.com/kopi.kenangan/"),
    ("kopikenangan", "https://www.instagram.com/kopikenangan/"),
    ("https://instagram.com/kopikenangan?hl=en", "https://www.instagram.com/kopikenangan/"),
    ("www.instagram.com/kopikenangan/", "https://www.instagram.com/kopikenangan/"),
    ("https://www.instagram.com/p/Da2F2isHz1d/", None),
    ("https://www.instagram.com/blog/", None),
    ("https://evil.com/x", None),
    ("", None),
])
def test_instagram_url(value, expected):
    assert instagram_url(value) == expected


def test_social_label_search_link():
    assert social_label("https://www.google.com/search?q=x", "Kopi") == "Cari IG Kopi"


def test_canonical_area():
    assert canonical_area("Jaksel") == "jakarta selatan"
    assert canonical_area("Bandung") == "Bandung"
