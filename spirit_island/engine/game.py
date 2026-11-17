"""Game state and the actions that change it.

The state is a plain JSON-able dict so it can be saved, sent to the browser
and later written to by the vision pipeline. Every change goes through
`Game.dispatch(action)`, which records an event (with its source, "manual" or
"vision") and keeps a snapshot so any change can be undone.
"""

import copy
import time
import uuid

from . import rules

QUIET = "_quiet"  # an action summary that is not written to the log

SETUP_STEPS = [
    "setup.welcome",
    "setup.players",
    "setup.island",
    "setup.spirits",
    "setup.invader_board",
    "setup.pieces",
    "setup.cards",
    "setup.first_explore",
]

ROUND_STEPS = [
    "spirit.growth",
    "spirit.energy",
    "spirit.powers",
    "fast",
    "invader.blighted",
    "invader.fear",
    "invader.ravage",
    "invader.build",
    "invader.explore",
    "invader.advance",
    "slow",
    "time_passes",
]

PHASES = {
    "setup": "Setup",
    "spirit": "Spirit phase",
    "fast": "Fast powers",
    "invader": "Invader phase",
    "slow": "Slow powers",
    "time_passes": "Time passes",
}

HISTORY_LIMIT = 300
LOG_LIMIT = 200


class ActionError(ValueError):
    """An action that does not make sense in the current state."""


def phase_of(step):
    return step.split(".")[0]


def new_state():
    return {
        "version": 1,
        "game_id": uuid.uuid4().hex[:8],
        "created": time.time(),
        "status": "setup",          # setup | playing | won | lost
        "result": None,
        "step": SETUP_STEPS[0],
        "round": 0,
        "players": [],
        "boards": [],
        "adversary": {"name": "None", "level": 0, "difficulty": 0},
        "fear": {
            "pool_size": 0,
            "generated": 0,          # markers moved off the pool toward the next card
            "deck": list(rules.DEFAULT_FEAR_DECK),
            "earned_total": 0,
            "unresolved": 0,         # earned cards waiting for the Fear step
        },
        "blight": {"pool": 0, "start": 0, "card_flipped": False},
        "invaders": {
            "deck_stages": list(rules.DEFAULT_DECK_STAGES),
            "drawn": [],             # cards revealed so far, in order
            "slots": {"ravage": None, "build": None, "explore": None},
            "discard": [],
        },
        "lands": {},
        "log": [],
    }


def terror_level(state):
    deck = state["fear"]["deck"]
    earned = state["fear"]["earned_total"]
    if earned >= deck[0] + deck[1]:
        return 3
    if earned >= deck[0]:
        return 2
    return 1


def fear_cards_left(state):
    return sum(state["fear"]["deck"]) - state["fear"]["earned_total"]


def invader_cards_left(state):
    inv = state["invaders"]
    return len(inv["deck_stages"]) - len(inv["drawn"])


def next_invader_stage(state):
    inv = state["invaders"]
    i = len(inv["drawn"])
    return inv["deck_stages"][i] if i < len(inv["deck_stages"]) else None


def possible_next_cards(state):
    """Cards that could still come off the top of the invader deck."""
    stage = next_invader_stage(state)
    if stage is None:
        return []
    inv = state["invaders"]
    # The same terrain card exists in Stage I and Stage II, so only count
    # cards already drawn from this stage.
    seen = {c for c, st in zip(inv["drawn"], inv["deck_stages"]) if st == stage}
    return [c for c in rules.INVADER_CARDS[stage] if c not in seen]


def land_matches(state, land_id, card):
    """True/False if the land matches the card, None if its terrain is unknown."""
    land = state["lands"][land_id]
    if card is None:
        return False
    if card == "C":
        return bool(land["coastal"])
    if land["terrain"] is None:
        return None
    return land["terrain"] in card


def invaders_in(land):
    return sum(land[p] for p in rules.INVADER_PIECES)


def totals(state):
    t = {p: 0 for p in rules.LAND_PIECES}
    for land in state["lands"].values():
        for p in rules.LAND_PIECES:
            t[p] += land[p]
    return t


def ravage_preview(land, defend=0):
    """What a ravage does to this land if no powers interfere."""
    damage = sum(land[p] * rules.PIECES[p][1] for p in rules.INVADER_PIECES)
    damage = max(0, damage - defend)
    dahan_killed = min(land["dahan"], damage // rules.PIECES["dahan"][0])
    survivors = land["dahan"] - dahan_killed
    fight_back = survivors * rules.PIECES["dahan"][1]
    # Suggest spending Dahan damage on the biggest invader it can destroy.
    left = {p: land[p] for p in rules.INVADER_PIECES}
    budget = fight_back
    killed = {p: 0 for p in rules.INVADER_PIECES}
    for p in ("cities", "towns", "explorers"):
        health = rules.PIECES[p][0]
        while left[p] and budget >= health:
            left[p] -= 1
            killed[p] += 1
            budget -= health
    return {
        "damage": damage,
        "blight": damage >= 2,
        "cascade": damage >= 2 and land["blight"] > 0,
        "dahan_killed": dahan_killed,
        "fight_back": fight_back,
        "invaders_killed": killed,
    }


def build_preview(land):
    if invaders_in(land) == 0:
        return None
    return "cities" if land["towns"] > land["cities"] else "towns"


def explore_preview(land):
    """'yes' if it surely gets an explorer, 'check' if it depends on neighbours."""
    if land["coastal"] or land["towns"] or land["cities"]:
        return "yes"
    return "check"


def score(state, outcome):
    """Score as the base rulebook describes it, to the best of our knowledge."""
    players = max(1, len(state["players"]))
    difficulty = state["adversary"].get("difficulty", 0)
    t = totals(state)
    left = invader_cards_left(state)
    if outcome == "won":
        base = 5 * difficulty + 10 + 2 * left
    else:
        base = 2 * difficulty + (len(state["invaders"]["deck_stages"]) - left)
    return base + t["dahan"] // players - t["blight"] // players


class Game:
    def __init__(self, state=None, history=None):
        self.state = state or new_state()
        self.history = history or []

    # -- public -----------------------------------------------------------
    def dispatch(self, action, source="manual"):
        kind = action.get("type")
        handler = getattr(self, f"_do_{kind}", None)
        if handler is None:
            raise ActionError(f"unknown action {kind!r}")
        if kind == "undo":
            return handler(action)
        before = copy.deepcopy(self.state)
        try:
            summary = handler(action)
        except Exception:
            self.state = before
            raise
        self.history.append(before)
        del self.history[:-HISTORY_LIMIT]
        if summary != QUIET:
            self._log(summary or kind, source)
        self._check_end()
        return self.state

    # -- helpers ----------------------------------------------------------
    def _log(self, text, source):
        s = self.state
        s["log"].append({"t": time.time(), "round": s["round"], "step": s["step"],
                         "source": source, "text": text})
        del s["log"][:-LOG_LIMIT]

    def _land(self, land_id):
        try:
            return self.state["lands"][land_id]
        except KeyError:
            raise ActionError(f"unknown land {land_id!r}") from None

    def _end(self, outcome, reason):
        s = self.state
        if s["status"] in ("won", "lost"):
            return
        s["status"] = outcome
        s["result"] = {"outcome": outcome, "reason": reason,
                       "score": score(s, outcome), "round": s["round"]}

    def _check_end(self):
        s = self.state
        if s["status"] != "playing":
            return
        if fear_cards_left(s) <= 0 and s["fear"]["unresolved"] == 0:
            self._end("won", "The whole fear deck was earned and resolved: the invaders flee.")

    # -- actions ----------------------------------------------------------
    def _do_undo(self, action):
        if not self.history:
            raise ActionError("nothing to undo")
        self.state = self.history.pop()
        return self.state

    def _do_place_start(self, action):
        """Put the printed starting pieces (and each spirit's starting presence) into the
        tracked game, so the camera can be checked against them."""
        from .guide import start_presence
        s = self.state
        for b in s["boards"]:
            for n in range(1, rules.LANDS_PER_BOARD + 1):
                land = s["lands"].get(f"{b}{n}")
                if land is None:
                    continue
                want = rules.START_PIECES.get(b, {}).get(n, {})
                for p in rules.LAND_PIECES:
                    land[p] = want.get(p, 0)
        for lid, n in start_presence(s).items():
            if lid in s["lands"]:
                s["lands"][lid]["presence"] += n
        s["start_placed"] = True
        return "Starting pieces placed"

    def _do_gain_power(self, action):
        """With power progression: a player takes the next card on their list."""
        s = self.state
        i = int(action.get("player", 0))
        nxt = s.setdefault("progression_next", {})
        nxt[str(i)] = max(0, nxt.get(str(i), 0) + int(action.get("delta", 1)))
        return f"{s['players'][i]['name']} gained a power card"

    def _do_back(self, action):
        """Go back one item, or to the last item of the previous setup screen, keeping
        everything already chosen."""
        s = self.state
        if s.get("sub", 0) > 0:
            s["sub"] -= 1
            return QUIET
        if s["status"] != "setup" or s["step"] not in SETUP_STEPS or s["step"] == SETUP_STEPS[0]:
            raise ActionError("already at the first setup step")
        s["step"] = SETUP_STEPS[SETUP_STEPS.index(s["step"]) - 1]
        s["sub"] = max(0, self._items() - 1)
        return f"Back to {s['step']}"

    def _do_new_game(self, action):
        self.state = new_state()
        return "Started a new game"

    def _do_configure(self, action):
        s = self.state
        if s["status"] != "setup":
            raise ActionError("the game has already started")
        players = action.get("players") or []
        if not 1 <= len(players) <= 4:
            raise ActionError("choose 1 to 4 players")
        boards = action.get("boards") or rules.BOARDS[: len(players)]
        if len(boards) != len(players) or len(set(boards)) != len(boards):
            raise ActionError("use one different island board per player")
        s["players"] = [{"name": p.get("name") or f"Player {i + 1}",
                         "spirit": p.get("spirit") or ""} for i, p in enumerate(players)]
        s["boards"] = list(boards)
        adv = action.get("adversary") or {}
        # Learning games default to each spirit's recommended power progression.
        s["progression"] = bool(action.get("progression", s.get("progression", True)))
        s["adversary"] = {"name": adv.get("name", "None"),
                          "level": int(adv.get("level", 0)),
                          "difficulty": int(adv.get("difficulty", 0))}
        n = len(players)
        s["fear"]["pool_size"] = int(action.get("fear_pool") or rules.FEAR_PER_PLAYER * n)
        s["fear"]["deck"] = [int(x) for x in (action.get("fear_deck") or rules.DEFAULT_FEAR_DECK)]
        blight = int(action.get("blight_pool") or rules.BLIGHT_PER_PLAYER * n + rules.BLIGHT_EXTRA)
        s["blight"] = {"pool": blight, "start": blight, "card_flipped": False}
        if action.get("deck_stages"):
            s["invaders"]["deck_stages"] = [int(x) for x in action["deck_stages"]]
        # Printed board layouts first, then anything tagged by hand (saved or sent).
        terrains = {**rules.default_terrains(boards), **(action.get("terrains") or {})}
        old = s["lands"]
        s["lands"] = {}
        for lid in rules.land_ids(boards):
            prev = old.get(lid, {})
            s["lands"][lid] = {
                "terrain": terrains.get(lid, prev.get("terrain")),
                "coastal": prev.get("coastal", int(lid[1:]) in rules.DEFAULT_COASTAL),
                **{p: prev.get(p, 0) for p in rules.LAND_PIECES},
            }
        names = ", ".join(f"{p['name']} ({p['spirit'] or 'spirit not chosen'})" for p in s["players"])
        return f"Set up {n} player(s): {names}; boards {', '.join(boards)}"

    def _items(self):
        from .guide import describe  # the screen's numbered items; imported here to avoid a cycle
        d = describe(self.state)
        return 1 if d.get("single") else len(d["do"])

    def _do_next(self, action):
        s = self.state
        if s["status"] in ("won", "lost"):
            raise ActionError("the game is over")
        # Walk the screen's numbered items one at a time before moving to the next screen.
        if not action.get("screen") and s.get("sub", 0) < self._items() - 1:
            s["sub"] = s.get("sub", 0) + 1
            return QUIET
        s["sub"] = 0
        step = s["step"]
        if step == "setup.players" and not s["players"]:
            raise ActionError("choose players and spirits first")
        if step == "setup.first_explore":
            if s["invaders"]["slots"]["explore"] is None:
                raise ActionError("tap the invader card you revealed first")
            self._advance_cards()
            s["status"] = "playing"
            s["round"] = 1
            s["step"] = ROUND_STEPS[0]
            return "Setup done; round 1 begins"
        if step == "invader.explore" and s["invaders"]["slots"]["explore"] is None:
            raise ActionError("tap the invader card you revealed first")
        if step == "invader.advance":
            self._advance_cards()
        if step == "invader.fear" and s["fear"]["unresolved"]:
            s["fear"]["unresolved"] = 0
        if step in SETUP_STEPS:
            s["step"] = SETUP_STEPS[SETUP_STEPS.index(step) + 1]
            return f"Next: {s['step']}"
        i = ROUND_STEPS.index(step)
        while True:
            i += 1
            if i == len(ROUND_STEPS):
                s["round"] += 1
                i = 0
                s["step"] = ROUND_STEPS[0]
                return f"Time passes; round {s['round']} begins"
            nxt = ROUND_STEPS[i]
            if nxt == "invader.blighted" and not s["blight"]["card_flipped"]:
                continue
            if nxt == "invader.fear" and not s["fear"]["unresolved"]:
                continue
            if nxt == "invader.explore" and invader_cards_left(s) == 0:
                s["step"] = nxt
                self._end("lost", "The invader deck ran out: time is up and the invaders hold the island.")
                return "Invader deck empty at Explore"
            s["step"] = nxt
            return f"Next: {nxt}"

    def _advance_cards(self):
        slots = self.state["invaders"]["slots"]
        if slots["ravage"]:
            self.state["invaders"]["discard"].append(slots["ravage"])
        slots["ravage"], slots["build"], slots["explore"] = slots["build"], slots["explore"], None

    def _do_reveal_invader(self, action):
        s = self.state
        card = action.get("card")
        if s["step"] not in ("setup.first_explore", "invader.explore"):
            raise ActionError("invader cards are revealed during Explore")
        inv = s["invaders"]
        if inv["slots"]["explore"] is not None:
            # Correcting a mis-tap: put the previous card back.
            inv["drawn"].pop()
        if card not in possible_next_cards(s):
            raise ActionError(f"{card!r} cannot be the next invader card")
        inv["drawn"].append(card)
        inv["slots"]["explore"] = card
        return f"Revealed invader card: {rules.card_label(card)}"

    def _do_set_slot(self, action):
        """Correction or camera input: set what card sits in a slot."""
        slot = action.get("slot")
        if slot not in ("ravage", "build", "explore"):
            raise ActionError("slot must be ravage, build or explore")
        card = action.get("card")
        if card is not None and not rules.is_card(card):
            raise ActionError(f"unknown invader card {card!r}")
        self.state["invaders"]["slots"][slot] = card
        return f"{slot.title()} slot set to {rules.card_label(card)}"

    def _do_fear(self, action):
        s = self.state
        f = s["fear"]
        delta = int(action.get("amount", 1))
        if delta < 0:
            f["generated"] = max(0, f["generated"] + delta)
            return f"Removed {-delta} fear"
        earned = 0
        for _ in range(delta):
            if fear_cards_left(s) <= 0:
                break
            f["generated"] += 1
            if f["generated"] >= f["pool_size"]:
                f["generated"] = 0
                f["earned_total"] += 1
                f["unresolved"] += 1
                earned += 1
        msg = f"Generated {delta} fear"
        if earned:
            msg += f"; earned {earned} fear card(s), terror level {terror_level(s)}"
        if fear_cards_left(s) <= 0:
            # Earning the last fear card wins at once; no need to resolve it.
            self._end("won", "The last fear card was earned: the invaders flee the island.")
        return msg

    def _do_resolve_fear_card(self, action):
        f = self.state["fear"]
        if f["unresolved"] <= 0:
            raise ActionError("no earned fear cards are waiting")
        f["unresolved"] -= 1
        return "Resolved a fear card"

    def _take_blight(self, n=1):
        b = self.state["blight"]
        b["pool"] -= n
        if b["pool"] <= 0 and b["card_flipped"]:
            b["pool"] = 0
            self._end("lost", "The blight card ran out of blight: the island is overrun.")

    def _do_blight(self, action):
        land = self._land(action.get("land"))
        delta = int(action.get("amount", 1))
        if delta > 0:
            land["blight"] += delta
            self._take_blight(delta)
            return f"Added {delta} blight to {action['land']}"
        delta = min(-delta, land["blight"])
        land["blight"] -= delta
        self.state["blight"]["pool"] += delta
        return f"Removed {delta} blight from {action['land']}"

    def _do_flip_blight_card(self, action):
        b = self.state["blight"]
        if action.get("invaders_win"):
            self._end("lost", "The blight card flipped to a side that ends the game.")
            return "Blight card flipped: game lost"
        b["card_flipped"] = True
        b["pool"] += int(action.get("add", 0))
        b["start"] += int(action.get("add", 0))
        return f"Blight card flipped; {action.get('add', 0)} blight added to it"

    def _do_set_pool(self, action):
        """Correction: set the blight pool or fear progress directly."""
        s = self.state
        if "blight_pool" in action:
            s["blight"]["pool"] = int(action["blight_pool"])
        if "fear_generated" in action:
            s["fear"]["generated"] = int(action["fear_generated"])
        if "fear_earned" in action:
            s["fear"]["earned_total"] = int(action["fear_earned"])
        return "Corrected pools"

    def _do_land(self, action):
        """Set or change pieces in a land. Used by taps and later by the camera."""
        lid = action.get("land")
        land = self._land(lid)
        piece = action.get("piece")
        if piece not in rules.LAND_PIECES:
            raise ActionError(f"unknown piece {piece!r}")
        if piece == "blight":
            if "value" in action:
                return self._do_blight({"land": lid, "amount": int(action["value"]) - land["blight"]})
            return self._do_blight({"land": lid, "amount": int(action.get("delta", 0))})
        if "value" in action:
            land[piece] = max(0, int(action["value"]))
        else:
            land[piece] = max(0, land[piece] + int(action.get("delta", 0)))
        return f"{lid}: {piece} = {land[piece]}"

    def _do_observe(self, action):
        """Bulk update from a perception source: {lands: {id: {piece: n}}, slots: {...}}."""
        changed = []
        for lid, pieces in (action.get("lands") or {}).items():
            for piece, value in pieces.items():
                if self._land(lid)[piece] != value:
                    self._do_land({"land": lid, "piece": piece, "value": value})
                    changed.append(f"{lid} {piece}={value}")
        for slot, card in (action.get("slots") or {}).items():
            if self.state["invaders"]["slots"].get(slot) != card:
                self._do_set_slot({"slot": slot, "card": card})
                changed.append(f"{slot}={card}")
        return "Observed: " + (", ".join(changed) or "no change")

    def _do_land_info(self, action):
        land = self._land(action.get("land"))
        if "terrain" in action:
            t = action["terrain"]
            if t is not None and t not in rules.TERRAINS:
                raise ActionError(f"unknown terrain {t!r}")
            land["terrain"] = t
        if "coastal" in action:
            land["coastal"] = bool(action["coastal"])
        return f"{action['land']}: terrain {land['terrain']}, coastal {land['coastal']}"

    def _do_apply_ravage(self, action):
        lid = action.get("land")
        land = self._land(lid)
        p = ravage_preview(land, int(action.get("defend", 0)))
        land["dahan"] -= p["dahan_killed"]
        for piece, n in p["invaders_killed"].items():
            land[piece] -= n
        if p["blight"]:
            land["blight"] += 1
            self._take_blight(1)
        k = p["invaders_killed"]
        return (f"Ravage in {lid}: {p['damage']} damage, "
                f"{'blight added, ' if p['blight'] else ''}{p['dahan_killed']} Dahan lost, "
                f"Dahan destroyed {k['cities']} city/{k['towns']} town/{k['explorers']} explorer")

    def _do_apply_build(self, action):
        lid = action.get("land")
        land = self._land(lid)
        piece = build_preview(land)
        if piece is None:
            raise ActionError(f"{lid} has no invaders, so nothing builds there")
        land[piece] += 1
        return f"Build in {lid}: +1 {piece[:-1] if piece == 'towns' else 'city'}"

    def _do_apply_explore(self, action):
        lid = action.get("land")
        self._land(lid)["explorers"] += 1
        return f"Explore in {lid}: +1 explorer"

    def _do_end_game(self, action):
        outcome = action.get("outcome")
        if outcome not in ("won", "lost"):
            raise ActionError("outcome must be won or lost")
        self._end(outcome, action.get("reason") or ("Victory" if outcome == "won" else "Defeat"))
        return f"Game {outcome}: {self.state['result']['reason']}"
