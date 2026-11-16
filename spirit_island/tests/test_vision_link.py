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


def test_piece_memory_keeps_a_piece_the_detector_missed_and_lets_go_of_a_removed_one():
    import numpy as np

    from spirit_island.perception.memory import PieceMemory

    rng = np.random.default_rng(1)
    board = (rng.integers(60, 200, (300, 300, 3))).astype(np.uint8)
    board = __import__("cv2").GaussianBlur(board, (7, 7), 0)
    with_piece = board.copy()
    with_piece[100:140, 100:140] = 235           # a pale square piece
    with_piece[115:125, 100:140] = 40            # with a dark stripe, so it has a pattern
    mem = PieceMemory(board, keep_for=2)
    seen = {"type": "town", "reference_bbox": [100, 100, 40, 40], "land": "2"}
    for _ in range(2):  # detected twice: now it's remembered
        mem.update({"registered": True, "_aligned": with_piece, "pieces": [dict(seen)]})
    dimmer = (with_piece * 0.6).astype(np.uint8)  # the light changes and the detector misses it
    r = mem.update({"registered": True, "_aligned": dimmer, "pieces": []})
    assert [p["type"] for p in r["pieces"]] == ["town"] and r["pieces"][0]["remembered"]
    for _ in range(3):  # taken off the board: the spot looks like the empty board again
        r = mem.update({"registered": True, "_aligned": board, "pieces": []})
    assert r["pieces"] == [] and mem.tracks == []


def _lands(**over):
    base = {f"C{n}": {"explorers": 0, "towns": 0, "cities": 0, "dahan": 0, "blight": 0, "presence": 0,
                      "terrain": None, "coastal": n <= 3} for n in range(1, 9)}
    for lid, vals in over.items():
        base[lid].update(vals)
    return base


def test_everything_vanishing_at_once_is_the_camera_not_the_game():
    from spirit_island.vision_link import blind

    lands = _lands(C1={"dahan": 2}, C2={"towns": 1, "cities": 1}, C5={"blight": 1})
    assert blind(to_game_counts({}, "C"), lands)
    assert not blind(to_game_counts({"1": {"dahan": 2}, "2": {"town": 1, "city": 1}}, "C"), lands)


def test_suggestions_are_judged_by_the_step():
    from spirit_island.vision_link import judge

    lands = _lands(C3={"terrain": "J"}, C4={"terrain": "S"})
    state = {"step": "invader.explore", "lands": lands,
             "invaders": {"slots": {"explore": "J", "build": None, "ravage": None}}}
    assert judge(state, {"land": "C3", "delta": {"explorers": 1}})[0] == "expected"
    assert judge(state, {"land": "C4", "delta": {"explorers": 1}})[0] == "unusual"
    assert judge(state, {"land": "C3", "delta": {"cities": -1}})[0] == "unusual"
    assert judge({**state, "step": "fast"}, {"land": "C4", "delta": {"dahan": -1}})[0] == "plausible"


def test_a_suggestion_must_hold_before_it_counts():
    from spirit_island.vision_link import VisionLink

    v = VisionLink("http://camera.invalid")
    state = {"step": "fast", "boards": ["C"], "lands": _lands(C1={"dahan": 1}, C2={"towns": 1}),
             "invaders": {"slots": {}}}
    reading = {"1": {"dahan": 1}, "2": {"town": 1}, "6": {"explorer": 1}}
    v.error, v.raw = None, {"status": "ok", "settled": "settled", "board_state": reading}
    v.history = [reading]
    (d,) = v.public(state)["diffs"]
    assert d["land"] == "C6" and not d["confirmed"]
    v.history = [reading, reading]
    assert v.public(state)["diffs"][0]["confirmed"]
