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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def load_config():
    cfg = {"host": "0.0.0.0", "port": 5055, "data_dir": "games"}
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
            payload = snapshot(self.game)
        self.broadcast(payload)
        return payload

    def broadcast(self, payload):
        data = json.dumps(payload)
        for q in list(self.listeners):
            try:
                q.put_nowait(data)
            except queue.Full:
                pass

    def snapshot(self):
        with self.lock:
            return snapshot(self.game)


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


def create_app(data_dir=None):
    cfg = load_config()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    store = Store(data_dir or cfg["data_dir"])
    app.config["STORE"] = store

    @app.get("/")
    def index():
        return render_template("index.html")

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
    args = ap.parse_args()
    app = create_app(args.data_dir)
    print(f"Spirit Island dashboard: http://localhost:{args.port}  (phone: http://{lan_address()}:{args.port})")
    app.run(host=args.host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
