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


class BoardMap:
    def __init__(self, ref_dir: str | Path):
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
        self.warp, self.width, self.height = self._straighten(quad, labels)
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
        return {"width": self.width, "height": self.height, "lands": self.lands}

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
