"""Camera gestures for the live game: watches the phone camera for hands and turns what
it sees into game actions.

- First, hold an open hand still for 2 seconds where you want your gesture spot.
  Gestures count only with your palm inside that spot (not over the map).
- Double tap with one finger: Next. With two fingers: Undo (Back during setup).
- Hold up N fingers for half a second: pick option N when the game asks for a number
  (e.g. a growth option).

One thing at a time: while the game is asking for a number, only a number counts (taps
are ignored); once it has one, only Next and Back count. Back takes the number back.

`GestureLink.process(t, hands)` is the whole pipeline after hand finding, so tests can
feed it hand points without a camera.
"""

from __future__ import annotations

import threading
import time

from .gestures import GestureReader, GestureZone



class GestureLink:
    def __init__(self, source=None, on_action=None, choices=None, work_width=480):
        """on_action(action dict): called for each game action. choices(): how many
        numbered options the game is asking to pick from right now (0 = none)."""
        self.source = source
        self.on_action = on_action or (lambda a: None)
        self.choices = choices or (lambda: 0)
        self.work_width = work_width
        self.reader = GestureReader()
        self.zone = GestureZone()  # gestures only count in the spot you set with an open hand
        self._stop = threading.Event()
        self.status = {"camera": "off", "fps": 0.0, "hands": 0}
        self.last = None           # last thing done, for the TV: {"what", "t"}

    # -- the pipeline ------------------------------------------------------------------
    def process(self, t, hands):
        seen, everyone = len(hands), hands
        hands = self.zone.update(t, hands)
        # Asking for a number above 5: with one hand in your spot, a second hand anywhere
        # in view adds its fingers (land choices can go up to 8).
        if hands and len(everyone) > len(hands) and self._wanted() > 5:
            hands = everyone
        events = self.reader.update(t, hands)
        # One thing at a time (Harrison, 2026-11-18): while the game wants a number, only
        # a number counts; once it has one, only Next and Back do (Back also takes the
        # number back, so you can pick again).
        wants_number = self.choices() > 0
        for ev in events:
            if ev["kind"] == "double_tap" and not wants_number:
                self._act({"type": "next"} if ev["fingers"] == 1 else {"type": "undo"},
                          "Next" if ev["fingers"] == 1 else "Back")
            elif ev["kind"] == "hold" and wants_number and 1 <= ev["count"] <= self.choices():
                self._choose(ev["count"])
        self.status["hands"] = seen
        self.status["wants_number"] = wants_number
        self.status["in_spot"] = len(hands)
        prog = self.reader.progress()
        if self.zone.setting:
            f = self.zone.progress()
            self.status["ring"] = {"fraction": f, "count": 5} if f else None
        else:
            self.status["ring"] = prog if prog["count"] and prog["count"] <= self.choices() else None
        return events

    def _wanted(self):
        return self.choices()

    def _choose(self, n):
        self._act({"type": "choose", "option": n}, f"Option {n}")

    def _act(self, action, what):
        self.last = {"what": what, "t": time.time()}
        try:
            self.on_action(action)
        except Exception as e:  # a refused action (e.g. nothing to undo) must not stop the camera
            self.last = {"what": f"{what}: {e}", "t": time.time()}

    def set_spot_again(self):
        self.zone.reset()
        self.reader.reset()

    def public(self):
        return {**self.status, "last": self.last, "spot": self.zone.public()}

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
