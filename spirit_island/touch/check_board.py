"""Check that the gesture camera can find the board: grabs one frame (or reads a photo),
lines it up with the board's clean scan, and saves a picture with each land outlined and
named, so you can see by eye whether pointing will land on the right land.

    python -m spirit_island.touch.check_board --camera <video URL or photo> --out check.jpg
"""

from __future__ import annotations

import argparse
import json
import os

import cv2
import numpy as np

from . import board_point as bp_mod

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--letter", default="C")
    ap.add_argument("--out", default="board_check.jpg")
    ap.add_argument("--reference", help="folder of the old board camera's references (config board_reference)")
    a = ap.parse_args(argv)
    if os.path.exists(a.camera):
        frame = cv2.imread(a.camera)
    else:
        cap = cv2.VideoCapture(a.camera)
        ok, frame = cap.read()
        if not ok:
            raise SystemExit("no frame from the camera")
    sources = []
    scan = os.path.join(BASE, "assets", "boards", f"{a.letter}.png")
    if os.path.exists(scan):
        seeds = json.load(open(os.path.join(BASE, "board_seeds.json"), encoding="utf-8"))["boards"][a.letter]
        sources.append(bp_mod.scan_source(scan, seeds))
    if a.reference:
        sources += bp_mod.reference_sources(a.reference)
    bp = bp_mod.BoardPointer(sources, a.letter)
    if not bp.locate_once(frame):
        raise SystemExit("could not line up with any picture of the board: " + ", ".join(s["name"] for s in sources))
    print("lined up with", bp.source_name)
    inv = np.linalg.inv(bp.homography)
    out = frame.copy()
    for i, name in enumerate(bp.names, 1):
        m = (bp.labels == i).astype(np.uint8)
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cs:
            pts = cv2.perspectiveTransform(c.astype(np.float32), inv).astype(np.int32)
            cv2.polylines(out, [pts], True, (0, 255, 255), 2)
            mx = pts.reshape(-1, 2).mean(0).astype(int)
            cv2.putText(out, str(name), tuple(int(v) for v in mx), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    cv2.imwrite(a.out, out)
    print("saved", a.out)


if __name__ == "__main__":
    main()
