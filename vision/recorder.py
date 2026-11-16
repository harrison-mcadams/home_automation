"""Session recorder: save what a camera sees, with timing and notes, for later development.

    python -m vision.recorder --source 0 --out recordings/my_session
    python -m vision.recorder --source http://phone:8080/video --still-url http://phone:8080/photo.jpg

While it runs, type a line and press Enter to timestamp a note (for example
"round 2 start" or "added 2 blight"). Type q and Enter, or press Ctrl-C, to stop.

A session folder holds:
    session.json   camera facts, settings, start/end times, frame counts
    video.mp4      the video, at a steady --video-fps (frames repeat if the camera is slower)
    frames.csv     for each video frame: camera frame index, capture time, whether it was new
    stills/        full-quality JPEG stills every --still-every seconds (full sensor if --still-url)
    stills.csv     still filename and capture time
    notes.jsonl    your typed notes with timestamps (ground truth for later stages)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

from vision.capture import Camera, parse_source


def _now_iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time()).isoformat(timespec="milliseconds")


class SessionRecorder:
    """Write a camera's frames to a session folder until stopped."""

    def __init__(
        self,
        camera: Camera,
        out_dir: Path,
        video_fps: float = 10.0,
        still_every: float = 2.0,
        codec: str = "mp4v",
        video_name: str = "video.mp4",
        jpeg_quality: int = 95,
        extra_metadata: Optional[dict] = None,
    ):
        self.camera = camera
        self.out_dir = Path(out_dir)
        self.video_fps = video_fps
        self.still_every = still_every
        self.codec = codec
        self.video_name = video_name
        self.jpeg_quality = jpeg_quality
        self.extra_metadata = extra_metadata or {}
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.stop_event = threading.Event()
        self._notes_lock = threading.Lock()
        self.stats = {"video_frames": 0, "new_camera_frames": 0, "stills": 0, "still_errors": 0, "notes": 0}

    # -- notes -------------------------------------------------------------

    def note(self, text: str) -> None:
        """Timestamp a free-text note (e.g. "round 3 start")."""
        entry = {"time": time.time(), "iso": _now_iso(), "text": text}
        with self._notes_lock:
            with open(self.out_dir / "notes.jsonl", "a") as f:
                f.write(json.dumps(entry) + "\n")
            self.stats["notes"] += 1

    # -- recording ---------------------------------------------------------

    def _write_metadata(self, started: float, ended: Optional[float] = None) -> None:
        meta = {
            "started": _now_iso(started),
            "ended": _now_iso(ended) if ended else None,
            "duration_seconds": round(ended - started, 1) if ended else None,
            "camera": self.camera.describe(),
            "settings": {
                "video_fps": self.video_fps,
                "still_every_seconds": self.still_every,
                "codec": self.codec,
                "jpeg_quality": self.jpeg_quality,
            },
            "stats": self.stats,
            **self.extra_metadata,
        }
        (self.out_dir / "session.json").write_text(json.dumps(meta, indent=2, default=str))

    def _still_loop(self) -> None:
        stills_dir = self.out_dir / "stills"
        stills_dir.mkdir(exist_ok=True)
        with open(self.out_dir / "stills.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["file", "capture_time", "iso"])
            next_due = time.monotonic()
            while not self.stop_event.is_set():
                wait = next_due - time.monotonic()
                if wait > 0 and self.stop_event.wait(wait):
                    break
                next_due += self.still_every
                try:
                    ts = time.time()
                    image = self.camera.grab_still()
                except Exception as exc:  # a phone dropping off Wi-Fi should not end the session
                    self.stats["still_errors"] += 1
                    print(f"[recorder] still failed: {exc}")
                    continue
                name = f"still_{self.stats['stills']:05d}.jpg"
                cv2.imwrite(str(stills_dir / name), image, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                writer.writerow([name, f"{ts:.3f}", _now_iso(ts)])
                f.flush()
                self.stats["stills"] += 1

    def run(self, duration: Optional[float] = None) -> dict:
        """Record until `duration` seconds pass, stop() is called, or a file source ends."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        first = self.camera.wait_for_frame(timeout=10)
        if first is None:
            raise RuntimeError("Camera delivered no frames")
        h, w = first.image.shape[:2]
        writer = cv2.VideoWriter(
            str(self.out_dir / self.video_name), cv2.VideoWriter_fourcc(*self.codec), self.video_fps, (w, h)
        )
        if not writer.isOpened():
            raise RuntimeError(f"Could not open a video writer with codec {self.codec!r}")

        started = time.time()
        self._write_metadata(started)
        still_thread = None
        if self.still_every and self.still_every > 0:
            still_thread = threading.Thread(target=self._still_loop, name="stills", daemon=True)
            still_thread.start()

        interval = 1.0 / self.video_fps
        next_due = time.monotonic()
        last_index = -1
        try:
            with open(self.out_dir / "frames.csv", "w", newline="") as f:
                rows = csv.writer(f)
                rows.writerow(["video_frame", "camera_frame", "capture_time", "new"])
                while not self.stop_event.is_set():
                    if duration is not None and time.time() - started >= duration:
                        break
                    if self.camera.ended and (self.camera.read() is None or self.camera.read().index == last_index):
                        break
                    wait = next_due - time.monotonic()
                    if wait > 0:
                        self.stop_event.wait(wait)
                    next_due += interval
                    packet = self.camera.read()
                    if packet is None:
                        continue
                    image = packet.image
                    if image.shape[1] != w or image.shape[0] != h:  # camera changed mode mid-session
                        image = cv2.resize(image, (w, h))
                    writer.write(image)
                    is_new = packet.index != last_index
                    last_index = packet.index
                    rows.writerow([self.stats["video_frames"], packet.index, f"{packet.timestamp:.3f}", int(is_new)])
                    self.stats["video_frames"] += 1
                    self.stats["new_camera_frames"] += int(is_new)
                    if self.stats["video_frames"] % int(self.video_fps * 30) == 0:
                        f.flush()
                        self._write_metadata(started)
        finally:
            self.stop_event.set()
            writer.release()
            if still_thread:
                still_thread.join(timeout=15)
            ended = time.time()
            self._write_metadata(started, ended)
        return self.stats

    def stop(self) -> None:
        self.stop_event.set()


def estimate_bytes_per_hour(width: int, height: int, video_fps: float, still_every: float) -> int:
    """Rough disk use, so a long game does not fill the disk by surprise.
    mp4v at these settings runs very roughly 0.1 bits per pixel per frame for a mostly still
    table; a quality-95 JPEG is roughly 0.25 bytes per pixel."""
    video = width * height * video_fps * 3600 * 0.1 / 8
    stills = (3600 / still_every) * width * height * 0.25 if still_every else 0
    return int(video + stills)


def read_notes_from_stdin(recorder: SessionRecorder) -> None:
    """Typed lines become timestamped notes; "q" stops the session."""
    try:
        lines = iter(sys.stdin.readline, "")
        for line in lines:
            if not _handle_note_line(recorder, line):
                return
    except (OSError, ValueError):  # no usable stdin (service, test runner): notes just stay off
        return


def _handle_note_line(recorder: SessionRecorder, line: str) -> bool:
    """Returns False when the line asks to stop."""
    text = line.strip()
    if not text:
        return True
    if text.lower() in {"q", "quit", "stop"}:
        recorder.stop()
        return False
    recorder.note(text)
    print(f"  noted at {datetime.now():%H:%M:%S}: {text}")
    return True


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default="0", help="device index, video file or stream URL (default 0)")
    p.add_argument("--still-url", help="full-resolution photo endpoint, e.g. http://phone:8080/photo.jpg")
    p.add_argument("--out", help="session folder (default recordings/<timestamp>)")
    p.add_argument("--width", type=int, help="request a width (default: camera default)")
    p.add_argument("--height", type=int)
    p.add_argument("--fourcc", help="request a pixel format, e.g. MJPG")
    p.add_argument("--video-fps", type=float, default=10.0)
    p.add_argument("--still-every", type=float, default=2.0, help="seconds between stills, 0 for none")
    p.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270],
                   help="rotate frames clockwise by this many degrees")
    p.add_argument("--duration", type=float, help="stop after this many seconds")
    p.add_argument("--preview-port", type=int, help="also serve a live preview on this port")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out or Path("recordings") / datetime.now().strftime("%Y%m%d-%H%M%S"))
    with Camera(parse_source(args.source), width=args.width, height=args.height,
                fourcc=args.fourcc, still_url=args.still_url, rotate=args.rotate) as cam:
        recorder = SessionRecorder(cam, out, video_fps=args.video_fps, still_every=args.still_every)
        if args.preview_port:
            from vision.preview import PreviewServer
            PreviewServer(cam, port=args.preview_port).start()
        gb = estimate_bytes_per_hour(cam.width, cam.height, args.video_fps, args.still_every) / 1e9
        print(f"Recording {cam.width}x{cam.height} to {out.resolve()} (roughly {gb:.1f} GB per hour).")
        print("Type a note and press Enter to timestamp it. Type q and Enter (or Ctrl-C) to stop.")
        threading.Thread(target=read_notes_from_stdin, args=(recorder,), daemon=True).start()
        try:
            stats = recorder.run(duration=args.duration)
        except KeyboardInterrupt:
            recorder.stop()
            stats = recorder.stats
    print(f"Done: {stats['video_frames']} video frames, {stats['stills']} stills, {stats['notes']} notes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
