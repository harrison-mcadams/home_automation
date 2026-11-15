# Spirit Island Capture Kit

This guide gets the camera over the table, tells you what it can actually see,
and records a game so later stages of the tracker can be built against real
footage of your table.

The camera code lives in `vision/` and knows nothing about Spirit Island, so the
same pieces can later drive other projects (for example gestures from the couch).
The game-specific wrapper is `spirit_island/capture_kit.py`.

## 1. Installation (once)

1.  Open **Terminal** on the MacBook (or SSH in).
2.  Navigate to your `home_automation` directory.
3.  If you use a venv or Conda environment, **activate it first**.
4.  Install the dependencies:
    ```bash
    python3 -m pip install -r vision/requirements.txt
    ```
5.  Check the camera is visible:
    ```bash
    python3 -m vision.probe --list
    ```
    You should see something like `0: 1280x720 by default (AVFOUNDATION)`. If the
    MacBook's own FaceTime camera is also listed, the USB webcam is usually `1`.

**Camera permission:** macOS asks for camera access the first time a program uses
it, and the prompt appears on the Mac's screen. If `--list` finds nothing or the
camera fails to open over SSH, run the command once from Terminal on the Mac
itself (or over Screen Sharing), click Allow, and check
**System Settings > Privacy & Security > Camera**.

## 2. Optional: print scale markers

To learn how many pixels a game piece covers, put a few printed markers on the
table:

```bash
python3 -m vision.markers --out markers.svg --size-mm 40
```

Open `markers.svg` and print it at **100% / actual size** (not "fit to page").
Measure one black square with a ruler; use that number for `--marker-mm`. Cut
the markers out and lay them flat at the corners of the play area.

No printer? Measure the width of the area the camera sees with a tape measure
and pass `--fov-width-mm` instead. It is less precise but good enough for a first look.

## 3. Run it

```bash
python3 -m spirit_island.capture_kit --marker-mm 40
```

Add `--source 1` if the webcam is not camera 0. The kit runs three steps:

1.  **Aim.** A live preview runs at `http://<your-mac-name>.local:8090`. Open it
    on your phone, position the camera over the board, and watch the sharpness
    number (higher is sharper). Press Enter in the terminal when it looks right.
2.  **Probe.** It asks the camera for every common resolution, records what
    really comes back and at what frame rate, then measures sharpness, lighting,
    noise and pixels per mm. The last line says whether the smallest pieces are
    big enough to detect.
3.  **Record.** Press Enter to start. Play as normal, and type short notes as you
    go, pressing Enter after each one: `setup done`, `round 1 start`, `ravage`,
    `fear card earned`. These become the answer key for later stages. Type `q`
    and Enter to stop.

To get only the camera report, add `--probe-only`.

## 4. What you get

Everything goes to `spirit_island/recordings/<date-time>/` (ignored by git):

| File | What it is |
| --- | --- |
| `probe/summary.txt` | The camera report in plain English |
| `probe/report.json` | Every measurement, including all delivered resolutions |
| `probe/snapshot.png`, `snapshot_annotated.jpg` | What the camera saw, with markers outlined |
| `video.mp4` | The game at 10 frames per second |
| `stills/` | Full-quality JPEG every 2 seconds |
| `notes.jsonl` | Your typed notes with timestamps |
| `frames.csv`, `stills.csv`, `session.json` | Timing and camera details |

A 1080p session uses a few GB per hour; the kit prints its own
estimate when recording starts. Use `--still-every 5` to save space.

## 5. Using a phone as the camera

Any phone app that serves an MJPEG stream works. With an IP Webcam style app on
Android, the video is at `/video` and a full-resolution photo at `/photo.jpg`:

```bash
python3 -m spirit_island.capture_kit --marker-mm 40 \
    --source http://<phone-ip>:8080/video \
    --still-url http://<phone-ip>:8080/photo.jpg
```

The video is used for aiming and timing; the stills come from the full sensor,
and the report gives pixels per mm for both.

## 6. The individual tools

| Command | Purpose |
| --- | --- |
| `python3 -m vision.probe --source 0 --marker-mm 40` | Camera report only, any use |
| `python3 -m vision.preview --source 0` | Live preview only, for aiming |
| `python3 -m vision.recorder --source 0` | Record a session, any use |
| `python3 -m vision.markers` | Printable ArUco markers |
| `python3 -m pytest vision spirit_island` | Run the tests (no camera needed) |
