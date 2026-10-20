# Limitations

* **Not validated.** No labelled real/fake dataset was available while building this, so detection accuracy is unknown. All thresholds
  (`backend/app/detector/config.py`) are uncalibrated defaults, partly inherited from the original notebook.
* **Percentages are not probabilities.** The displayed decision-support percentage is the share of the three heuristic checks that support the selected direction. For inconclusive results, the displayed percentage is face coverage. Neither is calibrated confidence.
* **Absence of a pulse is not evidence of a fake.** Compression, low light, make-up, dark skin tones at low exposure, motion and low resolution
  remove real pulses; such videos are reported *inconclusive*.
* **Presence of a consistent pulse is not proof of authenticity.** Some generators keep the source video's physiological signal, and shared
  lighting or compression artefacts can create cross-region correlation.
* **Green-channel rPPG only.** No chrominance methods (CHROM/POS), skin segmentation or motion compensation beyond box smoothing.
* **Haar fallback** is much less accurate than MediaPipe; run `scripts/download_model.py`.
* **One face, mostly frontal and still.** Multiple faces: the largest is used. Strong head motion triggers warnings or an inconclusive result.
* Hand-written synthetic signals in the tests check that the code behaves as designed; they say nothing about real-world performance.
* Local single-user tool: no authentication, one analysis at a time, uploads capped at 200 MB / 120 s by default.
* The React interface and the HTTP layer were written without being run in the authoring environment (no network): run the tests and the app yourself.

## What changed from the original notebook, and why

| Original | Now | Reason |
|---|---|---|
| Kept every Nth frame but filtered/FFT'd with the original fps | All frames read; real timestamps; resampled to a uniform grid | Decimation distorted the frequency axis (wrong heart rate and band) |
| Haar boxes jumped frame to frame | EMA-smoothed boxes; detection on a contrast-enhanced copy, measurement on the untouched frame | Box jitter injected motion noise; CLAHE altered the signal |
| Any one failed test => FAKE; no inconclusive state | Quality gate first; 3-way outcome; majority of three checks after quality gates; separate failed state | Reduces the one-check borderline dead zone while keeping poor-quality video inconclusive |
| `E_peak >= 3`, dominance, harmonic thresholds | Removed from the decision (harmonic kept as information); SNR gate instead | Units depended on clip length/ROI size; noise passed D and H |
| Phase coherence from unwrapped broadband Hilbert phase | Narrow-band phase-locking value (0–1, length independent) | The old score depended on clip length and drift |
| Amplitude CV from 3 numbers in the decision | Informational only | Too noisy to decide anything |
| Printed verdict in a notebook | FastAPI + SQLite + React, tests, saved reports, delete | Requested web application |
