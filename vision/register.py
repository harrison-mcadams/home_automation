"""Align one picture of a flat scene onto another (image registration).

Used to line a live frame up with a reference picture of the same printed
surface (a game board, a poster, a whiteboard), even after the surface or the
camera has moved a little. Works on any textured, mostly flat target.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass
class Registration:
    homography: np.ndarray  # maps image pixels -> reference pixels (full resolution)
    inliers: int
    matches: int

    @property
    def ok(self) -> bool:
        return self.inliers >= 25 and self.inliers >= 0.15 * max(self.matches, 1)


def _gray_scaled(image: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale = min(1.0, max_side / max(gray.shape[:2]))
    if scale < 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return gray, scale


def register(
    reference: np.ndarray,
    image: np.ndarray,
    max_side: int = 1600,
    reference_mask: Optional[np.ndarray] = None,
) -> Optional[Registration]:
    """Find the homography that maps `image` onto `reference`.

    `reference_mask` (same size as reference, nonzero = use) limits features to
    the target itself, so a moving background can't pull the alignment off.
    Returns None when there aren't enough matching features.
    """
    ref_gray, ref_scale = _gray_scaled(reference, max_side)
    img_gray, img_scale = _gray_scaled(image, max_side)
    mask = None
    if reference_mask is not None:
        mask = cv2.resize(reference_mask, (ref_gray.shape[1], ref_gray.shape[0]), interpolation=cv2.INTER_NEAREST)

    sift = cv2.SIFT_create(nfeatures=4000)
    kp_ref, des_ref = sift.detectAndCompute(ref_gray, mask)
    kp_img, des_img = sift.detectAndCompute(img_gray, None)
    if des_ref is None or des_img is None or len(kp_ref) < 8 or len(kp_img) < 8:
        return None

    matcher = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 64})
    pairs = matcher.knnMatch(des_img, des_ref, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return None

    src = np.float32([kp_img[m.queryIdx].pt for m in good]) / img_scale
    dst = np.float32([kp_ref[m.trainIdx].pt for m in good]) / ref_scale
    H, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0 / ref_scale)
    if H is None:
        return None
    return Registration(homography=H, inliers=int(inlier_mask.sum()), matches=len(good))


def warp_to_reference(image: np.ndarray, registration: Registration, reference_shape) -> np.ndarray:
    """Resample `image` into the reference's pixel grid."""
    h, w = reference_shape[:2]
    return cv2.warpPerspective(image, registration.homography, (w, h), flags=cv2.INTER_LINEAR)


def valid_mask(image_shape, registration: Registration, reference_shape) -> np.ndarray:
    """Pixels of the reference grid that the warped image actually covers."""
    ones = np.full(image_shape[:2], 255, np.uint8)
    h, w = reference_shape[:2]
    return cv2.warpPerspective(ones, registration.homography, (w, h), flags=cv2.INTER_NEAREST)
