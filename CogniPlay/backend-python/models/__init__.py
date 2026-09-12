"""Model package for the CogniPlay AI service.

Exposes the three scoring components:

* :class:`~models.cnn_model.DyslexiaCNN` -- 1D CNN over the feature vector.
* :class:`~models.lstm_model.AttentionLSTM` -- LSTM over the attention
  time-series.
* :class:`~models.fusion_model.FusionModel` -- combines both with the
  deterministic clinical heuristics that are the source of truth whenever no
  trained checkpoint is present.

Every import here is safe without PyTorch: each module falls back to a
NumPy-only implementation of the same interface.
"""

from typing import List

from .cnn_model import DyslexiaCNN, TORCH_AVAILABLE, build_cnn
from .lstm_model import AttentionLSTM, build_lstm
from .fusion_model import (
    CONDITIONS,
    HEURISTIC_WEIGHTS,
    MODEL_VERSION,
    FusionModel,
    heuristic_score,
    heuristic_scores,
    risk_level,
)

__all__: List[str] = [
    "DyslexiaCNN", "build_cnn", "AttentionLSTM", "build_lstm",
    "FusionModel", "HEURISTIC_WEIGHTS", "CONDITIONS", "MODEL_VERSION",
    "risk_level", "heuristic_score", "heuristic_scores", "TORCH_AVAILABLE",
]
