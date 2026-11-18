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
    left = [[hand((), at=(500 - i * 40, 300))] for i in range(8)]
    ev = run(left)
    assert [e["direction"] for e in ev if e["kind"] == "swipe"] == ["left"]
    right = [[hand((), at=(100 + i * 40, 300))] for i in range(8)]
    assert [e["direction"] for e in run(right) if e["kind"] == "swipe"] == ["right"]


def test_slow_drift_is_not_a_swipe():
    frames = [[hand((), at=(100 + i * 4, 300))] for i in range(60)]  # 240 px over 3 s
    assert not [e for e in run(frames) if e["kind"] == "swipe"]


def test_double_tap():
    up, down = hand(("index",)), hand(("index",), index_len=0.6)
    frames = [[up]] * 3 + [[down]] * 2 + [[up]] * 2 + [[down]] * 2 + [[up]] * 3
    ev = run(frames)
    assert [e["kind"] for e in ev].count("double_tap") == 1


def test_single_tap_is_not_double():
    up, down = hand(("index",)), hand(("index",), index_len=0.6)
    frames = [[up]] * 3 + [[down]] * 2 + [[up]] * 30
    assert not [e for e in run(frames) if e["kind"] == "double_tap"]
