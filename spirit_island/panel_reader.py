"""Read the spirit panel in the camera's view: discs left on each presence track, and the
energy tokens lying on the panel's art.

The panel is found by matching its printed art (assets/spirits/<spirit>/panel_front.jpg)
and straightened onto that picture, so rows and areas are fixed positions on it.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .engine import rules

ASSETS = Path(__file__).resolve().parent / "assets" / "spirits"


class PanelReader:
    def __init__(self, spirit: str):
        self.spirit = spirit
        folder = rules.SPIRIT_ART[spirit][0]
        self.panel = cv2.imread(str(ASSETS / folder / "panel_front.jpg"))
        self.sift = cv2.SIFT_create(8000)
        self.kp, self.des = self.sift.detectAndCompute(cv2.cvtColor(self.panel, cv2.COLOR_BGR2GRAY), None)
        self.track = rules.PRESENCE_TRACKS[spirit]

    def read(self, frame: np.ndarray) -> dict | None:
        k = min(1.0, 2400 / max(frame.shape[:2]))
        small = cv2.resize(frame, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        kp, des = self.sift.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), None)
        if des is None:
            return None
        good = [a for a, b in (p for p in cv2.BFMatcher().knnMatch(self.des, des, k=2) if len(p) == 2)
                if a.distance < 0.75 * b.distance]
        if len(good) < 30:
            return None
        H, inl = cv2.findHomography(np.float32([self.kp[g.queryIdx].pt for g in good]),
                                    np.float32([kp[g.trainIdx].pt for g in good]), cv2.RANSAC, 6)
        if H is None or inl.sum() < 40:
            return None
        h, w = self.panel.shape[:2]
        warp = cv2.warpPerspective(frame, np.linalg.inv(np.diag([1 / k, 1 / k, 1]) @ H), (w, h))
        hsv = cv2.cvtColor(warp, cv2.COLOR_BGR2HSV)
        return {"taken": self._taken(hsv), "tokens": self._tokens(hsv)}

    def _taken(self, hsv) -> dict:
        """Discs gone from each track = circles - 1 (the first is never covered) - discs left."""
        t = self.track
        out = {}
        blue = ((hsv[..., 0] > 95) & (hsv[..., 0] < 125) & (hsv[..., 1] > 110) & (hsv[..., 2] > 60)).astype(np.uint8)
        # Wood grain breaks a disc's colour up: close the gaps, then look at each circle.
        blue = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
        r = int(0.3 * t["dx"])
        for row, y, n in (("energy", t["energy_y"], t["energy"]), ("cards", t["cards_y"], t["cards"])):
            covered = 0
            for i in range(1, n):
                x = int(t["x0"] + i * t["dx"])
                if blue[y - r:y + r, x - r:x + r].mean() > 0.35:
                    covered += 1
            out[row] = n - 1 - covered
        return out

    def _tokens(self, hsv) -> int:
        """Energy tokens (tan, round) lying on the panel's picture (left part, blue art)."""
        h, w = hsv.shape[:2]
        tan = ((hsv[..., 0] >= 5) & (hsv[..., 0] <= 28) & (hsv[..., 1] >= 50) & (hsv[..., 2] >= 90)).astype(np.uint8)
        tan[:, int(0.37 * w):] = 0          # the parchment half is tan itself
        tan[int(0.74 * h):, :] = 0          # the name banner
        tan[:int(0.02 * h), :] = 0
        tan = cv2.morphologyEx(tan, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        count, _, stats, _ = cv2.connectedComponentsWithStats(tan)
        one = 15000.0  # a token's area on the straightened panel
        return int(sum(max(1, round(s[4] / one)) for s in stats[1:] if s[4] > 0.5 * one))
