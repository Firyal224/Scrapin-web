from __future__ import annotations

from pathlib import Path

import pytest

from scraper.config import Config
from scraper.models import Place


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        output_dir=tmp_path / "output",
        log_dir=tmp_path / "logs",
        host="127.0.0.1",
        port=8000,
        public_base_url="",
    )


def make_place(pid: str, name: str, **kwargs) -> Place:
    defaults = dict(
        address="Jl. Kemang, Jakarta Selatan",
        maps_url=f"https://www.google.com/maps/search/?api=1&query={pid}",
        phone="0812-3456-7890",
        website="https://www.instagram.com/example/",
    )
    defaults.update(kwargs)
    return Place(place_id=pid, name=name, **defaults)


class FakeSource:
    label = "Fake"

    def __init__(self, places: list[Place]) -> None:
        self.places = places
        self.consumed = 0

    def search(self, request):
        for place in self.places:
            self.consumed += 1
            yield place
