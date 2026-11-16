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

from spirit_island.perception import lands as land_map
from spirit_island.perception.board import BoardOutline, find_board
from spirit_island.perception.lands import piece_land
from spirit_island.perception.pieces import classify, describe, measure
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
        "touches_frame_edge": board.touches_edge,
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
    if board is not None and board.touches_edge:
        print("Note: the board runs off the edge of the picture; aim so it is fully in view.")
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


def detect_pieces(reference: np.ndarray, board_mask: np.ndarray, image: np.ndarray,
                  max_piece_frac: float = 0.03, min_thickness: float = 0.02, close_frac: float = 0.015,
                  lands: Optional[tuple] = None, **kwargs) -> dict:
    """Register `image` onto the reference and find what changed on the board."""
    reg = register(reference, image, reference_mask=board_mask)
    if reg is None or not reg.ok:
        return {"registered": False, "inliers": reg.inliers if reg else 0, "pieces": [], "large_changes": []}
    aligned = warp_to_reference(image, reg, reference.shape)
    covered = valid_mask(image.shape, reg, reference.shape)
    # Stay clear of the picture's edges, in both photos: where the board runs off the
    # frame, a few pixels of misalignment look like change.
    edge = max(8, int(0.006 * max(reference.shape[:2])))
    covered = cv2.erode(covered, np.ones((2 * edge + 1, 2 * edge + 1), np.uint8))
    covered[:edge, :] = 0
    covered[-edge:, :] = 0
    covered[:, :edge] = 0
    covered[:, -edge:] = 0
    region = cv2.bitwise_and(board_mask, covered)
    # Only the board itself counts, never the table around it: the board slides, so the
    # wood next to it changes. Outline the board in *this* photo too and keep the overlap,
    # pulled in a little from the rim.
    # Only used to cut away clear table, so it is filled and grown generously first:
    # pale grey mountains can drop out of this photo's outline (saturation ~5) and must
    # not take pieces with them.
    current = find_board(image)
    if current is not None:
        now_mask = cv2.warpPerspective(current.mask, reg.homography, (reference.shape[1], reference.shape[0]),
                                       flags=cv2.INTER_NEAREST)
        size = np.sqrt(max(1, int((now_mask > 0).sum())))
        close = int(0.08 * size) | 1
        now_mask = cv2.morphologyEx(now_mask, cv2.MORPH_CLOSE,
                                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close)))
        contours, _ = cv2.findContours(now_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        now_mask = np.zeros_like(now_mask)
        cv2.drawContours(now_mask, contours, -1, 255, thickness=cv2.FILLED)
        grow = int(0.02 * size) | 1
        now_mask = cv2.dilate(now_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow, grow)))
        # Trust it only near the board's rim, where table can creep in when the board
        # slides; the interior of the board always stays in.
        band = int(0.04 * size) | 1
        interior = cv2.erode(region, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * band + 1, 2 * band + 1)))
        region = cv2.bitwise_or(interior, cv2.bitwise_and(region, now_mask))
    rim = max(5, int(0.012 * np.sqrt(max(1, int((region > 0).sum())))))
    region = cv2.erode(region, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rim + 1, 2 * rim + 1)))
    board_area = max(1, int((region > 0).sum()))
    kwargs.setdefault("min_split_thickness", 1.2 * min_thickness * np.sqrt(board_area))
    blobs, change_mask, labels, scale = find_changes(reference, aligned, region, return_labels=True, **kwargs)
    work = cv2.resize(aligned, (labels.shape[1], labels.shape[0]), interpolation=cv2.INTER_AREA)
    full_board_area = float((board_mask > 0).sum()) * scale * scale  # in working pixels
    land_labels, land_names = lands if lands else (None, None)
    H_inv = np.linalg.inv(reg.homography)
    pieces, large = [], []
    for b in blobs:
        x, y, w, h = b.bbox
        corners = np.float32([[x, y], [x + w, y], [x + w, y + h], [x, y + h]]).reshape(-1, 1, 2)
        img_corners = cv2.perspectiveTransform(corners, H_inv).reshape(-1, 2)
        cx, cy = cv2.perspectiveTransform(np.float32([[b.centroid]]), H_inv).reshape(2)
        entry = {
            "centroid": [round(float(cx)), round(float(cy))],
            "outline": [[round(float(px)), round(float(py))] for px, py in img_corners],
            "reference_bbox": list(b.bbox),
            "area_px": b.area,
            "mean_bgr": list(b.mean_bgr),
            "change_score": b.score,
            "thickness_px": b.thickness,
        }
        piece_mask = labels == b.label
        feats = measure(work, piece_mask, full_board_area)
        entry.update(classify(feats))
        entry["features"] = describe(feats)
        if land_labels is not None:
            ys, xs = np.nonzero(piece_mask)
            pts = np.stack([(xs / scale).astype(int).clip(0, land_labels.shape[1] - 1),
                            (ys / scale).astype(int).clip(0, land_labels.shape[0] - 1)], axis=1)
            entry["land"] = piece_land(land_labels, land_names, pts)
        if b.area > max_piece_frac * board_area:
            large.append(entry)  # far bigger than any piece: a hand, a moved object, or the board moved
            continue
        if b.thickness < min_thickness * np.sqrt(board_area):
            # Thin, but maybe a spindly figure (an explorer and its staff, seen from a low
            # angle, are two thin parts with a gap). Close small gaps and notches and measure
            # again: a figure fills out, a line along a printed edge stays a line.
            k = max(3, int(close_frac * np.sqrt(full_board_area))) | 1
            closed = cv2.morphologyEx(piece_mask.astype(np.uint8), cv2.MORPH_CLOSE,
                                      cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
            closed_thickness = cv2.distanceTransform(closed, cv2.DIST_L2, 5).max() / scale
            if closed_thickness < min_thickness * np.sqrt(board_area):
                continue  # a thin line of change along a printed edge, not a piece
            entry["thickness_px"] = round(float(closed_thickness), 1)
        pieces.append(entry)
    # Safety net: a blob much bigger than a typical piece may be several pieces touching.
    if len(pieces) >= 3:
        median_area = float(np.median([p["area_px"] for p in pieces]))
        for p in pieces:
            p["maybe_several"] = bool(p["area_px"] > 2.5 * median_area)
    return {
        "registered": True,
        "inliers": reg.inliers,
        "matches": reg.matches,
        "pieces": pieces,
        "large_changes": large,
        "_aligned": aligned,
        "_change_mask": change_mask,
    }


def board_state(pieces: list) -> dict:
    """Pieces counted by land and type, e.g. {"2": {"city": 1, "town": 1}}."""
    state: dict = {}
    for p in pieces:
        land = p.get("land") or "?"
        kind = p.get("type", "unknown") + (f" ({p['colour']})" if p.get("colour") else "")
        state.setdefault(land, {})
        state[land][kind] = state[land].get(kind, 0) + 1
    return dict(sorted(state.items()))


def cmd_lands(args) -> int:
    ref_dir = Path(args.reference)
    reference = cv2.imread(str(ref_dir / "reference.jpg"))
    board_mask = cv2.imread(str(ref_dir / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
    if reference is None or board_mask is None:
        print(f"No reference in {ref_dir}.")
        return 1
    seeds = {}
    for item in args.seed:
        name, _, xy = item.partition("=")
        x, y = (float(v) for v in xy.split(","))
        seeds[name] = (x, y)
    labels, names = land_map.segment_lands(reference, board_mask, seeds)
    land_map.save(ref_dir, labels, names, seeds)
    path = save(ref_dir, "lands_overlay.jpg", land_map.draw(reference, labels, names))
    for i, name in enumerate(names, 1):
        print(f"  {name}: {int((labels == i).sum())} px")
    print(f"Check the land map: {path}")
    return 0


def draw_pieces(image: np.ndarray, result: dict) -> np.ndarray:
    out = image.copy()
    t = _thickness(out)
    for i, p in enumerate(result["pieces"], 1):
        cv2.polylines(out, [np.int32(p["outline"])], True, (0, 0, 255), t)
        x, y = p["centroid"]
        tag = f"{i} {p.get('type', '')}" + (f" @{p['land']}" if p.get("land") else "")
        cv2.putText(out, tag, (x + 15, y - 15), cv2.FONT_HERSHEY_SIMPLEX, t * 0.7, (0, 0, 0), t * 3)
        cv2.putText(out, tag, (x + 15, y - 15), cv2.FONT_HERSHEY_SIMPLEX, t * 0.7, (255, 255, 255), t)
    for p in result.get("large_changes", []):
        cv2.polylines(out, [np.int32(p["outline"])], True, (0, 165, 255), t)
    label = f"{len(result['pieces'])} piece(s)" if result["registered"] else "could not line up with reference"
    if result.get("large_changes"):
        label += f", {len(result['large_changes'])} large change(s)"
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
    land_labels, land_names = land_map.load(ref_dir)
    lands = (land_labels, land_names) if land_labels is not None else None
    result = detect_pieces(reference, board_mask, image, lands=lands)
    result["board_state"] = board_state(result["pieces"])

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
            note = "  (big: may be several pieces touching)" if p.get("maybe_several") else ""
            what = p.get("type", "?") + (f" ({p['colour']})" if p.get("colour") else "")
            where = f" on land {p['land']}" if p.get("land") else ""
            print(f"  {i}: {what}{where} at {p['centroid']}  [{p.get('why', '')}]{note}")
        if result["board_state"]:
            print("Board state:")
            for land, counts in result["board_state"].items():
                print(f"  land {land}: " + ", ".join(f"{n} {k}" for k, n in counts.items()))
        for p in result["large_changes"]:
            print(f"  (large change, not counted as a piece: at {p['centroid']}, {p['area_px']} px; "
                  "a hand, a moved object, or the board moved)")
    print(f"Annotated picture: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("lands", help="map the lands on the reference from one point inside each land")
    s.set_defaults(func=cmd_lands)
    s.add_argument("--reference", default=str(DEFAULT_REFERENCE))
    s.add_argument("--seed", action="append", required=True, metavar="NAME=X,Y",
                   help="a point inside a land on the reference photo, e.g. --seed 1=2925,1775 --seed ocean=2300,2200")
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
