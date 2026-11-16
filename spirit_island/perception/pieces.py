"""Tell what a detected piece is from its colour, size and shape.

A first, rule-based classifier for the pieces in Harrison's set, as seen from the
overhead camera (see the project notes for what each looks like):

    explorer, town, city   white plastic figures, told apart by size and shape
    dahan                  plain cream wooden disc
    presence               wooden disc in a spirit's colour (saturated)
    blight                 dark blue-grey bumpy plastic
    energy                 tan cardboard marker with a printed value (normally on a spirit panel)

Sizes are measured relative to the board, so they don't change with camera distance.
The thresholds live in RULES so they can be tuned against labelled photos.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

RULES = {
    # Colour families (OpenCV HSV: hue 0-180, saturation and value 0-255), from core pixels.
    "blight_max_value": 120,  # dark
    "vivid_min_saturation": 105,  # presence discs are strongly coloured
    "white_max_saturation": 38,  # plastic invaders are near-white (any hue)
    "white_min_value": 150,
    "warm_hue": (6, 32),  # cream (dahan) and tan (cardboard) are warm yellow-orange
    "cream_min_value": 170,  # dahan: light; energy marker: darker tan
    # Invader sizes, as sqrt(piece area) / sqrt(board area).
    "city_min_size": 0.085,
    "explorer_max_fill": 0.62,  # explorers are spindly: they fill little of their bounding rectangle
}

HUE_NAMES = [(5, "red"), (20, "orange"), (35, "yellow"), (85, "green"), (100, "cyan"), (130, "blue"),
             (160, "purple"), (175, "magenta"), (181, "red")]


@dataclass
class PieceFeatures:
    hue: float
    saturation: float
    value: float
    texture: float  # spread of brightness inside the piece (blight is bumpy)
    size: float  # sqrt(area) / sqrt(board area)
    thickness: float  # inscribed radius / sqrt(board area)
    elongation: float  # long / short side of the minimum-area rectangle
    fill: float  # area / minimum-area rectangle area


def hue_name(hue: float) -> str:
    for limit, name in HUE_NAMES:
        if hue < limit:
            return name
    return "red"


def measure(image: np.ndarray, piece_mask: np.ndarray, board_area: float) -> PieceFeatures:
    """Features of one piece. `image` and `piece_mask` share a pixel grid; `board_area`
    is in that grid's pixels too."""
    mask = piece_mask.astype(np.uint8)
    core = cv2.erode(mask, np.ones((5, 5), np.uint8))  # skip the rim, where shadow and table mix in
    if core.sum() < 20:
        core = mask
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    px = hsv[core > 0].astype(np.float32)
    # Hue is circular; take the median of the angle-unwrapped values around the mean direction.
    angles = px[:, 0] * (2 * np.pi / 180)
    mean_angle = np.arctan2(np.sin(angles).mean(), np.cos(angles).mean())
    hue = float((np.degrees(mean_angle) / 2) % 180)
    area = float(mask.sum())
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    (_, _), (rw, rh), _ = cv2.minAreaRect(max(contours, key=cv2.contourArea))
    rect_area = max(rw * rh, 1.0)
    root = np.sqrt(max(board_area, 1.0))
    return PieceFeatures(
        hue=round(hue, 1),
        saturation=round(float(np.median(px[:, 1])), 1),
        value=round(float(np.median(px[:, 2])), 1),
        texture=round(float(np.std(px[:, 2])), 1),
        size=round(float(np.sqrt(area) / root), 4),
        thickness=round(float(cv2.distanceTransform(mask, cv2.DIST_L2, 5).max() / root), 4),
        elongation=round(float(max(rw, rh) / max(min(rw, rh), 1.0)), 2),
        fill=round(float(area / rect_area), 3),
    )


def classify(f: PieceFeatures, rules: dict = RULES) -> dict:
    """Best guess of the piece type, with the reason, for checking against photos."""
    lo, hi = rules["warm_hue"]
    warm = lo <= f.hue <= hi
    if f.value <= rules["blight_max_value"]:
        return {"type": "blight", "why": f"dark (value {f.value})"}
    if f.saturation >= rules["vivid_min_saturation"] and not (warm and f.value < rules["cream_min_value"]):
        return {"type": "presence", "colour": hue_name(f.hue), "why": f"vivid {hue_name(f.hue)} (sat {f.saturation})"}
    if f.saturation <= rules["white_max_saturation"] and f.value >= rules["white_min_value"]:
        if f.size >= rules["city_min_size"]:
            kind = "city"
        elif f.fill <= rules["explorer_max_fill"]:
            kind = "explorer"
        else:
            kind = "town"
        return {"type": kind, "why": f"white plastic, size {f.size}, fill {f.fill}"}
    if warm and f.value >= rules["cream_min_value"]:
        return {"type": "dahan", "why": f"light cream (sat {f.saturation}, value {f.value})"}
    if warm:
        return {"type": "energy", "why": f"tan cardboard (sat {f.saturation}, value {f.value})"}
    return {"type": "unknown", "why": "no rule matched"}


def describe(f: PieceFeatures) -> dict:
    return asdict(f)
