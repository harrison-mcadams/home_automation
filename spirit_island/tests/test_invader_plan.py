"""The game works out Ravage, Build and Explore itself and applies them on Next."""

from spirit_island.engine import Game
from spirit_island.engine import invader_plan as ip


def game_on_c():
    game = Game()
    game.dispatch({"type": "configure", "players": [{"name": "P", "spirit": "River Surges in Sunlight"}],
                   "boards": ["C"]})
    while game.state["step"] != "setup.first_explore":
        game.dispatch({"type": "next", "screen": True})
    return game


def clear(game):
    for land in game.state["lands"].values():
        for p in ("explorers", "towns", "cities", "dahan", "blight", "presence"):
            land[p] = 0


def go_to(game, step):
    while game.state["step"] != step:
        if game.state["step"] == "invader.explore" and not game.state["invaders"]["slots"]["explore"]:
            game.dispatch({"type": "reveal_invader", "card": "J"})
        game.dispatch({"type": "next", "screen": True})


def terrain_land(game, t, coastal=None):
    for lid, land in sorted(game.state["lands"].items()):
        if land["terrain"] == t and (coastal is None or land["coastal"] == coastal):
            return lid
    raise AssertionError(f"no {t} land")


def test_first_explore_places_explorers():
    game = game_on_c()
    clear(game)
    game.dispatch({"type": "reveal_invader", "card": "S"})
    plan = ip.explore_plan(game.state, "S")
    yes = [r["land"] for r in plan if r["changes"]]
    assert yes
    game.dispatch({"type": "next", "screen": True})
    for lid in yes:
        assert game.state["lands"][lid]["explorers"] == 1


def test_ravage_explains_blight_and_dahan_and_applies_on_next():
    game = game_on_c()
    game.dispatch({"type": "reveal_invader", "card": "S"})
    game.dispatch({"type": "next", "screen": True})
    go_to(game, "invader.ravage")
    clear(game)
    s = game.state
    s["invaders"]["slots"]["ravage"] = "M"
    lid = terrain_land(game, "M")
    land = s["lands"][lid]
    land.update(cities=1, explorers=1, dahan=2, presence=1)
    pool = s["blight"]["pool"]
    [row] = [r for r in ip.ravage_plan(s, "M") if r["land"] == lid]
    # 4 damage: 1 blight (destroys the presence), 2 Dahan destroyed, nothing fights back.
    assert row["changes"] == {"blight": 1, "presence": -1, "dahan": -2}
    assert "4 damage" in row["why"] and "2 or more" in row["why"]
    game.dispatch({"type": "next", "screen": True})
    assert game.state["step"] == "invader.build"
    land = game.state["lands"][lid]
    assert (land["blight"], land["presence"], land["dahan"]) == (1, 0, 0)
    assert game.state["blight"]["pool"] == pool - 1
    # Undo puts it all back.
    game.dispatch({"type": "undo"})
    assert game.state["lands"][lid]["dahan"] == 2


def test_dahan_fight_back_and_cascade():
    game = game_on_c()
    s = game.state
    clear(game)
    lid = terrain_land(game, "W")
    s["lands"][lid].update(explorers=2, dahan=2, blight=1)
    rows = ip.ravage_plan(s, "W")
    mine = [r for r in rows if r["land"] == lid and "cascaded_from" not in r][0]
    # 2 damage: 1 blight, 1 Dahan destroyed; the other Dahan destroys 2 explorers.
    assert mine["changes"] == {"blight": 1, "dahan": -1, "explorers": -2}
    assert mine["cascade"]
    casc = [r for r in rows if lid in r.get("cascaded_from", [])]
    assert casc and casc[0]["changes"]["blight"] == 1
    assert casc[0]["land"] in ip.neighbours(s, lid)


def test_build_town_or_city_with_reason():
    game = game_on_c()
    s = game.state
    clear(game)
    a = terrain_land(game, "J")
    s["lands"][a]["towns"] = 1
    rows = {r["land"]: r for r in ip.build_plan(s, "J")}
    assert rows[a]["changes"] == {"cities": 1} and "more towns" in rows[a]["why"]
    s["lands"][a].update(towns=0, explorers=1)
    rows = {r["land"]: r for r in ip.build_plan(s, "J")}
    assert rows[a]["changes"] == {"towns": 1}


def test_manual_apply_is_not_applied_twice():
    game = game_on_c()
    game.dispatch({"type": "reveal_invader", "card": "S"})
    game.dispatch({"type": "next", "screen": True})
    go_to(game, "invader.build")
    clear(game)
    s = game.state
    s["invaders"]["slots"]["build"] = "J"
    a = terrain_land(game, "J")
    s["lands"][a]["explorers"] = 1
    game.dispatch({"type": "apply_build", "land": a})
    assert game.state["lands"][a]["towns"] == 1
    game.dispatch({"type": "next", "screen": True})
    assert game.state["lands"][a]["towns"] == 1


def test_describe_words():
    assert ip.describe({"blight": 1, "dahan": -2}) == "add 1 blight, remove 2 Dahan"
    assert ip.describe({"explorers": 1}) == "add 1 explorer"
    assert ip.describe({}) == "nothing"


def test_leaving_pieces_step_records_starting_pieces():
    game = Game()
    game.dispatch({"type": "configure", "players": [{"name": "P", "spirit": "River Surges in Sunlight"}],
                   "boards": ["C"]})
    while game.state["step"] != "setup.pieces":
        game.dispatch({"type": "next", "screen": True})
    game.dispatch({"type": "next", "screen": True})
    assert game.state["start_placed"]
    assert sum(l["dahan"] for l in game.state["lands"].values()) > 0
