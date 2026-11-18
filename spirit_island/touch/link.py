"""Camera gestures for the live game: watches the phone camera for hands and turns what
it sees into game actions.

- Double tap with one finger: Next. With two fingers: Undo (Back during setup).
- Hold up N fingers for half a second: pick option N of the choice the game is asking
  for (only while it asks, e.g. a growth option).

A one-finger hold waits a moment longer before it counts, because a finger resting on
the table before a double tap looks just like holding up 1; a double tap cancels it.

`GestureLink.process(t, hands)` is the whole pipeline after hand finding, so tests can
feed it hand points without a camera.
"""

from __future__ import annotations

import threading
import time

from .gestures import GestureReader

ONE_FINGER_WAIT_S = 1.0  # extra wait before a 1-finger hold counts (a double tap may follow)


class GestureLink:
    def __init__(self, source=None, on_action=None, choices=None, work_width=480):
        """on_action(action dict): called for each game action. choices(): how many
        numbered options the game is asking to pick from right now (0 = none)."""
        self.source = source
        self.on_action = on_action or (lambda a: None)
        self.choices = choices or (lambda: 0)
        self.work_width = work_width
        self.reader = GestureReader()
        self._pending_one = None   # time a 1-finger hold was seen, waiting to count
        self._stop = threading.Event()
        self.status = {"camera": "off", "fps": 0.0, "hands": 0}
        self.last = None           # last thing done, for the TV: {"what", "t"}

    # -- the pipeline ------------------------------------------------------------------
    def process(self, t, hands):
        events = self.reader.update(t, hands)
        for ev in events:
            if ev["kind"] == "double_tap":
                self._pending_one = None
                if ev["fingers"] == 1:
                    self._act({"type": "next"}, "Next")
                else:
                    self._act({"type": "undo"}, "Back")
            elif ev["kind"] == "hold":
                n = ev["count"]
                if not 1 <= n <= self.choices():
                    continue
                if n == 1:
                    self._pending_one = t
                else:
                    self._pending_one = None
                    self._choose(n)
        if self._pending_one is not None and t - self._pending_one >= ONE_FINGER_WAIT_S:
            self._pending_one = None
            if self.choices() >= 1:
                self._choose(1)
        self.status["hands"] = len(hands)
        prog = self.reader.progress()
        self.status["ring"] = prog if prog["count"] and prog["count"] <= self.choices() else None
        return events

    def _choose(self, n):
        self._act({"type": "choose", "option": n}, f"Option {n}")

    def _act(self, action, what):
        self.last = {"what": what, "t": time.time()}
        try:
            self.on_action(action)
        except Exception as e:  # a refused action (e.g. nothing to undo) must not stop the camera
            self.last = {"what": f"{what}: {e}", "t": time.time()}

    def public(self):
        return {**self.status, "last": self.last}

    # -- the camera thread ---------------------------------------------------------------
    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        try:
            from vision.capture import Camera
            from .hands import HandFinder
            cam = Camera(self.source)
            cam.start()
            finder = HandFinder(work_width=self.work_width)
        except Exception as e:
            self.status = {"camera": f"failed: {e}", "fps": 0.0, "hands": 0}
            return
        last_idx, frames, t0 = -1, 0, time.time()
        while not self._stop.is_set():
            pkt = cam.wait_for_frame(after_index=last_idx, timeout=2.0)
            if pkt is None:
                self.status = {**self.status, "camera": "no frames"}
                continue
            last_idx = pkt.index
            hands = finder.find(pkt.image, pkt.timestamp)
            self.process(pkt.timestamp, hands)
            frames += 1
            if time.time() - t0 >= 2.0:
                self.status["fps"] = round(frames / (time.time() - t0), 1)
                frames, t0 = 0, time.time()
            self.status["camera"] = "ok"
