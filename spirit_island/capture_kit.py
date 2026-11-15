"""Spirit Island capture kit: one command to test the camera and record a game.

    python -m spirit_island.capture_kit                        # USB camera 0
    python -m spirit_island.capture_kit --marker-mm 40         # with printed markers on the table
    python -m spirit_island.capture_kit --phone --marker-mm 40 # Android phone on USB (adb)
    python -m spirit_island.capture_kit --source http://<phone>:8080/video \\
        --still-url http://<phone>:8080/photo.jpg              # a phone over Wi-Fi

Runs the same on Windows, macOS and Linux.

Steps:
  1. Aim: a live preview runs at http://<this-computer>:8090 while you position
     the camera. Press Enter when it looks right.
  2. Probe: measures what the camera really delivers (resolution, frame rate,
     sharpness, pixels per mm) and says whether that is enough to see pieces.
  3. Record: saves video, regular full-quality stills and your typed notes
     (for example "round 2 start") until you type q.

Everything lands in spirit_island/recordings/<date-time>/, which git ignores.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from vision.capture import Camera, parse_source
from vision.preview import PreviewServer
from vision.probe import run_probe, summarize
from vision.recorder import SessionRecorder, estimate_bytes_per_hour, read_notes_from_stdin

RECORDINGS = Path(__file__).resolve().parent / "recordings"

# Rough guide, not a measured spec: the smallest pieces on the island (explorers,
# presence, some tokens) are around a centimetre across. Override with
# --smallest-piece-mm once you have measured yours.
SMALLEST_PIECE_MM = 10.0
# Pixels across the smallest piece. Small-object detectors start to work around
# 12 px and become comfortable around 20 px and up.
GOOD_PX, OK_PX = 20.0, 12.0


def game_verdict(report: dict, smallest_piece_mm: float = SMALLEST_PIECE_MM) -> str:
    """Translate a probe report into "can this camera see Spirit Island pieces?"."""
    px_per_mm = (report.get("still") or {}).get("px_per_mm") or (report.get("scale") or {}).get("px_per_mm")
    if not px_per_mm:
        return (
            "No scale measured yet, so I can't say whether pieces will be resolvable. "
            "Print markers (python -m vision.markers), lay them on the board, and rerun with --marker-mm."
        )
    px = smallest_piece_mm * px_per_mm
    if px >= GOOD_PX:
        grade = "Good: the smallest pieces should be detectable."
    elif px >= OK_PX:
        grade = "Borderline: large pieces (cities, towns, blight) should work; explorers and presence will be hard."
    else:
        grade = "Too coarse for pieces: fine for reading boards and cards, but expect to tap in piece counts by hand."
    source = "full-resolution still" if (report.get("still") or {}).get("px_per_mm") else "video"
    return f"A {smallest_piece_mm:g} mm piece spans about {px:.0f} px in the {source}. {grade}"


def aim(source, still_url: Optional[str], port: int) -> None:
    with Camera(source, still_url=still_url) as cam:
        server = PreviewServer(cam, port=port).start()
        print(f"Camera delivers {cam.width}x{cam.height} by default.")
        print("Position the camera over the board, then press Enter to continue.")
        try:
            input()
        finally:
            server.stop()


def record(source, still_url, out_dir: Path, width, height, video_fps, still_every, port, extra) -> dict:
    with Camera(source, width=width, height=height, still_url=still_url) as cam:
        server = PreviewServer(cam, port=port).start() if port else None
        recorder = SessionRecorder(cam, out_dir, video_fps=video_fps, still_every=still_every, extra_metadata=extra)
        gb = estimate_bytes_per_hour(cam.width, cam.height, video_fps, still_every) / 1e9
        print(f"\nRecording {cam.width}x{cam.height} into {out_dir} (roughly {gb:.1f} GB per hour).")
        print("Type notes as you play and press Enter, for example:")
        print('  "setup done", "round 1 start", "explore", "build", "ravage", "fear card 2"')
        print("Type q and Enter (or Ctrl-C) to stop.\n")
        threading.Thread(target=read_notes_from_stdin, args=(recorder,), daemon=True).start()
        try:
            stats = recorder.run()
        except KeyboardInterrupt:
            recorder.stop()
            stats = recorder.stats
        finally:
            if server:
                server.stop()
    return stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default="0", help="USB camera index, stream URL or video file (default 0)")
    p.add_argument("--phone", nargs="?", const=8080, type=int, metavar="PORT",
                   help="use an Android phone on USB: adb-forward its camera app (default port 8080)")
    p.add_argument("--still-url", help="full-resolution photo URL for phone cameras, e.g. http://phone:8080/photo.jpg")
    p.add_argument("--marker-mm", type=float, help="side of the printed ArUco markers in view, in mm")
    p.add_argument("--fov-width-mm", type=float, help="or: width of the area the camera sees, in mm")
    p.add_argument("--smallest-piece-mm", type=float, default=SMALLEST_PIECE_MM)
    p.add_argument("--port", type=int, default=8090, help="live preview port, 0 to disable")
    p.add_argument("--video-fps", type=float, default=10.0)
    p.add_argument("--still-every", type=float, default=2.0)
    p.add_argument("--skip-aim", action="store_true")
    p.add_argument("--probe-only", action="store_true", help="stop after the camera report")
    p.add_argument("--out", help="session folder (default spirit_island/recordings/<date-time>)")
    args = p.parse_args(argv)

    if args.phone:
        from vision import phone

        try:
            base = phone.forward(args.phone)
        except phone.PhoneError as exc:
            print(f"Problem with the phone: {exc}\nTry `python -m vision.phone` for a step-by-step check.")
            return 1
        args.source = phone.urls(base)["video"]
        args.still_url = args.still_url or phone.urls(base)["photo"]
        print(f"Using the phone on USB: video {args.source}, stills {args.still_url}")
    source = parse_source(args.source)
    session = Path(args.out) if args.out else RECORDINGS / datetime.now().strftime("%Y%m%d-%H%M%S")
    session.mkdir(parents=True, exist_ok=True)

    if not args.skip_aim and args.port:
        aim(source, args.still_url, args.port)

    report = run_probe(
        source=source,
        out_dir=session / "probe",
        marker_mm=args.marker_mm,
        fov_width_mm=args.fov_width_mm,
        still_url=args.still_url,
    )
    verdict = game_verdict(report, args.smallest_piece_mm)
    report["spirit_island_verdict"] = verdict
    (session / "probe" / "report.json").write_text(json.dumps(report, indent=2))
    summary = summarize(report) + "\n\nSpirit Island: " + verdict
    (session / "probe" / "summary.txt").write_text(summary + "\n")
    print("\n" + summary)
    print(f"\nCamera report saved to {session / 'probe'}")

    if args.probe_only:
        return 0
    print("\nPress Enter to start recording, or type q and Enter to finish here.")
    if input().strip().lower() in {"q", "quit"}:
        return 0

    cam = report["camera"]
    stats = record(
        source,
        args.still_url,
        session,
        cam["delivered_width"] if isinstance(source, int) else None,
        cam["delivered_height"] if isinstance(source, int) else None,
        args.video_fps,
        args.still_every,
        args.port,
        extra={"purpose": "spirit_island", "probe_summary": summary},
    )
    print(f"\nSaved {stats['video_frames']} video frames, {stats['stills']} stills and "
          f"{stats['notes']} notes to {session}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
