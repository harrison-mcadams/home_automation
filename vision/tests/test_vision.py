import csv
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import pytest

from vision import quality
from vision.capture import Camera, fetch_still, parse_source
from vision.markers import markers_svg
from vision.preview import PreviewServer
from vision.probe import run_probe, summarize
from vision.recorder import SessionRecorder

from .conftest import MARKER_MM, make_scene


def test_parse_source():
    assert parse_source("0") == 0
    assert parse_source(2) == 2
    assert parse_source("http://phone:8080/video") == "http://phone:8080/video"
    assert parse_source("clip.mp4") == "clip.mp4"


def test_marker_scale_matches_known_size(scene):
    scale = quality.marker_scale(scene, MARKER_MM)
    assert sorted(scale.per_marker) == [0, 1, 2, 3]
    assert scale.px_per_mm == pytest.approx(2.0, rel=0.03)
    assert scale.spread == pytest.approx(1.0, abs=0.05)  # flat, straight-down view


def test_sharpness_drops_when_blurred(scene):
    assert quality.sharpness(cv2.GaussianBlur(scene, (15, 15), 5)) < quality.sharpness(scene) / 3
    grid = quality.sharpness_grid(scene)
    assert len(grid) == 3 and len(grid[0]) == 3


def test_brightness_and_noise():
    black = np.zeros((10, 10, 3), np.uint8)
    assert quality.brightness(black)["pct_black"] == 100.0
    assert quality.temporal_noise([black, black, black]) == 0.0
    assert quality.temporal_noise([black]) is None


def test_camera_reads_file_and_reports_delivered_size(video_file):
    with Camera(str(video_file)) as cam:
        first = cam.wait_for_frame()
        second = cam.wait_for_frame(after_index=first.index)
        assert second.index > first.index
        assert (cam.width, cam.height) == (1280, 720)
        info = cam.describe()
        assert info["delivered_width"] == 1280
        assert info["driver_reported_fps"] == pytest.approx(20, abs=1)


def test_file_source_ends(video_file):
    cam = Camera(str(video_file), pace_files=False).start()
    deadline = time.time() + 10
    while not cam.ended and time.time() < deadline:
        time.sleep(0.05)
    assert cam.ended and cam.frames_read == 60
    cam.stop()


def test_probe_on_file(video_file, tmp_path):
    out = tmp_path / "probe"
    report = run_probe(str(video_file), out, marker_mm=MARKER_MM, settle_seconds=0.2, sample_seconds=0.5)
    assert report["camera"]["delivered_width"] == 1280
    assert report["markers"]["found"] == 4
    assert report["scale"]["px_per_mm"] == pytest.approx(2.0, rel=0.05)
    assert report["scale"]["view_width_mm"] == pytest.approx(640, rel=0.05)
    assert (out / "report.json").exists() and (out / "snapshot.png").exists()
    assert json.loads((out / "report.json").read_text())["markers"]["found"] == 4
    assert "px/mm" in summarize(report)


def test_probe_fov_width_fallback(video_file, tmp_path):
    report = run_probe(str(video_file), tmp_path, fov_width_mm=640, settle_seconds=0.1, sample_seconds=0.3)
    assert report["scale"]["px_per_mm"] == pytest.approx(2.0)
    assert report["scale"]["method"] == "fov_width"


def test_recorder_writes_session(video_file, tmp_path):
    out = tmp_path / "session"
    with Camera(str(video_file)) as cam:
        rec = SessionRecorder(cam, out, video_fps=10, still_every=0.5)
        rec.note("round 1 start")
        stats = rec.run(duration=1.5)
    assert stats["video_frames"] >= 10
    assert stats["stills"] >= 2
    meta = json.loads((out / "session.json").read_text())
    assert meta["camera"]["delivered_width"] == 1280 and meta["duration_seconds"] is not None
    with open(out / "frames.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == stats["video_frames"]
    notes = [json.loads(line) for line in (out / "notes.jsonl").read_text().splitlines()]
    assert notes[0]["text"] == "round 1 start"
    video = cv2.VideoCapture(str(out / "video.mp4"))
    ok, frame = video.read()
    assert ok and frame.shape[:2] == (720, 1280)
    assert len(list((out / "stills").glob("*.jpg"))) == stats["stills"]


def _serve(handler_cls):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def test_fetch_still_from_photo_endpoint():
    big = make_scene(width=3200, height=1800, marker_px=204)
    body = cv2.imencode(".jpg", big)[1].tobytes()

    class Photo(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server, port = _serve(Photo)
    try:
        still = fetch_still(f"http://127.0.0.1:{port}/photo.jpg")
        assert still.shape[:2] == (1800, 3200)
        assert quality.marker_scale(still, MARKER_MM).px_per_mm == pytest.approx(204 / MARKER_MM, rel=0.03)
    finally:
        server.shutdown()


def test_network_stream_source(video_file):
    """A phone-style MJPEG stream: serve the file through the preview server and read it back as a URL."""
    with Camera(str(video_file)) as file_cam:
        server = ThreadingHTTPServer(("127.0.0.1", 0), PreviewServer(file_cam)._handler())
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        try:
            with Camera(f"http://127.0.0.1:{port}/stream.mjpg") as net_cam:
                packet = net_cam.wait_for_frame(timeout=10)
                assert packet is not None
                assert net_cam.width == 1280  # preview downscales only above 1280 wide
                assert net_cam.describe()["source"].startswith("http://")
        finally:
            server.shutdown()


def test_markers_svg_is_real_size():
    svg = markers_svg([0, 1], size_mm=40)
    assert 'width="200mm"' in svg and "id 1, 40 mm" in svg


def test_probe_survives_file_ending_during_settle(tmp_path):
    """Regression: a short clip that ends before sampling must not divide by zero."""
    clip = tmp_path / "short.avi"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"MJPG"), 20, (640, 360))
    for _ in range(5):
        writer.write(make_scene(width=640, height=360))
    writer.release()
    report = run_probe(str(clip), tmp_path / "p", settle_seconds=1.0, sample_seconds=0.5)
    assert report["camera"]["delivered_width"] == 640
    assert report["camera"]["measured_fps"] >= 0


def test_fetch_still_with_basic_auth_and_redaction():
    from vision.capture import redact, with_credentials

    body = cv2.imencode(".jpg", make_scene(width=640, height=360))[1].tobytes()
    import base64
    expected = "Basic " + base64.b64encode(b"harrison:p@ss word").decode()

    class Locked(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.headers.get("Authorization") != expected:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="cam"')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server, port = _serve(Locked)
    try:
        url = with_credentials(f"http://127.0.0.1:{port}/photo.jpg", "harrison", "p@ss word")
        assert fetch_still(url).shape[:2] == (360, 640)
        assert "p%40ss" not in redact(url) and redact(url) == f"http://***@127.0.0.1:{port}/photo.jpg"
        with pytest.raises(Exception):
            fetch_still(f"http://127.0.0.1:{port}/photo.jpg")
    finally:
        server.shutdown()
    assert redact(0) == 0 and redact("clip.mp4") == "clip.mp4"
