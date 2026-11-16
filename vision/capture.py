"""Camera-agnostic threaded capture.

A generalised version of the ThreadedCamera in gesture_controller/main.py:
a background thread keeps only the newest frame, so consumers never read a
stale, buffered image. It works with any source OpenCV can open: a device
index (USB webcam), a video file (for replaying recordings), or a network
stream URL (for example an old phone running an IP Webcam style app). A
separate `still_url` can point at the same camera's full-resolution photo
endpoint.

Nothing here assumes a resolution. You may *request* one, but the size that
counts is the size of the frames that actually arrive, which is what
`Camera.width` / `Camera.height` report.
"""

from __future__ import annotations

import platform
import threading
import time
from dataclasses import dataclass
from typing import Optional, Union

import cv2
import numpy as np

Source = Union[int, str]


def parse_source(value: Union[int, str]) -> Source:
    """Turn a CLI value into a capture source: "0" -> 0, anything else unchanged."""
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text) if text.isdigit() else text


def _is_device(source: Source) -> bool:
    return isinstance(source, int)


def _is_stream(source: Source) -> bool:
    """A network stream, e.g. a phone running IP Webcam: http://<phone>:8080/video"""
    return isinstance(source, str) and "://" in source


def _is_live(source: Source) -> bool:
    """Live sources reconnect when they drop; files simply end."""
    return _is_device(source) or _is_stream(source)


def fetch_still(url: str, timeout: float = 10.0) -> np.ndarray:
    """Download one full-resolution still from a camera's photo endpoint.

    IP Webcam style phone apps serve the low-resolution video at /video and a
    full-sensor photo at /photo.jpg (or the current video frame at /shot.jpg),
    so the pipeline can watch the cheap video for stillness and fetch a sharp
    still only when it needs to read the table.
    """
    import base64
    import urllib.parse
    import urllib.request

    # urllib ignores user:password@ in a URL, so turn it into a Basic auth header
    # (IP Webcam's optional login uses Basic auth).
    parts = urllib.parse.urlsplit(url)
    request = urllib.request.Request(url)
    if parts.username:
        clean = parts._replace(netloc=parts.hostname + (f":{parts.port}" if parts.port else ""))
        request = urllib.request.Request(urllib.parse.urlunsplit(clean))
        user = urllib.parse.unquote(parts.username)
        password = urllib.parse.unquote(parts.password or "")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"{redact(url)} did not return a decodable image")
    return image


def with_credentials(url: str, user: Optional[str], password: Optional[str]) -> str:
    """Put user:password into a URL (OpenCV's stream reader understands this form)."""
    if not user:
        return url
    import urllib.parse

    parts = urllib.parse.urlsplit(url)
    auth = urllib.parse.quote(user, safe="") + ":" + urllib.parse.quote(password or "", safe="")
    return urllib.parse.urlunsplit(parts._replace(netloc=f"{auth}@{parts.netloc.split('@')[-1]}"))


def redact(value):
    """Hide any password in a URL before it is printed or saved to a report."""
    if not isinstance(value, str) or "@" not in value or "://" not in value:
        return value
    scheme, rest = value.split("://", 1)
    netloc, sep, path = rest.partition("/")
    if "@" not in netloc:
        return value
    return f"{scheme}://***@{netloc.rsplit('@', 1)[1]}{sep}{path}"


_ROTATIONS = {
    0: None,
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def _rotate(image: np.ndarray, degrees: int) -> np.ndarray:
    code = _ROTATIONS[degrees % 360]
    return image if code is None else cv2.rotate(image, code)


def _default_backend(source: Source) -> int:
    """Pick the native backend for webcams; let OpenCV choose for files/URLs."""
    if not _is_device(source):
        return cv2.CAP_ANY
    system = platform.system()
    if system == "Darwin":
        return cv2.CAP_AVFOUNDATION
    if system == "Linux":
        return cv2.CAP_V4L2
    if system == "Windows":
        return cv2.CAP_DSHOW
    return cv2.CAP_ANY


def open_capture(
    source: Source,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: Optional[float] = None,
    fourcc: Optional[str] = None,
    backend: Optional[int] = None,
) -> cv2.VideoCapture:
    """Open a cv2.VideoCapture and *request* settings. Returns it even if not opened."""
    backend = _default_backend(source) if backend is None else backend
    cap = cv2.VideoCapture(source, backend)
    if not cap.isOpened() and backend != cv2.CAP_ANY:
        cap = cv2.VideoCapture(source)
    if cap.isOpened() and _is_device(source):
        if fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        if width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if fps:
            cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


@dataclass
class FramePacket:
    """One captured frame plus when it arrived and its sequence number."""

    image: np.ndarray
    timestamp: float  # time.time() when the frame was read
    index: int  # 0, 1, 2 ... counts frames read since the camera was opened


class Camera:
    """Threaded "latest frame" reader for any OpenCV source.

    Usage:
        with Camera(0, width=1920, height=1080) as cam:
            packet = cam.wait_for_frame()
            print(cam.width, cam.height)  # what the camera actually delivers

    For video files, frames are paced to the file's own frame rate when
    `pace_files` is true, so a replayed recording behaves like a live camera.
    """

    def __init__(
        self,
        source: Source = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
        fourcc: Optional[str] = None,
        backend: Optional[int] = None,
        pace_files: bool = True,
        reconnect_delay: float = 2.0,
        rotate: int = 0,
        still_url: Optional[str] = None,
    ):
        self.source = parse_source(source)
        self.still_url = still_url
        self.requested = {"width": width, "height": height, "fps": fps, "fourcc": fourcc}
        self.backend = backend
        self.pace_files = pace_files
        self.reconnect_delay = reconnect_delay
        if rotate % 360 not in _ROTATIONS:
            raise ValueError("rotate must be 0, 90, 180 or 270 (degrees clockwise)")
        self.rotate = rotate % 360
        self._distinct = 0  # frames whose pixels differ from the previous one
        self._last_thumb = None

        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()
        self._new_frame = threading.Condition(self._lock)
        self._latest: Optional[FramePacket] = None
        self._count = 0
        self._stopped = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.ended = False  # True when a file source runs out of frames
        self.reported_fps: float = 0.0
        self.backend_name: str = ""

    # -- lifecycle ---------------------------------------------------------

    def _open(self) -> bool:
        self._cap = open_capture(self.source, backend=self.backend, **self.requested)
        if not self._cap.isOpened():
            return False
        self.reported_fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)
        try:
            self.backend_name = self._cap.getBackendName()
        except cv2.error:
            self.backend_name = "unknown"
        return True

    def start(self, first_frame_timeout: float = 10.0) -> "Camera":
        if not self._open():
            raise RuntimeError(
                f"Could not open camera source {redact(self.source)!r}. "
                "Run `python -m vision.probe --list` to see which cameras exist."
                + (
                    " On macOS, also check System Settings > Privacy & Security > Camera "
                    "for the app you are running this from (Terminal, iTerm, sshd)."
                    if platform.system() == "Darwin" and _is_device(self.source)
                    else ""
                )
            )
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run, name="camera-reader", daemon=True)
        self._thread.start()
        if self.wait_for_frame(timeout=first_frame_timeout) is None:
            self.stop()
            raise RuntimeError(f"Camera {redact(self.source)!r} opened but delivered no frames.")
        return self

    def stop(self) -> None:
        self._stopped.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "Camera":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- reader thread -----------------------------------------------------

    def _run(self) -> None:
        file_interval = 0.0
        if not _is_live(self.source) and self.pace_files and self.reported_fps > 0:
            file_interval = 1.0 / self.reported_fps
        next_due = time.monotonic()

        while not self._stopped.is_set():
            ok, image = self._cap.read() if self._cap is not None else (False, None)
            if not ok or image is None:
                if not _is_live(self.source):
                    self.ended = True  # end of a file; nothing to reconnect to
                    with self._new_frame:
                        self._new_frame.notify_all()
                    return
                self._reconnect()
                continue

            if file_interval:
                next_due += file_interval
                delay = next_due - time.monotonic()
                if delay > 0:
                    time.sleep(delay)

            image = _rotate(image, self.rotate)
            # Some network MJPEG readers hand back the same picture more than once;
            # count only frames that actually changed, for an honest frame rate.
            thumb = cv2.resize(image, (64, 36), interpolation=cv2.INTER_AREA)
            if self._last_thumb is None or cv2.absdiff(thumb, self._last_thumb).max() > 0:
                self._distinct += 1
            self._last_thumb = thumb
            packet = FramePacket(image=image, timestamp=time.time(), index=self._count)
            with self._new_frame:
                self._latest = packet
                self._count += 1
                self._new_frame.notify_all()

    def _reconnect(self) -> None:
        print(f"[vision] Camera {redact(self.source)!r} stopped delivering frames, reconnecting...")
        if self._cap is not None:
            self._cap.release()
        while not self._stopped.is_set():
            time.sleep(self.reconnect_delay)
            if self._open():
                print("[vision] Camera reconnected.")
                return

    # -- consumer API ------------------------------------------------------

    def read(self) -> Optional[FramePacket]:
        """The newest frame, or None if nothing has arrived yet. Never blocks."""
        with self._lock:
            return self._latest

    def wait_for_frame(self, after_index: int = -1, timeout: float = 5.0) -> Optional[FramePacket]:
        """Block until a frame newer than `after_index` arrives (or timeout / end of file)."""
        deadline = time.monotonic() + timeout
        with self._new_frame:
            while self._latest is None or self._latest.index <= after_index:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self.ended:
                    return None
                self._new_frame.wait(remaining)
            return self._latest

    def grab_still(self) -> np.ndarray:
        """A full-resolution still from `still_url` if set, else the newest video frame."""
        if self.still_url:
            return _rotate(fetch_still(self.still_url), self.rotate)
        packet = self.read()
        if packet is None:
            raise RuntimeError("No frame available yet")
        return packet.image

    @property
    def distinct_frames(self) -> int:
        """Frames read whose pixels changed from the previous frame."""
        with self._lock:
            return self._distinct

    @property
    def frames_read(self) -> int:
        with self._lock:
            return self._count

    @property
    def width(self) -> int:
        packet = self.read()
        return int(packet.image.shape[1]) if packet is not None else 0

    @property
    def height(self) -> int:
        packet = self.read()
        return int(packet.image.shape[0]) if packet is not None else 0

    def describe(self) -> dict:
        """Facts about the open camera, for reports and recording metadata."""
        return {
            "source": redact(self.source),
            "backend": self.backend_name,
            "requested": self.requested,
            "delivered_width": self.width,
            "delivered_height": self.height,
            "driver_reported_fps": round(self.reported_fps, 2),
            "still_url": redact(self.still_url),
            "rotate": self.rotate,
        }


def list_cameras(max_index: int = 6) -> list[dict]:
    """Try device indexes 0..max_index-1 and report the ones that deliver a frame."""
    found = []
    previous = cv2.utils.logging.getLogLevel()
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)  # missing indexes are expected
    try:
        for index in range(max_index):
            _try_index(index, found)
    finally:
        cv2.utils.logging.setLogLevel(previous)
    return found


def _try_index(index: int, found: list) -> None:
    cap = open_capture(index)
    try:
        if not cap.isOpened():
            return
        image = None
        for _ in range(5):  # some cameras return a few empty frames while waking
            ok, image = cap.read()
            if ok and image is not None:
                break
            image = None
            time.sleep(0.1)
        if image is not None:
            found.append(
                {
                    "index": index,
                    "default_width": int(image.shape[1]),
                    "default_height": int(image.shape[0]),
                    "backend": cap.getBackendName(),
                }
            )
    finally:
        cap.release()
