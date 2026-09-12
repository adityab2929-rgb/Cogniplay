# Synthetic demo data and training utilities

This folder contains **development fixtures only**.  The sessions and labels
are generated from assumptions in `generate_synthetic_data.py`; they are not
observations of children and must not be used to make, validate, calibrate, or
deploy a clinical screening model.

## Generated files

Run from `backend-python`:

```bash
python training/generate_synthetic_data.py
python training/validate_synthetic_data.py
```

The generator writes `training/synthetic_data/`:

| File | Rows | Purpose |
| --- | ---: | --- |
| `raw_sessions.jsonl` | 10,000 | Complete mock request payloads, one JSON object per session. |
| `labels.csv` | 10,000 | Synthetic binary labels for the three conditions and a profile name. |
| `cnn_training.csv` | 10,000 | One row per session.  Its **20 model-input columns** exactly equal `FEATURE_NAMES`; `dyslexia_label` is the target. |
| `lstm_training.csv` | 60,000 | Six rows per session.  Its **four model-input columns** are `interval_score`, `correct_norm`, `wrong_norm`, and `score_change`; group each six-row session into a `(6, 4)` LSTM input. |
| `manifest.json` | 1 | Reproducibility metadata, dimensions and SHA-256 checksums. |

All source values are complete and finite. The validation command checks:

* exact header/order agreement with the live feature code;
* 10,000 distinct session IDs and no duplicate model-input rows/sequences;
* six ordered timesteps for every LSTM session;
* no blank, NaN, infinite, or out-of-range feature values;
* label and raw-payload consistency; and
* exact equality between CSV values and a fresh call to
  `extract_features` / `build_sequence`.

## Training and deployment boundary

`train_models.py` can train the provided CNN and LSTM architectures **only
for a pipeline demonstration**. Its default output is
`training/demo_models/`, deliberately not `saved_models/`. It refuses the
synthetic folder as a source for a live checkpoint.

For a real research workflow, replace the synthetic folder with consented,
de-identified sessions and independently verified labels, validate on a
child-disjoint holdout set, obtain the required governance/clinical review,
and then explicitly select `backend-python/saved_models/` as the output
directory. The live service loads only these exact checkpoint names:

```text
saved_models/dyslexia_cnn.pt
saved_models/adhd_lstm.pt
```

Synthetic labels are not diagnoses and never enter the live API request or
live prediction path.

## Running the app in synthetic demonstration mode

After creating the two demo checkpoints, set this environment variable before
starting the Python service:

```powershell
$env:COGNIPLAY_SCORING_MODE = "demo"
.\.venv\Scripts\python.exe main.py
```

In this mode the service loads `training/demo_models/` and reports
`scoring_mode: "demo"`. The Results page shows an explicit warning. The
normal default, `heuristic`, never loads a checkpoint. `validated` is reserved
for independently validated checkpoints placed in `saved_models/`.
