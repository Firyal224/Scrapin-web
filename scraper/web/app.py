from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import config
from ..logging_setup import setup_logging
from ..output_writer import CSV_NAME, XLSX_NAME, ZIP_NAME
from ..prices import MAX_PRICE
from ..service import MAX_RESULTS_LIMIT, ScrapeRequest, ValidationError
from .gallery import render_gallery
from .jobs import DONE, JobManager, JobQueueFull

log = logging.getLogger(__name__)

FRONTEND_DIST = config.ROOT_DIR / "frontend" / "dist"
_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
_IMAGE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}\.jpg$")
_HOST_HEADER = re.compile(r"^(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]{1,253})(:\d{1,5})?$")
SOURCE_LABEL = "OpenStreetMap"
_FILES = {
    "csv": (CSV_NAME, "text/csv"),
    "xlsx": (XLSX_NAME, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "zip": (ZIP_NAME, "application/zip"),
}
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


class ScrapeIn(BaseModel):
    keyword: str = Field(max_length=100)
    area: str = Field(max_length=100)
    max_results: int = Field(ge=1, le=MAX_RESULTS_LIMIT)
    price_min: int | None = Field(default=None, ge=0, le=MAX_PRICE)
    price_max: int | None = Field(default=None, ge=0, le=MAX_PRICE)


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message})


def resolve_base_url(request: Request, cfg: config.Config) -> str:
    if cfg.public_base_url:
        return cfg.public_base_url
    host = request.headers.get("host", "")
    scheme = request.url.scheme if request.url.scheme in {"http", "https"} else "http"
    return f"{scheme}://{host}" if _HOST_HEADER.match(host) else cfg.fallback_base_url


def create_app(cfg: config.Config | None = None, manager: JobManager | None = None) -> FastAPI:
    config_error = ""
    if cfg is None:
        try:
            cfg = config.load()
            setup_logging(cfg.log_dir)
        except config.ConfigError as exc:
            setup_logging(config.ROOT_DIR / "logs")
            config_error = str(exc)
            log.error("Konfigurasi tidak valid: %s", exc)
    if cfg and manager is None:
        manager = JobManager(cfg.output_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if manager:
            manager.shutdown()

    app = FastAPI(title="Scraper Tempat Usaha", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        fields = {".".join(str(p) for p in err["loc"][1:]) for err in exc.errors()}
        return _error(422, f"Input tidak valid: {', '.join(sorted(fields)) or 'body'}.")

    def require_job(job_id: str):
        if not _JOB_ID.match(job_id):
            raise HTTPException(404, "Job tidak ditemukan.")
        job = manager.get(job_id) if manager else None
        if not job:
            raise HTTPException(404, "Job tidak ditemukan atau sudah kedaluwarsa.")
        return job

    @app.get("/api/health")
    def health(http_request: Request):
        base_url = resolve_base_url(http_request, cfg) if cfg else ""
        return {"ok": not config_error, "detail": config_error, "source": SOURCE_LABEL, "base_url": base_url}

    @app.post("/api/jobs", status_code=202)
    def create_job(payload: ScrapeIn, http_request: Request):
        if not manager:
            return _error(503, config_error)
        try:
            request = ScrapeRequest.create(
                payload.keyword, payload.area, payload.max_results, payload.price_min, payload.price_max,
            )
            job = manager.submit(request, resolve_base_url(http_request, cfg))
        except ValidationError as exc:
            return _error(422, str(exc))
        except JobQueueFull as exc:
            return _error(429, str(exc))
        log.info("Job %s dibuat: %r di %r", job.id[:8], request.keyword, request.area)
        return job.to_dict()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return require_job(job_id).to_dict()

    @app.get("/api/jobs/{job_id}/files/{kind}")
    def download(job_id: str, kind: str):
        job = require_job(job_id)
        if kind not in _FILES:
            raise HTTPException(404, "Format file tidak dikenal.")
        if job.status != DONE:
            raise HTTPException(409, "Scraping belum selesai.")
        name, media_type = _FILES[kind]
        path = job.output_dir / name
        if not path.is_file():
            raise HTTPException(404, "File hasil tidak ditemukan.")
        slug = re.sub(r"[^a-z0-9]+", "-", f"{job.request.keyword} {job.request.area}".lower()).strip("-")[:60]
        return FileResponse(path, media_type=media_type, filename=f"{slug or 'hasil'}.{kind}")

    @app.get("/api/jobs/{job_id}/images/{filename}")
    def image(job_id: str, filename: str):
        if not manager or not _JOB_ID.match(job_id) or not _IMAGE_NAME.match(filename):
            raise HTTPException(404, "Gambar tidak ditemukan.")
        images_dir = (manager.output_dir / job_id / "images").resolve()
        path = (images_dir / filename).resolve()
        if path.parent != images_dir or not path.is_file():
            raise HTTPException(404, "Gambar tidak ditemukan.")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/galeri/{job_id}/{key}", response_class=HTMLResponse)
    def gallery(job_id: str, key: str):
        page = render_gallery(manager.output_dir, job_id, key) if manager and _JOB_ID.match(job_id) else None
        if page is None:
            raise HTTPException(404, "Galeri tidak ditemukan.")
        return HTMLResponse(page)

    @app.exception_handler(HTTPException)
    async def http_handler(_: Request, exc: HTTPException):
        return _error(exc.status_code, str(exc.detail))

    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    else:
        @app.get("/")
        def frontend_missing():
            return _error(503, "Frontend belum dibuild. Jalankan: cd frontend && npm install && npm run build")

    return app
