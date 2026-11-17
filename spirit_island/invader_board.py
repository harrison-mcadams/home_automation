"""Read the invader cards lying in the Ravage, Build and Explore spaces of the invader board.

The invader board is found in the photo by matching its printed art (the base-game board
from the Tabletop Simulator mod, assets/components/invader_board_art.jpg). Each card space
is then cut out and straightened to a card, and compared with the 15 invader card faces,
the three stage backs and the empty space, by colour layout (a small, brightness-evened
Lab picture). A face-down card on Explore is the invader deck.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ART = HERE / "assets" / "components" / "invader_board_art.jpg"
CARDS = HERE / "assets" / "components" / "invader"
BACKS = HERE / "assets" / "components"

# Card spaces on the board art, as fractions of its width and height (x, y, w, h).
SLOTS = {
    "explore": (.843, .716, .14, .232),
    "build": (.671, .716, .136, .232),
    "ravage": (.5, .716, .139, .232),
    "discard": (.257, .716, .21, .15),
}
CARD_PX = (40, 60)  # cards are compared at this size


def _sig(img: np.ndarray, shift=None) -> np.ndarray:
    """Small Lab picture of a card with its overall brightness taken out (and the room's
    colour cast, when `shift` gives it)."""
    lab = cv2.cvtColor(cv2.resize(img, CARD_PX, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2LAB).astype(np.float32)
    if shift is not None:
        lab -= shift
    lab = cv2.GaussianBlur(lab, (5, 5), 0)
    lab[..., 0] -= lab[..., 0].mean()
    lab[..., 0] *= 0.5  # light and shade count less than colour
    m = 4  # skip the edge, where the cut may include the board around the card
    return lab[m:-m, m:-m]


class InvaderBoardReader:
    def __init__(self):
        self.sift = cv2.SIFT_create(6000)
        art = cv2.imread(str(ART))
        if art is None:
            raise FileNotFoundError(ART)
        self.art_size = (art.shape[1], art.shape[0])
        self.kp, self.des = self.sift.detectAndCompute(cv2.cvtColor(art, cv2.COLOR_BGR2GRAY), None)
        self.refs = []
        for path in sorted(CARDS.glob("*.jpg")):
            stage, code = path.stem.split("_", 1)
            self.refs.append(("face", code, int(stage), _sig(cv2.imread(str(path)))))
        for s in (1, 2, 3):
            back = cv2.imread(str(BACKS / f"stage{s}_back.jpg"))
            if back is not None:
                self.refs.append(("back", None, s, _sig(back)))
        self.art = art
        # The backs all share one detailed picture (explorers landing): found by features,
        # which the colour comparison can't tell from a face.
        back = cv2.imread(str(BACKS / "stage1_back.jpg"))
        self.back_kp, self.back_des = self.sift.detectAndCompute(cv2.cvtColor(back, cv2.COLOR_BGR2GRAY), None)
        self.empty = {}
        aw, ah = self.art_size
        for slot, (x, y, w, h) in SLOTS.items():
            crop = art[int(y * ah):int((y + h) * ah), int(x * aw):int((x + w) * aw)]
            self.empty[slot] = _sig(crop)

    def locate(self, frame: np.ndarray):
        """Homography from board-art pixels to frame pixels, or None if the board isn't in view."""
        k = min(1.0, 1600 / max(frame.shape[:2]))
        small = cv2.resize(frame, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        kp, des = self.sift.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), None)
        if des is None:
            return None
        good = [a for a, b in (p for p in cv2.BFMatcher().knnMatch(self.des, des, k=2) if len(p) == 2)
                if a.distance < 0.75 * b.distance]
        if len(good) < 25:
            return None
        H, inl = cv2.findHomography(np.float32([self.kp[g.queryIdx].pt for g in good]),
                                    np.float32([kp[g.trainIdx].pt for g in good]), cv2.RANSAC, 5)
        if H is None or inl.sum() < 25:
            return None
        return np.diag([1 / k, 1 / k, 1]) @ H

    def _is_back(self, frame, quad) -> bool:
        """A face-down invader card (the deck) in this space, by matching the back's art."""
        big = cv2.getPerspectiveTransform(quad.astype(np.float32), np.float32([[0, 0], [400, 0], [400, 600], [0, 600]]))
        crop = cv2.warpPerspective(frame, big, (400, 600))
        kp, des = self.sift.detectAndCompute(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), None)
        if des is None or len(kp) < 10:
            return False
        good = [a for a, b in (p for p in cv2.BFMatcher().knnMatch(self.back_des, des, k=2) if len(p) == 2)
                if a.distance < 0.75 * b.distance]
        if len(good) < 10:
            return False
        H, inl = cv2.findHomography(np.float32([self.back_kp[g.queryIdx].pt for g in good]),
                                    np.float32([kp[g.trainIdx].pt for g in good]), cv2.RANSAC, 6)
        return H is not None and inl.sum() >= 25  # the deck gives ~80; card faces and the board under 15

    def read(self, frame: np.ndarray) -> dict:
        H = self.locate(frame)
        if H is None:
            return {"found": False}
        aw, ah = self.art_size
        out = {"found": True, "slots": {}, "outlines": {}, "H": H, "art_size": (aw, ah)}
        # The room light tints everything (warm evening light): measure the tint on the
        # board's own printed art, away from the card spaces, and take it out of the cards.
        seen = cv2.warpPerspective(frame, np.linalg.inv(H), (aw, ah))
        keep = np.ones((ah, aw), bool)
        for x, y, w, h in SLOTS.values():
            keep[int(y * ah):int((y + h) * ah), int(x * aw):int((x + w) * aw)] = False
        keep &= seen.sum(-1) > 0
        a = cv2.cvtColor(self.art, cv2.COLOR_BGR2LAB).astype(np.float32)[keep]
        b = cv2.cvtColor(seen, cv2.COLOR_BGR2LAB).astype(np.float32)[keep]
        shift = np.median(b - a, axis=0) if len(a) > 1000 else None
        for slot, (x, y, w, h) in SLOTS.items():
            box = np.float32([[x * aw, y * ah], [(x + w) * aw, y * ah], [(x + w) * aw, (y + h) * ah], [x * aw, (y + h) * ah]])
            quad = cv2.perspectiveTransform(box.reshape(-1, 1, 2), H).reshape(-1, 2)
            out["outlines"][slot] = quad.tolist()
            if slot == "discard":
                continue  # the discard space is landscape and holds a pile; not needed for play
            W, Hh = 240, 360
            M = cv2.getPerspectiveTransform(quad, np.float32([[0, 0], [W, 0], [W, Hh], [0, Hh]]))
            card = cv2.warpPerspective(frame, M, (W, Hh))
            if self._is_back(frame, quad):
                out["slots"][slot] = {"card": None, "kind": "back", "dist": 0.0}
                continue
            sig = _sig(card, shift)
            flipped = _sig(cv2.rotate(card, cv2.ROTATE_180), shift)  # cards can lie either way up
            empty = float(np.sqrt(((sig - self.empty[slot]) ** 2).sum(-1)).mean())

            def dist(ref):
                return min(float(np.sqrt(((sig - ref) ** 2).sum(-1)).mean()),
                           float(np.sqrt(((flipped - ref) ** 2).sum(-1)).mean()))
            scored = sorted(((dist(r[3]), i, r) for i, r in enumerate(self.refs)), key=lambda t: t[0])
            scored = [(d, r) for d, _, r in scored]
            d, (kind, code, stage, _) = scored[0]
            if empty < d:
                out["slots"][slot] = {"card": None, "kind": "empty", "dist": round(empty, 1)}
            else:
                # The best other answer that would mean something different.
                second = next((dd for dd, r in scored[1:] if r[1] != code or r[0] != kind), 99.0)
                out["slots"][slot] = {"card": code if kind == "face" else None, "kind": kind, "stage": stage,
                                      "dist": round(d, 1), "margin": round(second - d, 1)}
        return out
