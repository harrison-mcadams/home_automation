"""Remember pieces between photos, so a change in the light can't make them vanish.

Fresh detection asks "what differs from the empty-board reference photo?". As the
sun moves, shadows and glare differ from that photo too, and pieces get lost in them
(or swallowed into one big "change"). But pieces don't vanish on their own: what we
saw a moment ago is the best guess for now.

So every piece we have seen is remembered with its type, where it sat (in reference
coordinates, which stay put however the camera or board moves) and what it looked
like. When a new photo's detection misses a remembered piece, we look for it right
where it was: if that spot still looks like the piece, and more like the piece than
like the empty board, it is still there. A piece missing for several photos in a row
is let go, so pieces really taken off the board do go away.

Brightness differences cancel out in the comparison (normalised correlation), which
is what makes this much more forgiving of the light than the change search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from spirit_island.perception.lands import land_at


def _gray(image: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)


def _crop(image, x, y, w, h):
    H, W = image.shape[:2]
    x0, y0, x1, y1 = max(0, int(x)), max(0, int(y)), min(W, int(x + w)), min(H, int(y + h))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None, (x0, y0)
    return image[y0:y1, x0:x1], (x0, y0)


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean(); b = b - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 1e-6 else 0.0


@dataclass
class Track:
    type: str
    colour: Optional[str]
    bbox: list            # [x, y, w, h] in reference pixels
    land: Optional[str]
    template: np.ndarray  # blurred grey patch of the piece, from the last photo it was seen in
    misses: int = 0
    seen: int = 1
    extra: dict = field(default_factory=dict)

    @property
    def centre(self):
        x, y, w, h = self.bbox
        return x + w / 2, y + h / 2


def _covers(a, b) -> bool:
    """True if box a and box b overlap enough to be the same piece."""
    if not a or not b:
        return False
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter > 0.3 * min(aw * ah, bw * bh)


class PieceMemory:
    def __init__(self, reference: np.ndarray, lands: Optional[tuple] = None,
                 keep_for: int = 12, min_score: float = 0.35, margin: float = 0.08, confirm: int = 2):
        self.reference = _gray(reference)
        self.lands = lands
        self.keep_for = keep_for      # photos a piece may go unseen before it's let go
        self.min_score = min_score    # how much the spot must still look like the piece
        self.margin = margin          # ... and by how much more than like the empty board
        self.confirm = confirm        # a new piece is only remembered once seen this many times
        self.tracks: list[Track] = []

    def _land(self, cx, cy, fallback):
        if self.lands is None:
            return fallback
        labels, names = self.lands
        return land_at(labels, names, cx, cy) or fallback

    def _find(self, track: Track, aligned: np.ndarray):
        """Look for a remembered piece near where it was. Returns (score, bbox) or None."""
        x, y, w, h = track.bbox
        pad = int(0.6 * max(w, h))
        window, (wx, wy) = _crop(aligned, x - pad, y - pad, w + 2 * pad, h + 2 * pad)
        t = track.template
        if window is None or window.shape[0] < t.shape[0] or window.shape[1] < t.shape[1]:
            return None
        res = cv2.matchTemplate(window, t, cv2.TM_CCOEFF_NORMED)
        _, score, _, (bx, by) = cv2.minMaxLoc(res)
        nx, ny = wx + bx, wy + by
        here, _ = _crop(aligned, nx, ny, t.shape[1], t.shape[0])
        empty, _ = _crop(self.reference, nx, ny, t.shape[1], t.shape[0])
        if here is None or empty is None or empty.shape != here.shape:
            return None
        # Would this spot pass for the empty board? Then the piece has gone.
        board_like = _ncc(here, empty)
        if score >= self.min_score and score >= board_like + self.margin:
            return round(float(score), 2), [int(nx), int(ny), int(t.shape[1]), int(t.shape[0])], round(board_like, 2)
        return None

    def update(self, result: dict) -> dict:
        """Add remembered pieces the detection missed to `result["pieces"]` (in place)."""
        aligned = result.get("_aligned")
        if not result.get("registered") or aligned is None:
            return result  # can't line up this photo: change nothing, remember everything
        gray = _gray(aligned)
        pieces = result["pieces"]
        free = list(range(len(self.tracks)))
        for p in pieces:
            if p.get("type") in (None, "unknown", "table") or not p.get("reference_bbox"):
                continue
            x, y, w, h = p["reference_bbox"]
            cx, cy = x + w / 2, y + h / 2
            best, bd = None, 0.9 * max(w, h, 1)
            for i in free:
                t = self.tracks[i]
                if t.type != p["type"] or t.colour != p.get("colour"):
                    continue
                d = float(np.hypot(t.centre[0] - cx, t.centre[1] - cy))
                if d < bd:
                    best, bd = i, d
            patch, _ = _crop(gray, x, y, w, h)
            if patch is None:
                continue
            if best is not None:
                free.remove(best)
                t = self.tracks[best]
                t.bbox, t.land, t.misses, t.seen = [x, y, w, h], p.get("land"), 0, t.seen + 1
                t.template = patch.copy()
            else:
                self.tracks.append(Track(p["type"], p.get("colour"), [x, y, w, h], p.get("land"), patch.copy()))
        for i in free:
            t = self.tracks[i]
            if t.seen < self.confirm:
                t.misses = self.keep_for  # seen once and not again: a passing shadow or glint
                continue
            found = self._find(t, gray)
            if found is None:
                t.misses += 1  # not seen this time; it gets a few more photos before it's let go
                continue
            score, bbox, board_like = found
            # Already covered by a piece seen in this photo (its blob just came out a
            # different shape, e.g. with its shadow): don't count it twice.
            if any(_covers(p.get("reference_bbox"), bbox) for p in pieces if not p.get("remembered")):
                t.misses = 0
                continue
            t.bbox, t.misses = bbox, 0
            cx, cy = t.centre
            t.land = self._land(cx, cy, t.land)
            x, y, w, h = bbox
            corners = np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h], [cx, cy]])
            H = result.get("_homography")
            if H is not None:  # back into the photo's own pixels, for drawing on it
                corners = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), np.linalg.inv(H)).reshape(-1, 2)
            pieces.append({
                "outline": [[round(float(px)), round(float(py))] for px, py in corners[:4]],
                "centroid": [round(float(corners[4][0])), round(float(corners[4][1]))],
                "type": t.type, "colour": t.colour, "land": t.land, "reference_bbox": bbox,
                "remembered": True, "sure": True,
                "why": f"remembered: the spot still looks like this {t.type} ({score} vs empty board {board_like})",
            })
        # Tracks that went unmatched and weren't found are dropped once they've missed too often.
        unseen_dropped = {id(t) for i in free for t in [self.tracks[i]] if t.misses >= self.keep_for}
        self.tracks = [t for t in self.tracks if id(t) not in unseen_dropped]
        result["remembered"] = sum(1 for p in pieces if p.get("remembered"))
        result["tracked"] = len(self.tracks)
        return result
