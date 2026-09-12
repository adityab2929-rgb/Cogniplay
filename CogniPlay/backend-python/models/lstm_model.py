"""
AttentionLSTM -- a recurrent scorer over the attention time-series.

Where ``DyslexiaCNN`` looks at a static summary of the whole session, this
model looks at *how attention changed over the course of it*. Sustained
attention that starts strong and decays is the temporal signature the ADHD
screen cares about; a child who is uniformly moderate looks very different
from one who begins at 90% and finishes at 40%, even when their session
averages match.

Input is the ``(T, F)`` sequence produced by
``features.extract_features.build_sequence`` -- T=6 intervals, F=4 per-interval
features (score, normalised correct, normalised wrong, change-vs-previous).

As with the CNN, two implementations share one interface:

* **torch available** -- a real ``nn.Module`` (``LSTM -> FC -> ReLU -> FC ->
  sigmoid``) that can load a trained ``adhd_lstm.pt``.
* **torch missing** -- a NumPy class computing the same three temporal
  quantities an LSTM would have to learn (level, trend, volatility) and
  combining them through a documented logistic.

**Honesty note.** Without a checkpoint the torch path is randomly initialised
and its output is meaningless; ``FusionModel`` checks ``is_trained`` and
ignores it. The NumPy path is a transparent heuristic, not a trained network.

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
        "PyTorch not installed -- AttentionLSTM will use the NumPy fallback."
    )

SEQUENCE_LENGTH: int = 6
SEQUENCE_FEATURES: int = 4
HIDDEN_SIZE: int = 32


def _sigmoid(x: float) -> float:
    """Numerically stable logistic function."""
    if x >= 0:
        return float(1.0 / (1.0 + np.exp(-x)))
    exp_x = np.exp(x)
    return float(exp_x / (1.0 + exp_x))


def _prepare_sequence(x: Any) -> np.ndarray:
    """Coerce arbitrary input into a ``(T, F)`` float32 array.

    Pads short sequences by repeating the final timestep (a plateau, which is
    a truthful "no further information" signal) and truncates long ones.
    A completely unusable input becomes a neutral sequence.
    """
    try:
        sequence = np.asarray(x, dtype=np.float32)
    except Exception:
        sequence = np.zeros((0, SEQUENCE_FEATURES), dtype=np.float32)

    if sequence.ndim == 1:
        # A flat vector: interpret it as a single timestep if it fits.
        if sequence.shape[0] == SEQUENCE_FEATURES:
            sequence = sequence.reshape(1, SEQUENCE_FEATURES)
        else:
            sequence = np.zeros((0, SEQUENCE_FEATURES), dtype=np.float32)
    elif sequence.ndim > 2:
        sequence = sequence.reshape(-1, sequence.shape[-1])

    if sequence.ndim != 2 or sequence.size == 0:
        neutral = np.zeros((SEQUENCE_LENGTH, SEQUENCE_FEATURES),
                           dtype=np.float32)
        neutral[:, 0] = 0.5
        neutral[:, 3] = 0.5
        return neutral

    # Fix the feature width.
    if sequence.shape[1] < SEQUENCE_FEATURES:
        pad_width = SEQUENCE_FEATURES - sequence.shape[1]
        sequence = np.pad(sequence, ((0, 0), (0, pad_width)))
    elif sequence.shape[1] > SEQUENCE_FEATURES:
        sequence = sequence[:, :SEQUENCE_FEATURES]

    # Fix the time width.
    if sequence.shape[0] > SEQUENCE_LENGTH:
        sequence = sequence[:SEQUENCE_LENGTH]
    while sequence.shape[0] < SEQUENCE_LENGTH:
        sequence = np.vstack([sequence, sequence[-1:]])

    return np.nan_to_num(sequence.astype(np.float32),
                         nan=0.0, posinf=1.0, neginf=0.0)


if TORCH_AVAILABLE:

    class AttentionLSTM(nn.Module):  # type: ignore[misc]
        """LSTM over attention intervals, producing an ADHD-risk score."""

        def __init__(self, input_features: int = SEQUENCE_FEATURES,
                     hidden_size: int = HIDDEN_SIZE) -> None:
            super().__init__()
            self.input_features = input_features
            self.hidden_size = hidden_size
            self.lstm = nn.LSTM(
                input_size=input_features,
                hidden_size=hidden_size,
                num_layers=1,
                batch_first=True,
            )
            self.relu = nn.ReLU()
            self.dropout = nn.Dropout(0.2)
            self.fc1 = nn.Linear(hidden_size, 16)
            self.fc2 = nn.Linear(16, 1)
            self.sigmoid = nn.Sigmoid()

            self._trained = False
            self.backend = "torch"

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            """Run the network. Input ``(batch, T, F)``.

            Only the final hidden state is used: it is the LSTM's summary of
            the whole trajectory, which is exactly the quantity of interest.
            """
            output, _ = self.lstm(x)
            last_hidden = output[:, -1, :]
            hidden = self.dropout(self.relu(self.fc1(last_hidden)))
            return self.sigmoid(self.fc2(hidden))

        def predict(self, x: Any) -> float:
            """Score one sequence, returning a float in [0, 1].

            Never raises: failures degrade to a neutral 0.5.
            """
            sequence = _prepare_sequence(x)
            try:
                self.eval()
                with torch.no_grad():
                    tensor = torch.from_numpy(sequence).unsqueeze(0)
                    output = self.forward(tensor)
                    return float(np.clip(float(output.item()), 0.0, 1.0))
            except Exception as exc:
                logger.warning("AttentionLSTM torch forward failed: %s", exc)
                return 0.5

        def load_weights(self, path: str) -> bool:
            """Load an ``.pt`` checkpoint, returning True on success."""
            if not path or not os.path.exists(path):
                logger.info("No LSTM checkpoint at %s -- staying untrained.",
                            path)
                return False
            try:
                state = torch.load(path, map_location="cpu")
                if isinstance(state, dict) and "state_dict" in state:
                    state = state["state_dict"]
                self.load_state_dict(state)
                self.eval()
                self._trained = True
                logger.info("AttentionLSTM loaded trained weights from %s",
                            path)
                return True
            except Exception as exc:
                logger.warning("Failed to load LSTM weights from %s: %s",
                               path, exc)
                self._trained = False
                return False

        @property
        def is_trained(self) -> bool:
            """True only when a real checkpoint was loaded successfully."""
            return self._trained

else:

    class AttentionLSTM:  # type: ignore[no-redef]
        """NumPy stand-in for the attention LSTM.

        A recurrent model over this sequence has three things it can usefully
        learn, and this fallback computes them directly:

        * **level** -- mean interval score. Low overall accuracy is weak but
          real evidence.
        * **trend** -- least-squares slope of score against interval index.
          A negative slope is the sustained-attention decline signal and
          carries the most weight.
        * **volatility** -- standard deviation across intervals. Erratic,
          spiky attention scores higher than a steady low.

        These are combined by a documented logistic. Transparent by design:
        every term can be pointed at during a demo.
        """

        def __init__(self, input_features: int = SEQUENCE_FEATURES,
                     hidden_size: int = HIDDEN_SIZE) -> None:
            self.input_features = input_features
            self.hidden_size = hidden_size
            self._trained = False
            self.backend = "numpy"

        def forward(self, x: Any) -> float:
            """Alias for :meth:`predict`, for interface parity with torch."""
            return self.predict(x)

        def predict(self, x: Any) -> float:
            """Score one sequence, returning a float in [0, 1]."""
            try:
                sequence = _prepare_sequence(x)
                scores = sequence[:, 0]
                n = scores.shape[0]
                if n == 0:
                    return 0.5

                level = float(np.mean(scores))

                # Least-squares slope over evenly spaced intervals.
                if n >= 2:
                    x_axis = np.arange(n, dtype=np.float32)
                    x_var = float(np.var(x_axis))
                    if x_var > 0.0:
                        x_centred = x_axis - float(np.mean(x_axis))
                        y_centred = scores - level
                        slope = float(np.mean(x_centred * y_centred) / x_var)
                    else:
                        slope = 0.0
                    volatility = float(np.std(scores))
                else:
                    slope = 0.0
                    volatility = 0.0

                # A slope of -0.1 per interval over 6 intervals is a ~60%
                # collapse; treat that as a saturating decline signal.
                decline = float(np.clip(-slope / 0.10, 0.0, 1.0))
                # Volatility of 0-1 values rarely exceeds 0.35 in practice.
                instability = float(np.clip(volatility / 0.35, 0.0, 1.0))
                inattention = float(np.clip(1.0 - level, 0.0, 1.0))

                activation = (0.45 * decline
                              + 0.30 * instability
                              + 0.25 * inattention)
                return float(np.clip(_sigmoid((activation - 0.5) * 5.0),
                                     0.0, 1.0))
            except Exception as exc:
                logger.warning("AttentionLSTM numpy predict failed: %s", exc)
                return 0.5

        def load_weights(self, path: str) -> bool:
            """Always False -- ``.pt`` checkpoints need PyTorch to load."""
            if path and os.path.exists(path):
                logger.warning(
                    "Found %s but PyTorch is not installed; cannot load "
                    "trained LSTM weights.", path
                )
            return False

        @property
        def is_trained(self) -> bool:
            """Always False: the NumPy path carries no learned parameters."""
            return False


def build_lstm(weights_path: Optional[str] = None) -> "AttentionLSTM":
    """Construct an :class:`AttentionLSTM`, loading weights when available.

    Args:
        weights_path: Optional path to ``adhd_lstm.pt``. A missing file is
            not an error -- the model simply stays untrained.

    Returns:
        A ready-to-use model. Never raises.
    """
    model = AttentionLSTM()
    if weights_path:
        try:
            model.load_weights(weights_path)
        except Exception as exc:
            logger.warning("build_lstm: weight load raised %s", exc)
    return model


__all__: List[str] = ["AttentionLSTM", "build_lstm", "TORCH_AVAILABLE",
                      "SEQUENCE_LENGTH", "SEQUENCE_FEATURES"]
