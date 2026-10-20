"""FastAPI application. Start with:  uvicorn app.main:create_app --factory --port 8000"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from .config import ALLOWED_EXTENSIONS, Settings, get_settings
from .database import Database
from .detector import DetectorConfig, VideoError, probe_video
from .services.analysis_service import AnalysisService
from .utils.files import clean_filename, ground_truth_from_filename, safe_unlink, sniff_video_container, valid_id

log = logging.getLogger("rppg.api")
VERDICT_FILTERS = {"all", "real_like", "fake_like", "inconclusive", "failed"}


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.init()
    db.mark_interrupted()
    service = AnalysisService(settings, db)
    cfg = DetectorConfig()

    # remove files left behind by a crash or restart
    for p in settings.uploads_dir.iterdir():
        if p.is_file() and p.stem not in db.active_ids():
            safe_unlink(p, settings.uploads_dir)
    for p in settings.artifacts_dir.iterdir():
        if p.is_file() and (not valid_id(p.stem) or db.get(p.stem) is None):
            safe_unlink(p, settings.artifacts_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        service.shutdown()

    app = FastAPI(title="rPPG-Based Explainable Deepfake Detection", lifespan=lifespan)
    app.state.db, app.state.service, app.state.settings = db, service, settings

    @app.exception_handler(VideoError)
    async def _video_error(_, exc: VideoError):
        return JSONResponse(status_code=422, content={"detail": {"code": exc.code, "message": exc.message}})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        return {"max_upload_mb": settings.max_upload_mb, "allowed_extensions": list(ALLOWED_EXTENSIONS),
                "min_duration_s": cfg.min_duration_s, "max_duration_s": cfg.max_duration_s, "min_fps": cfg.min_fps}

    @app.get("/api/stats")
    def stats():
        return db.stats()

    @app.post("/api/analyses", status_code=202)
    async def upload(file: UploadFile = File(...)):
        name = clean_filename(file.filename)
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise _err(415, "unsupported_type", f"Unsupported file type '{ext or 'none'}'. "
                                                f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}.")
        aid = uuid.uuid4().hex
        dest = settings.uploads_dir / f"{aid}{ext}"
        accepted = False
        try:
            size, head = 0, b""
            with open(dest, "wb") as out:
                while chunk := await file.read(1024 * 1024):
                    if not head:
                        head = chunk[:16]
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise _err(413, "too_large", f"File is larger than the {settings.max_upload_mb} MB limit.")
                    out.write(chunk)
            if size == 0:
                raise _err(400, "empty_file", "The uploaded file is empty.")
            if sniff_video_container(head) is None:
                raise _err(415, "not_a_video", "The file content is not a recognised video container "
                                               "(the extension alone is not trusted).")
            meta = await run_in_threadpool(probe_video, dest, cfg)
            meta["file_size_bytes"] = size
            # This optional filename-derived label is stored only for evaluation;
            # it is not passed into analyze_video and cannot affect the prediction.
            db.create(aid, name, meta, ground_truth_from_filename(name))
            accepted = True
        finally:
            await file.close()
            if not accepted:
                safe_unlink(dest, settings.uploads_dir)
        service.submit(aid, dest)
        return {"id": aid, "status": "queued"}

    @app.get("/api/analyses")
    def list_analyses(search: str = Query("", max_length=100), verdict: str = "all", sort: str = "newest",
                      page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
        if verdict not in VERDICT_FILTERS:
            raise _err(400, "bad_filter", "Unknown result filter.")
        if sort not in ("newest", "oldest"):
            raise _err(400, "bad_sort", "Sort must be 'newest' or 'oldest'.")
        items, total = db.list(search.strip(), verdict, sort, page, page_size)
        return {"items": items, "total": total, "page": page, "page_size": page_size,
                "pages": max(1, -(-total // page_size))}

    def _get_or_404(aid: str) -> dict:
        row = db.get(aid) if valid_id(aid) else None
        if row is None:
            raise _err(404, "not_found", "Analysis not found. It may have been deleted.")
        return row

    @app.get("/api/analyses/{aid}")
    def get_analysis(aid: str):
        return _get_or_404(aid)

    @app.get("/api/analyses/{aid}/download")
    def download(aid: str):
        row = _get_or_404(aid)
        return JSONResponse(row, headers={"Content-Disposition": f'attachment; filename="analysis-{aid[:8]}.json"'})

    @app.get("/api/analyses/{aid}/thumbnail")
    def thumbnail(aid: str):
        row = _get_or_404(aid)
        path = settings.artifacts_dir / f"{aid}.jpg"
        if not row["has_thumbnail"] or not path.is_file():
            raise _err(404, "no_thumbnail", "No preview image is stored for this analysis.")
        return FileResponse(path, media_type="image/jpeg")

    @app.delete("/api/analyses/{aid}")
    def delete_analysis(aid: str):
        if not valid_id(aid) or not service.delete(aid):
            raise _err(404, "not_found", "Analysis not found. It may already have been deleted.")
        return {"deleted": True}

    return app
