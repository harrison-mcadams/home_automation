# Spirit Island Guide and Tracker

A phone-friendly page that walks you through a game of Spirit Island step by
step and keeps track of the game as you go. It needs no camera: you play on the
real table, it tells you what to do next, and you tap what changed. Later
stages of the project will let the camera fill in the same state.

It runs the same on Windows and macOS. Commands use `python`; on Windows that may
be `py`, on macOS `python3`.

## Start it

From the `home_automation` folder:

```bash
python -m pip install -r spirit_island/requirements.txt   # once
python -m spirit_island.app
```

It prints two addresses. Open the `localhost` one on the computer, or the other
one (e.g. `http://192.168.1.20:5055`) on a phone or tablet on the same Wi-Fi.
Every open page stays in sync.

- **Windows:** the first time, Windows Firewall asks whether Python may accept
  connections. Allow it on *Private networks* or the phone can't connect.
- Change the port in `spirit_island/config.json` or with `--port 6000`.

## Using it at the table

- The big card says what phase you are in and **what to do on the table now**,
  with a short "why" underneath. Do it, then tap **Next**.
- **+1 Fear** whenever a power generates fear. The app moves fear markers, earns
  fear cards, raises the terror level and declares victory when the fear deck
  is gone.
- On **Explore**, tap the invader card you turned over. The app slides cards from
  Explore to Build to Ravage like the invader board does, and knows when the
  deck runs out.
- **Undo** reverses the last tap, any number of times.
- **Island** lists every land with counters for explorers, towns, cities, Dahan,
  blight and presence. Tracking pieces is optional. If you do, tag each land's
  terrain once (tap "terrain?" to cycle) and the app highlights which lands
  ravage, build and explore, and offers one-tap **Apply** for the standard result.
  Terrain tags are remembered for future games.
- **Learn** explains the words the game uses. **Game** has corrections, the
  blight card flip, ending the game and starting a new one.

The rules text is our own summary of the base game for learning. When a card,
panel or the rulebook says something different, follow the printed component
and correct the numbers here.

## Files

- `engine/`: game state, rules and step-by-step guidance; pure Python, no
  dependencies. Tests: `python -m pytest spirit_island`.
- `app.py`, `templates/`, `static/`: the Flask page and API.
- `games/` (not in git): the current game, saved after every tap, so a restart
  picks up where you left off; plus remembered board terrains.

## For the camera stages

Everything goes through `POST /api/action`. A perception step can send
`{"type": "observe", "source": "vision", "lands": {"A2": {"explorers": 2}},
"slots": {"build": "M"}}` and every open dashboard updates. Each change is
logged with its source.
