"""Video validation, face finding/tracking and per-frame ROI measurement."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from .config import DetectorConfig

ROI_NAMES = ("forehead", "left_cheek", "right_cheek")
Box = tuple[int, int, int, int]


class VideoError(Exception):
    """A video that cannot be analysed at all (as opposed to an inconclusive result)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Cancelled(Exception):
    pass


def probe_video(path: str | Path, cfg: DetectorConfig) -> dict:
    """Open the file, read metadata and decode one frame. Raises VideoError if unusable."""
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise VideoError("unreadable", "The file could not be opened as a video (it may be corrupted).")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        ok, _ = cap.read()
    finally:
        cap.release()
    if not ok:
        raise VideoError("unreadable", "No frames could be decoded from this file.")
    if not np.isfinite(fps) or fps < 1 or fps > 240:
        raise VideoError("bad_fps", f"The video reports an unusable frame rate ({fps:.1f} fps).")
    duration = frames / fps if frames > 0 else None
    meta = {"fps": round(fps, 3), "frame_count": frames or None, "width": width, "height": height,
            "duration_s": round(duration, 3) if duration else None}
    if fps < cfg.min_fps:
        raise VideoError("low_fps", f"Frame rate {fps:.1f} fps is below the {cfg.min_fps:.0f} fps minimum "
                                     "needed to sample a pulse signal reliably.")
    if duration is not None and duration < cfg.min_duration_s:
        raise VideoError("too_short", f"Video is {duration:.1f}s long; at least {cfg.min_duration_s:.0f}s is required.")
    if duration is not None and duration > cfg.max_duration_s:
        raise VideoError("too_long", f"Video is {duration:.0f}s long; the limit is {cfg.max_duration_s:.0f}s.")
    return meta


class FaceFinder:
    """MediaPipe FaceLandmarker if its model file exists, otherwise OpenCV Haar (less accurate)."""

    def __init__(self, model_path: str | Path | None):
        self.backend = "haar"
        self._lm = None
        self._mp = None
        if model_path and Path(model_path).is_file():
            try:
                import mediapipe as mp
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision as mp_vision
                opts = mp_vision.FaceLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
                    num_faces=1, min_face_detection_confidence=0.3,
                    min_face_presence_confidence=0.3, min_tracking_confidence=0.3)
                self._lm = mp_vision.FaceLandmarker.create_from_options(opts)
                self._mp = mp
                self.backend = "mediapipe"
            except Exception:  # missing/old mediapipe or bad model -> fall back
                self._lm = None
        self._haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def find(self, bgr: np.ndarray) -> Optional[Box]:
        if self._lm is not None:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            res = self._lm.detect(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb))
            if res.face_landmarks:
                h, w = bgr.shape[:2]
                xs = [p.x * w for p in res.face_landmarks[0]]
                ys = [p.y * h for p in res.face_landmarks[0]]
                return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            return None
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        dets = self._haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60))
        if len(dets) == 0:
            return None
        x, y, w, h = max(dets, key=lambda d: d[2] * d[3])
        return int(x), int(y), int(x + w), int(y + h)


_finder: Optional[FaceFinder] = None
_finder_key: Optional[str] = None
_finder_lock = threading.Lock()


def get_face_finder(model_path: str | Path | None) -> FaceFinder:
    """Create the face model once and reuse it between requests."""
    global _finder, _finder_key
    key = str(model_path)
    with _finder_lock:
        if _finder is None or _finder_key != key:
            _finder, _finder_key = FaceFinder(model_path), key
        return _finder


def roi_boxes(face: Box) -> dict[str, Box]:
    """Forehead and cheek boxes as fractions of the face box (same fractions as the original notebook)."""
    x0, y0, x1, y1 = face
    fw, fh = x1 - x0, y1 - y0
    return {
        "forehead": (x0 + fw // 4, y0 + int(fh * 0.04), x0 + 3 * fw // 4, y0 + int(fh * 0.22)),
        "left_cheek": (x0 + int(fw * 0.08), y0 + int(fh * 0.42), x0 + int(fw * 0.38), y0 + int(fh * 0.68)),
        "right_cheek": (x0 + int(fw * 0.62), y0 + int(fh * 0.42), x0 + int(fw * 0.92), y0 + int(fh * 0.68)),
    }


def _mean_green(frame: np.ndarray, box: Box) -> float:
    xa, ya = max(0, box[0]), max(0, box[1])
    xb, yb = min(frame.shape[1], box[2]), min(frame.shape[0], box[3])
    if (xb - xa) * (yb - ya) < 16:
        return float("nan")
    return float(frame[ya:yb, xa:xb, 1].mean())


def _enhance_for_detection(frame: np.ndarray) -> np.ndarray:
    """CLAHE on dark frames, used ONLY for finding the face (never for measuring the signal)."""
    if cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean() >= 90:
        return frame
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def extract_traces(path: str | Path, cfg: DetectorConfig, finder: FaceFinder,
                   progress: Callable[[int, int], None] | None = None,
                   should_cancel: Callable[[], bool] | None = None) -> dict:
    """Read EVERY frame (no decimation) and record per-ROI mean green, timestamps and face motion."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoError("unreadable", "The file could not be opened as a video.")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ts, native_ts, idx = [], [], 0
    traces = {n: [] for n in ROI_NAMES}
    bg, cx, cy, fw_list = [], [], [], []
    smooth: Optional[np.ndarray] = None
    miss_run = 0
    thumb = None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            native_ts.append(pos_ms / 1000.0 if pos_ms and pos_ms > 0 else np.nan)
            ts.append(idx / fps)
            if frame.shape[1] != cfg.target_width:
                s = cfg.target_width / frame.shape[1]
                frame = cv2.resize(frame, (cfg.target_width, max(1, int(frame.shape[0] * s))), interpolation=cv2.INTER_AREA)
            bg.append(float(frame[:, :, 1].mean()))
            box = finder.find(_enhance_for_detection(frame))
            if box is None:
                miss_run += 1
                if miss_run > 10:
                    smooth = None
                for n in ROI_NAMES:
                    traces[n].append(np.nan)
                cx.append(np.nan); cy.append(np.nan); fw_list.append(np.nan)
            else:
                miss_run = 0
                b = np.array(box, dtype=float)
                smooth = b if smooth is None else cfg.ema_alpha * b + (1 - cfg.ema_alpha) * smooth
                sb = tuple(int(v) for v in smooth)
                rois = roi_boxes(sb)
                for n in ROI_NAMES:
                    traces[n].append(_mean_green(frame, rois[n]))
                cx.append((sb[0] + sb[2]) / 2); cy.append((sb[1] + sb[3]) / 2); fw_list.append(sb[2] - sb[0])
                if thumb is None and idx >= 5:
                    thumb = frame.copy()
                    cv2.rectangle(thumb, sb[:2], sb[2:], (200, 200, 200), 1)
                    for n, r in rois.items():
                        cv2.rectangle(thumb, r[:2], r[2:], (80, 200, 80), 2)
            idx += 1
            if idx % 10 == 0:
                if should_cancel and should_cancel():
                    raise Cancelled()
                if progress:
                    progress(idx, total or idx)
            if idx / fps > cfg.max_duration_s + 1:
                raise VideoError("too_long", f"Video is longer than {cfg.max_duration_s:.0f}s.")
    finally:
        cap.release()
    if progress:
        progress(idx, idx)
    if idx == 0:
        raise VideoError("unreadable", "No frames could be decoded from this file.")

    t = np.array(ts)
    nt = np.array(native_ts)
    warnings = []
    # use container timestamps only if they are sane (monotonic and consistent with frame count)
    if np.isfinite(nt).all() and np.all(np.diff(nt) > 0) and abs(nt[-1] - t[-1]) < 0.1 * max(t[-1], 1):
        t = nt
        if np.ptp(np.diff(nt)) > 0.5 / fps:
            warnings.append("Frame timing is irregular (variable frame rate); signals were resampled to a uniform grid.")
    else:
        warnings.append("Container timestamps were unusable; assuming a constant frame rate.")
    fwm = np.nanmedian(fw_list) if np.isfinite(fw_list).any() else np.nan
    motion = float(np.sqrt(np.nanvar(cx) + np.nanvar(cy)) / fwm) if np.isfinite(fwm) and fwm > 0 else float("nan")
    return {"t": t, "native_fps": fps, "rois": {n: np.array(v) for n, v in traces.items()},
            "background": np.array(bg), "motion_index": motion, "thumbnail": thumb,
            "frames_read": idx, "warnings": warnings}
