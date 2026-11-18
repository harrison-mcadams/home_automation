"""What Ravage, Build and Explore do to each land, worked out from the game's own board.

The game is the truth about the board: these plans say exactly which pieces to add or
remove and why, and `apply_plan` makes the same change to the game's board when the
player presses Next. Nothing here looks at the camera.

A plan is a list of land entries in land order:
    {"land": "C5", "changes": {"blight": +1, "dahan": -1, "towns": -1, ...},
     "text": "add 1 blight, remove 1 Dahan, remove 1 town",
     "why": "its city and explorer deal 4 damage, which is 2 or more ..."}
Lands where nothing happens are left out, except Explore's "no" lands, which carry
`"changes": {}` so the screen can say why they were skipped.
"""

from __future__ import annotations

from . import rules
from .targets import adjacency

NAMES = {
    "explorers": ("explorer", "explorers"),
    "towns": ("town", "towns"),
    "cities": ("city", "cities"),
    "dahan": ("Dahan", "Dahan"),
    "blight": ("blight", "blight"),
    "presence": ("presence", "presence"),
}
ORDER = ["blight", "presence", "dahan", "cities", "towns", "explorers"]


def _n(piece, k):
    one, many = NAMES[piece]
    return f"{k} {one if k == 1 else many}"


def _list(parts):
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def describe(changes):
    """'add 1 blight, remove 2 Dahan' from {"blight": 1, "dahan": -2}."""
    adds = [_n(p, changes[p]) for p in ORDER if changes.get(p, 0) > 0]
    removes = [_n(p, -changes[p]) for p in ORDER if changes.get(p, 0) < 0]
    out = []
    if adds:
        out.append("add " + _list(adds))
    if removes:
        out.append("remove " + _list(removes))
    return ", ".join(out) or "nothing"


def land_number(lid):
    return lid[len(lid.rstrip("0123456789")):]


def _board_of(state, lid):
    for b in state.get("boards", []):
        if lid.startswith(b) and lid[len(b):].isdigit():
            return b
    return None


def neighbours(state, lid):
    """Land ids next to this one on its board (the ocean is not a land)."""
    b = _board_of(state, lid)
    if b is None:
        return []
    near = adjacency(b).get(land_number(lid), [])
    return [f"{b}{n}" for n in near if n != "ocean" and f"{b}{n}" in state["lands"]]


def lands_for(state, card):
    """Lands a Ravage / Build / Explore card hits, in land order."""
    from .game import land_matches
    hit = [lid for lid in state["lands"] if land_matches(state, lid, card)]
    return sorted(hit, key=lambda l: (l.rstrip("0123456789"), int(land_number(l) or 0)))


# ---- Ravage -------------------------------------------------------------------------

def _invader_words(land):
    parts = [_n(p, land[p]) for p in ("cities", "towns", "explorers") if land.get(p)]
    return _list(parts)


def _cascade_target(state, lid, blight_now):
    """The neighbour a cascading blight goes to: one without blight if possible (so it
    stops there), then the one with the least presence to lose, then the lowest number."""
    options = neighbours(state, lid)
    if not options:
        return None
    return min(options, key=lambda n: (blight_now.get(n, 0) > 0,
                                       state["lands"][n].get("presence", 0),
                                       int(land_number(n))))


def ravage_land(state, lid, blight_now=None, defend=0):
    """Changes and reasons for one land's ravage. `blight_now` is blight per land as it
    stands during this step (cascades from earlier lands count)."""
    land = state["lands"][lid]
    blight_now = blight_now if blight_now is not None else {k: v["blight"] for k, v in state["lands"].items()}
    damage = sum(land.get(p, 0) * rules.PIECES[p][1] for p in rules.INVADER_PIECES)
    if damage == 0:
        return None
    dealt = max(0, damage - defend)
    changes, why = {}, []
    who = _invader_words(land)
    why.append(f"its {who} deal{'s' if sum(land.get(p, 0) for p in rules.INVADER_PIECES) == 1 else ''} "
               f"{damage} damage" + (f", {defend} stopped by Defend" if defend else ""))
    cascades = []
    if dealt >= 2:
        changes["blight"] = 1
        if land.get("presence", 0):
            changes["presence"] = -1
        why.append("2 or more damage adds 1 blight" + (", which destroys 1 of your presence there"
                                                        if land.get("presence", 0) else ""))
        if blight_now.get(lid, 0) > 0:
            # Blight already there: it cascades to a neighbour, and on from there while
            # each land it reaches already had blight.
            seen, at = {lid}, lid
            while blight_now.get(at, 0) > 0:
                nxt = _cascade_target(state, at, blight_now)
                if nxt is None or nxt in seen:
                    break
                cascades.append(nxt)
                seen.add(nxt)
                at = nxt
            if cascades:
                why.append("the land already had blight, so it cascades: "
                           + "; ".join(f"1 blight to land {land_number(c)}" for c in cascades))
    else:
        why.append("under 2 damage adds no blight")
    dahan = land.get("dahan", 0)
    dahan_killed = min(dahan, dealt // rules.PIECES["dahan"][0])
    if dahan_killed:
        changes["dahan"] = -dahan_killed
        why.append(f"each 2 damage destroys a Dahan, so {_n('dahan', dahan_killed)} "
                   f"{'is' if dahan_killed == 1 else 'are'} destroyed")
    survivors = dahan - dahan_killed
    if survivors:
        budget = survivors * rules.PIECES["dahan"][1]
        left = {p: land.get(p, 0) for p in rules.INVADER_PIECES}
        killed = {}
        # Spend the Dahan's damage on the biggest invaders it can destroy outright.
        for p in ("cities", "towns", "explorers"):
            health = rules.PIECES[p][0]
            while left[p] and budget >= health:
                left[p] -= 1
                killed[p] = killed.get(p, 0) + 1
                budget -= health
        for p, k in killed.items():
            changes[p] = -k
        hit = _list([_n(p, k) for p, k in killed.items()])
        why.append(f"{_n('dahan', survivors)} left fight{'s' if survivors == 1 else ''} back for "
                   f"{survivors * rules.PIECES['dahan'][1]} damage"
                   + (f", destroying {hit}" if hit else ", not enough to destroy anything"))
    return {"land": lid, "changes": changes, "cascade": cascades, "damage": damage,
            "text": describe(changes), "why": "; ".join(why) + "."}


def ravage_plan(state, card):
    blight_now = {k: v["blight"] for k, v in state["lands"].items()}
    rows, extra = [], {}
    for lid in lands_for(state, card):
        r = ravage_land(state, lid, blight_now)
        if not r:
            continue
        rows.append(r)
        if r["changes"].get("blight"):
            blight_now[lid] = blight_now.get(lid, 0) + 1
        for c in r["cascade"]:
            blight_now[c] = blight_now.get(c, 0) + 1
            extra.setdefault(c, {"blight": 0, "from": [], "from_lands": []})
            extra[c]["blight"] += 1
            extra[c]["from"].append(land_number(lid))
            extra[c]["from_lands"].append(lid)
    # Cascaded blight shows on the land it lands in, as its own instruction.
    for c, e in extra.items():
        land = state["lands"][c]
        lost = min(e["blight"], land.get("presence", 0))
        changes = {"blight": e["blight"]}
        if lost:
            changes["presence"] = -lost
        rows.append({"land": c, "changes": changes, "cascade": [], "damage": 0, "cascaded_from": e["from_lands"], "key": f"{c}:cascade",
                     "text": describe(changes),
                     "why": f"blight cascading from land {_list(e['from'])}"
                            + (", which destroys your presence there" if lost else "")
                            + ". You may pick a different neighbour; the app picks one without blight "
                              "where it can, so the cascade stops."})
    return rows


# ---- Build ------------------------------------------------------------------------

def build_land(state, lid):
    land = state["lands"][lid]
    if not any(land.get(p, 0) for p in rules.INVADER_PIECES):
        return None
    t, c = land.get("towns", 0), land.get("cities", 0)
    if t > c:
        changes = {"cities": 1}
        why = f"it has more towns ({t}) than cities ({c}), so it builds a city"
    else:
        changes = {"towns": 1}
        why = (f"it has invaders and no more towns ({t}) than cities ({c}), so it builds a town")
    return {"land": lid, "changes": changes, "text": describe(changes), "why": why + "."}


def build_plan(state, card):
    return [r for r in (build_land(state, lid) for lid in lands_for(state, card)) if r]


# ---- Explore ----------------------------------------------------------------------

def explore_land(state, lid):
    land = state["lands"][lid]
    if land.get("coastal"):
        why = "it touches the ocean"
    elif land.get("towns") or land.get("cities"):
        why = "it has a town or city"
    else:
        near = [n for n in neighbours(state, lid)
                if state["lands"][n].get("towns") or state["lands"][n].get("cities")]
        if near:
            why = f"land {land_number(near[0])} next to it has a town or city"
        else:
            return {"land": lid, "changes": {}, "text": "nothing",
                    "why": "it is inland with no town or city in it or next to it."}
    return {"land": lid, "changes": {"explorers": 1}, "text": "add 1 explorer", "why": why + "."}


def explore_plan(state, card):
    return [explore_land(state, lid) for lid in lands_for(state, card)]


# ---- Applying ---------------------------------------------------------------------

STEP_SLOTS = {"invader.ravage": "ravage", "invader.build": "build", "invader.explore": "explore"}
PLANS = {"ravage": ravage_plan, "build": build_plan, "explore": explore_plan}


def plan_for_step(state, step=None):
    step = step or state["step"]
    slot = STEP_SLOTS.get(step)
    if not slot:
        return []
    card = state["invaders"]["slots"].get(slot)
    if not card:
        return []
    return PLANS[slot](state, card)


def apply_changes(game, lid, changes):
    """Apply one land's changes to the game's board, keeping the blight pool in step."""
    land = game.state["lands"][lid]
    for piece, d in changes.items():
        if piece == "blight":
            if d > 0:
                land["blight"] += d
                game._take_blight(d)
            else:
                d = min(-d, land["blight"])
                land["blight"] -= d
                game.state["blight"]["pool"] += d
        else:
            land[piece] = max(0, land.get(piece, 0) + d)
