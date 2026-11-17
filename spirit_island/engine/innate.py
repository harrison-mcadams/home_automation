"""Innate powers and sacred sites: what the elements on this round's cards switch on.

An innate power is printed on the spirit panel. It has thresholds of elements; each round,
count the elements on the power cards you played (plus any uncovered on your presence
tracks). Every threshold met adds that level's effect. It is fast or slow like a card, and
targets from a sacred site: a land with 2 or more of your presence (or, for River, any of
your presence in a wetland).
"""

from __future__ import annotations

from . import rules
from .targets import adjacency

# Elements on each power card (only the cards whose elements are known here).
ELEMENTS = {
    "Boon of Vigor": ["sun", "water", "plant"],
    "Flash Floods": ["sun", "water"],
    "River's Bounty": ["sun", "water", "animal"],
    "Wash Away": ["water", "earth"],
    "Uncanny Melting": ["sun", "moon", "water"],
    "Nature's Resilience": ["earth", "plant", "animal"],
    "Pull Beneath the Hungry Earth": ["moon", "water", "earth"],
}

SYMBOL = {"sun": "☀", "moon": "☾", "fire": "🔥", "air": "🪶", "water": "💧", "earth": "⛰", "plant": "🌿", "animal": "🐾"}

INNATES = {
    "River Surges in Sunlight": {
        "name": "Massive Flooding", "speed": "slow", "range": 1,
        "levels": [
            ({"sun": 1, "water": 2}, "Push 1 explorer or town.", {"push": ["towns", "explorers"], "up_to": 1}),
            ({"sun": 2, "water": 3}, "Instead: 2 damage, then push up to 3 explorers and/or towns.",
             {"push": ["towns", "explorers"], "up_to": 3}),
            ({"sun": 3, "water": 4, "earth": 1}, "Instead: 2 damage to each invader.", {}),
        ],
    },
}

# Spirits whose presence on a terrain counts as a sacred site on its own.
SACRED_TERRAIN = {"River Surges in Sunlight": "W"}


def spirit(state: dict, i: int = 0) -> str | None:
    return state["players"][i]["spirit"] if len(state.get("players", [])) > i else None


def sacred_sites(state: dict, i: int = 0) -> list:
    """Land ids that are this spirit's sacred sites."""
    terrain = SACRED_TERRAIN.get(spirit(state, i))
    out = []
    for lid, land in sorted(state["lands"].items()):
        n = land.get("presence", 0)
        if n >= 2 or (n >= 1 and terrain and land.get("terrain") == terrain):
            out.append(lid)
    return out


def _near(state: dict, starts: list, rng: int) -> set:
    out = set()
    for b in state["boards"]:
        adj = adjacency(b)
        start = {lid[len(b):] for lid in starts if lid.startswith(b)}
        seen, frontier = set(start), set(start)
        for _ in range(rng):
            frontier = {n for f in frontier for n in adj.get(f, [])} - seen
            seen |= frontier
        out |= {f"{b}{n}" for n in seen if n != "ocean"}
    return out


def status(state: dict, cards: list, i: int = 0) -> dict | None:
    """The spirit's innate power given the cards played: elements counted, levels met, and
    the lands it can reach. None for a spirit whose innate isn't known here."""
    inn = INNATES.get(spirit(state, i))
    if not inn:
        return None
    have, unknown = {}, []
    for c in cards:
        if c not in ELEMENTS:
            unknown.append(c)
        for e in ELEMENTS.get(c, []):
            have[e] = have.get(e, 0) + 1
    levels = [{"need": need, "text": text, "met": all(have.get(e, 0) >= n for e, n in need.items()), **extra}
              for need, text, extra in inn["levels"]]
    sites = sacred_sites(state, i)
    reach = sorted(_near(state, sites, inn["range"]))
    targets = [lid for lid in reach
               if sum(state["lands"][lid].get(k, 0) for k in ("explorers", "towns", "cities"))]
    return {"name": inn["name"], "speed": inn["speed"], "have": have, "levels": levels,
            "active": any(l["met"] for l in levels), "sites": sites, "targets": targets, "unknown": unknown}


def _fmt(need: dict) -> str:
    return " ".join(f"{n} {SYMBOL.get(e, '')}{e}" for e, n in need.items())


def lines(state: dict, cards: list, i: int = 0) -> list:
    """Guide lines: progress towards each threshold, and what to do if one is met."""
    st = status(state, cards, i)
    if not st:
        return []
    have = ", ".join(f"{n} {SYMBOL.get(e, '')}{e}" for e, n in sorted(st["have"].items())) or "no elements yet"
    when = "after the invaders (Slow powers)" if st["speed"] == "slow" else "before the invaders (Fast powers)"
    out = [f"Innate power, {st['name']} ({st['speed']}, range 1 from a sacred site): your cards give {have}."]
    for k, l in enumerate(st["levels"], 1):
        mark = "✓ met" if l["met"] else "not yet"
        out.append({"text": f"   Level {k}, needs {_fmt(l['need'])}: {l['text']} ({mark})",
                    "colour": "#86dc93" if l["met"] else "#6b7a70"})
    sites = ", ".join(f"land {s[1:]}" for s in st["sites"]) or "none yet"
    note = f"   Sacred sites: {sites}."
    if spirit(state, i) in SACRED_TERRAIN:
        note += " (Your presence in a wetland counts as a sacred site.)"
    out.append(note)
    if st["active"]:
        tgt = ", ".join(f"land {t[1:]}" for t in st["targets"]) or "no land with invaders in range"
        out.append({"text": f"It happens this round, {when}. Lands it can reach with invaders: {tgt}.",
                    "colour": "#ffd968"})
    if st["unknown"]:
        out.append(f"   (I don't know the elements on: {', '.join(st['unknown'])}. Count those yourself.)")
    return out
