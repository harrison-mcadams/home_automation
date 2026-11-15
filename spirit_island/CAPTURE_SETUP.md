# Spirit Island Capture Kit

This guide gets a camera over the table, tells you what it can actually see,
and records a game so later stages of the tracker can be built against real
footage of your table. It runs the same on Windows and macOS.

The camera code lives in `vision/` and knows nothing about Spirit Island, so the
same pieces can later drive other projects (for example gestures from the couch).
The game-specific wrapper is `spirit_island/capture_kit.py`.

Commands below use `python`. On Windows that may be `py`; on macOS, `python3`.

## 1. Installation (once)

1.  Open a terminal (PowerShell on Windows, Terminal on macOS).
2.  Navigate to your `home_automation` directory.
3.  If you use a venv or Conda environment, **activate it first**.
4.  Install the dependencies:
    ```bash
    python -m pip install -r vision/requirements.txt
    ```

## 2. Set up the camera

### Option A: Android phone on USB (recommended, e.g. an old Pixel 6)

A phone's main camera is far better than an old webcam, and over USB it needs
no Wi-Fi and charges while it works.

**On the phone (once):**

1.  Install an IP-camera app that serves `/video` and `/photo.jpg`, such as
    *IP Webcam*.
2.  In the app's settings:
    - **Video resolution:** 1920x1080. The video is only used for aiming and to
      notice when hands leave the table, so 1080p is plenty and keeps it smooth.
    - **Photo resolution:** the largest available. These full-sensor stills are
      what later stages read pieces from.
    - **Audio:** off.
    - **Keep the screen awake** and allow it to run in the background.
    - **Focus:** once the phone is mounted and aimed, lock focus (or set it to
      fixed) so it doesn't hunt when hands move over the board.
3.  Turn on **Developer options** (Settings > About phone, tap *Build number*
    seven times), then **USB debugging** (Settings > System > Developer options).
4.  Because the phone will sit on the charger for long stretches, turn on any
    battery protection your Android version offers (on Pixels this is under
    Settings > Battery, as *Adaptive charging* or a charging limit).
5.  Mount it overhead, main camera pointing straight down at the play area.

**On the computer (once):** install Android
[platform-tools](https://developer.android.com/tools/releases/platform-tools)
and make sure `adb` is on your PATH (`adb version` should work in a new terminal).

**Each session:** plug in the phone, start the app's server, then check it:

```bash
python -m vision.phone
```

This forwards the phone's port 8080 to `http://localhost:8080` over USB, and
prints the video size and full-photo size it gets. The first time, accept the
"Allow USB debugging?" prompt on the phone.

*Simpler fallback:* Android 14 and later can also act as a plain USB webcam (pull
down the notification after plugging in, choose *Webcam*). Then it behaves like
Option B, but you lose the full-resolution stills, so prefer the app.

### Option B: USB webcam

Plug it in and list cameras:

```bash
python -m vision.probe --list
```

You should see something like `0: 1280x720 by default (DSHOW)` on Windows or
`(AVFOUNDATION)` on macOS. If a laptop's built-in camera is also listed, the USB
webcam is usually `1`; pass it with `--source 1` below.

**Camera permission.** Windows: Settings > Privacy & security > Camera, turn on
*Let desktop apps access your camera*. macOS: the prompt appears on the Mac's
own screen the first time; if it fails over SSH, run once locally and click
Allow, then check System Settings > Privacy & Security > Camera.

## 3. Optional: print scale markers

To learn how many pixels a game piece covers, put a few printed markers on the
table:

```bash
python -m vision.markers --out markers.svg --size-mm 40
```

Open `markers.svg` in a browser and print it at **100% / actual size** (not
"fit to page"). Measure one black square with a ruler; use that number for
`--marker-mm`. Cut the markers out and lay them flat at the corners of the play area.

No printer? Measure the width of the area the camera sees with a tape measure
and pass `--fov-width-mm` instead. It is less precise but good enough for a first look.

## 4. Run it

Phone on USB:

```bash
python -m spirit_island.capture_kit --phone --marker-mm 40
```

USB webcam:

```bash
python -m spirit_island.capture_kit --marker-mm 40
```

The kit runs three steps:

1.  **Aim.** A live preview runs at `http://<this-computer>:8090` (it prints the
    address). Open it on another device, position the camera over the board,
    and watch the sharpness number (higher is sharper). Press Enter in the
    terminal when it looks right. Windows may ask to let Python through the
    firewall; allow it on private networks so your phone or tablet can see it.
2.  **Probe.** It records what resolution and frame rate the camera really
    delivers (for a webcam it tries everything from 4K down to 480p), then
    measures sharpness, lighting, noise and pixels per mm. For a phone it also
    measures the full-resolution stills. The last line says whether the
    smallest pieces are big enough to detect.
3.  **Record.** Press Enter to start. Play as normal, and type short notes as you
    go, pressing Enter after each one: `setup done`, `round 1 start`, `ravage`,
    `fear card earned`. These become the answer key for later stages. Type `q`
    and Enter to stop.

To get only the camera report, add `--probe-only`.

## 5. What you get

Everything goes to `spirit_island/recordings/<date-time>/` (ignored by git):

| File | What it is |
| --- | --- |
| `probe/summary.txt` | The camera report in plain English |
| `probe/report.json` | Every measurement, including all delivered resolutions |
| `probe/snapshot.png`, `snapshot_annotated.jpg`, `still.jpg` | What the camera saw, with markers outlined |
| `video.mp4` | The game at 10 frames per second |
| `stills/` | Full-quality JPEG every 2 seconds (full-sensor photos with a phone) |
| `notes.jsonl` | Your typed notes with timestamps |
| `frames.csv`, `stills.csv`, `session.json` | Timing and camera details |

A session uses a few GB per hour; the kit prints its own estimate when recording
starts. Use `--still-every 5` to save space.

## 6. The individual tools

| Command | Purpose |
| --- | --- |
| `python -m vision.phone` | Forward an Android phone over USB and test it |
| `python -m vision.probe --source 0 --marker-mm 40` | Camera report only, any use |
| `python -m vision.preview --source 0` | Live preview only, for aiming |
| `python -m vision.recorder --source 0` | Record a session, any use |
| `python -m vision.markers` | Printable ArUco markers |
| `python -m pytest vision spirit_island` | Run the tests (no camera needed) |

`--source` accepts a camera index, a video file, or a stream URL such as
`http://localhost:8080/video`.
