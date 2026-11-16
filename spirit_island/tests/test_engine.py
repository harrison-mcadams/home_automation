import pytest

from spirit_island.engine import ActionError, Game, describe
from spirit_island.engine import game as g


def setup_game(players=1, terrains=None):
    game = Game()
    game.dispatch({"type": "configure",
                   "players": [{"name": f"P{i}", "spirit": "River Surges in Sunlight"} for i in range(players)],
                   "terrains": terrains or {}})
    while game.state["step"] != "setup.first_explore":
        game.dispatch({"type": "next"})
    return game


def test_setup_numbers_scale_with_players():
    game = setup_game(players=2)
    s = game.state
    assert s["fear"]["pool_size"] == 8
    assert s["blight"]["pool"] == 5
    assert s["boards"] == ["A", "B"]
    assert len(s["lands"]) == 16
    assert s["lands"]["A1"]["coastal"] and not s["lands"]["A5"]["coastal"]


def test_every_step_has_guidance():
    game = setup_game()
    game.dispatch({"type": "reveal_invader", "card": "J"})
    game.dispatch({"type": "next"})
    seen = set()
    for _ in range(40):
        info = describe(game.state)
        assert info["title"] and info["do"], game.state["step"]
        seen.add(game.state["step"])
        if game.state["step"] == "invader.explore":
            game.dispatch({"type": "reveal_invader", "card": g.possible_next_cards(game.state)[0]})
        game.dispatch({"type": "next"})
    assert {"spirit.growth", "fast", "invader.ravage", "invader.build", "invader.explore", "slow",
            "time_passes"} <= seen


def test_first_explore_card_moves_to_build_then_ravage():
    game = setup_game()
    with pytest.raises(ActionError):
        game.dispatch({"type": "next"})  # must reveal first
    game.dispatch({"type": "reveal_invader", "card": "W"})
    game.dispatch({"type": "next"})
    s = game.state
    assert s["status"] == "playing" and s["round"] == 1
    assert s["invaders"]["slots"] == {"ravage": None, "build": "W", "explore": None}
    while s["step"] != "invader.explore":
        game.dispatch({"type": "next"})
        s = game.state
    with pytest.raises(ActionError):
        game.dispatch({"type": "reveal_invader", "card": "W"})  # already drawn
    game.dispatch({"type": "reveal_invader", "card": "S"})
    game.dispatch({"type": "next"})  # -> advance
    game.dispatch({"type": "next"})  # slides cards
    assert game.state["invaders"]["slots"] == {"ravage": "W", "build": "S", "explore": None}
    assert game.state["step"] == "slow"


def test_fear_earns_cards_and_raises_terror():
    game = setup_game()
    game.dispatch({"type": "reveal_invader", "card": "J"})
    game.dispatch({"type": "next"})
    game.dispatch({"type": "fear", "amount": 4 * 3})
    s = game.state
    assert s["fear"]["earned_total"] == 3 and s["fear"]["unresolved"] == 3
    assert g.terror_level(s) == 2
    # Fear step is not skipped when cards are waiting.
    while s["step"] != "invader.fear":
        game.dispatch({"type": "next"})
        s = game.state
    game.dispatch({"type": "resolve_fear_card"})
    assert game.state["fear"]["unresolved"] == 2


def test_fear_step_skipped_when_nothing_earned():
    game = setup_game()
    game.dispatch({"type": "reveal_invader", "card": "J"})
    game.dispatch({"type": "next"})
    steps = []
    for _ in range(8):
        if game.state["step"] == "invader.explore":
            game.dispatch({"type": "reveal_invader", "card": "W"})
        game.dispatch({"type": "next"})
        steps.append(game.state["step"])
    assert "invader.fear" not in steps and "invader.blighted" not in steps


def test_earning_whole_fear_deck_wins():
    game = setup_game()
    game.dispatch({"type": "reveal_invader", "card": "J"})
    game.dispatch({"type": "next"})
    game.dispatch({"type": "fear", "amount": 4 * 9})
    assert game.state["status"] == "won"
    assert game.state["result"]["score"] == 10 + 2 * g.invader_cards_left(game.state)


def test_ravage_preview_and_apply():
    land = {"explorers": 1, "towns": 1, "cities": 0, "dahan": 2, "blight": 1, "presence": 0,
            "terrain": "J", "coastal": True}
    p = g.ravage_preview(land)
    assert p["damage"] == 3 and p["blight"] and p["cascade"]
    assert p["dahan_killed"] == 1 and p["fight_back"] == 2
    assert p["invaders_killed"] == {"cities": 0, "towns": 1, "explorers": 0}

    game = setup_game(terrains={"A1": "J"})
    game.dispatch({"type": "land", "land": "A1", "piece": "towns", "value": 1})
    game.dispatch({"type": "land", "land": "A1", "piece": "explorers", "value": 1})
    game.dispatch({"type": "land", "land": "A1", "piece": "dahan", "value": 2})
    pool = game.state["blight"]["pool"]
    game.dispatch({"type": "apply_ravage", "land": "A1"})
    a1 = game.state["lands"]["A1"]
    assert (a1["towns"], a1["explorers"], a1["dahan"], a1["blight"]) == (0, 1, 1, 1)
    assert game.state["blight"]["pool"] == pool - 1


def test_build_rule():
    land = {"explorers": 1, "towns": 0, "cities": 0}
    assert g.build_preview(land) == "towns"
    assert g.build_preview({"explorers": 0, "towns": 2, "cities": 1}) == "cities"
    assert g.build_preview({"explorers": 0, "towns": 1, "cities": 1}) == "towns"
    assert g.build_preview({"explorers": 0, "towns": 0, "cities": 0}) is None


def test_card_matching_uses_terrain_and_coast():
    game = setup_game(terrains={"A1": "J", "A5": "M"})
    s = game.state
    assert g.land_matches(s, "A1", "JW") is True
    assert g.land_matches(s, "A5", "JW") is False
    assert g.land_matches(s, "A6", "JW") is None   # untagged
    assert g.land_matches(s, "A2", "C") is True
    assert g.land_matches(s, "A5", "C") is False


def test_blight_pool_loss_after_flip():
    game = setup_game()
    game.dispatch({"type": "reveal_invader", "card": "J"})
    game.dispatch({"type": "next"})
    game.dispatch({"type": "blight", "land": "A1", "amount": 3})
    assert game.state["blight"]["pool"] == 0 and game.state["status"] == "playing"
    game.dispatch({"type": "flip_blight_card", "add": 5})
    game.dispatch({"type": "blight", "land": "A2", "amount": 5})
    assert game.state["status"] == "lost"


def test_invader_deck_running_out_loses():
    game = setup_game()
    game.dispatch({"type": "reveal_invader", "card": "J"})
    game.dispatch({"type": "next"})
    for _ in range(200):
        if game.state["status"] != "playing":
            break
        if game.state["step"] == "invader.explore":
            game.dispatch({"type": "reveal_invader", "card": g.possible_next_cards(game.state)[0]})
        game.dispatch({"type": "next"})
    assert game.state["status"] == "lost"
    assert "deck" in game.state["result"]["reason"]
    # 12 cards: one explored in setup, then 11 rounds of explores; round 12 has none left.
    assert game.state["round"] == 12
    assert game.state["invaders"]["drawn"][3] == "J"  # Stage II Jungle is not blocked by Stage I Jungle


def test_undo_restores_previous_state():
    game = setup_game()
    game.dispatch({"type": "land", "land": "A3", "piece": "dahan", "delta": 2})
    game.dispatch({"type": "undo"})
    assert game.state["lands"]["A3"]["dahan"] == 0


def test_observe_records_vision_source():
    game = setup_game()
    game.dispatch({"type": "observe", "lands": {"A2": {"explorers": 2}}, "slots": {"build": "M"}},
                  source="vision")
    assert game.state["lands"]["A2"]["explorers"] == 2
    assert game.state["invaders"]["slots"]["build"] == "M"
    assert game.state["log"][-1]["source"] == "vision"


def test_bad_action_leaves_state_untouched():
    game = setup_game()
    before = repr(game.state)
    with pytest.raises(ActionError):
        game.dispatch({"type": "land", "land": "Z9", "piece": "dahan", "delta": 1})
    assert repr(game.state) == before
