import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, uploadVideo } from "../api.js";
import { fmtBytes, fmtSecs } from "../format.js";

export default function Upload() {
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const submitting = useRef(false);            // blocks double submissions even before React re-renders
  const [cfg, setCfg] = useState(null);
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState(null);

  useEffect(() => { api.config().then(setCfg).catch((e) => setError(e.message)); }, []);
  useEffect(() => () => url && URL.revokeObjectURL(url), [url]);

  function choose(f) {
    setError(""); setMeta(null); setProgress(null);
    if (!f) return;
    const ext = "." + f.name.split(".").pop().toLowerCase();
    if (cfg && !cfg.allowed_extensions.includes(ext)) return setError(`Unsupported file type. Use: ${cfg.allowed_extensions.join(", ")}`);
    if (f.size === 0) return setError("This file is empty.");
    if (cfg && f.size > cfg.max_upload_mb * 1048576) return setError(`File is ${fmtBytes(f.size)}; the limit is ${cfg.max_upload_mb} MB.`);
    setFile(f);
    setUrl(URL.createObjectURL(f));
  }

  function onMeta(e) {
    const v = e.target;
    const m = { duration: v.duration, width: v.videoWidth, height: v.videoHeight };
    setMeta(m);
    if (cfg && m.duration < cfg.min_duration_s) setError(`This video is ${fmtSecs(m.duration)} long; at least ${cfg.min_duration_s} s is needed.`);
    else if (cfg && m.duration > cfg.max_duration_s) setError(`This video is ${fmtSecs(m.duration)} long; the limit is ${cfg.max_duration_s} s.`);
  }

  async function analyze() {
    if (submitting.current || !file) return;
    submitting.current = true;
    setError(""); setProgress(0);
    try {
      const { id } = await uploadVideo(file, setProgress);
      navigate(`/analyses/${id}`);
    } catch (e) {
      setError(e.message); setProgress(null); submitting.current = false;
    }
  }

  const busy = progress !== null;
  return (
    <div className="card narrow">
      <h1>Analyze a video</h1>
      <p className="muted">
        Supported: {cfg ? cfg.allowed_extensions.join(", ") : "…"} · up to {cfg?.max_upload_mb ?? "…"} MB ·
        {" "}{cfg?.min_duration_s}–{cfg?.max_duration_s} seconds · at least {cfg?.min_fps} fps · one clearly visible, mostly still face.
      </p>

      <div className={`drop ${drag ? "drag" : ""}`} onClick={() => !busy && inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); if (!busy) choose(e.dataTransfer.files[0]); }}>
        <p><b>Drag and drop a video here</b></p>
        <button type="button" className="btn ghost" disabled={busy}>Browse files…</button>
        <input ref={inputRef} type="file" hidden accept="video/*,.mkv" onChange={(e) => choose(e.target.files[0])} />
      </div>

      {file && (
        <div className="selected">
          {url && <video src={url} controls muted preload="metadata" onLoadedMetadata={onMeta}
            onError={() => setMeta({ unsupported: true })} />}
          <dl>
            <dt>File name</dt><dd>{file.name}</dd>
            <dt>Size</dt><dd>{fmtBytes(file.size)}</dd>
            <dt>Duration</dt><dd>{meta?.duration ? fmtSecs(meta.duration) : meta?.unsupported ? "Browser cannot read it (the server will check)" : "reading…"}</dd>
            <dt>Resolution</dt><dd>{meta?.width ? `${meta.width} × ${meta.height}` : "—"}</dd>
          </dl>
        </div>
      )}

      {error && <div className="alert error">{error}</div>}
      {busy && (
        <div className="progress" aria-label="Upload progress"><div style={{ width: `${Math.round(progress * 100)}%` }} /></div>
      )}
      {busy && <p className="muted">Uploading… {Math.round(progress * 100)}% (analysis starts right after the upload)</p>}

      <button className="btn primary big" onClick={analyze} disabled={!file || busy || !!error}>
        {busy ? "Uploading…" : "Analyze Video"}
      </button>
    </div>
  );
}
