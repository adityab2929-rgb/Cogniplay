"""
Feature extraction for CogniPlay.

Turns the raw gameplay telemetry payload posted by the Node backend into a
fixed-length, fixed-order numeric feature vector that every downstream model
(CNN, LSTM, fusion heuristics, SHAP explainer) agrees on.

Design rules followed throughout this module:

* **Fixed length / fixed order.** ``FEATURE_NAMES`` is the single source of
  truth. The vector returned by :func:`extract_features` always has exactly
  ``len(FEATURE_NAMES)`` entries in exactly that order, even when the payload
  is empty. Models index into it positionally, so the order must never change
  without retraining.
* **Everything normalised to [0, 1].** Raw milliseconds and pixel speeds are
  squashed through :func:`_normalise_range` using developmentally sensible
  bounds for 4-5 year olds. This keeps the CNN inputs on one scale and makes
  the heuristic weights in ``fusion_model`` directly comparable.
* **Higher value == more evidence of difficulty**, except for the four
  "ability" features (letter_accuracy, number_accuracy, butterfly_accuracy,
  overall_accuracy, gaze_efficiency) which are kept in their natural direction
  because they read more clearly that way in the explanation text. The fusion
  model inverts them explicitly where needed.
* **Never raise.** Every division is guarded, every list access is guarded,
  and any missing/None/malformed section falls back to a neutral default.

Python 3.9 compatible: typing.Optional / typing.Dict / typing.List only, no
PEP 604 unions and no builtin generics.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Canonical feature order. DO NOT REORDER.
# ---------------------------------------------------------------------------

FEATURE_NAMES: List[str] = [
    # --- Dyslexia domain (Letter Land) ---
    "bd_confusion_rate",
    "pq_confusion_rate",
    "letter_accuracy",
    "hesitation_avg_ms",
    "letter_response_time",
    "reversal_error_ratio",
    # --- Dyscalculia domain (Number Ninja) ---
    "number_accuracy",
    "subitizing_gap",
    "number_response_time",
    "magnitude_error_avg",
    # --- ADHD domain (Butterfly Game) ---
    "impulsivity_score",
    "performance_drop",
    "attention_variance",
    "butterfly_accuracy",
    "response_time_variability",
    # --- Motor / gaze domain (Shape Tracer + eye tracking) ---
    "overall_accuracy",
    "avg_tremor_score",
    "drawing_speed",
    "gaze_efficiency",
    "off_screen_rate",
]

N_FEATURES: int = len(FEATURE_NAMES)

# Length of the LSTM time-series window (attention intervals).
SEQUENCE_LENGTH: int = 6
# Per-timestep feature width of that sequence.
SEQUENCE_FEATURES: int = 4

# Developmental normalisation bounds for ages 4-5. These are demo-time
# heuristics chosen to spread typical values across the [0, 1] range, not
# clinically validated norms.
_RESPONSE_TIME_MIN_MS: float = 500.0
_RESPONSE_TIME_MAX_MS: float = 6000.0
_HESITATION_MIN_MS: float = 0.0
_HESITATION_MAX_MS: float = 3000.0
_DRAWING_SPEED_MIN: float = 0.0
_DRAWING_SPEED_MAX: float = 400.0
_RT_VARIABILITY_MAX_MS: float = 2000.0
_MAGNITUDE_ERROR_MAX: float = 10.0
_REVERSAL_SATURATION_RATE: float = 0.10


# ---------------------------------------------------------------------------
# Small safe-math helpers
# ---------------------------------------------------------------------------

def _clamp01(value: float) -> float:
    """Clamp a float into [0.0, 1.0], mapping NaN/inf to 0.0."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(v):
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _safe_div(numerator: Any, denominator: Any, default: float = 0.0) -> float:
    """Divide, returning ``default`` when the denominator is zero/invalid."""
    try:
        n = float(numerator)
        d = float(denominator)
    except (TypeError, ValueError):
        return default
    if d == 0.0 or not np.isfinite(d) or not np.isfinite(n):
        return default
    return n / d


def _normalise_range(value: Any, low: float, high: float,
                     default: float = 0.0) -> float:
    """Linearly map ``value`` from [low, high] onto [0, 1] and clamp.

    Used for millisecond and pixel-speed quantities so they sit on the same
    scale as the accuracy/rate features.
    """
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(v):
        return default
    span = high - low
    if span == 0.0:
        return default
    return _clamp01((v - low) / span)


def _as_dict(payload: Any, key: str) -> Dict[str, Any]:
    """Fetch ``payload[key]`` as a dict, tolerating None/missing/wrong type."""
    if not isinstance(payload, dict):
        return {}
    section = payload.get(key)
    if isinstance(section, dict):
        return section
    # Pydantic models expose .dict()/.model_dump(); support both defensively.
    for attr in ("model_dump", "dict"):
        method = getattr(section, attr, None)
        if callable(method):
            try:
                dumped = method()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass
    return {}


def _as_list(section: Dict[str, Any], key: str) -> List[Any]:
    """Fetch ``section[key]`` as a list, tolerating None/missing/wrong type."""
    value = section.get(key) if isinstance(section, dict) else None
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _num(section: Dict[str, Any], key: str,
         default: Optional[float] = None) -> Optional[float]:
    """Fetch a numeric field, returning ``default`` when absent or unusable."""
    if not isinstance(section, dict):
        return default
    value = section.get(key)
    if value is None or isinstance(value, bool):
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(v):
        return default
    return v


def _entry_num(entry: Any, keys: Tuple[str, ...]) -> Optional[float]:
    """Pull the first numeric value found under any of ``keys`` in a dict."""
    if not isinstance(entry, dict):
        return None
    for key in keys:
        if key in entry:
            value = entry.get(key)
            if value is None or isinstance(value, bool):
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(v):
                return v
    return None


# ---------------------------------------------------------------------------
# Per-domain extraction
# ---------------------------------------------------------------------------

def _dyslexia_features(payload: Dict[str, Any]) -> List[float]:
    """Letter Land features: letter reversals, accuracy, hesitation, speed.

    b/d and p/q reversals are the classic behavioural marker screened for in
    early literacy. We express them as a *rate over total clicks* rather than
    a raw count so that a child who simply played longer is not penalised.
    """
    game = _as_dict(payload, "letter_land")

    total_clicks = _num(game, "total_clicks", 0.0) or 0.0
    wrong_clicks = _num(game, "wrong_clicks", 0.0) or 0.0
    correct_clicks = _num(game, "correct_clicks", 0.0) or 0.0
    bd_count = _num(game, "bd_confusion_count", 0.0) or 0.0
    pq_count = _num(game, "pq_confusion_count", 0.0) or 0.0

    # Reversal rates, scaled up because even a modest rate is meaningful.
    # Confusing b/d on 10% of all clicks is already a strong marker at this
    # age, so that is where the indicator saturates.
    bd_rate = _clamp01(_safe_div(bd_count, total_clicks, 0.0)
                       / _REVERSAL_SATURATION_RATE)
    pq_rate = _clamp01(_safe_div(pq_count, total_clicks, 0.0)
                       / _REVERSAL_SATURATION_RATE)

    # Accuracy: prefer the reported value, else recompute from raw counts.
    reported_accuracy = _num(game, "accuracy")
    if reported_accuracy is None:
        reported_accuracy = _safe_div(correct_clicks, total_clicks, 0.0)
    letter_accuracy = _clamp01(reported_accuracy)

    hesitation = _normalise_range(
        _num(game, "hesitation_avg_ms"),
        _HESITATION_MIN_MS, _HESITATION_MAX_MS, 0.0,
    )
    response_time = _normalise_range(
        _num(game, "avg_response_time_ms"),
        _RESPONSE_TIME_MIN_MS, _RESPONSE_TIME_MAX_MS, 0.0,
    )

    # What share of this child's mistakes were *reversals* specifically?
    # A high ratio points at orthographic confusion rather than inattention.
    reversal_total = bd_count + pq_count
    if wrong_clicks > 0:
        reversal_ratio = _clamp01(_safe_div(reversal_total, wrong_clicks, 0.0))
    else:
        # No wrong clicks recorded: fall back to the letter_errors list.
        letter_errors = _as_list(game, "letter_errors")
        reversal_hits = 0
        reversal_pairs = (("b", "d"), ("d", "b"), ("p", "q"), ("q", "p"))
        for entry in letter_errors:
            if not isinstance(entry, dict):
                continue
            shown = str(entry.get("shown", "")).strip().lower()
            clicked = str(entry.get("clicked", "")).strip().lower()
            if (shown, clicked) in reversal_pairs:
                reversal_hits += 1
        reversal_ratio = _clamp01(
            _safe_div(reversal_hits, len(letter_errors), 0.0)
        )

    return [bd_rate, pq_rate, letter_accuracy, hesitation, response_time,
            reversal_ratio]


def _dyscalculia_features(payload: Dict[str, Any]) -> List[float]:
    """Number Ninja features: accuracy, subitizing gap, speed, error magnitude.

    The *subitizing gap* is the headline feature. Typically developing 4-5
    year olds subitize small sets (1-5) near-instantly; a large drop-off for
    6-10 while 1-5 stays intact is a recognised numerosity-processing marker.
    """
    game = _as_dict(payload, "number_ninja")

    total_rounds = _num(game, "total_rounds", 0.0) or 0.0
    correct = _num(game, "correct_answers", 0.0) or 0.0

    reported_accuracy = _num(game, "accuracy")
    if reported_accuracy is None:
        reported_accuracy = _safe_div(correct, total_rounds, 0.0)
    number_accuracy = _clamp01(reported_accuracy)

    small_set = _num(game, "subitizing_accuracy_1_5")
    large_set = _num(game, "subitizing_accuracy_6_10")
    if small_set is None or large_set is None:
        subitizing_gap = 0.0
    else:
        # Only a *drop* from small to large sets counts; a negative gap
        # (better on large sets) is noise, not evidence.
        subitizing_gap = _clamp01(_clamp01(small_set) - _clamp01(large_set))

    response_time = _normalise_range(
        _num(game, "avg_response_time_ms"),
        _RESPONSE_TIME_MIN_MS, _RESPONSE_TIME_MAX_MS, 0.0,
    )

    # Mean absolute distance between the correct quantity and the answer
    # given. Being off by 1 is a near-miss; being off by 6 suggests the
    # child is not mapping symbols onto quantities at all.
    number_errors = _as_list(game, "number_errors")
    distances: List[float] = []
    for entry in number_errors:
        shown = _entry_num(entry, ("shown", "correct", "expected", "target"))
        answered = _entry_num(
            entry, ("answered", "clicked", "selected", "response", "given")
        )
        if shown is None or answered is None:
            continue
        distances.append(abs(shown - answered))
    if distances:
        magnitude_error = _clamp01(
            (sum(distances) / len(distances)) / _MAGNITUDE_ERROR_MAX
        )
    else:
        magnitude_error = 0.0

    return [number_accuracy, subitizing_gap, response_time, magnitude_error]


def _adhd_features(payload: Dict[str, Any]) -> List[float]:
    """Butterfly Game features: impulsivity, sustained-attention decline.

    ``attention_variance`` captures *inconsistency* across the session, which
    distinguishes attention-regulation difficulty from a child who is simply
    uniformly slower. Variance of values bounded in [0, 1] maxes out at 0.25,
    so we rescale by 4 to use the full indicator range.
    """
    game = _as_dict(payload, "butterfly_game")

    total_catches = _num(game, "total_catches", 0.0) or 0.0
    correct_catches = _num(game, "correct_catches", 0.0) or 0.0
    wrong_catches = _num(game, "wrong_catches", 0.0) or 0.0

    # Impulsivity: prefer the reported score, else derive it as the share of
    # catches that were false alarms (grabbing the wrong target).
    impulsivity = _num(game, "impulsivity_score")
    if impulsivity is None:
        impulsivity = _safe_div(wrong_catches, total_catches, 0.0)
    impulsivity = _clamp01(impulsivity)

    performance_drop = _clamp01(_num(game, "performance_drop", 0.0) or 0.0)

    intervals = _as_list(game, "attention_by_interval")
    scores: List[float] = []
    for entry in intervals:
        score = _entry_num(entry, ("score", "accuracy"))
        if score is None:
            correct = _entry_num(entry, ("correct",))
            wrong = _entry_num(entry, ("wrong", "incorrect"))
            if correct is None and wrong is None:
                continue
            correct = correct or 0.0
            wrong = wrong or 0.0
            score = _safe_div(correct, correct + wrong, 0.0)
        scores.append(_clamp01(score))
    if len(scores) >= 2:
        attention_variance = _clamp01(float(np.var(np.asarray(scores))) * 4.0)
    else:
        attention_variance = 0.0

    reported_accuracy = _num(game, "accuracy")
    if reported_accuracy is None:
        reported_accuracy = _safe_div(correct_catches, total_catches, 0.0)
    butterfly_accuracy = _clamp01(reported_accuracy)

    # Response-time variability across the three timed games. Erratic pacing
    # between tasks is a softer attention signal than within-task variance,
    # but it is the best proxy available from this payload.
    times: List[float] = []
    for section_name in ("letter_land", "number_ninja", "butterfly_game"):
        value = _num(_as_dict(payload, section_name), "avg_response_time_ms")
        if value is not None and value > 0:
            times.append(value)
    if len(times) >= 2:
        rt_variability = _clamp01(
            float(np.std(np.asarray(times))) / _RT_VARIABILITY_MAX_MS
        )
    else:
        rt_variability = 0.0

    return [impulsivity, performance_drop, attention_variance,
            butterfly_accuracy, rt_variability]


def _motor_gaze_features(payload: Dict[str, Any]) -> List[float]:
    """Shape Tracer + eye-tracking features: fine motor control and gaze.

    These are *supporting* signals. Tremor and poor tracing accuracy co-occur
    with dysgraphia and with dyslexia; frequent off-screen gaze co-occurs with
    inattention. They are weighted lightly in the fusion model because they
    are the least specific of the four domains.
    """
    shapes = _as_dict(payload, "shape_tracer")
    gaze = _as_dict(payload, "eye_tracking")

    overall = _num(shapes, "overall_accuracy")
    if overall is None:
        # Fall back to the mean of whichever per-shape accuracies exist.
        per_shape: List[float] = []
        for key in ("circle_accuracy", "square_accuracy", "triangle_accuracy"):
            value = _num(shapes, key)
            if value is not None:
                per_shape.append(_clamp01(value))
        overall = (sum(per_shape) / len(per_shape)) if per_shape else 0.0
    overall_accuracy = _clamp01(overall)

    tremor = _clamp01(_num(shapes, "avg_tremor_score", 0.0) or 0.0)
    drawing_speed = _normalise_range(
        _num(shapes, "avg_drawing_speed"),
        _DRAWING_SPEED_MIN, _DRAWING_SPEED_MAX, 0.0,
    )

    # Eye tracking is optional hardware; when it is unavailable we emit
    # neutral values rather than zeros so the absence of a camera does not
    # read as "perfectly attentive" or as "severely inattentive".
    available = gaze.get("available") if isinstance(gaze, dict) else None
    if not gaze or available is False:
        return [overall_accuracy, tremor, drawing_speed, 0.5, 0.0]

    gaze_efficiency = _clamp01(_num(gaze, "gaze_efficiency", 0.5) or 0.5)

    off_screen = _num(gaze, "off_screen_count", 0.0) or 0.0
    fixations = _num(gaze, "total_fixations", 0.0) or 0.0
    if fixations > 0:
        # Scaled so that looking away on 15% of fixations saturates.
        off_screen_rate = _clamp01(
            _safe_div(off_screen, fixations, 0.0) / 0.15
        )
    else:
        off_screen_rate = 0.0

    return [overall_accuracy, tremor, drawing_speed, gaze_efficiency,
            off_screen_rate]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_features(payload: Dict[str, Any]) -> Tuple[np.ndarray, List[str]]:
    """Build the fixed-length feature vector from a raw telemetry payload.

    Args:
        payload: The decoded ``/predict-learning-pattern`` request body. May
            be partial, may contain ``None`` sections, may be an empty dict.

    Returns:
        ``(features, names)`` where ``features`` is a float32 array of shape
        ``(N_FEATURES,)`` with every entry in [0, 1], and ``names`` is the
        matching list of feature names in the same order.

    This function never raises. A completely empty payload yields an
    all-neutral vector, which the fusion model scores as low risk across the
    board -- the correct behaviour when there is no evidence either way.
    """
    if not isinstance(payload, dict):
        payload = {}

    values: List[float] = []
    values.extend(_dyslexia_features(payload))
    values.extend(_dyscalculia_features(payload))
    values.extend(_adhd_features(payload))
    values.extend(_motor_gaze_features(payload))

    # Guard the contract: pad or truncate to the declared width so a future
    # edit to one domain helper can never desync the vector from its names.
    if len(values) < N_FEATURES:
        values.extend([0.0] * (N_FEATURES - len(values)))
    elif len(values) > N_FEATURES:
        values = values[:N_FEATURES]

    features = np.asarray([_clamp01(v) for v in values], dtype=np.float32)
    return features, list(FEATURE_NAMES)


def build_sequence(payload: Dict[str, Any]) -> np.ndarray:
    """Build the ``(T, F)`` attention time-series for the LSTM.

    Each timestep summarises one interval of the Butterfly Game:

    ==== ===========================================================
    idx  meaning
    ==== ===========================================================
    0    interval score (accuracy in that window)
    1    correct catches in the window, normalised by the busiest window
    2    wrong catches in the window, normalised by the busiest window
    3    signed change in score versus the previous window, mapped to
         [0, 1] with 0.5 == no change (the decline signal)
    ==== ===========================================================

    Intervals are padded (by repeating the last observed timestep, so the
    model sees a plateau rather than an artificial crash to zero) or
    truncated to ``SEQUENCE_LENGTH``.

    Returns:
        float32 array of shape ``(SEQUENCE_LENGTH, SEQUENCE_FEATURES)``.
        All-neutral (0.5 score, 0.5 delta) when no intervals are present.
    """
    if not isinstance(payload, dict):
        payload = {}

    game = _as_dict(payload, "butterfly_game")
    intervals = _as_list(game, "attention_by_interval")

    parsed: List[Tuple[float, float, float]] = []
    for entry in intervals:
        correct = _entry_num(entry, ("correct",)) or 0.0
        wrong = _entry_num(entry, ("wrong", "incorrect")) or 0.0
        score = _entry_num(entry, ("score", "accuracy"))
        if score is None:
            score = _safe_div(correct, correct + wrong, 0.0)
        parsed.append((_clamp01(score), max(correct, 0.0), max(wrong, 0.0)))

    if not parsed:
        neutral = np.zeros((SEQUENCE_LENGTH, SEQUENCE_FEATURES),
                           dtype=np.float32)
        neutral[:, 0] = 0.5  # neutral score
        neutral[:, 3] = 0.5  # neutral (no) change
        return neutral

    # Normalise counts against the busiest interval so the model reads the
    # *shape* of engagement over time, not the absolute volume.
    max_correct = max(p[1] for p in parsed)
    max_wrong = max(p[2] for p in parsed)

    rows: List[List[float]] = []
    previous_score: Optional[float] = None
    for score, correct, wrong in parsed:
        correct_norm = _clamp01(_safe_div(correct, max_correct, 0.0))
        wrong_norm = _clamp01(_safe_div(wrong, max_wrong, 0.0))
        if previous_score is None:
            delta = 0.5
        else:
            # Map a change of [-1, +1] onto [0, 1]; below 0.5 == declining.
            delta = _clamp01(0.5 + (score - previous_score) / 2.0)
        rows.append([score, correct_norm, wrong_norm, delta])
        previous_score = score

    if len(rows) > SEQUENCE_LENGTH:
        rows = rows[:SEQUENCE_LENGTH]
    while len(rows) < SEQUENCE_LENGTH:
        rows.append(list(rows[-1]))

    return np.asarray(rows, dtype=np.float32)


def features_to_dict(features: np.ndarray,
                     names: Optional[List[str]] = None) -> Dict[str, float]:
    """Zip a feature vector back into a name -> value mapping.

    Convenience for the explainer and for logging; guards against a mismatch
    in length by zipping only the overlapping prefix.
    """
    if names is None:
        names = list(FEATURE_NAMES)
    try:
        flat = np.asarray(features, dtype=np.float32).reshape(-1)
    except Exception:
        return {}
    return {name: float(flat[i]) for i, name in enumerate(names)
            if i < flat.shape[0]}
