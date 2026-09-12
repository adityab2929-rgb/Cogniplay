"""
DyslexiaCNN -- a 1D convolutional scorer over the CogniPlay feature vector.

Two implementations of the same public interface are defined here, and which
one you get depends on whether PyTorch is installed:

* **torch available** -- ``DyslexiaCNN`` is a real ``nn.Module``:
  ``Conv1d -> ReLU -> Conv1d -> ReLU -> AdaptiveMaxPool -> FC -> ReLU ->
  FC -> sigmoid``. Trained weights can be loaded from ``saved_models/``.
* **torch missing** -- ``DyslexiaCNN`` is a pure-NumPy class exposing the
  identical ``predict`` / ``load_weights`` / ``is_trained`` interface, so the
  service starts and returns correctly shaped predictions with nothing but
  numpy installed.

**Honesty note.** With no checkpoint in ``saved_models/`` the torch path is
*randomly initialised* and its output is meaningless. ``FusionModel`` checks
``is_trained`` and ignores an untrained network entirely, falling back to the
clinical heuristics. The NumPy path is not a trained network either: it is a
deterministic, hand-weighted transparent approximation, documented below.

Python 3.9 compatible: typing.Optional / typing.List only.
"""

import logging
import os
from typing import Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:  # pragma: no cover - depends on the deployment environment
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    TORCH_AVAILABLE = False
    logger.warning(
        "PyTorch not installed -- DyslexiaCNN will use the NumPy fallback."
    )

# Input width, kept in sync with features.extract_features.FEATURE_NAMES.
INPUT_FEATURES: int = 20

# Indices into the feature vector that carry dyslexia signal, with the sign
# of their contribution. Used only by the NumPy fallback readout.
#   index : (weight, higher_is_worse)
_DYSLEXIA_READOUT = (
    (0, 0.28, True),   # bd_confusion_rate
    (1, 0.18, True),   # pq_confusion_rate
    (2, 0.24, False),  # letter_accuracy  (higher accuracy -> lower risk)
    (3, 0.12, True),   # hesitation_avg_ms
    (4, 0.08, True),   # letter_response_time
    (5, 0.10, True),   # reversal_error_ratio
)


def _sigmoid(x: float) -> float:
    """Numerically stable logistic function."""
    if x >= 0:
        return float(1.0 / (1.0 + np.exp(-x)))
    exp_x = np.exp(x)
    return float(exp_x / (1.0 + exp_x))


def _prepare_vector(x: Any) -> np.ndarray:
    """Coerce arbitrary input into a 1D float32 vector of ``INPUT_FEATURES``.

    Pads with zeros or truncates so a caller passing a short vector can never
    trigger an index error deep inside the model.
    """
    try:
        vector = np.asarray(x, dtype=np.float32).reshape(-1)
    except Exception:
        vector = np.zeros(INPUT_FEATURES, dtype=np.float32)
    if vector.shape[0] < INPUT_FEATURES:
        vector = np.pad(vector, (0, INPUT_FEATURES - vector.shape[0]))
    elif vector.shape[0] > INPUT_FEATURES:
        vector = vector[:INPUT_FEATURES]
    return np.nan_to_num(vector, nan=0.0, posinf=1.0, neginf=0.0)


if TORCH_AVAILABLE:

    class DyslexiaCNN(nn.Module):  # type: ignore[misc]
        """1D CNN over the feature vector, producing a dyslexia score.

        The feature vector is treated as a length-20 single-channel signal.
        Convolution lets the network pick up on *groups* of adjacent
        features -- the vector is deliberately ordered by domain, so a kernel
        spanning positions 0-5 sees the whole dyslexia block at once.
        """

        def __init__(self, input_features: int = INPUT_FEATURES) -> None:
            super().__init__()
            self.input_features = input_features
            self.conv1 = nn.Conv1d(1, 16, kernel_size=3, padding=1)
            self.conv2 = nn.Conv1d(16, 32, kernel_size=3, padding=1)
            self.relu = nn.ReLU()
            self.pool = nn.AdaptiveMaxPool1d(4)
            self.dropout = nn.Dropout(0.2)
            self.fc1 = nn.Linear(32 * 4, 32)
            self.fc2 = nn.Linear(32, 1)
            self.sigmoid = nn.Sigmoid()

            self._trained = False
            self.backend = "torch"

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            """Run the network. Input ``(batch, 1, input_features)``."""
            x = self.relu(self.conv1(x))
            x = self.relu(self.conv2(x))
            x = self.pool(x)
            x = x.flatten(start_dim=1)
            x = self.dropout(self.relu(self.fc1(x)))
            return self.sigmoid(self.fc2(x))

        def predict(self, x: Any) -> float:
            """Score one feature vector, returning a float in [0, 1].

            Never raises: any torch-level failure degrades to a neutral 0.5,
            which the fusion model treats as "no information".
            """
            vector = _prepare_vector(x)
            try:
                self.eval()
                with torch.no_grad():
                    tensor = torch.from_numpy(vector).view(1, 1, -1)
                    output = self.forward(tensor)
                    return float(np.clip(float(output.item()), 0.0, 1.0))
            except Exception as exc:
                logger.warning("DyslexiaCNN torch forward failed: %s", exc)
                return 0.5

        def load_weights(self, path: str) -> bool:
            """Load a ``.pt`` checkpoint, returning True on success.

            Sets ``is_trained`` so the fusion model knows it may trust this
            network's output instead of the clinical heuristics.
            """
            if not path or not os.path.exists(path):
                logger.info("No CNN checkpoint at %s -- staying untrained.",
                            path)
                return False
            try:
                state = torch.load(path, map_location="cpu")
                if isinstance(state, dict) and "state_dict" in state:
                    state = state["state_dict"]
                self.load_state_dict(state)
                self.eval()
                self._trained = True
                logger.info("DyslexiaCNN loaded trained weights from %s", path)
                return True
            except Exception as exc:
                logger.warning("Failed to load CNN weights from %s: %s",
                               path, exc)
                self._trained = False
                return False

        @property
        def is_trained(self) -> bool:
            """True only when a real checkpoint was loaded successfully."""
            return self._trained

else:

    class DyslexiaCNN:  # type: ignore[no-redef]
        """NumPy stand-in for the dyslexia CNN.

        Mirrors the convolutional network's *shape* of computation without
        PyTorch: a fixed 3-tap smoothing kernel aggregates each feature with
        its neighbours (the analogue of ``Conv1d(kernel_size=3)``), then a
        hand-weighted logistic readout produces the score.

        The readout weights in ``_DYSLEXIA_READOUT`` are clinical judgement,
        not learned parameters -- b/d reversals dominate, letter accuracy
        pulls the score down, hesitation and latency contribute modestly.
        This makes the fallback fully explainable, which matters more for a
        screening demo than a black box would.
        """

        def __init__(self, input_features: int = INPUT_FEATURES) -> None:
            self.input_features = input_features
            self._trained = False
            self.backend = "numpy"
            # Normalised 3-tap smoothing kernel (the "conv" stage).
            self._kernel = np.array([0.25, 0.50, 0.25], dtype=np.float32)

        def _convolve(self, vector: np.ndarray) -> np.ndarray:
            """Same-length 1D convolution with edge padding."""
            padded = np.pad(vector, (1, 1), mode="edge")
            return np.convolve(padded, self._kernel, mode="valid")

        def forward(self, x: Any) -> float:
            """Alias for :meth:`predict`, for interface parity with torch."""
            return self.predict(x)

        def predict(self, x: Any) -> float:
            """Score one feature vector, returning a float in [0, 1]."""
            try:
                vector = _prepare_vector(x)
                smoothed = self._convolve(vector)

                # Weighted logistic readout over the dyslexia feature block.
                total_weight = 0.0
                activation = 0.0
                for index, weight, higher_is_worse in _DYSLEXIA_READOUT:
                    if index >= smoothed.shape[0]:
                        continue
                    value = float(smoothed[index])
                    if not higher_is_worse:
                        value = 1.0 - value
                    activation += weight * value
                    total_weight += weight

                if total_weight <= 0.0:
                    return 0.5
                # Centre on 0.5 and apply a gain so the logistic uses a
                # useful slice of its range rather than hugging 0.5.
                normalised = activation / total_weight
                return float(np.clip(_sigmoid((normalised - 0.5) * 5.0),
                                     0.0, 1.0))
            except Exception as exc:
                logger.warning("DyslexiaCNN numpy predict failed: %s", exc)
                return 0.5

        def load_weights(self, path: str) -> bool:
            """Always False -- ``.pt`` checkpoints need PyTorch to load."""
            if path and os.path.exists(path):
                logger.warning(
                    "Found %s but PyTorch is not installed; cannot load "
                    "trained CNN weights.", path
                )
            return False

        @property
        def is_trained(self) -> bool:
            """Always False: the NumPy path carries no learned parameters."""
            return False


def build_cnn(weights_path: Optional[str] = None) -> "DyslexiaCNN":
    """Construct a :class:`DyslexiaCNN`, loading weights when available.

    Args:
        weights_path: Optional path to ``dyslexia_cnn.pt``. Missing files are
            not an error -- the model simply stays untrained.

    Returns:
        A ready-to-use model. Never raises.
    """
    model = DyslexiaCNN()
    if weights_path:
        try:
            model.load_weights(weights_path)
        except Exception as exc:
            logger.warning("build_cnn: weight load raised %s", exc)
    return model


__all__: List[str] = ["DyslexiaCNN", "build_cnn", "TORCH_AVAILABLE",
                      "INPUT_FEATURES"]
