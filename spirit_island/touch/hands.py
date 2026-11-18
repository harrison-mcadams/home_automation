"""Find hands in a frame with MediaPipe, as lists of 21 (x, y) pixel points.

Uses the MediaPipe Tasks hand landmarker (MediaPipe 0.10.x and later). It needs the
model file `hand_landmarker.task`; `ensure_model()` downloads it once (about 8 MB) to
spirit_island/touch/models/, which git ignores.
"""

from __future__ import annotations

import os
import time
import urllib.request

import cv2
import numpy as np

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
MODEL_PATH = os.path.join(MODEL_DIR, "hand_landmarker.task")


def ensure_model(path=MODEL_PATH):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        urllib.request.urlretrieve(MODEL_URL, tmp)
        os.replace(tmp, path)
    return path


class HandFinder:
    """Video-mode hand landmarker. `find(frame_bgr)` -> list of hands, each 21 (x, y)
    points in the frame's own pixels, plus `handedness` and `score` on the last call.

    Frames are shrunk to `work_width` before detection: hands are big in the frame, and
    a small image keeps each frame to a few milliseconds."""

    def __init__(self, max_hands=2, work_width=480, min_confidence=0.5, model_path=None):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self._mp = mp
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path or ensure_model()),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=min_confidence,
            min_hand_presence_confidence=min_confidence,
            min_tracking_confidence=min_confidence,
        )
        self._det = vision.HandLandmarker.create_from_options(opts)
        self.work_width = work_width
        self._last_ms = 0
        self.scores = []
        self.ms = 0.0  # time the last detection took

    def find(self, frame_bgr, t=None):
        h, w = frame_bgr.shape[:2]
        scale = min(1.0, self.work_width / float(w))
        small = cv2.resize(frame_bgr, (int(w * scale), int(h * scale))) if scale < 1 else frame_bgr
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        ms = int((t if t is not None else time.time()) * 1000)
        ms = max(ms, self._last_ms + 1)  # the landmarker wants rising timestamps
        self._last_ms = ms
        start = time.perf_counter()
        res = self._det.detect_for_video(self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                                                        data=np.ascontiguousarray(rgb)), ms)
        self.ms = (time.perf_counter() - start) * 1000
        hands, self.scores = [], []
        for i, lms in enumerate(res.hand_landmarks):
            hands.append([(p.x * w, p.y * h) for p in lms])
            try:
                self.scores.append(res.handedness[i][0].score)
            except (IndexError, AttributeError):
                self.scores.append(1.0)
        return hands

    def close(self):
        try:
            self._det.close()
        except Exception:
            pass


HAND_LINKS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
              (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18),
              (18, 19), (19, 20), (0, 17)]


def draw_hand(img, lm, colour=(120, 230, 120)):
    for a, b in HAND_LINKS:
        cv2.line(img, tuple(map(int, lm[a])), tuple(map(int, lm[b])), colour, 2, cv2.LINE_AA)
    for i, p in enumerate(lm):
        cv2.circle(img, tuple(map(int, p)), 6 if i == 8 else 3, (255, 255, 255) if i == 8 else colour, -1)
