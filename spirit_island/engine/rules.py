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


# Pictures of each spirit's panel and its 4 unique power cards, kept under
# assets/spirits/<folder>/ (gitignored; fetched from the open-source Tabletop Simulator mod).
SPIRIT_ART = {
    'River Surges in Sunlight': ('river', ['Boon of Vigor', 'Flash Floods', "River's Bounty", 'Wash Away']),
    "Lightning's Swift Strike": ('lightning', ['Harbingers of the Lightning', "Lightning's Boon", 'Raging Storm', 'Shatter Homesteads']),
    'Vital Strength of the Earth': ('earth', ['A Year of Perfect Stillness', 'Draw of the Fruitful Earth', 'Guard the Healing Land', 'Rituals of Destruction']),
    'Shadows Flicker Like Flame': ('shadows', ['Concealing Shadows', 'Crops Wither and Fade', 'Favors Called Due', 'Mantle of Dread']),
    'A Spread of Rampant Green': ('green', ['Fields Choked with Growth', 'Gift of Proliferation', 'Overgrow in a Night', 'Stem the Flow of Fresh Water']),
    'Thunderspeaker': ('thunderspeaker', ['Manifestation of Power and Glory', 'Sudden Ambush', 'Voice of Thunder', 'Words of Warning']),
    "Ocean's Hungry Grasp": ('ocean', ['Call of the Deeps', 'Grasping Tide', 'Swallow the Land-Dwellers', 'Tidal Boon']),
    'Bringer of Dreams and Nightmares': ('bringer', ["Call on Midnight's Dream", 'Dreams of the Dahan', 'Predatory Nightmares', 'Dread Apparitions']),
}


# Where the presence-track circles sit on the panel pictures (panel_front.jpg, 1600 x 1066):
# the first circle of each row, the gap between circles, and how many circles per row.
PANEL_SIZE = (1600, 1066)
PRESENCE_TRACKS = {
    "River Surges in Sunlight": {"x0": 682, "dx": 117.2, "energy_y": 320, "energy": 7, "cards_y": 489, "cards": 7},
    "Lightning's Swift Strike": {"x0": 697, "dx": 116.6, "energy_y": 319, "energy": 8, "cards_y": 490, "cards": 5},
    "Vital Strength of the Earth": {"x0": 703, "dx": 117.4, "energy_y": 321, "energy": 6, "cards_y": 489, "cards": 6},
}

# Numbers printed on the presence tracks, left to right (the first is uncovered at the start).
# A space without a number keeps the one before it (River's "Reclaim One").
TRACK_VALUES = {
    "River Surges in Sunlight": {"energy": [1, 2, 2, 3, 4, 4, 5], "cards": [1, 2, 2, 3, 3, 4, 5]},
}
# Energy a growth option gives right away.
GROWTH_ENERGY = {"River Surges in Sunlight": {1: 1}}
# Presence each growth option adds, as the range from your presence for each disc.
GROWTH_PRESENCE = {"River Surges in Sunlight": {1: [], 2: [1, 1], 3: [2]}}

# Starting presence from each panel's back: (terrain, discs) in the highest-numbered land
# of that terrain on the player's board.
START_PRESENCE = {
    "River Surges in Sunlight": [("W", 1)],
    "Lightning's Swift Strike": [("S", 2)],
    "Vital Strength of the Earth": [("M", 2), ("J", 1)],
}

# Recommended power progressions (from each spirit's Power Progression card): when you gain
# a power card, take the next one instead of drawing. A Major means forgetting a power.
PROGRESSION = {
    "River Surges in Sunlight": [("Uncanny Melting", "Minor"), ("Nature's Resilience", "Minor"),
        ("Pull Beneath the Hungry Earth", "Minor"), ("Accelerated Rot", "Major"), ("Song of Sanctity", "Minor"),
        ("Tsunami", "Major"), ("Encompassing Ward", "Minor")],
    "Lightning's Swift Strike": [("Delusions of Danger", "Minor"), ("Call to Bloodshed", "Minor"),
        ("Powerstorm", "Major"), ("Purifying Flame", "Minor"), ("Pillar of Living Flame", "Major"),
        ("Entrancing Apparitions", "Minor"), ("Call to Isolation", "Minor")],
    "Vital Strength of the Earth": [("Rouse the Trees and Stones", "Minor"), ("Call to Migrate", "Minor"),
        ("Poisoned Land", "Major"), ("Devouring Ants", "Minor"), ("Vigor of the Breaking Dawn", "Major"),
        ("Voracious Growth", "Minor"), ("Savage Mawbeasts", "Minor")],
}

# Energy cost and speed of the power cards the app can recognise.
POWER_INFO = {
    "Boon of Vigor": (0, "fast"), "Flash Floods": (2, "fast"), "River's Bounty": (0, "slow"), "Wash Away": (1, "slow"),
    "Uncanny Melting": (1, "slow"), "Nature's Resilience": (1, "fast"), "Pull Beneath the Hungry Earth": (1, "slow"),
    "Accelerated Rot": (4, "slow"), "Song of Sanctity": (1, "slow"), "Tsunami": (6, "slow"),
    "Encompassing Ward": (1, "fast"),
}

# What each recognised power card can target: range from your presence, which lands
# ("any", terrain letters, or "coastal"), or a spirit instead of a land.
POWER_TARGETS = {
    "Boon of Vigor": {"spirit": True},
    "Encompassing Ward": {"spirit": True},
    "Flash Floods": {"range": 1, "land": "any"},
    "River's Bounty": {"range": 0, "land": "any"},
    "Wash Away": {"range": 1, "land": "any"},
    "Uncanny Melting": {"range": 1, "land": "any"},
    "Nature's Resilience": {"range": 1, "land": "any"},
    "Pull Beneath the Hungry Earth": {"range": 1, "land": "any"},
    "Accelerated Rot": {"range": 2, "land": "JW"},
    "Song of Sanctity": {"range": 1, "land": "MJ"},
    "Tsunami": {"range": 2, "land": "coastal"},
}

# Starting pieces printed on each balanced board (expansion icons left out).
START_PIECES = {
    "A": {2: {"cities": 1, "dahan": 1}, 3: {"dahan": 2}, 4: {"blight": 1}, 6: {"dahan": 1}, 7: {"dahan": 2}, 8: {"towns": 1}},
    "B": {1: {"dahan": 1}, 2: {"cities": 1}, 3: {"dahan": 2}, 4: {"blight": 1}, 6: {"towns": 1}, 7: {"dahan": 1}, 8: {"dahan": 2}},
    "C": {1: {"dahan": 1}, 2: {"cities": 1}, 3: {"dahan": 2}, 5: {"dahan": 2, "blight": 1}, 6: {"dahan": 1}, 7: {"towns": 1}},
    "D": {1: {"dahan": 2}, 2: {"cities": 1, "dahan": 1}, 5: {"dahan": 1, "blight": 1}, 7: {"towns": 1, "dahan": 2}},
}

# Size of the clean board scans (assets/boards/*.png) that board_seeds.json points into.
SCAN_SIZE = (3800, 2542)


def picture_slug(name):
    return "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")


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
