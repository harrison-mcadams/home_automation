"""Camera gestures driving the live game (no camera: hand points are fed in)."""

import pytest

from spirit_island.tests.test_gestures import hand
from spirit_island.touch.link import GestureLink

pytest.importorskip("flask")
from spirit_island.app import create_app  # noqa: E402


def feed(link, frames, t0=0.0, dt=1 / 20):
    for i, hands in enumerate(frames):
        link.process(t0 + i * dt, hands)
    return t0 + len(frames) * dt


def with_spot(link):
    """Set the gesture spot first, as at the start of a session (open hand, 2 s)."""
    feed(link, [[hand(("thumb", "index", "middle", "ring", "pinky"))]] * 45, t0=-100)
    assert not link.zone.setting
    return link


def double_tap(fingers=1):
    up = ("index", "middle") if fingers == 2 else ("index",)
    rest, lift = hand(up), hand(up, index_len=1.12)
    return [[rest]] * 8 + [[lift]] * 3 + [[rest]] * 3 + [[lift]] * 3 + [[rest]] * 8


def test_taps_become_next_and_undo():
    got = []
    link = with_spot(GestureLink(on_action=got.append))
    feed(link, double_tap(1))
    t = feed(link, [[]] * 20, t0=10)
    feed(link, double_tap(2), t0=t + 1)
    assert [a["type"] for a in got] == ["next", "undo"]


def test_numbers_only_count_while_a_choice_is_open():
    got = []
    open_ = [0]
    link = with_spot(GestureLink(on_action=got.append, choices=lambda: open_[0]))
    feed(link, [[hand(("index", "middle", "ring"))]] * 20)
    assert got == []
    open_[0] = 3
    feed(link, [[]] * 10, t0=5)
    feed(link, [[hand(("index", "middle", "ring"))]] * 20, t0=10)
    assert got == [{"type": "choose", "option": 3}]
    feed(link, [[]] * 10, t0=15)
    feed(link, [[hand(("index", "middle", "ring", "pinky", "thumb"))]] * 20, t0=20)
    assert len(got) == 1  # 5 is not one of the 3 options


def test_one_thing_at_a_time_number_then_taps():
    """While the game wants a number only numbers count; once it has one, only taps."""
    got = []
    wants = [3]
    link = with_spot(GestureLink(on_action=lambda a: (got.append(a), wants.__setitem__(0, 0))))
    link.choices = lambda: wants[0]
    feed(link, [[hand(("index", "middle"))]] * 15, t0=5)
    assert got == [{"type": "choose", "option": 2}]   # number taken; no longer wants one
    feed(link, [[]] * 10, t0=7)
    feed(link, double_tap(1), t0=10)
    feed(link, [[hand(("index", "middle", "ring"))]] * 15, t0=13)  # a number now: ignored
    assert [a["type"] for a in got] == ["choose", "next"]


def _to_growth(store):
    store.dispatch({"type": "configure", "players": [{"name": "H", "spirit": "River Surges in Sunlight"}],
                    "boards": ["C"]}, "manual")
    for _ in range(40):
        if store.game.state["step"] == "spirit.growth":
            return
        if store.game.state["step"] == "setup.first_explore" and not store.game.state["invaders"]["slots"]["explore"]:
            from spirit_island.engine.game import possible_next_cards
            store.dispatch({"type": "reveal_invader", "card": possible_next_cards(store.game.state)[0]}, "manual")
        store.dispatch({"type": "next", "screen": True}, "manual")
    raise AssertionError(store.game.state["step"])


def test_store_maps_gestures_to_game_actions(tmp_path):
    app = create_app(str(tmp_path), vision_url="")
    store = app.config["STORE"]
    assert store.choices_open() == 0
    with pytest.raises(Exception):
        store.gesture_action({"type": "undo"})      # nothing to undo yet: refused
    _to_growth(store)
    assert store.choices_open() == 3
    store.gesture_action({"type": "choose", "option": 2})
    assert store.game.state["growth_choice"]["0"] == 2
    assert store.game.state["log"][-1]["source"] == "gesture"
    assert store.choices_open() == 2                    # now: which track?
    store.gesture_action({"type": "choose", "option": 1})
    n = store.choices_open()                            # which land?
    assert n >= 1 and store.game.state["pending"]["kind"] == "land"
    store.gesture_action({"type": "undo"})              # back to: which track?
    assert store.game.state["pending"]["kind"] == "track"
    store.gesture_action({"type": "undo"})              # back to picking the option
    assert store.choices_open() == 3
    store.gesture_action({"type": "choose", "option": 1})   # option 1 asks nothing more
    assert store.choices_open() == 0
    store.gesture_action({"type": "next"})
    assert store.game.state["step"] != "spirit.growth" or store.game.state.get("sub", 0) > 0
    store.gesture_action({"type": "undo"})
    assert store.game.state["step"] == "spirit.growth"
    with pytest.raises(Exception):
        store.gesture_action({"type": "choose", "option": 9})   # not an option: refused


def test_gesture_status_endpoint(tmp_path):
    app = create_app(str(tmp_path), vision_url="")
    assert app.test_client().get("/api/gestures").json == {"camera": "off"}


def test_nothing_counts_until_the_spot_is_set_and_only_inside_it():
    got = []
    link = GestureLink(on_action=got.append)
    feed(link, double_tap(1))
    assert got == [] and link.public()["spot"]["setting"]
    with_spot(link)                                        # spot around (300, 300)
    far = [[hand(("index",), at=(900, 300))]] * 8 + [[hand(("index",), at=(900, 300), index_len=1.12)]] * 3 \
        + [[hand(("index",), at=(900, 300))]] * 3 + [[hand(("index",), at=(900, 300), index_len=1.12)]] * 3 \
        + [[hand(("index",), at=(900, 300))]] * 8
    feed(link, far, t0=10)                                 # over the map: ignored
    assert got == []
    feed(link, double_tap(1), t0=20)
    assert [a["type"] for a in got] == ["next"]
    link.set_spot_again()
    assert link.public()["spot"]["setting"]


def test_spot_endpoint(tmp_path):
    app = create_app(str(tmp_path), vision_url="")
    store = app.config["STORE"]
    store.gestures = with_spot(GestureLink(on_action=store.gesture_action, choices=store.choices_open))
    r = app.test_client().post("/api/gestures/spot")
    assert r.json["spot"]["setting"] is True


def test_moving_pieces_on_the_map_fires_nothing_with_a_spot_set():
    """Harrison's piece-moving check (2026-11-18) fired one false Next with no spot. With
    the spot where his palm was during that day's live tap run, the same hand points fire
    nothing (his hand came within 253 px of it; the spot reaches about 205)."""
    import csv
    from pathlib import Path
    got = []
    link = GestureLink(on_action=got.append, choices=lambda: 3)
    link.zone.spot = (941, 484, 1.2 * 170)   # where his palm was in the live tap run
    for row in csv.DictReader(open(Path(__file__).parent / "data" / "rest_moves_frames.csv")):
        hands = [[(float(row[f"x{i}"]), float(row[f"y{i}"])) for i in range(21)]] if row["x0"] else []
        link.process(float(row["t"]), hands)
    assert got == []


def test_next_leaves_a_screen_that_shows_a_single_line(tmp_path):
    """The TV's "No fast powers this round" screen has one line; one Next must leave it
    (it used to walk the plain guide's 8 hidden lines first)."""
    app = create_app(str(tmp_path), vision_url="")
    store = app.config["STORE"]
    _to_growth(store)
    step = store.game.state["step"]
    plain = store._snapshot

    def one_line():
        out = plain()
        out["guide"] = {**out["guide"], "single": True, "do": ["Nothing happens now."]}
        return out
    store._snapshot = one_line
    store.dispatch({"type": "next"}, "gesture")
    assert store.game.state["step"] != step


def test_a_hand_drifting_while_tapping_stays_in_the_spot():
    got = []
    link = with_spot(GestureLink(on_action=got.append))   # spot at (300, 300), r = 48 px
    drift = (300 + 1.2 * 0.8 * 60, 300)                  # past the edge, inside the keep reach
    rest, lift = hand(("index",), at=drift), hand(("index",), at=drift, index_len=1.12)
    feed(link, [[hand(("index",))]] * 5, t0=0)           # comes in at the centre
    feed(link, [[rest]] * 15 + [[lift]] * 3 + [[rest]] * 3 + [[lift]] * 3 + [[rest]] * 8, t0=0.25)
    assert [a["type"] for a in got] == ["next"]
