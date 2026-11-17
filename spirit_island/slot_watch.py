"""Watch the invader board during the explore steps and reveal the card turned over.

While the game is on First explore or Explore, the newest camera photo is read every
couple of seconds (invader_board.py). When the Explore space shows the same face-up card
twice in a row and the game hasn't got a card there yet, the card is revealed in the
game (logged as the camera; Undo and tapping still work). A small picture of the invader
board with each space outlined and labelled is kept for the screens.
"""

from __future__ import annotations

import threading
import time
import urllib.request

import cv2
import numpy as np

WATCH_STEPS = ("setup.first_explore", "invader.explore")
COLOURS = {"explore": (120, 220, 90), "build": (60, 200, 255), "ravage": (90, 90, 255), "discard": (180, 180, 180)}


class SlotWatch:
    def __init__(self, store, snapshot_url: str, every: float = 2.0):
        self.store = store
        self.url = snapshot_url
        self.every = every
        self.reader = None
        self.state: dict = {"active": False}
        self.jpeg = b""
        self.lock = threading.Lock()
        self.recent: list = []
        self._thread = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="slot-watch")
            self._thread.start()

    def public(self) -> dict:
        with self.lock:
            return dict(self.state)

    def _run(self):
        while True:
            st = self.store.game.state
            step = st.get("step")
            # Read the invader board all game long (for the screens); only the explore
            # steps reveal a card by themselves.
            if step in WATCH_STEPS or st.get("status") == "playing":
                try:
                    self._once()
                except Exception as e:  # camera hiccup: say so, try again
                    with self.lock:
                        self.state = {"active": True, "found": False, "why": f"camera: {type(e).__name__}"}
                    self.store.broadcast(self.store.snapshot())
            elif self.state.get("active"):
                with self.lock:
                    self.state, self.recent = {"active": False}, []
                self.store.broadcast(self.store.snapshot())
            time.sleep(self.every)

    def _once(self):
        if self.reader is None:
            from .invader_board import InvaderBoardReader
            self.reader = InvaderBoardReader()
        with urllib.request.urlopen(self.url, timeout=6) as r:
            frame = cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
        result = self.reader.read(frame)
        if not result.get("found"):
            with self.lock:
                self.state = {"active": True, "found": False,
                              "why": "looking for the invader board (is it in the camera's view?)"}
            self.store.broadcast(self.store.snapshot())
            return
        slots = {k: v for k, v in result["slots"].items()}
        explore = slots.get("explore", {})
        seen = explore.get("card") if explore.get("kind") == "face" and explore.get("margin", 0) >= 2 else None
        self.recent = (self.recent + [seen])[-2:]
        self._picture(frame, result)
        with self.lock:
            self.state = {"active": True, "found": True, "stamp": time.time(),
                          "slots": {k: (v.get("card") if v.get("kind") == "face" else v.get("kind")) for k, v in slots.items()},
                          "explore_seen": seen}
        game = self.store.game.state
        # Advance step: once the cards are seen one space left (twice running), move on.
        if game.get("step") == "invader.advance":
            have = game["invaders"]["slots"]
            read = self.state["slots"]
            moved = (read.get("ravage") == have.get("build") and read.get("build") == have.get("explore")
                     and (have.get("build") or have.get("explore")))
            self.advanced = (getattr(self, "advanced", 0) + 1) if moved else 0
            if self.advanced >= 2:
                self.advanced = 0
                try:
                    self.store.dispatch({"type": "next", "screen": True}, "camera")
                    return
                except Exception as e:
                    with self.lock:
                        self.state["why"] = str(e)
        if seen and len(self.recent) == 2 and self.recent[0] == seen and game["invaders"]["slots"]["explore"] is None                 and game.get("step") in WATCH_STEPS:
            try:
                self.store.dispatch({"type": "reveal_invader", "card": seen}, "camera")
                return
            except Exception as e:  # e.g. not a card that can come next: leave it to a tap
                with self.lock:
                    self.state["why"] = str(e)
        self.store.broadcast(self.store.snapshot())

    def _picture(self, frame, result):
        """The invader board's card row seen straight on, the way it's printed (Discard,
        Ravage, Build, Explore from left to right), each space outlined and named."""
        from .invader_board import SLOTS
        aw, ah = result["art_size"]
        x0, y0, x1, y1 = 0.24 * aw, 0.69 * ah, 0.995 * aw, 0.965 * ah
        W = 1200
        Hh = int(W * (y1 - y0) / (x1 - x0))
        to_strip = np.float32([[W / (x1 - x0), 0, -x0 * W / (x1 - x0)], [0, Hh / (y1 - y0), -y0 * Hh / (y1 - y0)], [0, 0, 1]])
        M = to_strip @ np.linalg.inv(result["H"])
        strip = cv2.warpPerspective(frame, M, (W, Hh))
        for slot, (x, y, w, h) in SLOTS.items():
            box = np.float32([[x * aw, y * ah], [(x + w) * aw, (y + h) * ah]])
            (bx0, by0), (bx1, by1) = cv2.perspectiveTransform(box.reshape(-1, 1, 2), to_strip).reshape(-1, 2)
            cv2.rectangle(strip, (int(bx0), int(by0)), (int(bx1), int(by1)), COLOURS[slot], 5)
            info = result["slots"].get(slot)
            text = slot.title() if not info else f"{slot.title()}: {info.get('card') or info.get('kind')}"
            cv2.putText(strip, text, (int(bx0) + 6, int(by1) - 12), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 6, cv2.LINE_AA)
            cv2.putText(strip, text, (int(bx0) + 6, int(by1) - 12), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", strip, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if ok:
            self.jpeg = buf.tobytes()
