"""A live web page of the board: the latest photo with each piece labelled, and a count per land.

    python -m spirit_island.board_view --phone --reference <reference folder>
    # then open http://<this computer>:8091 on a phone, tablet or TV browser

Every few seconds it takes a full-resolution photo, finds the pieces (see detect.py)
and updates the page. The counts only change once most recent photos agree, and are
held while a hand is over the board. It only reads from the camera, so it can run next to the
live preview. `--image a.jpg --image b.jpg` cycles through saved photos instead,
for trying it without the camera.
"""

from __future__ import annotations

import argparse
import html
import json
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2

from spirit_island import detect
from spirit_island.perception import lands as land_map
from spirit_island.perception.memory import PieceMemory

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spirit Island board</title>
<style>
 body {{ margin: 0; font: 16px system-ui, sans-serif; background: #15171a; color: #e8e6e1; }}
 main {{ display: flex; flex-wrap: wrap; gap: 16px; padding: 16px; }}
 img {{ max-width: 100%; max-height: 85vh; border-radius: 6px; flex: 1 1 600px; object-fit: contain; }}
 section {{ flex: 0 1 320px; }}
 h1 {{ font-size: 20px; margin: 0 0 8px; }}
 .meta {{ color: #9a978f; font-size: 13px; margin-bottom: 12px; }}
 table {{ border-collapse: collapse; width: 100%; }}
 td {{ padding: 6px 4px; border-bottom: 1px solid #2c2f34; vertical-align: top; }}
 td:first-child {{ font-weight: 600; white-space: nowrap; width: 5em; }}
 .warn {{ color: #f0b35a; }}
</style></head>
<body><main>
<img id="photo" src="/board.jpg?{stamp}" alt="Latest photo of the board, pieces labelled">
<section>
 <h1>Board state</h1>
 <div class="meta" id="meta">{meta}</div>
 <table id="lands">{rows}</table>
</section>
</main>
<script>
let last = "{stamp}";
async function poll() {{
  try {{
    const r = await fetch("/state.json", {{cache: "no-store"}});
    const s = await r.json();
    if (s.stamp && s.stamp !== last) {{ location.reload(); return; }}
  }} catch (e) {{}}
  setTimeout(poll, 2000);
}}
setTimeout(poll, 2000);
</script>
</body></html>"""


def land_rows(result: dict) -> str:
    state = result.get("board_state") or {}
    if not state:
        return "<tr><td colspan=2>No pieces found.</td></tr>"
    rows = []
    for land, counts in state.items():
        name = "Ocean" if land == "ocean" else ("Unknown" if land == "?" else f"Land {land}")
        what = ", ".join(f"{n} {kind}" for kind, n in counts.items())
        rows.append(f"<tr><td>{html.escape(name)}</td><td>{html.escape(what)}</td></tr>")
    return "".join(rows)


def _overlap(a, b) -> float:
    """Intersection over union of two [x, y, w, h] boxes."""
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0


class BoardView:
    def __init__(self, reference_dir: Path, grab, every: float = 5.0, max_side: int = 1600,
                 confirm: int = 3, save_dir: Path | None = None):
        # One reference folder, or a folder of them named by board letter (A, B, C, D):
        # then the page follows whichever board is under the camera.
        reference_dir = Path(reference_dir)
        if (reference_dir / "reference.jpg").exists():
            folders = {self._letter(reference_dir): reference_dir}
        else:
            folders = {d.name: d for d in sorted(reference_dir.iterdir()) if (d / "reference.jpg").exists()}
        if not folders:
            raise SystemExit(f"No reference in {reference_dir}.")
        self.boards = {letter: self._load(d) for letter, d in folders.items()}
        self.misses = 0
        self.grab = grab
        self.every = every
        self.max_side = max_side
        self.lock = threading.Lock()
        self.jpeg = b""
        self.state: dict = {"stamp": "", "status": "starting"}
        self.stopping = threading.Event()
        self.confirm = confirm
        self.stable: dict | None = None
        self.window = max(confirm, 2 * confirm - 1)
        self.recent: list[str] = []
        self.save_dir = save_dir
        self.last_seen: dict | None = None
        self.last_large: list = []
        self.use(next(iter(self.boards)))

    @staticmethod
    def _letter(folder: Path) -> str:
        meta = folder / "reference.json"
        letter = json.loads(meta.read_text()).get("letter") if meta.exists() else None
        return letter or folder.name

    @staticmethod
    def _load(folder: Path) -> dict:
        reference = cv2.imread(str(folder / "reference.jpg"))
        mask = cv2.imread(str(folder / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
        if reference is None or mask is None:
            raise SystemExit(f"No reference in {folder}.")
        labels, names = land_map.load(folder)
        lands = (labels, names) if labels is not None else None
        meta = folder / "reference.json"
        rotate = json.loads(meta.read_text()).get("rotate", 0) if meta.exists() else 0
        # Remember pieces between photos so changing light can't make them vanish.
        return {"reference": reference, "mask": mask, "lands": lands, "rotate": rotate,
                "memory": PieceMemory(reference, lands)}

    def use(self, letter: str) -> None:
        """Switch to another board's reference; its readings start afresh."""
        b = self.boards[letter]
        self.board = letter
        self.reference, self.board_mask, self.lands = b["reference"], b["mask"], b["lands"]
        self.rotate, self.memory = b["rotate"], b["memory"]
        self.stable, self.recent, self.last_large, self.misses = None, [], [], 0

    def _other_board(self, image) -> tuple[str, dict] | None:
        """After a couple of photos that don't line up, see if another known board does."""
        for letter, b in self.boards.items():
            if letter == self.board:
                continue
            result = detect.detect_pieces(b["reference"], b["mask"], detect.rotate(image, b["rotate"]),
                                          lands=b["lands"])
            if result["registered"]:
                return letter, result
        return None

    def update_once(self) -> dict:
        started = time.time()
        raw = self.grab()
        image = detect.rotate(raw, self.rotate)
        result = detect.detect_pieces(self.reference, self.board_mask, image, lands=self.lands)
        if result["registered"]:
            self.misses = 0
        elif len(self.boards) > 1:
            self.misses += 1
            if self.misses >= 2:
                other = self._other_board(raw)
                if other:
                    self.use(other[0])
                    image, result = detect.rotate(raw, self.rotate), other[1]
        self.memory.update(result)
        result["board_state"] = detect.board_state(result["pieces"])
        picture = detect.draw_pieces(image, result)
        scale = min(1.0, self.max_side / max(picture.shape[:2]))
        if scale < 1:
            picture = cv2.resize(picture, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", picture, [cv2.IMWRITE_JPEG_QUALITY, 85])
        public = {k: v for k, v in result.items() if not k.startswith("_")}
        public["board"] = self.board
        public["stamp"] = datetime.now().strftime("%H:%M:%S")
        public["seconds"] = round(time.time() - started, 1)
        public["status"] = "ok" if result["registered"] else "could not line up with the reference"
        public["seen"] = public["board_state"]
        public["board_state"], public["settled"] = self.settle(result)
        if self.save_dir is not None and (public["seen"] != self.last_seen or result.get("large_changes")):
            self.keep_photo(image, public)
        self.last_seen = public["seen"]
        with self.lock:
            if ok:
                self.jpeg = buf.tobytes()
            self.state = public
        return public

    def settle(self, result: dict) -> tuple[dict, str]:
        """The board state to show, and why.

        One photo can be wrong: a hand over the board, pieces being moved, or a reading
        right on a threshold that flips between photos. So the page shows the reading that
        most of the last few clear photos agree on (`confirm` of the last `window`), and
        keeps the last settled state otherwise.
        """
        if not result["registered"]:
            return self.stable, "holding: the board is hidden or moved too far to line up (a hand?)"
        large = [c["reference_bbox"] for c in result.get("large_changes") or [] if c.get("reference_bbox")]
        moving = [b for b in large if not any(_overlap(b, o) > 0.3 for o in self.last_large)]
        self.last_large = large
        if moving:
            # Something big appeared or moved since the last photo: a hand, most likely.
            # A big change that stays put (a shadow, a bag next to the board) doesn't hold
            # the reading up; the pieces under it are kept by the piece memory.
            return self.stable, "holding: something large is over the board (a hand?)"
        seen = result["board_state"]
        self.recent = (self.recent + [json.dumps(seen, sort_keys=True)])[-self.window:]
        best = max(set(self.recent), key=self.recent.count)
        if self.stable is None or self.recent.count(best) >= self.confirm:
            self.stable = json.loads(best)
        if seen == self.stable:
            return self.stable, "settled"
        return self.stable, "changing: the latest photo differs, waiting for more to agree"

    def keep_photo(self, image, public: dict) -> None:
        """Save the raw photo when the reading changes, for checking afterwards (newest 60 kept)."""
        self.save_dir.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime("%Y%m%d-%H%M%S")
        cv2.imwrite(str(self.save_dir / f"{name}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        (self.save_dir / f"{name}.json").write_text(json.dumps(public, indent=2))
        photos = sorted(self.save_dir.glob("*.jpg"))
        for old in photos[:-60]:
            old.unlink(missing_ok=True)
            old.with_suffix(".json").unlink(missing_ok=True)

    def run(self) -> None:
        while not self.stopping.is_set():
            started = time.time()
            try:
                self.update_once()
            except Exception as e:  # camera hiccup: keep the last picture, say so, try again
                with self.lock:
                    self.state = {**self.state, "status": f"error: {type(e).__name__}: {e}"}
            self.stopping.wait(max(0.5, self.every - (time.time() - started)))

    def page(self) -> str:
        with self.lock:
            s = dict(self.state)
        meta = f"Updated {s.get('stamp') or '-'}"
        if s.get("seconds") is not None:
            meta += f" (took {s['seconds']} s)"
        if s.get("pieces") is not None:
            meta += f" · {len(s['pieces'])} piece(s)"
        if s.get("status") not in ("ok", None):
            meta += f' · <span class="warn">{html.escape(str(s["status"]))}</span>'
        if s.get("settled") and s["settled"] != "settled":
            meta += f' · <span class="warn">{html.escape(s["settled"])}</span>'
        return PAGE.format(stamp=html.escape(s.get("stamp") or ""), meta=meta, rows=land_rows(s))

    def handler(self):
        view = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, body: bytes, kind: str):
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/":
                    self._send(view.page().encode(), "text/html; charset=utf-8")
                elif path == "/board.jpg":
                    with view.lock:
                        body = view.jpeg
                    if not body:
                        self.send_error(503, "no photo yet")
                        return
                    self._send(body, "image/jpeg")
                elif path == "/state.json":
                    with view.lock:
                        body = json.dumps(view.state).encode()
                    self._send(body, "application/json")
                else:
                    self.send_error(404)

        return Handler


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--phone", nargs="?", const=8080, type=int, metavar="PORT")
    src.add_argument("--image", action="append", help="saved photo(s), cycled in turn")
    p.add_argument("--phone-host")
    p.add_argument("--reference", default=str(detect.DEFAULT_REFERENCE))
    p.add_argument("--every", type=float, default=5.0, help="seconds between photos")
    p.add_argument("--port", type=int, default=8091)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--confirm", type=int, default=3,
                   help="how many of the last 2N-1 photos must agree before the shown state changes")
    p.add_argument("--save", help="folder to keep the raw photo whenever the reading changes")
    args = p.parse_args(argv)

    if args.image:
        images = [cv2.imread(f) for f in args.image]
        if any(i is None for i in images):
            raise SystemExit("Could not read one of the --image files.")
        counter = iter(range(10 ** 9))
        grab = lambda: images[next(counter) % len(images)]  # noqa: E731
    else:
        from vision import phone
        from vision.capture import fetch_still

        url = phone.urls(phone.connect(args.phone, args.phone_host))["photo"]
        grab = lambda: fetch_still(url, timeout=20)  # noqa: E731

    view = BoardView(Path(args.reference), grab, every=args.every, confirm=args.confirm,
                     save_dir=Path(args.save) if args.save else None)
    threading.Thread(target=view.run, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), view.handler())
    print(f"Board page on http://localhost:{args.port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        view.stopping.set()
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
