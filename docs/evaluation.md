# Evaluation status

**Model accuracy has not been established.** No labelled real/fake videos were used and no benchmark was run, so there are no accuracy,
precision, recall, F1 or ROC-AUC numbers for this project. The only measurements are automated software tests
(`backend/tests`): synthetic signals and synthetic face-less videos, which verify the code, not the detector's real-world validity.

## How to evaluate properly

1. Collect labelled videos (e.g. real clips you recorded plus fakes made from them; public sets such as FaceForensics++, Celeb-DF, DFDC
   have their own licences). Record class counts: imbalance changes how accuracy should be read.
2. Split by **person/source video**, not by clip: clips of the same person or the same source must all be in train *or* test.
3. Tune thresholds only on the tuning split; report once on the held-out split. Report compression level, because rPPG is very sensitive to it.
4. Run `python scripts\evaluate.py <dataset>` (backend terminal). It reports coverage (share of videos that got a real/fake-like verdict),
   a confusion matrix, accuracy, precision, recall and F1 on decided videos only, plus a per-video CSV. Treat "inconclusive" as a cost, not a success.
5. ROC-AUC is not meaningful for the current rule-based verdict; it would need a continuous score calibrated on held-out data.

Filename labels beginning with `real_`, `real-`, `real `, `fake_`, `fake-`, or `fake ` are saved only as optional evaluation labels in the web app. The detector never receives those labels. The UI's decision-support percentage is a proportion of heuristic checks, not a calibrated probability; inconclusive reports show face coverage instead.
