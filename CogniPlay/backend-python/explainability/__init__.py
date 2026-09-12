"""Explainability package for the CogniPlay AI service.

Turns opaque scores into something a parent can actually read:

* :func:`~explainability.shap_explain.explain` -- top contributing factors
  per condition, with plain-English descriptions. Uses SHAP when installed,
  otherwise a transparent weight-times-value attribution.
* :func:`~explainability.gradcam.generate_heatmap` -- a base64 PNG attention
  heatmap. Encodes with OpenCV, else Pillow, else a 1x1 placeholder.

Neither function ever raises: an explanation failure must not cost the caller
their prediction.
"""

from typing import List

from .shap_explain import explain, SHAP_AVAILABLE
from .gradcam import generate_heatmap, CV2_AVAILABLE, PIL_AVAILABLE

__all__: List[str] = [
    "explain", "generate_heatmap", "SHAP_AVAILABLE", "CV2_AVAILABLE",
    "PIL_AVAILABLE",
]
