"""Application settings. Everything can be overridden with environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

ALLOWED_EXTENSIONS = (".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv")


@dataclass(frozen=True)
class Settings:
    storage_dir: Path
    max_upload_mb: int
    keep_uploads: bool
    model_path: Path

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def artifacts_dir(self) -> Path:
        return self.storage_dir / "artifacts"

    @property
    def db_path(self) -> Path:
        return self.storage_dir / "analyses.db"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for d in (self.storage_dir, self.uploads_dir, self.artifacts_dir):
            d.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Read settings fresh each call (keeps tests simple)."""
    return Settings(
        storage_dir=Path(os.environ.get("RPPG_STORAGE_DIR", PROJECT_DIR / "storage")).resolve(),
        max_upload_mb=int(os.environ.get("RPPG_MAX_UPLOAD_MB", "200")),
        keep_uploads=os.environ.get("RPPG_KEEP_UPLOADS", "0") == "1",
        model_path=Path(os.environ.get("RPPG_FACE_MODEL", BACKEND_DIR / "models" / "face_landmarker.task")),
    )
