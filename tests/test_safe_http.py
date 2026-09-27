import io
import socket

import pytest
from PIL import Image

from scraper import safe_http
from scraper.images import InvalidImageError, to_jpeg


def _resolve_to(ip):
    return lambda host, port, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "http:///nohost",
    "http://example.com:8080/",
])
def test_rejects_bad_scheme_host_or_port(url):
    with pytest.raises(safe_http.UnsafeUrlError):
        safe_http.ensure_public_url(url)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1"])
def test_rejects_private_addresses(monkeypatch, ip):
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", _resolve_to(ip))
    with pytest.raises(safe_http.UnsafeUrlError, match="nonpublik"):
        safe_http.ensure_public_url("https://sneaky.example.com/")


def test_accepts_public_address(monkeypatch):
    monkeypatch.setattr(safe_http.socket, "getaddrinfo", _resolve_to("93.184.216.34"))
    safe_http.ensure_public_url("https://example.com/")


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _photo_like(size=(1200, 600)) -> Image.Image:
    red = Image.linear_gradient("L").resize(size)
    green = Image.linear_gradient("L").rotate(90).resize(size)
    blue = Image.radial_gradient("L").resize(size)
    return Image.merge("RGB", (red, green, blue))


def test_to_jpeg_reencodes_photo():
    data = to_jpeg(_png(_photo_like()))
    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "JPEG"
        assert max(image.size) == 800


@pytest.mark.parametrize("image", [
    Image.new("RGB", (600, 400), "white"),
    Image.new("RGBA", (600, 400), (0, 0, 0, 0)),
    Image.new("RGB", (600, 100), "white").resize((600, 100)),
], ids=["flat", "transparent", "too-small"])
def test_to_jpeg_rejects_graphics_and_small(image):
    with pytest.raises(InvalidImageError):
        to_jpeg(_png(image))


def test_to_jpeg_rejects_garbage():
    with pytest.raises(InvalidImageError):
        to_jpeg(b"<html>not an image</html>")
