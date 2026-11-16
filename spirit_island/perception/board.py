"""Find a Spirit Island island board in a photo of the table.

The printed lands (green jungle, tan sands, blue-green wetland, ocean blue) are
far more saturated than a wooden or grey table, so a saturation mask, cleaned
up and reduced to its biggest solid shape, outlines the board. This needs no
reference picture and is used to (a) say where the board is and (b) limit
piece detection to the board.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass
class BoardOutline:
    contour: np.ndarray  # Nx1x2 int, full-resolution pixels
    quad: np.ndarray  # 4x2 float32, corners ordered TL, TR, BR, BL
    mask: np.ndarray  # uint8 255 inside the board, full resolution
    area_frac: float  # share of the frame the board covers

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        x, y, w, h = cv2.boundingRect(self.contour)
        return int(x), int(y), int(w), int(h)


def order_corners(pts: np.ndarray) -> np.ndarray:
    """TL, TR, BR, BL from any 4 points."""
    pts = np.asarray(pts, np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def _quad_from_contour(contour: np.ndarray) -> np.ndarray:
    hull = cv2.convexHull(contour)
    peri = cv2.arcLength(hull, True)
    for eps in np.linspace(0.01, 0.1, 19):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            return order_corners(approx)
    return order_corners(cv2.boxPoints(cv2.minAreaRect(contour)))


def find_board(
    image: np.ndarray,
    work_side: int = 1200,
    min_saturation: int = 60,
    min_area_frac: float = 0.02,
    exclude: Optional[np.ndarray] = None,
) -> Optional[BoardOutline]:
    """Outline the island board, or None if nothing board-like is found.

    `exclude` (uint8, 255 = ignore) masks out areas known not to be the board,
    for example a colourful rug in the background.
    """
    h, w = image.shape[:2]
    scale = min(1.0, work_side / max(h, w))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    hsv = cv2.cvtColor(cv2.GaussianBlur(small, (5, 5), 0), cv2.COLOR_BGR2HSV)
    sat = hsv[..., 1]
    otsu, _ = cv2.threshold(sat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = (sat > max(min_saturation, otsu)).astype(np.uint8) * 255
    if exclude is not None:
        ex = cv2.resize(exclude, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
        mask[ex > 0] = 0

    # Close the gaps that line-art, printed numbers and pieces leave in the lands.
    k = max(5, int(0.02 * max(small.shape[:2])) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k // 2 | 1, k // 2 | 1)))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = small.shape[0] * small.shape[1]
    best, best_score = None, 0.0
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area_frac * frame_area:
            continue
        solidity = area / max(cv2.contourArea(cv2.convexHull(c)), 1.0)
        score = area * solidity**2  # a board is big and compact; rugs and stray objects are ragged
        if score > best_score:
            best, best_score = c, score
    if best is None:
        return None

    # Grey mountains and pale wetlands are barely saturated, so one board can split
    # into several coloured pieces. Gather the pieces lying next to the best one...
    group = [best]
    bx, by, bw, bh = cv2.boundingRect(best)
    reach = 0.35 * max(bw, bh)
    for c in contours:
        if c is best or cv2.contourArea(c) < 0.002 * frame_area:
            continue
        cx, cy, cw, ch = cv2.boundingRect(c)
        gap_x = max(0, max(bx, cx) - min(bx + bw, cx + cw))
        gap_y = max(0, max(by, cy) - min(by + bh, cy + ch))
        if max(gap_x, gap_y) <= reach and cw * ch < 4 * bw * bh:
            group.append(c)
    # ...and close the gaps between them with a kernel sized to the board.
    union = np.zeros_like(mask)
    cv2.drawContours(union, group, -1, 255, thickness=cv2.FILLED)
    gx, gy, gw, gh = cv2.boundingRect(np.vstack(group))
    k2 = max(k, int(0.35 * min(gw, gh)) | 1)
    pad = k2
    padded = cv2.copyMakeBorder(union, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    padded = cv2.morphologyEx(padded, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k2, k2)))
    union = padded[pad:-pad, pad:-pad]
    merged, _ = cv2.findContours(union, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = max(merged, key=cv2.contourArea)

    contour = (best.astype(np.float32) / scale).astype(np.int32)
    full_mask = np.zeros((h, w), np.uint8)
    cv2.drawContours(full_mask, [contour], -1, 255, thickness=cv2.FILLED)
    return BoardOutline(
        contour=contour,
        quad=_quad_from_contour(contour),
        mask=full_mask,
        area_frac=round(float(cv2.contourArea(best)) / frame_area, 4),
    )
