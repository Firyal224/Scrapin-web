from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(ROOT_DIR / ".env")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    output_dir: Path
    log_dir: Path
    host: str
    port: int
    public_base_url: str

    @property
    def fallback_base_url(self) -> str:
        host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"http://{host}:{self.port}"


def is_valid_base_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.path in {"", "/"} and not parsed.query


def _path_from_env(name: str, default: str) -> Path:
    raw = Path(os.environ.get(name, default))
    return (raw if raw.is_absolute() else ROOT_DIR / raw).resolve()


def load() -> Config:
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError as exc:
        raise ConfigError("PORT harus berupa angka.") from exc

    public_base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base_url and not is_valid_base_url(public_base_url):
        raise ConfigError(f"PUBLIC_BASE_URL tidak valid: {public_base_url!r}. Contoh: http://192.168.1.10:8000")

    return Config(
        output_dir=_path_from_env("OUTPUT_DIR", "output"),
        log_dir=_path_from_env("LOG_DIR", "logs"),
        host=os.environ.get("HOST", "127.0.0.1").strip(),
        port=port,
        public_base_url=public_base_url,
    )
