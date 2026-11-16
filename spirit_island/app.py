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


def load_board_map(path):
    """The drawn-board map from the camera's reference folder, or None if it isn't there."""
    if not path:
        return None
    try:
        from .board_map import BoardMap
        return BoardMap(path)
    except Exception as e:  # missing folder, no OpenCV, ...: the photo view still works
        print(f"No drawn board view ({type(e).__name__}: {e})")
        return None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def load_config():
    cfg = {"host": "0.0.0.0", "port": 5055, "data_dir": "games",
           "board_camera_url": "http://localhost:8091", "public_urls": [],
           "board_reference": ""}
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
        with self.lock:
            if action.get("type") == "configure":
                action = {**action, "terrains": {**self.saved_terrains(), **(action.get("terrains") or {})}}
            self.game.dispatch(action, source=source)
            self._save()
            payload = self._snapshot()
        self.broadcast(payload)
        return payload

    def _snapshot(self):
        out = snapshot(self.game)
        if self.vision is not None:
            out["vision"] = self.vision.public(self.game.state)
        return out

    def vision_changed(self):
        """Called by the vision link when a new camera reading arrives (or the link drops).

        With auto-sync on, a settled reading that differs from the tracked game is copied
        in (logged as coming from the camera, and Undo-able like any other change).
        """
        v = self.vision
        if v is not None and v.auto and v.settled() and self.game.state["status"] == "playing":
            diffs = v.public(self.game.state)["diffs"]
            if diffs:
                try:
                    self.dispatch({"type": "observe", "lands": {d["land"]: d["camera"] for d in diffs}}, "camera")
                    return
                except ActionError as e:
                    print(f"camera sync failed: {e}")
        self.broadcast(self.snapshot())

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


def snapshot(game):
    s = game.state
    return {
        "state": s,
        "guide": describe(s),
        "can_undo": bool(game.history),
        "derived": {
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
                                  board_map=load_board_map(cfg.get("board_reference")))
        if start_vision:
            store.vision.start()

    @app.get("/")
    @app.get("/phone")
    def index():
        return render_template("index.html")

    @app.get("/tv")
    def tv():
        return render_template("tv.html")

    @app.get("/api/links")
    def links():
        port = request.host.rsplit(":", 1)[1] if ":" in request.host else "80"
        hosts = cfg["public_urls"] or [f"http://{lan_address()}:{port}"]
        return jsonify({"phone": [h.rstrip("/") + "/phone" for h in hosts],
                        "tv": [h.rstrip("/") + "/tv" for h in hosts]})

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
            lands = {d["land"]: d["camera"] for d in diffs if accept in ("all", d["land"])}
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
