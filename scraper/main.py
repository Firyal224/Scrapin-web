from __future__ import annotations

import argparse
import logging
import sys
import uuid

from . import config
from .logging_setup import setup_logging
from .models import SourceError
from .service import MAX_RESULTS_LIMIT, NoResultsError, ScrapeRequest, ValidationError, run_scrape

log = logging.getLogger("scraper.cli")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scraper data tempat usaha (OpenStreetMap)")
    parser.add_argument("--keyword", required=True, help='contoh: "salon"')
    parser.add_argument("--area", required=True, help='contoh: "Jakarta Selatan"')
    parser.add_argument("--max-results", type=int, default=20, help=f"1-{MAX_RESULTS_LIMIT}")
    parser.add_argument("--price-min", type=int, help="harga minimum (Rupiah), opsional")
    parser.add_argument("--price-max", type=int, help="harga maksimum (Rupiah), opsional")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cfg = config.load()
    except config.ConfigError as exc:
        print(f"Error konfigurasi: {exc}", file=sys.stderr)
        return 1

    log_file = setup_logging(cfg.log_dir)
    try:
        request = ScrapeRequest.create(args.keyword, args.area, args.max_results, args.price_min, args.price_max)
        job_id = uuid.uuid4().hex
        base_url = cfg.public_base_url or cfg.fallback_base_url
        result = run_scrape(request, cfg.output_dir / job_id, base_url, job_id, lambda done, total, msg: log.info(msg))
    except ValidationError as exc:
        log.error("Input tidak valid: %s", exc)
        return 2
    except NoResultsError as exc:
        log.warning("%s", exc)
        return 3
    except SourceError as exc:
        log.error("%s | detail: %s", exc.user_message, exc.detail)
        return 1

    log.info("Berhasil: %d baris -> %s", len(result.rows), result.files["csv"])
    log.info("Log lengkap: %s", log_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
