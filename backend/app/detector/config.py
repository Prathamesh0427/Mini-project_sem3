"""Detector parameters. Defaults keep the original notebook's values where they were
reasonable; every threshold is UNCALIBRATED (no labelled validation data exists yet)."""
from __future__ import annotations

from dataclasses import asdict, dataclass

MODEL_VERSION = "rppg-heuristic-2.0"
METHOD_NAME = "Training-free rPPG pulse-consistency heuristic (green channel, 3 facial ROIs)"


@dataclass(frozen=True)
class DetectorConfig:
    # signal band / heart-rate search range (original notebook values)
    f_low: float = 0.7
    f_high: float = 4.0
    filter_order: int = 3
    hr_min_bpm: float = 42.0
    hr_max_bpm: float = 180.0
    target_fs: float = 30.0        # signals are resampled to min(native fps, this)
    # input validation
    min_duration_s: float = 5.0
    max_duration_s: float = 120.0
    min_fps: float = 15.0
    target_width: int = 480        # frames are resized for ROI measurement
    # quality gate (insufficient evidence => INCONCLUSIVE)
    min_face_coverage: float = 0.70
    min_snr_db: float = 0.0
    max_motion_index: float = 0.30
    max_gap_s: float = 1.0
    # consistency checks (only evaluated when the gate passes)
    thresh_roi_corr: float = 0.60  # original notebook value
    thresh_plv: float = 0.60       # replaces the original phase-coherence formula
    max_hr_spread_bpm: float = 12.0
    # warnings only
    motion_warn: float = 0.15
    ema_alpha: float = 0.4         # ROI box smoothing
    display_window_s: float = 20.0  # seconds of signal stored for charts

    def to_dict(self) -> dict:
        return asdict(self)
