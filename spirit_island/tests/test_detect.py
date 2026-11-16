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
