# Architecture

```
Browser (React/Vite) --/api--> FastAPI --> SQLite (storage/analyses.db)
                                  |--> single background worker --> detector (app/detector)
                                  '--> storage/uploads (temporary), storage/artifacts (preview JPEG)
```

* **Upload**: streamed to `storage/uploads/<uuid>.<ext>` with a size cap. The content is sniffed (MP4/MOV, AVI, WebM/MKV
  signatures), then OpenCV must decode a frame and metadata must satisfy duration/fps limits. Failures return a JSON error and
  leave no file behind. Valid uploads get a row (`queued`) and are processed by one worker thread (CPU-bound; the face model is
  loaded once and reused).
* **Detector** (`backend/app/detector`)
  * `video.py`: validation, face finding (MediaPipe if the model file exists, else Haar), smoothed ROI boxes, per-frame mean green of
    forehead / left cheek / right cheek, real frame timestamps, head-motion index. Every frame is read (no decimation).
  * `signal.py`: uniform resampling, AC/DC normalisation, detrend, Butterworth band-pass (`sosfiltfilt`), Welch spectrum, de Haan-style SNR,
    narrow-band cross-region correlation and phase-locking value, quality gate, decision rules, JSON-safe result with chart data.
  * `pipeline.py`: `analyze_video()`, the single entry point used by the service. Pure functions in `signal.py` are unit-tested without video.
* **Statuses**: `queued -> processing -> completed | failed`. `failed` means a processing problem (corrupt video, internal error);
  `inconclusive` is a *completed* analysis with insufficient evidence. They are never mixed. Rows left active by a crash are marked `failed` on restart.
* **Storage**: the full result JSON (features, checks, reasons, warnings, downsampled signal and spectrum for charts, config, model version)
  is stored in the row, so reports never need the original video. The uploaded video is deleted when analysis ends (`RPPG_KEEP_UPLOADS=1` to keep).
* **Delete**: sets the job's cancel flag, deletes the row, then removes `uploads/<id>*` and `artifacts/<id>*` (only inside the storage folders;
  ids are validated 32-hex strings). A worker that finishes after deletion finds no row and removes whatever it wrote.
* **API**: `GET /api/config, /api/stats`; `POST /api/analyses`; `GET /api/analyses?search&verdict&sort&page&page_size`;
  `GET|DELETE /api/analyses/{id}`; `GET /api/analyses/{id}/thumbnail|download`.

SQLite table `analyses`: id, file_name, status, stage, progress_done/total, created_at, started_at, finished_at, processing_seconds,
verdict, signal_quality, video_meta (JSON), result (JSON), error_code, error_message, model_version, has_thumbnail.
