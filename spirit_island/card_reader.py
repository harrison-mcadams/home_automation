"""Read an invader card held up under the board camera.

The card faces (assets/components/invader/<stage>_<code>.jpg, from the Tabletop Simulator
mod) are matched against a camera frame with SIFT features and a RANSAC homography. A
card is read when one card's matches clearly beat every other card's. Cards that share a
terrain code (the Stage I and Stage II "J") count as one answer.

The scanner runs only while someone asks for it (the explore steps), on frames from the
live preview server, so it costs nothing the rest of the game.
"""

from __future__ import annotations

import threading
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

CARD_DIR = Path(__file__).resolve().parent / "assets" / "components" / "invader"
WORK_SIDE = 1400          # frames are shrunk to this before matching
MIN_INLIERS = 13          # matches agreeing on one card shape
LEAD = 1.6                # ... and this many times more than the best other card


class CardReader:
    def __init__(self, card_dir: Path = CARD_DIR):
        self.sift = cv2.SIFT_create(3000)
        self.matcher = cv2.BFMatcher()
        self.cards = []
        for path in sorted(Path(card_dir).glob("*.jpg")):
            stage, code = path.stem.split("_", 1)
            img = cv2.imread(str(path))
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            kp, des = self.sift.detectAndCompute(gray, None)
            if des is not None:
                self.cards.append({"code": code, "stage": int(stage), "kp": kp, "des": des,
                                   "size": (img.shape[1], img.shape[0]), "colours": _half_colours(img)})

    def read(self, frame: np.ndarray) -> dict:
        """Best reading over two scales: a card held close reads well small, a card lying
        far off needs the full resolution."""
        best = None
        for side in (1600, 3200):
            r = self._read(frame, side)
            if r.get("card"):
                return r
            if best is None or max(r.get("scores", {}).values() or [0]) > max(best.get("scores", {}).values() or [0]):
                best = r
            if max(frame.shape[:2]) <= side:
                break
        return best

    def _read(self, frame: np.ndarray, work_side: int) -> dict:
        k = min(1.0, work_side / max(frame.shape[:2]))
        small = cv2.resize(frame, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else frame
        kp, des = self.sift.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), None)
        if des is None or len(kp) < 10:
            return {"card": None, "why": "nothing to match in the picture"}
        results = []
        for c in self.cards:
            pairs = self.matcher.knnMatch(c["des"], des, k=2)
            good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
            if len(good) < 8:
                results.append((0, c, None))
                continue
            src = np.float32([c["kp"][m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst = np.float32([kp[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 6)
            n = int(inl.sum()) if inl is not None else 0
            if n and len(c["code"]) == 2:
                # Two-terrain cards share a half with other cards (W+S and W+M both have the
                # wetland half): both halves must match.
                ys = src.reshape(-1, 2)[inl.ravel() > 0][:, 1]
                half = c["size"][1] / 2
                n = 2 * min(int((ys < half).sum()), int((ys >= half).sum()))
            quad = None
            if H is not None:
                w, h = c["size"]
                corners = cv2.perspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2), H)
                quad = (corners.reshape(-1, 2) / k).tolist()
                if not _plausible(corners.reshape(-1, 2), small.shape):
                    n = 0
            if n and H is not None:
                # The features can line up by chance on similar textures; the card's colours
                # (green jungle, pale wetland, orange sands, grey mountain) must agree too.
                w, h = c["size"]
                seen = cv2.warpPerspective(small, np.linalg.inv(H), (w, h))
                if _colour_distance(_half_colours(seen), c["colours"]) > 28:
                    n = 0
            results.append((n, c, quad))
        best_by_code: dict = {}
        for n, c, quad in results:
            if n > best_by_code.get(c["code"], (0,))[0]:
                best_by_code[c["code"]] = (n, c, quad)
        ranked = sorted(best_by_code.values(), key=lambda r: -r[0])
        scores = {r[1]["code"]: r[0] for r in ranked}
        if not ranked or ranked[0][0] == 0:
            return {"card": None, "scores": scores, "why": "no invader card in view"}
        n, c, quad = ranked[0]
        other = ranked[1][0] if len(ranked) > 1 else 0
        if n < MIN_INLIERS:
            return {"card": None, "scores": scores, "quad": quad, "why": "a card may be there, but too unclear to read"}
        if n < LEAD * max(1, other):
            return {"card": None, "scores": scores, "quad": quad,
                    "why": f"unsure between {c['code']} and {ranked[1][1]['code']}"}
        return {"card": c["code"], "stage": c["stage"], "score": n, "scores": scores, "quad": quad,
                "why": f"{n} matching features"}


def _half_colours(img: np.ndarray) -> np.ndarray:
    """Mean Lab colour (a, b, and lightness) of the inner top and bottom halves of a card."""
    h, w = img.shape[:2]
    lab = cv2.cvtColor(cv2.resize(img, (60, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2LAB).astype(np.float32)
    top, bottom = lab[12:40, 10:50], lab[50:78, 10:50]
    return np.array([top.reshape(-1, 3).mean(0), bottom.reshape(-1, 3).mean(0)])


def _colour_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Worst half's colour difference, ignoring an overall brightness shift (the room light)."""
    shift = (a[:, 0] - b[:, 0]).mean()
    d = a.copy()
    d[:, 0] -= shift
    return float(np.max(np.linalg.norm((d - b) * np.array([0.5, 1, 1]), axis=1)))


def _plausible(quad: np.ndarray, shape) -> bool:
    """The card outline must be a convex, card-shaped quad of a sensible size."""
    if not cv2.isContourConvex(quad.astype(np.float32)):
        return False
    area = cv2.contourArea(quad.astype(np.float32))
    frame = shape[0] * shape[1]
    if not (0.003 * frame < area < 0.6 * frame):
        return False
    sides = [np.linalg.norm(quad[i] - quad[(i + 1) % 4]) for i in range(4)]
    return max(sides) < 4 * min(sides)


class CardScanner:
    """Reads the card in view every second or so while active; stops by itself after a while."""

    def __init__(self, snapshot_url: str, on_change=None, active_for: float = 90.0):
        self.url = snapshot_url
        self.on_change = on_change
        self.active_for = active_for
        self.until = 0.0
        self.state: dict = {"active": False}
        self.jpeg = b""
        self.lock = threading.Lock()
        self.reader = None
        self.recent: list = []
        self._thread = None

    def start(self):
        self.until = time.time() + self.active_for
        with self.lock:
            self.recent = []
            self.state = {"active": True, "card": None, "why": "starting the camera..."}
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True, name="card-scanner")
            self._thread.start()
        self._changed()

    def stop(self):
        self.until = 0
        with self.lock:
            self.state = {"active": False}
        self._changed()

    def public(self) -> dict:
        with self.lock:
            return dict(self.state)

    def _changed(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception as e:  # never let a listener kill the scanner
                print(f"card scanner listener failed: {e}")

    def _run(self):
        if self.reader is None:
            self.reader = CardReader()
        while time.time() < self.until:
            started = time.time()
            try:
                with urllib.request.urlopen(self.url, timeout=5) as r:
                    data = r.read()
                frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                result = self.reader.read(frame)
                # A reading must repeat before it counts, so a card being moved into place
                # doesn't flash a wrong answer.
                self.recent = (self.recent + [result.get("card")])[-3:]
                steady = result.get("card") and self.recent.count(result["card"]) >= 2
                picture = frame.copy()
                if result.get("quad"):
                    colour = (90, 220, 120) if steady else (60, 200, 255)
                    cv2.polylines(picture, [np.int32(result["quad"])], True, colour, max(4, frame.shape[1] // 300))
                k = 960 / max(picture.shape[:2])
                ok, buf = cv2.imencode(".jpg", cv2.resize(picture, None, fx=k, fy=k), [cv2.IMWRITE_JPEG_QUALITY, 80])
                with self.lock:
                    if ok:
                        self.jpeg = buf.tobytes()
                    self.state = {"active": True, "card": result.get("card") if steady else None,
                                  "seen": result.get("card"), "stage": result.get("stage"),
                                  "why": result.get("why"), "stamp": time.time()}
            except Exception as e:  # camera hiccup: say so and keep trying
                with self.lock:
                    self.state = {"active": True, "card": None, "why": f"camera not reachable ({type(e).__name__})"}
            self._changed()
            time.sleep(max(0.2, 1.0 - (time.time() - started)))
        with self.lock:
            self.state = {"active": False}
        self._changed()
