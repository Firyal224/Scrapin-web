from __future__ import annotations

import logging
import sys

import uvicorn

from .. import config
from ..logging_setup import setup_logging
from .app import create_app

log = logging.getLogger("scraper.web")


def main() -> int:
    try:
        cfg = config.load()
    except config.ConfigError as exc:
        print(f"Error konfigurasi: {exc}", file=sys.stderr)
        return 1

    setup_logging(cfg.log_dir)
    log.info("Buka %s di browser. Link foto: %s", cfg.fallback_base_url, cfg.public_base_url or "otomatis mengikuti alamat akses")
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_config=None, server_header=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
