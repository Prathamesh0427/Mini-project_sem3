"""HTTP-level tests. Need FastAPI + httpx (pip install -r requirements-dev.txt)."""
import time

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

import app.services.analysis_service as svc  # noqa: E402
from app.detector import analyze_traces  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.helpers import make_settings, make_video, synthetic_traces  # noqa: E402


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


@pytest.fixture
def video_bytes(tmp_path):
    return make_video(tmp_path / "v.mp4", seconds=12).read_bytes()


def _wait(client, aid, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        row = client.get(f"/api/analyses/{aid}").json()
        if row["status"] in ("completed", "failed"):
            return row
        time.sleep(0.1)
    raise AssertionError("timed out")


def _post(client, data, name="clip.mp4"):
    return client.post("/api/analyses", files={"file": (name, data, "video/mp4")})


def test_valid_upload_runs_real_pipeline_and_is_inconclusive_without_face(client, video_bytes):
    r = _post(client, video_bytes)
    assert r.status_code == 202
    row = _wait(client, r.json()["id"])
    assert row["status"] == "completed" and row["verdict"] == "inconclusive"
    assert row["video_meta"]["duration_s"] > 10 and row["processing_seconds"] is not None


def test_empty_file_rejected(client):
    r = _post(client, b"")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "empty_file"


def test_wrong_extension_rejected(client, video_bytes):
    assert _post(client, video_bytes, "clip.txt").status_code == 415


def test_fake_video_extension_rejected_by_content_sniffing(client):
    r = _post(client, b"this is just text, not a video" * 20, "clip.mp4")
    assert r.status_code == 415 and r.json()["detail"]["code"] == "not_a_video"


def test_corrupt_video_rejected(client):
    r = _post(client, b"\x00\x00\x00\x18ftypmp42" + b"junk" * 100)
    assert r.status_code == 422


def test_too_short_video_rejected(client, tmp_path):
    short = make_video(tmp_path / "s.mp4", seconds=3).read_bytes()
    r = _post(client, short)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_short"


def test_oversized_upload_rejected_and_nothing_left_behind(client, tmp_path):
    big = b"\x00\x00\x00\x18ftypmp42" + b"0" * (6 * 1024 * 1024)       # limit is 5 MB in tests
    assert _post(client, big).status_code == 413
    assert list((tmp_path / "storage" / "uploads").iterdir()) == []


def test_successful_analysis_history_download_and_delete(client, video_bytes, tmp_path):
    original = svc.analyze_video

    def fake(path, model_path=None, cfg=None, progress=None, should_cancel=None):
        t, rois = synthetic_traces("real")
        res = analyze_traces(t, rois, None, 0.05, "mediapipe")
        res["video"] = {"fps": 30}
        return res, np.full((60, 80, 3), 100, np.uint8)

    svc.analyze_video = fake
    try:
        aid = _post(client, video_bytes, "my_clip.mp4").json()["id"]
        row = _wait(client, aid)
    finally:
        svc.analyze_video = original
    assert row["verdict"] == "real_like"
    assert client.get(f"/api/analyses/{aid}/thumbnail").status_code == 200
    assert client.get(f"/api/analyses/{aid}/download").status_code == 200
    assert client.get("/api/stats").json()["real_like"] == 1
    listing = client.get("/api/analyses", params={"search": "my_cl", "verdict": "real_like"}).json()
    assert listing["total"] == 1

    assert client.delete(f"/api/analyses/{aid}").status_code == 200
    assert client.get(f"/api/analyses/{aid}").status_code == 404           # report URL no longer works
    assert client.get(f"/api/analyses/{aid}/thumbnail").status_code == 404
    assert client.delete(f"/api/analyses/{aid}").status_code == 404
    assert client.get("/api/stats").json()["analyzed"] == 0                 # dashboard updates
    assert list((tmp_path / "storage" / "artifacts").iterdir()) == []
    assert list((tmp_path / "storage" / "uploads").iterdir()) == []


def test_history_survives_application_restart(tmp_path, video_bytes):
    s = make_settings(tmp_path)
    with TestClient(create_app(s)) as c1:
        aid = _post(c1, video_bytes).json()["id"]
        _wait(c1, aid)
    with TestClient(create_app(s)) as c2:                                    # "restart"
        assert c2.get(f"/api/analyses/{aid}").json()["status"] == "completed"
        assert c2.get("/api/analyses").json()["total"] == 1


def test_bad_ids_and_filters_are_rejected_safely(client):
    for bad in ("..", "not-an-id", "A" * 32, "../../etc/passwd"):
        assert client.get(f"/api/analyses/{bad}").status_code == 404
        assert client.delete(f"/api/analyses/{bad}").status_code in (404, 405)
    assert client.get("/api/analyses", params={"verdict": "bogus"}).status_code == 400
    assert client.get("/api/analyses", params={"page": 0}).status_code == 422


def test_empty_history_listing(client):
    r = client.get("/api/analyses").json()
    assert r["items"] == [] and r["total"] == 0 and r["pages"] == 1
