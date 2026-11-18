"""Gesture events from made-up hand landmarks (no camera needed)."""

from spirit_island.touch.gestures import GestureReader, count_up, pointing

XS = {"index": -0.3, "middle": 0.0, "ring": 0.25, "pinky": 0.5}


def hand(up=("index",), at=(300, 300), p=60.0, index_len=1.0):
    """A hand seen from above, fingers pointing up the image. `up` names raised fingers
    ("thumb" too). index_len < 1 shortens the index finger (tipped down for a tap)."""
    cx, cy = at
    pt = lambda x, y: (cx + x * p, cy + y * p)  # noqa: E731
    lm = [None] * 21
    lm[0] = pt(0, 0)
    thumb_up = "thumb" in up
    lm[1], lm[2], lm[3] = pt(-0.3, -0.2), pt(-0.5, -0.4), pt(-0.7, -0.55)
    lm[4] = pt(-0.95, -0.7) if thumb_up else pt(-0.2, -0.7)
    for name, base in zip(("index", "middle", "ring", "pinky"), (5, 9, 13, 17)):
        x = XS[name]
        lm[base] = pt(x, -1.0)
        lm[base + 1] = pt(x, -1.4)
        if name in up:
            ext = 0.9 * (index_len if name == "index" else 1.0)
            lm[base + 2], lm[base + 3] = pt(x, -1.0 - ext * 0.75), pt(x, -1.0 - ext)
        else:
            lm[base + 2], lm[base + 3] = pt(x, -1.2), pt(x, -1.05)
    return lm


def run(frames, dt=1 / 20):
    r, out = GestureReader(), []
    for i, hands in enumerate(frames):
        out += r.update(i * dt, hands, None)
    return out


def test_counts_fingers():
    assert count_up(hand(())) == 0
    assert count_up(hand(("index",))) == 1 and pointing(hand(("index",)))
    assert count_up(hand(("index", "middle", "ring"))) == 3
    assert count_up(hand(("thumb", "index", "middle", "ring", "pinky"))) == 5
    assert not pointing(hand(("index", "middle")))


def test_hold_three_fires_once_after_half_a_second():
    frames = [[hand(("index", "middle", "ring"))]] * 30  # 1.5 s
    ev = run(frames)
    assert [e["kind"] for e in ev] == ["hold"] and ev[0]["count"] == 3


def test_quick_flash_of_fingers_does_nothing():
    assert run([[hand(("index", "middle"))]] * 6) == []  # 0.3 s


def test_two_hands_add_up():
    frames = [[hand(("thumb", "index", "middle", "ring", "pinky")), hand(("index", "middle"), at=(600, 300))]] * 20
    ev = run(frames)
    assert ev and ev[0]["count"] == 7 and ev[0]["hands"] == 2


def test_point_hold_gives_the_fingertip():
    ev = run([[hand(("index",), at=(200, 250))]] * 20)
    assert ev[0]["count"] == 1 and ev[0]["tip"] is not None


def test_moving_hand_does_not_hold():
    frames = [[hand(("index", "middle"), at=(100 + i * 15, 300))] for i in range(30)]
    assert not [e for e in run(frames) if e["kind"] == "hold"]


def test_swipe_left_and_right():
    defaults = GestureReader.__init__.__defaults__
    GestureReader.__init__.__defaults__ = (True,) + defaults[1:]  # swipes are off by default
    left = [[hand((), at=(500 - i * 40, 300))] for i in range(8)]
    ev = run(left)
    assert [e["direction"] for e in ev if e["kind"] == "swipe"] == ["left"]
    right = [[hand((), at=(100 + i * 40, 300))] for i in range(8)]
    assert [e["direction"] for e in run(right) if e["kind"] == "swipe"] == ["right"]
    GestureReader.__init__.__defaults__ = defaults


def test_swipes_off_by_default():
    left = [[hand((), at=(500 - i * 40, 300))] for i in range(8)]
    assert not [e for e in run(left) if e["kind"] == "swipe"]


def test_slow_drift_is_not_a_swipe():
    frames = [[hand((), at=(100 + i * 4, 300))] for i in range(60)]  # 240 px over 3 s
    assert not [e for e in run(frames) if e["kind"] == "swipe"]


def test_double_tap_one_finger_is_next():
    up, down = hand(("index",)), hand(("index",), index_len=0.6)
    frames = [[up]] * 3 + [[down]] * 2 + [[up]] * 2 + [[down]] * 2 + [[up]] * 3
    taps = [e for e in run(frames) if e["kind"] == "double_tap"]
    assert len(taps) == 1 and taps[0]["fingers"] == 1


def test_double_tap_two_fingers_is_back():
    up = hand(("index", "middle"))
    down = hand(("middle",), index_len=0.6)  # both folded: build a short pair by hand
    down = [list(p) for p in up]
    for base in (5,):  # the index tips down; the middle stays raised (as on camera)
        for k in (2, 3):
            x, y = up[base]
            tx, ty = up[base + k]
            down[base + k] = (x + (tx - x) * 0.55, y + (ty - y) * 0.55)
    frames = [[up]] * 3 + [[down]] * 2 + [[up]] * 2 + [[down]] * 2 + [[up]] * 3
    taps = [e for e in run(frames) if e["kind"] == "double_tap"]
    assert len(taps) == 1 and taps[0]["fingers"] == 2


def test_single_tap_is_not_double():
    up, down = hand(("index",)), hand(("index",), index_len=0.6)
    frames = [[up]] * 3 + [[down]] * 2 + [[up]] * 30
    assert not [e for e in run(frames) if e["kind"] == "double_tap"]


def _trace(pairs, t_end):
    """Frames at 28 fps from a time:length trace, holding each length until the next."""
    out, i, t = [], 0, 0.0
    while t < t_end:
        while i + 1 < len(pairs) and pairs[i + 1][0] <= t:
            i += 1
        out.append([hand(("index",), index_len=pairs[i][1] / 205)])
        t += 1 / 28
    return out


def test_finger_resting_on_table_lifts_twice():
    """Spot 2 of Harrison's second recording: the finger rests down (~181) and each tap is
    a quick lift (~202)."""
    rest = [(0.0, 181)]
    dt = [(1.0 + a, v) for a, v in [(0.03, 185), (0.09, 192), (0.11, 201), (0.16, 202),
          (0.19, 196), (0.23, 180), (0.30, 181), (0.35, 192), (0.36, 202), (0.44, 201),
          (0.45, 205), (0.50, 199), (0.57, 179)]]
    pairs = rest + dt + [(1.7, 181)]
    pairs += [(a + 1.2, v) for a, v in dt] + [(2.9, 181)]  # and again 1.2 s later
    taps = [e for e in run(_trace(pairs, 4.0), dt=1 / 28) if e["kind"] == "double_tap"]
    assert len(taps) == 2 and all(t["fingers"] == 1 for t in taps)


def test_spot_one_shallower_lifts():
    """Spot 1: down ~173, lifted ~186 (7.5%)."""
    pairs = [(0.0, 173), (1.0, 186), (1.08, 181), (1.12, 169), (1.18, 172), (1.24, 181),
             (1.28, 185), (1.36, 186), (1.37, 181), (1.42, 169), (1.5, 174)]
    taps = [e for e in run(_trace(pairs, 3.0), dt=1 / 28) if e["kind"] == "double_tap"]
    assert len(taps) == 1


def test_single_lift_is_not_double():
    pairs = [(0.0, 181), (1.0, 202), (1.2, 181)]
    assert not [e for e in run(_trace(pairs, 3.0), dt=1 / 28) if e["kind"] == "double_tap"]


def test_rest_wobble_is_not_a_tap():
    import math
    frames = [[hand(("index",), index_len=1 + 0.015 * math.sin(i))] for i in range(120)]
    assert not [e for e in run(frames, dt=1 / 28) if e["kind"] == "double_tap"]


def test_whole_hand_lift_is_not_a_tap():
    """Big lifts move the palm and change its size: not taps (Harrison wants small ones)."""
    up = hand(("index",))
    lifted = hand(("index",), at=(300, 200), p=45.0, index_len=0.6)
    frames = [[up]] * 3 + [[lifted]] * 2 + [[up]] * 2 + [[lifted]] * 2 + [[up]] * 3
    assert not [e for e in run(frames) if e["kind"] == "double_tap"]


def test_half_curled_middle_still_reads_one_finger():
    up = hand(("index",))
    up[11], up[12] = (up[9][0], up[9][1] - 0.5 * 60), (up[9][0], up[9][1] - 0.45 * 60)
    down = hand(("index",), index_len=0.88)
    down[11], down[12] = up[11], up[12]
    frames = [[up]] * 6 + [[down]] * 3 + [[up]] * 3 + [[down]] * 3 + [[up]] * 6
    taps = [e for e in run(frames) if e["kind"] == "double_tap"]
    assert len(taps) == 1 and taps[0]["fingers"] == 1


def test_hold_then_lower_and_raise_slowly_is_not_a_double_tap():
    one, fist = hand(("index",)), hand(())
    frames = [[one]] * 30 + [[fist]] * 20 + [[one]] * 30  # 1.5 s up, 1 s down, up again
    assert not [e for e in run(frames) if e["kind"] == "double_tap"]


def test_recorded_small_taps_clip():
    """Harrison's 30 s clip of small one-finger double taps (2026-11-18), as a per-frame
    trace: every double tap is found, as 1 finger, and nothing else fires (including the
    lone lift at 20.13 s as his hand settled)."""
    import csv
    from pathlib import Path
    data = Path(__file__).parent / "data"
    ref = [tuple(map(float, line.split())) for line in (data / "small_taps_lifts.txt").read_text().splitlines()
           if line and line[0].isdigit()]
    r, events = GestureReader(), []
    for row in csv.DictReader(open(data / "small_taps_trace.csv")):
        t, p = float(row["t"]), float(row["palm"])
        # The trace only says how many fingers were counted, not how the middle finger
        # looked, so it is drawn curled throughout (the live-run test covers the pose).
        h = hand(("index",), at=(float(row["cx"]), float(row["cy"])), p=p,
                 index_len=float(row["index"]) / (0.9 * p))
        events += [(t, e["fingers"]) for e in r.update(t, [h]) if e["kind"] == "double_tap"]
    within = lambda t, a, b: a <= t <= b + 0.6  # noqa: E731
    assert all(any(within(t, a, b) for t, _ in events) for a, b in ref)
    assert all(any(within(t, a, b) for a, b in ref) for t, _ in events)
    assert len(events) == len(ref) and all(f == 1 for _, f in events)


def test_recorded_live_run_one_and_two_fingers():
    """Harrison's live test run (2026-11-18), real hand points: prompts 0-3 asked for
    one-finger double taps, 4-7 for two. Every lift pair seen is found, with the right
    finger count, and no double tap fires as the wrong one."""
    import csv
    from pathlib import Path
    data = Path(__file__).parent / "data"
    ref = [tuple(map(float, line.split()[:2])) for line in (data / "live_taps_lifts.txt").read_text().splitlines()
           if line and line[0].isdigit()]
    r, events = GestureReader(), []
    for row in csv.DictReader(open(data / "live_taps_frames.csv")):
        t = float(row["t"])
        hands = [[(float(row[f"x{i}"]), float(row[f"y{i}"])) for i in range(21)]] if row["x0"] else []
        events += [(t, int(row["prompt"]), e["fingers"]) for e in r.update(t, hands)
                   if e["kind"] == "double_tap"]
    assert all(any(a <= t <= b + 0.6 for t, _, _ in events) for a, b in ref)
    assert all((f == 2) == (prompt >= 4) for _, prompt, f in events)
    assert all(any(e[1] == p for e in events) for p in (1, 2, 3))


def test_back_to_back_double_taps_both_count():
    """Two double taps with only a short rest between them (Harrison, 2026-11-18)."""
    frames, dt = [], 1 / 28

    def add(lifted, seconds):
        frames.extend([[hand(("index",), index_len=1.12 if lifted else 1.0)]] * round(seconds / dt))
    add(0, 0.6)
    for _ in range(2):
        add(1, 0.15); add(0, 0.12); add(1, 0.15); add(0, 0.12)  # noqa: E702
    add(0, 0.8)
    taps = [e for e in run(frames, dt=dt) if e["kind"] == "double_tap"]
    assert len(taps) == 2
