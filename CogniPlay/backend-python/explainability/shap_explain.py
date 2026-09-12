"""
Explanation layer -- why did each condition score the way it did?

A screening indicator that a parent cannot interrogate is not much use, so
every score ships with the handful of behaviours that drove it, each written
in plain English.

Two attribution paths, same output shape:

* **SHAP available** -- a ``KernelExplainer`` is run against the clinical
  heuristic scoring function, giving proper Shapley attributions.
* **SHAP missing (the default)** -- a transparent attribution: each feature's
  contribution is its heuristic weight times its risk-oriented value,
  normalised to a share of the total evidence. For an additive weighted-sum
  model this is *exactly* what SHAP would converge to anyway, so the fallback
  is not an approximation of convenience -- it is the analytic answer.

Either way, a failure in this module must never cost the caller their
prediction: :func:`explain` catches everything and degrades.

Python 3.9 compatible: typing.Optional / typing.Dict / typing.List only.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from models.fusion_model import (
    CONDITIONS,
    HEURISTIC_WEIGHTS,
    directional_value,
    heuristic_score,
    risk_level,
)

logger = logging.getLogger(__name__)

try:  # pragma: no cover - depends on the deployment environment
    import shap
    SHAP_AVAILABLE = True
except ImportError:  # pragma: no cover
    shap = None  # type: ignore[assignment]
    SHAP_AVAILABLE = False
    logger.info(
        "SHAP not installed -- using the analytic weight x value attribution."
    )

#: How many factors to report per condition.
MAX_FACTORS: int = 5
MIN_FACTORS: int = 3

#: Number of KernelExplainer samples. Kept low: the request is synchronous
#: and the heuristic is cheap but not free.
_SHAP_NSAMPLES: int = 100


# ---------------------------------------------------------------------------
# Plain-English descriptions
# ---------------------------------------------------------------------------
# For each feature: (text when this is a *concern*, text when it is a
# *strength*). Chosen by the risk-oriented value crossing 0.5, so the
# sentence always agrees with the direction of the contribution.
#
# Written at a reading level a parent can follow, with no jargon and no
# diagnostic language ("confused b and d often", never "shows dyslexic
# reversal pathology").
# ---------------------------------------------------------------------------

_DESCRIPTIONS: Dict[str, Tuple[str, str]] = {
    "bd_confusion_rate": (
        "Often mixed up the letters b and d",
        "Told the letters b and d apart reliably",
    ),
    "pq_confusion_rate": (
        "Often mixed up the letters p and q",
        "Told the letters p and q apart reliably",
    ),
    "letter_accuracy": (
        "Picked the correct letter less often than expected for this age",
        "Picked the correct letter most of the time",
    ),
    "hesitation_avg_ms": (
        "Paused for a long time before choosing a letter",
        "Chose letters without long pauses",
    ),
    "letter_response_time": (
        "Took a long time to respond in the letter game",
        "Responded at a comfortable pace in the letter game",
    ),
    "reversal_error_ratio": (
        "Most letter mistakes were mirror-image letters rather than "
        "random guesses",
        "Letter mistakes were spread out rather than mirror-image letters",
    ),
    "number_accuracy": (
        "Answered fewer number questions correctly than expected for "
        "this age",
        "Answered most number questions correctly",
    ),
    "subitizing_gap": (
        "Counted small groups (1-5) well but struggled with larger "
        "groups (6-10)",
        "Handled small and larger groups of objects equally well",
    ),
    "number_response_time": (
        "Took a long time to answer number questions",
        "Answered number questions at a comfortable pace",
    ),
    "magnitude_error_avg": (
        "When wrong, the answer was far from the correct number rather "
        "than close to it",
        "When wrong, the answer was usually close to the correct number",
    ),
    "impulsivity_score": (
        "Tapped quickly on the wrong targets, suggesting acting before "
        "looking",
        "Waited to check the target before tapping",
    ),
    "performance_drop": (
        "Accuracy fell noticeably as the game went on",
        "Kept accuracy steady from the start of the game to the end",
    ),
    "attention_variance": (
        "Focus swung between very good and very poor across the session",
        "Focus stayed at a consistent level across the session",
    ),
    "butterfly_accuracy": (
        "Caught the correct butterfly less often than expected for "
        "this age",
        "Caught the correct butterfly most of the time",
    ),
    "response_time_variability": (
        "Speed of responding varied a lot between games",
        "Responded at a similar speed across the different games",
    ),
    "overall_accuracy": (
        "Tracing shapes was less accurate than expected for this age",
        "Traced shapes accurately",
    ),
    "avg_tremor_score": (
        "The drawing line was shaky, suggesting developing hand control",
        "The drawing line was steady",
    ),
    "drawing_speed": (
        "Drew very quickly, which can reduce accuracy",
        "Drew at a controlled speed",
    ),
    "gaze_efficiency": (
        "Eyes moved around the screen inefficiently while searching",
        "Looked directly at the relevant part of the screen",
    ),
    "off_screen_rate": (
        "Looked away from the screen often during play",
        "Kept eyes on the screen throughout play",
    ),
}

# Where to find a human-meaningful raw value for each feature in the original
# payload, so the explanation can quote "14 times" rather than "0.97".
#   feature -> (payload section, field)
_RAW_VALUE_PATHS: Dict[str, Tuple[str, str]] = {
    "bd_confusion_rate": ("letter_land", "bd_confusion_count"),
    "pq_confusion_rate": ("letter_land", "pq_confusion_count"),
    "letter_accuracy": ("letter_land", "accuracy"),
    "hesitation_avg_ms": ("letter_land", "hesitation_avg_ms"),
    "letter_response_time": ("letter_land", "avg_response_time_ms"),
    "number_accuracy": ("number_ninja", "accuracy"),
    "number_response_time": ("number_ninja", "avg_response_time_ms"),
    "impulsivity_score": ("butterfly_game", "impulsivity_score"),
    "performance_drop": ("butterfly_game", "performance_drop"),
    "butterfly_accuracy": ("butterfly_game", "accuracy"),
    "overall_accuracy": ("shape_tracer", "overall_accuracy"),
    "avg_tremor_score": ("shape_tracer", "avg_tremor_score"),
    "drawing_speed": ("shape_tracer", "avg_drawing_speed"),
    "gaze_efficiency": ("eye_tracking", "gaze_efficiency"),
    "off_screen_rate": ("eye_tracking", "off_screen_count"),
}

#: Friendly condition names for the summary sentences.
_CONDITION_LABELS: Dict[str, str] = {
    "dyslexia": "reading and letter recognition",
    "dyscalculia": "early number sense",
    "adhd": "attention and impulse control",
}


def _feature_map(features: Any, names: List[str]) -> Dict[str, float]:
    """Zip features and names, guarding against a length mismatch."""
    try:
        flat = np.asarray(features, dtype=np.float32).reshape(-1)
    except Exception:
        return {}
    result: Dict[str, float] = {}
    for index, name in enumerate(names or []):
        if index >= flat.shape[0]:
            break
        value = float(flat[index])
        if not np.isfinite(value):
            value = 0.0
        result[name] = float(min(1.0, max(0.0, value)))
    return result


def _describe(feature: str, oriented_value: float) -> str:
    """Pick the concern/strength sentence for a feature."""
    concern, strength = _DESCRIPTIONS.get(
        feature,
        ("This behaviour contributed to the score",
         "This behaviour did not raise any concern"),
    )
    return concern if oriented_value >= 0.5 else strength


def _raw_value(feature: str, normalised: float,
               payload: Optional[Dict[str, Any]]) -> float:
    """Find a human-meaningful value for a feature, else use the normalised one.

    Quoting "14 confusions" is far more useful to a parent than "0.97", so we
    reach back into the original payload when it is available.
    """
    if isinstance(payload, dict):
        path = _RAW_VALUE_PATHS.get(feature)
        if path is not None:
            section = payload.get(path[0])
            if isinstance(section, dict):
                value = section.get(path[1])
                if value is not None and not isinstance(value, bool):
                    try:
                        candidate = float(value)
                        if np.isfinite(candidate):
                            return round(candidate, 4)
                    except (TypeError, ValueError):
                        pass
    return round(float(normalised), 4)


def _analytic_contributions(condition: str,
                            feature_map: Dict[str, float]
                            ) -> Dict[str, float]:
    """Weight x risk-oriented value, normalised to shares of total evidence.

    For an additive weighted-sum scorer this *is* the Shapley attribution,
    computed in closed form.
    """
    weights = HEURISTIC_WEIGHTS.get(condition, {})
    contributions: Dict[str, float] = {}
    total = 0.0
    for name, spec in weights.items():
        if name not in feature_map:
            continue
        weight, higher_is_worse = spec
        oriented = directional_value(feature_map[name], higher_is_worse)
        amount = weight * oriented
        contributions[name] = amount
        total += amount

    if total <= 0.0:
        # No evidence at all: report the weights themselves so the parent
        # still sees which behaviours were examined.
        fallback_total = sum(w for w, _ in weights.values()) or 1.0
        return {name: (w / fallback_total)
                for name, (w, _) in weights.items()
                if name in feature_map}

    return {name: (amount / total) for name, amount in contributions.items()}


def _shap_contributions(condition: str, features: Any, names: List[str],
                        feature_map: Dict[str, float]
                        ) -> Optional[Dict[str, float]]:
    """Attribute with SHAP's KernelExplainer. Returns None on any failure."""
    if not SHAP_AVAILABLE:
        return None
    try:
        ordered = list(names)

        def score_batch(matrix: Any) -> Any:
            """Score a batch of feature vectors with the clinical heuristic."""
            batch = np.asarray(matrix, dtype=np.float64)
            if batch.ndim == 1:
                batch = batch.reshape(1, -1)
            outputs = []
            for row in batch:
                row_map = {name: float(row[i])
                           for i, name in enumerate(ordered)
                           if i < row.shape[0]}
                outputs.append(heuristic_score(condition, row_map)[0])
            return np.asarray(outputs, dtype=np.float64)

        # Background = an all-zero "no difficulty observed" reference child.
        # Attributions therefore read as "how far this child's behaviour
        # moved the score away from an unremarkable baseline".
        background = np.zeros((1, len(ordered)), dtype=np.float64)
        sample = np.asarray(
            [feature_map.get(name, 0.0) for name in ordered],
            dtype=np.float64,
        ).reshape(1, -1)

        explainer = shap.KernelExplainer(score_batch, background)
        values = explainer.shap_values(sample, nsamples=_SHAP_NSAMPLES,
                                       silent=True)
        array = np.asarray(values, dtype=np.float64).reshape(-1)
        if array.shape[0] < len(ordered):
            return None

        magnitudes = np.abs(array[:len(ordered)])
        total = float(np.sum(magnitudes))
        if not np.isfinite(total) or total <= 0.0:
            return None

        weights = HEURISTIC_WEIGHTS.get(condition, {})
        return {name: float(magnitudes[i] / total)
                for i, name in enumerate(ordered) if name in weights}
    except Exception as exc:
        logger.warning("SHAP explanation for %s failed (%s) -- falling back "
                       "to the analytic attribution.", condition, exc)
        return None


def _summary(condition: str, score: float,
             factors: List[Dict[str, Any]]) -> str:
    """Compose the parent-facing summary sentence for one condition.

    Deliberately non-diagnostic: describes what was observed and what it
    suggests doing next, never what the child "has".
    """
    label = _CONDITION_LABELS.get(condition, condition)
    level = risk_level(score)
    percent = int(round(float(score) * 100))

    if level == "High":
        opening = (
            "This session showed several patterns linked to difficulty with "
            "{label} ({percent}% indicator).".format(label=label,
                                                     percent=percent)
        )
        closing = (
            " We suggest sharing these results with your child's teacher or "
            "a learning specialist, who can decide whether a fuller "
            "assessment would help."
        )
    elif level == "Moderate":
        opening = (
            "This session showed some patterns linked to difficulty with "
            "{label} ({percent}% indicator).".format(label=label,
                                                     percent=percent)
        )
        closing = (
            " This is common at ages 4-5 and often improves with practice. "
            "Playing again in a few weeks will show whether the pattern "
            "persists."
        )
    else:
        opening = (
            "This session showed few patterns linked to difficulty with "
            "{label} ({percent}% indicator).".format(label=label,
                                                     percent=percent)
        )
        closing = (
            " No particular follow-up is suggested for this area right now."
        )

    if factors:
        drivers = "; ".join(
            str(factor.get("description", "")).rstrip(".")
            for factor in factors[:2]
            if factor.get("description")
        )
        if drivers:
            middle = " The main things we noticed: {0}.".format(drivers)
        else:
            middle = ""
    else:
        middle = ""

    return opening + middle + closing


def _explain_condition(condition: str, features: Any, names: List[str],
                       feature_map: Dict[str, float], score: float,
                       payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the ``{top_factors, summary}`` block for one condition."""
    contributions = _shap_contributions(condition, features, names,
                                        feature_map)
    method = "shap"
    if not contributions:
        contributions = _analytic_contributions(condition, feature_map)
        method = "analytic"

    ranked = sorted(contributions.items(), key=lambda item: item[1],
                    reverse=True)

    weights = HEURISTIC_WEIGHTS.get(condition, {})
    factors: List[Dict[str, Any]] = []
    for name, contribution in ranked[:MAX_FACTORS]:
        spec = weights.get(name)
        higher_is_worse = spec[1] if spec else True
        normalised = feature_map.get(name, 0.0)
        oriented = directional_value(normalised, higher_is_worse)
        factors.append({
            "feature": name,
            "value": _raw_value(name, normalised, payload),
            "contribution": round(float(contribution), 4),
            "description": _describe(name, oriented),
        })

    # The contract asks for 3-5 factors. If the weight table for this
    # condition is unusually small we simply return what exists rather than
    # inventing filler.
    if len(factors) < MIN_FACTORS:
        logger.debug("Only %d factors available for %s", len(factors),
                     condition)

    return {
        "top_factors": factors,
        "summary": _summary(condition, score, factors),
        "method": method,
    }


def explain(features: Any, names: List[str], scores: Dict[str, Any],
            payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Explain all three condition scores.

    Args:
        features: The feature vector used for the prediction.
        names: Matching feature names.
        scores: Either the full fusion result (with ``dyslexia_score`` etc.)
            or a plain ``{condition: score}`` mapping. Both are accepted.
        payload: Optional original telemetry, used to quote raw values such
            as "14 confusions" instead of the normalised 0-1 figure.

    Returns:
        ``{condition: {"top_factors": [...], "summary": "...",
        "method": "shap"|"analytic"}}`` for each of the three conditions.

    Never raises. If everything fails, returns a structurally valid
    explanation with empty factor lists so the response contract holds.
    """
    try:
        names = list(names or [])
        feature_map = _feature_map(features, names)
        score_map = _normalise_scores(scores)

        return {
            condition: _explain_condition(
                condition, features, names, feature_map,
                score_map.get(condition, 0.0), payload,
            )
            for condition in CONDITIONS
        }
    except Exception as exc:
        logger.error("explain() failed entirely: %s", exc, exc_info=True)
        return {
            condition: {
                "top_factors": [],
                "summary": (
                    "An explanation could not be generated for this session. "
                    "The screening indicator above is still valid."
                ),
                "method": "unavailable",
            }
            for condition in CONDITIONS
        }


def _normalise_scores(scores: Any) -> Dict[str, float]:
    """Accept either a fusion result dict or a plain condition->score map."""
    result: Dict[str, float] = {}
    if not isinstance(scores, dict):
        return {condition: 0.0 for condition in CONDITIONS}
    for condition in CONDITIONS:
        value = scores.get("{0}_score".format(condition))
        if value is None:
            value = scores.get(condition)
        try:
            number = float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            number = 0.0
        if not np.isfinite(number):
            number = 0.0
        result[condition] = float(min(1.0, max(0.0, number)))
    return result


__all__: List[str] = ["explain", "SHAP_AVAILABLE", "MAX_FACTORS"]
