"""Runs analyses one at a time in a background thread and keeps DB + files consistent."""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2

from ..config import Settings
from ..database import Database
from ..detector import Cancelled, VideoError, analyze_video
from ..utils.files import files_for_id, safe_unlink

log = logging.getLogger("rppg.service")


class AnalysisService:
    def __init__(self, settings: Settings, db: Database):
        self.settings, self.db = settings, db
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rppg-worker")
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def submit(self, analysis_id: str, upload_path: Path) -> None:
        with self._lock:
            self._cancel[analysis_id] = threading.Event()
        self._pool.submit(self._run, analysis_id, upload_path)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def remove_files(self, analysis_id: str) -> None:
        """Delete everything the app stored for this id (upload + generated artifacts)."""
        for root in (self.settings.uploads_dir, self.settings.artifacts_dir):
            for p in files_for_id(root, analysis_id):
                safe_unlink(p, root)

    def delete(self, analysis_id: str) -> bool:
        with self._lock:
            ev = self._cancel.get(analysis_id)
        if ev:
            ev.set()  # tells a running worker to stop
        existed = self.db.delete(analysis_id)
        self.remove_files(analysis_id)
        return existed

    # ------------------------------------------------------------------
    def _run(self, aid: str, path: Path) -> None:
        ev = self._cancel[aid]
        t0 = time.perf_counter()
        try:
            if ev.is_set() or not self.db.set_processing(aid):
                return
            state = {"last": 0}

            def progress(done: int, total: int) -> None:
                if done - state["last"] >= 30 or done == total:
                    state["last"] = done
                    self.db.set_progress(aid, "Finding the face and measuring skin colour", done, total)

            result, thumb = analyze_video(path, self.settings.model_path, progress=progress, should_cancel=ev.is_set)
            if ev.is_set():
                raise Cancelled()

            # Demo-only fallback: retain the genuine rPPG result and its metrics, but
            # allow a labelled demo file to produce a visible UI outcome when rPPG
            # cannot decide. Never describe the fallback percentage as confidence.
            row = self.db.get(aid) or {}
            label = row.get("ground_truth_label")
            if result.get("verdict") == "inconclusive" and label in ("real", "fake"):
                result["detector_verdict"] = "inconclusive"
                result["detector_headline"] = result.get("headline")
                result["prediction_source"] = "demo_filename_fallback"
                result["demo_display_percent"] = 50
                result["verdict"] = "real_like" if label == "real" else "fake_like"
                result["headline"] = ("Demo fallback result: Real (rPPG analysis was inconclusive)."
                                       if label == "real" else
                                       "Demo fallback result: Fake (rPPG analysis was inconclusive).")

            self.db.set_progress(aid, "Computing pulse features")
            has_thumb = False
            if thumb is not None:
                out = self.settings.artifacts_dir / f"{aid}.jpg"
                has_thumb = bool(cv2.imwrite(str(out), thumb))
            if not self.db.complete(aid, result, time.perf_counter() - t0, has_thumb):
                self.remove_files(aid)  # deleted while we were working
        except Cancelled:
            self.remove_files(aid)
        except VideoError as exc:
            self.db.fail(aid, exc.code, exc.message, time.perf_counter() - t0)
        except Exception:  # never leak internals/paths to the user; details go to the log
            log.exception("analysis %s failed", aid)
            self.db.fail(aid, "internal_error", "The analysis failed unexpectedly. See the server log.",
                         time.perf_counter() - t0)
        finally:
            if not self.settings.keep_uploads:
                safe_unlink(path, self.settings.uploads_dir)
            if self.db.get(aid) is None:
                self.remove_files(aid)
            with self._lock:
                self._cancel.pop(aid, None)
