"""Recognise power cards lying face up in the board camera's view.

Power cards have detailed art, so each known card (the spirit's starting cards and its
progression cards) is found anywhere in the photo with SIFT features and a homography.
A watcher reads the newest photo during the spirit phase and keeps the list of cards in
view, so the Play powers step can show (and record) what was played.
"""

from __future__ import annotations

import threading
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from .engine import rules

ASSETS = Path(__file__).resolve().parent / "assets"
MIN_INLIERS = 60      # a card in view gives 150+; the background gives up to ~40
WATCH_STEPS = ("spirit.growth", "spirit.energy", "spirit.powers")


def card_paths(spirit: str) -> dict:
    out = {}
    art = rules.SPIRIT_ART.get(spirit)
    if art:
        folder, cards = art
        for c in cards:
            out[c] = ASSETS / "spirits" / folder / f"{rules.picture_slug(c)}.jpg"
    for c, _ in rules.PROGRESSION.get(spirit, []):
        out[c] = ASSETS / "powers" / f"{rules.picture_slug(c)}.jpg"
    return {k: v for k, v in out.items() if v.exists()}


class PowerCardReader:
    def __init__(self, paths: dict):
        self.sift = cv2.SIFT_create(8000)
        self.cards = []
        for name, path in paths.items():
            img = cv2.imread(str(path))
            kp, des = self.sift.detectAndCompute(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), None)
            if des is not None:
                self.cards.append((name, kp, des, (img.shape[1], img.shape[0])))

    def read(self, frame: np.ndarray) -> list:
        k = min(1.0, 2400 / max(frame.shape[:2]))
        small = cv2.resize(frame, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        kp, des = self.sift.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), None)
        if des is None:
            return []
        found = []
        matcher = cv2.BFMatcher()
        for name, ckp, cdes, (w, h) in self.cards:
            pairs = matcher.knnMatch(cdes, des, k=2)
            good = [a for a, b in (p for p in pairs if len(p) == 2) if a.distance < 0.75 * b.distance]
            if len(good) < MIN_INLIERS:
                continue
            H, inl = cv2.findHomography(np.float32([ckp[g.queryIdx].pt for g in good]),
                                        np.float32([kp[g.trainIdx].pt for g in good]), cv2.RANSAC, 6)
            n = int(inl.sum()) if inl is not None else 0
            if H is None or n < MIN_INLIERS:
                continue
            quad = cv2.perspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2), H).reshape(-1, 2)
            if not cv2.isContourConvex(quad):
                continue
            found.append({"name": name, "score": n, "quad": (quad / k).tolist()})
        return sorted(found, key=lambda f: -f["score"])


class PowerWatch:
    """Reads the power cards in view every couple of seconds during the spirit phase."""

    def __init__(self, store, snapshot_url: str, every: float = 2.5):
        self.store = store
        self.url = snapshot_url
        self.every = every
        self.reader = None
        self.spirit = None
        self.state: dict = {"active": False}
        self.lock = threading.Lock()
        self.recent: list = []
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="power-watch")
            self._thread.start()

    def public(self) -> dict:
        with self.lock:
            return dict(self.state)

    def _run(self):
        while True:
            s = self.store.game.state
            if s.get("step") in WATCH_STEPS and s.get("players"):
                try:
                    self._once(s)
                except Exception as e:  # camera hiccup
                    with self.lock:
                        self.state = {"active": True, "cards": [], "why": f"camera: {type(e).__name__}"}
            elif self.state.get("active"):
                with self.lock:
                    self.state, self.recent = {"active": False}, []
                self.store.broadcast(self.store.snapshot())
            time.sleep(self.every)

    def _once(self, s):
        spirit = s["players"][0]["spirit"]
        if self.reader is None or self.spirit != spirit:
            self.reader, self.spirit = PowerCardReader(card_paths(spirit)), spirit
        with urllib.request.urlopen(self.url, timeout=6) as r:
            frame = cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
        names = sorted(f["name"] for f in self.reader.read(frame))
        # Keep what two photos in a row agree on, so a card being moved doesn't flicker.
        self.recent = (self.recent + [names])[-2:]
        steady = sorted(set(self.recent[0]) & set(self.recent[-1])) if len(self.recent) == 2 else names
        cards = [{"name": n, "cost": rules.POWER_INFO.get(n, (None, None))[0],
                  "speed": rules.POWER_INFO.get(n, (None, None))[1]} for n in steady]
        changed = cards != self.state.get("cards")
        with self.lock:
            self.state = {"active": True, "cards": cards, "stamp": time.time(),
                          "cost": sum(c["cost"] or 0 for c in cards)}
        if changed:
            try:
                self.store.growth_from_presence()
            except Exception as e:
                print(f"growth suggestion failed: {e}")
            self.store.broadcast(self.store.snapshot())
