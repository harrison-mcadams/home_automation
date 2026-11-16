"""Find the island board and the pieces on it.

Three steps, each writing an annotated picture you can look at:

    # 1. Where is the board? Works on any photo, no setup needed.
    python -m spirit_island.detect outline --phone

    # 2. Take a reference photo of the board with nothing on it.
    python -m spirit_island.detect reference --phone

    # 3. Find pieces: compare a new photo with the reference.
    python -m spirit_island.detect find --phone

`--phone` takes a full-resolution photo from the phone camera (same settings as
the capture kit); use `--image path.jpg` to work on a saved photo instead.

Pieces are found as "what differs from the empty board", after lining the new
photo up with the reference, so the board and camera may move a little between
photos. Telling *which* piece each blob is comes later.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from spirit_island.perception.board import BoardOutline, find_board
from vision.changes import find_changes
from vision.register import register, valid_mask, warp_to_reference

ROOT = Path(__file__).resolve().parent / "recordings" / "detect"
DEFAULT_REFERENCE = ROOT / "reference"


def grab_image(args) -> np.ndarray:
    if args.image:
        image = cv2.imread(args.image)
        if image is None:
            raise SystemExit(f"Could not read {args.image}")
        return image
    from vision import phone
    from vision.capture import fetch_still

    url = phone.urls(phone.connect(args.phone, args.phone_host))["photo"]
    return fetch_still(url, timeout=20)


def rotate(image: np.ndarray, degrees: int) -> np.ndarray:
    codes = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    return cv2.rotate(image, codes[degrees]) if degrees in codes else image


def _thickness(image) -> int:
    return max(2, int(max(image.shape[:2]) / 600))


def draw_outline(image: np.ndarray, board: Optional[BoardOutline]) -> np.ndarray:
    out = image.copy()
    t = _thickness(out)
    if board is None:
        cv2.putText(out, "no board found", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, t, (0, 0, 255), t * 2)
        return out
    cv2.drawContours(out, [board.contour], -1, (0, 255, 255), t)
    cv2.polylines(out, [board.quad.astype(np.int32)], True, (255, 0, 255), t)
    for name, (x, y) in zip(["TL", "TR", "BR", "BL"], board.quad):
        cv2.circle(out, (int(x), int(y)), t * 4, (255, 0, 255), -1)
        cv2.putText(out, name, (int(x) + 10, int(y) - 10), cv2.FONT_HERSHEY_SIMPLEX, t * 0.6, (255, 0, 255), t)
    return out


def save(out_dir: Path, name: str, image: np.ndarray, max_side: int = 2000) -> Path:
    """Save a viewable copy (downscaled so it opens quickly)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    scale = min(1.0, max_side / max(image.shape[:2]))
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    path = out_dir / name
    cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return path


def board_summary(board: Optional[BoardOutline]) -> dict:
    if board is None:
        return {"found": False}
    return {
        "found": True,
        "bbox": board.bbox,
        "area_frac": board.area_frac,
        "quad": [[round(float(x)), round(float(y))] for x, y in board.quad],
    }


# -- commands --------------------------------------------------------------


def cmd_outline(args) -> int:
    image = rotate(grab_image(args), args.rotate)
    board = find_board(image)
    out = Path(args.out or ROOT / datetime.now().strftime("outline-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "input.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    path = save(out, "outline.jpg", draw_outline(image, board))
    summary = board_summary(board)
    (out / "outline.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    print(f"Annotated picture: {path}")
    return 0 if board else 1


def cmd_reference(args) -> int:
    image = rotate(grab_image(args), args.rotate)
    board = find_board(image)
    if board is None:
        print("No board found in this picture; reference not saved.")
        return 1
    ref_dir = Path(args.reference)
    ref_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ref_dir / "reference.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    # Grow the mask slightly so pieces sitting on the coastline still count as on the board.
    grow = max(3, int(0.01 * max(image.shape[:2])))
    mask = cv2.dilate(board.mask, np.ones((grow, grow), np.uint8))
    cv2.imwrite(str(ref_dir / "board_mask.png"), mask)
    meta = {"saved": datetime.now().isoformat(timespec="seconds"), "rotate": args.rotate, "board": board_summary(board)}
    (ref_dir / "reference.json").write_text(json.dumps(meta, indent=2))
    path = save(ref_dir, "reference_outline.jpg", draw_outline(image, board))
    print(f"Saved reference to {ref_dir} (board covers {board.area_frac:.0%} of the frame).")
    print(f"Check the outline: {path}")
    return 0


def detect_pieces(reference: np.ndarray, board_mask: np.ndarray, image: np.ndarray, **kwargs) -> dict:
    """Register `image` onto the reference and find what changed on the board."""
    reg = register(reference, image, reference_mask=board_mask)
    if reg is None or not reg.ok:
        return {"registered": False, "inliers": reg.inliers if reg else 0, "pieces": []}
    aligned = warp_to_reference(image, reg, reference.shape)
    covered = valid_mask(image.shape, reg, reference.shape)
    region = cv2.bitwise_and(board_mask, covered)
    blobs, change_mask = find_changes(reference, aligned, region, **kwargs)
    H_inv = np.linalg.inv(reg.homography)
    pieces = []
    for b in blobs:
        x, y, w, h = b.bbox
        corners = np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]]).reshape(-1, 1, 2)
        img_corners = cv2.perspectiveTransform(corners, H_inv).reshape(-1, 2)
        cx, cy = cv2.perspectiveTransform(np.float32([[b.centroid]]), H_inv).reshape(2)
        pieces.append({
            "centroid": [round(float(cx)), round(float(cy))],
            "outline": [[round(float(px)), round(float(py))] for px, py in img_corners],
            "reference_bbox": list(b.bbox),
            "area_px": b.area,
            "mean_bgr": list(b.mean_bgr),
            "change_score": b.score,
        })
    return {
        "registered": True,
        "inliers": reg.inliers,
        "matches": reg.matches,
        "pieces": pieces,
        "_aligned": aligned,
        "_change_mask": change_mask,
    }


def draw_pieces(image: np.ndarray, result: dict) -> np.ndarray:
    out = image.copy()
    t = _thickness(out)
    for i, p in enumerate(result["pieces"], 1):
        cv2.polylines(out, [np.int32(p["outline"])], True, (0, 0, 255), t)
        x, y = p["centroid"]
        cv2.putText(out, str(i), (x + 15, y - 15), cv2.FONT_HERSHEY_SIMPLEX, t * 0.8, (0, 0, 255), t * 2)
    label = f"{len(result['pieces'])} piece(s)" if result["registered"] else "could not line up with reference"
    cv2.putText(out, label, (30, 60 * t // 2 + 30), cv2.FONT_HERSHEY_SIMPLEX, t * 0.8, (0, 0, 0), t * 3)
    cv2.putText(out, label, (30, 60 * t // 2 + 30), cv2.FONT_HERSHEY_SIMPLEX, t * 0.8, (255, 255, 255), t)
    return out


def cmd_find(args) -> int:
    ref_dir = Path(args.reference)
    reference = cv2.imread(str(ref_dir / "reference.jpg"))
    board_mask = cv2.imread(str(ref_dir / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
    if reference is None or board_mask is None:
        print(f"No reference in {ref_dir}. Take one first: python -m spirit_island.detect reference --phone")
        return 1
    rot = json.loads((ref_dir / "reference.json").read_text()).get("rotate", 0) if args.rotate is None else args.rotate
    image = rotate(grab_image(args), rot)
    result = detect_pieces(reference, board_mask, image)

    out = Path(args.out or ROOT / datetime.now().strftime("find-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "input.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    path = save(out, "pieces.jpg", draw_pieces(image, result))
    if result["registered"]:
        save(out, "aligned.jpg", result["_aligned"])
        save(out, "changes.jpg", result["_change_mask"])
    public = {k: v for k, v in result.items() if not k.startswith("_")}
    (out / "pieces.json").write_text(json.dumps(public, indent=2))

    if not result["registered"]:
        print(f"Could not line the photo up with the reference ({result['inliers']} matching points).")
    else:
        print(f"Lined up with the reference ({result['inliers']} of {result['matches']} matches). "
              f"Found {len(result['pieces'])} piece(s):")
        for i, p in enumerate(result["pieces"], 1):
            print(f"  {i}: at {p['centroid']}, {p['area_px']} px, colour BGR {p['mean_bgr']}, "
                  f"change {p['change_score']}")
    print(f"Annotated picture: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn, help_text in [
        ("outline", cmd_outline, "outline the board in one photo"),
        ("reference", cmd_reference, "save a photo of the empty board as the reference"),
        ("find", cmd_find, "find pieces by comparing with the reference"),
    ]:
        s = sub.add_parser(name, help=help_text)
        s.set_defaults(func=fn)
        src = s.add_mutually_exclusive_group(required=True)
        src.add_argument("--image", help="a saved photo")
        src.add_argument("--phone", nargs="?", const=8080, type=int, metavar="PORT",
                         help="take a full-resolution photo from the phone camera")
        s.add_argument("--phone-host", help="phone's Wi-Fi address (default IPWEBCAM_HOST)")
        s.add_argument("--rotate", type=int, choices=[0, 90, 180, 270],
                       default=None if name == "find" else 0)
        s.add_argument("--reference", default=str(DEFAULT_REFERENCE), help="reference folder")
        s.add_argument("--out", help="output folder")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
