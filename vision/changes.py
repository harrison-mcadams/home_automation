"""Find what changed between a reference picture and an aligned new picture.

With the new picture registered onto the reference (see vision.register),
anything placed on the surface shows up as a blob of changed pixels. This is
the generic "something is here that wasn't before" step; deciding *what* each
blob is belongs to the game-specific code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass
class Blob:
    bbox: tuple[int, int, int, int]  # x, y, w, h in reference pixels
    centroid: tuple[float, float]
    area: int  # pixels, in reference resolution
    mean_bgr: tuple[float, float, float]  # colour of the blob in the new picture
    score: float  # mean colour difference inside the blob


def change_map(
    reference: np.ndarray,
    aligned: np.ndarray,
    region: Optional[np.ndarray] = None,
    blur: int = 7,
) -> np.ndarray:
    """Per-pixel colour difference (float32, roughly CIE delta-E) after evening out
    a global lighting change inside `region`."""
    ref = cv2.GaussianBlur(reference, (blur, blur), 0)
    new = cv2.GaussianBlur(aligned, (blur, blur), 0)
    ref_lab = cv2.cvtColor(ref, cv2.COLOR_BGR2LAB).astype(np.float32)
    new_lab = cv2.cvtColor(new, cv2.COLOR_BGR2LAB).astype(np.float32)
    sel = region > 0 if region is not None else np.ones(ref.shape[:2], bool)
    if sel.any():
        # Lighting drifts (clouds, a lamp); shift each channel so the typical pixel matches.
        for c in range(3):
            new_lab[..., c] -= float(np.median(new_lab[..., c][sel] - ref_lab[..., c][sel]))
    diff = new_lab - ref_lab
    diff[..., 0] *= 0.5  # brightness changes (shadows) count half as much as colour changes
    return np.sqrt((diff**2).sum(axis=2))


def find_changes(
    reference: np.ndarray,
    aligned: np.ndarray,
    region: Optional[np.ndarray] = None,
    min_area_frac: float = 0.0003,
    threshold: Optional[float] = None,
    work_side: int = 1600,
) -> tuple[list[Blob], np.ndarray]:
    """Blobs where `aligned` differs from `reference`, inside `region` (255 = look).

    Returns (blobs sorted largest first, binary change mask at reference size).
    `min_area_frac` is the smallest blob as a fraction of the region's area.
    """
    full_h, full_w = reference.shape[:2]
    scale = min(1.0, work_side / max(full_h, full_w))
    size = (max(1, int(full_w * scale)), max(1, int(full_h * scale)))
    ref = cv2.resize(reference, size, interpolation=cv2.INTER_AREA)
    new = cv2.resize(aligned, size, interpolation=cv2.INTER_AREA)
    reg = (
        cv2.resize(region, size, interpolation=cv2.INTER_NEAREST)
        if region is not None
        else np.full(size[::-1], 255, np.uint8)
    )
    # Stay a few pixels inside the region: edges are where small misalignments show.
    reg = cv2.erode(reg, np.ones((9, 9), np.uint8))

    diff = change_map(ref, new, reg)
    inside = diff[reg > 0]
    if inside.size == 0:
        return [], np.zeros((full_h, full_w), np.uint8)
    if threshold is None:
        # Noise floor from the region itself: median + a generous multiple of the MAD.
        med = float(np.median(inside))
        mad = float(np.median(np.abs(inside - med))) + 1e-6
        threshold = max(12.0, med + 8.0 * mad)

    mask = ((diff > threshold) & (reg > 0)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    min_area = max(4, int(min_area_frac * int((reg > 0).sum())))
    count, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    blobs = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if area < min_area:
            mask[labels == i] = 0
            continue
        sel = labels == i
        mean_bgr = tuple(round(float(v), 1) for v in new[sel].mean(axis=0))
        blobs.append(
            Blob(
                bbox=(int(x / scale), int(y / scale), int(w / scale), int(h / scale)),
                centroid=(float(cents[i][0] / scale), float(cents[i][1] / scale)),
                area=int(area / scale / scale),
                mean_bgr=mean_bgr,
                score=round(float(diff[sel].mean()), 1),
            )
        )
    blobs.sort(key=lambda b: b.area, reverse=True)
    full_mask = cv2.resize(mask, (full_w, full_h), interpolation=cv2.INTER_NEAREST)
    return blobs, full_mask
