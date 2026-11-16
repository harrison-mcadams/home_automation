"""Link between the game dashboard and the live board camera page (board_view.py, port 8091).

The board page already does the hard part: it lines each photo up with a reference,
finds the pieces, gives each a land, and only changes its reading once most recent
photos agree (and holds it while a hand is over the board). This module just reads
that settled reading over HTTP, turns it into the game's piece names and land ids,
and compares it with what the game is tracking.

It never talks to the camera itself, so it can't disturb the board page, and if the
board page is not running the dashboard carries on without it.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

# Detector piece type -> game piece name. Anything else (energy tokens, unknown) is ignored.
KIND_TO_PIECE = {
    "explorer": "explorers",
    "town": "towns",
    "city": "cities",
    "dahan": "dahan",
    "blight": "blight",
    "presence": "presence",
}
TRACKED = ("explorers", "towns", "cities", "dahan", "blight", "presence")


def to_game_counts(board_state: dict | None, board: str) -> dict:
    """{"2": {"city": 1, "presence (yellow)": 1}} -> {"C2": {"cities": 1, "presence": 1, ...}}.

    Pieces in the ocean or with no land are left out. Every land the camera covers
    (1 to 8) gets an entry, so a land the camera sees as empty reads as zeros.
    """
    out = {f"{board}{n}": {p: 0 for p in TRACKED} for n in range(1, 9)}
    for land, kinds in (board_state or {}).items():
        lid = f"{board}{land}"
        if lid not in out:
            continue
        for kind, n in kinds.items():
            piece = KIND_TO_PIECE.get(kind.split(" (")[0])
            if piece:
                out[lid][piece] += int(n)
    return out


def differences(seen: dict, lands: dict) -> list[dict]:
    """Lands where the camera and the tracked game disagree."""
    diffs = []
    for lid, counts in seen.items():
        tracked = lands.get(lid)
        if tracked is None:
            continue
        delta = {p: counts[p] - tracked.get(p, 0) for p in TRACKED if counts[p] != tracked.get(p, 0)}
        if delta:
            diffs.append({"land": lid, "camera": counts,
                          "tracked": {p: tracked.get(p, 0) for p in TRACKED}, "delta": delta})
    return diffs


class VisionLink:
    """Polls the board page and keeps the latest settled reading."""

    def __init__(self, url: str = "http://localhost:8091", every: float = 3.0, on_change=None, board_map=None):
        self.url = url.rstrip("/")
        self.map = board_map       # BoardMap for the drawn board view, or None
        self.pieces: list = []     # piece positions from the last settled photo
        self.view = "board" if board_map is not None else "photo"  # what the screens show: photo | board
        self.every = every
        self.on_change = on_change  # called with no args when a new reading arrives or the link drops
        self.lock = threading.Lock()
        self.raw: dict | None = None
        self.error: str | None = "not checked yet"
        self.last_ok = 0.0
        self.board = None          # which game board the camera is pointed at (None = auto)
        self.auto = False          # copy settled camera counts into the game automatically
        self.stopping = threading.Event()
        self._thread = None

    # -- polling --
    def fetch_once(self) -> bool:
        """Read the board page once; returns True if what we show changed."""
        try:
            with urllib.request.urlopen(self.url + "/state.json", timeout=4) as r:
                data = json.loads(r.read().decode("utf-8"))
            with self.lock:
                changed = (self.error is not None or self.raw is None
                           or data.get("stamp") != self.raw.get("stamp"))
                self.raw, self.error, self.last_ok = data, None, time.time()
                # Only move the drawn pieces when the reading has settled, so a hand over
                # the board or a half-moved piece doesn't make them jump about.
                if data.get("status") == "ok" and data.get("settled") == "settled" and self.map is not None:
                    self.pieces = self.map.place(data.get("pieces"))
            return changed
        except (OSError, ValueError, urllib.error.URLError) as e:
            with self.lock:
                changed = self.error is None
                self.error = f"board camera page not reachable at {self.url} ({type(e).__name__})"
            return changed

    def run(self):
        while not self.stopping.is_set():
            if self.fetch_once() and self.on_change:
                try:
                    self.on_change()
                except Exception as e:  # never let a listener kill the poller
                    print(f"vision link listener failed: {e}")
            self.stopping.wait(self.every)

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self.run, daemon=True, name="vision-link")
            self._thread.start()

    def photo(self) -> bytes | None:
        try:
            with urllib.request.urlopen(self.url + "/board.jpg", timeout=6) as r:
                return r.read()
        except (OSError, urllib.error.URLError):
            return None

    # -- reading --
    def camera_board(self, state: dict) -> str | None:
        boards = state.get("boards") or []
        if self.board and self.board in boards:
            return self.board
        return "C" if "C" in boards else (boards[0] if boards else None)

    def settled(self) -> bool:
        with self.lock:
            raw = self.raw or {}
            return self.error is None and raw.get("status") == "ok" and raw.get("settled") == "settled"

    def seen(self, state: dict) -> dict | None:
        board = self.camera_board(state)
        with self.lock:
            raw = self.raw
        if raw is None or board is None or raw.get("board_state") is None:
            return None
        return to_game_counts(raw["board_state"], board)

    def public(self, state: dict) -> dict:
        with self.lock:
            raw = dict(self.raw or {})
            error = self.error
            age = round(time.time() - self.last_ok) if self.last_ok else None
        seen = self.seen(state)
        status = raw.get("settled") or raw.get("status") or ""
        return {
            "url": self.url,
            "connected": error is None,
            "error": error,
            "stamp": raw.get("stamp"),
            "age": age,
            "status": status,
            "settled": error is None and raw.get("status") == "ok" and raw.get("settled") == "settled",
            "board": self.camera_board(state),
            "auto": self.auto,
            "pieces_seen": len(raw.get("pieces") or []),
            "has_map": self.map is not None,
            "view": self.view,
            "pieces": list(self.pieces),
            "seen": seen,
            "diffs": differences(seen, state.get("lands", {})) if seen else [],
        }
