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


_REF_CACHE: dict = {}


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
    # The reference is the same photo call after call: find its features once.
    key = (id(reference), reference.shape, max_side, None if reference_mask is None else id(reference_mask))
    if key not in _REF_CACHE:
        if len(_REF_CACHE) > 16:
            _REF_CACHE.clear()
        _REF_CACHE[key] = sift.detectAndCompute(ref_gray, mask)
    kp_ref, des_ref = _REF_CACHE[key]
    kp_img, des_img = sift.detectAndCompute(img_gray, None)
    if des_ref is None or des_img is None or len(kp_ref) < 8 or len(kp_img) < 8:
        return None

    cv2.setRNGSeed(0)  # FLANN's randomised trees and RANSAC both draw on OpenCV's RNG
    matcher = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 64})
    pairs = matcher.knnMatch(des_img, des_ref, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return None

    src = np.float32([kp_img[m.queryIdx].pt for m in good]) / img_scale
    dst = np.float32([kp_ref[m.trainIdx].pt for m in good]) / ref_scale
    # RANSAC is random: fix the seed so the same photo always gives the same answer, then
    # refit on all inliers by least squares so small sampling differences average out.
    # Borderline decisions downstream (is this one piece or two?) must not flicker.
    cv2.setRNGSeed(0)
    method = getattr(cv2, "USAC_MAGSAC", cv2.RANSAC)
    H, inlier_mask = cv2.findHomography(src, dst, method, 4.0 / ref_scale, maxIters=5000, confidence=0.999)
    if H is None:
        return None
    keep = inlier_mask.ravel().astype(bool)
    if keep.sum() >= 8:
        refined, _ = cv2.findHomography(src[keep], dst[keep], 0)
        if refined is not None:
            H = refined
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
