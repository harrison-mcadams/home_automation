"""Use an Android phone, plugged in by USB, as a camera.

    python -m vision.phone                 # forward the phone's camera app to localhost and test it

The phone runs an IP-camera app (for example "IP Webcam"), which serves:
    /video       an MJPEG video stream
    /photo.jpg   a full-resolution photo from the main sensor (autofocused)
    /shot.jpg    the current video frame

Over USB, `adb forward tcp:8080 tcp:8080` makes those appear at
http://localhost:8080 on this computer, with no Wi-Fi involved: steadier, lower
latency, and the phone can charge from the same cable. Works the same on
Windows, macOS and Linux as long as `adb` (Android platform-tools) is installed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from typing import Optional

DEFAULT_PORT = 8080


class PhoneError(RuntimeError):
    pass


def find_adb() -> str:
    adb = shutil.which("adb")
    if not adb:
        raise PhoneError(
            "adb not found. Install Android platform-tools "
            "(https://developer.android.com/tools/releases/platform-tools) and put it on your PATH."
        )
    return adb


def _run(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise PhoneError((result.stderr or result.stdout).strip() or f"{' '.join(args)} failed")
    return result.stdout


def list_devices(adb: Optional[str] = None) -> list[dict]:
    """Phones adb can see, with their state ("device" means ready, "unauthorized" means
    accept the USB-debugging prompt on the phone)."""
    adb = adb or find_adb()
    devices = []
    for line in _run([adb, "devices", "-l"]).splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            extra = dict(p.split(":", 1) for p in parts[2:] if ":" in p)
            devices.append({"serial": parts[0], "state": parts[1], "model": extra.get("model", "")})
    return devices


def forward(port: int = DEFAULT_PORT, serial: Optional[str] = None, adb: Optional[str] = None) -> str:
    """Forward localhost:port to the phone's port. Returns the base URL."""
    adb = adb or find_adb()
    ready = [d for d in list_devices(adb) if d["state"] == "device"]
    if serial:
        ready = [d for d in ready if d["serial"] == serial]
    if not ready:
        raise PhoneError(
            "No phone ready over USB. Plug it in, enable USB debugging "
            "(Settings > System > Developer options), and accept the prompt on the phone."
        )
    if len(ready) > 1 and not serial:
        raise PhoneError(f"More than one phone attached; pass a serial: {[d['serial'] for d in ready]}")
    _run([adb, "-s", ready[0]["serial"], "forward", f"tcp:{port}", f"tcp:{port}"])
    return f"http://localhost:{port}"


def urls(base: str) -> dict:
    return {"video": f"{base}/video", "photo": f"{base}/photo.jpg", "shot": f"{base}/shot.jpg"}


def check(base: str) -> dict:
    """Fetch a video frame and a full-resolution photo; report both sizes and timings."""
    from vision.capture import fetch_still

    out = {}
    for name in ("shot", "photo"):
        t0 = time.monotonic()
        image = fetch_still(urls(base)[name], timeout=20)
        out[name] = {"width": int(image.shape[1]), "height": int(image.shape[0]),
                     "seconds": round(time.monotonic() - t0, 2)}
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="the camera app's port on the phone")
    p.add_argument("--serial", help="which phone, if several are attached")
    args = p.parse_args(argv)
    try:
        base = forward(args.port, args.serial)
        print(f"Phone forwarded to {base}")
        result = check(base)
    except PhoneError as exc:
        print(f"Problem: {exc}")
        return 1
    except Exception as exc:  # camera app not running, wrong port, etc.
        print(f"Forwarded, but the camera app did not answer: {exc}\n"
              "Open the camera app on the phone and start its server, then try again.")
        return 1
    print(f"Video frames:  {result['shot']['width']}x{result['shot']['height']}")
    print(f"Full photos:   {result['photo']['width']}x{result['photo']['height']} "
          f"({result['photo']['seconds']} s each)")
    print("\nUse it with:")
    print(f"  python -m spirit_island.capture_kit --phone")
    print(f"  (or --source {urls(base)['video']} --still-url {urls(base)['photo']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
