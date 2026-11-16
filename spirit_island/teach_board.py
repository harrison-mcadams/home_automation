"""Teach the board camera a new island board from one photo of it, empty.

    python -m spirit_island.teach_board --phone --phone-host 192.168.1.60 --out <boards folder>

Takes a photo, finds the board in it, works out which board it is by matching the printed
art against the clean scans (assets/boards/A.png ...), and saves a reference folder
<out>/<letter>/ the board page can use. The lands come from the scan too: each land's
outline on the scan (grown from one point per land in board_seeds.json) is carried onto
the photo, so nobody has to click the lands by hand.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from . import detect
from .board_map import match_board
from .perception import lands as land_map
from .perception.board import find_board

HERE = Path(__file__).resolve().parent
SEEDS = HERE / "board_seeds.json"
BOARDS = HERE / "assets" / "boards"


def scan_lands(letter: str, boards_dir: Path = BOARDS):
    """Land label image on the clean scan of a board, and the land names."""
    scan = cv2.imread(str(boards_dir / f"{letter}.png"), cv2.IMREAD_UNCHANGED)
    img = scan[..., :3].copy()
    mask = ((scan[..., 3] > 128) * 255).astype(np.uint8) if scan.shape[2] == 4 else \
        np.full(scan.shape[:2], 255, np.uint8)
    img[mask == 0] = 0
    seeds = json.loads(SEEDS.read_text())["boards"][letter]
    return land_map.segment_lands(img, mask, {k: tuple(v) for k, v in seeds.items()})


def _outline_from_mask(mask: np.ndarray):
    """A BoardOutline for the saved summary and the outline picture."""
    from .perception.board import BoardOutline, _quad_from_contour
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(contours, key=cv2.contourArea)
    return BoardOutline(contour=c, quad=_quad_from_contour(c), mask=mask,
                        area_frac=float((mask > 0).mean()))


def teach(image: np.ndarray, out_root: Path, boards_dir: Path = BOARDS, expect: str | None = None) -> dict:
    board = find_board(image)
    grow = max(3, int(0.01 * max(image.shape[:2])))
    # The table's outline finder can grab the whole frame (wood grain, cards); then just
    # match the art across the whole photo.
    hint = board.mask if board is not None and board.area_frac < 0.5 else None
    found = match_board(image, hint, boards_dir)
    if not found:
        raise SystemExit("Couldn't tell which board this is (glare, or pieces covering it?).")
    letter, H, _scan, scores = found
    if expect and letter != expect:
        raise SystemExit(f"That looks like board {letter}, not {expect} (match scores {scores}).")

    # The board's outline comes from the scan, carried onto the photo: exact, with no
    # holes from glare and nothing from the table around it.
    scan = cv2.imread(str(boards_dir / f"{letter}.png"), cv2.IMREAD_UNCHANGED)
    h, w = image.shape[:2]
    alpha = ((scan[..., 3] > 128) * 255).astype(np.uint8) if scan.shape[2] == 4 else         np.full(scan.shape[:2], 255, np.uint8)
    outline = cv2.warpPerspective(alpha, np.linalg.inv(H), (w, h), flags=cv2.INTER_NEAREST)
    mask = cv2.dilate(outline, np.ones((grow, grow), np.uint8))
    board = _outline_from_mask(outline)

    ref_dir = out_root / letter
    ref_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ref_dir / "reference.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    cv2.imwrite(str(ref_dir / "board_mask.png"), mask)
    meta = {"saved": datetime.now().isoformat(timespec="seconds"), "rotate": 0, "letter": letter,
            "match_scores": scores, "board": detect.board_summary(board)}
    (ref_dir / "reference.json").write_text(json.dumps(meta, indent=2))
    detect.save(ref_dir, "reference_outline.jpg", detect.draw_outline(image, board))

    # Carry the scan's lands onto the photo (H maps photo -> scan).
    labels_scan, names = scan_lands(letter, boards_dir)
    h, w = image.shape[:2]
    labels = cv2.warpPerspective(labels_scan, np.linalg.inv(H), (w, h), flags=cv2.INTER_NEAREST)
    labels[mask == 0] = 0
    seeds_scan = json.loads(SEEDS.read_text())["boards"][letter]
    pts = cv2.perspectiveTransform(np.float32([seeds_scan[n] for n in names]).reshape(-1, 1, 2),
                                   np.linalg.inv(H)).reshape(-1, 2)
    seeds = {n: [round(float(x), 1), round(float(y), 1)] for n, (x, y) in zip(names, pts)}
    land_map.save(ref_dir, labels, names, seeds)
    overlay = detect.save(ref_dir, "lands_overlay.jpg", land_map.draw(image, labels, names))
    return {"letter": letter, "folder": str(ref_dir), "scores": scores, "overlay": str(overlay),
            "land_px": {n: int((labels == i).sum()) for i, n in enumerate(names, 1)}}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="a saved photo of the empty board")
    src.add_argument("--phone", nargs="?", const=8080, type=int, metavar="PORT")
    p.add_argument("--phone-host")
    p.add_argument("--out", required=True, help="folder holding one reference folder per board letter")
    p.add_argument("--expect", help="the board letter you put down, to catch a mix-up")
    args = p.parse_args(argv)
    result = teach(detect.grab_image(args), Path(args.out), expect=args.expect)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
