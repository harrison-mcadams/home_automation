"""Base-game reference data for Spirit Island.

Everything here is written in our own words from general knowledge of the
game. Where a number is easy to misremember it is a setting the players can
change at setup, and the dashboard tells them to trust the printed component
over this file.
"""

TERRAINS = {
    "J": "Jungle",
    "W": "Wetland",
    "S": "Sands",
    "M": "Mountain",
}

# Invader cards by stage. A letter is a terrain; "C" means every coastal land;
# Stage III cards name two terrains.
INVADER_CARDS = {
    1: ["J", "W", "S", "M"],
    2: ["J", "W", "S", "M", "C"],
    3: ["JW", "JS", "JM", "WS", "WM", "SM"],
}

# Without an adversary the deck is 3 Stage I, 4 Stage II and 5 Stage III cards,
# with one random card of each stage left in the box unseen.
DEFAULT_DECK_STAGES = [1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3]

# Fear cards per terror level (top of deck first). Adversaries can change this.
DEFAULT_FEAR_DECK = [3, 3, 3]
FEAR_PER_PLAYER = 4
BLIGHT_PER_PLAYER = 2
BLIGHT_EXTRA = 1

PIECES = {
    # name: (health, damage it deals when ravaging / fighting back)
    "explorers": (1, 1),
    "towns": (2, 2),
    "cities": (3, 3),
    "dahan": (2, 2),
}
INVADER_PIECES = ("explorers", "towns", "cities")
LAND_PIECES = ("explorers", "towns", "cities", "dahan", "blight", "presence")

BOARDS = ["A", "B", "C", "D"]
LANDS_PER_BOARD = 8
# Lands 1 to 3 on each base board touch the ocean. Editable per land.
DEFAULT_COASTAL = {1, 2, 3}

SPIRITS = [
    {"name": "River Surges in Sunlight", "complexity": "Low",
     "style": "Moves invaders and Dahan around and floods the Wetlands. A gentle first spirit."},
    {"name": "Lightning's Swift Strike", "complexity": "Low",
     "style": "Turns slow powers fast and hits invaders before they can act."},
    {"name": "Vital Strength of the Earth", "complexity": "Low",
     "style": "Sturdy defender of the Mountains; protects lands from ravages."},
    {"name": "Shadows Flicker Like Flame", "complexity": "Low",
     "style": "Reaches far across the island and spreads fear."},
    {"name": "A Spread of Rampant Green", "complexity": "Moderate",
     "style": "Spreads presence fast and chokes invader builds with plant life."},
    {"name": "Thunderspeaker", "complexity": "Moderate",
     "style": "Leads the Dahan to war; strongest where the Dahan gather."},
    {"name": "Ocean's Hungry Grasp", "complexity": "High",
     "style": "Drags coastal invaders into the sea; awkward away from the coast."},
    {"name": "Bringer of Dreams and Nightmares", "complexity": "High",
     "style": "Frightens instead of harming; wins by fear, not destruction."},
]

ADVERSARIES = ["None", "Brandenburg-Prussia", "England", "Sweden"]

GLOSSARY = [
    ("Spirit", "You. Each player is a spirit of the island with its own panel, powers and presence."),
    ("Presence", "Your discs on the island. They show where you can reach. Lose every disc and the game is lost."),
    ("Sacred site", "A land with two or more of one spirit's presence. Some powers measure range from these."),
    ("Invaders", "The colonists: explorers (small, 1 health), towns (2 health) and cities (3 health)."),
    ("Dahan", "The island's native people, 2 health each. They fight back when invaders ravage their land."),
    ("Blight", "Damage to the land. Comes from the blight card; if the card runs dry the island is lost."),
    ("Fear", "Scaring invaders. Enough fear earns fear cards; earn the whole fear deck and you win."),
    ("Terror level", "Rises as fear cards are earned (1, 2, 3). Higher terror makes fear cards stronger and winning easier."),
    ("Energy", "Your currency for paying power cards. Gained each round from your energy track."),
    ("Elements", "Symbols on played cards (sun, moon, fire...). Enough of them switch on your innate powers."),
    ("Fast / Slow", "Every power is fast (before the invaders act) or slow (after them)."),
    ("Range", "How many lands away from your presence a power can target. Range 0 means a land with your presence."),
    ("Damage and health", "Damage destroys a piece once it reaches that piece's health. Damage heals at end of round."),
    ("Ravage", "Invaders attack a land: they hurt the land (blight) and the Dahan, then surviving Dahan fight back."),
    ("Build", "Invaders add a town or city where they already are."),
    ("Explore", "New explorers arrive in lands next to the ocean or near towns and cities."),
    ("Push / Gather", "Move pieces out of a land to adjacent ones / into a land from adjacent ones."),
    ("Defend", "Reduces the damage invaders deal in that land this round."),
]


# Terrain of lands 1 to 8 on the balanced (lettered) side of each base-game board,
# read off the printed boards. Used to tag lands automatically; any land can still be
# changed by hand (e.g. when playing the thematic side).
BOARD_TERRAINS = {
    "A": "MWJSWMSJ",
    "B": "WMSJSWMJ",
    "C": "JSMJWSMW",
    "D": "WJWSMJSM",
}


def default_terrains(boards):
    return {f"{b}{i}": t for b in boards if b in BOARD_TERRAINS for i, t in enumerate(BOARD_TERRAINS[b], 1)}


def land_ids(boards):
    return [f"{b}{n}" for b in boards for n in range(1, LANDS_PER_BOARD + 1)]


def card_label(card):
    if card is None:
        return "-"
    if card == "C":
        return "Coastal lands"
    return " + ".join(TERRAINS[c] for c in card)


def is_card(card):
    return any(card in cards for cards in INVADER_CARDS.values())
