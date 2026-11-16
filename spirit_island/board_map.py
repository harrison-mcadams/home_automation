"""A drawable map of the physical board, made from the camera's reference folder.

The board page (board_view.py) lines each photo up with a reference photo whose lands
were outlined once (lands.png + lands.json, see perception/lands.py). This module turns
those outlines into simple polygons, straightened to a top-down view using the board's
four corners from reference.json, so the dashboard can draw a clean, animated board and
put each detected piece where it really sits.

Piece positions from the board page are in reference-photo pixels (`reference_bbox`),
so the same straightening applies to them.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

MAP_WIDTH = 1000  # the straightened board is drawn this many units wide


def _small(image, side=1600):
    k = side / max(image.shape[:2])
    return cv2.resize(image, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), k


def match_board(reference: np.ndarray, board_mask: np.ndarray | None, boards_dir: Path, ratio: float = 3):
    """Which clean board scan the camera's reference photo shows, and how it lines up.

    Matches the printed art (SIFT features) against each scan in `boards_dir`
    (A.png, B.png, ...). Returns (letter, homography reference->scan pixels, scan image,
    scores) for a clear winner, else None. The homography takes care of the board's
    rotation and the camera's tilt, so the scan comes out the right way round.
    """
    scans = sorted(Path(boards_dir).glob("*.png")) if boards_dir else []
    if not scans:
        return None
    sift = cv2.SIFT_create(4000)
    ref, kr = _small(reference)
    m = None if board_mask is None else cv2.resize(board_mask, (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_NEAREST)
    k1, d1 = sift.detectAndCompute(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), m)
    if d1 is None:
        return None
    results = []
    for path in scans:
        scan = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if scan is None:
            continue
        small, kb = _small(scan[..., :3])
        am = None
        if scan.shape[2] == 4:
            am = (cv2.resize(scan[..., 3], (small.shape[1], small.shape[0])) > 128).astype(np.uint8) * 255
        k2, d2 = sift.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), am)
        if d2 is None:
            continue
        good = [a for a, b in cv2.BFMatcher().knnMatch(d1, d2, k=2) if a.distance < 0.75 * b.distance]
        if len(good) < 8:
            results.append((0, path.stem, None, scan))
            continue
        H, inl = cv2.findHomography(np.float32([k1[g.queryIdx].pt for g in good]),
                                    np.float32([k2[g.trainIdx].pt for g in good]), cv2.RANSAC, 5)
        n = int(inl.sum()) if inl is not None else 0
        if H is not None:  # back to full-size pixels on both sides
            H = np.diag([1 / kb, 1 / kb, 1]) @ H @ np.diag([kr, kr, 1])
        results.append((n, path.stem, H, scan))
    results.sort(key=lambda r: -r[0])
    scores = {r[1]: r[0] for r in results}
    best = results[0] if results else None
    runner_up = results[1][0] if len(results) > 1 else 0
    if best is None or best[2] is None or best[0] < 30 or best[0] < ratio * max(1, runner_up):
        return None
    return best[1], best[2], best[3], scores


class BoardMap:
    def __init__(self, ref_dir: str | Path, boards_dir: str | Path | None = None):
        ref_dir = Path(ref_dir)
        meta = json.loads((ref_dir / "lands.json").read_text())
        self.names = meta["names"]
        labels = cv2.imread(str(ref_dir / "lands.png"), cv2.IMREAD_GRAYSCALE)
        if labels is None:
            raise FileNotFoundError(ref_dir / "lands.png")
        quad = None
        ref_json = ref_dir / "reference.json"
        if ref_json.exists():
            quad = (json.loads(ref_json.read_text()).get("board") or {}).get("quad")
        self.ref_dir = ref_dir
        self._art = None
        self.letter, self.scan, self.scores = None, None, {}
        found = None
        if boards_dir:
            reference = cv2.imread(str(ref_dir / "reference.jpg"))
            mask = cv2.imread(str(ref_dir / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
            if reference is not None:
                found = match_board(reference, mask, Path(boards_dir))
        if found:
            # A clean scan of this very board: draw on that, true to shape.
            self.letter, H, self.scan, self.scores = found
            k = MAP_WIDTH / self.scan.shape[1]
            self.warp = np.diag([k, k, 1]) @ H
            self.width, self.height = MAP_WIDTH, int(round(self.scan.shape[0] * k))
        else:
            self.warp, self.width, self.height = self._straighten(quad, labels)
            self._fit(labels > 0)
        self.lands = self._outlines(labels)

    def _straighten(self, quad, labels):
        if quad and len(quad) == 4:
            q = np.array(quad, dtype=np.float32)
            top = np.linalg.norm(q[1] - q[0]); bottom = np.linalg.norm(q[2] - q[3])
            left = np.linalg.norm(q[3] - q[0]); right = np.linalg.norm(q[2] - q[1])
            aspect = (left + right) / max(1.0, top + bottom)
        else:  # no corners saved: just crop to the outlined area
            ys, xs = np.nonzero(labels)
            x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
            q = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)
            aspect = (y1 - y0) / max(1, x1 - x0)
        w, h = MAP_WIDTH, int(round(MAP_WIDTH * aspect))
        dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        return cv2.getPerspectiveTransform(q, dst), w, h

    def _fit(self, board):
        """Grow the straightened view so the whole board fits, not just the four corners."""
        contours, _ = cv2.findContours(board.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return
        pts = self.to_map(np.vstack([c.reshape(-1, 2) for c in contours]))
        (x0, y0), (x1, y1) = pts.min(0), pts.max(0)
        k = MAP_WIDTH / max(1.0, x1 - x0)
        fit = np.array([[k, 0, -x0 * k], [0, k, -y0 * k], [0, 0, 1]], dtype=np.float64)
        self.warp = fit @ self.warp
        self.width, self.height = MAP_WIDTH, int(round((y1 - y0) * k))

    def art_png(self) -> bytes | None:
        """The reference photo of the board, straightened, with everything off the board
        made transparent: the board's own printed art, from your own copy."""
        if self._art is None and self.scan is not None:
            scan = self.scan if self.scan.shape[2] == 4 else cv2.cvtColor(self.scan, cv2.COLOR_BGR2BGRA)
            scan = cv2.resize(scan, (2 * self.width, 2 * self.height), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".png", scan)
            self._art = buf.tobytes() if ok else b""
        if self._art is None:
            ref = cv2.imread(str(self.ref_dir / "reference.jpg"))
            mask = cv2.imread(str(self.ref_dir / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
            if ref is None:
                return None
            if mask is None:
                mask = np.full(ref.shape[:2], 255, np.uint8)
            mask = cv2.resize(mask, (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_NEAREST)
            size = (self.width, self.height)
            img = cv2.warpPerspective(ref, self.warp, size, flags=cv2.INTER_AREA)
            alpha = cv2.warpPerspective(mask, self.warp, size)
            alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
            ok, buf = cv2.imencode(".png", np.dstack([img, alpha]))
            self._art = buf.tobytes() if ok else b""
        return self._art or None

    def to_map(self, points) -> np.ndarray:
        pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.warp).reshape(-1, 2)

    def _outlines(self, labels):
        lands = []
        for i, name in enumerate(self.names, 1):
            mask = (labels == i).astype(np.uint8)
            if not mask.any():
                continue
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            c = max(contours, key=cv2.contourArea)
            c = cv2.approxPolyDP(c, 0.004 * cv2.arcLength(c, True), True)
            pts = self.to_map(c.reshape(-1, 2))
            m = cv2.moments(mask, binaryImage=True)
            centre = self.to_map([[m["m10"] / m["m00"], m["m01"] / m["m00"]]])[0]
            lands.append({"name": name, "points": [[round(float(x), 1), round(float(y), 1)] for x, y in pts],
                          "centre": [round(float(centre[0]), 1), round(float(centre[1]), 1)]})
        return lands

    def public(self) -> dict:
        return {"width": self.width, "height": self.height, "lands": self.lands,
                "has_art": self.scan is not None or (self.ref_dir / "reference.jpg").exists(),
                "board": self.letter, "match_scores": self.scores}

    def place(self, pieces: list) -> list:
        """Detected pieces -> [{type, colour, land, x, y}] in map units."""
        out = []
        for p in pieces or []:
            box = p.get("reference_bbox")
            if not box or p.get("type") in (None, "unknown"):
                continue
            x, y = self.to_map([[box[0] + box[2] / 2, box[1] + box[3] / 2]])[0]
            out.append({"type": p["type"], "colour": p.get("colour"), "land": p.get("land"),
                        "x": round(float(x), 1), "y": round(float(y), 1)})
        return out
