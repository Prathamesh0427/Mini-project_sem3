"""Public entry point used by the web service."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import DetectorConfig
from .signal import analyze_traces
from .video import extract_traces, get_face_finder, probe_video

_PROCESS_LOCK = __import__("threading").Lock()  # one video at a time: the face model is not thread-safe


def analyze_video(path: str | Path, model_path: str | Path | None = None, cfg: DetectorConfig | None = None,
                  progress: Callable[[int, int], None] | None = None,
                  should_cancel: Callable[[], bool] | None = None):
    """Analyse a video file. Returns (result_dict, thumbnail_bgr_or_None). Raises VideoError/Cancelled."""
    cfg = cfg or DetectorConfig()
    meta = probe_video(path, cfg)
    with _PROCESS_LOCK:
        finder = get_face_finder(model_path)
        tr = extract_traces(path, cfg, finder, progress, should_cancel)
        result = analyze_traces(tr["t"], tr["rois"], tr["background"], tr["motion_index"], finder.backend,
                                tr["warnings"], cfg)
    result["video"] = {**meta, "frames_read": tr["frames_read"]}
    return result, tr["thumbnail"]
