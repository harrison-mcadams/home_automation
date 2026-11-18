"""Plain-English guidance for each step: what to do at the table right now.

The text is our own summary of the base game rules, aimed at someone learning
to play. When it disagrees with a printed card or panel, the printed component
wins (that is also how the real game works).
"""

from . import game as g
from . import innate, invader_plan, rules


def _lands_for(state, card):
    hit, unknown = [], []
    for lid in state["lands"]:
        m = g.land_matches(state, lid, card)
        if m:
            hit.append(lid)
        elif m is None:
            unknown.append(lid)
    return hit, unknown


def _unknown_note(unknown):
    if not unknown:
        return []
    return [f"Terrain not tagged yet for {', '.join(unknown)}. Tag terrains in the Island panel "
            f"and the app will pick out the right lands for you."]


def describe(state):
    step = state["step"]
    fn = _STEPS.get(step)
    out = {"step": step, "phase": g.PHASES[g.phase_of(step)], "title": step, "do": [],
           "why": "", "tips": [], "helper": None, "pictures": []}
    if fn:
        out.update(fn(state))
    out["sub"] = 0 if out.get("single") else max(0, min(state.get("sub", 0), len(out["do"]) - 1))
    if state["status"] in ("won", "lost"):
        r = state["result"]
        out.update({
            "title": "Victory!" if r["outcome"] == "won" else "The island has fallen",
            "do": [r["reason"], f"Score: {r['score']} (round {r['round']})."],
            "why": "Score formula used: a win is 5 x difficulty + 10 + 2 per invader card still in the "
                   "deck; a loss is 2 x difficulty + 1 per invader card that left the deck. Either way "
                   "add 1 per (Dahan / players) and subtract 1 per (blight / players) on the island. "
                   "Check it against your rulebook's scoring section.",
            "tips": ["Tap Undo if the game ended by mistake, or New game to play again."],
            "helper": None,
        })
    return out


# --- setup ----------------------------------------------------------------

def _welcome(s):
    return {
        "title": "Welcome to Spirit Island",
        "do": [
            "You and any other players are spirits of an island. Colonising invaders are spreading "
            "across it, and you work together to drive them off.",
            "Every round has the same rhythm: spirits grow and pick powers, fast powers happen, "
            "the invaders act (ravage, build, explore), slow powers happen, then time passes.",
            "You win by scaring the invaders off (earning fear cards). You lose if the land is "
            "blighted too much, a spirit is wiped off the island, or the invader deck runs out.",
            "This app walks you through each step. Do what it says on the table, tap what changed, "
            "then tap Next.",
        ],
        "why": "The game is cooperative: everyone wins or loses together, so talk plans over freely.",
        "tips": ["Open 'Learn' any time for the meaning of a word like presence, Dahan or ravage."],
    }


def _roster(s):
    info = {x["name"]: x for x in rules.SPIRITS}
    return [{"name": p["name"], "spirit": p["spirit"] or "not chosen yet",
             "board": s["boards"][i] if i < len(s["boards"]) else "",
             "complexity": info.get(p["spirit"], {}).get("complexity", ""),
             "style": info.get(p["spirit"], {}).get("style", "")}
            for i, p in enumerate(s["players"])]


def _players(s):
    return {
        "title": "Choose players and spirits",
        "do": [
            "Pick how many players (1 or 2 is a great start) and give each a spirit.",
            "For a first game choose Low complexity spirits. River Surges in Sunlight and Vital "
            "Strength of the Earth are friendly to learn.",
            "Island boards are dealt at random, one per player. Tap Re-deal on the phone for a "
            "different draw, or pick a board by hand.",
            "Skip the adversary for your first games; it is an optional extra challenge.",
        ],
        "why": "Each spirit plays very differently. The complexity is printed on the back of its panel.",
        "tips": [],
        "helper": {"kind": "configure", "roster": _roster(s)},
        "pictures": [{"src": f"spirits/{rules.SPIRIT_ART[p['spirit']][0]}/panel_front.jpg", "wide": True,
                      "group": i, "caption": f"{p['name']} · {p['spirit']}"}
                     for i, p in enumerate(s["players"]) if p["spirit"] in rules.SPIRIT_ART],
    }


def _island(s):
    n = len(s["players"])
    return {
        "title": "Lay out the island",
        "do": [
            f"Take {n} island board{'s' if n > 1 else ''} ({', '.join(s['boards'])}), one per player.",
            "Use the side with the lettered lands (the standard, balanced side).",
        ] + ([
            "Two boards: turn the second board upside down and push its inland edge against the "
            "first board's inland edge, so the oceans are on the outside (like the picture). The "
            "edges are shaped to fit together.",
        ] if n > 1 else []) + [
            "Each board has 8 numbered lands plus an ocean. Lands are Jungle, Mountain, Sands or Wetland.",
        ],
        "why": "Invader cards name a terrain, and every land of that terrain is affected.",
        "tips": [],
        "pictures": ([{"src": f"layout/{s['boards'][0]}-{s['boards'][1]}.jpg", "wide": True,
                       "caption": f"Boards {s['boards'][0]} and {s['boards'][1]} joined, oceans on the outside"}]
                     if n == 2 else [_comp(f"board_{b}", f"Board {b}", True) for b in s["boards"]]),
    }


def _highest_id(s, terrain, b):
    """Land id (e.g. 'C8') of the highest-numbered land of a terrain on board b."""
    if not b:
        return None
    terrains = rules.default_terrains([b])
    for lid, info in s.get("lands", {}).items():  # a terrain set on the Island panel wins
        if lid in terrains and info.get("terrain"):
            terrains[lid] = info["terrain"]
    lands = [lid for lid, t in terrains.items() if t == terrain]
    return max(lands, key=lambda l: int(l[len(b):])) if lands else None


def _highest(s, terrain, b):
    """'land 8 on board C' for the highest-numbered land of a terrain on board b."""
    lid = _highest_id(s, terrain, b)
    return f"land {lid[len(b):]} on board {b}" if lid else None


def _start_text(s, spirit, b):
    places = rules.START_PRESENCE.get(spirit)
    if not places or not all(_highest_id(s, t, b) for t, _ in places):
        return None
    parts = [f"{n} disc{'s' if n > 1 else ''} on {_highest(s, t, b)} (the highest-numbered "
             f"{rules.TERRAINS[t]})" for t, n in places]
    return "Starting presence: " + " and ".join(parts) + ". These come from your supply, not the tracks."


_SEEDS = None


def _land_point(lid, b):
    """Where a land sits on its board picture, as fractions of the picture's width and height."""
    global _SEEDS
    if _SEEDS is None:
        import json
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "board_seeds.json")
        try:
            with open(path, encoding="utf-8") as f:
                _SEEDS = json.load(f)["boards"]
        except OSError:
            _SEEDS = {}
    pt = _SEEDS.get(b, {}).get(lid[len(b):])
    return (pt[0] / rules.SCAN_SIZE[0], pt[1] / rules.SCAN_SIZE[1]) if pt else None


DISC_COLOURS = ["#3fa8ff", "#ff5ab0", "#ffd23a", "#9b6bff"]


def _track_discs(spirit):
    """Every presence-track circle except the first of each row, as picture fractions."""
    t = rules.PRESENCE_TRACKS.get(spirit)
    if not t:
        return []
    w, h = rules.PANEL_SIZE
    return [{"x": round((t["x0"] + i * t["dx"]) / w, 4), "y": round(y / h, 4)}
            for y, n in ((t["energy_y"], t["energy"]), (t["cards_y"], t["cards"])) for i in range(1, n)]


def spirit_pictures(state, start_item=3):
    """Pictures for the spirit step, each tagged with the numbered item it illustrates:
    0 the panel, 1 the starting cards, 2 presence on the tracks, 3+ starting presence."""
    pics = []
    for group, p in enumerate(state["players"]):
        art = rules.SPIRIT_ART.get(p["spirit"])
        if not art:
            continue
        folder, cards = art
        colour = DISC_COLOURS[group % len(DISC_COLOURS)]
        who = f"{p['name']}'s spirit panel" if len(state["players"]) > 1 else "Spirit panel"
        pics.append({"src": f"spirits/{folder}/panel_front.jpg", "wide": True, "group": group, "items": [0],
                     "caption": f"{who} (front) for {p['spirit']}"})
        pics.append({"src": f"spirits/{folder}/card_back.jpg", "mark": True, "group": group, "items": [1],
                     "caption": "Back of your 4 starting cards: your spirit's art"})
        for c in cards:
            pics.append({"src": f"spirits/{folder}/{rules.picture_slug(c)}.jpg", "group": group, "items": [1],
                         "caption": f"{c} (starting power card)"})
        pics.append({"src": f"spirits/{folder}/panel_front.jpg", "wide": True, "group": group, "items": [2],
                     "discs": _track_discs(p["spirit"]), "disc_colour": colour, "disc_size": 0.052,
                     "caption": f"{who}: a disc on every track circle but the first"})
        b = state["boards"][group] if group < len(state["boards"]) else None
        discs = []
        for t, n in rules.START_PRESENCE.get(p["spirit"], []):
            lid = _highest_id(state, t, b)
            pt = _land_point(lid, b) if lid else None
            if pt:
                discs += [{"x": round(pt[0] + 0.03 * k, 4), "y": round(pt[1], 4), "land": True} for k in range(n)]
        if discs:
            pics.append({"src": f"components/board_{b}.jpg", "wide": True, "group": group,
                         "items": [start_item + group], "discs": discs, "disc_colour": colour,
                         "disc_size": 0.06, "caption": f"Board {b}: starting presence"})
    return pics


def _spirits(s):
    starts, unknown, start_groups = [], False, []
    for i, p in enumerate(s["players"]):
        board = s["boards"][i] if i < len(s["boards"]) else None
        t = _start_text(s, p["spirit"], board)
        if t and len(s["players"]) > 1:
            t = f"{p['name']}: " + t[0].lower() + t[1:]
        if t:
            starts.append(t)
            start_groups.append(i)
        else:
            unknown = True
    return {
        "title": "Set up each spirit",
        "do": [
            "Spirit panel: the big double-sided card (large picture). Lay it front side up.",
            "Starting hand: the 4 power cards whose BACK shows your spirit's art (the highlighted "
            "picture). Their fronts don't name the spirit. Every spirit starts with its own 4.",
            "Presence: in the middle of the panel are two rows of circles. Put a disc of your colour "
            "on every circle except the first one in each row.",
        ] + starts + (["Starting presence: the SETUP box on the back of each panel says where "
                       "the first discs go on the island. Place them now."] if unknown else []),
        "why": "Each disc you later move from a track onto the island uncovers a bigger number, so "
               "you gain more energy or more card plays as you spread.",
        "tips": ["Tap the Presence counts in the Island panel if you want the app to track them."],
        "pictures": [dict(p, items=[3 + start_groups.index(p["group"])]) if p["items"][0] >= 3 else p
                     for p in spirit_pictures(s) if p["items"][0] < 3 or p["group"] in start_groups],
    }


def _comp(name, caption, wide=False, items=None):
    pic = {"src": f"components/{name}.jpg", "caption": caption}
    if items is not None:
        pic["items"] = items
    if wide:
        pic["wide"] = True
    return pic


def _invader_board(s):
    f = s["fear"]
    return {
        "title": "Set up the invader board",
        "do": [
            "Invader board: unfold it beside the island. It has spaces for the fear pool and fear "
            "cards, the terror level, the blight card, and the invader cards (Ravage, Build, and the "
            "invader deck on the Explore space).",
            f"Fear pool: {f['pool_size']} fear markers (4 per player).",
            f"Fear deck: shuffle the fear cards and deal {sum(f['deck'])} face down, building from the "
            f"bottom up: {f['deck'][2]} cards, the Terror III divider, {f['deck'][1]} cards, the "
            f"Terror II divider, {f['deck'][0]} cards on top. The rest go back in the box.",
            f"Blight card: Healthy Island side up, with {s['blight']['pool']} blight on it.",
            "Invader deck: sort the invader cards by the I, II, III on their backs and shuffle each "
            "pile. Take 1 card from each pile without looking and put it back in the box. Stack them "
            "face down: Stage III at the bottom, Stage II on it, Stage I on top (12 cards).",
        ],
        "why": "The fear deck is your victory clock; the invader deck is your defeat clock.",
        "tips": ["An adversary changes these numbers. If you use one, follow its setup and correct the "
                 "pools in Settings."] if s["adversary"]["name"] != "None" else [],
        "pictures": [
            {"anim": "photo", "src": "components/invader_board_art.jpg", "aspect": 0.907, "wide": True, "items": [0],
             "caption": "Invader board: where everything goes",
             "zones": [{"x": .41, "y": .015, "w": .2, "h": .085, "label": "Fear pool"},
                       {"x": .38, "y": .25, "w": .24, "h": .28, "label": "Generated fear"},
                       {"x": .017, "y": .019, "w": .205, "h": .315, "label": "Fear deck"},
                       {"x": .017, "y": .35, "w": .205, "h": .305, "label": "Earned fear"},
                       {"x": .017, "y": .674, "w": .205, "h": .305, "label": "Fear discard"},
                       {"x": .783, "y": .019, "w": .2, "h": .31, "label": "Terror level"},
                       {"x": .783, "y": .35, "w": .2, "h": .31, "label": "Blight card"},
                       {"x": .843, "y": .716, "w": .14, "h": .232, "label": "Invader deck"},
                       {"x": .671, "y": .716, "w": .136, "h": .232, "label": "Build"},
                       {"x": .5, "y": .716, "w": .139, "h": .232, "label": "Ravage"},
                       {"x": .257, "y": .716, "w": .21, "h": .15, "label": "Discard"}]},
            {"anim": "setup", "step": 1, "fear": f["pool_size"], "deck": f["deck"], "blight": s["blight"]["pool"], "wide": True, "items": [1], "caption": "Fear markers into the fear pool"},
            {"anim": "setup", "step": 2, "fear": f["pool_size"], "deck": f["deck"], "blight": s["blight"]["pool"], "wide": True, "items": [2], "caption": "The fear deck, built from the bottom up"},
            {"anim": "setup", "step": 3, "fear": f["pool_size"], "deck": f["deck"], "blight": s["blight"]["pool"], "wide": True, "items": [3], "caption": "Blight card, Healthy Island side up"},
            {"anim": "setup", "step": 4, "fear": f["pool_size"], "deck": f["deck"], "blight": s["blight"]["pool"], "wide": True, "items": [4], "caption": "Invader deck on the Explore space"},
        ],
    }


_PIECE_WORDS = {"dahan": ("Dahan", "Dahan"), "cities": ("city", "cities"), "towns": ("town", "towns"),
                "blight": ("blight", "blight"), "explorers": ("explorer", "explorers"), "presence": ("presence", "presence")}


def piece_text(counts):
    return ", ".join(f"{n} {_PIECE_WORDS[p][n != 1]}" for p, n in counts.items() if n) or "nothing"


def start_presence(s):
    """{land id: discs} for every player's starting presence."""
    out = {}
    for i, p in enumerate(s["players"]):
        b = s["boards"][i] if i < len(s["boards"]) else None
        for t, n in rules.START_PRESENCE.get(p["spirit"], []):
            lid = _highest_id(s, t, b)
            if lid:
                out[lid] = out.get(lid, 0) + n
    return out


def _expected_start(s):
    out = {}
    for b in s["boards"]:
        for n in range(1, 9):
            out[f"{b}{n}"] = dict(rules.START_PIECES.get(b, {}).get(n, {}))
    for lid, n in start_presence(s).items():
        if lid in out:
            out[lid]["presence"] = out[lid].get("presence", 0) + n
    return out


def _pieces(s):
    rows = []
    for b in s["boards"]:
        if b in rules.START_PIECES:
            rows.append(f"Board {b}: " + "; ".join(f"land {n}: {piece_text(c)}" for n, c in
                                                    sorted(rules.START_PIECES[b].items())) + ". The rest start empty.")
    return {
        "title": "Place the starting pieces",
        "single": True,
        "do": [
            "The small black icons by each land number are its starting pieces.",
        ] + rows + [
            "Dahan: round wooden pieces. Town: small white house. City: tall white tower. "
            "Blight: grey-blue bumpy piece (from the box, not the blight card).",
            "Ignore the paw and spiral icons; they're for an expansion.",
            "Place them, then press Next. The app records them for you; it never needs to check.",
        ],
        "why": "This is the island as the invaders first find it.",
        "tips": [],
        "helper": {"kind": "verify", "placed": bool(s.get("start_placed")), "expected": _expected_start(s),
                   # where each land sits on the single-board picture, for marking the check on it
                   "points": ({f"{s['boards'][0]}{n}": _land_point(f"{s['boards'][0]}{n}", s["boards"][0])
                               for n in range(1, 9)} if len(s["boards"]) == 1 else {})},
        "pictures": ([{"src": f"layout/{s['boards'][0]}-{s['boards'][1]}.jpg", "wide": True,
                       "caption": f"Boards {s['boards'][0]} and {s['boards'][1]}: starting-piece icons by each land number"}]
                     if len(s["boards"]) == 2 else
                     [_comp(f"board_{b}", f"Board {b}: starting-piece icons by each land number", True)
                      for b in s["boards"]]),
    }


def _progression_list(cards):
    return ", ".join(f"{i}. {c}{' (Major)' if kind == 'Major' else ''}" for i, (c, kind) in enumerate(cards, 1))


def _cards(s):
    prog = s.get("progression") and any(p["spirit"] in rules.PROGRESSION for p in s["players"])
    if prog:
        do = [f"{p['name']}: pull these cards out of the Minor and Major decks (as on {p['spirit']}'s "
              f"Power Progression card) and stack them face down in this order: "
              f"{_progression_list(rules.PROGRESSION[p['spirit']])}."
              for p in s["players"] if p["spirit"] in rules.PROGRESSION]
        do += ["Whenever growth says gain a power card, take the next card from your stack instead of "
               "drawing. After taking a Major, forget (remove) one power card of your choice.",
               "Shuffle the rest of the Minor and Major decks and set them nearby; some powers draw from them."]
        pics = [{"src": f"spirits/{rules.SPIRIT_ART[p['spirit']][0]}/progression.jpg",
                 "caption": f"{p['name']}'s power progression"}
                for p in s["players"] if p["spirit"] in rules.PROGRESSION]
        return {"title": "Power cards: your progression", "single": True, "do": do,
                "why": "A fixed, good order of new powers, so a first game is about learning, not choosing.",
                "tips": ["Turn the progression off on the Players step to draw powers normally."],
                "pictures": pics}
    return {
        "title": "Power card decks",
        "do": [
            "Shuffle the Minor Power deck (gold-brown backs) and the Major Power deck (blue lightning "
            "backs) separately and set them nearby.",
            "Leave room for your discard pile next to your panel.",
        ],
        "why": "As you grow you draw new powers from these decks.",
        "tips": [],
        "pictures": [
            _comp("minor_back", "Minor Power (back)"),
            _comp("minor_card", "Minor Power (front)"),
            _comp("major_back", "Major Power (back)"),
            _comp("major_card", "Major Power (front)"),
        ],
    }


def _first_explore(s):
    slot = s["invaders"]["slots"]["explore"]
    do = [
        "Turn over the top invader card and put it in the Explore space of the invader board.",
        "Tap that card below.",
    ]
    helper = {"kind": "reveal", "options": g.possible_next_cards(s)}
    if slot:
        hit, unknown = _lands_for(s, slot)
        do = [f"Revealed: {rules.card_label(slot)}.",
              "Add 1 explorer to each land of that terrain that is coastal, has a town or city, "
              "or is next to a land with a town or city."] + _unknown_note(unknown) + [
              f"Then slide the {rules.card_label(slot)} card one space left, from Explore to Build. "
              "Those lands will build in round 1. Tap Next and the app moves it too."]
        helper["rows"] = [{"land": lid, "explore": g.explore_preview(s["lands"][lid], s, lid)} for lid in hit]
    return {
        "title": "First explore",
        "do": do,
        "why": "The invaders scout the island before the first round. When you tap Next the card "
               "slides to the Build space, so these lands will build in round 1.",
        "tips": [],
        "helper": helper,
    }


# --- round --------------------------------------------------------------------

def _next_powers(s):
    if not s.get("progression"):
        return []
    out = []
    for i, p in enumerate(s["players"]):
        lst = rules.PROGRESSION.get(p["spirit"])
        k = s.get("progression_next", {}).get(str(i), 0)
        if lst and k < len(lst):
            c, kind = lst[k]
            out.append(f"{p['name']}'s next power card, if you gain one: {c}"
                       + (" (a Major: then forget a power)." if kind == "Major" else "."))
    return out


# Each spirit's growth options, with a picture cut from the panel (growth_<n>.jpg).
GROWTH = {
    "River Surges in Sunlight": [
        ("Reclaim + power card + energy",
         "Take every power card from your discard pile back into your hand, gain 1 new power card{nextcard}, "
         "and gain 1 energy now. Pick this when your hand is running low."),
        ("Two presence",
         "Add 2 presence to the island: take discs from either track (leftmost first) and put each in a land "
         "within 1 of your presence. Spreads you fast and uncovers bigger numbers on your tracks."),
        ("Power card + presence at range 2",
         "Gain 1 new power card{nextcard}, and add 1 presence to a land within 2 of your presence. "
         "A balance of a new power and reach."),
    ],
}


GROWTH_GAINS_CARD = {"River Surges in Sunlight": {1, 3}}
# New presence discs -> growth option, where that tells them apart.
GROWTH_BY_PRESENCE = {"River Surges in Sunlight": {0: 1, 1: 3, 2: 2}}


def _growth(s):
    g = _growth_base(s)
    before = s.get("presence_lands_at_growth") or {}
    marks = {}
    for lid, land in s["lands"].items():
        n = land.get("presence", 0) - before.get(lid, land.get("presence", 0))
        if n > 0:
            marks[lid] = {"text": f"+{n} presence (new)", "colour": "#5fd0e8"}
    marks.update(g.get("marks") or {})  # the lands a question offers win
    return {**g, "marks": marks} if marks else g


def _presence_note(s, p, n):
    need = len(rules.GROWTH_PRESENCE.get(p["spirit"], {}).get(n, []))
    if not need:
        return ""
    added = sum(l["presence"] for l in s["lands"].values()) - s.get("presence_at_growth", 0)
    if added >= need:
        return "Presence placed. "
    return (f"{need - added} presence still to place: two-finger double tap to take the option "
            f"back and pick it again, or add it on the phone. ")


def _growth_question(s, p, chosen, q, st, pictures):
    """Growth after picking an option: the one question it is asking now."""
    title = GROWTH[p["spirit"]][chosen - 1][0]
    vals = rules.TRACK_VALUES.get(p["spirit"], {})
    left = len(s.get("growth_todo") or [])
    total = len(rules.GROWTH_PRESENCE[p["spirit"]][chosen])
    which = f"presence {total - left + 1} of {total}" if total > 1 else "1 presence"
    marks = {}
    if q["kind"] == "track":
        sp = s.get("spirits", {}).get("0", {"taken": {"energy": 0, "cards": 0}})
        te, tc = sp["taken"]["energy"], sp["taken"]["cards"]
        # One line only: the screen numbers its lines, which would read like finger counts.
        do = [f"Option {chosen}, {title}: add {which}. Which track does the disc come from? "
              f"Point at that row on your panel and hold still: the energy row (top: energy each turn "
              f"{vals['energy'][min(te, len(vals['energy']) - 1)]} → {vals['energy'][min(te + 1, len(vals['energy']) - 1)]}) "
              f"or the card plays row (bottom: card plays "
              f"{vals['cards'][min(tc, len(vals['cards']) - 1)]} → {vals['cards'][min(tc + 1, len(vals['cards']) - 1)]}). "
              f"If the camera can't see your panel, hold up 1 or 2 fingers."]
        ttl = "Growth: which track?"
    else:
        lands = q["options"]
        for k, lid in enumerate(lands, 1):
            marks[lid] = {"text": str(k), "colour": "#5fd0e8"}
        src = {"energy": "the energy track", "cards": "the card plays track"}.get(q.get("track"), "your track")
        do = [f"Option {chosen}: take the leftmost disc from {src} and put it in a land within "
              f"{q['range']} of your presence. Point at one of the lit lands on the board and hold still. "
              "If the camera can't see the board, hold up the number lit on it."]
        ttl = "Growth: which land?"
    return {"title": ttl, "single": True, "do": do, "pictures": pictures, "marks": marks,
            "why": "Two-finger double tap takes the last answer back.",
            "helper": {"kind": "choose", "options": len(q["options"]), "question": q["kind"]}, "tips": []}


def _growth_base(s):
    pics, items = [], []
    chosen = s.get("growth_choice", {}).get("0")
    suggested = s.get("growth_suggest", {}).get("0")
    single = len(s["players"]) == 1
    p = s["players"][0] if s["players"] else None
    if single and p and p["spirit"] in GROWTH:
        folder = rules.SPIRIT_ART[p["spirit"]][0]
        nxt, card = "", None
        if s.get("progression") and p["spirit"] in rules.PROGRESSION:
            k = s.get("progression_next", {}).get("0", 0)
            if chosen in GROWTH_GAINS_CARD.get(p["spirit"], set()):
                k -= 1  # the choice already counted its card
            lst = rules.PROGRESSION[p["spirit"]]
            if 0 <= k < len(lst):
                card = lst[k]
                nxt = f" (the next on your progression: {card[0]}" + (", a Major: then forget a power)" if card[1] == "Major" else ")")
        items = ["Pick ONE of the three growth options at the top of your panel and do everything in it. "
                 "Here they are, one at a time:"]
        pics.append({"src": f"spirits/{folder}/growth.jpg", "wide": True, "items": [0],
                     "caption": "Growth (pick one): three options, separated by the lines"})
        for n, (title, text) in enumerate(GROWTH[p["spirit"]], 1):
            items.append(f"Option {n}, {title}: " + text.format(nextcard=nxt))
            pics.append({"src": f"spirits/{folder}/growth_{n}.jpg", "wide": True, "items": [n],
                         "caption": f"Option {n}: {title}"})
            if card and n in GROWTH_GAINS_CARD.get(p["spirit"], set()):
                pics.append({"src": f"powers/{rules.picture_slug(card[0])}.jpg", "items": [n],
                             "caption": f"You'd take: {card[0]}"})
        st = g.spirit_stats(s, 0)
        track_q = ([f"Which track did your new disc{'s' if st['unassigned'] > 1 else ''} come from? "
                    "Press E (energy, top) or C (card plays, bottom)" + (f", {st['unassigned']} to go." if st['unassigned'] > 1 else ".")]
                   if st and st["unassigned"] else [])
        q = s.get("pending")
        if chosen and q:
            return _growth_question(s, p, chosen, q, st, [dict(pp, items=[0]) for pp in pics if pp.get("items") == [chosen]])
        if chosen or suggested:
            # Picked with a key, or suggested by the camera: show just that option, big.
            # A suggestion is only taken when you press → (or a number key).
            n = chosen or suggested
            title, text = GROWTH[p["spirit"]][n - 1]
            return {
                "title": f"Growth: option {n} ✓" if chosen else f"Growth: option {n}?",
                "single": True,
                "do": ([f"Chosen: option {n}, {title}. " + text.format(nextcard=nxt),
                        _presence_note(s, p, n)
                        + "Double tap (or →) for Gain energy; two-finger double tap to go back."] if chosen else
                       [f"The camera thinks you took option {n}, {title}: " + text.format(nextcard=nxt),
                        f"Right? Press → to confirm it and go on to Gain energy. Otherwise press 1, 2 or 3."]) + track_q,
                "pictures": [dict(pp, items=[0]) for pp in pics if pp.get("items") == [n]],
                "why": "Worked out from your new presence discs." if not chosen else "",
                "helper": {"kind": "growth", "options": len(GROWTH[p["spirit"]]), "chosen": chosen},
                "tips": [],
            }
        items.append((f"You chose option {chosen}. " if chosen else
                      "Point at the option on your panel and hold still to pick it (or press 1, 2, 3 on the "
                      "remote or phone; if the camera can't see your panel, hold up 1, 2 or 3 fingers). ")
                     + "The app then walks you through it.")
    else:
        items = [
            "Each spirit picks ONE growth option on the top of their panel and does everything in it.",
            "Common pieces of growth: reclaim (take your discarded power cards back into hand), "
            + ("gain a power card (take the next card from your progression stack), " if s.get("progression")
               else "gain a power card (draw 4 minor or major, keep 1), ")
            + "add presence (move a disc from a track onto a land within the range shown), gain energy.",
        ] + _next_powers(s) + [
            "Moving presence off a track uncovers a bigger number or a new symbol. That is how a "
            "spirit gets stronger.",
        ]
    return {
        "title": "Growth",
        "do": items,
        "pictures": pics,
        "why": "Everyone does this at the same time; it does not matter who goes first.",
        "helper": {"kind": "growth", "options": len(GROWTH.get(p["spirit"], [])) if p else 0, "chosen": chosen},
        "tips": ["Running low on cards in hand? A reclaim option is usually the right choice.",
                 "Taking a Major power means forgetting (permanently removing) one card you own."],
    }


def _energy(s):
    st = g.spirit_stats(s, 0) if len(s["players"]) == 1 else None
    if st:
        ask = (["First: which track did your new disc come from? Press E (energy, top) or C (card "
                "plays, bottom). The numbers below update."] if st["unassigned"] else [])
        return {
            "title": "Gain energy",
            "single": True,
            "do": ask + [f"Take {st['energy_per_turn']} energy: the highest number uncovered on your energy track. "
                   + (f"Put the tokens on your panel's picture ({st['energy']} → {st['energy'] + st['energy_per_turn']}): "
                      "the game moves on when the camera sees them." if s.get("energy_from_camera") else
                      f"You'll have {st['energy'] + st['energy_per_turn']} (the app adds it when you press →)."),
                   f"This round you can play up to {st['card_plays']} power card"
                   f"{'s' if st['card_plays'] != 1 else ''} (your card plays track)."],
            "why": "Energy pays for power cards.",
            "tips": [],
        }
    return {
        "title": "Gain energy",
        "do": [
            "Each spirit gains energy equal to the highest number now visible on their energy track.",
            "Collect any bonus symbols that are uncovered on the track (elements count every round).",
        ],
        "why": "Energy pays for power cards.",
        "tips": [],
    }


def _powers_base(s):
    st = g.spirit_stats(s, 0) if len(s["players"]) == 1 else None
    extra = [f"You have {st['energy']} energy and can play up to {st['card_plays']} card"
             f"{'s' if st['card_plays'] != 1 else ''}. When you press →, the cost of the cards the camera "
             "sees played is paid from your energy."] if st else []
    return {
        "title": "Choose and pay for powers",
        "do": extra + [
            "Each spirit plays power cards from hand face up in front of them, up to the number "
            "visible on their card-plays track. Lay them in the camera's view, off the island: "
            "the screen lists them with their total cost.",
            "Pay each card's energy cost (top-left corner).",
            "Count the elements on the cards you played (plus any from your tracks). If they meet "
            "a threshold on one of your innate powers, that innate power will happen this round.",
        ],
        "why": "Played cards are not used yet. Fast ones happen next; slow ones after the invaders.",
        "tips": ["The colour band on a card says fast (red, lightning) or slow (blue, turtle).",
                 "Saving energy is fine; unspent energy stays with you."],
    }



def _powers(s):
    g = _powers_base(s)
    return {**g, "do": list(g["do"]) + innate.lines(s, [c["name"] for c in s.get("played", [])])}

def _fast_base(s):
    return {
        "title": "Fast powers",
        "do": [
            "Resolve every fast power card and fast innate power, in any order the group likes.",
            "Read the target: range from your presence (or sacred site), and the kind of land allowed.",
            "Tap +Fear whenever a power generates fear, and update pieces in the Island panel if "
            "you are tracking them.",
        ],
        "why": "Fast powers act before the invaders: good for stopping a ravage or build that is "
               "about to happen. Check the Ravage and Build cards on the invader board.",
        "tips": _invader_threat_tips(s),
    }



def _fast(s):
    g = _fast_base(s)
    return {**g, "do": list(g["do"]) + innate.lines(s, [c["name"] for c in s.get("played", [])])}

def _invader_threat_tips(s):
    slots = s["invaders"]["slots"]
    tips = []
    if slots["ravage"]:
        tips.append(f"This round's ravage hits {rules.card_label(slots['ravage'])}.")
    if slots["build"]:
        tips.append(f"This round's build happens in {rules.card_label(slots['build'])}.")
    return tips


def _blighted(s):
    return {
        "title": "Blighted island",
        "do": ["The blight card is on its blighted side. Do whatever it says happens each round."],
        "why": "A blighted island makes the game harder until the end.",
        "tips": [],
    }


def _fear(s):
    n = s["fear"]["unresolved"]
    tl = g.terror_level(s)
    return {
        "title": f"Fear cards ({n} to resolve)",
        "do": [
            f"Take the {n} earned fear card{'s' if n > 1 else ''} in the order you earned them and "
            "flip them face up one at a time.",
            f"Read the effect for Terror Level {tl} (the current level) and do it.",
            "Tap Resolved after each card.",
        ],
        "why": "Earned fear cards wait face down until now. Higher terror levels give stronger effects.",
        "tips": [_victory_text(tl)],
        "helper": {"kind": "fear_cards", "left": n},
    }


def _victory_text(tl):
    return {
        1: "Terror level 1 victory: no invaders of any kind left on the island.",
        2: "Terror level 2 victory: no towns and no cities left on the island.",
        3: "Terror level 3 victory: no cities left on the island.",
    }[tl]


COLOURS = {"blight": "#ff6b6b", "cities": "#ff8f6b", "towns": "#f2c14e", "explorers": "#7fc8f8",
           "dahan": "#ff6b6b", None: "#8a948c"}


def _colour(changes):
    for p in ("blight", "cities", "towns", "explorers", "dahan"):
        if changes.get(p):
            return COLOURS[p]
    return COLOURS[None]


def _plan_items(rows):
    """One instruction per land: what to place or remove, then why."""
    items, marks = [], {}
    for r in rows:
        n = invader_plan.land_number(r["land"])
        what = r["text"]
        if not r["changes"]:
            items.append({"text": f"Land {n}: nothing, because {r['why']}", "colour": COLOURS[None]})
            marks[r["land"]] = {"text": "nothing", "colour": COLOURS[None]}
            continue
        what = what[0].upper() + what[1:]
        items.append({"text": f"Land {n}: {what}. Why: {r['why']}", "colour": _colour(r["changes"])})
        # Several rows can land in one land (its own ravage and a cascade into it).
        old = marks.get(r["land"])
        marks[r["land"]] = {"text": (old["text"] + "; " if old and old["text"] != "nothing" else "") + r["text"],
                            "colour": _colour(r["changes"])}
    return items, marks


def _plan_helper(kind, rows):
    return {"kind": kind, "rows": [{"land": r["land"], "text": r["text"], "why": r["why"],
                                    "changes": r["changes"], "explore": "yes" if r["changes"] else "no"}
                                   for r in rows]}


def _ravage(s):
    card = s["invaders"]["slots"]["ravage"]
    if not card:
        return {"title": "Ravage", "do": ["No card in the Ravage space yet, so nothing ravages. Press Next."],
                "why": "Cards reach the Ravage space after two rounds on the board.", "tips": []}
    rows = invader_plan.ravage_plan(s, card)
    items, marks = _plan_items(rows)
    if not rows:
        items = [f"No {rules.card_label(card)} land has invaders, so nothing ravages. Press Next."]
    else:
        items.append("Make these changes on the table, then press Next. The app has already worked them out.")
    return {
        "title": f"Ravage: {rules.card_label(card)}",
        "single": True,
        "do": [f"Ravage card: {rules.card_label(card)}."] + items,
        "why": "Rule: invaders deal damage (explorer 1, town 2, city 3). 2 or more adds a blight, and a land "
               "that already had blight cascades one into a neighbour. The damage also destroys Dahan (2 each), "
               "and surviving Dahan fight back for 2 each.",
        "tips": ["If a power gave a land Defend, change that land by hand on the phone before pressing Next."]
                if rows else [],
        "helper": _plan_helper("ravage", rows),
        "marks": marks,
    }


def _build(s):
    card = s["invaders"]["slots"]["build"]
    if not card:
        return {"title": "Build", "do": ["No card in the Build space yet, so nothing builds. Press Next."],
                "why": "", "tips": []}
    rows = invader_plan.build_plan(s, card)
    items, marks = _plan_items(rows)
    if not rows:
        items = [f"No {rules.card_label(card)} land has invaders, so nothing builds. Press Next."]
    else:
        items.append("Place them, then press Next.")
    return {
        "title": f"Build: {rules.card_label(card)}",
        "single": True,
        "do": [f"Build card: {rules.card_label(card)}."] + items,
        "why": "Rule: a land with invaders adds a city if it has more towns than cities, otherwise a town. "
               "Dahan don't stop a build.",
        "tips": [],
        "helper": _plan_helper("build", rows),
        "marks": marks,
    }


def _explore(s):
    slot = s["invaders"]["slots"]["explore"]
    helper = {"kind": "reveal", "options": g.possible_next_cards(s),
              "stage": g.next_invader_stage(s), "left": g.invader_cards_left(s)}
    if not slot:
        return {
            "title": "Explore",
            "do": [
                f"Turn over the top invader card (Stage {helper['stage']}, "
                f"{helper['left']} left) and put it in the Explore space.",
                "Tap that card below.",
            ],
            "why": "Explore brings new invaders onto the island.",
            "tips": ["Stage II includes a 'Coastal lands' card; Stage III cards name two terrains."],
            "helper": helper,
        }
    rows = invader_plan.explore_plan(s, slot)
    items, marks = _plan_items(rows)
    helper.update(_plan_helper("reveal", rows))
    return {
        "title": f"Explore: {rules.card_label(slot)}",
        "single": True,
        "do": [f"Explore card: {rules.card_label(slot)}."] + items
              + ["Place the explorers, then press Next."],
        "why": "Rule: a land gets an explorer if it touches the ocean, has a town or city, or is next to a "
               "land with a town or city.",
        "tips": [],
        "helper": helper,
        "marks": marks,
    }


def _advance(s):
    slots = s["invaders"]["slots"]
    return {
        "title": "Advance invader cards",
        "pictures": [{"anim": "advance", "wide": True, "items": [0],
                      "slots": {k: slots.get(k) for k in ("ravage", "build", "explore")},
                      "caption": "Each card slides one space left"}],
        "do": [
            "Slide the invader cards one space left: Ravage card to the discard pile, Build card to "
            "Ravage, Explore card to Build.",
            "The camera moves on by itself once it sees the cards shifted (or tap Next).",
        ],
        "why": "So each card explores, then builds the next round, then ravages the round after: "
               "you always see two rounds of trouble coming.",
        "tips": [],
    }


def _slow_base(s):
    return {
        "title": "Slow powers",
        "do": ["Resolve every slow power card and slow innate power, in any order.",
               "Tap +Fear when fear is generated and update pieces if you are tracking them."],
        "why": "Slow powers happen after the invaders, so they can clean up or prepare for next round.",
        "tips": [_victory_text(g.terror_level(s))],
    }



def _slow(s):
    g = _slow_base(s)
    return {**g, "do": list(g["do"]) + innate.lines(s, [c["name"] for c in s.get("played", [])])}

DAMAGE_CARDS = {"Flash Floods", "Pull Beneath the Hungry Earth", "Accelerated Rot", "Tsunami", "Massive Flooding"}


def _damage_this_round(s):
    """Did anything take damage this round: a ravage that happened, or a damaging power?"""
    if DAMAGE_CARDS & set(s.get("resolved", {})):
        return True
    return any(e.get("round") == s["round"] and e.get("step") == "invader.ravage" and not e["text"].startswith("Next")
               for e in s.get("log", []))


def _time_passes(s):
    return {
        "title": "Time passes",
        "do": [
            "Every spirit discards the power cards played this round to their own discard pile.",
            ("Any damage heals: invaders and Dahan that were hurt but not destroyed are back to full "
             "health." if _damage_this_round(s) else
             "Any damage would heal now, but nothing took damage this round, so there's nothing to do."),
            "Elements and any 'this round' effects end. Energy stays.",
        ],
        "why": "Each round starts fresh except for what is on the island and in your energy.",
        "tips": [f"Next round is round {s['round'] + 1}. {g.invader_cards_left(s)} invader cards left in the deck."],
    }


_STEPS = {
    "setup.welcome": _welcome,
    "setup.players": _players,
    "setup.island": _island,
    "setup.spirits": _spirits,
    "setup.invader_board": _invader_board,
    "setup.pieces": _pieces,
    "setup.cards": _cards,
    "setup.first_explore": _first_explore,
    "spirit.growth": _growth,
    "spirit.energy": _energy,
    "spirit.powers": _powers,
    "fast": _fast,
    "invader.blighted": _blighted,
    "invader.fear": _fear,
    "invader.ravage": _ravage,
    "invader.build": _build,
    "invader.explore": _explore,
    "invader.advance": _advance,
    "slow": _slow,
    "time_passes": _time_passes,
}
