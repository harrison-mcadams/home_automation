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

## Two screens: TV and phone

The same server gives two pages that follow one game, so a tap on either shows
on the other at once. Use both together, or either alone.

- **TV (couch view):** `http://<this computer>:5055/tv` in the TV's browser.
  Big type for across the room: round, terror level, fear and blight meters,
  the round's steps with the current one lit, what to do right now (with the
  lands it affects and what will happen in each), the invader cards, every land's
  pieces, and the latest board photo. Words from the rules are explained under
  the instructions. A remote or keyboard can drive it alone: right arrow or
  Enter = next step, left arrow = undo, F = +1 fear.
- **Phone (controls):** `http://<this computer>:5055/phone` (or just `/`).
  Everything you tap: setup, revealing cards, applying ravage/build/explore,
  fixing piece counts, fear, undo. The *Game* tab lists the TV address.

At home: `http://192.168.1.169:5055`. Away over Tailscale: `http://100.98.2.44:5055`.
(Set `public_urls` in `config.json` if those change.)

## Camera

**Off by default (since the 2026-11 redesign).** The game is the truth about the
board: it tells you where to put pieces and never checks the table. With
`camera_tracking` off, the camera can only report a card it read; it can't
change pieces, steps or energy, and the background watchers (piece tracking,
invader slots, power cards, spirit panel) don't start.

To bring back the old live tracking, set `"camera_tracking": true` in
`config.json` or start with `--camera-tracking`. The notes below describe that mode.

If the live board page is running (`python -m spirit_island.board_view ...`,
port 8091), the dashboard reads its *settled* reading every few seconds. That
page already copes with a moved camera or board and holds its reading while a
hand is over the board, so the dashboard only ever sees readings most recent
photos agree on. It never touches the camera itself.

- The TV shows the board photo and marks lands where the camera disagrees with
  the tracker ("cam +1 town").
- The phone's *Camera* tab lists those lands with a *Use camera* button each
  (or all at once), lets you say which board the camera looks at, and has an
  *Auto-sync* switch that copies settled readings in during play. Camera changes
  are logged as "camera" and Undo-able.
- Presence of all colours counts together; energy tokens are ignored.
- Without the board page the dashboard works as before. `--board-camera ''`
  turns the link off; `--board-camera http://host:8091` points it elsewhere.

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
  blight and presence. Each land's terrain is filled in from the printed layout of
  base boards A to D (balanced side), so the app highlights which lands ravage,
  build and explore, and offers one-tap **Apply** for the standard result. Tap a
  terrain to change it (e.g. for the thematic side); changes are remembered.
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
