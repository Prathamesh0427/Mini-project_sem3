"""rPPG signal processing, feature extraction and the transparent decision rules.

Everything here works on plain numpy arrays so it can be unit-tested without any video."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy.signal import butter, detrend, hilbert, sosfiltfilt, welch

from .config import METHOD_NAME, MODEL_VERSION, DetectorConfig
from .video import ROI_NAMES, VideoError

LIMITATIONS = [
    "Thresholds are heuristic and have NOT been calibrated or validated on labelled real/fake videos.",
    "The score is a count of passed consistency checks, not a calibrated probability.",
    "A missing or weak pulse does not prove a video is fake: compression, lighting, make-up, motion and "
    "low resolution all remove real pulses.",
    "A present, consistent pulse does not prove a video is real: some generators preserve the source video's signal.",
    "Results are a research estimate, not a forensic judgement.",
]


def _sanitize(o):
    if isinstance(o, dict):
        return {k: _sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sanitize(v) for v in o]
    if isinstance(o, np.ndarray):
        return _sanitize(o.tolist())
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return round(v, 5) if math.isfinite(v) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def _fill(t: np.ndarray, x: np.ndarray) -> np.ndarray | None:
    x = np.asarray(x, float).copy()
    bad = ~np.isfinite(x)
    if bad.all():
        return None
    if bad.any():
        x[bad] = np.interp(t[bad], t[~bad], x[~bad])
    return x


def _longest_run_s(valid: np.ndarray, dt: float) -> float:
    longest = run = 0
    for v in valid:
        run = 0 if v else run + 1
        longest = max(longest, run)
    return longest * dt


def _condition(t: np.ndarray, x: np.ndarray, fs: float, sos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Resample to a uniform grid, normalise (AC/DC), detrend and band-pass."""
    tu = np.arange(t[0], t[-1], 1.0 / fs)
    xu = np.interp(tu, t, x)
    dc = float(np.mean(xu))
    xu = detrend(xu, type="linear")
    if abs(dc) > 1e-6:
        xu = xu / dc
    return tu, sosfiltfilt(sos, xu)


def _psd(x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    nperseg = int(min(len(x), 10 * fs))
    nfft = 1 << int(math.ceil(math.log2(nperseg * 4)))
    return welch(x, fs=fs, nperseg=nperseg, noverlap=nperseg // 2, nfft=nfft)


def _snr_db(f: np.ndarray, p: np.ndarray, f0: float, cfg: DetectorConfig, bw: float = 0.15) -> float:
    """De Haan-style SNR: power around f0 and 2*f0 vs the rest of the cardiac band."""
    band = (f >= cfg.f_low) & (f <= cfg.f_high)
    sig = band & ((np.abs(f - f0) <= bw) | (np.abs(f - 2 * f0) <= bw))
    return float(10 * np.log10((p[sig].sum() + 1e-12) / (p[band & ~sig].sum() + 1e-12)))


def _narrow(x: np.ndarray, fs: float, f0: float, half: float = 0.3) -> np.ndarray:
    lo, hi = max(0.5, f0 - half), min(f0 + half, 0.45 * fs)
    return sosfiltfilt(butter(2, [lo, hi], btype="band", fs=fs, output="sos"), x)


def _zs(x: np.ndarray) -> np.ndarray:
    s = np.std(x)
    return (x - np.mean(x)) / s if s > 1e-12 else np.zeros_like(x)


def _verdict_text(verdict: str) -> str:
    return {
        "real_like": "Real-like: a pulse-band signal is present and most consistency checks support a real-like pattern.",
        "fake_like": "Fake-like: a pulse-band signal is present and multiple consistency checks fail under this heuristic.",
        "inconclusive": "Inconclusive: the video does not provide enough reliable evidence for a physiological judgement.",
    }[verdict]


def analyze_traces(t: Sequence[float], rois: dict[str, np.ndarray], background: np.ndarray | None,
                   motion_index: float, face_backend: str, extra_warnings: Sequence[str] = (),
                   cfg: DetectorConfig | None = None) -> dict:
    """Turn per-frame ROI traces (NaN = face not found) into a full, JSON-safe analysis result."""
    cfg = cfg or DetectorConfig()
    t = np.asarray(t, float)
    n = len(t)
    warnings = list(extra_warnings)
    if n < 3 or not np.all(np.diff(t) > 0):
        raise VideoError("bad_timestamps", "Frame timestamps are missing or not increasing.")
    dt = float(np.median(np.diff(t)))
    fps_est = 1.0 / dt
    fs = min(cfg.target_fs, fps_est)
    if fs < cfg.min_fps:
        raise VideoError("low_fps", f"Effective frame rate {fps_est:.1f} fps is below {cfg.min_fps:.0f} fps.")
    if cfg.f_high >= fs / 2:
        raise VideoError("bad_fps", f"Sampling rate {fs:.1f} Hz is too low for a {cfg.f_high} Hz upper band edge.")

    stack = np.vstack([np.asarray(rois[k], float) for k in ROI_NAMES])
    valid = np.isfinite(stack).all(axis=0)
    coverage = float(valid.mean())
    duration = float(t[-1] - t[0])
    gap = _longest_run_s(valid, dt)

    quality = {"face_coverage": coverage, "duration_s": duration, "native_fps_estimate": fps_est,
               "analysis_fs_hz": fs, "longest_gap_s": gap, "motion_index": motion_index,
               "fused_snr_db": None, "roi_snr_db": {}, "usable_rois": [], "label": "insufficient"}
    gate: list[str] = []
    if duration < cfg.min_duration_s:
        gate.append(f"Analysed segment is {duration:.1f}s; at least {cfg.min_duration_s:.0f}s is required.")
    if coverage < cfg.min_face_coverage:
        gate.append(f"Face (and all three regions) visible in only {coverage * 100:.0f}% of frames; "
                    f"at least {cfg.min_face_coverage * 100:.0f}% is required.")
    if np.isfinite(motion_index) and motion_index > cfg.max_motion_index:
        gate.append(f"Head movement is too large (motion index {motion_index:.2f} > {cfg.max_motion_index}).")

    base = {"pipeline": {"method": METHOD_NAME, "version": MODEL_VERSION, "face_backend": face_backend,
                         "config": cfg.to_dict()},
            "limitations": LIMITATIONS}
    if face_backend == "haar":
        warnings.append("MediaPipe model not found; the less accurate OpenCV Haar face detector was used. "
                        "Run scripts/download_model.py for better face tracking.")

    # too little usable data to compute any signal at all
    if valid.sum() < max(0.25 * n, 3 * fs):
        gate.append("The face was found in too few frames to extract any pulse signal.")
        return _sanitize({**base, "verdict": "inconclusive", "headline": _verdict_text("inconclusive"),
                          "consistency_score": None, "support_percent": None, "quality": quality, "features": {}, "checks": [],
                          "reasons": [{"kind": "measured", "text": g} for g in gate],
                          "warnings": warnings, "signals": None, "spectrum": None})

    if gap > cfg.max_gap_s:
        warnings.append(f"Face was lost for up to {gap:.1f}s; gaps were interpolated, which weakens the signal.")
    if fps_est < 20:
        warnings.append(f"Low frame rate ({fps_est:.1f} fps) reduces pulse-signal reliability.")
    if np.isfinite(motion_index) and motion_index > cfg.motion_warn:
        warnings.append(f"Noticeable head movement (motion index {motion_index:.2f}); motion can mimic or hide a pulse.")

    sos = butter(cfg.filter_order, [cfg.f_low, cfg.f_high], btype="band", fs=fs, output="sos")
    sig, tu = {}, None
    for k in ROI_NAMES:
        x = _fill(t, rois[k])
        tu, sig[k] = _condition(t, x, fs, sos)
    fused = np.mean([_zs(sig[k]) for k in ROI_NAMES], axis=0)

    f, p_fused = _psd(fused, fs)
    search = (f >= max(cfg.f_low, cfg.hr_min_bpm / 60)) & (f <= min(cfg.f_high, cfg.hr_max_bpm / 60))
    f0 = float(f[search][np.argmax(p_fused[search])])
    fused_snr = _snr_db(f, p_fused, f0, cfg)
    psd_roi, peak_roi, snr_roi = {}, {}, {}
    for k in ROI_NAMES:
        _, psd_roi[k] = _psd(sig[k], fs)
        peak_roi[k] = float(f[search][np.argmax(psd_roi[k][search])])
        snr_roi[k] = _snr_db(f, psd_roi[k], peak_roi[k], cfg)
    usable = [k for k in ROI_NAMES if snr_roi[k] >= cfg.min_snr_db]
    hr_spread = float((max(peak_roi.values()) - min(peak_roi.values())) * 60)

    # narrow-band consistency around the detected pulse frequency (edges trimmed)
    trim = int(fs)
    nb = {k: _narrow(sig[k], fs, f0)[trim:-trim] for k in ROI_NAMES}
    pairs = [("forehead", "left_cheek"), ("forehead", "right_cheek"), ("left_cheek", "right_cheek")]
    roi_corr = float(np.mean([np.corrcoef(nb[a], nb[b])[0, 1] for a, b in pairs]))
    ph = {k: np.angle(hilbert(nb[k])) for k in ROI_NAMES}
    plv = float(np.mean([abs(np.mean(np.exp(1j * (ph[a] - ph[b])))) for a, b in pairs]))
    rms = np.array([np.sqrt(np.mean(nb[k] ** 2)) for k in ROI_NAMES])
    amp_cv = float(np.std(rms) / (np.mean(rms) + 1e-12))
    h_mask = np.abs(f - 2 * f0) < 0.2
    harmonic = float(p_fused[h_mask].max() / (p_fused[search].max() + 1e-12)) if h_mask.any() else float("nan")

    # background (whole frame) at the pulse frequency -> possible lighting/camera artefact
    if background is not None and len(background) == n:
        _, bg = _condition(t, np.asarray(background, float), fs, sos)
        _, p_bg = _psd(bg, fs)
        bg_peak = float(f[search][np.argmax(p_bg[search])])
        if abs(bg_peak - f0) <= 0.1 and _snr_db(f, p_bg, bg_peak, cfg) >= cfg.min_snr_db:
            warnings.append("The whole-frame brightness also oscillates at the detected pulse frequency "
                            "(possible lighting flicker or camera artefact).")

    if fused_snr < cfg.min_snr_db:
        gate.append(f"No clear periodic component in the cardiac band (SNR {fused_snr:.1f} dB < {cfg.min_snr_db} dB). "
                    "This can be caused by compression, lighting or motion, so it is not evidence of a fake.")
    quality.update(fused_snr_db=fused_snr, roi_snr_db=snr_roi, usable_rois=usable,
                   label="insufficient" if gate else ("good" if fused_snr >= 6 else "marginal"))

    features = {"hr_bpm": f0 * 60, "pulse_freq_hz": f0, "fused_snr_db": fused_snr,
                "roi_peak_bpm": {k: v * 60 for k, v in peak_roi.items()}, "hr_spread_bpm": hr_spread,
                "roi_correlation": roi_corr, "phase_locking_value": plv, "amplitude_cv": amp_cv,
                "harmonic_ratio": harmonic}

    checks, reasons, score = [], [], None
    if gate:
        verdict = "inconclusive"
        reasons += [{"kind": "measured", "text": g} for g in gate]
    else:
        checks = [
            {"name": "roi_correlation", "label": "Cross-region correlation (narrow band)", "value": roi_corr,
             "threshold": cfg.thresh_roi_corr, "comparison": ">=", "passed": roi_corr >= cfg.thresh_roi_corr},
            {"name": "phase_locking_value", "label": "Cross-region phase locking", "value": plv,
             "threshold": cfg.thresh_plv, "comparison": ">=", "passed": plv >= cfg.thresh_plv},
            {"name": "hr_spread_bpm", "label": "Heart-rate spread between regions (BPM)", "value": hr_spread,
             "threshold": cfg.max_hr_spread_bpm, "comparison": "<=", "passed": hr_spread <= cfg.max_hr_spread_bpm},
        ]
        failed = [c for c in checks if not c["passed"]]
        score = (len(checks) - len(failed)) / len(checks)
        # With adequate signal quality, classify the direction supported by the majority
        # of the three checks. This removes the old "exactly one failed => inconclusive"
        # dead zone without pretending the heuristic is a trained/calibrated classifier.
        verdict = "real_like" if len(failed) <= 1 else "fake_like"
        reasons.append({"kind": "measured", "text": f"A pulse-band peak was found at {f0 * 60:.0f} BPM "
                                                    f"(SNR {fused_snr:.1f} dB)."})
        for c in checks:
            word = "passed" if c["passed"] else "failed"
            reasons.append({"kind": "heuristic", "text": f"{c['label']} {word}: measured {c['value']:.3f} "
                                                         f"(threshold {c['comparison']} {c['threshold']}, uncalibrated)."})
        if len(failed) == 1:
            reasons.append({"kind": "heuristic", "text": "Two of three consistency checks support a real-like pattern; one check did not pass. This is a heuristic majority decision, not a validated probability."})
        elif len(failed) == 2:
            reasons.append({"kind": "heuristic", "text": "Two of three consistency checks do not pass, supporting a fake-like pattern under this heuristic. This is not proof of manipulation."})
    reasons.append({"kind": "measured", "text": "Regions with a usable signal: " +
                    (", ".join(k.replace("_", " ") for k in usable) or "none") + "."})

    w = int(cfg.display_window_s * fs)
    norm = lambda p: p / (p.max() + 1e-12)
    show = (f >= 0.4) & (f <= 4.6)
    signals = {"fs": fs, "window_s": cfg.display_window_s, "t": (tu - tu[0])[:w],
               "fused": fused[:w], **{k: sig[k][:w] for k in ROI_NAMES}}
    spectrum = {"freqs": f[show], "fused": norm(p_fused)[show], **{k: norm(psd_roi[k])[show] for k in ROI_NAMES},
                "peak_hz": f0}
    # Transparent support score, deliberately NOT named probability/confidence:
    # it is the proportion of the three checks supporting the selected direction.
    # The UI can always show a percentage without claiming statistical calibration.
    if verdict == "real_like":
        support_percent = round(100 * sum(bool(c["passed"]) for c in checks) / len(checks))
    elif verdict == "fake_like":
        support_percent = round(100 * sum(not bool(c["passed"]) for c in checks) / len(checks))
    else:
        support_percent = None
    return _sanitize({**base, "verdict": verdict, "headline": _verdict_text(verdict), "consistency_score": score,
                      "support_percent": support_percent,
                      "quality": quality, "features": features, "checks": checks, "reasons": reasons,
                      "warnings": warnings, "signals": signals, "spectrum": spectrum})
