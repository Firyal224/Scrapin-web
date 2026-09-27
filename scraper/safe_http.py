from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "ScrapIn/1.0 (local business data scraper)"
_TIMEOUT = (5, 10)
_MAX_REDIRECTS = 3
_ALLOWED_PORTS = {None, 80, 443}


class UnsafeUrlError(ValueError):
    pass


def ensure_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError(f"Skema/host tidak diizinkan: {url[:100]}")
    if parsed.port not in _ALLOWED_PORTS:
        raise UnsafeUrlError(f"Port tidak diizinkan: {parsed.port}")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Host tidak bisa diresolve: {parsed.hostname}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise UnsafeUrlError(f"Host mengarah ke IP nonpublik: {parsed.hostname}")


def fetch(url: str, max_bytes: int, accept: str = "*/*") -> tuple[bytes, str]:
    for _ in range(_MAX_REDIRECTS + 1):
        ensure_public_url(url)
        with requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": accept},
            timeout=_TIMEOUT,
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise UnsafeUrlError(f"Respons melebihi {max_bytes} byte")
                chunks.append(chunk)
            return b"".join(chunks), url
    raise UnsafeUrlError("Terlalu banyak redirect")
