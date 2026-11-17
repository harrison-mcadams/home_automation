// Spirit Island guide: renders server state and sends taps as actions.
"use strict";

let S = null;          // last snapshot from the server
let REF = null;        // reference data (spirits, terrains, glossary)
let LINKS = null;      // addresses of the phone and TV pages
let tab = "island";
const $ = (id) => document.getElementById(id);
const PIECE_LABEL = { explorers: "Explorers", towns: "Towns", cities: "Cities", dahan: "Dahan",
  blight: "Blight", presence: "Presence" };
const SETUP_STEPS = ["setup.welcome", "setup.players", "setup.island", "setup.spirits", "setup.invader_board",
  "setup.pieces", "setup.cards", "setup.first_explore"];
const ROUND_STEPS = ["spirit.growth", "spirit.energy", "spirit.powers", "fast", "invader.blighted",
  "invader.fear", "invader.ravage", "invader.build", "invader.explore", "invader.advance", "slow", "time_passes"];

// Starting-piece check: each land the camera covers, what should be there vs what it sees.
function pieceCheck() {
  const v = S.vision || {}, seen = v.seen, lands = S.state.lands;
  if (!S.state.start_placed) return null;
  if (!seen) return { ok: null, rows: [], note: v.connected ? "The camera can't line up the board yet." : "The camera isn't connected." };
  const P = ["explorers", "towns", "cities", "dahan", "blight", "presence"];
  const word = { explorers: "explorer", towns: "town", cities: "city", dahan: "Dahan", blight: "blight", presence: "presence" };
  const txt = (c) => P.filter((p) => c[p]).map((p) => `${c[p]} ${word[p]}`).join(", ") || "empty";
  const rows = Object.keys(seen).sort().map((lid) => {
    const want = lands[lid] || {}, got = seen[lid];
    const ok = P.every((p) => (want[p] || 0) === (got[p] || 0));
    return { lid, ok, want: txt(want), got: txt(got) };
  });
  return { ok: rows.every((r) => r.ok), rows, board: v.board, settled: v.settled };
}

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) e.append(kid.nodeType ? kid : String(kid));
  return e;
}

function toast(msg, ok = false) {
  const t = $("toast");
  t.textContent = msg; t.classList.remove("hidden"); t.classList.toggle("ok", ok);
  clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.add("hidden"), 3500);
}

async function act(action) {
  try {
    const r = await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(action) });
    const data = await r.json();
    if (!r.ok) return toast(data.error || "That didn't work");
    render(data);
  } catch (e) { toast("Can't reach the game server"); }
}

function cardLabel(c) { return c ? (S.derived.card_labels[c] || c) : "-"; }

// ---------- header ----------
function renderHeader() {
  const s = S.state, d = S.derived;
  $("round").textContent = s.status === "setup" ? "Setup" : s.status === "playing" ? `Round ${s.round}` :
    (s.status === "won" ? "Victory" : "Defeat");
  const si = SETUP_STEPS.indexOf(s.step);
  $("phase").textContent = si >= 0 ? `· step ${si + 1} of ${SETUP_STEPS.length}` : "· " + S.guide.phase;
  $("chip-terror").querySelector("span").textContent = d.terror_level;
  const f = s.fear;
  $("chip-fear").querySelector("span").textContent =
    `${f.generated}/${f.pool_size || "-"}` + (f.unresolved ? ` +${f.unresolved}🂠` : "");
  $("chip-fear").title = `${d.fear_cards_left} fear cards left to earn`;
  $("chip-blight").querySelector("span").textContent = s.blight.pool + (s.blight.card_flipped ? " ⚠" : "");
  $("chip-deck").querySelector("span").textContent =
    d.invader_cards_left + (d.next_stage ? ` (St ${"I".repeat(d.next_stage)})` : "");
  for (const k of ["ravage", "build", "explore"]) $("slot-" + k).textContent = cardLabel(s.invaders.slots[k]);
  const bar = $("phasebar"); bar.innerHTML = "";
  if (s.status === "playing") {
    const i = ROUND_STEPS.indexOf(s.step);
    ROUND_STEPS.forEach((st, j) => bar.append(el("i", { class: j < i ? "done" : j === i ? "now" : "" })));
  }
  // During setup the left button steps back a screen; once playing it undoes the last tap.
  const back = s.status === "setup";
  $("btn-undo").textContent = back ? "‹ Back" : "Undo";
  $("btn-undo").disabled = back ? s.step === "setup.welcome" && !s.sub : !S.can_undo;
  $("btn-next").disabled = s.status === "won" || s.status === "lost";
  $("btn-fear").disabled = s.status !== "playing";
}

// ---------- guide ----------
// Presence discs drawn over a picture: they drop onto the panel's track circles one by
// one, then onto the starting land on the board, and the whole thing replays. The discs
// sit in a layer laid exactly over the picture (kept in step as the picture resizes).
function addDiscs(fig, img, p) {
  if (!p.discs || !p.discs.length) return;
  const layer = el("div", { class: "disc-layer" });
  const start = p.discs[0].land ? 3.2 : 0;  // board discs land after the panel ones
  p.discs.forEach((d, i) => {
    const disc = el("span", { class: "disc" + (d.land ? " on-land" : "") });
    const size = (p.disc_size || 0.05) * 100;
    disc.style.cssText = `left:${d.x * 100}%;top:${d.y * 100}%;width:${size}%;padding-bottom:${size}%;` +
      `background:${p.disc_colour || "#3fa8ff"};animation-delay:${start + i * 0.25}s`;
    layer.append(disc);
  });
  const place = () => {
    Object.assign(layer.style, { left: img.offsetLeft + "px", top: img.offsetTop + "px",
                                 width: img.offsetWidth + "px", height: img.offsetHeight + "px" });
  };
  img.addEventListener("load", place);
  window.addEventListener("resize", place);
  requestAnimationFrame(place);
  fig.append(layer);
}
function pictures(list) {
  return (list || []).map((p) => {
    if (p.anim) return el("figure", { class: "wide anim" }, animScene(p), el("figcaption", {}, p.caption));
    const img = el("img", { src: "/assets/" + p.src, alt: p.caption, loading: "lazy" });
    const fig = el("figure", { class: (p.wide ? "wide" : "") + (p.mark ? " mark" : "") }, el("a", { href: "/assets/" + p.src, target: "_blank" }, img), el("figcaption", {}, p.caption));
    img.onerror = () => fig.remove();
    addDiscs(fig, img, p);
    return fig;
  });
}

function renderGuide() {
  const g = S.guide;
  $("g-phase").textContent = g.phase;
  $("g-title").textContent = g.title;
  const sub = g.sub || 0;
  $("g-do").replaceChildren(...g.do.map((t, i) => el("li", { class: g.single || i === sub ? "now" : i < sub ? "done" : "" }, t)));
  $("g-why").textContent = g.why || "";
  $("g-tips").replaceChildren(...(g.tips || []).map((t) => el("li", {}, t)));
  $("g-pics").replaceChildren(...pictures((g.pictures || []).filter((p) => !p.items || p.items.includes(sub))));
  const h = $("g-helper"); h.replaceChildren();
  if (!g.helper) return;
  const fn = HELPERS[g.helper.kind];
  if (fn) h.append(fn(g.helper));
}

function landRow(lid, what, button) {
  return el("div", { class: "rowline" }, el("div", { class: "what" }, el("b", {}, lid), " ", what), button);
}

const HELPERS = {
  gain_power(h) {
    const box = el("div", { class: "helper" });
    for (const p of h.players || []) {
      box.append(landRow(p.name, el("span", {}, "gained a power card?"),
        el("span", {}, el("button", { onclick: () => act({ type: "gain_power", player: p.i, delta: -1 }) }, "-"), " ",
          el("button", { onclick: () => act({ type: "gain_power", player: p.i }) }, "Took the next one"))));
    }
    return box;
  },
  verify(h) {
    const box = el("div", { class: "helper" });
    box.append(el("button", { class: "primary", onclick: () => act({ type: "place_start" }) },
      h.placed ? "Check again" : "Verify with the camera"));
    const c = pieceCheck();
    if (c) {
      if (c.note) box.append(el("p", {}, c.note));
      else {
        box.append(el("p", {}, c.ok ? `✓ Board ${c.board}: everything is where it should be.` :
          `Board ${c.board}: ${c.rows.filter((r) => !r.ok).length} land(s) don't match${c.settled ? "" : " (camera still settling)"}.`));
        for (const r of c.rows.filter((r) => !r.ok)) {
          box.append(landRow(r.lid, el("span", {}, `should be ${r.want}; camera sees ${r.got}`), null));
        }
      }
    }
    return box;
  },
  configure() {
    const s = S.state;
    const box = el("div", { class: "helper form" });
    const playersBox = el("div");
    const inputs = [];
    // Save as you go so the TV shows the players while you fill them in.
    let timer = null;
    const autosave = (delay) => { clearTimeout(timer); timer = setTimeout(save, delay); };
    // The rules deal island boards at random; Re-deal shuffles them again.
    const randomBoard = (taken) => { const free = REF.boards.filter((b) => !taken.includes(b)); return free[Math.floor(Math.random() * free.length)]; };
    let rows = s.players.length ? s.players.map((p, i) => ({ name: p.name, spirit: p.spirit, board: s.boards[i] }))
      : [{ name: "", spirit: REF.spirits[0].name, board: randomBoard([]) }];
    const current = () => inputs.map((x) => ({ name: x.name.value, spirit: x.sp.value, board: x.bd.value }));
    function addPlayer() {
      rows = current();
      const used = rows.map((r) => r.spirit), boards = rows.map((r) => r.board);
      rows.push({ name: "", spirit: (REF.spirits.find((x) => !used.includes(x.name)) || REF.spirits[0]).name,
                  board: randomBoard(boards) });
      drawPlayers(); autosave(0);
    }
    function removePlayer(i) { rows = current(); rows.splice(i, 1); drawPlayers(); autosave(0); }
    const addBtn = el("button", { class: "add-player", onclick: addPlayer }, "+ Add player");
    const dealBtn = el("button", { class: "add-player", onclick: () => {
      rows = current(); const taken = [];
      rows.forEach((r) => { r.board = randomBoard(taken); taken.push(r.board); });
      drawPlayers(); autosave(0);
    } }, "Re-deal boards at random");
    function drawPlayers() {
      playersBox.replaceChildren(); inputs.length = 0;
      rows.forEach((p, i) => {
        const name = el("input", { value: p.name, placeholder: `Player ${i + 1}`, oninput: () => autosave(700) });
        const style = el("div", { class: "spirit-style" });
        const sp = el("select", { onchange: () => { upd(); autosave(0); } },
          REF.spirits.map((x) => el("option", { value: x.name, selected: x.name === p.spirit }, `${x.name} (${x.complexity})`)));
        const upd = () => { style.textContent = REF.spirits.find((x) => x.name === sp.value).style; };
        upd();
        const bd = el("select", { onchange: () => autosave(0) }, REF.boards.map((b) => el("option", { value: b, selected: b === p.board }, `Board ${b}`)));
        inputs.push({ name, sp, bd });
        const head = el("div", { class: "player-head" }, el("b", {}, `Player ${i + 1}`),
          rows.length > 1 ? el("button", { class: "remove-player", onclick: () => removePlayer(i) }, "Remove") : null);
        playersBox.append(el("div", { class: "player" }, head, el("label", {}, "Name"), name,
          el("label", {}, "Spirit"), sp, style,
          el("label", {}, "Island board (the letter printed on it)"), bd));
      });
      addBtn.classList.toggle("hidden", rows.length >= 4);
    }
    drawPlayers();
    const prog = el("input", { type: "checkbox", onchange: () => autosave(0) });
    prog.checked = s.progression !== false;
    const adv = el("select", { onchange: () => autosave(0) }, REF.adversaries.map((a) => el("option", { value: a, selected: a === s.adversary.name }, a)));
    const lvl = el("input", { type: "number", min: 0, max: 6, value: s.adversary.level, style: "width:5em" });
    const diff = el("input", { type: "number", min: 0, max: 20, value: s.adversary.difficulty, style: "width:5em" });
    box.append(el("h3", {}, "Players"), playersBox, addBtn, dealBtn,
      el("label", { class: "check-line" }, prog, " Use the recommended power progression (best for learning)"),
      el("label", {}, "Adversary (optional; leave None for now)"), adv,
      el("label", {}, "Adversary level and difficulty (from its panel; used for the score)"),
      el("div", { class: "btngrid" }, lvl, diff),
      el("p", { class: "why" }, "Changes save by themselves and show on the TV. Tap Next when everyone's in."));
    function save() {
      return act({
        type: "configure",
        players: inputs.map((x) => ({ name: x.name.value.trim(), spirit: x.sp.value })),
        boards: inputs.map((x) => x.bd.value),
        adversary: { name: adv.value, level: +lvl.value, difficulty: +diff.value },
        progression: prog.checked,
      });
    }
    if (!s.players.length) setTimeout(() => autosave(0));
    return box;
  },
  reveal(h) {
    const box = el("div", { class: "helper" });
    const cur = S.state.invaders.slots.explore;
    box.append(el("h3", {}, cur ? "Revealed card (tap another to fix a mis-tap)" : "Which card did you turn over?"),
      el("div", { class: "btngrid" }, h.options.concat(cur && !h.options.includes(cur) ? [cur] : []).map((c) =>
        el("button", { class: c === cur ? "sel" : "", onclick: () => act({ type: "reveal_invader", card: c }) }, cardLabel(c)))));
    if (cur && h.rows) {
      if (!h.rows.length) box.append(el("p", {}, "No tagged land matches this card."));
      for (const r of h.rows) {
        box.append(landRow(r.land, r.explore === "yes" ? el("span", { class: "badge bad" }, "gets explorer")
          : el("span", { class: "badge" }, "check neighbours"),
          el("button", { onclick: () => act({ type: "apply_explore", land: r.land }) }, "+1 explorer")));
      }
    }
    return box;
  },
  ravage(h) {
    const box = el("div", { class: "helper" }, el("h3", {}, "Ravaging lands (from tracked pieces)"));
    if (!h.rows.length) box.append(el("p", {}, "None found among tagged lands."));
    for (const r of h.rows) {
      const k = r.invaders_killed;
      const kills = [k.cities && `${k.cities} city`, k.towns && `${k.towns} town`, k.explorers && `${k.explorers} explorer`].filter(Boolean).join(", ");
      box.append(landRow(r.land, el("span", {},
        `${r.damage} dmg`, r.blight ? el("span", { class: "badge bad" }, r.cascade ? "blight + cascade!" : "blight") : el("span", { class: "badge ok" }, "no blight"),
        r.dahan_killed ? el("span", { class: "badge bad" }, `-${r.dahan_killed} Dahan`) : null,
        r.fight_back ? el("span", { class: "badge ok" }, `Dahan hit back ${r.fight_back}${kills ? ": " + kills : ""}`) : null),
        el("button", { onclick: () => act({ type: "apply_ravage", land: r.land }) }, "Apply")));
    }
    return box;
  },
  build(h) {
    const box = el("div", { class: "helper" }, el("h3", {}, "Building lands (from tracked pieces)"));
    if (!h.rows.length) box.append(el("p", {}, "None found among tagged lands."));
    for (const r of h.rows) box.append(landRow(r.land, `adds a ${r.adds === "cities" ? "city" : "town"}`,
      el("button", { onclick: () => act({ type: "apply_build", land: r.land }) }, "Apply")));
    return box;
  },
  fear_cards(h) {
    return el("div", { class: "helper" }, el("h3", {}, `${h.left} card(s) left to resolve`),
      el("button", { class: "primary", onclick: () => act({ type: "resolve_fear_card" }) }, "Resolved one"));
  },
};

// ---------- tabs ----------
function hitLands() {
  const s = S.state, step = s.step;
  const card = step === "invader.ravage" ? s.invaders.slots.ravage : step === "invader.build" ? s.invaders.slots.build :
    (step === "invader.explore" || step === "setup.first_explore") ? s.invaders.slots.explore : null;
  if (!card) return new Set();
  return new Set(Object.entries(s.lands).filter(([, l]) =>
    card === "C" ? l.coastal : l.terrain && card.includes(l.terrain)).map(([k]) => k));
}

function renderIsland() {
  const box = $("tab-island"); box.replaceChildren();
  const s = S.state;
  if (!Object.keys(s.lands).length) { box.append(el("p", {}, "Choose players first; their boards appear here.")); return; }
  const t = S.derived.totals;
  box.append(el("div", { class: "totals" },
    `On the island: ${t.explorers} explorers, ${t.towns} towns, ${t.cities} cities, ${t.dahan} Dahan, ${t.blight} blight. `,
    `Score now: ${S.derived.score_if_won} if you won, ${S.derived.score_if_lost} if you lost.`));
  const hits = hitLands();
  const camDiff = {};
  for (const d of (S.vision && S.vision.diffs) || []) if (d.confirmed) camDiff[d.land] = d;
  const order = [null, "J", "W", "S", "M"];
  const grid = el("div", { class: "lands" });
  for (const [lid, l] of Object.entries(s.lands)) {
    const nextT = order[(order.indexOf(l.terrain) + 1) % order.length];
    grid.append(el("div", { class: "land" + (hits.has(lid) ? " hit" : "") },
      el("header", {}, el("b", {}, lid),
        el("button", { class: "terr " + (l.terrain ? "T-" + l.terrain : ""), title: "Tap to set terrain",
          onclick: () => act({ type: "land_info", land: lid, terrain: nextT }) }, l.terrain ? REF.terrains[l.terrain] : "terrain?"),
        el("button", { class: "coast", title: "Coastal?", onclick: () => act({ type: "land_info", land: lid, coastal: !l.coastal }) },
          l.coastal ? "🌊" : "–")),
      REF.pieces.map((p) => el("div", { class: "ctr" }, el("span", { class: "nm" }, PIECE_LABEL[p]),
        el("button", { onclick: () => act({ type: "land", land: lid, piece: p, delta: -1 }) }, "−"),
        el("span", { class: "n" }, l[p]),
        el("button", { onclick: () => act({ type: "land", land: lid, piece: p, delta: 1 }) }, "+"))),
      camDiff[lid] ? el("div", { class: "camdiff" }, `Camera sees: ${diffText(camDiff[lid])} `,
        el("button", { onclick: () => vision({ accept: lid }) }, "Use camera")) : null));
  }
  box.append(grid);
}

function renderLearn() {
  const box = $("tab-learn"); box.replaceChildren();
  box.append(el("h3", {}, "Words you'll meet"),
    el("dl", { class: "gloss" }, REF.glossary.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])),
    el("h3", {}, "How you win"),
    el("p", {}, "Earn every fear card. Or, at terror level 1, clear every invader; at level 2, every town and city; at level 3, every city."),
    el("h3", {}, "How you lose"),
    el("p", {}, "The blight card runs out of blight (after it has flipped), any spirit has no presence left on the island, or the invader deck is empty when it's time to explore."));
}

// ---------- camera ----------
async function vision(body) {
  try {
    const r = await fetch("/api/vision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) return toast(data.error || "That didn't work");
    render(data);
    if (body.accept) toast("Copied the camera's counts", true);
  } catch (e) { toast("Can't reach the game server"); }
}

function diffText(d) {
  return Object.entries(d.delta).map(([p, n]) => `${PIECE_LABEL[p]} ${d.camera[p]} (${n > 0 ? "+" : ""}${n})`).join(", ");
}

let lastCamStamp = null;
function renderCamera() {
  const box = $("tab-camera"); box.replaceChildren();
  const v = S.vision;
  if (!v) { box.append(el("p", {}, "The camera link is turned off for this server.")); return; }
  if (!v.connected) {
    box.append(el("h3", {}, "Board camera not running"),
      el("p", {}, "Start the live board page on the PC (it serves port 8091), then this tab fills in by itself:"),
      el("pre", { class: "cmd" }, "py -m spirit_island.board_view --phone --reference <reference folder>"),
      el("p", { class: "why" }, v.error || ""));
    return;
  }
  const boards = S.state.boards;
  box.append(
    el("div", { class: "rowline" },
      el("div", { class: "what" }, el("b", {}, v.settled ? "Settled" : "Waiting"), ` · photo ${v.stamp || "-"} · ${v.pieces_seen} piece(s) seen`,
        v.settled ? null : el("div", { class: "why" }, v.status))),
    boards.length > 1 ? el("div", { class: "rowline" }, el("div", { class: "what" }, "The camera is looking at"),
      el("select", { onchange: (e) => vision({ board: e.target.value }) },
        boards.map((b) => el("option", { value: b, selected: b === v.board }, `Board ${b}`)))) : "",
    el("div", { class: "rowline" },
      el("div", { class: "what" }, el("b", {}, "Auto-sync"), el("div", { class: "why" },
        "Copy camera changes in by itself, but only ones that held for a few readings and fit the current step. Unusual ones wait for you. Undo still works.")),
      el("button", { class: v.auto ? "primary" : "", onclick: () => vision({ auto: !v.auto }) }, v.auto ? "On" : "Off")));

  if (v.blind) box.append(el("p", { class: "badge bad" },
    "The camera can't see the pieces well right now (the light has probably changed). The tracked board is kept as it is."));
  if (!boards.length) box.append(el("p", {}, "Choose players first, so the camera's lands have names."));
  else if (!v.diffs.length) box.append(el("p", { class: "badge ok" }, "The camera agrees with the tracker."));
  else {
    box.append(el("h3", {}, `${v.diffs.length} land(s) where the camera sees something different`),
      el("p", { class: "why" }, "The tracker is the truth; these are the camera's suggestions."));
    const VERDICT = { expected: ["ok", "expected"], plausible: ["", "possible"], unusual: ["bad", "unusual"] };
    for (const d of v.diffs) {
      const [cls, word] = VERDICT[d.verdict] || ["", d.verdict];
      box.append(landRow(d.land, el("span", {}, diffText(d),
        el("span", { class: "badge " + cls, title: d.why }, word),
        d.confirmed ? null : el("span", { class: "badge" }, `checking ${d.streak}/2`),
        el("div", { class: "why" }, d.why)),
        el("button", { onclick: () => vision({ accept: d.land }) }, "Use camera")));
    }
    if (v.diffs.some((d) => d.confirmed && d.verdict !== "unusual"))
      box.append(el("button", { class: "primary", onclick: () => vision({ accept: "all" }) }, "Use all the expected ones"));
    box.append(el("p", { class: "why" }, "Presence counts all colours together; energy tokens and anything unrecognised are ignored."));
  }
  const board = v.view === "board" && v.has_map;
  box.append(el("h3", {}, "What the camera sees"));
  if (v.has_map) box.append(el("div", { class: "rowline" },
    el("div", { class: "what" }, "Show on every screen (TV too)"),
    el("div", { class: "seg" },
      el("button", { class: board ? "" : "primary", onclick: () => vision({ view: "photo" }) }, "Photo"),
      el("button", { class: board ? "primary" : "", onclick: () => vision({ view: "board" }) }, "Drawn board"))));
  if (board) {
    if (!phoneMap.view) loadPhoneMap();
    box.append(phoneMap.box);
    drawPhoneMap(v);
  } else {
    box.append(el("img", { class: "camphoto", alt: "Latest board photo, pieces labelled",
      src: "/api/vision/board.jpg?" + encodeURIComponent(v.stamp || "") }));
  }
}

// The drawn board keeps one SVG alive between renders so its pieces can animate.
const phoneMap = { box: null, view: null, loading: false };
phoneMap.box = el("div", { class: "phonemap" });
async function loadPhoneMap() {
  if (phoneMap.loading) return; phoneMap.loading = true;
  try {
    const r = await fetch("/api/vision/map");
    if (!r.ok) return;
    phoneMap.view = BoardMap.create(phoneMap.box);
    BoardMap.setMap(phoneMap.view, await r.json());
    if (S && S.vision) drawPhoneMap(S.vision);
  } finally { phoneMap.loading = false; }
}
function drawPhoneMap(v) {
  const m = phoneMap.view;
  if (!m) return;
  const hits = hitLands(), info = {};
  for (const l of m.map.lands) {
    const lid = (v.board || "") + l.name, land = S.state.lands[lid];
    info[l.name] = { terrain: land && land.terrain, hit: hits.has(lid) };
  }
  BoardMap.setLands(m, info);
  BoardMap.setPieces(m, v.pieces || []);
}

function renderLog() {
  const box = $("tab-log"); box.replaceChildren();
  const items = S.state.log.slice().reverse();
  box.append(el("div", { class: "log" }, items.length ? items.map((e) => el("div", {},
    el("span", { class: "src" }, `R${e.round} · ${e.source} · `), e.text)) : "Nothing yet."));
}

function renderSettings() {
  const box = $("tab-settings"); box.replaceChildren();
  const s = S.state;
  const blightIn = el("input", { type: "number", value: s.blight.pool, style: "width:5em" });
  box.append(el("div", { class: "stack" },
    el("h3", {}, "Screens"),
    el("p", {}, "Open this on the TV's browser for the couch view (big type, follows every tap here):"),
    el("div", { class: "links" }, (LINKS ? LINKS.tv : ["/tv"]).map((u) => el("div", {}, el("a", { href: u, target: "_blank" }, u)))),
    el("h3", {}, "Fix a number"),
    el("div", { class: "btngrid" }, el("button", { onclick: () => act({ type: "fear", amount: -1 }) }, "−1 Fear"),
      el("button", { onclick: () => act({ type: "fear", amount: 1 }) }, "+1 Fear")),
    el("div", { class: "btngrid" }, el("span", {}, "Blight on the card:"), blightIn,
      el("button", { onclick: () => act({ type: "set_pool", blight_pool: +blightIn.value }) }, "Set")),
    el("h3", {}, "Blight card"),
    el("p", {}, "When the blight card runs out of blight, flip it and read the new side."),
    el("div", { class: "btngrid" },
      el("button", { onclick: () => { const n = prompt("How much blight does the flipped side add to the card?", String(5 * Math.max(1, s.players.length)));
        if (n !== null) act({ type: "flip_blight_card", add: +n || 0 }); } }, "Flipped: it adds blight"),
      el("button", { onclick: () => act({ type: "flip_blight_card", invaders_win: true }) }, "Flipped: invaders win")),
    el("h3", {}, "End the game"),
    el("div", { class: "btngrid" },
      el("button", { onclick: () => act({ type: "end_game", outcome: "won", reason: `Terror level ${S.derived.terror_level} victory condition met.` }) }, "We won (terror condition)"),
      el("button", { onclick: () => act({ type: "end_game", outcome: "lost", reason: "A spirit has no presence left on the island." }) }, "A spirit lost all presence"),
      el("button", { onclick: () => confirm("Start a new game? The current one is cleared (Undo can bring it back).") && act({ type: "new_game" }) }, "New game"))));
}

function renderTabs() {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== "tab-" + tab));
  const v = S.vision;
  const nConf = v && v.connected ? v.diffs.filter((d) => d.confirmed).length : 0;
  $("cam-dot").textContent = v && v.blind ? " (!)" : nConf ? ` (${nConf})` : "";
  // The camera tab reloads its photo only when there is a new one, so it doesn't flicker on every tap.
  if (tab === "camera" && v && v.stamp === lastCamStamp && renderTabs.drawnFor === JSON.stringify([v, S.state.boards])) return;
  if (tab === "camera") { lastCamStamp = v && v.stamp; renderTabs.drawnFor = JSON.stringify([v, S.state.boards]); }
  ({ island: renderIsland, camera: renderCamera, learn: renderLearn, log: renderLog, settings: renderSettings })[tab]();
}

function render(snapshot) {
  if (S && S.boot && snapshot.boot && S.boot !== snapshot.boot) { location.reload(); return; }
  const stepChanged = !S || S.state.step !== snapshot.state.step;
  S = snapshot;
  renderHeader();
  // Don't wipe a half-filled setup form when someone else taps.
  const busy = document.activeElement && document.activeElement.closest && document.activeElement.closest("#g-helper") &&
    S.guide.helper && S.guide.helper.kind === "configure";
  if (!busy) renderGuide();
  renderTabs();
  if (stepChanged) window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------- wiring ----------
$("btn-next").onclick = () => act({ type: "next" });
$("btn-undo").onclick = () => act({ type: S.state.status === "setup" ? "back" : "undo" });
$("btn-fear").onclick = () => act({ type: "fear", amount: 1 });
document.querySelectorAll(".tabs button").forEach((b) => b.onclick = () => { tab = b.dataset.tab; renderTabs(); });

function connect() {
  const es = new EventSource("/api/events");
  es.onopen = () => $("conn").classList.add("live");
  es.onmessage = (m) => render(JSON.parse(m.data));
  es.onerror = () => { $("conn").classList.remove("live"); };
}

(async function start() {
  REF = await (await fetch("/api/reference")).json();
  try { LINKS = await (await fetch("/api/links")).json(); } catch (e) { LINKS = null; }
  render(await (await fetch("/api/state")).json());
  connect();
})();
