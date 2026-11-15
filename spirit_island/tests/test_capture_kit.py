import json

import cv2

from spirit_island import capture_kit
from vision.tests.conftest import make_scene


def test_verdict_grades_by_pixels_across_smallest_piece():
    assert "No scale" in capture_kit.game_verdict({})
    assert "Good" in capture_kit.game_verdict({"scale": {"px_per_mm": 2.5}})
    assert "Borderline" in capture_kit.game_verdict({"scale": {"px_per_mm": 1.5}})
    assert "Too coarse" in capture_kit.game_verdict({"scale": {"px_per_mm": 0.8}})
    # A full-resolution still beats the video when both are measured.
    verdict = capture_kit.game_verdict({"scale": {"px_per_mm": 0.8}, "still": {"px_per_mm": 3.0}})
    assert "Good" in verdict and "still" in verdict


def test_one_command_probe_and_record(tmp_path, monkeypatch):
    clip = tmp_path / "game.avi"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"MJPG"), 20, (1280, 720))
    for _ in range(40):
        writer.write(make_scene())
    writer.release()

    monkeypatch.setattr("builtins.input", lambda *a: "")  # press Enter to start recording
    session = tmp_path / "session"
    rc = capture_kit.main([
        "--source", str(clip), "--marker-mm", "42", "--skip-aim", "--port", "0",
        "--out", str(session), "--still-every", "0.5",
    ])
    assert rc == 0
    report = json.loads((session / "probe" / "report.json").read_text())
    assert report["markers"]["found"] == 4
    assert "spans about 20 px" in report["spirit_island_verdict"]  # ~2 px/mm, 10 mm piece
    assert (session / "probe" / "summary.txt").exists()
    meta = json.loads((session / "session.json").read_text())
    assert meta["purpose"] == "spirit_island"
    assert meta["stats"]["video_frames"] > 0
    assert (session / "video.mp4").exists()
