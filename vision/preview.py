"""Live preview over HTTP, for aiming a camera attached to a headless machine.

    python -m vision.preview --source 0 --port 8090
    python -m vision.preview --phone --max-width 1920 --fps 15     # the phone, TV-sized
    then open the printed http://<this-computer>:8090 address on a phone, laptop or TV browser.

Serves an MJPEG stream (downscaled to keep Wi-Fi happy) with the delivered
resolution and a live sharpness number, so you can adjust the mount and focus
while watching from across the room.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from vision import quality
from vision.capture import Camera, parse_source

PAGE = """<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Camera preview</title>
<style>body{margin:0;background:#111;color:#eee;font:15px system-ui}
img{width:100%;height:auto;display:block}p{margin:8px 12px}</style></head>
<body><img src="/stream.mjpg" alt="live camera">
<p>Full-resolution frame: <a style="color:#9cf" href="/snapshot.jpg">snapshot.jpg</a></p>
</body></html>"""


def lan_ip() -> str:
    """This computer's address on the local network (no traffic is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.0.1", 9))
            return s.getsockname()[0]
    except OSError:
        return "localhost"


class PreviewServer:
    def __init__(self, camera: Camera, port: int = 8090, max_width: int = 1280, fps: float = 8.0):
        self.camera = camera
        self.port = port
        self.max_width = max_width
        self.interval = 1.0 / fps
        self._server: ThreadingHTTPServer | None = None

    def _overlay_jpeg(self) -> bytes | None:
        packet = self.camera.read()
        if packet is None:
            return None
        image = packet.image
        h, w = image.shape[:2]
        text = [f"{w}x{h}", f"sharpness {quality.sharpness(image):.0f}"]
        if w > self.max_width:
            image = cv2.resize(image, (self.max_width, int(h * self.max_width / w)), interpolation=cv2.INTER_AREA)
        image = quality.annotate(image, lines=text)
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else None

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep the console quiet
                pass

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    body = PAGE.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path.startswith("/snapshot.jpg"):
                    packet = server.camera.read()
                    if packet is None:
                        self.send_error(503, "no frame yet")
                        return
                    ok, buf = cv2.imencode(".jpg", packet.image, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    body = buf.tobytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path.startswith("/stream.mjpg"):
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.end_headers()
                    try:
                        while True:
                            jpg = server._overlay_jpeg()
                            if jpg:
                                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                                self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                                self.wfile.write(jpg + b"\r\n")
                            time.sleep(server.interval)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                else:
                    self.send_error(404)

        return Handler

    def start(self) -> "PreviewServer":
        self._server = ThreadingHTTPServer(("0.0.0.0", self.port), self._handler())
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="preview", daemon=True).start()
        print(f"Live preview at http://{lan_ip()}:{self.port}  (or http://{socket.gethostname()}:{self.port})")
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default="0")
    p.add_argument("--phone", nargs="?", const=8080, type=int, metavar="PORT",
                   help="use the Android phone's camera app (Wi-Fi if IPWEBCAM_HOST is set, else USB)")
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270])
    p.add_argument("--max-width", type=int, default=1280, help="downscale the stream to this width (1920 for a TV)")
    p.add_argument("--fps", type=float, default=8.0, help="stream frame rate")
    args = p.parse_args(argv)
    source = args.source
    if args.phone:
        from vision import phone

        source = phone.urls(phone.connect(args.phone))["video"]
    with Camera(parse_source(source), width=args.width, height=args.height, rotate=args.rotate) as cam:
        PreviewServer(cam, port=args.port, max_width=args.max_width, fps=args.fps).start()
        print("Ctrl-C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
