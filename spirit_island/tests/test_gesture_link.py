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


def double_tap(fingers=1):
    up = ("index", "middle") if fingers == 2 else ("index",)
    rest, lift = hand(up), hand(up, index_len=1.12)
    return [[rest]] * 8 + [[lift]] * 3 + [[rest]] * 3 + [[lift]] * 3 + [[rest]] * 8


def test_taps_become_next_and_undo():
    got = []
    link = GestureLink(on_action=got.append)
    feed(link, double_tap(1))
    t = feed(link, [[]] * 20, t0=10)
    feed(link, double_tap(2), t0=t + 1)
    assert [a["type"] for a in got] == ["next", "undo"]


def test_numbers_only_count_while_a_choice_is_open():
    got = []
    open_ = [0]
    link = GestureLink(on_action=got.append, choices=lambda: open_[0])
    feed(link, [[hand(("index", "middle", "ring"))]] * 20)
    assert got == []
    open_[0] = 3
    feed(link, [[]] * 10, t0=5)
    feed(link, [[hand(("index", "middle", "ring"))]] * 20, t0=10)
    assert got == [{"type": "choose", "option": 3}]
    feed(link, [[]] * 10, t0=15)
    feed(link, [[hand(("index", "middle", "ring", "pinky", "thumb"))]] * 20, t0=20)
    assert len(got) == 1  # 5 is not one of the 3 options


def test_one_finger_choice_waits_and_a_double_tap_cancels_it():
    got = []
    link = GestureLink(on_action=got.append, choices=lambda: 3)
    feed(link, [[hand(("index",))]] * 50)  # held 2.5 s: counts as option 1
    assert got == [{"type": "choose", "option": 1}]
    got.clear()
    feed(link, [[]] * 10, t0=10)
    feed(link, double_tap(1), t0=20)       # finger rests ~0.4 s, then taps: Next only
    assert [a["type"] for a in got] == ["next"]


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
    store.gesture_action({"type": "undo"})          # nothing to undo yet: ignored
    _to_growth(store)
    assert store.choices_open() == 3
    store.gesture_action({"type": "choose", "option": 2})
    assert store.game.state["growth_choice"]["0"] == 2
    assert store.game.state["log"][-1]["source"] == "gesture"
    store.gesture_action({"type": "next"})
    assert store.game.state["step"] != "spirit.growth" or store.game.state.get("sub", 0) > 0
    store.gesture_action({"type": "undo"})
    assert store.game.state["step"] == "spirit.growth"
    store.gesture_action({"type": "choose", "option": 9})   # not an option: refused quietly


def test_gesture_status_endpoint(tmp_path):
    app = create_app(str(tmp_path), vision_url="")
    assert app.test_client().get("/api/gestures").json == {"camera": "off"}
