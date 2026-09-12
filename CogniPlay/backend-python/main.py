"""
CogniPlay AI Service -- FastAPI application entry point.

Receives gameplay telemetry from the Node backend, runs the screening
pipeline, and returns the three indicators with explanations, a heatmap and
age-appropriate recommendations.

Pipeline for ``POST /predict-learning-pattern``::

    payload -> extract_features -> FusionModel.predict -> explain
            -> generate_heatmap -> recommendations -> response

Design commitments:

* **Never 422.** Every field of every Pydantic model is optional with a
  default, so a partial payload from a half-finished game is scored on what
  it has rather than rejected.
* **Never 500 on the prediction route.** Any internal failure returns a
  correctly shaped response with ``degraded_mode: true`` instead, because a
  demo that shows a fallback beats one that shows a stack trace.
* **Starts with four packages.** fastapi, uvicorn, numpy and pydantic are
  enough. torch, shap, opencv and reportlab are all optional; ``/health``
  reports exactly which ones are present.

**This service produces screening indicators, not diagnoses.** See the notice
at the top of ``models/fusion_model.py``.

Python 3.9 compatible: typing.Optional / typing.Dict / typing.List only.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from explainability.gradcam import (
    CV2_AVAILABLE, PIL_AVAILABLE, TRANSPARENT_PIXEL_PNG, generate_heatmap,
)
from explainability.shap_explain import SHAP_AVAILABLE, explain
from features.extract_features import build_sequence, extract_features
from models.fusion_model import (
    CONDITIONS, MODEL_VERSION, FusionModel, risk_level,
)
from models.cnn_model import TORCH_AVAILABLE
from report.pdf_generator import REPORTLAB_AVAILABLE, generate_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("cogniplay")

SERVICE_NAME: str = "CogniPlay AI Service"

ALLOWED_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://localhost:3001",
]

app = FastAPI(
    title=SERVICE_NAME,
    description=(
        "Play-based early screening indicators for ages 4-5. "
        "Screening tool only -- not a diagnostic instrument."
    ),
    version=MODEL_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Built once at import time and reused: constructing it scans saved_models/
# and (when torch is present) allocates the networks, neither of which should
# happen per request.
fusion_model = FusionModel()


# ---------------------------------------------------------------------------
# Request models
#
# EVERY field is Optional with a default. A child who quits after two games
# still gets scored on those two games; the pipeline treats absent sections as
# "no evidence" rather than as zeros.
# ---------------------------------------------------------------------------

try:  # pydantic v2
    from pydantic import model_validator

    def _pre_validator(func):
        """Register a whole-model pre-validator across pydantic 1 and 2."""
        return model_validator(mode="before")(classmethod(func))

except ImportError:  # pragma: no cover - pydantic v1
    from pydantic import root_validator

    def _pre_validator(func):
        return root_validator(pre=True, allow_reuse=True)(classmethod(func))


class _Permissive(BaseModel):
    """Base model that accepts and preserves unknown fields.

    The game client is expected to evolve faster than this service. Accepting
    extra keys means a frontend that starts sending a new metric does not
    break scoring for everyone else.

    It also *never rejects a payload*. A declared field carrying a value of the
    wrong type is reset to its default rather than raising, because a
    half-corrupt telemetry blob from a tablet that dropped its connection
    mid-game is still worth scoring on the fields that survived. Returning 422
    would discard a real child's entire ten-minute session over one bad number.
    """

    class Config:
        extra = "allow"

    @_pre_validator
    def _sanitise(cls, data: Any) -> Any:
        """Reset declared fields whose value cannot satisfy their type."""
        if not isinstance(data, dict):
            return data

        cleaned = dict(data)
        declared = getattr(cls, "model_fields", None) or getattr(
            cls, "__fields__", {}
        )

        for name in declared:
            if name not in cleaned:
                continue
            value = cleaned[name]
            if value is None or isinstance(value, (int, float, bool)):
                continue

            # Numbers arriving as numeric strings are a normal encoding quirk -
            # coerce those rather than throw the measurement away.
            if isinstance(value, str):
                try:
                    cleaned[name] = float(value)
                except (TypeError, ValueError):
                    cleaned[name] = None
                continue

            # A container is only legitimate where the field actually declares
            # one (a nested game model, or a list of error records) - that
            # nested model sanitises its own contents in turn. A list handed to
            # a scalar counter is not salvageable.
            if isinstance(value, (list, dict)):
                if not cls._expects_container(declared[name]):
                    cleaned[name] = None
                continue

            cleaned[name] = None

        return cleaned

    @staticmethod
    def _expects_container(field: Any) -> bool:
        """Whether a declared field can legitimately hold a list or a dict."""
        annotation = getattr(field, "annotation", None)
        if annotation is None:
            annotation = getattr(field, "outer_type_", None)
        text = str(annotation)
        return ("List" in text or "list" in text
                or "Dict" in text or "dict" in text
                or "Data" in text)  # nested *Data game models


class LetterLandData(_Permissive):
    """Letter Land telemetry -- letter recognition and reversal errors."""

    total_clicks: Optional[int] = 0
    correct_clicks: Optional[int] = 0
    wrong_clicks: Optional[int] = 0
    accuracy: Optional[float] = None
    avg_response_time_ms: Optional[float] = None
    letter_errors: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    bd_confusion_count: Optional[int] = 0
    pq_confusion_count: Optional[int] = 0
    hesitation_avg_ms: Optional[float] = None


class NumberNinjaData(_Permissive):
    """Number Ninja telemetry -- counting, subitizing and magnitude errors."""

    total_rounds: Optional[int] = 0
    correct_answers: Optional[int] = 0
    wrong_answers: Optional[int] = 0
    accuracy: Optional[float] = None
    avg_response_time_ms: Optional[float] = None
    number_errors: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    subitizing_accuracy_1_5: Optional[float] = None
    subitizing_accuracy_6_10: Optional[float] = None


class ButterflyGameData(_Permissive):
    """Butterfly Game telemetry -- impulsivity and sustained attention."""

    total_catches: Optional[int] = 0
    correct_catches: Optional[int] = 0
    wrong_catches: Optional[int] = 0
    accuracy: Optional[float] = None
    impulsivity_score: Optional[float] = None
    attention_by_interval: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list
    )
    performance_drop: Optional[float] = None
    avg_response_time_ms: Optional[float] = None


class ShapeTracerData(_Permissive):
    """Shape Tracer telemetry -- fine motor control."""

    shapes_completed: Optional[int] = 0
    circle_accuracy: Optional[float] = None
    square_accuracy: Optional[float] = None
    triangle_accuracy: Optional[float] = None
    overall_accuracy: Optional[float] = None
    avg_tremor_score: Optional[float] = None
    avg_drawing_speed: Optional[float] = None


class EyeTrackingData(_Permissive):
    """Optional webcam gaze metrics. ``available`` gates their use."""

    available: Optional[bool] = False
    total_fixations: Optional[int] = 0
    avg_fixation_duration_ms: Optional[float] = None
    off_screen_count: Optional[int] = 0
    gaze_efficiency: Optional[float] = None


class SessionPayload(_Permissive):
    """A complete gameplay session posted by the Node backend."""

    child_id: Optional[str] = None
    child_name: Optional[str] = None
    child_age: Optional[int] = None
    session_date: Optional[str] = None
    total_duration_ms: Optional[int] = None

    letter_land: Optional[LetterLandData] = None
    number_ninja: Optional[NumberNinjaData] = None
    butterfly_game: Optional[ButterflyGameData] = None
    shape_tracer: Optional[ShapeTracerData] = None
    eye_tracking: Optional[EyeTrackingData] = None


class ReportRequest(_Permissive):
    """Body of ``POST /generate-report``: the session plus its results."""

    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)
    results: Optional[Dict[str, Any]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_dict(model: Any) -> Dict[str, Any]:
    """Convert a Pydantic model to a plain dict, on either Pydantic v1 or v2.

    v2 renamed ``.dict()`` to ``.model_dump()``; supporting both keeps this
    service working whichever version pip resolves.
    """
    if model is None:
        return {}
    if isinstance(model, dict):
        return model
    for attribute in ("model_dump", "dict"):
        method = getattr(model, attribute, None)
        if callable(method):
            try:
                dumped = method()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                continue
    return {}


def build_recommendations(scores: Dict[str, float],
                          levels: Dict[str, str],
                          child_name: Optional[str] = None,
                          child_age: Optional[int] = None) -> List[str]:
    """Compose age-appropriate suggestions from the risk bands.

    Only conditions scoring Moderate or High generate targeted suggestions.
    A session where everything is Low gets encouragement plus the standard
    "play again in a few weeks" advice rather than manufactured concern.

    All suggestions are play-based activities a parent of a 4-5 year old can
    do at home in a few minutes. None of them are treatments, and none of
    them assume a diagnosis.
    """
    name = (child_name or "your child").strip() or "your child"
    recommendations: List[str] = []

    dyslexia_level = levels.get("dyslexia", "Low")
    dyscalculia_level = levels.get("dyscalculia", "Low")
    adhd_level = levels.get("adhd", "Low")
    flagged = [level for level in (dyslexia_level, dyscalculia_level,
                                   adhd_level) if level in ("Moderate", "High")]

    # --- Reading and letters ---------------------------------------------
    if dyslexia_level == "High":
        recommendations.append(
            "Practise the letters b, d, p and q one pair at a time. Trace them "
            "large in sand, foam or finger paint so {0} feels the direction "
            "as well as seeing it -- 5 minutes a day is plenty.".format(name)
        )
        recommendations.append(
            "Read aloud together daily and pause to point at single letters "
            "as you say them. Hearing and seeing a letter at the same moment "
            "helps the link form."
        )
        recommendations.append(
            "Share these results with {0}'s teacher. Early support for "
            "reading works best when it starts before formal reading "
            "instruction does.".format(name)
        )
    elif dyslexia_level == "Moderate":
        recommendations.append(
            "Play letter-matching games with the trickier pairs (b/d, p/q). "
            "Turning it into a game rather than a test keeps it low-pressure."
        )
        recommendations.append(
            "Keep a short daily story time and let {0} turn the pages and "
            "find one letter on each page.".format(name)
        )

    # --- Numbers ----------------------------------------------------------
    if dyscalculia_level == "High":
        recommendations.append(
            "Count real objects together every day -- steps on the stairs, "
            "grapes on a plate, buttons on a coat. Physical objects build "
            "number sense far better than screens do."
        )
        recommendations.append(
            "Practise recognising small groups instantly (dice patterns, "
            "fingers, dominoes) before moving to bigger numbers. Getting 1-5 "
            "solid first makes 6-10 much easier."
        )
        recommendations.append(
            "Mention the number results to {0}'s teacher so early maths "
            "support can be considered.".format(name)
        )
    elif dyscalculia_level == "Moderate":
        recommendations.append(
            "Use dice and domino games to practise seeing 'how many' at a "
            "glance, without counting one by one."
        )
        recommendations.append(
            "Bring numbers into everyday moments -- laying the table, sorting "
            "socks, counting out snacks."
        )

    # --- Attention --------------------------------------------------------
    if adhd_level == "High":
        recommendations.append(
            "Keep focused activities short (10-15 minutes) with movement "
            "breaks in between. At this age, attention grows in small steps."
        )
        recommendations.append(
            "Try 'stop and think' games such as Simon Says or red-light/"
            "green-light. They practise pausing before acting, which is what "
            "the game measured."
        )
        recommendations.append(
            "A predictable daily routine and a calm, low-clutter play space "
            "make focusing noticeably easier for many children."
        )
        recommendations.append(
            "If teachers are seeing the same pattern at school, it is worth "
            "raising with your GP or paediatrician."
        )
    elif adhd_level == "Moderate":
        recommendations.append(
            "Break activities into short chunks and praise {0} for finishing "
            "one before starting the next.".format(name)
        )
        recommendations.append(
            "Play turn-taking games that need waiting -- they build impulse "
            "control gently."
        )

    # --- Universal --------------------------------------------------------
    if not flagged:
        recommendations.append(
            "Nothing in this session stood out as a concern. Keep doing what "
            "you are doing -- daily reading, counting games and plenty of "
            "play are exactly right at this age."
        )
    try:
        age = int(child_age) if child_age is not None else None
    except (TypeError, ValueError):
        age = None
    if age is not None and age <= 4:
        recommendations.append(
            "At age {0}, many of these skills are only just beginning to "
            "develop, so treat this as a starting point rather than a "
            "result. Play again in 4-6 weeks -- changes over time tell you "
            "far more than any one score.".format(age)
        )
    else:
        recommendations.append(
            "Play again in 4-6 weeks. A single session is a snapshot; "
            "changes over time tell you far more than any one score."
        )
    recommendations.append(
        "Remember that this is a screening game, not a diagnosis. Only a "
        "qualified professional can assess a learning difficulty."
    )

    return recommendations


def _fallback_response(reason: str) -> Dict[str, Any]:
    """A correctly shaped response for when the pipeline could not run.

    Scores are 0.0 rather than invented, ``degraded_mode`` is true, and the
    explanation summaries say plainly that no assessment was produced. The
    frontend can render this without special-casing.
    """
    logger.error("Returning degraded response: %s", reason)
    message = (
        "We could not analyse this session. Please try playing the games "
        "again, or contact support if this keeps happening."
    )
    return {
        "dyslexia_score": 0.0,
        "dyscalculia_score": 0.0,
        "adhd_score": 0.0,
        "risk_levels": {condition: "Low" for condition in CONDITIONS},
        "explanation": {
            condition: {"top_factors": [], "summary": message}
            for condition in CONDITIONS
        },
        "heatmap": TRANSPARENT_PIXEL_PNG,
        "recommendations": [
            message,
            "No screening result was produced, so nothing here should be "
            "read as a finding about your child.",
        ],
        "model_version": MODEL_VERSION,
        "degraded_mode": True,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def root() -> Dict[str, Any]:
    """Service banner: what this is, what it offers, and what it is not."""
    return {
        "service": SERVICE_NAME,
        "version": MODEL_VERSION,
        "status": "running",
        "description": (
            "Play-based early learning screening for children aged 4-5, "
            "from gameplay telemetry."
        ),
        "conditions_screened": list(CONDITIONS),
        "endpoints": {
            "GET /": "This service information",
            "GET /health": "Health and optional-dependency status",
            "POST /predict-learning-pattern": "Score a gameplay session",
            "POST /generate-report": "Render the parent PDF report",
        },
        "disclaimer": (
            "This service produces screening indicators only. It is not a "
            "diagnostic tool and does not replace assessment by a qualified "
            "professional."
        ),
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    """Report service health and exactly which optional libraries are present.

    The frontend uses ``degraded_mode`` on predictions; this endpoint tells an
    operator *why* the service might be degraded, before any request is made.
    """
    return {
        "status": "healthy",
        "torch_available": TORCH_AVAILABLE,
        "shap_available": SHAP_AVAILABLE,
        "reportlab_available": REPORTLAB_AVAILABLE,
        "cv2_available": CV2_AVAILABLE,
        "pillow_available": PIL_AVAILABLE,
        "trained_weights_loaded": fusion_model.uses_trained_weights,
        "scoring_path": (
            "blended" if fusion_model.uses_trained_weights else "heuristic"
        ),
        "model_version": MODEL_VERSION,
    }


# --- Data sufficiency ------------------------------------------------------

#: Which game each condition's score is actually derived from. If that game
#: produced no data, the condition cannot be scored - and must not be reported
#: as though it were.
CONDITION_SOURCE_GAME = {
    "dyslexia": "letter_land",
    "dyscalculia": "number_ninja",
    "adhd": "butterfly_game",
}

#: A game object needs at least one of these keys to count as "played".
_EVIDENCE_KEYS = (
    "total_clicks", "total_rounds", "total_catches", "shapes_completed",
)


def _played(game: Any) -> bool:
    """True when a game block carries real gameplay evidence.

    An absent game and a game whose counters are all zero are treated the
    same: no evidence. This is the difference between "we saw nothing" and
    "we saw poor performance", and conflating the two is how a screening tool
    ends up flagging a child who simply never played that round.
    """
    if not isinstance(game, dict) or not game:
        return False
    for key in _EVIDENCE_KEYS:
        try:
            if float(game.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def unscoreable_conditions(payload: Dict[str, Any]) -> List[str]:
    """Conditions whose source game produced no usable data."""
    missing = []
    for condition, game_key in CONDITION_SOURCE_GAME.items():
        if not _played(payload.get(game_key)):
            missing.append(condition)
    return missing


def _mark_unscoreable(condition, scores, levels, explanation):
    """Neutralise one condition that has no evidence behind it.

    The score is zeroed and the level set to "Low" so the contract still holds
    for every consumer, but the explanation says plainly that this is absence
    of data rather than absence of risk.
    """
    scores[condition] = 0.0
    levels[condition] = "Low"
    explanation[condition] = {
        "top_factors": [],
        "summary": (
            "Not enough gameplay data to score this area - the matching game "
            "was not completed. This is not a low-risk result; it means we "
            "have nothing to judge. Play the full session to get a score."
        ),
        "insufficient_data": True,
    }


@app.post("/predict-learning-pattern")
def predict_learning_pattern(session: SessionPayload) -> Dict[str, Any]:
    """Score one gameplay session.

    Returns the full contract: three scores, three risk levels, per-condition
    explanations, a base64 heatmap, recommendations, the model version, and
    a ``degraded_mode`` flag.

    Each stage is individually guarded. A failure in the *optional* stages
    (heatmap, explanation) sets ``degraded_mode`` but still returns real
    scores; a failure in the core scoring returns the neutral fallback. This
    endpoint does not raise HTTP 500.
    """
    degraded = False

    try:
        payload = _to_dict(session)
    except Exception as exc:
        return _fallback_response("payload conversion failed: {0}".format(exc))

    child_name = payload.get("child_name")
    child_age = payload.get("child_age")
    logger.info("Scoring session for child_id=%s age=%s",
                payload.get("child_id"), child_age)

    # --- Core scoring (must succeed) --------------------------------------
    try:
        features, names = extract_features(payload)
        sequence = build_sequence(payload)
        prediction = fusion_model.predict(features, names, sequence)
        if prediction.get("used_path") == "error":
            degraded = True
    except Exception as exc:
        return _fallback_response("scoring failed: {0}".format(exc))

    scores = {
        condition: float(prediction.get("{0}_score".format(condition), 0.0))
        for condition in CONDITIONS
    }
    levels = prediction.get("risk_levels") or {
        condition: risk_level(scores[condition]) for condition in CONDITIONS
    }

    # --- Explanation (optional) -------------------------------------------
    try:
        explanation = explain(features, names, prediction, payload)
    except Exception as exc:
        logger.error("Explanation stage failed: %s", exc, exc_info=True)
        degraded = True
        explanation = {
            condition: {
                "top_factors": [],
                "summary": ("An explanation could not be generated for this "
                            "session. The score above is still valid."),
            }
            for condition in CONDITIONS
        }

    # --- Data sufficiency gate --------------------------------------------
    # Missing data must never read as impairment. A child who skipped Number
    # Ninja has no dyscalculia evidence at all - reporting a mid-range score
    # there would be an invented finding.
    insufficient = unscoreable_conditions(payload)
    for condition in insufficient:
        _mark_unscoreable(condition, scores, levels, explanation)
    if insufficient:
        logger.info("Insufficient data, conditions neutralised: %s",
                    ", ".join(insufficient))

    # --- Heatmap (optional) -----------------------------------------------
    try:
        heatmap = generate_heatmap(payload)
    except Exception as exc:
        logger.error("Heatmap stage failed: %s", exc, exc_info=True)
        degraded = True
        heatmap = TRANSPARENT_PIXEL_PNG

    # --- Recommendations (optional) ---------------------------------------
    try:
        recommendations = build_recommendations(scores, levels, child_name,
                                                child_age)
    except Exception as exc:
        logger.error("Recommendation stage failed: %s", exc, exc_info=True)
        degraded = True
        recommendations = [
            "Play again in 4-6 weeks to see how these skills develop.",
            "This is a screening game, not a diagnosis.",
        ]

    return {
        "dyslexia_score": scores["dyslexia"],
        "dyscalculia_score": scores["dyscalculia"],
        "adhd_score": scores["adhd"],
        "risk_levels": levels,
        "explanation": explanation,
        "heatmap": heatmap,
        "recommendations": recommendations,
        "model_version": MODEL_VERSION,
        "degraded_mode": degraded,
        "insufficient_data": insufficient,
    }


@app.post("/generate-report")
def generate_pdf_report(request: ReportRequest) -> StreamingResponse:
    """Render the parent-facing PDF for a session and its results.

    Accepts ``{"payload": {...}, "results": {...}}``. If ``results`` is
    missing, the session is re-scored here so a caller can request a report
    with the session alone.

    Returns a ``StreamingResponse`` of ``application/pdf``. Never raises: the
    PDF generator falls back to a stdlib writer, so a response always has a
    valid document body.
    """
    import io

    body = _to_dict(request)
    payload = body.get("payload") or {}
    results = body.get("results") or {}

    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(results, dict):
        results = {}

    # Re-score when the caller sent only the session.
    if not results:
        try:
            logger.info("No results supplied to /generate-report -- rescoring.")
            results = predict_learning_pattern(SessionPayload(**payload))
        except Exception as exc:
            logger.error("Rescoring for the report failed: %s", exc)
            results = _fallback_response("rescore failed")

    pdf_bytes = generate_report(payload, results)

    raw_name = str(payload.get("child_name") or "child").strip() or "child"
    safe_name = "".join(
        char if (char.isalnum() or char in "-_") else "_" for char in raw_name
    ).strip("_") or "child"
    filename = "cogniplay_report_{0}.pdf".format(safe_name.lower())

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="{0}"'.format(
                filename
            ),
            "Content-Length": str(len(pdf_bytes)),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
