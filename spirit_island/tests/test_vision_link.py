from spirit_island.vision_link import differences, to_game_counts


def test_detector_names_become_game_pieces():
    seen = to_game_counts({"1": {"dahan": 1}, "6": {"explorer": 2, "presence (yellow)": 1, "presence (red)": 1},
                           "?": {"town": 1}, "ocean": {"city": 1}, "3": {"unknown": 1, "energy": 2}}, "C")
    assert set(seen) == {f"C{n}" for n in range(1, 9)}
    assert seen["C6"]["explorers"] == 2 and seen["C6"]["presence"] == 2
    assert seen["C1"]["dahan"] == 1
    assert sum(seen["C3"].values()) == 0


def test_differences_only_lists_disagreeing_lands():
    seen = to_game_counts({"2": {"town": 1}}, "A")
    lands = {f"A{n}": {"explorers": 0, "towns": 0, "cities": 0, "dahan": 0, "blight": 0, "presence": 0} for n in range(1, 9)}
    lands["A5"]["dahan"] = 2
    diffs = differences(seen, lands)
    assert {d["land"]: d["delta"] for d in diffs} == {"A2": {"towns": 1}, "A5": {"dahan": -2}}
