"""Which lands a power card can target right now, and what it would do in each."""

from __future__ import annotations

import json
import os

from . import rules

_ADJ = None


def adjacency(board: str) -> dict:
    global _ADJ
    if _ADJ is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "board_adjacency.json")
        try:
            with open(path, encoding="utf-8") as f:
                _ADJ = json.load(f)
        except OSError:
            _ADJ = {}
    return _ADJ.get(board, {})


def in_range(state: dict, rng: int) -> set:
    """Land ids within `rng` of any of your presence (range counts across the ocean)."""
    out = set()
    for b in state["boards"]:
        adj = adjacency(b)
        start = {lid[len(b):] for lid, l in state["lands"].items() if lid.startswith(b) and l.get("presence")}
        seen, frontier = set(start), set(start)
        for _ in range(rng):
            frontier = {n for f in frontier for n in adj.get(f, [])} - seen
            seen |= frontier
        out |= {f"{b}{n}" for n in seen if n != "ocean"}
    return out


def effect(card: str, land: dict, presence_here: bool) -> str:
    inv = land.get("explorers", 0) + land.get("towns", 0) + land.get("cities", 0)
    t, coastal = land.get("terrain"), land.get("coastal")
    if card == "Uncanny Melting":
        parts = []
        if inv:
            parts.append("1 fear")
        if t in ("S", "W") and land.get("blight"):
            parts.append("remove 1 blight")
        return ", ".join(parts) or "nothing here"
    if card == "Flash Floods":
        return f"{2 if coastal else 1} damage" if inv else "no invaders"
    if card == "Wash Away":
        n = land.get("explorers", 0) + land.get("towns", 0)
        return f"push up to {min(3, n)} explorer/town" if n else "nothing to push"
    if card == "River's Bounty":
        return "gather up to 2 Dahan" + ("; then +1 Dahan, +1 energy" if land.get("dahan", 0) >= 2 else "")
    if card == "Nature's Resilience":
        return "defend 6"
    if card == "Pull Beneath the Hungry Earth":
        parts = (["1 fear, 1 damage"] if presence_here else []) + (["1 damage"] if t in ("S", "W") else [])
        return " + ".join(parts) or "nothing here"
    if card == "Accelerated Rot":
        return "2 fear, 4 damage"
    if card == "Song of Sanctity":
        return "push all explorers" if land.get("explorers") else ("remove 1 blight" if land.get("blight") else "nothing here")
    if card == "Tsunami":
        return "2 fear, 8 damage, destroy 2 Dahan"
    return ""


def targets(state: dict, card: str) -> dict:
    """{"spirit": True} for spirit-targeting cards, else {land id: what it would do}."""
    spec = rules.POWER_TARGETS.get(card)
    if not spec:
        return {}
    if spec.get("spirit"):
        return {"spirit": True}
    out = {}
    for lid in sorted(in_range(state, spec["range"])):
        land = state["lands"][lid]
        want = spec["land"]
        if want == "coastal" and not land.get("coastal"):
            continue
        if want not in ("any", "coastal") and land.get("terrain") not in want:
            continue
        out[lid] = effect(card, land, bool(land.get("presence")))
    return out


COLOURS = ["#f2c14e", "#5fd0e8", "#ff8f6b", "#a98bff", "#7ee08a", "#ff6fae", "#c7c7c7"]


def _option(card: str, land: dict, presence_here: bool) -> dict | None:
    """What the card would do here: text, fear it makes, and the board change the camera
    can check ({"blight": -1} / {"invaders": -1} / {"dahan": +1} / {"explorers": -1})."""
    inv = land.get("explorers", 0) + land.get("towns", 0) + land.get("cities", 0)
    t, coastal = land.get("terrain"), land.get("coastal")
    if card == "Uncanny Melting":
        fear = 1 if inv else 0
        blight = t in ("S", "W") and land.get("blight")
        if not (fear or blight):
            return None
        return {"text": ", ".join((["1 fear"] if fear else []) + (["remove 1 blight"] if blight else [])),
                "fear": fear, "expect": {"blight": -1} if blight else {}}
    if card == "Flash Floods":
        return {"text": f"{2 if coastal else 1} damage", "fear": 0, "expect": {"invaders": -1}} if inv else None
    if card == "Wash Away":
        n = land.get("explorers", 0) + land.get("towns", 0)
        return {"text": f"push up to {min(3, n)} explorer/town", "fear": 0, "expect": {"invaders": -1}} if n else None
    if card == "River's Bounty":
        return {"text": "gather up to 2 Dahan" + (", then +1 Dahan, +1 energy" if land.get("dahan", 0) >= 2 else ""),
                "fear": 0, "expect": {"dahan": 1}}
    if card == "Nature's Resilience":
        return {"text": "defend 6", "fear": 0, "expect": {}}
    if card == "Pull Beneath the Hungry Earth":
        fear = 1 if presence_here and inv else 0
        if not (inv and (presence_here or t in ("S", "W"))):
            return None
        return {"text": ("1 fear, " if fear else "") + "damage", "fear": fear, "expect": {"invaders": -1}}
    if card == "Accelerated Rot":
        return {"text": "2 fear, 4 damage", "fear": 2, "expect": {"invaders": -1} if inv else {}}
    if card == "Song of Sanctity":
        if land.get("explorers"):
            return {"text": "push all explorers", "fear": 0, "expect": {"explorers": -1}}
        return {"text": "remove 1 blight", "fear": 0, "expect": {"blight": -1}} if land.get("blight") else None
    if card == "Tsunami":
        return {"text": "2 fear, 8 damage, destroy 2 Dahan", "fear": 2, "expect": {"invaders": -1}}
    return None


def options(state: dict, card: str) -> list:
    """The card's useful choices right now, each with a colour: [{land, text, fear, expect, colour}]."""
    spec = rules.POWER_TARGETS.get(card)
    if not spec or spec.get("spirit"):
        return []
    out = []
    for lid in sorted(in_range(state, spec["range"])):
        land = state["lands"][lid]
        want = spec["land"]
        if want == "coastal" and not land.get("coastal"):
            continue
        if want not in ("any", "coastal") and land.get("terrain") not in want:
            continue
        o = _option(card, land, bool(land.get("presence")))
        if o:
            out.append({"land": lid, **o})
    for i, o in enumerate(out):
        o["colour"] = COLOURS[i % len(COLOURS)]
        o["key"] = i + 1
    return out


def done(option: dict, delta: dict) -> bool:
    """Does a confirmed camera change on the option's land carry the option out?"""
    exp = option.get("expect") or {}
    if not exp:
        return False
    for k, v in exp.items():
        if k == "invaders":
            d = sum(delta.get(p, 0) for p in ("explorers", "towns", "cities"))
        else:
            d = delta.get(k, 0)
        if (v < 0 and d >= 0) or (v > 0 and d <= 0):
            return False
    return True
