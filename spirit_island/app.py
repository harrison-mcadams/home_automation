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
        # Paused (e.g. while pieces are moved about to teach the camera): nothing the camera
        # sees touches the game.
        if getattr(self, "paused", False) and source == "camera":
            return self.snapshot()
        # With a card in view, Next leaves the step in one go (the card screen is one step).
        if action.get("type") == "next" and self.game.state["step"] in ("spirit.powers", "fast", "slow")                 and self.card_focus():
            action = {**action, "screen": True}
        # Leaving Play powers: pay for the cards the camera sees played (only when really
        # leaving the step, not when Next walks through its numbered items).
        if action.get("type") == "next" and self.game.state["step"] == "spirit.powers"                 and (action.get("screen") or self.game.state.get("sub", 0) >= self.game._items() - 1)                 and getattr(self, "power_watch", None) is not None:
            pw_now = self.power_watch.public()
            cost = pw_now.get("cost") or 0
            # Remember what was played, so Fast and Slow still show those cards once
            # they've been moved out of the camera's view.
            with self.lock:
                for c in pw_now.get("cards", []):
                    self.game.dispatch({"type": "note", "key": "played", "add": {k: c.get(k) for k in ("name", "cost", "speed")}},
                                       source="camera")
            if cost and not self.game.state.get("energy_from_camera"):
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
        out["paused"] = bool(getattr(self, "paused", False))
        if getattr(self, "slot_watch", None) is not None:
            out["slot_watch"] = self.slot_watch.public()
        if getattr(self, "change_watch", None) is not None:
            out["changes"] = self.change_watch.public()
        if getattr(self, "power_watch", None) is not None:
            out["power_watch"] = pw = self.power_watch.public()
            # Where the cards in view could be used, for the drawn board.
            focus = self.card_focus()
            step = self.game.state["step"]
            if step in ("fast", "slow"):
                # Only the cards that act now; the others just get a mention.
                later = [c for c in focus if c["speed"] != step]
                focus = [c for c in focus if c["speed"] == step]
                if not focus:
                    other = "slow" if step == "fast" else "fast"
                    names = ", ".join(c["name"] for c in later)
                    out["guide"] = {**out["guide"], "single": True, "pictures": [], "helper": None, "tips": [], "why": "",
                                    "title": f"No {step} powers this round",
                                    "do": [f"You played no {step} cards, so nothing happens now. Press → to go on."]
                                    + ([f"{names} {'is' if len(later) == 1 else 'are'} {other}: "
                                        + ("it acts after the invaders, in Slow powers." if other == "slow"
                                           else "it already acted, in Fast powers.")] if later else [])}
            if focus:
                out["card_focus"] = focus
                out["targets"] = {c["name"]: {o["land"]: o["text"] for o in c["options"]} for c in focus}
                out["guide"] = card_guide(self.game.state, focus, out["guide"])
        return out

    def vision_changed(self):
        """Called by the vision link when a new camera reading arrives (or the link drops).

        With auto-sync on, a settled reading that differs from the tracked game is copied
        in (logged as coming from the camera, and Undo-able like any other change).
        """
        # (Pieces are entered by the change tracker, see camera_events; the piece-by-piece
        # reading is only shown, e.g. on the starting-pieces step.)
        self.growth_from_presence()
        self.broadcast(self.snapshot())

    def camera_events(self, events):
        """Pieces the camera saw put down or taken off since the board was last still.

        Each is entered in the light of the step: a white piece arriving during Build or
        Explore is that step's building or explorer; otherwise the piece is entered as seen
        (white pieces by size, or by what the land holds when one leaves). Returns the
        events with what was done about them, for the screens."""
        from .engine import game as G
        from .engine.guide import describe
        from .engine.targets import done as option_done
        WHITE = ("explorers", "towns", "cities")
        WORD = {"explorers": "explorer", "towns": "town", "cities": "city", "dahan": "Dahan",
                "blight": "blight", "presence": "presence"}
        out = []
        # Pieces taken off come first: a push is a removal here and an arrival next door.
        events = sorted(events, key=lambda e: e["delta"])
        for e in events:
            s = self.game.state
            lid, piece, delta = e["land"], e["piece"], e["delta"]
            land = s["lands"].get(lid)
            if land is None:
                continue
            step, did = s["step"], None
            # The cards' choices as they stood before this change (a choice to destroy the last
            # explorer in a land is gone from the list once it's done).
            try:
                focus_before = [c for c in self.card_focus() if c["now"] and not c["resolved"]]
            except ActionError:
                focus_before = []
            try:
                push = self._card_push(lid) if piece in WHITE and delta < 0 and step in ("fast", "slow") else None
                if push:
                    # A played card pushes invaders out of this land: the white pieces leaving
                    # are the ones it can push (never a city), and they arrive next door.
                    card, o = push
                    moved = []
                    for kind in o["push"]:
                        while land.get(kind, 0) > 0 and len(moved) < o["up_to"]:
                            self.dispatch({"type": "land", "land": lid, "piece": kind, "delta": -1}, "camera")
                            moved.append(kind)
                    self.pushed = moved
                    self.dispatch({"type": "card_resolved", "card": card, "land": lid, "fear": o["fear"]}, "camera")
                    did = f"{card}: pushed {', '.join(WORD[k] for k in moved)} out of land {lid[1:]}"
                elif piece in WHITE and delta > 0 and getattr(self, "pushed", None):
                    for kind in self.pushed:
                        self.dispatch({"type": "land", "land": lid, "piece": kind, "delta": 1}, "camera")
                    did = f"pushed {', '.join(WORD[k] for k in self.pushed)} into land {lid[1:]}"
                    self.pushed = []
                elif piece in WHITE and delta > 0 and step == "invader.build":
                    marks = describe(s).get("marks") or {}
                    key = f"built:{s['round']}"
                    if marks.get(lid, {}).get("text", "nothing") != "nothing" and lid not in s.get(key, []):
                        kind = G.build_preview(land)
                        self.dispatch({"type": "apply_build", "land": lid}, "camera")
                        self.dispatch({"type": "note", "key": key, "add": lid}, "camera")
                        did = f"+1 {'city' if kind == 'cities' else 'town'} on land {lid[1:]} (build)"
                elif piece in WHITE and delta > 0 and step in ("invader.explore", "setup.first_explore"):
                    self.dispatch({"type": "apply_explore", "land": lid}, "camera")
                    self.dispatch({"type": "note", "key": f"explored:{s['round']}", "add": lid}, "camera")
                    did = f"+1 explorer on land {lid[1:]} (explore)"
                if did is None:
                    if piece in WHITE and delta < 0:
                        here = [p for p in WHITE if land.get(p, 0) > 0]
                        if not here:
                            continue
                        piece = piece if piece in here else here[0]
                    if delta < 0 and land.get(piece, 0) <= 0:
                        continue
                    self.dispatch({"type": "land", "land": lid, "piece": piece, "delta": delta}, "camera")
                    did = f"{'+1' if delta > 0 else '-1'} {WORD[piece]} on land {lid[1:]}"
            except ActionError as err:
                did = f"a change on land {lid[1:]} that could not be entered ({err})"
            out.append({**e, "did": did})
            # A played card whose choice this carries out is done.
            try:
                done_now = set(self.game.state.get("resolved", {}))
                for c in [c for c in focus_before if c["name"] not in done_now]:
                    for o in c["options"]:
                        if o["land"] == lid and option_done(o, {e["piece"]: delta}):
                            self.dispatch({"type": "card_resolved", "card": c["name"], "land": lid,
                                           "fear": o["fear"]}, "camera")
                            break
            except ActionError:
                pass
        self.growth_from_presence()
        self.after_camera_events()
        return out

    def _card_push(self, lid):
        """(card, option) when a played card still to resolve pushes invaders out of this land."""
        for c in self.card_focus():
            if not c["now"] or c["resolved"]:
                continue
            for o in c["options"]:
                if o["land"] == lid and o.get("push"):
                    return c["name"], o
        return None

    def after_camera_events(self):
        """Move on when the step's work has all been seen."""
        from .engine.guide import describe
        s = self.game.state
        g = describe(s)
        if s["step"] == "invader.build":
            want = {l for l, m in (g.get("marks") or {}).items() if m["text"] != "nothing"}
            if want and want <= set(s.get(f"built:{s['round']}", [])):
                self.dispatch({"type": "next", "screen": True}, "camera")
        elif s["step"] == "invader.explore":
            rows = (g.get("helper") or {}).get("rows") or []
            want = {r["land"] for r in rows if r.get("explore") == "yes"}
            if want and want <= set(s.get(f"explored:{s['round']}", [])):
                self.dispatch({"type": "next", "screen": True}, "camera")
        else:
            self.advance_if_cards_done()

    def step_done_from_camera(self, lands):
        """The camera saw the build / explore carried out: enter it and move on."""
        s = self.game.state
        kind = {"invader.build": "apply_build", "invader.explore": "apply_explore"}.get(s["step"])
        if not kind:
            return
        for lid in lands:
            try:
                self.dispatch({"type": kind, "land": lid}, "camera")
            except ActionError as e:
                print(f"{kind} {lid}: {e}")
        self.dispatch({"type": "next", "screen": True}, "camera")

    @staticmethod
    def _taken_plausible(s, before, seen):
        """Discs only leave the tracks to become presence on the island, at most 2 at a time:
        a reading that doesn't fit (the panel at the photo's edge, glare) is ignored."""
        from .engine import rules as R
        start = sum(n for _, n in R.START_PRESENCE.get(s["players"][0]["spirit"], []))
        on_island = sum(l.get("presence", 0) for l in s["lands"].values())
        old = sum((before or {}).values())
        new = sum(seen.values())
        return new >= on_island - start and (before is None or old <= new <= old + 2)

    def panel_sync(self):
        """Follow the spirit panel the camera reads: track discs and energy tokens. Taking
        your energy (Gain energy) or paying for the cards in view (Play powers) with the
        tokens moves the game on."""
        pw = self.power_watch.public() if getattr(self, "power_watch", None) else {}
        panel = pw.get("panel")
        s = self.game.state
        if not panel or s["status"] != "playing" or len(s["players"]) != 1:
            return
        from .engine import game as G
        before = G.spirit_stats(s, 0)
        sp = s.get("spirits", {}).get("0", {})
        change = {}
        if panel["taken"] != sp.get("taken") and self._taken_plausible(s, sp.get("taken"), panel["taken"]):
            change["taken"] = panel["taken"]
        if before is None or panel["tokens"] != before["energy"]:
            change["tokens"] = panel["tokens"]
        if s["step"] in ("spirit.energy", "spirit.powers") and s.get("energy_at_step") is None and before:
            # (e.g. after an Undo back into the step) the energy as the step began
            self.dispatch({"type": "mark_energy_start", "value": before["energy"]}, "camera")
        if change:
            self.dispatch({"type": "panel_seen", **change}, "camera")
        start = s.get("energy_at_step")
        now = panel["tokens"]
        if start is None:
            return
        # More tokens than when the step began: one was out of view then. Count from the most seen.
        if s["step"] == "spirit.powers" and now > start:
            self.dispatch({"type": "mark_energy_start", "value": now}, "camera")
            start = now
        st = G.spirit_stats(s, 0)
        if s["step"] == "spirit.energy" and st and now == start + st["energy_per_turn"]:
            self.dispatch({"type": "next", "screen": True}, "camera")
        elif s["step"] == "spirit.powers" and pw.get("cost") and now == start - pw["cost"]:
            self.dispatch({"type": "next", "screen": True}, "camera")

    def card_focus(self):
        """The power cards in view during Play powers / Fast / Slow, with their choices."""
        s = self.game.state
        pw = self.power_watch.public() if getattr(self, "power_watch", None) else {}
        cards = list(pw.get("cards") or [])
        if s["step"] in ("fast", "slow"):
            seen = {c["name"] for c in cards}
            cards += [c for c in s.get("played", []) if c["name"] not in seen]
        if s["step"] not in ("spirit.powers", "fast", "slow") or not cards:
            return []
        from .engine.targets import options
        from .engine import rules as R
        out = []
        for c in cards:
            art = R.SPIRIT_ART.get(s["players"][0]["spirit"]) if s["players"] else None
            folder = art[0] if art and c["name"] in art[1] else None
            src = f"spirits/{folder}/{R.picture_slug(c['name'])}.jpg" if folder else f"powers/{R.picture_slug(c['name'])}.jpg"
            out.append({**c, "src": src, "options": options(s, c["name"]),
                        "spirit": bool(R.POWER_TARGETS.get(c["name"], {}).get("spirit")),
                        "resolved": c["name"] in s.get("resolved", {}),
                        "now": s["step"] == c["speed"]})
        return out

    def resolve_cards_from_camera(self):
        """In Fast / Slow, a card whose choice the camera sees carried out is marked done;
        once every card for this step is done, the game moves on."""
        s = self.game.state
        if s["step"] not in ("fast", "slow") or self.vision is None:
            return
        from .engine.targets import done
        focus = [c for c in self.card_focus() if c["now"]]
        if not focus:
            return
        diffs = {d["land"]: d for d in self.vision.public(s)["diffs"] if d["confirmed"]}
        for c in focus:
            if c["resolved"]:
                continue
            for o in c["options"]:
                d = diffs.get(o["land"])
                if d and done(o, d["delta"]):
                    self.dispatch({"type": "observe", "lands": {o["land"]: d["camera"]}}, "camera")
                    self.dispatch({"type": "card_resolved", "card": c["name"], "land": o["land"], "fear": o["fear"]}, "camera")
                    break
        self.advance_if_cards_done()

    def advance_if_cards_done(self):
        s = self.game.state
        if s["step"] not in ("fast", "slow"):
            return
        now = [c for c in self.card_focus() if c["now"]]
        # An innate power switched on for this step is done at the table too: leave it to Next.
        from .engine import innate
        inn = innate.status(s, [c["name"] for c in self.card_focus()])
        if inn and inn["active"] and inn["speed"] == s["step"] and inn["name"] not in s.get("resolved", {}):
            return
        if now and all(c["name"] in s.get("resolved", {}) for c in now):
            self.dispatch({"type": "next"}, "camera")

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
        # No new presence is also what the table looks like before anything is done: an
        # option that adds none is only suggested once something else of it shows (a card).
        if added == 0 and not new_card:
            if s.get("growth_suggest", {}).get("0"):
                self.dispatch({"type": "growth_suggest", "option": 0}, "camera")
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


def card_guide(state, focus, base):
    """The step's guide replaced by what the cards in view can do, choices colour-coded."""
    step = state["step"]
    do, pics = [], []
    for c in focus:
        when = {"fast": "before the invaders (Fast powers)", "slow": "after the invaders (Slow powers)"}[c["speed"]]
        head = f"{c['name']}: {c['cost']} energy, {c['speed']}, resolves {when}."
        if c["resolved"]:
            do.append(head + " Done ✓")
        elif c["spirit"]:
            do.append(head + " It targets a spirit (you), not a land.")
        elif not c["options"]:
            do.append(head + " Nothing useful in range right now.")
        else:
            do.append(head + (" Choose:" if c["now"] else " Your choices, as things stand:"))
            for o in c["options"]:
                do.append({"text": f"{o['key']}. Land {o['land'][1:]}: {o['text']}", "colour": o["colour"]})
        # (The card picture sits under the list; the side keeps the drawn board, with the
        # choices lit in the same colours.)
    if step == "spirit.powers":
        cost = sum(c["cost"] or 0 for c in focus)
        have = (state.get("spirits", {}).get("0", {}) or {}).get("energy", 0)
        if state.get("energy_from_camera") and cost:
            do.append({"text": f"Pay: take {cost} energy token{'s' if cost > 1 else ''} off your panel "
                               f"({have} → {have - cost}). The game moves on when the camera sees it.",
                       "colour": "#ffd968"})
        else:
            do.append("Press → to pay and move on.")
    elif any(c["now"] and not c["resolved"] for c in focus):
        do.append("Do it at the table. The camera spots the change and moves on, or press the option's number.")
    from .engine import innate
    do += innate.lines(state, [c["name"] for c in focus])
    return {**base, "title": " + ".join(c["name"] for c in focus), "do": do, "pictures": pics, "single": True,
            "helper": {"kind": "card_options", "cards": focus}, "why": "", "tips": []}


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
        from .step_watch import StepWatch
        if cfg.get("board_reference"):
            from .change_watch import ChangeWatch
            store.change_watch = ChangeWatch(store, cfg["camera_snapshot_url"].replace("/photo.jpg", "/frame.jpg"),
                                             cfg["board_reference"], every=0.5,
                                             fallback=cfg["camera_snapshot_url"])
            if start_vision and url:
                store.change_watch.start()
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

    @app.post("/api/pause_camera")
    def pause_camera():
        """{"on": true} stops the camera changing the game (training, tidying the table)."""
        store.paused = bool((request.get_json(silent=True) or {}).get("on", True))
        out = store.snapshot()
        store.broadcast(out)
        return jsonify(out)

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
