"""Which land a fingertip is over, from the gesture camera's own picture.

The island board is found by its printed art: each frame from time to time is lined up
with the board's reference photo (the same reference folder the old board camera used:
reference.jpg, board_mask.png, lands.png + lands.json). A fingertip in the camera picture
then maps through that alignment onto the reference, where every pixel is labelled with
its land. Nothing is calibrated to a position: if the board or the camera moves, the next
alignment picks it up (Harrison's rule: everything gets bumped).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np

LOCATE_EVERY_S = 3.0   # line the board up again this often


def rotate_point(x, y, w, h, degrees):
    """Where pixel (x, y) of a w x h picture lands after rotating the picture."""
    if degrees == 90:
        return h - 1 - y, x
    if degrees == 180:
        return w - 1 - x, h - 1 - y
    if degrees == 270:
        return y, w - 1 - x
    return x, y


class LandLookup:
    """Reference-pixel land labels plus the latest camera -> reference alignment."""

    def __init__(self, labels, names, letter, rotate=0):
        self.labels, self.names, self.letter, self.rotate = labels, names, letter, rotate
        self.homography = None      # camera (rotated) pixels -> reference pixels
        self.frame_size = None      # (w, h) of the camera picture, before rotating
        self.located_at = 0.0

    def land_at(self, pt):
        """Land id (e.g. "C4") under a camera-picture point, or None."""
        if self.homography is None or self.frame_size is None:
            return None
        from spirit_island.perception.lands import land_at
        w, h = self.frame_size
        x, y = rotate_point(pt[0], pt[1], w, h, self.rotate)
        ref = cv2.perspectiveTransform(np.float32([[[x, y]]]), self.homography)[0, 0]
        name = land_at(self.labels, self.names, float(ref[0]), float(ref[1]), search=0)
        if name is None or not str(name).isdigit():
            return None   # off the board, or the ocean
        return f"{self.letter}{name}"


def plausible(H_cam_to_ref, ref_shape, frame_size):
    """An alignment is believable when the board's outline, carried back into the camera
    picture, is a convex shape of sensible size (a bad match can have many 'inliers')."""
    h, w = ref_shape[:2]
    try:
        inv = np.linalg.inv(H_cam_to_ref)
    except np.linalg.LinAlgError:
        return False
    corners = cv2.perspectiveTransform(np.float32([[[0, 0], [w, 0], [w, h], [0, h]]]), inv)[0]
    if not cv2.isContourConvex(corners.astype(np.float32)):
        return False
    area = cv2.contourArea(corners)
    fw, fh = frame_size
    return 0.05 * fw * fh <= area <= 1.5 * fw * fh


def scan_source(scan_path, seeds):
    """A board's clean printed scan (assets/boards/<letter>.png), its lands found from seeds."""
    from spirit_island.perception.lands import segment_lands
    scan = cv2.imread(str(scan_path), cv2.IMREAD_UNCHANGED)
    if scan is None:
        raise FileNotFoundError(scan_path)
    bgr = scan[..., :3]
    mask = (scan[..., 3] > 128).astype(np.uint8) * 255 if scan.shape[2] == 4 else \
        np.full(scan.shape[:2], 255, np.uint8)
    labels, names = segment_lands(bgr, mask, {k: tuple(v) for k, v in seeds.items()})
    return {"name": f"scan {Path(scan_path).stem}", "reference": bgr, "mask": mask,
            "labels": labels, "names": names, "rotate": 0}


def reference_sources(ref_dir):
    """Every board reference folder the old board camera saved (reference.jpg, board_mask.png,
    lands.png + lands.json), under `ref_dir` or `ref_dir` itself."""
    from spirit_island.perception.lands import load
    ref_dir = Path(ref_dir)
    folders = [ref_dir] if (ref_dir / "reference.jpg").exists() else \
        [d for d in sorted(ref_dir.iterdir()) if (d / "reference.jpg").exists()]
    out = []
    for d in folders:
        labels, names = load(d)
        ref = cv2.imread(str(d / "reference.jpg"))
        if labels is None or ref is None:
            continue
        meta = json.loads((d / "reference.json").read_text()) if (d / "reference.json").exists() else {}
        out.append({"name": f"reference {d.name}", "reference": ref,
                    "mask": cv2.imread(str(d / "board_mask.png"), cv2.IMREAD_GRAYSCALE),
                    "labels": labels, "names": names, "rotate": meta.get("rotate", 0)})
    return out


class BoardPointer(LandLookup):
    """Keeps the camera lined up with the board, in the background.

    Tries each known picture of the board (the clean scans and the old camera's reference
    photos; their folder letters aren't trusted, since on 2026-11-18 Harrison's board C
    matched the folder named A) and keeps whichever lines up with a believable outline.
    Land ids always use the game's own board letter."""

    def __init__(self, sources, letter):
        if not sources:
            raise FileNotFoundError("no pictures of the board to line up with")
        self.sources = sources
        self.active = 0
        s0 = sources[0]
        super().__init__(s0["labels"], s0["names"], letter, s0["rotate"])
        self.status = "not lined up yet"
        self.source_name = None
        self._frame = None
        self._stop = threading.Event()

    def give_frame(self, frame):
        self._frame = frame

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _try(self, src, frame):
        from vision.register import register
        img = frame
        if src["rotate"] in (90, 180, 270):
            img = cv2.rotate(frame, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                                     270: cv2.ROTATE_90_COUNTERCLOCKWISE}[src["rotate"]])
        try:
            reg = register(src["reference"], img, reference_mask=src["mask"])
        except Exception:
            return None
        if reg is not None and reg.ok and plausible(reg.homography, src["reference"].shape, img.shape[1::-1]):
            return reg.homography
        return None

    def locate_once(self, frame):
        """Line up one frame: the board that worked last time first, then the others."""
        order = [self.active] + [i for i in range(len(self.sources)) if i != self.active]
        for i in order:
            H = self._try(self.sources[i], frame)
            if H is not None:
                src = self.sources[i]
                self.active, self.source_name = i, src["name"]
                self.labels, self.names, self.rotate = src["labels"], src["names"], src["rotate"]
                self.homography, self.frame_size = H, (frame.shape[1], frame.shape[0])
                self.located_at, self.status = time.time(), "lined up"
                return True
        if time.time() - self.located_at > 30:
            self.status = "can't find the board"
        return False

    def _run(self):
        while not self._stop.is_set():
            if self._frame is not None:
                self.locate_once(self._frame)
            self._stop.wait(LOCATE_EVERY_S)
