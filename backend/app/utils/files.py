"""Safe filename handling, content sniffing and deletion helpers."""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger("rppg.files")
ID_RE = re.compile(r"^[0-9a-f]{32}$")


def valid_id(analysis_id: str) -> bool:
    return bool(ID_RE.match(analysis_id or ""))


def clean_filename(name: str | None) -> str:
    """Keep only the base name, drop control characters, cap the length."""
    base = (name or "video").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return (base or "video")[:200]




def ground_truth_from_filename(name: str | None) -> str | None:
    """Read an optional evaluation label from a filename prefix, never for prediction.

    Examples: real_vid2.mp4 -> real; FAKE_test.mov -> fake.
    Names such as not_real_video.mp4 remain unlabeled.
    """
    base = clean_filename(name).lower()
    prefix = re.match(r"^(real|fake)(?=$|[_. -])", base)
    return prefix.group(1) if prefix else None

def sniff_video_container(head: bytes) -> str | None:
    """Recognise common video containers by their first bytes (extensions are not trusted)."""
    if len(head) >= 12 and head[4:8] in (b"ftyp", b"moov", b"mdat", b"free", b"wide", b"skip"):
        return "mp4/mov"
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "avi"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm/mkv"
    return None


def safe_unlink(path: Path, root: Path) -> bool:
    """Delete one file only if it lives inside `root`. Never raises."""
    try:
        resolved = path.resolve()
        if root.resolve() not in resolved.parents:
            log.warning("refusing to delete outside storage: %s", path.name)
            return False
        resolved.unlink(missing_ok=True)
        return True
    except OSError as exc:  # e.g. Windows file still open; the worker retries in its cleanup
        log.warning("could not delete %s: %s", path.name, exc)
        return False


def files_for_id(root: Path, analysis_id: str) -> list[Path]:
    """All files in `root` belonging to an analysis id (ids are validated hex, so the glob is safe)."""
    if not valid_id(analysis_id) or not root.is_dir():
        return []
    return [p for p in root.glob(f"{analysis_id}*") if p.is_file()]
