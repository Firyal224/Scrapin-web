from __future__ import annotations

import re

MIN_PRICE = 2_000
MAX_PRICE = 10_000_000

_RUPIAH = re.compile(r"(?:Rp\.?|IDR)\s?(\d{1,3}(?:[.,]\d{3})+|\d{4,8})(?![\d.,]*\d)", re.I)
_NOT_MONEY = r"(?!\s*(?:followers?|pengikut|views?|likes?|subscribers?|reviews?|ulasan|orders?|terjual|sold|km|kb|mb|gb)\b)"
_SHORTHAND = re.compile(rf"(?<![\w.,])(\d{{1,4}})(?:[.,](\d))?\s?(rb|ribu|k|jt|juta)\b{_NOT_MONEY}", re.I)
_MULTIPLIER = {"rb": 1_000, "ribu": 1_000, "k": 1_000, "jt": 1_000_000, "juta": 1_000_000}


def extract_prices(text: str) -> list[int]:
    prices: list[int] = []
    for match in _RUPIAH.finditer(text):
        prices.append(int(re.sub(r"[.,]", "", match.group(1))))
    for match in _SHORTHAND.finditer(text):
        whole, decimal, unit = match.group(1), match.group(2) or "0", match.group(3).lower()
        multiplier = _MULTIPLIER[unit]
        prices.append(int(whole) * multiplier + int(decimal) * multiplier // 10)
    return sorted({p for p in prices if MIN_PRICE <= p <= MAX_PRICE})


def any_in_range(prices: tuple[int, ...] | list[int], low: int | None, high: int | None) -> bool:
    low = low or 0
    high = high or MAX_PRICE
    return any(low <= price <= high for price in prices)


def format_rupiah(value: int) -> str:
    return "Rp " + f"{value:,}".replace(",", ".")


def describe_range(low: int | None, high: int | None) -> str:
    if low and high:
        return f"{format_rupiah(low)} sampai {format_rupiah(high)}"
    if low:
        return f"minimal {format_rupiah(low)}"
    return f"maksimal {format_rupiah(high)}"
