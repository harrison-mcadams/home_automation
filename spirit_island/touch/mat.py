"""Find the dark input mat, and any card lying on it.

The mat is the largest dark, low-colour patch in view: matte black or charcoal against
Harrison's brown wooden table. It is found afresh in every look, so a moved mat or a
bumped camera only costs one look. Cards are pale rectangles inside it.
"""

from __future__ import annotations

import cv2
import numpy as np

CARD_ASPECT = (0.55, 0.85)   # short side / long side: power and invader cards are ~0.71
MIN_MAT_FRAC = 0.03          # the mat covers at least this much of the frame


def find_mat(frame_bgr, hands=None):
    """-> {"box": 4 corner points (float, image pixels), "width", "height", "mask"} or None.

    `hands` (landmark lists) are painted out first so a hand on the mat doesn't split it."""
    h, w = frame_bgr.shape[:2]
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1].astype(np.int32), hsv[..., 2].astype(np.int32)
    med_v = float(np.median(v))
    # Dark compared with the rest of the scene, and not strongly coloured (wood is
    # orange-brown; a black mat stays grey even in warm light).
    dark = (v < max(35.0, 0.55 * med_v)) & ((s < 110) | (v < 30))
    mask = dark.astype(np.uint8) * 255
    if hands:
        for lm in hands:
            hull = cv2.convexHull(np.array(lm, np.int32))
            cv2.fillConvexPoly(mask, hull, 255)  # treat the hand as part of whatever it covers
    k = max(3, int(min(h, w) * 0.01)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    k2 = max(5, int(min(h, w) * 0.03)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k2, k2)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < MIN_MAT_FRAC * h * w:
        return None
    rect = cv2.minAreaRect(c)
    # A mat is a solid rectangle: most of its bounding rectangle should be dark.
    if area < 0.7 * rect[1][0] * rect[1][1]:
        return None
    box = cv2.boxPoints(rect)
    region = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(region, box.astype(np.int32), 255)
    return {"box": box.tolist(), "width": max(rect[1]), "height": min(rect[1]), "mask": region,
            "centre": rect[0]}


def inside(mat, pt, margin=0):
    if not mat:
        return False
    return cv2.pointPolygonTest(np.array(mat["box"], np.float32), (float(pt[0]), float(pt[1])), True) >= -margin


def find_cards(frame_bgr, mat, hands=None):
    """Pale card-shaped rectangles on the mat -> list of {"box", "centre", "size"}."""
    if not mat:
        return []
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    v = hsv[..., 2]
    on_mat = mat["mask"] > 0
    if not on_mat.any():
        return []
    mat_v = float(np.median(v[on_mat]))
    bright = ((v > mat_v + 45) & on_mat).astype(np.uint8) * 255
    if hands:
        for lm in hands:
            cv2.fillConvexPoly(bright, cv2.convexHull(np.array(lm, np.int32)), 0)
    k = 5
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mat_area = mat["width"] * mat["height"]
    out = []
    for c in contours:
        a = cv2.contourArea(c)
        if not (0.02 * mat_area <= a <= 0.4 * mat_area):
            continue
        rect = cv2.minAreaRect(c)
        long_, short = max(rect[1]), min(rect[1])
        if long_ <= 0 or not (CARD_ASPECT[0] <= short / long_ <= CARD_ASPECT[1]):
            continue
        if a < 0.8 * long_ * short:
            continue  # not a solid rectangle
        out.append({"box": cv2.boxPoints(rect).tolist(), "centre": rect[0], "size": (short, long_)})
    return out


def card_crop(frame_bgr, card, out_size=(252, 352)):
    """Straighten a card from the frame to an upright picture (for showing it big, and
    later for matching it against the card library)."""
    box = np.array(card["box"], np.float32)
    # Order corners so the long side runs top to bottom.
    s = box.sum(1)
    d = np.diff(box, axis=1).ravel()
    tl, br, tr, bl = box[np.argmin(s)], box[np.argmax(s)], box[np.argmin(d)], box[np.argmax(d)]
    src = np.array([tl, tr, br, bl], np.float32)
    if np.linalg.norm(tr - tl) > np.linalg.norm(bl - tl):  # lying sideways: rotate
        src = np.array([bl, tl, tr, br], np.float32)
    w, h = out_size
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
    return cv2.warpPerspective(frame_bgr, cv2.getPerspectiveTransform(src, dst), (w, h))


class CardWatch:
    """A card counts as laid down once it has stayed put for `settle_s`; it is reported
    once, then again only after it leaves."""

    def __init__(self, settle_s=0.4):
        self.settle_s = settle_s
        self._seen = {}  # rounded centre -> first seen time
        self._reported = set()

    def update(self, t, cards):
        events, now = [], {}
        for c in cards:
            key = (round(c["centre"][0] / 25), round(c["centre"][1] / 25))
            match = next((k for k in self._seen if abs(k[0] - key[0]) <= 1 and abs(k[1] - key[1]) <= 1), key)
            now[match] = self._seen.get(match, t)
            if t - now[match] >= self.settle_s and match not in self._reported:
                self._reported.add(match)
                events.append({"kind": "card_down", "card": c})
        for k in set(self._reported) - set(now):
            self._reported.discard(k)
            events.append({"kind": "card_up"})
        self._seen = now
        return events
