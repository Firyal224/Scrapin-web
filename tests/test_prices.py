import pytest

from scraper.prices import any_in_range, describe_range, extract_prices, format_rupiah


@pytest.mark.parametrize("text, expected", [
    ("Nasi Goreng Rp 35.000", [35000]),
    ("Rp25,000 / IDR 125.000", [25000, 125000]),
    ("Rp. 18000", [18000]),
    ("Kopi 28k, Latte 32K", [28000, 32000]),
    ("mulai 45rb", [45000]),
    ("Treatment 1,2jt", [1200000]),
    ("Paket 1,5 juta", [1500000]),
    ("10k followers dan 2.5K views", []),
    ("Berdiri tahun 2024, telp 0812345678", []),
    ("Rp 500 dan Rp 1.000", []),
])
def test_extract_prices(text, expected):
    assert extract_prices(text) == expected


@pytest.mark.parametrize("prices, low, high, expected", [
    ((25000, 90000), 50000, 100000, True),
    ((25000, 30000), 50000, 100000, False),
    ((150000,), None, 100000, False),
    ((150000,), 100000, None, True),
    ((), None, 100000, False),
])
def test_any_in_range(prices, low, high, expected):
    assert any_in_range(prices, low, high) is expected


def test_formatting():
    assert format_rupiah(1250000) == "Rp 1.250.000"
    assert describe_range(50000, 100000) == "Rp 50.000 sampai Rp 100.000"
    assert describe_range(50000, None) == "minimal Rp 50.000"
    assert describe_range(None, 100000) == "maksimal Rp 100.000"
