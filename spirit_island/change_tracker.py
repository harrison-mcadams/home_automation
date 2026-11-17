"""Follow the island by what changes, the way a scorekeeper does.

Reading every piece from scratch in each photo is fragile: pieces bunch up, shadows
merge them, and dim light makes white plastic look like the board. But the game is
already tracked, so the camera only has to answer a much easier question: *what changed
since the last time the board was still?*

Every photo is lined up to the board (so the camera or the board can move), and compared
with the last still photo, the baseline:

- taken moments apart, the two photos share the same light, so light never matters;
- a piece put down or taken off is one compact patch of change in one land, however
  crowded that land is, and is named from its colour and size alone;
- when the board is still again, that photo becomes the new baseline, so slow changes in
  light, or a bumped camera, are absorbed instead of piling up.

Each change becomes an event {land, piece, delta} for the game to accept in the light of
the current step (a white piece appearing during Build is the building that step expects).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from vision.changes import change_map
from vision.register import register, warp_to_reference

from .perception import lands as land_map

WORK = 1600          # long side of the lined-up working picture
MIN_PIECE = 0.0012   # smallest change that can be a piece, as a share of the board
MAX_PIECE = 0.03     # bigger than any piece or two: a hand, an arm, something left on the board
MOVED = 0.02         # board corners moving this much (of the board's size) = camera or board moved
# Shares of the board a white figure's change covers (with its shadow), at this scale.
EXPLORER_MAX, TOWN_MAX = 0.0034, 0.0066


class Board:
    def __init__(self, folder: Path):
        self.reference = cv2.imread(str(folder / "reference.jpg"))
        self.mask = cv2.imread(str(folder / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
        labels, self.names = land_map.load(folder)
        self.k = WORK / max(self.reference.shape[:2])
        small = lambda m, i: cv2.resize(m, None, fx=self.k, fy=self.k, interpolation=i)  # noqa: E731
        self.labels = small(labels, cv2.INTER_NEAREST)
        self.region = cv2.erode(small(self.mask, cv2.INTER_NEAREST), np.ones((7, 7), np.uint8))
        self.empty = small(self.reference, cv2.INTER_AREA)
        self.area = max(1, int((self.region > 0).sum()))
        x, y, w, h = cv2.boundingRect(self.mask)
        self.corners = np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]]).reshape(-1, 1, 2)
        self.size = float(np.hypot(w, h))


def classify(pixels_bgr: np.ndarray, share: float) -> tuple[str, str]:
    """(piece, why) for one patch of change, from the colours inside it and its size."""
    hsv = cv2.cvtColor(pixels_bgr.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    blue = float(((h > 92) & (h < 128) & (s > 110) & (v > 60)).mean())
    tan = float(((h >= 6) & (h <= 28) & (s >= 85) & (v >= 120)).mean())
    dark = float(((v < 115) & (s < 80)).mean())
    pale = float(((s < 75) & (v >= 125)).mean())
    if blue > 0.3:
        return "presence", f"blue disc ({blue:.0%} blue)"
    if tan > 0.3 and tan >= pale:
        return "dahan", f"tan wood ({tan:.0%} tan)"
    if dark > 0.45 and pale < 0.2:
        return "blight", f"dark piece ({dark:.0%} dark)"
    kind = "explorers" if share <= EXPLORER_MAX else "towns" if share <= TOWN_MAX else "cities"
    return kind, f"white plastic ({pale:.0%} pale), size {share:.4f}"


class ChangeTracker:
    def __init__(self, boards_dir: str | Path, namer="auto"):
        self.boards_dir = Path(boards_dir)
        # The recogniser trained on Harrison's own pieces (piece_pixels), when there is one.
        if namer == "auto":
            try:
                from .piece_pixels import PixelPieces
                namer = PixelPieces()
            except Exception as e:  # no trained model: fall back to colour rules
                print(f"change tracker: no trained piece model ({e}); using colour rules")
                namer = None
        self.namer = namer
        self.boards: dict = {}
        self.letter = None
        self.baseline = None      # lined-up picture of the board when it was last still
        self.base_corners = None  # where the board's corners were in that photo
        self.prev = None          # the previous photo, to tell "still" from "moving"
        self.status = "starting"

    def board(self, letter: str) -> Board:
        if letter not in self.boards:
            self.boards[letter] = Board(self.boards_dir / letter)
        return self.boards[letter]

    def _align(self, b: Board, image: np.ndarray):
        reg = register(b.reference, image, reference_mask=b.mask)
        if reg is None or not reg.ok:
            return None, None
        aligned = warp_to_reference(image, reg, b.reference.shape)
        corners = cv2.perspectiveTransform(b.corners, np.linalg.inv(reg.homography)).reshape(-1, 2)
        return cv2.resize(aligned, None, fx=b.k, fy=b.k, interpolation=cv2.INTER_AREA), corners

    def _stuff(self, b: Board, frame: np.ndarray) -> np.ndarray:
        """Where a photo shows something that isn't the empty board (pieces and their shadows)."""
        return (change_map(b.empty, frame, b.region, zones=b.labels) > 18) & (b.region > 0)

    def _patches(self, b: Board, old: np.ndarray, new: np.ndarray, close: int = 9):
        """Compact patches where two lined-up photos differ: [(mask, share of board)], large."""
        diff = change_map(old, new, b.region, zones=b.labels)
        inside = diff[b.region > 0]
        med = float(np.median(inside))
        mad = float(np.median(np.abs(inside - med))) + 1e-6
        m = ((diff > max(16.0, med + 9 * mad)) & (b.region > 0)).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        # A white piece set down against another white piece barely changes where they overlap:
        # close generously so one placement is one patch.
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close)))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        out, large = [], 0.0
        for i in range(1, n):
            share = stats[i][4] / b.area
            if share < MIN_PIECE:
                continue
            # A thin sliver is the edge of a piece seen from a slightly different angle.
            thick = cv2.distanceTransform((lab == i).astype(np.uint8), cv2.DIST_L2, 3).max()
            if thick < 0.012 * np.sqrt(b.area):
                continue
            if share > MAX_PIECE:
                large += share
                continue
            out.append((lab == i, share, (diff > 16) & (lab == i)))
        return out, large

    def _name_pixels(self, b: Board, frame: np.ndarray) -> np.ndarray:
        from .piece_pixels import name_pixels
        return name_pixels(self.namer.pix, b, frame)

    def _name(self, b: Board, frame, names, mask, has):
        """(piece, why) from the trained recogniser, for the piece inside this patch."""
        from .piece_pixels import COLOURS, WHITE, white_features
        inside = names[mask & has] if (mask & has).any() else names[mask]
        counts = np.bincount(inside, minlength=len(COLOURS))[1:]
        if counts.sum() < 30:
            return None
        colour = COLOURS[1 + int(counts.argmax())]
        share = counts.max() / max(1, counts.sum())
        if colour != "white":
            return colour, f"trained: {colour} ({share:.0%} of the piece's pixels)"
        # The piece's white, tidied the way the recogniser was trained (its biggest blob).
        from .piece_pixels import white_blobs
        grow = cv2.dilate(mask.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        blobs = white_blobs(b, grow & (names == 1))
        if not blobs:
            return None
        white, (x, y, w, h) = max(blobs, key=lambda t: t[0].sum())
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        p = self.namer.white.predict_proba([white_features(b, white, gray, (x, y, w, h))])[0]
        kind = WHITE[int(p.argmax())]
        return kind, f"trained: white plastic, shaped like a {kind[:-1] if kind != 'cities' else 'city'} ({p.max():.0%})"

    def update(self, image: np.ndarray, letter: str) -> list:
        """Feed one photo; returns the events since the last still board (usually none)."""
        b = self.board(letter)
        if letter != self.letter:
            self.letter, self.baseline, self.prev = letter, None, None
        now, corners = self._align(b, image)
        if now is None:
            self.status, self.prev = "can't see the board (covered or out of view)", None
            return []
        if self.baseline is None:
            self.baseline, self.base_corners, self.prev = now, corners, now
            self.status = "watching"
            return []
        if self.prev is None:  # the board was out of view (a hand over it): start the stillness check again
            self.prev = now
            self.status = "watching"
            return []
        # Still? (compared with the photo just before)
        moving, big = self._patches(b, self.prev, now)
        self.prev = now
        if moving or big:
            self.status = "something is moving on the board"
            return []
        # The camera or the board moved: pieces are seen from a new angle, so every piece
        # would look changed. Start again from this photo.
        if float(np.abs(corners - self.base_corners).max()) > MOVED * b.size:
            self.baseline, self.base_corners = now, corners
            self.status = "the camera or board moved; watching again"
            return []
        patches, big = self._patches(b, self.baseline, now, close=int(0.035 * np.sqrt(b.area)) | 1)
        if big:
            self.status = "something large is on the board"
            return []
        events = []
        if not patches:
            self.baseline, self.base_corners = now, corners
            self.status = "watching"
            return []
        stuff_old, stuff_new = self._stuff(b, self.baseline), self._stuff(b, now)
        named = {}  # pixel names per photo, worked out only when needed
        for mask, _, changed in patches:
            vals = b.labels[mask]
            vals = vals[vals > 0]
            if len(vals) == 0:
                continue
            land = b.names[int(np.bincount(vals).argmax()) - 1]
            if land == "ocean":
                continue
            # More "not the empty board" than before = something was added; less = taken off.
            # About the same = a piece nudged.
            n_old, n_new = int(stuff_old[mask].sum()), int(stuff_new[mask].sum())
            net = (n_new - n_old) / b.area
            if abs(net) < 0.6 * MIN_PIECE:
                continue
            delta = 1 if net > 0 else -1
            frame, has = (now, stuff_new) if delta > 0 else (self.baseline, stuff_old)
            px = frame[changed & has]
            if len(px) < 20:
                px = frame[mask]
            piece, why = classify(px, abs(net))
            if self.namer is not None:
                key = "now" if delta > 0 else "base"
                if key not in named:
                    named[key] = self._name_pixels(b, frame)
                got = self._name(b, frame, named[key], mask, has)
                if got:
                    piece, why = got
            events.append({"land": land, "piece": piece, "delta": delta, "share": round(abs(net), 4), "why": why})
        self.baseline, self.base_corners = now, corners
        self.status = "watching"
        return events
