"""Run the change tracker on the camera's photos and feed its events to the game."""

from __future__ import annotations

import threading
import time
import urllib.request

import cv2
import numpy as np

from .change_tracker import ChangeTracker


class ChangeWatch:
    def __init__(self, store, photo_url: str, boards_dir: str, every: float = 1.0, fallback: str | None = None):
        self.store = store
        self.url = photo_url
        self.fallback = fallback  # full photos, when there are no video frames
        self.every = every
        self.tracker = ChangeTracker(boards_dir)
        self.recent: list = []     # the last few events, newest first, for the screens
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="change-watch")
            self._thread.start()

    def public(self) -> dict:
        return {"status": self.tracker.status, "recent": self.recent[:4]}

    def _run(self):
        while True:
            started = time.time()
            try:
                self._once()
            except Exception as e:  # camera hiccup: say so, keep going
                import traceback
                self.tracker.status = f"camera: {type(e).__name__}"
                self.last_error = traceback.format_exc()
                print(self.last_error)
            time.sleep(max(0.2, self.every - (time.time() - started)))

    def _once(self):
        s = self.store.game.state
        v = self.store.vision
        letter = v.camera_board(s) if v else None
        if not letter or not s.get("lands"):
            return
        try:
            with urllib.request.urlopen(self.url, timeout=8) as r:
                image = cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            if not self.fallback:
                raise
            with urllib.request.urlopen(self.fallback, timeout=8) as r:
                image = cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
        before = self.tracker.status
        events = self.tracker.update(image, letter)
        for e in events:
            e["land"] = f"{letter}{e['land']}"
            e["t"] = time.time()
        if events:
            done = self.store.camera_events(events)
            self.recent = (done + self.recent)[:8]
        if events or before != self.tracker.status:
            self.store.broadcast(self.store.snapshot())
