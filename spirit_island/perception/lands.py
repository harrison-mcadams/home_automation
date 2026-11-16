"""Map a board's lands on its reference photo, so each piece gets a land number.

You give one point inside each land (and the ocean) on the reference photo; the
lands are then grown from those points until they meet along the printed colour
boundaries (a watershed over the photo's colour edges). Done once per board
reference. Because every new photo is lined up to the reference, a piece's land
is just a lookup, wherever the board or camera has moved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


MEDIAN = 7  # median-blur kernel at working size; with board_side it sets how much printed art is ignored


def segment_lands(
    reference: np.ndarray,
    board_mask: np.ndarray,
    seeds: dict[str, tuple[float, float]],
    board_side: int = 200,
) -> tuple[np.ndarray, list[str]]:
    """Label image at reference size (0 = off board, i = names[i-1]) and the names.

    Works on a copy shrunk so the board is about `board_side` pixels across: at that
    size the printed art inside a land blurs away while the colour borders between
    lands survive, whatever the photo's resolution or the camera's distance.
    """
    h, w = reference.shape[:2]
    board_px = float(np.sqrt(max(int((board_mask > 0).sum()), 1)))
    scale = min(1.0, board_side / board_px)
    small = cv2.resize(reference, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    mask = cv2.resize(board_mask, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)

    # Smooth away the line-art inside each land but keep the boundaries between lands.
    smooth = cv2.bilateralFilter(cv2.medianBlur(small, MEDIAN), 7, 50, 7)
    lab = cv2.cvtColor(smooth, cv2.COLOR_BGR2LAB).astype(np.float32)
    grad = np.zeros(lab.shape[:2], np.float32)
    for c in range(3):
        gx = cv2.Sobel(lab[..., c], cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(lab[..., c], cv2.CV_32F, 0, 1, ksize=3)
        grad += cv2.magnitude(gx, gy)
    grad = cv2.normalize(grad, None, 0, 254, cv2.NORM_MINMAX).astype(np.uint8)
    # A wall along the board's edge, so the off-board region can't leak into a land
    # through a soft colour border: the lands fill everything inside first.
    rim = cv2.morphologyEx((mask > 0).astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    grad[rim > 0] = 255

    names = list(seeds)
    markers = np.zeros(mask.shape, np.int32)
    markers[mask == 0] = len(names) + 1  # off board
    radius = max(3, int(0.015 * np.sqrt(max(int((mask > 0).sum()), 1))))
    for i, name in enumerate(names, 1):
        x, y = seeds[name]
        cv2.circle(markers, (int(x * scale), int(y * scale)), radius, i, -1)
    markers[mask == 0] = len(names) + 1
    cv2.watershed(cv2.merge([grad, grad, grad]), markers)
    markers[(markers > len(names)) | (markers < 0)] = 0

    # Boundary pixels (-1 from the watershed) go to the neighbouring land.
    on_board = (mask > 0) & (markers == 0)
    if on_board.any():
        filled = cv2.dilate(markers.astype(np.float32), np.ones((3, 3), np.uint8)).astype(np.int32)
        markers[on_board] = filled[on_board]
    labels = cv2.resize(markers.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
    return labels, names


def land_at(labels: np.ndarray, names: list[str], x: float, y: float, search: int = 40) -> Optional[str]:
    """Land name at a reference-pixel position (nearest land within `search` px if on a boundary)."""
    h, w = labels.shape
    xi, yi = int(round(x)), int(round(y))
    if 0 <= xi < w and 0 <= yi < h and labels[yi, xi] > 0:
        return names[labels[yi, xi] - 1]
    y0, y1, x0, x1 = max(0, yi - search), min(h, yi + search + 1), max(0, xi - search), min(w, xi + search + 1)
    window = labels[y0:y1, x0:x1]
    ys, xs = np.nonzero(window)
    if len(xs) == 0:
        return None
    k = int(np.argmin((xs + x0 - x) ** 2 + (ys + y0 - y) ** 2))
    return names[window[ys[k], xs[k]] - 1]


def piece_land(labels: np.ndarray, names: list[str], piece_mask_points: np.ndarray) -> Optional[str]:
    """Land most of a piece sits on (by its pixels' votes), for pieces near a boundary."""
    if len(piece_mask_points) == 0:
        return None
    vals = labels[piece_mask_points[:, 1], piece_mask_points[:, 0]]
    vals = vals[vals > 0]
    if len(vals) == 0:
        return None
    return names[int(np.bincount(vals).argmax()) - 1]


def save(ref_dir: Path, labels: np.ndarray, names: list[str], seeds: dict) -> None:
    cv2.imwrite(str(ref_dir / "lands.png"), labels)
    (ref_dir / "lands.json").write_text(json.dumps({"names": names, "seeds": seeds}, indent=2))


def load(ref_dir: Path):
    path = ref_dir / "lands.json"
    if not path.exists():
        return None, None
    meta = json.loads(path.read_text())
    labels = cv2.imread(str(ref_dir / "lands.png"), cv2.IMREAD_GRAYSCALE)
    return labels, meta["names"]


def draw(reference: np.ndarray, labels: np.ndarray, names: list[str]) -> np.ndarray:
    """Reference photo with each land tinted and labelled, for checking the map by eye."""
    rng = np.random.default_rng(4)
    colours = rng.integers(60, 255, size=(len(names) + 1, 3))
    tint = colours[labels].astype(np.uint8)
    out = reference.copy()
    on = labels > 0
    out[on] = (0.55 * out[on] + 0.45 * tint[on]).astype(np.uint8)
    edges = cv2.morphologyEx(labels, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    out[edges] = (0, 0, 0)
    t = max(2, int(max(out.shape[:2]) / 700))
    for i, name in enumerate(names, 1):
        ys, xs = np.nonzero(labels == i)
        if len(xs):
            cx, cy = int(xs.mean()), int(ys.mean())
            cv2.putText(out, name, (cx, cy), cv2.FONT_HERSHEY_SIMPLEX, t, (0, 0, 0), t * 3)
            cv2.putText(out, name, (cx, cy), cv2.FONT_HERSHEY_SIMPLEX, t, (255, 255, 255), t)
    return out
