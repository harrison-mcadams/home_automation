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


class BoardPointer(LandLookup):
    """Keeps the camera lined up with a board, in the background.

    Prefers the clean printed scan of the board (assets/boards/<letter>.png, its lands
    found from board_seeds.json), which has no old lighting baked in; falls back to the
    old camera reference folder."""

    @classmethod
    def from_scan(cls, scan_path, letter, seeds):
        from spirit_island.perception.lands import segment_lands
        scan = cv2.imread(str(scan_path), cv2.IMREAD_UNCHANGED)
        if scan is None:
            raise FileNotFoundError(scan_path)
        bgr = scan[..., :3]
        mask = (scan[..., 3] > 128).astype(np.uint8) * 255 if scan.shape[2] == 4 else \
            np.full(scan.shape[:2], 255, np.uint8)
        labels, names = segment_lands(bgr, mask, {k: tuple(v) for k, v in seeds.items()})
        self = cls.__new__(cls)
        LandLookup.__init__(self, labels, names, letter, 0)
        self.reference, self.mask = bgr, mask
        self._init_thread()
        return self

    def _init_thread(self):
        self.status = "not lined up yet"
        self._frame = None
        self._stop = threading.Event()

    def __init__(self, ref_dir, letter_hint=None):
        ref_dir = Path(ref_dir)
        if not (ref_dir / "reference.jpg").exists():
            folders = [d for d in sorted(ref_dir.iterdir()) if (d / "reference.jpg").exists()]
            pick = [d for d in folders if d.name == letter_hint] or folders
            if not pick:
                raise FileNotFoundError(f"no board reference in {ref_dir}")
            ref_dir = pick[0]
        from spirit_island.perception.lands import load
        labels, names = load(ref_dir)
        if labels is None:
            raise FileNotFoundError(f"no land map in {ref_dir}")
        meta = json.loads((ref_dir / "reference.json").read_text()) if (ref_dir / "reference.json").exists() else {}
        super().__init__(labels, names, meta.get("letter") or ref_dir.name, meta.get("rotate", 0))
        self.reference = cv2.imread(str(ref_dir / "reference.jpg"))
        self.mask = cv2.imread(str(ref_dir / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
        self._init_thread()

    def give_frame(self, frame):
        self._frame = frame

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self):
        from vision.register import register
        while not self._stop.is_set():
            frame = self._frame
            if frame is not None:
                h, w = frame.shape[:2]
                img = frame
                if self.rotate in (90, 180, 270):
                    img = cv2.rotate(frame, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                                             270: cv2.ROTATE_90_COUNTERCLOCKWISE}[self.rotate])
                try:
                    reg = register(self.reference, img, reference_mask=self.mask)
                except Exception as e:  # never stop the gesture camera over this
                    reg, self.status = None, f"error: {e}"
                if reg is not None and reg.ok and plausible(reg.homography, self.reference.shape, img.shape[1::-1]):
                    self.homography, self.frame_size = reg.homography, (w, h)
                    self.located_at, self.status = time.time(), "lined up"
                elif time.time() - self.located_at > 30:
                    self.status = "can't find the board"
            self._stop.wait(LOCATE_EVERY_S)
