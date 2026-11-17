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
