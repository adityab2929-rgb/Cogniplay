"""Feature engineering package for the CogniPlay AI service.

Converts raw gameplay telemetry into the fixed-length, fixed-order feature
vector shared by every model, plus the ``(T, F)`` attention sequence used by
the LSTM. Pure NumPy -- no heavy dependencies.
"""

from typing import List

from .extract_features import (
    FEATURE_NAMES,
    N_FEATURES,
    SEQUENCE_FEATURES,
    SEQUENCE_LENGTH,
    build_sequence,
    extract_features,
    features_to_dict,
)

__all__: List[str] = [
    "extract_features", "build_sequence", "features_to_dict",
    "FEATURE_NAMES", "N_FEATURES", "SEQUENCE_LENGTH", "SEQUENCE_FEATURES",
]
