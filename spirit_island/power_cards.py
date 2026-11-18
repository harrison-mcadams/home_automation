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
WATCH_STEPS = ("spirit.growth", "spirit.energy", "spirit.powers", "fast", "slow")


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
        # The spirit panel: discs gone from the tracks, energy tokens on it. Kept when two
        # photos in a row agree.
        panel = None
        if spirit in rules.PRESENCE_TRACKS:
            from .panel_reader import PanelReader
            if getattr(self, "panel_reader", None) is None or self.panel_reader.spirit != spirit:
                self.panel_reader = PanelReader(spirit)
            p = self.panel_reader.read(frame)
            self.panel_recent = (getattr(self, "panel_recent", []) + [p])[-2:]
            if p and len(self.panel_recent) == 2 and self.panel_recent[0] == p:
                panel = p
        # Keep what two photos in a row agree on, so a card being moved doesn't flicker.
        self.recent = (self.recent + [names])[-2:]
        steady = sorted(set(self.recent[0]) & set(self.recent[-1])) if len(self.recent) == 2 else names
        cards = [{"name": n, "cost": rules.POWER_INFO.get(n, (None, None))[0],
                  "speed": rules.POWER_INFO.get(n, (None, None))[1]} for n in steady]
        changed = cards != self.state.get("cards") or (panel and panel != self.state.get("panel"))
        with self.lock:
            self.state = {"active": True, "cards": cards, "stamp": time.time(),
                          "cost": sum(c["cost"] or 0 for c in cards),
                          "panel": panel or self.state.get("panel")}
        if changed:
            for hook in (self.store.panel_sync, self.store.growth_from_presence):
                try:
                    hook()
                except Exception as e:
                    print(f"{hook.__name__} failed: {e}")
            self.store.broadcast(self.store.snapshot())


CARD_STEPS = ("spirit.powers", "fast", "slow")
CARD_EVERY_S = 1.0     # read the cards in view this often
CARD_KEEP = 3          # a card missing from this many reads in a row is gone (a hand over it)


class CardWatch:
    """The power cards lying in the gesture camera's view, read from its own frames (no
    second camera connection). Each card's outline is kept, so pointing at it can play it.
    Reads only cards: the app, not the camera, keeps energy and the board."""
    kinds = {"card"}

    def __init__(self, store, every=CARD_EVERY_S):
        self.store = store
        self.every = every
        self.reader = None
        self.spirit = None
        self._frame = None
        self.frame_size = None
        self.seen = {}            # name -> {"quad": [...], "missed": n}
        self.status = "off"
        self.lock = threading.Lock()
        self._stop = threading.Event()

    # -- pointing ------------------------------------------------------------------------
    def give_frame(self, frame):
        self._frame = frame

    def target_at(self, pt):
        with self.lock:
            items = list(self.seen.items())
        for name, c in items:
            quad = np.float32(c["quad"]).reshape(-1, 1, 2)
            if cv2.pointPolygonTest(quad, (float(pt[0]), float(pt[1])), False) >= 0:
                return f"card:{name}"
        return None

    # -- what the game reads -------------------------------------------------------------
    def public(self) -> dict:
        s = self.store.game.state
        if s.get("step") not in CARD_STEPS:
            return {"active": False}
        with self.lock:
            names = sorted(self.seen)
        cards = [{"name": n, "cost": rules.POWER_INFO.get(n, (None, None))[0],
                  "speed": rules.POWER_INFO.get(n, (None, None))[1]} for n in names]
        return {"active": True, "cards": cards, "cost": sum(c["cost"] or 0 for c in cards),
                "status": self.status}

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="card-watch").start()
        return self

    def stop(self):
        self._stop.set()

    def update(self, found):
        """Fold one read into the cards in view; True when the list of names changed."""
        with self.lock:
            before = set(self.seen)
            for f in found:
                self.seen[f["name"]] = {"quad": f["quad"], "missed": 0}
            names = {f["name"] for f in found}
            for n in list(self.seen):
                if n not in names:
                    self.seen[n]["missed"] += 1
                    if self.seen[n]["missed"] >= CARD_KEEP:
                        del self.seen[n]
            return set(self.seen) != before

    def _run(self):
        while not self._stop.is_set():
            s = self.store.game.state
            if s.get("step") in CARD_STEPS and s.get("players") and self._frame is not None:
                try:
                    spirit = s["players"][0]["spirit"]
                    if self.reader is None or self.spirit != spirit:
                        self.reader, self.spirit = PowerCardReader(card_paths(spirit)), spirit
                    self.status = "lined up"
                    if self.update(self.reader.read(self._frame)):
                        self.store.broadcast(self.store.snapshot())
                except Exception as e:
                    self.status = f"failed: {type(e).__name__}"
            elif self.seen:
                with self.lock:
                    self.seen = {}
                self.status = "off"
            self._stop.wait(self.every)
