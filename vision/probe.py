"""Camera probe: find out what a camera really delivers.

    python -m vision.probe --list                 # which cameras exist
    python -m vision.probe --source 0             # full report for camera 0
    python -m vision.probe --source 0 --marker-mm 40   # plus pixels-per-mm from printed markers
    python -m vision.probe --source http://phone:8080/video --still-url http://phone:8080/photo.jpg

Writes report.json, snapshot.png and snapshot_annotated.jpg to --out.
Nothing here assumes a resolution: it asks the camera for a ladder of common
sizes and records what actually comes back, and how fast.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

from vision import quality
from vision.capture import Camera, Source, fetch_still, list_cameras, open_capture, parse_source

# Requested sizes, largest first. Cameras snap to the nearest mode they support.
CANDIDATE_SIZES = [(3840, 2160), (2560, 1440), (1920, 1080), (1600, 1200), (1280, 720), (640, 480)]


def measure_fps(cap: cv2.VideoCapture, seconds: float = 1.5, warmup: float = 0.5) -> float:
    """Frames per second actually delivered by an open capture."""
    end_warmup = time.monotonic() + warmup
    while time.monotonic() < end_warmup:
        cap.read()
    count, start = 0, time.monotonic()
    while time.monotonic() - start < seconds:
        ok, _ = cap.read()
        if ok:
            count += 1
    elapsed = time.monotonic() - start
    return round(count / elapsed, 1) if elapsed > 0 else 0.0


def sweep_modes(source: Source, fourcc: Optional[str] = None, fps_seconds: float = 1.5) -> list[dict]:
    """Request each candidate size; record the delivered size and measured fps.

    Returns one entry per distinct delivered size, largest first.
    """
    seen: dict[tuple[int, int], dict] = {}
    for req_w, req_h in CANDIDATE_SIZES:
        cap = open_capture(source, width=req_w, height=req_h, fourcc=fourcc)
        try:
            if not cap.isOpened():
                continue
            image = None
            for _ in range(10):
                ok, image = cap.read()
                if ok and image is not None:
                    break
                time.sleep(0.1)
            if image is None:
                continue
            delivered = (int(image.shape[1]), int(image.shape[0]))
            if delivered in seen:
                seen[delivered]["requested"].append(f"{req_w}x{req_h}")
                continue
            fps = measure_fps(cap, seconds=fps_seconds) if fps_seconds > 0 else None
            seen[delivered] = {
                "width": delivered[0],
                "height": delivered[1],
                "measured_fps": fps,
                "requested": [f"{req_w}x{req_h}"],
            }
            print(f"  asked {req_w}x{req_h:<5} -> got {delivered[0]}x{delivered[1]}"
                  + (f" at {fps} fps" if fps is not None else ""))
        finally:
            cap.release()
    return sorted(seen.values(), key=lambda m: m["width"] * m["height"], reverse=True)


def run_probe(
    source: Source = 0,
    out_dir: Path = Path("probe_output"),
    width: Optional[int] = None,
    height: Optional[int] = None,
    fourcc: Optional[str] = None,
    marker_mm: Optional[float] = None,
    fov_width_mm: Optional[float] = None,
    still_url: Optional[str] = None,
    sweep: bool = True,
    settle_seconds: float = 2.0,
    sample_seconds: float = 3.0,
) -> dict:
    """Measure a camera and write report.json plus snapshots into out_dir."""
    source = parse_source(source)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"probed_at": datetime.now().isoformat(timespec="seconds"), "source": source}

    is_device = isinstance(source, int)
    if sweep and is_device and width is None:
        print("Checking which resolutions the camera delivers...")
        report["modes"] = sweep_modes(source, fourcc=fourcc)
        if report["modes"]:
            width, height = report["modes"][0]["width"], report["modes"][0]["height"]

    size = f"{width}x{height}" if width else "its default size"
    print(f"Opening camera at {size} and letting exposure settle...")
    with Camera(source, width=width, height=height, fourcc=fourcc, still_url=still_url) as cam:
        time.sleep(settle_seconds)  # auto-exposure and auto-focus need a moment
        start_index = cam.frames_read
        start = time.monotonic()
        frames = []
        last = cam.read().index
        while time.monotonic() - start < sample_seconds:
            packet = cam.wait_for_frame(after_index=last, timeout=2.0)
            if packet is None:
                break
            last = packet.index
            if len(frames) < 15:
                frames.append(packet.image)
        elapsed = time.monotonic() - start
        report["camera"] = cam.describe()
        # A file can run out during the settle wait, and Windows' clock is coarse: guard both.
        report["camera"]["measured_fps"] = (
            round((cam.frames_read - start_index) / elapsed, 1) if elapsed > 0 else 0.0
        )
        snapshot = cam.read().image

    report["image"] = {
        "sharpness": round(quality.sharpness(snapshot), 1),
        "sharpness_grid_3x3": quality.sharpness_grid(snapshot),
        "brightness": quality.brightness(snapshot),
        "temporal_noise": quality.temporal_noise(frames),
    }

    scale = None
    px_per_mm = None
    if marker_mm:
        scale = quality.marker_scale(snapshot, marker_mm)
        px_per_mm = scale.px_per_mm
        report["markers"] = {
            "marker_mm": marker_mm,
            "found": len(scale.per_marker),
            "per_marker": scale.per_marker,
            "px_per_mm": px_per_mm,
            "tilt_spread": scale.spread,
        }
    if px_per_mm is None and fov_width_mm:
        px_per_mm = round(snapshot.shape[1] / fov_width_mm, 3)
        report["fov_width_mm"] = fov_width_mm
    if px_per_mm:
        h, w = snapshot.shape[:2]
        report["scale"] = {
            "px_per_mm": px_per_mm,
            "px_across_10mm": round(10 * px_per_mm, 1),
            "view_width_mm": round(w / px_per_mm),
            "view_height_mm": round(h / px_per_mm),
            "method": "markers" if scale and scale.px_per_mm else "fov_width",
        }

    if still_url:
        t0 = time.monotonic()
        still = fetch_still(still_url)
        fetch_s = round(time.monotonic() - t0, 2)
        report["still"] = {
            "url": still_url,
            "width": int(still.shape[1]),
            "height": int(still.shape[0]),
            "fetch_seconds": fetch_s,
            "sharpness": round(quality.sharpness(still), 1),
        }
        if marker_mm:
            still_scale = quality.marker_scale(still, marker_mm)
            report["still"]["markers_found"] = len(still_scale.per_marker)
            report["still"]["px_per_mm"] = still_scale.px_per_mm
        elif fov_width_mm:
            report["still"]["px_per_mm"] = round(still.shape[1] / fov_width_mm, 3)
        cv2.imwrite(str(out_dir / "still.jpg"), still, [cv2.IMWRITE_JPEG_QUALITY, 95])

    cv2.imwrite(str(out_dir / "snapshot.png"), snapshot)
    lines = [f"{snapshot.shape[1]}x{snapshot.shape[0]} @ {report['camera']['measured_fps']} fps",
             f"sharpness {report['image']['sharpness']}"]
    if px_per_mm:
        lines.append(f"{px_per_mm} px/mm")
    cv2.imwrite(str(out_dir / "snapshot_annotated.jpg"), quality.annotate(snapshot, scale, lines))
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    return report


def summarize(report: dict) -> str:
    """Plain-English summary of a probe report."""
    cam = report["camera"]
    img = report["image"]
    out = [
        f"Camera {cam['source']} ({cam['backend']}): delivers {cam['delivered_width']}x"
        f"{cam['delivered_height']} at {cam['measured_fps']} fps measured "
        f"(driver claims {cam['driver_reported_fps']}).",
    ]
    if report.get("modes"):
        modes = ", ".join(
            f"{m['width']}x{m['height']}" + (f"@{m['measured_fps']}" if m.get("measured_fps") else "")
            for m in report["modes"]
        )
        out.append(f"Modes it actually delivers: {modes}.")
    b = img["brightness"]
    out.append(
        f"Sharpness {img['sharpness']} (variance of Laplacian), brightness {b['mean']}/255, "
        f"{b['pct_white']}% blown highlights, frame-to-frame noise {img['temporal_noise']}."
    )
    grid = img["sharpness_grid_3x3"]
    flat = [v for row in grid for v in row]
    if flat and max(flat) > 0 and min(flat) / max(flat) < 0.25:
        out.append("Focus or lighting is uneven across the frame: see sharpness_grid_3x3 in report.json.")
    if "markers" in report:
        m = report["markers"]
        if m["found"] == 0:
            out.append("No ArUco markers found in the snapshot.")
        else:
            tilt = f", tilt spread {m['tilt_spread']}" if m["tilt_spread"] else ""
            out.append(f"Found {m['found']} markers{tilt}.")
    if "scale" in report:
        s = report["scale"]
        out.append(
            f"Scale: {s['px_per_mm']} px/mm, so a 10 mm object spans about {s['px_across_10mm']} px. "
            f"The view covers about {s['view_width_mm']} x {s['view_height_mm']} mm."
        )
    if "still" in report:
        st = report["still"]
        line = (f"Full-resolution still from {st['url']}: {st['width']}x{st['height']}, "
                f"fetched in {st['fetch_seconds']} s")
        if st.get("px_per_mm"):
            line += f", {st['px_per_mm']} px/mm ({round(10 * st['px_per_mm'], 1)} px across 10 mm)"
        out.append(line + ".")
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="list cameras and exit")
    p.add_argument("--source", default="0", help="device index, video file or stream URL (default 0)")
    p.add_argument("--out", default="probe_output", help="folder for report.json and snapshots")
    p.add_argument("--width", type=int, help="request this width instead of the largest delivered")
    p.add_argument("--height", type=int)
    p.add_argument("--fourcc", help="request a pixel format, e.g. MJPG (helps some USB cameras reach 30 fps)")
    p.add_argument("--marker-mm", type=float, help="printed side length of the ArUco markers in view, in mm")
    p.add_argument("--fov-width-mm", type=float, help="width of the area in view, in mm (if no markers)")
    p.add_argument("--still-url", help="full-resolution photo endpoint, e.g. http://phone:8080/photo.jpg")
    p.add_argument("--no-sweep", action="store_true", help="skip the resolution sweep")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        cams = list_cameras()
        if not cams:
            print("No cameras found.")
            return 1
        for c in cams:
            print(f"  {c['index']}: {c['default_width']}x{c['default_height']} by default ({c['backend']})")
        return 0
    report = run_probe(
        source=args.source,
        out_dir=Path(args.out),
        width=args.width,
        height=args.height,
        fourcc=args.fourcc,
        marker_mm=args.marker_mm,
        fov_width_mm=args.fov_width_mm,
        still_url=args.still_url,
        sweep=not args.no_sweep,
    )
    print()
    print(summarize(report))
    print(f"\nSaved report.json and snapshots to {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
