from __future__ import annotations

import contextvars
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

job_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("job_id", default="-")

_FORMAT = "%(asctime)s %(levelname)-7s [job=%(job_id)s] %(name)s: %(message)s"
_configured = False


class _JobIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.job_id = job_id_var.get()
        return True


def setup_logging(log_dir: Path) -> Path:
    global _configured
    log_file = log_dir / "scraper.log"
    if _configured:
        return log_file

    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)
    job_filter = _JobIdFilter()

    file_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    console_handler = logging.StreamHandler()
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        handler.addFilter(job_filter)

    root = logging.getLogger()
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _configured = True
    return log_file
