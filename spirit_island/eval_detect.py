"""Score piece detection against photos of a board whose contents are known.

    python -m spirit_island.eval_detect <truth folder> [--boards <boards folder>]

A truth folder holds photos (*.jpg) and truth.json: {"board": "C", "lands": {"3": {"dahan": 2, ...}}}.
Prints, per photo, the lands read wrong, and the share of lands and photos read right.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from . import detect
from .perception import lands as land_map
from .vision_link import to_game_counts

BOARDS = Path(r"C:/Users/harri/Desktop/home_automation_capture/spirit_island/recordings/detect_dev/boards")
PIECES = ("explorers", "towns", "cities", "dahan", "blight", "presence")


def score(folder: Path, boards: Path = BOARDS, verbose: bool = True, reader=None) -> dict:
    truth = json.loads((folder / "truth.json").read_text())
    b = truth["board"]
    ref = cv2.imread(str(boards / b / "reference.jpg"))
    mask = cv2.imread(str(boards / b / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
    lands = land_map.load(boards / b)
    want = {f"{b}{n}": {p: truth["lands"].get(str(n), {}).get(p, 0) for p in PIECES} for n in range(1, 9)}
    lands_ok = lands_all = photos_ok = photos = 0
    for f in sorted(folder.glob("*.jpg")):
        image = cv2.imread(str(f))
        if reader is not None:
            got = reader(image, b)
        else:
            r = detect.detect_pieces(ref, mask, image, lands=lands)
            got = to_game_counts(detect.board_state(r["pieces"]), b) if r["registered"] else None
        photos += 1
        if got is None:
            if verbose:
                print(f.name, "could not line up")
            lands_all += 8
            continue
        wrong = {l: {p: (got[l][p], want[l][p]) for p in PIECES if got[l][p] != want[l][p]} for l in want if got[l] != want[l]}
        lands_all += 8
        lands_ok += 8 - len(wrong)
        photos_ok += not wrong
        if verbose and wrong:
            print(f.name, {l: {p: f"saw {a}, is {t}" for p, (a, t) in w.items()} for l, w in wrong.items()})
    out = {"photos": photos, "photos_right": photos_ok, "lands_right": round(lands_ok / max(1, lands_all), 3)}
    if verbose:
        print(out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--boards", default=str(BOARDS))
    a = ap.parse_args()
    score(Path(a.folder), Path(a.boards))
