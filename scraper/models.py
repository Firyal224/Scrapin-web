from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .service import ScrapeRequest


class SourceError(RuntimeError):
    def __init__(self, user_message: str, detail: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = " ".join(detail.split())


@dataclass(frozen=True)
class Photo:
    url: str
    is_menu: bool = False


@dataclass(frozen=True)
class Place:
    place_id: str
    name: str
    address: str
    maps_url: str
    phone: str | None = None
    website: str | None = None
    instagram: str | None = None
    photos: tuple[Photo, ...] = ()
    prices: tuple[int, ...] = ()


class Source(Protocol):
    label: str

    def search(self, request: ScrapeRequest) -> Iterator[Place]: ...
