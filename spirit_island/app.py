"""Spirit Island dashboard: a phone-friendly guide and tracker for a real table.

Run from the repo root (Windows or macOS):

    python -m spirit_island.app            # then open http://<this-computer>:5055 on a phone

All game changes go through POST /api/action, which the camera pipeline can
call too (with "source": "vision"). Every open page updates live through
server-sent events on /api/events.
"""

import argparse
import json
import os
import queue
import socket
import threading

from flask import Flask, Response, jsonify, render_template, request

from .engine import ActionError, Game, describe, rules
from .engine import game as g
from .vision_link import VisionLink


def load_board_map(path, boards_dir=None):
    """The drawn-board map from the camera's reference folder, or None if it isn't there."""
    if not path:
        return None
    try:
        from pathlib import Path
        from .board_map import BoardMap
        if not (Path(path) / "reference.jpg").exists():  # a folder of boards, one per letter
            return {d.name: BoardMap(d, boards_dir) for d in sorted(Path(path).iterdir())
                    if (d / "lands.json").exists()} or None
        return BoardMap(path, boards_dir)
    except Exception as e:  # missing folder, no OpenCV, ...: the photo view still works
        print(f"No drawn board view ({type(e).__name__}: {e})")
        return None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def load_config():
    cfg = {"host": "0.0.0.0", "port": 5055, "data_dir": "games",
           "board_camera_url": "http://localhost:8091", "public_urls": [],
           "board_reference": "", "board_art_dir": "assets/boards",
           "camera_snapshot_url": "http://localhost:8091/photo.jpg"}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    if not os.path.isabs(cfg["data_dir"]):
        cfg["data_dir"] = os.path.join(BASE_DIR, cfg["data_dir"])
    return cfg


class Store:
    """Holds the one live game, saves it after each change, and fans out updates."""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "current.json")
        self.terrain_path = os.path.join(data_dir, "board_terrains.json")
        self.lock = threading.Lock()
        self.listeners = []
        self.game = self._load()
        self.vision = None  # VisionLink, when the board camera page is linked
        self.cards = None   # CardScanner, reads invader cards held up to the camera

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                return Game(saved["state"], saved.get("history", []))
            except (OSError, ValueError, KeyError) as e:
                print(f"Could not read saved game ({e}); starting fresh.")
        return Game()

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"state": self.game.state, "history": self.game.history}, f)
        os.replace(tmp, self.path)
        # Remember terrain tags per board so they only need entering once.
        known = self.saved_terrains()
        for lid, land in self.game.state["lands"].items():
            if land["terrain"]:
                known[lid] = land["terrain"]
        with open(self.terrain_path, "w", encoding="utf-8") as f:
            json.dump(known, f, indent=1)

    def saved_terrains(self):
        try:
            with open(self.terrain_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def dispatch(self, action, source):
        # Leaving Play powers: pay for the cards the camera sees played.
        if action.get("type") == "next" and self.game.state["step"] == "spirit.powers"                 and getattr(self, "power_watch", None) is not None:
            cost = self.power_watch.public().get("cost") or 0
            if cost:
                try:
                    with self.lock:
                        self.game.dispatch({"type": "energy", "delta": -cost}, source="camera")
                except ActionError:
                    pass
        with self.lock:
            if action.get("type") == "configure":
                # Hand-tagged terrains only fill gaps: the printed boards' own terrains win
                # (old hand tags from before they were known can be wrong).
                printed = rules.default_terrains(rules.BOARDS)
                saved = {k: v for k, v in self.saved_terrains().items() if k not in printed}
                action = {**action, "terrains": {**saved, **(action.get("terrains") or {})}}
            self.game.dispatch(action, source=source)
            self._save()
            payload = self._snapshot()
        self.broadcast(payload)
        return payload

    def _snapshot(self):
        out = snapshot(self.game)
        if self.vision is not None:
            out["vision"] = self.vision.public(self.game.state)
        if self.cards is not None:
            out["card_scan"] = self.cards.public()
        if getattr(self, "slot_watch", None) is not None:
            out["slot_watch"] = self.slot_watch.public()
        if getattr(self, "power_watch", None) is not None:
            out["power_watch"] = self.power_watch.public()
        return out

    def vision_changed(self):
        """Called by the vision link when a new camera reading arrives (or the link drops).

        With auto-sync on, a settled reading that differs from the tracked game is copied
        in (logged as coming from the camera, and Undo-able like any other change).
        """
        v = self.vision
        if v is not None and v.auto and v.settled() and self.game.state["status"] == "playing":
            # Only believable suggestions: held for a few readings, camera not blind,
            # and fitting the step. Unusual ones wait for a tap on the phone.
            diffs = [d for d in v.public(self.game.state)["diffs"]
                     if d["confirmed"] and d["verdict"] in ("expected", "plausible")]
            # Only presence is copied in by itself for now: it's colour-checked and reliable.
            # Other differences wait for a tap (shaded white figures still flicker).
            # Only additions: a disc the camera briefly loses (merged with a piece it touches)
            # must not be taken off the tracker. Removals wait for a tap.
            lands = {d["land"]: {"presence": d["camera"]["presence"]} for d in diffs if d["delta"].get("presence", 0) > 0}
            if lands:
                try:
                    self.dispatch({"type": "observe", "lands": lands}, "camera")
                    self.growth_from_presence()
                    return
                except ActionError as e:
                    print(f"camera sync failed: {e}")
        self.growth_from_presence()
        self.broadcast(self.snapshot())

    def growth_from_presence(self):
        """During Growth, suggest the option from what's new on the table: new presence
        discs (River: 0 -> 1, 1 -> 3, 2 -> 2), backed up by a new progression card in view.
        It stays a suggestion until the player confirms (→) or picks with 1/2/3."""
        from .engine.guide import GROWTH_BY_PRESENCE, GROWTH_GAINS_CARD
        from .engine import rules as R
        s = self.game.state
        if s["step"] != "spirit.growth" or len(s["players"]) != 1 or s.get("growth_choice", {}).get("0"):
            return
        spirit = s["players"][0]["spirit"]
        table = GROWTH_BY_PRESENCE.get(spirit)
        base = s.get("presence_at_growth")
        if not table or base is None:
            return
        added = sum(l["presence"] for l in s["lands"].values()) - base
        option = table.get(added)
        # A new power card in view means an option that gains one (River: 1 or 3).
        pw = self.power_watch.public() if getattr(self, "power_watch", None) else {}
        prog = {c for c, _ in R.PROGRESSION.get(spirit, [])}
        new_card = any(c["name"] in prog for c in pw.get("cards", []))
        if option is None or (new_card and option not in GROWTH_GAINS_CARD.get(spirit, set())):
            return
        if s.get("growth_suggest", {}).get("0") != option:
            self.dispatch({"type": "growth_suggest", "option": option}, "camera")

    def broadcast(self, payload):
        data = json.dumps(payload)
        for q in list(self.listeners):
            try:
                q.put_nowait(data)
            except queue.Full:
                pass

    def snapshot(self):
        with self.lock:
            return self._snapshot()


# Changes each time the server starts, so open pages reload to pick up new code.
BOOT_ID = str(os.getpid()) + "-" + str(int(__import__("time").time()))


def snapshot(game):
    s = game.state
    return {
        "boot": BOOT_ID,
        "state": s,
        "guide": describe(s),
        "can_undo": bool(game.history),
        "derived": {
            "spirits": [g.spirit_stats(s, i) for i in range(len(s["players"]))],
            "terror_level": g.terror_level(s),
            "fear_cards_left": g.fear_cards_left(s),
            "invader_cards_left": g.invader_cards_left(s),
            "next_stage": g.next_invader_stage(s),
            "totals": g.totals(s),
            "score_if_won": g.score(s, "won"),
            "score_if_lost": g.score(s, "lost"),
            "card_labels": {c: rules.card_label(c) for cards in rules.INVADER_CARDS.values() for c in cards},
        },
    }


REFERENCE = {
    "spirits": rules.SPIRITS,
    "adversaries": rules.ADVERSARIES,
    "terrains": rules.TERRAINS,
    "boards": rules.BOARDS,
    "glossary": rules.GLOSSARY,
    "pieces": list(rules.LAND_PIECES),
}


def create_app(data_dir=None, vision_url=None, start_vision=True):
    cfg = load_config()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    store = Store(data_dir or cfg["data_dir"])
    app.config["STORE"] = store
    url = cfg["board_camera_url"] if vision_url is None else vision_url
    if url:
        store.vision = VisionLink(url, on_change=store.vision_changed,
                                  board_map=load_board_map(cfg.get("board_reference"), os.path.join(BASE_DIR, cfg["board_art_dir"])))
        if start_vision:
            store.vision.start()

    # Scripts and styles carry the server's start id, so a restart always loads fresh copies
    # instead of whatever the browser cached.
    @app.context_processor
    def asset_version():
        return {"v": BOOT_ID}

    @app.get("/")
    @app.get("/phone")
    def index():
        return render_template("index.html")

    @app.get("/tv")
    def tv():
        return render_template("tv.html")

    @app.get("/assets/layout/<first>-<second>.jpg")
    def layout_picture(first, second):
        """Two boards fitted together (made once, then kept next to the board pictures)."""
        from flask import send_file
        ok = set(rules.BOARDS)
        if first not in ok or second not in ok:
            return Response("not found", status=404)
        boards_dir = os.path.join(BASE_DIR, cfg["board_art_dir"])
        out = os.path.join(BASE_DIR, "assets", "components", f"layout_{first}_{second}.jpg")
        try:
            from .layout_art import two_board_layout
            return send_file(two_board_layout(boards_dir, first, second, out), max_age=86400)
        except FileNotFoundError:
            return Response("no board pictures", status=404)

    @app.get("/assets/<path:name>")
    def asset(name):
        """Pictures of game components (spirit panels, cards) shown on the setup steps."""
        from flask import send_from_directory
        if not name.lower().endswith((".jpg", ".png")):
            return Response("not found", status=404)
        return send_from_directory(os.path.join(BASE_DIR, "assets"), name, max_age=0)

    @app.get("/api/links")
    def links():
        port = request.host.rsplit(":", 1)[1] if ":" in request.host else "80"
        hosts = cfg["public_urls"] or [f"http://{lan_address()}:{port}"]
        return jsonify({"phone": [h.rstrip("/") + "/phone" for h in hosts],
                        "tv": [h.rstrip("/") + "/tv" for h in hosts]})

    if cfg.get("camera_snapshot_url"):
        from .card_reader import CardScanner
        store.cards = CardScanner(cfg["camera_snapshot_url"], on_change=lambda: store.broadcast(store.snapshot()))

        from .slot_watch import SlotWatch
        store.slot_watch = SlotWatch(store, cfg["camera_snapshot_url"])
        from .power_cards import PowerWatch
        store.power_watch = PowerWatch(store, cfg["camera_snapshot_url"])
        if start_vision and url:
            store.slot_watch.start()
            store.power_watch.start()

    @app.get("/api/slot_watch.jpg")
    def slot_watch_photo():
        body = store.slot_watch.jpeg if getattr(store, "slot_watch", None) else b""
        if not body:
            return Response("no picture yet", status=503)
        return Response(body, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/card_scan")
    def card_scan():
        """{"on": true} starts reading the invader card held under the camera, {"on": false} stops."""
        if store.cards is None:
            return jsonify({"error": "no camera for card reading"}), 404
        (store.cards.start if (request.get_json(silent=True) or {}).get("on", True) else store.cards.stop)()
        return jsonify(store.snapshot())

    @app.post("/api/read_slots")
    def read_slots():
        """Read the invader cards on the invader board's Ravage, Build and Explore spaces from
        the camera's newest photo, and set the slots to what's clearly readable."""
        import urllib.request
        import cv2
        import numpy as np
        from .invader_board import InvaderBoardReader
        if not hasattr(store, "slot_reader"):
            store.slot_reader = InvaderBoardReader()
        try:
            with urllib.request.urlopen(cfg["camera_snapshot_url"], timeout=6) as r:
                frame = cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
        except OSError as e:
            return jsonify({"error": f"camera not reachable ({type(e).__name__})"}), 503
        result = store.slot_reader.read(frame)
        if not result.get("found"):
            return jsonify({"error": "can't see the invader board in the camera's picture"}), 422
        read = {}
        slots = store.game.state["invaders"]["slots"]
        explore_step = store.game.state["step"] in ("setup.first_explore", "invader.explore")
        for slot, info in result["slots"].items():
            if slot == "explore" and not explore_step:
                continue  # the deck sits there face down between explores
            if info["kind"] == "face" and info.get("margin", 0) >= 2:
                read[slot] = info["card"]
            elif info["kind"] == "empty" and slot != "explore":
                read[slot] = None
        for slot, card in read.items():
            if slots.get(slot) != card:
                store.dispatch({"type": "set_slot", "slot": slot, "card": card}, "camera")
        out = store.snapshot()
        out["read"] = read
        out["slot_reading"] = result["slots"]
        return jsonify(out)

    @app.get("/api/card_scan.jpg")
    def card_scan_photo():
        body = store.cards.jpeg if store.cards else b""
        if not body:
            return Response("no picture yet", status=503)
        return Response(body, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/vision/board.jpg")
    def vision_photo():
        body = store.vision.photo() if store.vision else None
        if not body:
            return Response("no photo yet", status=503)
        return Response(body, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/vision/map")
    def vision_map():
        m = store.vision.map if store.vision else None
        if m is None:
            return jsonify({"error": "no board map; set board_reference in config.json"}), 404
        return jsonify(m.public())

    @app.get("/api/vision/board_art.png")
    def vision_art():
        m = store.vision.map if store.vision else None
        body = m.art_png() if m is not None else None
        if not body:
            return Response("no board art", status=404)
        return Response(body, mimetype="image/png", headers={"Cache-Control": "max-age=3600"})

    @app.post("/api/vision")
    def vision_control():
        """{"board": "C"} says which board the camera sees, {"auto": true} turns on
        auto-sync, {"accept": "C3"} or {"accept": "all"} copies the camera's counts in,
        {"view": "photo" | "board"} switches every screen between the photo and the drawn board."""
        v = store.vision
        if v is None:
            return jsonify({"error": "no board camera is linked"}), 400
        body = request.get_json(silent=True) or {}
        if "board" in body:
            v.board = body["board"] or None
        if "auto" in body:
            v.auto = bool(body["auto"])
        if body.get("view") in ("photo", "board"):
            v.view = body["view"] if (body["view"] == "photo" or v.map is not None) else "photo"
        accept = body.get("accept")
        if accept:
            diffs = v.public(store.game.state)["diffs"]
            # "all" takes only what's believable; a single land can be taken by hand regardless.
            lands = {d["land"]: d["camera"] for d in diffs
                     if d["land"] == accept or (accept == "all" and d["confirmed"] and d["verdict"] != "unusual")}
            if lands:
                try:
                    return jsonify(store.dispatch({"type": "observe", "lands": lands}, "camera"))
                except ActionError as e:
                    return jsonify({"error": str(e)}), 400
        if body.get("auto"):
            store.vision_changed()
        payload = store.snapshot()
        store.broadcast(payload)
        return jsonify(payload)

    @app.get("/health")
    def health():
        s = store.game.state
        return jsonify({"ok": True, "status": s["status"], "round": s["round"], "step": s["step"]})

    @app.get("/api/state")
    def get_state():
        return jsonify(store.snapshot())

    @app.get("/api/reference")
    def reference():
        return jsonify(REFERENCE)

    @app.post("/api/action")
    def action():
        body = request.get_json(silent=True) or {}
        source = body.pop("source", "manual")
        try:
            return jsonify(store.dispatch(body, source))
        except ActionError as e:
            return jsonify({"error": str(e)}), 400

    @app.get("/api/events")
    def events():
        q = queue.Queue(maxsize=50)
        store.listeners.append(q)

        def stream():
            try:
                yield f"data: {json.dumps(store.snapshot())}\n\n"
                while True:
                    try:
                        yield f"data: {q.get(timeout=15)}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
            finally:
                store.listeners.remove(q)

        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


def lan_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "localhost"


def main():
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Spirit Island guide and tracker dashboard")
    ap.add_argument("--host", default=cfg["host"])
    ap.add_argument("--port", type=int, default=cfg["port"])
    ap.add_argument("--data-dir", default=cfg["data_dir"])
    ap.add_argument("--board-camera", default=cfg["board_camera_url"],
                    help="URL of the live board page (board_view.py); pass '' to run without the camera")
    args = ap.parse_args()
    app = create_app(args.data_dir, vision_url=args.board_camera)
    ip = lan_address()
    print(f"Spirit Island dashboard on port {args.port}")
    print(f"  phone (controls): http://{ip}:{args.port}/phone")
    print(f"  TV (couch view):  http://{ip}:{args.port}/tv")
    app.run(host=args.host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
