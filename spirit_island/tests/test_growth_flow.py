"""Growth walks the chosen option one question at a time: track, then land."""

import pytest

from spirit_island.engine import ActionError, Game, describe
from spirit_island.engine.game import possible_next_cards


def to_growth():
    g = Game()
    g.dispatch({"type": "configure", "players": [{"name": "H", "spirit": "River Surges in Sunlight"}], "boards": ["C"]})
    for _ in range(40):
        if g.state["step"] == "spirit.growth":
            return g
        if g.state["step"] == "setup.first_explore" and not g.state["invaders"]["slots"]["explore"]:
            g.dispatch({"type": "reveal_invader", "card": possible_next_cards(g.state)[0]})
        g.dispatch({"type": "next", "screen": True})
    raise AssertionError(g.state["step"])


def test_option_two_asks_track_then_land_twice():
    g = to_growth()
    g.dispatch({"type": "growth_choice", "option": 2})
    q = g.state["pending"]
    assert q["kind"] == "track" and describe(g.state)["title"] == "Growth: which track?"
    g.dispatch({"type": "choose", "option": 1})                 # energy track
    q = g.state["pending"]
    assert q["kind"] == "land" and q["track"] == "energy"
    lands = q["options"]
    assert "C8" in lands                                        # starting presence is in C8
    d = describe(g.state)
    assert d["title"] == "Growth: which land?" and d["marks"][lands[0]]["text"] == "1"
    before = g.state["lands"][lands[0]]["presence"]
    g.dispatch({"type": "choose", "option": 1})
    assert g.state["lands"][lands[0]]["presence"] == before + 1
    assert g.state["spirits"]["0"]["taken"]["energy"] == 1
    assert g.state["pending"]["kind"] == "track"               # the second presence
    g.dispatch({"type": "choose", "option": 2})
    g.dispatch({"type": "choose", "option": 1})
    assert g.state["pending"] is None
    assert g.state["spirits"]["0"]["taken"] == {"energy": 1, "cards": 1}
    assert "Presence placed" in " ".join(describe(g.state)["do"])
    g.dispatch({"type": "undo"})                               # takes the last answer back
    assert g.state["pending"]["kind"] == "land"


def test_option_three_reaches_range_two_and_option_one_asks_nothing():
    g = to_growth()
    g.dispatch({"type": "growth_choice", "option": 3})
    g.dispatch({"type": "choose", "option": 2})
    near = set(Game.lands_within(g, 1))
    far = set(g.state["pending"]["options"])
    assert near < far and g.state["pending"]["range"] == 2
    g2 = to_growth()
    g2.dispatch({"type": "growth_choice", "option": 1})
    assert g2.state["pending"] is None


def test_wrong_number_is_refused_and_leaving_growth_clears_questions():
    g = to_growth()
    g.dispatch({"type": "growth_choice", "option": 2})
    with pytest.raises(ActionError):
        g.dispatch({"type": "choose", "option": 3})
    g.dispatch({"type": "next", "screen": True})
    assert g.state["step"] != "spirit.growth" and g.state["pending"] is None
