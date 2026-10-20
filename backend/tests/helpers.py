"""Shared helpers for tests (plain functions so they are easy to reuse)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.config import Settings


def make_settings(root: Path) -> Settings:
    return Settings(storage_dir=root / "storage", max_upload_mb=5, keep_uploads=False,
                    model_path=root / "no_model_here.task")


def make_video(path: Path, seconds: float = 12.0, fps: float = 20.0, size=(240, 180)) -> Path:
    """A valid video with NO face: a smooth gradient with slight noise."""
    w, h = size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    assert writer.isOpened(), "OpenCV could not open a video writer (codec missing?)"
    rng = np.random.default_rng(0)
    base = np.tile(np.linspace(60, 180, w, dtype=np.uint8), (h, 1))
    for _ in range(int(seconds * fps)):
        frame = np.dstack([base, base, base]).astype(np.int16) + rng.integers(-3, 4, (h, w, 3))
        writer.write(np.clip(frame, 0, 255).astype(np.uint8))
    writer.release()
    return path


def synthetic_traces(kind: str = "real", seconds: float = 30.0, fps: float = 30.0, seed: int = 0):
    rng = np.random.default_rng(seed)
    t = np.arange(0, seconds, 1 / fps)
    n = len(t)

    def pulse(phase=0.0, f=1.2):
        return 128 + np.sin(2 * np.pi * f * t + phase) + 0.3 * np.sin(4 * np.pi * f * t + phase) + rng.normal(0, 0.35, n)

    if kind == "real":
        rois = {"forehead": pulse(0), "left_cheek": pulse(0.1), "right_cheek": pulse(0.15)}
    elif kind == "noise":
        rois = {k: 128 + rng.normal(0, 1, n) for k in ("forehead", "left_cheek", "right_cheek")}
    elif kind == "inconsistent":
        rois = {"forehead": pulse(0), "left_cheek": pulse(0.1), "right_cheek": pulse(0, f=2.1)}
    else:
        raise ValueError(kind)
    return t, rois
