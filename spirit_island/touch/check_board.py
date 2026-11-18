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

from .board_point import BoardPointer, plausible

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--letter", default="C")
    ap.add_argument("--out", default="board_check.jpg")
    a = ap.parse_args(argv)
    if os.path.exists(a.camera):
        frame = cv2.imread(a.camera)
    else:
        cap = cv2.VideoCapture(a.camera)
        ok, frame = cap.read()
        if not ok:
            raise SystemExit("no frame from the camera")
    seeds = json.load(open(os.path.join(BASE, "board_seeds.json"), encoding="utf-8"))["boards"][a.letter]
    bp = BoardPointer.from_scan(os.path.join(BASE, "assets", "boards", f"{a.letter}.png"), a.letter, seeds)
    from vision.register import register
    reg = register(bp.reference, frame, reference_mask=bp.mask)
    if reg is None:
        raise SystemExit("no alignment at all")
    ok = reg.ok and plausible(reg.homography, bp.reference.shape, frame.shape[1::-1])
    print(f"inliers {reg.inliers} of {reg.matches} matches; plausible: {ok}")
    inv = np.linalg.inv(reg.homography)
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
