"""Plain-English guidance for each step: what to do at the table right now.

The text is our own summary of the base game rules, aimed at someone learning
to play. When it disagrees with a printed card or panel, the printed component
wins (that is also how the real game works).
"""

from . import game as g
from . import rules


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
           "why": "", "tips": [], "helper": None}
    if fn:
        out.update(fn(state))
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


def _players(s):
    return {
        "title": "Choose players and spirits",
        "do": [
            "Pick how many players (1 or 2 is a great start) and give each a spirit.",
            "For a first game choose Low complexity spirits. River Surges in Sunlight and Vital "
            "Strength of the Earth are friendly to learn.",
            "Skip the adversary for your first games; it is an optional extra challenge.",
        ],
        "why": "Each spirit plays very differently. The complexity is printed on the back of its panel.",
        "tips": [],
        "helper": {"kind": "configure"},
    }


def _island(s):
    n = len(s["players"])
    return {
        "title": "Lay out the island",
        "do": [
            f"Take {n} island board{'s' if n > 1 else ''} ({', '.join(s['boards'])}), one per player.",
            "Use the side with the lettered lands (the standard, balanced side).",
            "With two boards, put them edge to edge so the ocean edges face away from each other; "
            "the rulebook shows the suggested layouts.",
            "Each board has 8 numbered lands plus an ocean. Lands are Jungle, Mountain, Sands or Wetland.",
        ],
        "why": "Invader cards name a terrain, and every land of that terrain is affected.",
        "tips": ["Optional but useful: open Island and tap each land's terrain once. The app remembers "
                 "it for future games and can then tell you exactly which lands ravage, build and explore."],
    }


def _spirits(s):
    return {
        "title": "Set up each spirit",
        "do": [
            "Each player takes their spirit panel and its 4 unique power cards (the ones with the "
            "spirit's name). Those are your starting hand.",
            "Fill every empty circle on the panel's two presence tracks (energy and card plays) with "
            "presence discs in your colour.",
            "The back of the panel shows where your starting presence goes on the island (often "
            "in a specific terrain). Place those discs now.",
            "Take any special pieces your panel mentions.",
        ],
        "why": "Presence on the tracks is what you will move onto the island as you grow; uncovering "
               "track spaces gives you more energy and more card plays.",
        "tips": ["Tap the Presence counts in the Island panel if you want the app to track them."],
    }


def _invader_board(s):
    f = s["fear"]
    return {
        "title": "Set up the invader board",
        "do": [
            f"Fear pool: put {f['pool_size']} fear markers in the fear pool (4 per player).",
            f"Fear deck: shuffle the fear cards and build a deck of {sum(f['deck'])}: "
            f"{f['deck'][0]} cards, the Terror Level II divider, {f['deck'][1]} cards, the Terror "
            f"Level III divider, then {f['deck'][2]} cards at the bottom.",
            f"Blight: put the blight card healthy-side up with {s['blight']['pool']} blight on it "
            "(2 per player plus 1).",
            "Invader deck: sort invader cards by stage (the I, II, III on the back). Remove one "
            "random card of each stage without looking. Shuffle each stage and stack them with "
            "Stage III at the bottom, Stage II in the middle, Stage I on top: 3 + 4 + 5 = 12 cards.",
        ],
        "why": "The fear deck is your victory clock; the invader deck is your defeat clock.",
        "tips": ["An adversary changes these numbers. If you use one, follow its setup and correct the "
                 "pools in Settings."] if s["adversary"]["name"] != "None" else [],
    }


def _pieces(s):
    return {
        "title": "Place the starting pieces",
        "do": [
            "Each land shows small icons for its starting pieces: Dahan, towns, cities and sometimes "
            "blight. Put those pieces on each land now.",
            "Blight placed during setup comes from the box, not from the blight card.",
            "Put the rest of the pieces in easy reach.",
        ],
        "why": "This is the island as the invaders first find it.",
        "tips": ["To have the app track the board, enter each land's pieces in the Island panel. "
                 "It is optional: the step-by-step guide works without it."],
    }


def _cards(s):
    return {
        "title": "Power card decks",
        "do": [
            "Shuffle the Minor Power deck and the Major Power deck separately and set them nearby.",
            "Leave room for each player's discard pile next to their panel.",
        ],
        "why": "As you grow you draw new powers from these decks.",
        "tips": [],
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
              "or is next to a land with a town or city."] + _unknown_note(unknown)
        helper["rows"] = [{"land": lid, "explore": g.explore_preview(s["lands"][lid])} for lid in hit]
    return {
        "title": "First explore",
        "do": do,
        "why": "The invaders scout the island before the first round. When you tap Next the card "
               "slides to the Build space, so these lands will build in round 1.",
        "tips": [],
        "helper": helper,
    }


# --- round --------------------------------------------------------------------

def _growth(s):
    return {
        "title": "Growth",
        "do": [
            "Each spirit picks ONE growth option on the top of their panel and does everything in it.",
            "Common pieces of growth: reclaim (take your discarded power cards back into hand), "
            "gain a power card (draw 4 minor or major, keep 1), add presence (move a disc from a "
            "track onto a land within the range shown), gain energy.",
            "Moving presence off a track uncovers a bigger number or a new symbol. That is how a "
            "spirit gets stronger.",
        ],
        "why": "Everyone does this at the same time; it does not matter who goes first.",
        "tips": ["Running low on cards in hand? A reclaim option is usually the right choice.",
                 "Taking a Major power means forgetting (permanently removing) one card you own."],
    }


def _energy(s):
    return {
        "title": "Gain energy",
        "do": [
            "Each spirit gains energy equal to the highest number now visible on their energy track.",
            "Collect any bonus symbols that are uncovered on the track (elements count every round).",
        ],
        "why": "Energy pays for power cards.",
        "tips": [],
    }


def _powers(s):
    return {
        "title": "Choose and pay for powers",
        "do": [
            "Each spirit plays power cards from hand face up in front of them, up to the number "
            "visible on their card-plays track.",
            "Pay each card's energy cost (top-left corner).",
            "Count the elements on the cards you played (plus any from your tracks). If they meet "
            "a threshold on one of your innate powers, that innate power will happen this round.",
        ],
        "why": "Played cards are not used yet. Fast ones happen next; slow ones after the invaders.",
        "tips": ["The colour band on a card says fast (red, lightning) or slow (blue, turtle).",
                 "Saving energy is fine; unspent energy stays with you."],
    }


def _fast(s):
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


def _ravage(s):
    card = s["invaders"]["slots"]["ravage"]
    if not card:
        return {"title": "Ravage", "do": ["No card in the Ravage space yet, so nothing ravages. Tap Next."],
                "why": "Cards reach the Ravage space after two rounds on the board.", "tips": []}
    hit, unknown = _lands_for(s, card)
    rows = []
    for lid in hit:
        land = s["lands"][lid]
        if g.invaders_in(land):
            rows.append({"land": lid, **g.ravage_preview(land)})
    do = [
        f"Ravage card: {rules.card_label(card)}. In every land of that terrain that has invaders:",
        "1. Add up invader damage: explorer 1, town 2, city 3 (minus any Defend from powers).",
        "2. If that is 2 or more, add 1 blight from the blight card to the land. If the land already "
        "had blight, the blight cascades: add one more to an adjacent land too (your choice). Each "
        "time blight lands, it destroys a Presence there.",
        "3. The same damage hits the Dahan: each 2 damage destroys a Dahan (health 2).",
        "4. Surviving Dahan fight back: 2 damage each, split among the invaders as you like "
        "(explorer 1 health, town 2, city 3).",
    ] + _unknown_note(unknown)
    if hit and not rows:
        do.append("By the tracked pieces no matching land has invaders, so nothing ravages.")
    return {
        "title": "Ravage",
        "do": do,
        "why": "Ravages are how the island gets blighted. Stopping them is a big part of the game.",
        "tips": ["Use 'Apply' for a land if no power changed it; otherwise adjust pieces by hand."] if rows else [],
        "helper": {"kind": "ravage", "rows": rows},
    }


def _build(s):
    card = s["invaders"]["slots"]["build"]
    if not card:
        return {"title": "Build", "do": ["No card in the Build space yet, so nothing builds. Tap Next."],
                "why": "", "tips": []}
    hit, unknown = _lands_for(s, card)
    rows = [{"land": lid, "adds": g.build_preview(s["lands"][lid])}
            for lid in hit if g.build_preview(s["lands"][lid])]
    return {
        "title": "Build",
        "do": [
            f"Build card: {rules.card_label(card)}. In every land of that terrain that has any invaders:",
            "If the land has more towns than cities, add a city. Otherwise add a town.",
            "Lands with no invaders do not build.",
        ] + _unknown_note(unknown),
        "why": "Towns and cities hit hard when they ravage later, so builds matter.",
        "tips": [],
        "helper": {"kind": "build", "rows": rows},
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
    hit, unknown = _lands_for(s, slot)
    rows = [{"land": lid, "explore": g.explore_preview(s["lands"][lid])} for lid in hit]
    helper.update({"rows": rows})
    return {
        "title": "Explore",
        "do": [
            f"Explore card: {rules.card_label(slot)}. Add 1 explorer to each land of that terrain that is:",
            "next to the ocean (coastal), OR has a town or city in it, OR is next to a land with a "
            "town or city.",
        ] + _unknown_note(unknown),
        "why": "Invaders arrive by sea and spread out from their settlements.",
        "tips": ["Lands marked 'check' only get an explorer if a neighbouring land has a town or city."],
        "helper": helper,
    }


def _advance(s):
    return {
        "title": "Advance invader cards",
        "do": [
            "Slide the invader cards one space left: Ravage card to the discard pile, Build card to "
            "Ravage, Explore card to Build.",
            "Tap Next and the app moves them too.",
        ],
        "why": "So each card explores, then builds the next round, then ravages the round after: "
               "you always see two rounds of trouble coming.",
        "tips": [],
    }


def _slow(s):
    return {
        "title": "Slow powers",
        "do": ["Resolve every slow power card and slow innate power, in any order.",
               "Tap +Fear when fear is generated and update pieces if you are tracking them."],
        "why": "Slow powers happen after the invaders, so they can clean up or prepare for next round.",
        "tips": [_victory_text(g.terror_level(s))],
    }


def _time_passes(s):
    return {
        "title": "Time passes",
        "do": [
            "Every spirit discards the power cards played this round to their own discard pile.",
            "All damage heals: damaged invaders and Dahan are back to full health.",
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
