"""SQLite persistence. One short-lived connection per call keeps it thread-safe."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id               TEXT PRIMARY KEY,
    file_name        TEXT NOT NULL,
    ground_truth_label TEXT CHECK (ground_truth_label IN ('real','fake') OR ground_truth_label IS NULL),
    status           TEXT NOT NULL CHECK (status IN ('queued','processing','completed','failed')),
    stage            TEXT,
    progress_done    INTEGER,
    progress_total   INTEGER,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT,
    processing_seconds REAL,
    verdict          TEXT CHECK (verdict IN ('real_like','fake_like','inconclusive') OR verdict IS NULL),
    signal_quality   TEXT,
    video_meta       TEXT,
    result           TEXT,
    error_code       TEXT,
    error_message    TEXT,
    model_version    TEXT,
    has_thumbnail    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses (created_at);
CREATE INDEX IF NOT EXISTS idx_analyses_verdict ON analyses (verdict);
"""

SUMMARY_COLS = ("id, file_name, status, stage, progress_done, progress_total, created_at, finished_at, "
                "processing_seconds, verdict, signal_quality, error_code, error_message, has_thumbnail, ground_truth_label")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            with conn:  # commit or roll back as one transaction
                yield conn
        finally:
            conn.close()

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            # Backward-compatible migration for databases created by earlier ZIP versions.
            columns = {row["name"] for row in c.execute("PRAGMA table_info(analyses)")}
            if "ground_truth_label" not in columns:
                c.execute("ALTER TABLE analyses ADD COLUMN ground_truth_label TEXT")

    # ---- writes -------------------------------------------------------
    def create(self, analysis_id: str, file_name: str, video_meta: dict,
               ground_truth_label: str | None = None) -> None:
        if ground_truth_label not in (None, "real", "fake"):
            raise ValueError("ground_truth_label must be 'real', 'fake', or None")
        with self._conn() as c:
            c.execute("INSERT INTO analyses (id, file_name, ground_truth_label, status, stage, created_at, video_meta) "
                      "VALUES (?,?,?,?,?,?,?)",
                      (analysis_id, file_name, ground_truth_label, "queued", "Waiting in queue",
                       now_iso(), json.dumps(video_meta)))

    def set_processing(self, analysis_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE analyses SET status='processing', stage='Reading frames', started_at=? "
                            "WHERE id=?", (now_iso(), analysis_id))
            return cur.rowcount == 1

    def set_progress(self, analysis_id: str, stage: str, done: Optional[int] = None, total: Optional[int] = None) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE analyses SET stage=?, progress_done=?, progress_total=? WHERE id=?",
                            (stage, done, total, analysis_id))
            return cur.rowcount == 1

    def complete(self, analysis_id: str, result: dict, seconds: float, has_thumbnail: bool) -> bool:
        """Returns False if the row no longer exists (deleted while processing)."""
        with self._conn() as c:
            cur = c.execute(
                "UPDATE analyses SET status='completed', stage='Done', finished_at=?, processing_seconds=?, "
                "verdict=?, signal_quality=?, video_meta=?, result=?, model_version=?, has_thumbnail=?, "
                "progress_done=NULL, progress_total=NULL WHERE id=?",
                (now_iso(), round(seconds, 2), result["verdict"], result["quality"]["label"],
                 json.dumps(result.get("video", {})), json.dumps(result, allow_nan=False),
                 result["pipeline"]["version"], int(has_thumbnail), analysis_id))
            return cur.rowcount == 1

    def fail(self, analysis_id: str, code: str, message: str, seconds: Optional[float] = None) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE analyses SET status='failed', stage='Failed', finished_at=?, "
                            "processing_seconds=?, error_code=?, error_message=? WHERE id=?",
                            (now_iso(), seconds, code, message, analysis_id))
            return cur.rowcount == 1

    def delete(self, analysis_id: str) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM analyses WHERE id=?", (analysis_id,)).rowcount == 1

    def mark_interrupted(self) -> int:
        """After a restart nothing is really running: fail rows left queued/processing."""
        with self._conn() as c:
            return c.execute("UPDATE analyses SET status='failed', stage='Failed', error_code='interrupted', "
                             "error_message='The application stopped before this analysis finished.', finished_at=? "
                             "WHERE status IN ('queued','processing')", (now_iso(),)).rowcount

    # ---- reads --------------------------------------------------------
    def get(self, analysis_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        for key in ("video_meta", "result"):
            d[key] = json.loads(d[key]) if d[key] else None
        d["has_thumbnail"] = bool(d["has_thumbnail"])
        return d

    def active_ids(self) -> set[str]:
        with self._conn() as c:
            return {r["id"] for r in c.execute("SELECT id FROM analyses WHERE status IN ('queued','processing')")}

    def list(self, search: str = "", verdict: str = "all", sort: str = "newest", page: int = 1,
             page_size: int = 10) -> tuple[list[dict], int]:
        where, args = [], []
        if search:
            where.append("file_name LIKE ? ESCAPE '\\'")
            args.append(f"%{_like_escape(search)}%")
        if verdict == "failed":
            where.append("status='failed'")
        elif verdict in ("real_like", "fake_like", "inconclusive"):
            where.append("verdict=?")
            args.append(verdict)
        elif verdict != "all":
            raise ValueError("invalid verdict filter")
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        order = "ASC" if sort == "oldest" else "DESC"
        with self._conn() as c:
            total = c.execute(f"SELECT COUNT(*) FROM analyses {clause}", args).fetchone()[0]
            rows = c.execute(f"SELECT {SUMMARY_COLS} FROM analyses {clause} ORDER BY created_at {order}, id {order} "
                             "LIMIT ? OFFSET ?", [*args, page_size, (page - 1) * page_size]).fetchall()
        return [dict(r) | {"has_thumbnail": bool(r["has_thumbnail"])} for r in rows], total

    def stats(self) -> dict[str, int]:
        with self._conn() as c:
            r = c.execute("SELECT "
                          "SUM(status='completed') AS analyzed, "
                          "SUM(verdict='real_like') AS real_like, SUM(verdict='fake_like') AS fake_like, "
                          "SUM(verdict='inconclusive') AS inconclusive, SUM(status='failed') AS failed, "
                          "SUM(status IN ('queued','processing')) AS in_progress FROM analyses").fetchone()
        return {k: int(r[k] or 0) for k in r.keys()}
