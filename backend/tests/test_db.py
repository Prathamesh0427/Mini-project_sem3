from app.database import Database
from tests.helpers import synthetic_traces
from app.detector import analyze_traces

ID1, ID2 = "a" * 32, "b" * 32


def _result(kind="real"):
    t, rois = synthetic_traces(kind)
    r = analyze_traces(t, rois, None, 0.05, "mediapipe")
    r["video"] = {"fps": 30}
    return r


def test_save_and_retrieve(tmp_path):
    db = Database(tmp_path / "t.db"); db.init()
    db.create(ID1, "clip.mp4", {"fps": 30})
    assert db.get(ID1)["status"] == "queued"
    assert db.set_processing(ID1)
    assert db.complete(ID1, _result(), 1.5, True)
    row = db.get(ID1)
    assert row["status"] == "completed" and row["verdict"] == "real_like"
    assert row["result"]["signals"]["t"]            # chart data stored, no video needed
    assert row["processing_seconds"] == 1.5 and row["has_thumbnail"] is True


def test_history_persists_after_reopen(tmp_path):
    path = tmp_path / "t.db"
    db = Database(path); db.init(); db.create(ID1, "clip.mp4", {})
    db2 = Database(path); db2.init()
    assert db2.get(ID1)["file_name"] == "clip.mp4"


def test_delete_removes_row(tmp_path):
    db = Database(tmp_path / "t.db"); db.init(); db.create(ID1, "a.mp4", {})
    assert db.delete(ID1) is True
    assert db.get(ID1) is None and db.delete(ID1) is False
    assert not db.complete(ID1, _result(), 1.0, False)   # late worker result for a deleted row is dropped


def test_list_search_filter_sort_pagination(tmp_path):
    db = Database(tmp_path / "t.db"); db.init()
    for i in range(25):
        aid = f"{i:032x}"
        db.create(aid, f"video_{i}.mp4", {})
        db.complete(aid, _result("real" if i % 2 else "noise"), 1.0, False)
    items, total = db.list(page=1, page_size=10)
    assert total == 25 and len(items) == 10
    assert db.list(verdict="real_like")[1] == 12
    assert db.list(verdict="inconclusive")[1] == 13
    assert db.list(search="video_2")[1] == 6               # video_2, video_20..24
    assert db.list(search="_")[1] == 25                    # underscore is literal, not a wildcard match-all bug
    assert db.list(search="%")[1] == 0
    assert db.list(sort="oldest", page_size=1)[0][0]["file_name"] == "video_0.mp4"
    assert len(db.list(page=3, page_size=10)[0]) == 5


def test_stats_and_interrupted(tmp_path):
    db = Database(tmp_path / "t.db"); db.init()
    db.create(ID1, "a.mp4", {}); db.create(ID2, "b.mp4", {})
    db.complete(ID1, _result(), 1, False)
    assert db.stats()["in_progress"] == 1
    assert db.mark_interrupted() == 1
    s = db.stats()
    assert s["failed"] == 1 and s["analyzed"] == 1 and s["real_like"] == 1



def test_filename_ground_truth_label_is_saved_separately(tmp_path):
    db = Database(tmp_path / "labels.db"); db.init()
    db.create(ID1, "real_clip.mp4", {}, ground_truth_label="real")
    row = db.get(ID1)
    assert row["ground_truth_label"] == "real"
    assert row["verdict"] is None  # filename label is not the detector prediction
    items, total = db.list()
    assert total == 1 and items[0]["ground_truth_label"] == "real"
