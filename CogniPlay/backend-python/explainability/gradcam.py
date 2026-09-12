"""
Attention heatmap generation.

:func:`generate_heatmap` renders the child's attention across the session as
a base64 ``data:image/png;base64,...`` string that the React frontend can drop
straight into an ``<img src>``.

**What the picture actually shows.** This is not raw eye-tracking video and it
is not a CNN Grad-CAM over pixels -- the payload carries aggregate metrics, not
gaze coordinates. It is an honest visualisation of the metrics we *do* have:
the horizontal axis is time through the session, and warmth is attention
*lapse* (cool blue = focused, red = struggling), reconstructed from the
per-interval Butterfly Game scores. A top band encodes looking-away events
from the eye tracker when it was available. The module is named ``gradcam``
for continuity with the project's architecture diagram; the technique is a
metric-driven activation map, and the docstring says so rather than
overclaiming.

Encoding is attempted three ways, best first:

1. **OpenCV** (``cv2.imencode``) when installed.
2. **Pillow** when installed.
3. **Pure stdlib** -- a small ``zlib``-based PNG writer, so a real heatmap is
   produced even with nothing but NumPy available.

Only if all three fail does the function return a 1x1 transparent PNG. It
never raises.

Python 3.9 compatible: typing.Optional / typing.Dict / typing.List only.
"""

import base64
import logging
import struct
import zlib
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:  # pragma: no cover - depends on the deployment environment
    import cv2
    CV2_AVAILABLE = True
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    CV2_AVAILABLE = False

try:  # pragma: no cover - depends on the deployment environment
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    PIL_AVAILABLE = False

#: Output dimensions. Small on purpose -- this is inlined as base64 into a
#: JSON response, so every pixel costs bandwidth on the wire.
HEATMAP_WIDTH: int = 360
HEATMAP_HEIGHT: int = 120

#: Blur radius, in pixels, applied to soften the interval blocks.
_BLUR_SIGMA: float = 9.0

#: A 1x1 fully transparent PNG. The last-resort return value.
TRANSPARENT_PIXEL_PNG: str = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYA"
    "AjCB0C8AAAAASUVORK5CYII="
)


def _clamp01(value: Any) -> float:
    """Clamp to [0, 1], mapping None/NaN/inf to 0.0."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(v):
        return 0.0
    return float(min(1.0, max(0.0, v)))


def _section(payload: Any, key: str) -> Dict[str, Any]:
    """Fetch a payload section as a dict, tolerating None/missing/wrong type."""
    if not isinstance(payload, dict):
        return {}
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _interval_lapses(payload: Dict[str, Any]) -> List[float]:
    """Per-interval attention *lapse* values in [0, 1] (1 == worst).

    Falls back to a single neutral column when no interval data exists, so
    the heatmap is always a valid, if uninformative, image.
    """
    game = _section(payload, "butterfly_game")
    intervals = game.get("attention_by_interval")
    if not isinstance(intervals, list) or not intervals:
        return [0.5]

    lapses: List[float] = []
    for entry in intervals:
        if not isinstance(entry, dict):
            continue
        score = entry.get("score")
        if score is None:
            correct = entry.get("correct") or 0
            wrong = entry.get("wrong") or 0
            try:
                total = float(correct) + float(wrong)
                score = (float(correct) / total) if total > 0 else 0.5
            except (TypeError, ValueError):
                score = 0.5
        lapses.append(1.0 - _clamp01(score))

    return lapses if lapses else [0.5]


def _gaussian_blur(image: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur using only NumPy convolution.

    Applied along each axis in turn, which is equivalent to a 2D Gaussian and
    far cheaper. Edges use ``mode="edge"`` padding so the blur does not drag
    the borders toward black.
    """
    if sigma <= 0.0:
        return image

    radius = int(max(1, round(sigma * 2.0)))
    axis = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(axis ** 2) / (2.0 * sigma * sigma))
    total = float(np.sum(kernel))
    if total <= 0.0:
        return image
    kernel = kernel / total

    blurred = image.astype(np.float32)

    # Horizontal pass.
    padded = np.pad(blurred, ((0, 0), (radius, radius)), mode="edge")
    blurred = np.stack(
        [np.convolve(padded[row], kernel, mode="valid")
         for row in range(padded.shape[0])],
        axis=0,
    )

    # Vertical pass.
    padded = np.pad(blurred, ((radius, radius), (0, 0)), mode="edge")
    blurred = np.stack(
        [np.convolve(padded[:, col], kernel, mode="valid")
         for col in range(padded.shape[1])],
        axis=1,
    )

    return blurred


def _build_intensity_map(payload: Dict[str, Any]) -> np.ndarray:
    """Build the float32 ``(H, W)`` intensity field in [0, 1].

    Layout:

    * Full height, left to right: one vertical band per attention interval,
      warm where the child was lapsing.
    * Top ~18% of the frame: an overlay whose warmth is the eye tracker's
      off-screen rate, spread evenly. Skipped when eye tracking was absent.
    * A gentle left-to-right ramp weighted by ``performance_drop``, so a
      session that decayed reads as warming toward the right edge even when
      the interval data is coarse.
    """
    lapses = _interval_lapses(payload)
    columns = len(lapses)

    intensity = np.zeros((HEATMAP_HEIGHT, HEATMAP_WIDTH), dtype=np.float32)

    # Interval bands across the width.
    edges = np.linspace(0, HEATMAP_WIDTH, columns + 1).astype(int)
    for index in range(columns):
        start = int(edges[index])
        end = int(edges[index + 1])
        if end <= start:
            end = min(start + 1, HEATMAP_WIDTH)
        intensity[:, start:end] = float(lapses[index])

    # Session-decline ramp.
    game = _section(payload, "butterfly_game")
    try:
        drop = _clamp01(game.get("performance_drop", 0.0))
    except Exception:
        drop = 0.0
    if drop > 0.0:
        ramp = np.linspace(0.0, drop, HEATMAP_WIDTH, dtype=np.float32)
        intensity += ramp.reshape(1, -1) * 0.5

    # Off-screen band along the top.
    gaze = _section(payload, "eye_tracking")
    if gaze and gaze.get("available") is not False:
        try:
            off_screen = float(gaze.get("off_screen_count") or 0.0)
            fixations = float(gaze.get("total_fixations") or 0.0)
            rate = (off_screen / fixations) if fixations > 0 else 0.0
            # Saturate at 15% of fixations, matching the feature extractor.
            band_intensity = _clamp01(rate / 0.15)
        except (TypeError, ValueError):
            band_intensity = 0.0
        if band_intensity > 0.0:
            band_height = max(1, int(HEATMAP_HEIGHT * 0.18))
            intensity[:band_height, :] = np.maximum(
                intensity[:band_height, :], band_intensity
            )

    intensity = _gaussian_blur(intensity, _BLUR_SIGMA)
    return np.clip(intensity, 0.0, 1.0).astype(np.float32)


def _colourise(intensity: np.ndarray) -> np.ndarray:
    """Map intensity in [0, 1] onto an RGB uint8 image.

    A hand-built blue -> cyan -> green -> yellow -> red ramp, interpolated in
    NumPy so no matplotlib or OpenCV colormap is required. Cool = focused,
    warm = struggling, which matches the convention parents expect from
    "heatmap" imagery.
    """
    stops = np.array(
        [
            [40, 60, 140],    # deep blue   -- focused
            [40, 160, 190],   # cyan
            [70, 180, 110],   # green
            [235, 200, 70],   # yellow
            [200, 70, 60],    # red         -- struggling
        ],
        dtype=np.float32,
    )

    positions = np.linspace(0.0, 1.0, stops.shape[0], dtype=np.float32)
    flat = np.clip(intensity.reshape(-1), 0.0, 1.0)

    channels = [np.interp(flat, positions, stops[:, c]) for c in range(3)]
    rgb = np.stack(channels, axis=1)
    rgb = rgb.reshape(intensity.shape[0], intensity.shape[1], 3)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    """Build one length-prefixed, CRC-suffixed PNG chunk."""
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _encode_png_stdlib(rgb: np.ndarray) -> bytes:
    """Encode an RGB uint8 array as a PNG using only ``zlib`` and ``struct``.

    Writes a truecolour, 8-bit, non-interlaced PNG with filter type 0 on every
    scanline. Enough for a heatmap, and it removes any hard dependency on an
    imaging library.
    """
    height, width = int(rgb.shape[0]), int(rgb.shape[1])

    # Prefix each scanline with its filter byte (0 == None).
    filtered = np.concatenate(
        [np.zeros((height, 1), dtype=np.uint8),
         rgb.reshape(height, width * 3).astype(np.uint8)],
        axis=1,
    )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(filtered.tobytes(), 6))
        + _png_chunk(b"IEND", b"")
    )


def _encode_png(rgb: np.ndarray) -> Optional[bytes]:
    """Encode RGB pixels to PNG bytes, trying each backend in turn."""
    if CV2_AVAILABLE:
        try:
            # OpenCV expects BGR channel order. ascontiguousarray because
            # the reversed slice has negative strides, which cv2 rejects.
            bgr = np.ascontiguousarray(rgb[:, :, ::-1])
            success, buffer = cv2.imencode(".png", bgr)
            if success:
                return bytes(buffer.tobytes())
            logger.warning("cv2.imencode reported failure; trying Pillow.")
        except Exception as exc:
            logger.warning("OpenCV PNG encoding failed: %s", exc)

    if PIL_AVAILABLE:
        try:
            import io
            buffer = io.BytesIO()
            Image.fromarray(rgb, mode="RGB").save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception as exc:
            logger.warning("Pillow PNG encoding failed: %s", exc)

    try:
        return _encode_png_stdlib(rgb)
    except Exception as exc:
        logger.warning("Stdlib PNG encoding failed: %s", exc)
        return None


def generate_heatmap(payload: Dict[str, Any]) -> str:
    """Render the session attention heatmap as a base64 PNG data URI.

    Args:
        payload: The raw telemetry payload. Any part of it may be missing.

    Returns:
        ``"data:image/png;base64,..."``. On any failure, the 1x1 transparent
        PNG constant, so the frontend's ``<img>`` still has a valid source.

    This function never raises.
    """
    try:
        if not isinstance(payload, dict):
            payload = {}
        intensity = _build_intensity_map(payload)
        rgb = _colourise(intensity)
        png_bytes = _encode_png(rgb)
        if not png_bytes:
            return TRANSPARENT_PIXEL_PNG
        encoded = base64.b64encode(png_bytes).decode("ascii")
        return "data:image/png;base64,{0}".format(encoded)
    except Exception as exc:
        logger.error("generate_heatmap failed: %s", exc, exc_info=True)
        return TRANSPARENT_PIXEL_PNG


def heatmap_dimensions() -> Tuple[int, int]:
    """Return the ``(width, height)`` of the generated heatmap."""
    return HEATMAP_WIDTH, HEATMAP_HEIGHT


__all__: List[str] = [
    "generate_heatmap", "heatmap_dimensions", "CV2_AVAILABLE",
    "PIL_AVAILABLE", "TRANSPARENT_PIXEL_PNG",
]
