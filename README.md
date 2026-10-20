# rPPG-Based Explainable Deepfake Detection

A local web app around a training-free remote-photoplethysmography (rPPG) detector. It measures the faint
pulse-related colour change on the forehead and both cheeks, checks whether the regions agree, and explains
the result. It runs on a normal Windows laptop, CPU only. **No accuracy has been measured** (see `docs/evaluation.md`).

```
backend/   FastAPI + SQLite + the detector (app/detector)      -> http://127.0.0.1:8000
frontend/  React + Vite user interface                         -> http://localhost:5173
notebooks/ original/ (untouched backup) + improved_detector.ipynb
storage/   created at runtime: analyses.db, uploads/, artifacts/
docs/      architecture.md, limitations.md, evaluation.md
```

## 1. One-time installs (Windows)

1. **Python 3.11 or 3.12** (64-bit) from https://www.python.org/downloads/ . Tick *Add python.exe to PATH*.
   MediaPipe does not support the newest Python versions, so avoid 3.13+.
2. **Node.js LTS** from https://nodejs.org/ .
3. Open **PowerShell** (not cmd) and check: `py --version` and `node --version`.

## 2. Backend setup  —  run these in PowerShell window #1 ("backend terminal")

```powershell
cd path\to\deepfake-detector\backend
py -3.12 -m venv .venv            # use -3.11 if that is what you installed
Set-ExecutionPolicy -Scope Process Bypass    # only needed if activation is blocked
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts\download_model.py   # downloads the ~4 MB MediaPipe face model (needs internet)
python -m app.database.init_db     # creates storage\analyses.db (it is also created automatically on start)
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Leave this window open. If you skip the model download the app still works but falls back to the less accurate
OpenCV Haar face detector (the report says which one was used).

Optional environment variables (set before `uvicorn`, none are required):

```powershell
$env:RPPG_MAX_UPLOAD_MB = "200"     # upload size limit
$env:RPPG_STORAGE_DIR   = "D:\rppg-data"   # where the database and files live
$env:RPPG_KEEP_UPLOADS  = "0"       # "1" keeps uploaded videos after analysis (default deletes them)
```

## 3. Frontend setup  —  run these in PowerShell window #2 ("frontend terminal")

```powershell
cd path\to\deepfake-detector\frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser. Both windows must stay running.

## 4. Running again later

Backend window: `cd backend`, `.\.venv\Scripts\Activate.ps1`, `uvicorn app.main:create_app --factory --port 8000`.
Frontend window: `cd frontend`, `npm run dev`. Your history is kept in `storage\analyses.db`.

## 5. Tests  —  backend terminal (venv active)

```powershell
cd path\to\deepfake-detector\backend
pip install -r requirements-dev.txt
pytest -q
```

## 6. Using it

* **Analyze video**: drop a clip (10–120 s, ≥ 15 fps, one mostly still, well-lit face, ≤ 200 MB). Progress is shown on the report page.
* **Result**: *real-like*, *fake-like* or *inconclusive*, with the measured numbers, charts and reasons. Classified results also show a transparent heuristic decision-support percentage (not a calibrated probability); inconclusive results show face-coverage percentage instead.
* **Optional filename labels**: filenames beginning with `real` or `fake` followed by a separator (for example `real_vid2.mp4`, `FAKE-test4.mov`) are stored as ground-truth labels for evaluation only. They never affect the prediction. Other filenames remain unlabeled.
* **History**: search, filter, sort, open or delete reports. Deleting removes the database record, the preview image and any leftover upload.
* Best results: steady camera, frontal face, even lighting, little compression (a recording straight from a phone, not a re-shared clip).

## 7. Evaluating on your own labelled videos

Put videos in `dataset\real\` and `dataset\fake\`, then (backend terminal) run `python scripts\evaluate.py path\to\dataset`.
It reports coverage (how many were decidable), a confusion matrix, precision, recall and F1 on decided videos only.

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope Process Bypass`, then activate again |
| `pip install mediapipe` fails | Use Python 3.11/3.12 64-bit; recreate the venv |
| Browser shows "Cannot reach the backend" | Start the backend window first; it must print `Uvicorn running on http://127.0.0.1:8000` |
| Port already in use | Add `--port 8001` and change `target` in `frontend/vite.config.js` |
| Almost every video is *inconclusive* | Read the measured gate reasons on the report; poor face coverage, weak pulse SNR, short clips and movement can prevent classification. The updated heuristic uses a majority of three checks once quality gates pass, but it is not a validated deepfake classifier. |
