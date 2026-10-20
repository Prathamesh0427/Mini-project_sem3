"""Download the MediaPipe face landmarker model (about 4 MB) into backend/models/.
Run once:  python scripts\\download_model.py   (needs internet)"""
import urllib.request
from pathlib import Path

URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
DEST = Path(__file__).resolve().parents[1] / "models" / "face_landmarker.task"

if __name__ == "__main__":
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        print(f"Already present: {DEST}")
    else:
        print("Downloading face landmarker model ...")
        urllib.request.urlretrieve(URL, DEST)
        print(f"Saved to {DEST}")
