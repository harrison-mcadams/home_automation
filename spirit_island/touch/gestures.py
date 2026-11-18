"""Hand landmarks over time -> events.

Landmarks are the 21 MediaPipe hand points in image pixels:
    0 wrist; thumb 1-4; index 5-8; middle 9-12; ring 13-16; pinky 17-20 (tip last).

`GestureReader.update(t, hands, mat=None)` is fed once per frame and returns a list of
events, each a dict with a "kind":

    hold       fingers held still for HOLD_S: {"count": total raised fingers, "tip": (x, y)
               of the index tip when exactly one finger is up, "hands": n}
    swipe      a hand moved sideways across the mat: {"direction": "left" | "right"}
               (left = towards smaller x in the image)
    double_tap two quick taps: {"fingers": 1 (Next) or 2 (Back), "tip": (x, y)}

`progress()` says how far a hold has got (0..1) and what it would be, for the ring on
the TV. Everything is relative to the hand's own size, so nothing depends on camera
height or resolution.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

HOLD_S = 0.5          # a hold commits after this long
STILL = 0.35          # a hold's palm may wander this far (in palm lengths) and still count
SWIPE_MAX_S = 0.8     # a swipe happens within this long
SWIPE_MIN = 2.2       # ... and covers at least this many palm lengths sideways
SWIPE_MAT_FRAC = 0.3  # ... or this fraction of the mat's width, whichever is smaller
SWIPE_COOLDOWN_S = 0.8
TAP_DIP = 0.12        # a tap shortens the index finger's image by at least this fraction
TAP_RECOVER = 0.6     # ... and it springs back at least this share of the dip
TAP_MAX_S = 0.45      # one tap (down and up) takes at most this long
DOUBLE_TAP_S = 1.0    # two taps within this long make a double tap
LOST_S = 0.25         # a hand missing this long counts as gone


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def palm_size(lm):
    """Wrist to middle-finger knuckle: the hand's own ruler."""
    return max(1e-6, _d(lm[0], lm[9]))


def palm_centre(lm):
    pts = [lm[i] for i in (0, 5, 9, 13, 17)]
    return (sum(p[0] for p in pts) / 5, sum(p[1] for p in pts) / 5)


def fingers_up(lm):
    """Which fingers are raised: [thumb, index, middle, ring, pinky] as booleans.

    A finger is up when its tip is clearly farther from the wrist than its middle joint.
    Seen from above, a curled finger's tip folds back towards the palm, so this holds
    whichever way the hand is turned."""
    w = lm[0]
    out = []
    # Thumb: its tip well away from the index knuckle and farther out than its own base.
    p = palm_size(lm)
    out.append(_d(lm[4], lm[5]) > 0.55 * p and _d(lm[4], lm[17]) > _d(lm[2], lm[17]) * 1.1)
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        out.append(_d(lm[tip], w) > _d(lm[pip], w) * 1.15)
    return out


def count_up(lm):
    return sum(fingers_up(lm))


def pointing(lm):
    """Index up, middle, ring and pinky down (the thumb may do what it likes)."""
    f = fingers_up(lm)
    return f[1] and not (f[2] or f[3] or f[4])


@dataclass
class _Tap:
    """Watches the index finger's length in the image: it shortens as the finger tips
    down to the table (and the hand drops away from the camera), and springs back."""
    history: deque = field(default_factory=lambda: deque(maxlen=60))
    down: bool = False
    peak: float = 0.0
    low: float = 0.0
    down_at: float = 0.0
    taps: deque = field(default_factory=lambda: deque(maxlen=4))

    def update(self, t, length):
        self.history.append((t, length))
        recent = [v for (s, v) in self.history if t - s <= 0.4]
        if not self.down:
            self.peak = max(recent)
            if length < self.peak * (1 - TAP_DIP):
                self.down, self.low, self.down_at = True, length, t
            return None
        self.low = min(self.low, length)
        if t - self.down_at > TAP_MAX_S:
            self.down = False  # held down: not a tap
            return None
        if length >= self.low + TAP_RECOVER * (self.peak - self.low):
            self.down = False
            self.taps.append(t)
            if len(self.taps) >= 2 and self.taps[-1] - self.taps[-2] <= DOUBLE_TAP_S:
                self.taps.clear()
                return "double"
        return None

    def reset(self):
        self.history.clear()
        self.down = False
        self.taps.clear()


class _Flash:
    """A double tap seen as the fingers flashing: shown briefly, gone (folded, fist or
    hand out of view), and shown again. Finger counts are what the camera reads best, so
    this catches taps however the hand moves."""

    MAX_SHOW_S = 0.8   # the first showing is short (a longer one is a hold)
    GAP_S = (0.04, 0.7)

    def __init__(self):
        self.segs = []  # (value, start time); value 1 / 2 = that pose, 0 = none, -1 = other

    def update(self, t, value):
        """Fires when the second short showing ends: N, gone, N, gone. (Firing on the
        second appearance would also catch a single tap that folds the finger.)"""
        if not self.segs or self.segs[-1][0] != value:
            self.segs.append((value, t))
            self.segs = self.segs[-5:]
            if value == 0 and len(self.segs) >= 4:
                (a, ta), (b, tb), (c, tc) = self.segs[-4:-1]
                if a in (1, 2) and a == c and b == 0 and tb - ta <= self.MAX_SHOW_S and \
                        t - tc <= self.MAX_SHOW_S and self.GAP_S[0] <= tc - tb <= self.GAP_S[1]:
                    self.segs = [(0, t)]
                    return a
        return None


class GestureReader:
    def __init__(self, swipes=False):
        self.swipes = swipes  # off: Harrison found them unreliable (2026-11-18 touch test)
        self.reset()

    def reset(self):
        self._hold_key = None       # (count, n hands) being held
        self._hold_since = 0.0
        self._hold_anchor = None    # palm centre when the hold started
        self._hold_fired = False    # this hold already committed; wait for a change
        self._track = deque(maxlen=90)  # (t, palm centre x, y, palm size) of the main hand
        self._last_swipe = -1e9
        self._last_seen = -1e9
        self._tap = _Tap()
        self._pointed_at = -1e9
        self._tap_pose = None
        self._flash = _Flash()
        self._progress = (0.0, None)

    def progress(self):
        return {"fraction": self._progress[0], "count": self._progress[1]}

    def update(self, t, hands, mat=None):
        """hands: list of landmark lists (21 (x, y) points each). mat: optional dict with
        "width" in pixels, used to size swipes."""
        events = []
        if not hands:
            self._flash.update(t, 0)
            if t - self._last_seen > LOST_S:
                self._hold_key, self._hold_fired = None, False
                self._track.clear()
                self._tap.reset()
                self._progress = (0.0, None)
            return events
        self._last_seen = t
        # The main hand: the biggest in view (nearest the camera, usually the one in use).
        main = max(hands, key=palm_size)
        p = palm_size(main)
        cx, cy = palm_centre(main)
        self._track.append((t, cx, cy, p))

        # --- swipe: the main hand travels sideways fast enough --------------------------
        swiped = False
        if self.swipes and t - self._last_swipe > SWIPE_COOLDOWN_S:
            need = SWIPE_MIN * p
            if mat and mat.get("width"):
                need = min(need, SWIPE_MAT_FRAC * mat["width"])
            for (s, x, y, _) in self._track:
                if t - s > SWIPE_MAX_S:
                    continue
                dx, dy = cx - x, cy - y
                if abs(dx) >= need and abs(dy) < 0.6 * abs(dx):
                    events.append({"kind": "swipe", "direction": "right" if dx > 0 else "left"})
                    self._last_swipe = t
                    self._track.clear()
                    self._hold_key, self._hold_fired = None, False
                    swiped = True
                    break

        # --- hold: the same number of fingers, kept still ---------------------------------
        counts = [count_up(h) for h in hands]
        total = sum(counts)
        key = (total, sum(1 for c in counts if c))
        if swiped:
            self._progress = (0.0, None)
        elif total == 0:
            self._hold_key, self._hold_fired = None, False
            self._progress = (0.0, None)
        else:
            moved = self._hold_anchor is not None and _d((cx, cy), self._hold_anchor) > STILL * p
            if key != self._hold_key or moved:
                self._hold_key, self._hold_since, self._hold_anchor = key, t, (cx, cy)
                self._hold_fired = False
            frac = min(1.0, (t - self._hold_since) / HOLD_S)
            self._progress = (0.0 if self._hold_fired else frac, total)
            if frac >= 1.0 and not self._hold_fired:
                self._hold_fired = True
                tip = None
                if total == 1:
                    for h, c in zip(hands, counts):
                        if c == 1 and pointing(h):
                            tip = tuple(h[8])
                events.append({"kind": "hold", "count": total, "tip": tip, "hands": key[1]})

        # --- double tap with 1 finger (Next) or 2 fingers (Back) ----------------------
        # Two ways to see it: the fingers flash twice, or they dip towards the table twice.
        fu = fingers_up(main)
        n = sum(fu[1:]) if not fu[0] else -1
        flash_val = 0 if n == 0 else (1 if (fu[1] and n == 1) else 2 if (fu[1] and fu[2] and n == 2) else -1)
        if len(hands) > 1:
            flash_val = -1
        got = self._flash.update(t, flash_val)
        if got:
            events.append({"kind": "double_tap", "fingers": got, "tip": tuple(main[8]), "how": "flash"})
            self._hold_fired = True
            self._tap.reset()
            return events
        # The raised fingers may look folded at the bottom of a tap, so the pose is the one
        # last seen clearly, and only the ring and little fingers must stay curled.
        f = fingers_up(main)
        if len(hands) == 1 and not (f[3] or f[4]):
            pose = 2 if (f[1] and f[2]) else 1 if (f[1] and not f[2]) else None
            if pose:
                if pose != self._tap_pose:
                    self._tap.reset()
                self._tap_pose, self._pointed_at = pose, t
            if self._tap_pose and t - self._pointed_at < 0.5:
                tips = [main[8]] + ([main[12]] if self._tap_pose == 2 else [])
                bases = [main[5]] + ([main[9]] if self._tap_pose == 2 else [])
                length = sum(_d(a_, b_) for a_, b_ in zip(bases, tips)) / len(tips)
                if self._tap.update(t, length) == "double":
                    events.append({"kind": "double_tap", "fingers": self._tap_pose, "tip": tuple(main[8]), "how": "dip"})
                    self._flash.segs = []
                    # Taps wobble the finger count; don't let that also count as a hold.
                    self._hold_fired = True
            else:
                self._tap.reset()
                self._tap_pose = None
        else:
            self._tap.reset()
            self._tap_pose = None
        return events
