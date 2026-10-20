"""Evaluate the detector on YOUR labelled videos (nothing is invented here).

Folder layout:   dataset/real/*.mp4   dataset/fake/*.mp4
Usage:           python scripts\\evaluate.py C:\\path\\to\\dataset

Inconclusive results are reported separately (coverage), and metrics are computed only on
videos that received a real-like / fake-like verdict. 'fake' is the positive class.
IMPORTANT: if you tune thresholds, tune on one split and report on a different held-out split,
and keep videos of the same person/source in the same split to avoid leakage."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402
from app.detector import VideoError, analyze_video  # noqa: E402

EXT = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}


def main(root: Path) -> None:
    model = get_settings().model_path
    rows = []
    for label in ("real", "fake"):
        for p in sorted((root / label).glob("*")):
            if p.suffix.lower() not in EXT:
                continue
            try:
                res, _ = analyze_video(p, model)
                verdict, snr = res["verdict"], res["quality"]["fused_snr_db"]
            except VideoError as e:
                verdict, snr = f"error:{e.code}", None
            rows.append((p.name, label, verdict, snr))
            print(f"{label:5s} {verdict:13s} {p.name}")
    out = root / "evaluation_results.csv"
    with open(out, "w", newline="") as f:
        csv.writer(f).writerows([("file", "label", "verdict", "snr_db"), *rows])
    decided = [r for r in rows if r[2] in ("real_like", "fake_like")]
    n_real = sum(r[1] == "real" for r in rows); n_fake = sum(r[1] == "fake" for r in rows)
    print(f"\nVideos: {len(rows)} (real {n_real}, fake {n_fake}); decided {len(decided)}; "
          f"inconclusive/error {len(rows) - len(decided)}  -> coverage {len(decided) / max(len(rows), 1):.0%}")
    tp = sum(r[1] == "fake" and r[2] == "fake_like" for r in decided)
    fp = sum(r[1] == "real" and r[2] == "fake_like" for r in decided)
    tn = sum(r[1] == "real" and r[2] == "real_like" for r in decided)
    fn = sum(r[1] == "fake" and r[2] == "real_like" for r in decided)
    print(f"Confusion matrix (decided only)   pred real | pred fake\n  actual real: {tn:8d} | {fp:8d}\n  actual fake: {fn:8d} | {tp:8d}")
    if decided:
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if tp else float("nan")
        print(f"Accuracy {(tp + tn) / len(decided):.3f}  Precision {prec:.3f}  Recall {rec:.3f}  F1 {f1:.3f}")
    print(f"Per-video results saved to {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
