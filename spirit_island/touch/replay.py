"""Replay a recorded clip through the hand finder and gesture reader, and print what
happened frame by frame (for tuning swipes and taps against real hands).

    python -m spirit_island.touch.replay clip.mp4 [--every 1] [--work-width 480]
    python -m spirit_island.touch.replay --record clip.mp4 --camera URL --seconds 40
"""

from __future__ import annotations

import argparse
import time

import cv2

from .gestures import GestureReader, _d, count_up, palm_centre, palm_size
from .hands import HandFinder


def record(camera, path, seconds):
    from vision.capture import Camera
    with Camera(camera) as cam:
        pkt = cam.wait_for_frame(timeout=10)
        h, w = pkt.image.shape[:2]
        out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
        stamps, last, end = [], -1, time.time() + seconds
        print(f"RECORDING {seconds}s now", flush=True)
        while time.time() < end:
            p = cam.wait_for_frame(after_index=last, timeout=2)
            if p is None:
                continue
            last = p.index
            out.write(p.image)
            stamps.append(p.timestamp)
        out.release()
    with open(path + ".times", "w") as f:
        f.write("\n".join(f"{t:.4f}" for t in stamps))
    print(f"saved {len(stamps)} frames ({len(stamps) / seconds:.1f} fps) to {path}")


def replay(path, every=1, work_width=480):
    cap = cv2.VideoCapture(path)
    try:
        times = [float(x) for x in open(path + ".times").read().split()]
    except OSError:
        times = None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    finder, reader = HandFinder(work_width=work_width), GestureReader()
    i, rows = 0, []
    while True:
        ok, img = cap.read()
        if not ok:
            break
        t = times[i] if times and i < len(times) else i / fps
        if i % every == 0:
            hands = finder.find(img, t)
            ev = reader.update(t, hands)
            if hands:
                m = max(hands, key=palm_size)
                cx, cy = palm_centre(m)
                p = palm_size(m)
                row = (f"{t - (times[0] if times else 0):7.2f}s n={len(hands)} fingers={count_up(m)} "
                       f"palm=({cx:6.0f},{cy:6.0f}) size={p:5.1f} index={_d(m[5], m[8]):5.1f}")
            else:
                row = f"{t - (times[0] if times else 0):7.2f}s no hand"
            if ev:
                row += "   EVENT " + ", ".join(f"{e['kind']}:{e.get('direction') or e.get('count') or ''}" for e in ev)
            print(row)
        i += 1
    print(f"frames {i}, frame size {img.shape[1] if i else 0}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--camera")
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--work-width", type=int, default=480)
    a = ap.parse_args(argv)
    if a.record:
        record(a.camera, a.clip, a.seconds)
    else:
        replay(a.clip, a.every, a.work_width)


if __name__ == "__main__":
    main()
