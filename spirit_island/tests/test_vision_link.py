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


def test_board_map_straightens_lands_and_places_pieces(tmp_path):
    import json

    import cv2
    import numpy as np

    from spirit_island.board_map import BoardMap

    labels = np.zeros((400, 600), np.uint8)
    labels[100:300, 100:300] = 1   # land "1" on the left
    labels[100:300, 300:500] = 2   # land "2" on the right
    cv2.imwrite(str(tmp_path / "lands.png"), labels)
    (tmp_path / "lands.json").write_text(json.dumps({"names": ["1", "2"], "seeds": {}}))
    (tmp_path / "reference.json").write_text(json.dumps({"board": {"quad": [[100, 100], [500, 100], [500, 300], [100, 300]]}}))
    m = BoardMap(tmp_path).public()
    assert m["width"] == 1000 and abs(m["height"] - 500) <= 3
    left, right = (next(l for l in m["lands"] if l["name"] == n)["centre"] for n in ("1", "2"))
    assert left[0] < 500 < right[0]
    placed = BoardMap(tmp_path).place([{"type": "town", "land": "2", "reference_bbox": [390, 190, 20, 20]},
                                       {"type": "unknown", "reference_bbox": [0, 0, 1, 1]}])
    assert len(placed) == 1 and abs(placed[0]["x"] - 750) < 5 and abs(placed[0]["y"] - 250) < 5
