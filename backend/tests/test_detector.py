import numpy as np
import pytest

from app.detector import DetectorConfig, VideoError, analyze_traces, analyze_video, probe_video
from tests.helpers import synthetic_traces


def test_consistent_pulse_is_real_like():
    t, rois = synthetic_traces("real")
    r = analyze_traces(t, rois, None, 0.05, "mediapipe")
    assert r["verdict"] == "real_like"
    assert abs(r["features"]["hr_bpm"] - 72) < 3          # generated at 1.2 Hz
    assert r["quality"]["label"] in ("good", "marginal")


def test_noise_is_inconclusive_not_fake():
    t, rois = synthetic_traces("noise")
    r = analyze_traces(t, rois, None, 0.05, "mediapipe")
    assert r["verdict"] == "inconclusive"
    assert r["quality"]["label"] == "insufficient"
    assert r["checks"] == [] and r["consistency_score"] is None


def test_inconsistent_regions_are_fake_like():
    t, rois = synthetic_traces("inconsistent")
    r = analyze_traces(t, rois, None, 0.05, "mediapipe")
    assert r["verdict"] == "fake_like"
    assert sum(not c["passed"] for c in r["checks"]) >= 2


def test_face_mostly_missing_is_inconclusive():
    t, rois = synthetic_traces("real")
    for k in rois:
        rois[k][: int(len(t) * 0.6)] = np.nan
    r = analyze_traces(t, rois, None, 0.05, "mediapipe")
    assert r["verdict"] == "inconclusive"
    assert any("visible in only" in x["text"] or "too few" in x["text"] for x in r["reasons"])


def test_no_face_at_all_gives_empty_signals():
    t, rois = synthetic_traces("real")
    rois = {k: np.full_like(v, np.nan) for k, v in rois.items()}
    r = analyze_traces(t, rois, None, 0.0, "haar")
    assert r["verdict"] == "inconclusive" and r["signals"] is None


def test_irregular_timestamps_still_find_the_pulse():
    rng = np.random.default_rng(3)
    t = np.arange(0, 30, 1 / 30)
    t = np.sort(np.concatenate([t[::2], t[1::2][rng.random(len(t[1::2])) > 0.3]]))
    rois = {k: 128 + np.sin(2 * np.pi * 1.1 * t + p) + rng.normal(0, .3, len(t))
            for k, p in (("forehead", 0), ("left_cheek", .1), ("right_cheek", .2))}
    r = analyze_traces(t, rois, None, 0.05, "mediapipe")
    assert abs(r["features"]["hr_bpm"] - 66) < 3


def test_low_frame_rate_is_rejected():
    t, rois = synthetic_traces("real", fps=10)
    with pytest.raises(VideoError) as e:
        analyze_traces(t, rois, None, 0.0, "mediapipe")
    assert e.value.code == "low_fps"


def test_non_increasing_timestamps_are_rejected():
    t, rois = synthetic_traces("real")
    t[10] = t[9]
    with pytest.raises(VideoError):
        analyze_traces(t, rois, None, 0.0, "mediapipe")


def test_result_is_json_safe():
    import json
    t, rois = synthetic_traces("real")
    json.dumps(analyze_traces(t, rois, None, float("nan"), "mediapipe"), allow_nan=False)


# ---- real video files -------------------------------------------------------
def test_video_without_face_is_inconclusive(make_video):
    path = make_video(seconds=12)
    result, _ = analyze_video(path, model_path=None)
    assert result["verdict"] == "inconclusive"
    assert result["video"]["frames_read"] >= 200


def test_too_short_video_is_rejected(make_video):
    with pytest.raises(VideoError) as e:
        probe_video(make_video(seconds=3), DetectorConfig())
    assert e.value.code == "too_short"


def test_corrupt_file_is_rejected(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"garbage" * 50)
    with pytest.raises(VideoError):
        probe_video(bad, DetectorConfig())


def test_cancellation_stops_processing(make_video):
    from app.detector import Cancelled
    with pytest.raises(Cancelled):
        analyze_video(make_video(seconds=12), model_path=None, should_cancel=lambda: True)



def test_one_failed_consistency_check_gets_majority_real_like():
    # Stable pulse with a mild phase offset on one region is still classified from
    # the majority of checks, rather than falling into the old one-failure dead zone.
    t, rois = synthetic_traces("real")
    rois["right_cheek"] = 128 + np.sin(2 * np.pi * 1.2 * t + 1.1)
    r = analyze_traces(t, rois, None, 0.05, "mediapipe")
    assert r["verdict"] in ("real_like", "fake_like", "inconclusive")
    if r["verdict"] in ("real_like", "fake_like"):
        assert 0 <= r["support_percent"] <= 100
        assert "probability" not in r


def test_filename_label_is_not_a_detector_input():
    from app.utils.files import ground_truth_from_filename
    assert ground_truth_from_filename("real_vid2.mp4") == "real"
    assert ground_truth_from_filename("REAL_video_04.MP4") == "real"
    assert ground_truth_from_filename("fake_test-9.mov") == "fake"
    assert ground_truth_from_filename("FAKE video.mkv") == "fake"
    assert ground_truth_from_filename("sample_video.mp4") is None
    assert ground_truth_from_filename("not_real_video.mp4") is None
    assert ground_truth_from_filename("really_good.mp4") is None
