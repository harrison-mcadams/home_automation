"""Camera gestures for the live game: watches the phone camera for hands and turns what
it sees into game actions.

- First, hold an open hand still for 2 seconds where you want your gesture spot.
  Gestures count only with your palm inside that spot (not over the map).
- Double tap with one finger: Next. With two fingers: Undo (Back during setup).
- Point at what you want and hold still: a land on the map, a growth option or a presence
  row on your spirit panel, or a power card you laid down (plays it). A held point is taken straight away (no confirm).
- Holding up N fingers picks option N only when the camera can't see what the question
  is about (a backup).

One thing at a time: while the game is asking for a number, only a number counts (taps
are ignored); once it has one, only Next and Back count. Back takes the number back.

`GestureLink.process(t, hands)` is the whole pipeline after hand finding, so tests can
feed it hand points without a camera.
"""

from __future__ import annotations

import threading
import time

from .gestures import POINT_HOLD_S, GestureReader, GestureZone, pointing



def label(key):
    """How a point target reads on the TV: "land 4", "growth option 2", "the energy row"."""
    kind, _, what = key.partition(":")
    if kind == "land":
        return "land " + what.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if kind == "growth":
        return f"growth option {what}"
    if kind == "track":
        return {"energy": "the energy row", "cards": "the card plays row"}.get(what, what)
    if kind == "card":
        return what
    return key


class GestureLink:
    def __init__(self, source=None, on_action=None, choices=None, work_width=480,
                 land_options=None, board=None, targets=None, pointers=None):
        """on_action(action dict): called for each game action. choices(): how many
        numbered options the game is asking to pick from right now (0 = none).
        targets(): the question's options as point targets, in option order ("land:C4",
        "growth:2", "track:energy"). pointers: things with target_at(point) (BoardPointer,
        PanelPointer). land_options/board are the older land-only form of the same."""
        self.source = source
        self.on_action = on_action or (lambda a: None)
        self.choices = choices or (lambda: 0)
        self.work_width = work_width
        self.reader = GestureReader()
        self.land_options = land_options or (lambda: [])
        self.board = board
        self.pointers = list(pointers or ([board] if board is not None else []))
        self.targets = targets or (lambda: [f"land:{l}" for l in self.land_options()])
        self.pointer = GestureReader(hold_s=POINT_HOLD_S)  # pointing: any hand, anywhere
        self.zone = GestureZone()  # gestures only count in the spot you set with an open hand
        self._stop = threading.Event()
        self.status = {"camera": "off", "fps": 0.0, "hands": 0}
        self.last = None           # last thing done, for the TV: {"what", "t"}

    # -- the pipeline ------------------------------------------------------------------
    def process(self, t, hands):
        seen, everyone = len(hands), hands
        hands = self.zone.update(t, hands)
        wants_number = self.choices() > 0
        targets = self.targets()
        aim = self._aimers(targets)
        # Asking for a number above 5: with one hand in your spot, a second hand anywhere
        # in view adds its fingers (land choices can go up to 8).
        if hands and len(everyone) > len(hands) and self._wanted() > 5:
            hands = everyone
        events = self.reader.update(t, hands)
        # One thing at a time (Harrison, 2026-11-18): while the game wants a number, only
        # a number counts; once it has one, only Next and Back do (Back also takes the
        # number back, so you can pick again).
        for ev in events:
            if ev["kind"] == "double_tap" and not wants_number:
                self._act({"type": "next"} if ev["fingers"] == 1 else {"type": "undo"},
                          "Next" if ev["fingers"] == 1 else "Back")
            # Finger counts are only a backup: when the camera can see what the question
            # is about, you point instead (Harrison, 2026-11-18), so a pointing finger in
            # your spot can't read as "1".
            elif ev["kind"] == "hold" and wants_number and not aim and 1 <= ev["count"] <= self.choices():
                self._choose(ev["count"])
        # Pointing at a lit target (fingertip held still) answers the question straight
        # away, wherever the board and panel sit in the picture.
        self.status["pointing"] = None
        self.status["point_kind"] = targets[0].split(":")[0] if aim else None
        if aim:
            for h in everyone:
                if pointing(h):
                    key = self._target_at(aim, h[8])
                    if key in targets:
                        self.status["pointing"] = label(key)
            for ev in self.pointer.update(t, everyone):
                if ev["kind"] == "hold" and ev.get("tip") is not None:
                    key = self._target_at(aim, ev["tip"])
                    if key in targets and key.startswith("card:"):
                        self._act({"type": "play_card", "card": key[5:]}, f"Played {key[5:]}")
                    elif key in targets:
                        self._act({"type": "choose", "option": targets.index(key) + 1}, label(key).capitalize())
        else:
            self.pointer.reset()
        self.status["hands"] = seen
        self.status["wants_number"] = wants_number
        self.status["in_spot"] = len(hands)
        prog = self.reader.progress()
        if self.zone.setting:
            f = self.zone.progress()
            self.status["ring"] = {"fraction": f, "count": 5} if f else None
        elif aim:
            pp = self.pointer.progress()
            self.status["ring"] = {"fraction": pp["fraction"], "count": "☝"} \
                if self.status["pointing"] and pp.get("fraction") else None
        else:
            self.status["ring"] = prog if prog["count"] and prog["count"] <= self.choices() else None
        return events

    def _aimers(self, targets):
        """The lined-up pointers that can find this question's targets ([] = count fingers)."""
        if not targets:
            return []
        kind = targets[0].split(":")[0]
        return [p for p in self.pointers if kind in getattr(p, "kinds", {"land"})
                and getattr(p, "status", "lined up") == "lined up"]

    @staticmethod
    def _target_at(aim, pt):
        for p in aim:
            key = p.target_at(pt) if hasattr(p, "target_at") else \
                (lambda lid: f"land:{lid}" if lid else None)(p.land_at(pt))
            if key:
                return key
        return None

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
        out = {**self.status, "last": self.last, "spot": self.zone.public()}
        if self.board is not None:
            out["board"] = getattr(self.board, "status", "ok")
        for p in self.pointers:
            if "growth" in getattr(p, "kinds", ()):
                out["panel"] = getattr(p, "status", "ok")
        return out

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
            for p in self.pointers:
                if hasattr(p, "give_frame"):
                    p.give_frame(pkt.image)
            self.process(pkt.timestamp, hands)
            frames += 1
            if time.time() - t0 >= 2.0:
                self.status["fps"] = round(frames / (time.time() - t0), 1)
                frames, t0 = 0, time.time()
            self.status["camera"] = "ok"
