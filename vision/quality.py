"""Image-quality measurements used by the camera probe.

All functions take plain BGR numpy images, so they work on live frames,
recordings and test fixtures alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import cv2
import numpy as np

# The marker family used everywhere in this repo: small, robust, and printable.
ARUCO_DICT = cv2.aruco.DICT_4X4_50


def _gray(image: np.ndarray) -> np.ndarray:
    return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def sharpness(image: np.ndarray) -> float:
    """Variance of the Laplacian: higher is sharper. Compare like with like
    (same camera, same scene); the absolute value depends on scene detail."""
    return float(cv2.Laplacian(_gray(image), cv2.CV_64F).var())


def sharpness_grid(image: np.ndarray, rows: int = 3, cols: int = 3) -> list[list[float]]:
    """Sharpness per tile, to spot a corner that is out of focus or in shadow."""
    gray = _gray(image)
    h, w = gray.shape
    grid = []
    for r in range(rows):
        row = []
        for c in range(cols):
            tile = gray[r * h // rows : (r + 1) * h // rows, c * w // cols : (c + 1) * w // cols]
            row.append(round(sharpness(tile), 1))
        grid.append(row)
    return grid


def brightness(image: np.ndarray) -> dict:
    """Mean level plus the share of clipped pixels (blown highlights / crushed shadows)."""
    gray = _gray(image)
    total = gray.size
    return {
        "mean": round(float(gray.mean()), 1),
        "pct_black": round(100.0 * float((gray <= 5).sum()) / total, 2),
        "pct_white": round(100.0 * float((gray >= 250).sum()) / total, 2),
    }


def temporal_noise(frames: Sequence[np.ndarray]) -> Optional[float]:
    """Mean absolute difference between consecutive frames of a still scene.
    Grows with sensor noise (dim light) and with anything moving."""
    if len(frames) < 2:
        return None
    diffs = [
        float(cv2.absdiff(_gray(a), _gray(b)).mean()) for a, b in zip(frames[:-1], frames[1:])
    ]
    return round(float(np.median(diffs)), 2)


@dataclass
class MarkerScale:
    """Pixels-per-millimetre measured from ArUco markers of known printed size."""

    marker_mm: float
    per_marker: dict = field(default_factory=dict)  # id -> {"px_per_mm", "center"}
    corners: list = field(default_factory=list)  # raw corners, for drawing

    @property
    def px_per_mm(self) -> Optional[float]:
        if not self.per_marker:
            return None
        return round(float(np.mean([m["px_per_mm"] for m in self.per_marker.values()])), 3)

    @property
    def spread(self) -> Optional[float]:
        """Max/min ratio across markers. Near 1.0 means the camera looks straight
        down; well above 1.0 means the view is tilted (perspective)."""
        values = [m["px_per_mm"] for m in self.per_marker.values()]
        if len(values) < 2:
            return None
        return round(max(values) / min(values), 3)


def detect_markers(image: np.ndarray):
    """Return (corners, ids) for every ArUco marker in the image."""
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(ARUCO_DICT), cv2.aruco.DetectorParameters()
    )
    corners, ids, _ = detector.detectMarkers(_gray(image))
    return corners, ids


def marker_scale(image: np.ndarray, marker_mm: float) -> MarkerScale:
    """Measure pixels per mm from the side length of each detected marker."""
    corners, ids = detect_markers(image)
    result = MarkerScale(marker_mm=marker_mm, corners=list(corners))
    if ids is None:
        return result
    for quad, marker_id in zip(corners, ids.flatten()):
        pts = quad.reshape(4, 2)
        sides = [float(np.linalg.norm(pts[i] - pts[(i + 1) % 4])) for i in range(4)]
        result.per_marker[int(marker_id)] = {
            "px_per_mm": round(float(np.mean(sides)) / marker_mm, 3),
            "center": [round(float(v), 1) for v in pts.mean(axis=0)],
        }
    return result


def annotate(image: np.ndarray, scale: Optional[MarkerScale] = None, lines: Sequence[str] = ()) -> np.ndarray:
    """Copy of the image with markers outlined and a few lines of text, for snapshots."""
    out = image.copy()
    if scale is not None and scale.corners:
        cv2.aruco.drawDetectedMarkers(out, scale.corners)
    size = max(0.5, out.shape[1] / 1600)
    y = int(40 * size)
    for text in lines:
        cv2.putText(out, text, (15, y), cv2.FONT_HERSHEY_SIMPLEX, size, (0, 0, 0), int(5 * size) + 1)
        cv2.putText(out, text, (15, y), cv2.FONT_HERSHEY_SIMPLEX, size, (255, 255, 255), int(2 * size) + 1)
        y += int(40 * size)
    return out
