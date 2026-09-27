from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from ..logging_setup import job_id_var
from ..models import SourceError
from ..service import NoResultsError, ScrapeRequest, run_scrape

log = logging.getLogger(__name__)

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


class JobQueueFull(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    request: ScrapeRequest
    output_dir: Path
    base_url: str
    status: str = QUEUED
    done: int = 0
    total: int = 0
    message: str = "Menunggu antrian..."
    error: str = ""
    rows: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scanned: int = 0
    source: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "keyword": self.request.keyword,
            "area": self.request.area,
            "max_results": self.request.max_results,
            "price_min": self.request.price_min,
            "price_max": self.request.price_max,
            "done": self.done,
            "total": self.total,
            "message": self.message,
            "error": self.error,
            "rows": self.rows if self.status == DONE else [],
            "warnings": self.warnings,
            "scanned": self.scanned,
            "source": self.source,
            "duration": round((self.finished_at or time.time()) - self.created_at, 1),
        }


class JobManager:
    def __init__(self, output_dir: Path, max_workers: int = 2, max_pending: int = 5, max_jobs: int = 50) -> None:
        self.output_dir = output_dir
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="scrape")
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._max_pending = max_pending
        self._max_jobs = max_jobs

    def submit(self, request: ScrapeRequest, base_url: str) -> Job:
        with self._lock:
            active = sum(1 for job in self._jobs.values() if job.status in {QUEUED, RUNNING})
            if active >= self._max_pending:
                raise JobQueueFull("Terlalu banyak scraping yang sedang berjalan. Tunggu sebentar lalu coba lagi.")
            job_id = uuid.uuid4().hex
            job = Job(id=job_id, request=request, output_dir=self.output_dir / job_id, base_url=base_url)
            self._jobs[job_id] = job
            self._evict_old()

        self._executor.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _evict_old(self) -> None:
        finished = [job for job in self._jobs.values() if job.status in {DONE, FAILED}]
        for job in finished[: max(0, len(self._jobs) - self._max_jobs)]:
            self._jobs.pop(job.id, None)

    def _progress(self, job: Job, done: int, total: int, message: str) -> None:
        job.done, job.total, job.message = done, total, message

    def _run(self, job: Job) -> None:
        job_id_var.set(job.id[:8])
        job.status = RUNNING
        log.info("Job dimulai: keyword=%r area=%r max=%d base=%s",
                 job.request.keyword, job.request.area, job.request.max_results, job.base_url)
        try:
            result = run_scrape(
                job.request, job.output_dir, job.base_url, job.id,
                lambda done, total, message: self._progress(job, done, total, message),
            )
        except NoResultsError as exc:
            self._fail(job, str(exc))
        except SourceError as exc:
            log.error("Sumber data error: %s | detail: %s", exc.user_message, exc.detail)
            self._fail(job, exc.user_message)
        except Exception:
            log.exception("Error tidak terduga")
            self._fail(job, f"Terjadi kesalahan internal. Cek logs/scraper.log (job {job.id[:8]}).")
        else:
            job.rows = result.rows
            job.warnings = result.warnings
            job.scanned, job.source = result.scanned, result.source
            job.message = f"Berhasil mengambil {len(result.rows)} data."
            job.finished_at = time.time()
            job.status = DONE
            log.info("Job selesai dalam %.1f detik", job.finished_at - job.created_at)

    def _fail(self, job: Job, message: str) -> None:
        job.error = message
        job.message = message
        job.finished_at = time.time()
        job.status = FAILED
        log.warning("Job gagal: %s", message)
