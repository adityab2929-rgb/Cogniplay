# saved_models/

**This directory is intentionally empty. No trained model weights ship with
CogniPlay.**

## Why it is empty

Training the CNN and the LSTM properly would require a labelled dataset of
gameplay sessions from children with confirmed diagnoses. We do not have one,
and publishing weights fitted to anything less would imply a validity this
project does not have.

So instead of shipping weights that look authoritative and are not, the
service ships with the path it can actually defend.

## What runs instead

`models/fusion_model.py` falls back to a **deterministic clinical-heuristic
scorer**. It is a transparent weighted sum over behavioural markers taken from
the early-screening literature:

| Condition | Markers driving the score |
| --- | --- |
| Dyslexia | b/d and p/q letter reversals, letter accuracy, hesitation before answering, response latency |
| Dyscalculia | number accuracy, the subitizing gap (intact on 1-5 but collapsing on 6-10), how far wrong answers land from the target |
| ADHD | impulsive false-alarm taps, accuracy decline across the session, inconsistency of attention between intervals |

Every weight lives in the `HEURISTIC_WEIGHTS` table in
`models/fusion_model.py`, and every score can be traced back through
`explainability/shap_explain.py` to the individual behaviours that produced
it. The markers are drawn from published work; **the weights are the authors'
judgement, not values fitted to clinical data.**

The startup log tells you which path is active:

```
FusionModel ready -- NO trained weights found in .../saved_models. Using the
deterministic clinical-heuristic path as the source of truth.
```

`GET /health` reports the same thing as `trained_weights_loaded` and
`scoring_path`.

## Enabling the trained path

If you train your own networks, drop the checkpoints here using these exact
filenames:

```
saved_models/
  dyslexia_cnn.pt     -> loaded by models/cnn_model.py  (DyslexiaCNN)
  adhd_lstm.pt        -> loaded by models/lstm_model.py (AttentionLSTM)
```

Requirements for a checkpoint to load:

1. **PyTorch must be installed.** Uncomment `torch` in `requirements.txt`.
   Without torch the NumPy fallback classes are used, and they log a warning
   if they find a `.pt` file they cannot read.
2. **The architecture must match.** Save a `state_dict` (or a dict with a
   `"state_dict"` key) from the exact classes in `models/cnn_model.py` and
   `models/lstm_model.py`:
   - `DyslexiaCNN` expects a 20-feature input vector, in the order given by
     `features.extract_features.FEATURE_NAMES`.
   - `AttentionLSTM` expects a `(6, 4)` sequence from
     `features.extract_features.build_sequence`.
3. **Restart the service.** Weights are loaded once at startup.

A failed load is never fatal: the error is logged and the heuristic path
continues.

Once a checkpoint loads, `FusionModel` **blends** rather than replaces --
60% CNN / 40% heuristic for dyslexia, 50% LSTM / 50% heuristic for ADHD.
Dyscalculia has no dedicated network and stays fully heuristic. Blending keeps
a partially trained model from producing an output nobody can explain.

## Reminder

Whichever path is active, the output is a **screening indicator, not a
diagnosis**. See the notice at the top of `models/fusion_model.py`.
