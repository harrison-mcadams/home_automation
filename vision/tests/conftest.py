"""Synthetic camera fixtures: a fake table scene with ArUco markers of known size."""

import cv2
import numpy as np
import pytest

from vision.markers import marker_bits

MARKER_PX = 84  # side of each marker's black square in the synthetic image (multiple of 6 cells)
MARKER_MM = 42  # so the true scale is 2.0 px/mm


def make_scene(width=1280, height=720, seed=0, marker_px=MARKER_PX, shift=0):
    rng = np.random.default_rng(seed)
    noise = rng.integers(60, 200, size=(height // 8, width // 8, 3), dtype=np.uint8)
    scene = cv2.resize(noise, (width, height), interpolation=cv2.INTER_NEAREST)
    pad = marker_px // 3
    spots = [(60, 60), (width - 60 - marker_px, 60), (60, height - 60 - marker_px),
             (width - 60 - marker_px, height - 60 - marker_px)]
    for marker_id, (x, y) in enumerate(spots):
        x += shift
        cv2.rectangle(scene, (x - pad, y - pad), (x + marker_px + pad, y + marker_px + pad), (255, 255, 255), -1)
        bits = cv2.resize(marker_bits(marker_id), (marker_px, marker_px), interpolation=cv2.INTER_NEAREST)
        scene[y : y + marker_px, x : x + marker_px] = cv2.cvtColor(bits, cv2.COLOR_GRAY2BGR)
    return scene


@pytest.fixture
def scene():
    return make_scene()


@pytest.fixture
def video_file(tmp_path):
    """A 3-second, 20 fps synthetic recording with slight motion."""
    path = tmp_path / "table.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 20, (1280, 720))
    assert writer.isOpened()
    for i in range(60):
        writer.write(make_scene(shift=i % 3))
    writer.release()
    return path
