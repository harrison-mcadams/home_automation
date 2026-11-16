"""Board and piece detection on a synthetic table: textured coloured lands on grey wood."""

import json

import cv2
import numpy as np
import pytest

from spirit_island import detect
from spirit_island.perception.board import find_board

W, H = 2400, 1800
BOARD = np.float32([[900, 600], [1900, 560], [2000, 1400], [820, 1450]])  # oblique-ish quad


def flat_board(seed=1, size=(1000, 700)):
    """A top-down 'board': coloured land patches with busy, feature-rich texture."""
    rng = np.random.default_rng(seed)
    w, h = size
    colours = [(60, 160, 60), (90, 170, 210), (190, 160, 90), (160, 148, 138), (200, 120, 40)]
    board = np.zeros((h, w, 3), np.uint8)
    for i, c in enumerate(colours):
        board[:, i * w // 5:(i + 1) * w // 5] = c
    noise = rng.integers(-60, 60, size=(h // 6, w // 6, 1))
    board = np.clip(board + cv2.resize(noise, (w, h), interpolation=cv2.INTER_NEAREST)[..., None], 0, 255)
    for _ in range(150):  # printed line-art and symbols
        p = tuple(int(v) for v in rng.integers(0, [w, h]))
        cv2.circle(board, p, int(rng.integers(5, 25)), (30, 30, 30), 2)
    return board.astype(np.uint8)


def table(seed=2):
    rng = np.random.default_rng(seed)
    grain = rng.normal(120, 12, size=(H // 4, 1)).repeat(W // 4, axis=1)
    wood = cv2.resize(grain, (W, H)).astype(np.uint8)
    return cv2.merge([wood, wood, (wood * 1.05).clip(0, 255).astype(np.uint8)])


def place(board, quad, background):
    h, w = board.shape[:2]
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), quad)
    warped = cv2.warpPerspective(board, M, (W, H))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), M, (W, H))
    out = background.copy()
    out[mask > 0] = warped[mask > 0]
    return out, M


def add_token(board, center=(330, 360), radius=35):
    b = board.copy()
    cv2.circle(b, center, radius, (215, 225, 230), -1)  # cream disc
    cv2.circle(b, (center[0] + 6, center[1] + 6), radius, (0, 0, 0), 2)  # a bit of shadow
    return b


@pytest.fixture(scope="module")
def scene():
    board = flat_board()
    reference, _ = place(board, BOARD, table())
    moved = BOARD + np.float32([[25, -15], [30, -10], [20, 5], [15, 0]])  # board nudged between photos
    with_token, M = place(add_token(board), moved, table(seed=3))
    token_xy = cv2.perspectiveTransform(np.float32([[[330, 360]]]), M).reshape(2)
    return reference, with_token, token_xy


def test_outline_finds_board(scene):
    reference, _, _ = scene
    reference = reference.copy()
    # A white mug just off the board (cool-tinted glaze, like the real one) must stay out.
    cv2.circle(reference, (1300, 330), 140, (215, 205, 195), -1)
    board = find_board(reference)
    assert board is not None
    x, y, w, h = board.bbox
    assert abs(x - 820) < 40 and abs(y - 560) < 40 and abs((x + w) - 2000) < 40 and abs((y + h) - 1450) < 40
    for got, want in zip(board.quad, BOARD):
        assert np.linalg.norm(got - want) < 60
    assert not board.touches_edge


def test_board_running_off_frame_is_flagged():
    image, _ = place(flat_board(), BOARD + np.float32([600, 0]), table())
    board = find_board(image)
    assert board is not None and board.touches_edge


def test_find_single_token_after_board_moved(scene):
    reference, with_token, token_xy = scene
    mask = find_board(reference).mask
    result = detect.detect_pieces(reference, mask, with_token)
    assert result["registered"] and result["inliers"] > 50
    assert len(result["pieces"]) == 1, result["pieces"]
    cx, cy = result["pieces"][0]["centroid"]
    assert np.hypot(cx - token_xy[0], cy - token_xy[1]) < 25


def test_empty_board_finds_nothing(scene):
    reference, _, _ = scene
    mask = find_board(reference).mask
    again, _ = place(flat_board(), BOARD + 8, table(seed=4))  # same board, slightly moved, new table noise
    result = detect.detect_pieces(reference, mask, again)
    assert result["registered"]
    assert result["pieces"] == []


def test_cli_reference_then_find(scene, tmp_path):
    reference, with_token, _ = scene
    ref_img, tok_img = tmp_path / "empty.jpg", tmp_path / "token.jpg"
    cv2.imwrite(str(ref_img), reference, [cv2.IMWRITE_JPEG_QUALITY, 95])
    cv2.imwrite(str(tok_img), with_token, [cv2.IMWRITE_JPEG_QUALITY, 95])
    ref_dir = tmp_path / "ref"
    assert detect.main(["reference", "--image", str(ref_img), "--reference", str(ref_dir)]) == 0
    assert (ref_dir / "board_mask.png").exists()
    out = tmp_path / "find"
    assert detect.main(["find", "--image", str(tok_img), "--reference", str(ref_dir), "--out", str(out)]) == 0
    result = json.loads((out / "pieces.json").read_text())
    assert len(result["pieces"]) == 1
    assert (out / "pieces.jpg").exists()
    assert detect.main(["outline", "--image", str(tok_img), "--out", str(tmp_path / "o")]) == 0


def test_thin_edge_sliver_is_not_a_piece(scene):
    reference, _, _ = scene
    mask = find_board(reference).mask
    image = reference.copy()
    cv2.rectangle(image, (1500, 900), (1512, 1000), (20, 20, 20), -1)  # 12 x 100 px dark strip
    result = detect.detect_pieces(reference, mask, image)
    assert result["registered"] and result["pieces"] == []


def test_board_turned_and_slid_still_finds_only_the_token(scene):
    """Like the real r5 photo: board rotated ~90 degrees, moved, and the room darker."""
    reference, _, _ = scene
    mask = find_board(reference).mask
    turned = np.float32([[1500, 300], [1550, 1350], [700, 1300], [760, 330]])  # corners rotated by one
    image, M = place(add_token(flat_board()), turned, table(seed=5))
    image = (image.astype(np.float32) * 0.8).astype(np.uint8)
    result = detect.detect_pieces(reference, mask, image)
    token_xy = cv2.perspectiveTransform(np.float32([[[330, 360]]]), M).reshape(2)
    assert result["registered"]
    assert len(result["pieces"]) == 1, result["pieces"]
    cx, cy = result["pieces"][0]["centroid"]
    assert np.hypot(cx - token_xy[0], cy - token_xy[1]) < 30


def test_lands_and_types_on_synthetic_board(scene, tmp_path):
    """Land map from one point per land; pieces get a land and a type."""
    from spirit_island.perception import lands as land_map

    reference, _, _ = scene
    mask = find_board(reference).mask
    board = flat_board()
    # Seeds at the centres of the five colour columns of the flat board, mapped into the photo.
    _, M = place(board, BOARD, table())
    pts = cv2.perspectiveTransform(np.float32([[[100 + 200 * i, 350]] for i in range(5)]), M).reshape(-1, 2)
    seeds = {str(i + 1): (float(x), float(y)) for i, (x, y) in enumerate(pts)}
    labels, names = land_map.segment_lands(reference, mask, seeds)
    assert set(names) == {"1", "2", "3", "4", "5"}
    for name, (x, y) in seeds.items():
        assert land_map.land_at(labels, names, x, y) == name

    piece_board = board.copy()
    cv2.circle(piece_board, (500, 300), 38, (40, 40, 200), -1)  # vivid red presence disc, column 3
    cv2.circle(piece_board, (300, 500), 36, (55, 55, 60), -1)  # dark blight, column 2
    image, _ = place(piece_board, BOARD, table(seed=6))
    result = detect.detect_pieces(reference, mask, image, lands=(labels, names))
    found = {(p["type"], p["land"]) for p in result["pieces"]}
    assert ("presence", "3") in found and ("blight", "2") in found, result["pieces"]
    state = detect.board_state(result["pieces"])
    assert state["3"] == {"presence (red)": 1}


# Features measured on Harrison's real pieces (Pixel 6, layouts r6-r9), at the edges of
# each piece's observed range. The rules must keep sorting all of them correctly.
MEASURED = [
    ((21, 43, 202, 8.3, .065, .032, 1.08, .80), "dahan"), ((24, 51, 219, 17.4, .068, .033, 1.22, .84), "dahan"),
    ((21, 38, 219, 7.1, .066, .031, 1.10, .79), "dahan"),
    ((31, 147, 213, 6, .069, .033, 1.1, .77), "presence"), ((140, 123, 221, 16.5, .082, .040, 1.1, .82), "presence"),
    ((100, 79, 116, 19, .065, .031, 1.1, .79), "blight"), ((103, 91, 129, 22, .068, .033, 1.1, .83), "blight"),
    ((19, 69, 153, 29, .093, .047, 1.1, .81), "energy"), ((21, 78, 170, 32, .095, .048, 1.1, .82), "energy"),
    ((105, 51, 239, 30, .070, .0265, 1.79, .70), "explorer"), ((70, 27, 212, 20, .065, .025, 1.70, .73), "explorer"),
    ((100, 39, 235, 26, .080, .036, 1.03, .68), "city"), ((107, 58, 245, 28, .083, .040, 1.11, .73), "city"),
    ((101, 38, 220, 22, .086, .035, 1.76, .39), "town"),
    ((21, 105, 142, 25.5, .096, .047, 1.2, .80), "energy"),  # warm sunlight, after the camera moved
    ((23, 48, 176, 25.2, .072, .034, 1.1, .82), "dahan"),  # dim, textured dahan: must not be energy
    ((17, 105, 91, 14, .045, .020, 1.5, .60), "table"),  # dark table wood at the moved board's rim
]


@pytest.mark.parametrize("values,truth", MEASURED)
def test_rules_sort_measured_pieces(values, truth):
    from spirit_island.perception.pieces import PieceFeatures, classify

    assert classify(PieceFeatures(*values))["type"] == truth


def test_board_view_page(scene, tmp_path):
    from spirit_island.board_view import BoardView

    reference, _, _ = scene
    ref_dir = tmp_path / "ref"
    ref_dir.mkdir()
    cv2.imwrite(str(ref_dir / "reference.jpg"), reference)
    cv2.imwrite(str(ref_dir / "board_mask.png"), find_board(reference).mask)
    image, _ = place(add_token(flat_board()), BOARD, table(seed=5))
    view = BoardView(ref_dir, lambda: image)
    state = view.update_once()
    assert state["status"] == "ok" and len(state["pieces"]) == 1
    page = view.page()
    assert "Land ?" not in page and "1 piece(s)" in page and view.jpeg[:2] == b"\xff\xd8"


def test_board_view_holds_state_through_a_hand_and_a_one_off_reading(scene, tmp_path):
    from spirit_island.board_view import BoardView

    reference, _, _ = scene
    ref_dir = tmp_path / "ref"
    ref_dir.mkdir()
    cv2.imwrite(str(ref_dir / "reference.jpg"), reference)
    cv2.imwrite(str(ref_dir / "board_mask.png"), find_board(reference).mask)
    view = BoardView(ref_dir, lambda: None, save_dir=tmp_path / "kept")
    one = {"registered": True, "large_changes": [], "board_state": {"?": {"dahan": 1}}}
    two = {"registered": True, "large_changes": [], "board_state": {"?": {"dahan": 2}}}
    hand = {"registered": True, "large_changes": [{}], "board_state": {}}
    lost = {"registered": False, "large_changes": [], "board_state": {}}
    assert view.settle(one) == (one["board_state"], "settled")
    assert view.settle(hand)[0] == one["board_state"]
    assert view.settle(lost)[0] == one["board_state"]
    for _ in range(2):
        view.settle(one)
    flicker = [view.settle(r)[0] for r in (two, one, two, one)]
    assert all(f == one["board_state"] for f in flicker)  # an alternating reading doesn't win
    for _ in range(3):
        shown = view.settle(two)[0]
    assert shown == two["board_state"]  # a real change wins once it holds
