"""Notice the invaders' build and explore being carried out on the table.

When a Build or Explore step starts, a photo of the board is kept (lined up to the board's
reference). Every few seconds the newest photo is compared with it, land by land: a new
piece shows up as a fresh patch of change in its land, whatever kind of piece it is and
however hard it is to classify in dim light. When every land that should get a piece has
one (twice in a row), the step's changes are entered and the game moves on.
"""

from __future__ import annotations

import threading
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from vision.register import register, warp_to_reference
from .perception import lands as land_map

STEPS = ("invader.build", "invader.explore")
WORK = 1200            # comparison size (long side)
NEW_PIECE = 0.0022     # a new piece's share of the board area (an explorer is ~0.004)


class StepWatch:
    def __init__(self, store, photo_url: str, boards_dir: str, every: float = 3.0):
        self.store = store
        self.url = photo_url
        self.boards_dir = Path(boards_dir)
        self.every = every
        self.base = None        # (step key, aligned small photo)
        self.refs = {}
        self.hits = 0
        self.state = {}
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="step-watch")
            self._thread.start()

    def _ref(self, letter):
        if letter not in self.refs:
            d = self.boards_dir / letter
            ref = cv2.imread(str(d / "reference.jpg"))
            mask = cv2.imread(str(d / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
            labels, names = land_map.load(d)
            k = WORK / max(ref.shape[:2])
            small = lambda m: cv2.resize(m, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)  # noqa: E731
            self.refs[letter] = (ref, mask, small(labels), names, k, small(mask))
        return self.refs[letter]

    def _photo(self, letter):
        ref, mask, labels, names, k, smask = self._ref(letter)
        with urllib.request.urlopen(self.url, timeout=8) as r:
            img = cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
        reg = register(ref, img, reference_mask=mask)
        if reg is None or not reg.ok:
            return None
        al = warp_to_reference(img, reg, ref.shape)
        return cv2.resize(al, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)

    def _run(self):
        while True:
            try:
                self._once()
            except Exception as e:  # camera hiccup
                print(f"step watch: {type(e).__name__}: {e}")
            time.sleep(self.every)

    def _expected(self, s):
        """{land id: True} for the lands that should get a piece in this step."""
        from .engine.guide import describe
        g = describe(s)
        if s["step"] == "invader.build":
            return {lid for lid, m in (g.get("marks") or {}).items() if m["text"] != "nothing"}
        if s["step"] == "invader.explore":
            rows = (g.get("helper") or {}).get("rows") or []
            return {r["land"] for r in rows if r.get("explore") == "yes"}
        return set()

    def _once(self):
        s = self.store.game.state
        v = self.store.vision
        letter = v.camera_board(s) if v else None
        key = (s.get("step"), s.get("round"), s["invaders"]["slots"].get("explore"))
        if s.get("step") not in STEPS or not letter:
            self.base, self.hits = None, 0
            return
        if self.base is None or self.base[0] != key:
            photo = self._photo(letter)
            if photo is not None:
                self.base, self.hits = (key, photo), 0
            return
        want = self._expected(s)
        if not want:
            return
        now = self._photo(letter)
        if now is None:
            return
        _, mask, labels, names, k, smask = self._ref(letter)
        a = cv2.cvtColor(cv2.GaussianBlur(self.base[1], (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
        b = cv2.cvtColor(cv2.GaussianBlur(now, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
        diff = np.sqrt(((a - b) ** 2).sum(-1))
        changed = (diff > 22) & (smask > 0)
        changed = cv2.morphologyEx(changed.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
        board = max(1, int((smask > 0).sum()))
        got = set()
        for lid in want:
            n = lid[len(letter):]
            if n in names and (changed & (labels == names.index(n) + 1)).sum() >= NEW_PIECE * board:
                got.add(lid)
        self.state = {"want": sorted(want), "got": sorted(got)}
        self.hits = self.hits + 1 if got == want else 0
        if self.hits >= 2 and self.store.game.state.get("step") == s["step"]:
            self.hits = 0
            self.store.step_done_from_camera(sorted(want))
