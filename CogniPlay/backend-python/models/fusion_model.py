"""
FusionModel -- combines the CNN, the LSTM and a clinical-heuristic scorer
into the three CogniPlay screening indicators.

=============================================================================
SCIENTIFIC HONESTY / SCOPE NOTICE -- READ BEFORE INTERPRETING ANY OUTPUT
=============================================================================
The numbers produced by this module are **screening indicators for a student
project demonstration. They are NOT a clinical diagnosis** of dyslexia,
dyscalculia, ADHD, or any other condition, and must never be presented to a
parent, teacher or clinician as one.

Specifically:

* **No trained weights ship with this project.** ``saved_models/`` is empty by
  design. With no checkpoint present, the neural networks are randomly
  initialised, so their output carries no information and this class ignores
  them entirely.
* **The default path is the deterministic clinical heuristic below.** It is a
  transparent weighted sum over hand-chosen behavioural markers drawn from the
  published early-screening literature (letter reversals, the subitizing
  gap, impulsive responding, within-session attention decline). The *markers*
  are real; the *weights* are the authors' judgement, not values fitted to
  labelled clinical data.
* **It has never been validated.** There is no sensitivity, specificity, or
  normative sample behind these thresholds. A "High" indicator means "this
  gameplay pattern resembles the markers described in the literature", and
  the only appropriate action it supports is a conversation with a qualified
  professional.
* **Nothing here substitutes for assessment by an educational psychologist.**

The heuristic path is deliberately the source of truth: a transparent,
inspectable rule that a grader or a parent can follow line by line is far more
defensible for this use case than an unvalidated black box would be.
=============================================================================

Python 3.9 compatible: typing.Optional / typing.Dict / typing.List only.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .cnn_model import DyslexiaCNN, TORCH_AVAILABLE
from .lstm_model import AttentionLSTM

logger = logging.getLogger(__name__)

MODEL_VERSION: str = "1.0.0"

#: The three conditions screened for, in the order they appear in responses.
CONDITIONS: List[str] = ["dyslexia", "dyscalculia", "adhd"]

#: Filenames looked for inside ``saved_models/``.
CNN_WEIGHTS_FILENAME: str = "dyslexia_cnn.pt"
LSTM_WEIGHTS_FILENAME: str = "adhd_lstm.pt"


# ---------------------------------------------------------------------------
# Clinical heuristic weights
# ---------------------------------------------------------------------------
# Structure:  condition -> { feature_name: (weight, higher_value_is_worse) }
#
# ``higher_value_is_worse=False`` marks an *ability* feature (an accuracy or
# efficiency), whose contribution is inverted -- high accuracy lowers risk.
#
# Weights per condition need not sum to 1.0; the scorer divides by the total
# weight it actually found, so a feature missing from the vector degrades the
# score gracefully rather than silently biasing it toward zero.
#
# Rationale for the headline weights:
#   dyslexia     -- b/d and p/q reversals are the most specific behavioural
#                   marker available from this gameplay, so they carry the
#                   most weight; letter accuracy is the broad ability check.
#   dyscalculia  -- number accuracy plus the subitizing gap (intact on 1-5,
#                   collapsing on 6-10), the classic numerosity signature.
#   adhd         -- impulsive false alarms plus decline and inconsistency of
#                   attention across the session.
# Motor and gaze features appear with small weights across all three as
# non-specific supporting evidence.
# ---------------------------------------------------------------------------

HEURISTIC_WEIGHTS: Dict[str, Dict[str, Tuple[float, bool]]] = {
    "dyslexia": {
        "bd_confusion_rate": (0.30, True),
        "pq_confusion_rate": (0.18, True),
        "letter_accuracy": (0.22, False),
        "hesitation_avg_ms": (0.12, True),
        "reversal_error_ratio": (0.10, True),
        "letter_response_time": (0.08, True),
        "avg_tremor_score": (0.06, True),
        "overall_accuracy": (0.04, False),
        "drawing_speed": (0.03, True),
    },
    "dyscalculia": {
        "number_accuracy": (0.34, False),
        "subitizing_gap": (0.28, True),
        "magnitude_error_avg": (0.22, True),
        "number_response_time": (0.16, True),
        "overall_accuracy": (0.05, False),
        "gaze_efficiency": (0.05, False),
    },
    "adhd": {
        "impulsivity_score": (0.28, True),
        "performance_drop": (0.24, True),
        "attention_variance": (0.20, True),
        "butterfly_accuracy": (0.14, False),
        "response_time_variability": (0.08, True),
        "gaze_efficiency": (0.08, False),
        "off_screen_rate": (0.06, True),
    },
}

# Calibration of the raw weighted evidence onto a 0-1 indicator.
#
# The raw score is a weighted mean of features that mostly sit low for a
# typically developing child, so mapping it linearly would bunch every result
# around 0.2-0.4 and never separate anyone. Instead we push it through a
# logistic centred on ``_CALIBRATION_MIDPOINT``: a child whose weighted
# evidence sits at 0.35 lands at exactly 0.5 (the borderline), and the scale
# controls how sharply the indicator moves away from that point.
#
# These two constants are the honest location of all the "clinical judgement"
# in this model. Changing them shifts every score, so they are named, exposed
# and documented rather than buried in an expression.
_CALIBRATION_MIDPOINT: float = 0.35
_CALIBRATION_SCALE: float = 0.18

# Risk banding thresholds, fixed by the API contract.
_LOW_THRESHOLD: float = 0.34
_MODERATE_THRESHOLD: float = 0.67

# Blend ratios used *only* when a genuine trained checkpoint is loaded.
_TRAINED_MODEL_SHARE: float = 0.60
_TRAINED_LSTM_SHARE: float = 0.50


def _clamp01(value: Any) -> float:
    """Clamp to [0, 1], mapping None/NaN/inf to 0.0."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(v):
        return 0.0
    return float(min(1.0, max(0.0, v)))


def _logistic(x: float) -> float:
    """Numerically stable logistic function."""
    if x >= 0:
        return float(1.0 / (1.0 + np.exp(-x)))
    exp_x = np.exp(x)
    return float(exp_x / (1.0 + exp_x))


def risk_level(score: Any) -> str:
    """Band a 0-1 indicator into ``"Low"`` / ``"Moderate"`` / ``"High"``.

    Thresholds are fixed by the API contract that the Node backend and the
    React frontend both depend on: ``< 0.34`` Low, ``< 0.67`` Moderate,
    otherwise High.
    """
    value = _clamp01(score)
    if value < _LOW_THRESHOLD:
        return "Low"
    if value < _MODERATE_THRESHOLD:
        return "Moderate"
    return "High"


def directional_value(value: float, higher_is_worse: bool) -> float:
    """Orient a feature so that larger always means *more* evidence of risk.

    Ability features (accuracy, efficiency) are inverted; difficulty features
    pass through unchanged.
    """
    v = _clamp01(value)
    return v if higher_is_worse else (1.0 - v)


def calibrate(raw_score: float) -> float:
    """Map raw weighted evidence onto the reported 0-1 indicator.

    See ``_CALIBRATION_MIDPOINT`` / ``_CALIBRATION_SCALE`` above for what the
    curve means and why it exists.
    """
    if _CALIBRATION_SCALE <= 0.0:
        return _clamp01(raw_score)
    z = (_clamp01(raw_score) - _CALIBRATION_MIDPOINT) / _CALIBRATION_SCALE
    return _clamp01(_logistic(z))


def heuristic_score(condition: str,
                    feature_map: Dict[str, float]) -> Tuple[float, float]:
    """Score one condition from the clinical heuristic.

    Args:
        condition: One of ``CONDITIONS``.
        feature_map: ``feature_name -> value`` mapping, all values in [0, 1].

    Returns:
        ``(calibrated_score, raw_weighted_evidence)``. Both in [0, 1]. When
        the condition is unknown or no weighted feature is present, returns
        ``(0.0, 0.0)`` -- no evidence means no risk asserted.
    """
    weights = HEURISTIC_WEIGHTS.get(condition)
    if not weights or not isinstance(feature_map, dict):
        return 0.0, 0.0

    weighted_sum = 0.0
    total_weight = 0.0
    for name, spec in weights.items():
        if name not in feature_map:
            continue
        weight, higher_is_worse = spec
        weighted_sum += weight * directional_value(feature_map[name],
                                                   higher_is_worse)
        total_weight += weight

    if total_weight <= 0.0:
        return 0.0, 0.0

    raw = weighted_sum / total_weight
    return calibrate(raw), _clamp01(raw)


def heuristic_scores(feature_map: Dict[str, float]) -> Dict[str, float]:
    """Score all three conditions from the clinical heuristic."""
    return {condition: heuristic_score(condition, feature_map)[0]
            for condition in CONDITIONS}


class FusionModel:
    """Combines CNN, LSTM and clinical heuristics into the final scores.

    Decision rule, in plain terms:

    * The clinical heuristic is computed for all three conditions, always.
    * If -- and only if -- a genuine trained checkpoint was loaded, the
      corresponding network's output is blended in (60% CNN for dyslexia,
      50% LSTM for ADHD). Dyscalculia has no dedicated network and is always
      pure heuristic.
    * Without checkpoints (the shipped state) the heuristic is used alone and
      ``used_path`` reports ``"heuristic"``.

    The model is stateless per request and safe to construct once at startup
    and reuse across requests.
    """

    def __init__(self, saved_models_dir: Optional[str] = None) -> None:
        """Build the sub-models and attempt to load weights.

        Args:
            saved_models_dir: Directory to search for ``.pt`` checkpoints.
                Defaults to the ``saved_models/`` folder beside this package.
        """
        if saved_models_dir is None:
            package_dir = os.path.dirname(os.path.abspath(__file__))
            saved_models_dir = os.path.join(
                os.path.dirname(package_dir), "saved_models"
            )
        self.saved_models_dir = saved_models_dir
        self.model_version = MODEL_VERSION
        self.torch_available = TORCH_AVAILABLE

        self.cnn = DyslexiaCNN()
        self.lstm = AttentionLSTM()

        self.cnn_trained = self._try_load(self.cnn, CNN_WEIGHTS_FILENAME)
        self.lstm_trained = self._try_load(self.lstm, LSTM_WEIGHTS_FILENAME)

        if self.cnn_trained or self.lstm_trained:
            logger.info(
                "FusionModel ready -- trained weights in use (cnn=%s, "
                "lstm=%s). Neural output is blended with the heuristic.",
                self.cnn_trained, self.lstm_trained,
            )
        else:
            logger.info(
                "FusionModel ready -- NO trained weights found in %s. Using "
                "the deterministic clinical-heuristic path as the source of "
                "truth. Output is a screening indicator, not a diagnosis.",
                self.saved_models_dir,
            )

    def _try_load(self, model: Any, filename: str) -> bool:
        """Attempt to load one checkpoint. Never raises."""
        try:
            path = os.path.join(self.saved_models_dir, filename)
            if not os.path.exists(path):
                return False
            loaded = bool(model.load_weights(path))
            return loaded and bool(getattr(model, "is_trained", False))
        except Exception as exc:
            logger.warning("Checkpoint load for %s failed: %s", filename, exc)
            return False

    @property
    def uses_trained_weights(self) -> bool:
        """True when at least one genuine checkpoint is driving the output."""
        return bool(self.cnn_trained or self.lstm_trained)

    def predict(self, features: Any, names: Optional[List[str]] = None,
                sequence: Optional[Any] = None) -> Dict[str, Any]:
        """Produce the three screening indicators.

        Args:
            features: The fixed-length feature vector from
                ``features.extract_features.extract_features``.
            names: Matching feature names. Required to map values onto the
                heuristic weight tables; when omitted, the heuristic cannot
                run and all scores fall back to 0.0.
            sequence: Optional ``(T, F)`` attention sequence for the LSTM.

        Returns:
            A dict with keys ``dyslexia_score``, ``dyscalculia_score``,
            ``adhd_score`` (floats in [0, 1]), ``risk_levels`` (dict of
            three band strings), ``raw_scores`` (pre-calibration evidence,
            useful for debugging), ``used_path`` (``"heuristic"`` /
            ``"blended"``), and ``model_version``.

        Never raises: any internal failure degrades to neutral 0.0 scores
        with ``used_path`` set to ``"error"``.
        """
        try:
            feature_map = self._to_feature_map(features, names)

            scores: Dict[str, float] = {}
            raw_scores: Dict[str, float] = {}
            for condition in CONDITIONS:
                score, raw = heuristic_score(condition, feature_map)
                scores[condition] = score
                raw_scores[condition] = raw

            used_path = "heuristic"

            # Blend in the networks only when genuinely trained. An untrained
            # net is random noise and is deliberately excluded.
            if self.cnn_trained:
                cnn_score = _clamp01(self.cnn.predict(features))
                scores["dyslexia"] = _clamp01(
                    _TRAINED_MODEL_SHARE * cnn_score
                    + (1.0 - _TRAINED_MODEL_SHARE) * scores["dyslexia"]
                )
                used_path = "blended"

            if self.lstm_trained and sequence is not None:
                lstm_score = _clamp01(self.lstm.predict(sequence))
                scores["adhd"] = _clamp01(
                    _TRAINED_LSTM_SHARE * lstm_score
                    + (1.0 - _TRAINED_LSTM_SHARE) * scores["adhd"]
                )
                used_path = "blended"

            logger.info(
                "FusionModel.predict path=%s dyslexia=%.3f dyscalculia=%.3f "
                "adhd=%.3f",
                used_path, scores["dyslexia"], scores["dyscalculia"],
                scores["adhd"],
            )

            return {
                "dyslexia_score": round(scores["dyslexia"], 4),
                "dyscalculia_score": round(scores["dyscalculia"], 4),
                "adhd_score": round(scores["adhd"], 4),
                "risk_levels": {
                    condition: risk_level(scores[condition])
                    for condition in CONDITIONS
                },
                "raw_scores": {k: round(v, 4) for k, v in raw_scores.items()},
                "used_path": used_path,
                "model_version": self.model_version,
            }
        except Exception as exc:
            logger.error("FusionModel.predict failed: %s", exc, exc_info=True)
            return {
                "dyslexia_score": 0.0,
                "dyscalculia_score": 0.0,
                "adhd_score": 0.0,
                "risk_levels": {c: "Low" for c in CONDITIONS},
                "raw_scores": {c: 0.0 for c in CONDITIONS},
                "used_path": "error",
                "model_version": self.model_version,
            }

    @staticmethod
    def _to_feature_map(features: Any,
                        names: Optional[List[str]]) -> Dict[str, float]:
        """Zip features and names into a mapping, guarding length mismatch."""
        if not names:
            return {}
        try:
            flat = np.asarray(features, dtype=np.float32).reshape(-1)
        except Exception:
            return {}
        return {name: _clamp01(flat[i]) for i, name in enumerate(names)
                if i < flat.shape[0]}


__all__: List[str] = [
    "FusionModel", "HEURISTIC_WEIGHTS", "CONDITIONS", "MODEL_VERSION",
    "risk_level", "heuristic_score", "heuristic_scores", "calibrate",
    "directional_value",
]
