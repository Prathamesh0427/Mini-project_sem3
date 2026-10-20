import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { REGION, VERDICT, fmtDate, fmtSecs, num } from "../format.js";
import Badge from "../components/Badge.jsx";
import LineChart from "../components/Charts.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";

const COLORS = { forehead: "#c2410c", left_cheek: "#0f766e", right_cheek: "#6d28d9", fused: "#1f2937" };

function qSafeCoverage(result) {
  return result?.quality?.face_coverage ?? 0;
}

export default function Report() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [a, setA] = useState(null);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let stop = false, timer;
    const load = async () => {
      try {
        const d = await api.get(id);
        if (stop) return;
        setA(d); setError("");
        if (d.status === "queued" || d.status === "processing") timer = setTimeout(load, 1000);
      } catch (e) { if (!stop) setError(e.status === 404 ? "This analysis does not exist (it may have been deleted)." : e.message); }
    };
    load();
    return () => { stop = true; clearTimeout(timer); };
  }, [id]);

  async function remove() {
    setDeleting(true);
    try { await api.remove(id); navigate("/history"); }
    catch (e) { if (e.status === 404) navigate("/history"); else { setError(e.message); setDeleting(false); setConfirm(false); } }
  }

  if (error && !a) return <div className="card"><div className="alert error">{error}</div><Link className="btn ghost" to="/history">Back to history</Link></div>;
  if (!a) return <div className="card"><p className="muted">Loading…</p></div>;

  const actions = (
    <div className="row actions-bar">
      <Link className="btn primary" to="/upload">Analyze another video</Link>
      <Link className="btn ghost" to="/">Dashboard</Link>
      <Link className="btn ghost" to="/history">History</Link>
      {a.status === "completed" && <a className="btn ghost" href={`/api/analyses/${a.id}/download`}>Download report (JSON)</a>}
      <button className="btn danger-ghost" onClick={() => setConfirm(true)}>Delete analysis</button>
    </div>
  );
  const dialog = confirm && (
    <ConfirmDialog title="Delete this analysis?" busy={deleting} onConfirm={remove} onCancel={() => setConfirm(false)}>
      “{a.file_name}” and its saved report will be permanently removed. This cannot be undone.
    </ConfirmDialog>
  );

  if (a.status === "queued" || a.status === "processing") {
    const pct = a.progress_total ? Math.min(100, Math.round((a.progress_done / a.progress_total) * 100)) : null;
    return (
      <div className="card narrow">
        <h1>Analyzing “{a.file_name}”</h1>
        <p><b>{a.stage}</b>{pct !== null && ` — frame ${a.progress_done} of ${a.progress_total}`}</p>
        {pct !== null ? <div className="progress"><div style={{ width: `${pct}%` }} /></div>
          : <div className="progress indeterminate"><div /></div>}
        <p className="muted">Progress is only shown where it can be measured. Analysis runs on this computer’s CPU; you can leave this page and find the result in History.</p>
        {actions}{dialog}
      </div>
    );
  }
  if (a.status === "failed") {
    return (
      <div className="card narrow">
        <h1>Analysis failed</h1>
        <div className="alert error">{a.error_message}</div>
        <p className="muted">This is a processing failure, not a real/fake result. File: {a.file_name}</p>
        {actions}{dialog}
      </div>
    );
  }

  const r = a.result, v = VERDICT[a.verdict], q = r.quality, f = r.features, s = r.signals, sp = r.spectrum;
  const vid = { ...(a.video_meta || {}), ...(r.video || {}) };
  const cfg = r.pipeline.config;
  const isDemoFallback = r.prediction_source === "demo_filename_fallback";
  const supportPercent = r.support_percent ?? (
    a.verdict === "real_like" && r.checks?.length
      ? Math.round(100 * r.checks.filter((c) => c.passed).length / r.checks.length)
      : a.verdict === "fake_like" && r.checks?.length
        ? Math.round(100 * r.checks.filter((c) => !c.passed).length / r.checks.length)
        : null
  );
  const roiSeries = s && ["forehead", "left_cheek", "right_cheek"].map((k) => ({ name: REGION[k], color: COLORS[k], x: s.t, y: s[k] }));
  const specSeries = sp && [{ name: "Combined", color: COLORS.fused, x: sp.freqs, y: sp.fused },
    ...["forehead", "left_cheek", "right_cheek"].map((k) => ({ name: REGION[k], color: COLORS[k], x: sp.freqs, y: sp[k] }))];

  return (
    <div className="stack">
      <section className={`card verdict ${v.cls}`}>
        <div className="row between"><h1>{a.file_name}</h1><Badge analysis={a} /></div>
        <p className="headline">{r.headline}</p>
        <div className="support-score">
          {isDemoFallback ? (
            <>
              <p><b>Demo display indicator: {r.demo_display_percent ?? 50}%</b></p>
              <div className="progress" role="img" aria-label="Demo display indicator, not confidence">
                <div style={{ width: `${r.demo_display_percent ?? 50}%` }} />
              </div>
              <p className="muted">This is a neutral demo display value, not a confidence score. The rPPG detector could not make a reliable prediction; the displayed Real/Fake category comes from the demo filename fallback.</p>
              <p><b>Underlying rPPG result:</b> Inconclusive</p>
            </>
          ) : supportPercent != null ? (
            <>
              <p><b>Heuristic decision-support score: {supportPercent}%</b></p>
              <div className="progress" role="img" aria-label={`Heuristic decision-support score ${supportPercent}%`}>
                <div style={{ width: `${supportPercent}%` }} />
              </div>
              <p className="muted">This percentage is the share of the three consistency checks that support the displayed direction. It is not a calibrated probability that the video is real or fake.</p>
            </>
          ) : (
            <>
              <p><b>Prediction score: Not available</b></p>
              <p className="muted">The detector did not calculate a Real/Fake decision-support score because the rPPG signal did not pass the quality checks. No percentage is shown rather than inventing one.</p>
            </>
          )}
          <p><b>Face coverage: {Math.round(Math.max(0, Math.min(1, qSafeCoverage(r))) * 100)}%</b> — this measures how much usable facial data was available; it is not prediction confidence.</p>
        </div>
        <p className="note">This is a research estimate from an uncalibrated heuristic, not a definitive forensic judgment. {isDemoFallback ? "A demo fallback was used because the rPPG result was inconclusive; do not interpret the displayed category or indicator as an independently detected result." : "When the rPPG quality checks pass, the result is based on the measured signal and heuristic consistency checks."}</p>
        {r.warnings.length > 0 && <ul className="warnings">{r.warnings.map((w) => <li key={w}>⚠ {w}</li>)}</ul>}
      </section>

      <section className="card">
        <h2>Signal analysis</h2>
        <div className="grid2">
          <div>
            <dl className="kv">
              <dt>Signal quality</dt><dd><b>{{ good: "Good", marginal: "Marginal", insufficient: "Insufficient" }[q.label]}</b></dd>
              <dt>Pulse-band SNR</dt><dd>{q.fused_snr_db == null ? "not computed" : `${num(q.fused_snr_db, 1)} dB`}</dd>
              <dt>Detected pulse</dt><dd>{f.hr_bpm ? `${num(f.hr_bpm, 0)} BPM (${num(f.pulse_freq_hz)} Hz)` : "—"}</dd>
              <dt>Face visible</dt><dd>{num(q.face_coverage * 100, 0)}% of frames</dd>
              <dt>Longest face loss</dt><dd>{num(q.longest_gap_s, 1)} s</dd>
              <dt>Head movement index</dt><dd>{num(q.motion_index)}</dd>
              <dt>Sampling used</dt><dd>{num(q.analysis_fs_hz, 1)} Hz (video ≈ {num(q.native_fps_estimate, 1)} fps)</dd>
            </dl>
            {Object.keys(q.roi_snr_db).length > 0 && (
              <table className="mini"><thead><tr><th>Region</th><th>Own peak (BPM)</th><th>SNR (dB)</th><th>Usable</th></tr></thead>
                <tbody>{Object.keys(REGION).map((k) => (
                  <tr key={k}><td>{REGION[k]}</td><td>{num(f.roi_peak_bpm?.[k], 0)}</td><td>{num(q.roi_snr_db[k], 1)}</td>
                    <td>{q.usable_rois.includes(k) ? "yes" : "no"}</td></tr>))}</tbody></table>
            )}
          </div>
          {a.has_thumbnail && (
            <figure className="thumb"><img src={`/api/analyses/${a.id}/thumbnail`} alt="Frame with the measured regions outlined" />
              <figcaption>Green boxes: forehead and cheek regions that were measured.</figcaption></figure>
          )}
        </div>
        {s ? (
          <>
            <h3>Filtered pulse-band signal per region (first {s.window_s} s)</h3>
            <LineChart series={roiSeries} xLabel="Time (s)" yLabel="Relative colour change" />
            <h3>Frequency spectrum (each curve scaled to its own maximum)</h3>
            <LineChart series={specSeries} xLabel="Frequency (Hz)" yLabel="Relative power" height={200}
              marks={[{ x: sp.peak_hz, label: `${num(sp.peak_hz * 60, 0)} BPM` }]} />
          </>
        ) : <p className="muted">No signal could be extracted from this video, so there are no signal charts.</p>}
      </section>

      <section className="card">
        <h2>Explainability</h2>
        {isDemoFallback && <p className="note"><b>Detector status:</b> {r.detector_headline || "Inconclusive"} The fallback is separate from the rPPG analysis.</p>}
        {r.checks.length > 0 ? (
          <table><thead><tr><th>Consistency check</th><th>Measured value</th><th>Heuristic threshold</th><th>Result</th></tr></thead>
            <tbody>{r.checks.map((c) => (
              <tr key={c.name}><td>{c.label}</td><td>{num(c.value, 3)}</td><td>{c.comparison} {c.threshold}</td>
                <td className={c.passed ? "ok" : "bad"}>{c.passed ? "passed" : "failed"}</td></tr>))}</tbody></table>
        ) : <p className="muted">Consistency checks were not run because the signal-quality requirements were not met (see reasons below).</p>}
        <h3>Why this result</h3>
        <ul className="reasons">{r.reasons.map((x, i) => (
          <li key={i}><span className={`tag ${x.kind}`}>{x.kind === "measured" ? "Measured" : "Heuristic"}</span> {x.text}</li>))}</ul>
        <p className="note"><b>Measured</b> items are numbers computed from the video. <b>Heuristic</b> items compare those numbers with
          thresholds chosen by the authors, which have not been validated on labelled data.</p>
        {f.amplitude_cv != null && <p className="muted">Informational (not used in the decision): amplitude variation between regions {num(f.amplitude_cv, 2)}, second-harmonic ratio {num(f.harmonic_ratio, 2)}.</p>}
      </section>

      <section className="card grid2">
        <div>
          <h2>Video information</h2>
          <dl className="kv">
            <dt>File name</dt><dd>{a.file_name}</dd>
            <dt>Duration</dt><dd>{vid.duration_s ? fmtSecs(vid.duration_s) : "—"}</dd>
            <dt>Frame rate</dt><dd>{vid.fps ? `${num(vid.fps, 2)} fps` : "—"}</dd>
            <dt>Resolution</dt><dd>{vid.width ? `${vid.width} × ${vid.height}` : "—"}</dd>
            <dt>Frames read</dt><dd>{vid.frames_read ?? "—"}</dd>
            <dt>Analyzed</dt><dd>{fmtDate(a.finished_at)}</dd>
            <dt>Processing time</dt><dd>{fmtSecs(a.processing_seconds)} (measured)</dd>
          </dl>
        </div>
        <div>
          <h2>Model information</h2>
          <dl className="kv">
            <dt>Method</dt><dd>{r.pipeline.method}</dd>
            <dt>Version</dt><dd>{r.pipeline.version}</dd>
            <dt>Face detector</dt><dd>{r.pipeline.face_backend === "mediapipe" ? "MediaPipe FaceLandmarker" : "OpenCV Haar cascade (fallback)"}</dd>
            <dt>Pulse band</dt><dd>{cfg.f_low}–{cfg.f_high} Hz, heart rate {cfg.hr_min_bpm}–{cfg.hr_max_bpm} BPM</dd>
            <dt>Quality gate</dt><dd>coverage ≥ {cfg.min_face_coverage * 100}%, SNR ≥ {cfg.min_snr_db} dB, motion ≤ {cfg.max_motion_index}</dd>
            <dt>Decision thresholds</dt><dd>correlation ≥ {cfg.thresh_roi_corr}, phase locking ≥ {cfg.thresh_plv}, HR spread ≤ {cfg.max_hr_spread_bpm} BPM</dd>
          </dl>
        </div>
      </section>

      <section className="card">
        <h2>Known limitations that apply</h2>
        <ul>{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </section>
      <section className="card">{actions}</section>
      {dialog}
    </div>
  );
}
