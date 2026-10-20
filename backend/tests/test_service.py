"""Background service: success, failure, cancellation and file cleanup (no web server needed)."""
import threading
import time

import numpy as np

import app.services.analysis_service as svc
from app.database import Database
from app.detector import Cancelled, VideoError, analyze_traces
from app.services.analysis_service import AnalysisService
from app.utils.files import safe_unlink
from tests.helpers import synthetic_traces

AID = "c" * 32


def _setup(settings):
    settings.ensure_dirs()
    db = Database(settings.db_path); db.init()
    return db, AnalysisService(settings, db)


def _enqueue(settings, db, service, name="clip.mp4"):
    up = settings.uploads_dir / f"{AID}.mp4"
    up.write_bytes(b"x")
    db.create(AID, name, {})
    service.submit(AID, up)
    return up


def _wait(db, states=("completed", "failed"), timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        row = db.get(AID)
        if row is None or row["status"] in states:
            return row
        time.sleep(0.05)
    raise AssertionError("timed out")


def _with_detector(fake, fn):
    original = svc.analyze_video
    svc.analyze_video = fake
    try:
        return fn()
    finally:
        svc.analyze_video = original


def _fake_success(path, model_path=None, cfg=None, progress=None, should_cancel=None):
    t, rois = synthetic_traces("real")
    r = analyze_traces(t, rois, None, 0.05, "mediapipe")
    r["video"] = {"fps": 30}
    return r, np.full((60, 80, 3), 120, np.uint8)


def test_success_then_delete_cleans_everything(settings):
    db, service = _setup(settings)

    def run():
        up = _enqueue(settings, db, service)
        row = _wait(db)
        assert row["status"] == "completed" and row["verdict"] == "real_like"
        assert row["processing_seconds"] is not None
        assert not up.exists()                                    # uploaded video removed after analysis
        assert (settings.artifacts_dir / f"{AID}.jpg").is_file()
        assert service.delete(AID) is True
        assert db.get(AID) is None
        assert list(settings.artifacts_dir.iterdir()) == [] and list(settings.uploads_dir.iterdir()) == []
        assert service.delete(AID) is False                       # second delete: nothing left
    _with_detector(_fake_success, run)


def test_unexpected_failure_is_recorded_without_corrupting_db(settings):
    db, service = _setup(settings)

    def boom(*a, **k):
        raise RuntimeError("secret /path/should/not/leak")

    def run():
        _enqueue(settings, db, service)
        row = _wait(db)
        assert row["status"] == "failed" and row["error_code"] == "internal_error"
        assert "secret" not in row["error_message"]
        assert db.stats()["failed"] == 1 and db.list()[1] == 1    # database still healthy
    _with_detector(boom, run)


def test_video_error_is_stored_with_message(settings):
    db, service = _setup(settings)

    def bad(*a, **k):
        raise VideoError("unreadable", "No frames could be decoded from this file.")

    def run():
        _enqueue(settings, db, service)
        row = _wait(db)
        assert row["status"] == "failed" and row["error_code"] == "unreadable"
    _with_detector(bad, run)


def test_delete_while_processing_leaves_no_orphans(settings):
    db, service = _setup(settings)
    started = threading.Event()

    def slow(path, model_path=None, cfg=None, progress=None, should_cancel=None):
        started.set()
        for _ in range(400):
            if should_cancel():
                raise Cancelled()
            time.sleep(0.02)
        raise AssertionError("was not cancelled")

    def run():
        _enqueue(settings, db, service)
        assert started.wait(10)
        assert service.delete(AID) is True
        end = time.time() + 10
        while time.time() < end and (list(settings.uploads_dir.iterdir()) or AID in service._cancel):
            time.sleep(0.05)
        assert db.get(AID) is None
        assert list(settings.uploads_dir.iterdir()) == [] and list(settings.artifacts_dir.iterdir()) == []
    _with_detector(slow, run)


def test_result_written_after_delete_is_discarded(settings):
    """Worker finishes at the same moment the user deleted: nothing may be left behind."""
    db, service = _setup(settings)
    gate = threading.Event()

    def late(path, model_path=None, cfg=None, progress=None, should_cancel=None):
        gate.wait(10)
        return _fake_success(path)

    def run():
        _enqueue(settings, db, service)
        time.sleep(0.3)
        db.delete(AID)                    # row vanishes without the cancel flag being set
        gate.set()
        time.sleep(1.0)
        assert db.get(AID) is None
        assert list(settings.artifacts_dir.iterdir()) == []
    _with_detector(late, run)


def test_real_pipeline_on_video_without_face(settings, make_video):
    db, service = _setup(settings)
    clip = make_video(seconds=12)
    up = settings.uploads_dir / f"{AID}.mp4"
    up.write_bytes(clip.read_bytes())
    db.create(AID, "noface.mp4", {})
    service.submit(AID, up)
    row = _wait(db)
    assert row["status"] == "completed" and row["verdict"] == "inconclusive"
    assert row["signal_quality"] == "insufficient"


def test_safe_unlink_refuses_files_outside_root(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    outside = tmp_path / "keep.txt"; outside.write_text("x")
    assert safe_unlink(outside, root) is False and outside.exists()


def test_inconclusive_result_uses_transparent_demo_fallback_for_labeled_file(settings):
    db, service = _setup(settings)

    def inconclusive(path, model_path=None, cfg=None, progress=None, should_cancel=None):
        t, rois = synthetic_traces("real")
        result = analyze_traces(t, rois, None, 0.05, "mediapipe")
        result["verdict"] = "inconclusive"
        result["headline"] = "Inconclusive: test signal quality gate."
        result["support_percent"] = None
        result["quality"]["label"] = "insufficient"
        result["video"] = {"fps": 30}
        return result, None

    def run():
        up = settings.uploads_dir / f"{AID}.mp4"
        up.write_bytes(b"x")
        db.create(AID, "real_demo.mp4", {}, "real")
        service.submit(AID, up)
        row = _wait(db)
        assert row["status"] == "completed"
        assert row["verdict"] == "real_like"
        assert row["result"]["detector_verdict"] == "inconclusive"
        assert row["result"]["prediction_source"] == "demo_filename_fallback"
        assert row["result"]["demo_display_percent"] == 50
        assert row["result"]["support_percent"] is None
        assert "not a confidence" in row["result"]["headline"].lower() or "fallback" in row["result"]["headline"].lower()
    _with_detector(inconclusive, run)
