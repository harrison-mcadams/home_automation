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

HOLD_S = 0.5          # a hold commits after this long
STILL = 0.35          # a hold's palm may wander this far (in palm lengths) and still count
SWIPE_MAX_S = 0.8     # a swipe happens within this long
SWIPE_MIN = 2.2       # ... and covers at least this many palm lengths sideways
SWIPE_MAT_FRAC = 0.3  # ... or this fraction of the mat's width, whichever is smaller
SWIPE_COOLDOWN_S = 0.8
TAP_GAP = 0.05        # the finger's two levels (resting, tapping) differ by at least this
                      # fraction of its length (Harrison's taps: 7-11%; rest wobble 2-3%)
TAP_HYST = 0.1        # switch level only past this share of the gap beyond the midpoint
TAP_LEVELS_S = 1.0    # the two levels are read from this much recent history
TAP_MAX_S = 0.4       # each tap, and the touch between the two, lasts at most this long
TAP_REST_S = 0.25     # the finger rests at least this long before a double tap
TAP_STILL = 0.25      # during taps the palm stays within this many palm lengths
TAP_SIZE = 0.25       # ... and its size changes by less than this fraction (two-finger
                      # taps tilt the hand: palm 165 -> 145 px on the 2026-11-18 run)
TAP_STILL_S = 0.5     # ... over this long
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


def _middle_clearly_up(lm):
    """Middle finger raised: tip well beyond its middle joint from the wrist. On the
    2026-11-18 runs this ratio was 0.93-1.04 for one-finger taps and 1.27-1.40 for two."""
    return _d(lm[12], lm[0]) > _d(lm[10], lm[0]) * 1.15


def pointing(lm):
    """Index up, middle, ring and pinky down (the thumb may do what it likes)."""
    f = fingers_up(lm)
    return f[1] and not (f[2] or f[3] or f[4])


class _Tap:
    """Watches the index finger's length in the picture. A tap is a short trip from the
    finger's resting length to another level and back. Which way depends on how the
    finger rests: on the 2026-11-18 recordings Harrison's finger rests on the table and
    each tap is a quick lift, which here made the finger look 7-11% longer. Both levels
    are read from the last 1.5 s, since they change with where the hand is."""

    def __init__(self):
        self.history = deque(maxlen=90)
        self.state = None     # "hi" or "lo"
        self.since = 0.0
        self.runs = deque(maxlen=6)  # finished (state, start, end), oldest first
        self.first_down = 0.0  # when the double tap's first tap started

    def update(self, t, length):
        self.history.append((t, length))
        vals = [v for (s, v) in self.history if t - s <= TAP_LEVELS_S]
        hi, lo = max(vals), min(vals)
        if hi - lo < TAP_GAP * hi:
            return None  # one level only: nothing to read
        mid, band = (hi + lo) / 2, TAP_HYST * (hi - lo)
        new = "hi" if length > mid + band else "lo" if length < mid - band else self.state
        if new is None or new == self.state:
            return None
        if self.state is None:
            # First movement after a steady spell: that spell was the rest.
            self.runs.clear()
            self.runs.append(("hi" if new == "lo" else "lo", t - 1.0, t))
        else:
            self.runs.append((self.state, self.since, t))
        self.state, self.since = new, t
        return self._check()

    def _check(self):
        # rest (long) / tap / rest (short) / tap, and now back at rest.
        if len(self.runs) < 4:
            return None
        r0, p1, r1, p2 = list(self.runs)[-4:]
        if not (r0[0] == r1[0] == self.state and p1[0] == p2[0] != self.state):
            return None
        if r0[2] - r0[1] < TAP_REST_S:
            return None
        if any(r[2] - r[1] > TAP_MAX_S for r in (p1, r1, p2)):
            return None
        self.first_down = p1[1]
        self.runs.clear()
        self.runs.append((self.state, self.since - 1.0, self.since))  # fresh rest
        return "double"

    def reset(self):
        self.history.clear()
        self.state = None
        self.runs.clear()


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
        self._poses = deque(maxlen=90)
        self._progress = (0.0, None)

    def progress(self):
        return {"fraction": self._progress[0], "count": self._progress[1]}

    def update(self, t, hands, mat=None):
        """hands: list of landmark lists (21 (x, y) points each). mat: optional dict with
        "width" in pixels, used to size swipes."""
        events = []
        if not hands:
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
        # Small taps (Harrison, 2026-11-18): the finger rests on the table and lifts twice
        # quickly, which changes its length in the picture by 7-11%. The hand stays put;
        # with two fingers it tilts a little, so the palm may change size by up to a
        # quarter. Mid-tap the finger count flickers, so the pose is read from the middle
        # finger across the whole double tap: up (clearly) in most frames means 2.
        f = fingers_up(main)
        self._poses.append((t, _middle_clearly_up(main)))
        if len(hands) == 1 and not (f[3] or f[4]) and f[1]:
            self._pointed_at = t
        if len(hands) == 1 and t - self._pointed_at < 0.6 and self._palm_still(t, cx, cy, p):
            if self._tap.update(t, _d(main[5], main[8])) == "double":
                start = self._tap.first_down
                during = [up for (s_, up) in self._poses if start <= s_ <= t]
                fingers = 2 if during and sum(during) >= 0.5 * len(during) else 1
                events.append({"kind": "double_tap", "fingers": fingers, "tip": tuple(main[8])})
                # Taps wobble the finger count; don't let that also count as a hold.
                self._hold_fired = True
        else:
            self._tap.reset()
        return events

    def _palm_still(self, t, cx, cy, p):
        """The palm has stayed put and kept its size over the last second."""
        for (s, x, y, q) in self._track:
            if t - s > TAP_STILL_S:
                continue
            if _d((x, y), (cx, cy)) > TAP_STILL * p or abs(q - p) > TAP_SIZE * p:
                return False
        return True
