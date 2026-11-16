"""Tell what a detected piece is from its colour, size and shape.

A first, rule-based classifier for the pieces in Harrison's set, as seen from the
overhead camera (see the project notes for what each looks like):

    explorer, town, city   white plastic figures (read cool/blue-ish): explorer thinnest,
                           city big and squat, town the rest
    dahan                  plain cream wooden disc (warm hue, smooth)
    presence               wooden disc in a spirit's colour (saturated)
    blight                 blue-grey bumpy plastic
    energy                 tan cardboard marker with a printed value (warm, textured, larger)

Sizes are measured relative to the board, so they don't change with camera distance.
The thresholds live in RULES so they can be tuned against labelled photos.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

RULES = {
    # Measured on Harrison's set under the Pixel 6 (r7-r9 layouts, 2026-11-16). Colour is
    # OpenCV HSV (hue 0-180, saturation and value 0-255), the median of the piece's core.
    "vivid_min_saturation": 105,  # presence discs: S 115-165; nothing else above ~90
    "dark_max_value": 100,
    "presence_min_value": 130,  # painted discs are bright (V 204-230); dark saturated brown is wood  # anything this dark is blight, whatever its hue
    "blight_hue": (85, 125),  # blight is blue-grey: H 100-103, S 79-91, V 116-129
    "blight_min_saturation": 60,
    "blight_max_value": 175,
    "warm_hue": (5, 35),  # cream dahan (H 21-24) and tan cardboard (H 19-21); white plastic is H 70-109
    "pale_max_saturation": 70,  # white plastic S 27-58 (bluish white balance), dahan S 38-58
    "pale_min_value": 170,
    "disc_max_elongation": 1.5,  # dahan 1.08-1.35; explorers 1.7-2.1
    "disc_min_fill": 0.72,  # dahan 0.78-0.84; an explorer with sand in its gaps 0.64
    "dahan_min_value": 130,  # dahan V 202-219; leaves room for shade
    "energy_min_texture": 20,  # printed card: texture 25-32; dahan 7-25 (dim light), presence 4-17
    "energy_min_size": 0.085,  # energy marker 0.093-0.096; dahan 0.065-0.072, presence up to 0.082
    # White plastic invaders. Sizes are sqrt(piece area) / sqrt(board area).
    "explorer_max_thickness": 0.030,  # spindly: 0.025-0.0265; town and city 0.035-0.040
    "city_min_size": 0.075,  # city 0.080-0.083; explorer 0.065-0.070
    "city_max_elongation": 1.35,  # city 1.03-1.11
    "bad_segment_max_fill": 0.5,  # a cut through touching pieces leaves ragged shapes
}

HUE_NAMES = [(5, "red"), (20, "orange"), (35, "yellow"), (85, "green"), (100, "cyan"), (125, "blue"),
             (135, "purple"), (170, "magenta"), (181, "red")]


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
    """Best guess of the piece type, with the reason, for checking against photos.

    Hue does most of the work: under the camera's white balance the white plastic reads
    cool (blue-ish) while the wooden dahan and cardboard read warm, even though both are
    pale with similar saturation.
    """
    lo, hi = rules["warm_hue"]
    warm = lo <= f.hue <= hi
    blo, bhi = rules["blight_hue"]
    out: dict
    # Dahan are round discs. A long, ragged blob with a warm hue is a white figure with tan
    # sand showing through its gaps, which pulls the average colour warm.
    disc = f.elongation <= rules["disc_max_elongation"] and f.fill >= rules["disc_min_fill"]
    blue_grey = blo <= f.hue <= bhi and f.saturation >= rules["blight_min_saturation"]
    # The energy marker is both printed and clearly larger than a disc; a dim dahan can get
    # as textured (up to 25), so size must agree.
    printed = f.texture >= rules["energy_min_texture"] and f.size >= rules["energy_min_size"]
    if f.value <= rules["dark_max_value"] and (f.saturation < rules["blight_min_saturation"] or blue_grey):
        # Dark and grey or blue-grey. Dark *brown* is table wood showing at a moved board's rim.
        out = {"type": "blight", "why": f"dark (value {f.value})"}
    elif warm and printed and f.value > rules["dark_max_value"]:
        # Before presence: in warm sunlight the tan card can get as saturated as a yellow disc,
        # but it stays textured (printed) and larger.
        out = {"type": "energy", "why": f"tan, printed (texture {f.texture}, size {f.size})"}
    elif f.saturation >= rules["vivid_min_saturation"] and f.value >= rules["presence_min_value"]:
        out = {"type": "presence", "colour": hue_name(f.hue), "why": f"vivid {hue_name(f.hue)} (sat {f.saturation})"}
    elif blue_grey and f.value <= rules["blight_max_value"]:
        out = {"type": "blight", "why": f"blue-grey (hue {f.hue}, sat {f.saturation}, value {f.value})"}
    elif warm and f.value >= rules["dahan_min_value"] and disc:
        out = {"type": "dahan", "why": f"plain cream (hue {f.hue}, texture {f.texture})"}
    elif f.saturation <= rules["pale_max_saturation"] and f.value >= rules["pale_min_value"]:
        if f.thickness <= rules["explorer_max_thickness"]:
            kind = "explorer"
        elif f.size >= rules["city_min_size"] and f.elongation <= rules["city_max_elongation"]:
            kind = "city"
        else:
            kind = "town"
        out = {"type": kind, "why": f"white plastic, thickness {f.thickness}, size {f.size}, elongation {f.elongation}"}
    elif warm and f.value < rules["dahan_min_value"]:
        # Darker than any cream or tan piece, brownish: the wooden table, uncovered at the
        # rim when the board slides.
        out = {"type": "table", "why": f"dark brown (hue {f.hue}, value {f.value}): table wood"}
    else:
        out = {"type": "unknown", "why": f"no rule matched (hue {f.hue}, sat {f.saturation}, value {f.value})"}
    out["sure"] = f.fill > rules["bad_segment_max_fill"]
    if not out["sure"]:
        out["why"] += f"; ragged outline (fill {f.fill}), may be cut wrongly from a touching piece"
    return out


def describe(f: PieceFeatures) -> dict:
    return asdict(f)
