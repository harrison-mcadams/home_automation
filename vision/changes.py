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
    thickness: float = 0.0  # radius of the largest circle that fits inside, in reference pixels


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


def split_touching(mask: np.ndarray, dist: np.ndarray, core_ratio: float = 0.55,
                   min_core_frac: float = 0.35) -> np.ndarray:
    """Label blobs, splitting ones made of several touching objects (two pieces side by side).

    Each object has a thick core (high distance-to-edge); the neck between two touching
    objects is thinner. Cores are seeds for a watershed over the distance map. A core
    only counts if it is at least `min_core_frac` as thick as the blob's thickest point,
    so one lumpy object is not cut up.
    """
    count, cc = cv2.connectedComponents(mask, connectivity=8)
    markers = np.zeros(mask.shape, np.int32)
    next_label = 1
    for i in range(1, count):
        sel = cc == i
        peak = float(dist[sel].max())
        core = (sel & (dist > core_ratio * peak)).astype(np.uint8)
        n, core_lab = cv2.connectedComponents(core, connectivity=8)
        kept = [j for j in range(1, n) if float(dist[core_lab == j].max()) >= min_core_frac * peak]
        if len(kept) <= 1:
            markers[sel] = next_label
            next_label += 1
            continue
        for j in kept:
            markers[core_lab == j] = next_label
            next_label += 1
    if next_label == 1:
        return markers
    # Unassigned pixels inside a split blob get the label of the nearest core, following the distance map.
    relief = cv2.normalize(-dist, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    ws_markers = markers.copy()
    ws_markers[mask == 0] = next_label  # background seed
    cv2.watershed(cv2.merge([relief, relief, relief]), ws_markers)
    ws_markers[(ws_markers == next_label) | (ws_markers < 0) | (mask == 0)] = 0
    return ws_markers


def find_changes(
    reference: np.ndarray,
    aligned: np.ndarray,
    region: Optional[np.ndarray] = None,
    min_area_frac: float = 0.0003,
    threshold: Optional[float] = None,
    work_side: int = 1600,
    split: bool = True,
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
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    for i in range(1, count):
        if stats[i][4] < min_area:
            mask[labels == i] = 0
    # Thickness tells a compact object from a thin line of change along a printed
    # edge (which can be long and curved, so its bounding box looks big).
    inside_dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    labels = split_touching(mask, inside_dist) if split else cv2.connectedComponents(mask, connectivity=8)[1]

    blobs = []
    for i in range(1, int(labels.max()) + 1):
        sel = labels == i
        area = int(sel.sum())
        if area == 0:
            continue
        ys, xs = np.nonzero(sel)
        x, y, w, h = int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
        piece_dist = cv2.distanceTransform(sel.astype(np.uint8), cv2.DIST_L2, 5)
        blobs.append(
            Blob(
                bbox=(int(x / scale), int(y / scale), int(w / scale), int(h / scale)),
                centroid=(float(xs.mean() / scale), float(ys.mean() / scale)),
                area=int(area / scale / scale),
                mean_bgr=tuple(round(float(v), 1) for v in new[sel].mean(axis=0)),
                score=round(float(diff[sel].mean()), 1),
                thickness=round(float(piece_dist.max() / scale), 1),
            )
        )
    blobs.sort(key=lambda b: b.area, reverse=True)
    full_mask = cv2.resize(mask, (full_w, full_h), interpolation=cv2.INTER_NEAREST)
    return blobs, full_mask
