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
    assert store.point_targets() == ["growth:1", "growth:2", "growth:3"]
    store.gesture_action({"type": "choose", "option": 2})
    assert store.game.state["growth_choice"]["0"] == 2
    assert store.game.state["log"][-1]["source"] == "gesture"
    assert store.choices_open() == 2                    # now: which track?
    assert store.point_targets() == ["track:energy", "track:cards"]
    store.gesture_action({"type": "choose", "option": 1})
    assert store.point_targets()[0].startswith("land:")
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


def test_a_second_hand_anywhere_adds_fingers_when_more_than_five_options():
    got = []
    link = with_spot(GestureLink(on_action=got.append, choices=lambda: 7))
    five = hand(("thumb", "index", "middle", "ring", "pinky"))
    two_far = hand(("index", "middle"), at=(900, 300))
    feed(link, [[five, two_far]] * 15, t0=0)
    assert got == [{"type": "choose", "option": 7}]
    got.clear()
    link.choices = lambda: 3                             # 3 options: the far hand is ignored
    feed(link, [[]] * 10, t0=5)
    feed(link, [[hand(("index", "middle")), hand(("index",), at=(900, 300))]] * 15, t0=10)
    assert got == [{"type": "choose", "option": 2}]


class _Board:
    """Stands in for the board finder: the left half of the picture is land C4."""
    def land_at(self, pt):
        return "C4" if pt[0] < 500 else None


def test_pointing_at_a_lit_land_answers_which_land():
    got = []
    link = with_spot(GestureLink(on_action=got.append, choices=lambda: 2,
                                 land_options=lambda: ["C2", "C4"], board=_Board()))
    over_map = hand(("index",), at=(300, 700))        # outside the spot, over "C4"
    feed(link, [[over_map]] * 20, t0=0)
    assert got == [{"type": "choose", "option": 2}]
    assert link.public()["pointing"] == "land 4"


def test_pointing_off_the_lit_lands_does_nothing():
    got = []
    link = with_spot(GestureLink(on_action=got.append, choices=lambda: 2,
                                 land_options=lambda: ["C2", "C4"], board=_Board()))
    feed(link, [[hand(("index",), at=(900, 700))]] * 20, t0=0)
    assert got == []


def test_land_lookup_through_the_alignment():
    import numpy as np
    from spirit_island.touch.board_point import LandLookup, rotate_point
    labels = np.zeros((100, 200), np.uint8)
    labels[:, :100], labels[:, 100:] = 1, 2
    look = LandLookup(labels, ["3", "ocean"], "C")
    assert look.land_at((10, 10)) is None              # not lined up yet
    look.homography, look.frame_size = np.eye(3), (200, 100)
    assert look.land_at((10, 10)) == "C3" and look.land_at((150, 10)) is None  # ocean
    assert rotate_point(0, 0, 200, 100, 90) == (99, 0)


def test_an_implausible_alignment_is_rejected():
    import numpy as np
    from spirit_island.touch.board_point import plausible
    assert plausible(np.eye(3), (400, 600), (1280, 720))
    squash = np.diag([50.0, 50.0, 1.0])                 # board would be a speck
    assert not plausible(squash, (400, 600), (1280, 720))


class _Panel:
    """Stands in for the panel finder: three growth boxes across the top of the picture,
    the energy row below them, the card plays row below that."""
    kinds = {"growth", "track"}
    status = "lined up"

    def target_at(self, pt):
        x, y = pt
        if x < 400:
            return None              # where the tap spot is
        if y < 200:
            return f"growth:{int(x // 400)}"
        if y < 400:
            return "track:energy"
        if y < 600:
            return "track:cards"
        return None


def test_pointing_at_a_growth_option_picks_it_without_counting():
    got = []
    link = with_spot(GestureLink(on_action=got.append, choices=lambda: 3,
                                 targets=lambda: ["growth:1", "growth:2", "growth:3"], pointers=[_Panel()]))
    # A pointing finger in the spot no longer reads as "1" while you can point instead.
    feed(link, [[hand(("index",))]] * 30, t0=0)
    assert got == []
    feed(link, [[]] * 10, t0=5)
    feed(link, [[hand(("index",), at=(1000, 250))]] * 20, t0=10)   # over option 2
    assert got == [{"type": "choose", "option": 2}]


def test_pointing_at_a_presence_row():
    got = []
    link = GestureLink(on_action=got.append, choices=lambda: 2,
                       targets=lambda: ["track:energy", "track:cards"], pointers=[_Panel()])
    feed(link, [[hand(("index",), at=(500, 650))]] * 20, t0=0)
    assert got == [{"type": "choose", "option": 2}]
    assert link.public()["pointing"] == "the card plays row"


def test_one_long_point_answers_only_one_question():
    """Option 2 asks for two lands, and the same land can be legal both times: the second
    answer needs the hand to move or lift first."""
    got = []
    link = GestureLink(on_action=got.append, choices=lambda: 2,
                       land_options=lambda: ["C2", "C4"], board=_Board())
    feed(link, [[hand(("index",), at=(300, 700))]] * 60, t0=0)
    assert got == [{"type": "choose", "option": 2}]


def test_finger_counts_are_the_backup_when_the_panel_isnt_found():
    got = []
    panel = _Panel()
    panel.status = "can't find the board"
    link = with_spot(GestureLink(on_action=got.append, choices=lambda: 3,
                                 targets=lambda: ["growth:1", "growth:2", "growth:3"], pointers=[panel]))
    feed(link, [[hand(("index", "middle"))]] * 15, t0=0)
    assert got == [{"type": "choose", "option": 2}]


def test_panel_regions_and_lookup():
    import numpy as np
    from spirit_island.touch.board_point import PanelLookup, panel_regions
    regions = panel_regions("River Surges in Sunlight")
    assert set(regions) == {"growth:1", "growth:2", "growth:3", "track:energy", "track:cards"}
    look = PanelLookup(regions)
    assert look.target_at((700, 100)) is None              # not lined up yet
    look.homography, look.frame_size = np.eye(3), (1600, 1066)
    assert look.target_at((700, 100)) == "growth:1"
    assert look.target_at((1400, 120)) == "growth:3"
    assert look.target_at((682 + 3 * 117, 320)) == "track:energy"
    assert look.target_at((682, 489)) == "track:cards"
    assert look.target_at((100, 900)) is None              # the spirit's art


def test_drawn_map_follows_the_game_board_not_the_first_folder():
    from spirit_island.vision_link import VisionLink

    class M:
        def __init__(self, letter):
            self.letter = letter
    v = VisionLink("http://x", board_map={"A": M("A"), "C": M("C")})
    assert v.map.letter == "A"                      # nothing known: first folder
    v.game_board = lambda: "C"
    assert v.map.letter == "C"
    assert v.camera_board({"boards": ["C"]}) == "C"


def _to_powers(store):
    _to_growth(store)
    store.gesture_action({"type": "choose", "option": 1})      # reclaim + card + 1 energy
    for _ in range(10):
        if store.game.state["step"] == "spirit.powers":
            return
        store.dispatch({"type": "next", "screen": True}, "manual")
    raise AssertionError(store.game.state["step"])


class _Cards:
    """Stands in for the card watcher: Wash Away (1) and Flash Floods (2) in view; the
    right half of the picture is Flash Floods, the left half Wash Away."""
    kinds = {"card"}
    status = "lined up"

    def public(self):
        return {"active": True, "cards": [{"name": "Flash Floods", "cost": 2, "speed": "fast"},
                                          {"name": "Wash Away", "cost": 1, "speed": "slow"}], "cost": 3}

    def target_at(self, pt):
        return "card:Flash Floods" if pt[0] > 500 else "card:Wash Away"


def test_gain_energy_adds_energy_when_the_camera_does_not_count_tokens(tmp_path):
    app = create_app(str(tmp_path), vision_url="")
    store = app.config["STORE"]
    _to_powers(store)
    s = store.game.state
    s["energy_from_camera"] = True                   # an old save from the camera-tracking days
    store.gesture_action({"type": "undo"})
    while store.game.state["step"] != "spirit.energy":
        store.gesture_action({"type": "undo"})
    store.game.state["energy_from_camera"] = True
    before = store.game.state["spirits"]["0"]["energy"]
    store.dispatch({"type": "next", "screen": True}, "manual")
    assert store.game.state["spirits"]["0"]["energy"] > before


def test_pointing_at_a_card_plays_and_pays_for_it(tmp_path):
    app = create_app(str(tmp_path), vision_url="")
    store = app.config["STORE"]
    store.power_watch = _Cards()
    _to_powers(store)
    s = store.game.state
    s["spirits"]["0"]["energy"] = 2
    s["spirits"]["0"]["taken"]["cards"] = 1           # 2 card plays
    assert store.point_targets() == ["card:Flash Floods", "card:Wash Away"]
    assert store.choices_open() == 0                 # double taps still go Next / Back
    guide = store.snapshot()["guide"]
    assert guide["single"] and "Point at it" in str(guide["do"])
    store.gesture_action({"type": "play_card", "card": "Wash Away"})
    s = store.game.state
    assert s["spirits"]["0"]["energy"] == 1 and [c["name"] for c in s["played"]] == ["Wash Away"]
    assert store.point_targets() == ["card:Flash Floods"]
    with pytest.raises(Exception, match="needs 2 energy"):
        store.gesture_action({"type": "play_card", "card": "Flash Floods"})
    store.gesture_action({"type": "undo"})          # takes it back, energy too
    assert store.game.state["spirits"]["0"]["energy"] == 2 and not store.game.state.get("played")
    store.gesture_action({"type": "play_card", "card": "Flash Floods"})
    store.gesture_action({"type": "next"})          # leaving charges nothing more
    assert store.game.state["step"] == "fast" and store.game.state["spirits"]["0"]["energy"] == 0


def test_link_plays_the_card_pointed_at_and_taps_still_work():
    got = []
    cards = _Cards()
    link = with_spot(GestureLink(on_action=got.append, choices=lambda: 0,
                                 targets=lambda: ["card:Flash Floods", "card:Wash Away"], pointers=[cards]))
    feed(link, [[hand(("index",), at=(900, 700))]] * 20, t0=0)
    assert got == [{"type": "play_card", "card": "Flash Floods"}]
    feed(link, [[]] * 10, t0=5)
    feed(link, double_tap(1), t0=10)
    assert got[-1] == {"type": "next"}


def test_card_watch_keeps_a_card_through_a_missed_read():
    from spirit_island.power_cards import CARD_KEEP, CardWatch
    w = CardWatch(store=None)
    quad = [[0, 0], [100, 0], [100, 150], [0, 150]]
    assert w.update([{"name": "Wash Away", "quad": quad}])
    assert w.target_at((50, 50)) == "card:Wash Away" and w.target_at((300, 50)) is None
    for _ in range(CARD_KEEP - 1):
        w.update([])                                 # a hand over it
    assert w.target_at((50, 50)) == "card:Wash Away"
    assert w.update([])                              # gone now
    assert w.target_at((50, 50)) is None
