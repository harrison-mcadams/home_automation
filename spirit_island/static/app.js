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

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "onclick") e.addEventListener("click", v);
    else if (k === "onchange") e.addEventListener("change", v);
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
  $("btn-undo").disabled = !S.can_undo;
  $("btn-next").disabled = s.status === "won" || s.status === "lost";
  $("btn-fear").disabled = s.status !== "playing";
}

// ---------- guide ----------
function renderGuide() {
  const g = S.guide;
  $("g-phase").textContent = g.phase;
  $("g-title").textContent = g.title;
  $("g-do").replaceChildren(...g.do.map((t) => el("li", {}, t)));
  $("g-why").textContent = g.why || "";
  $("g-tips").replaceChildren(...(g.tips || []).map((t) => el("li", {}, t)));
  const h = $("g-helper"); h.replaceChildren();
  if (!g.helper) return;
  const fn = HELPERS[g.helper.kind];
  if (fn) h.append(fn(g.helper));
}

function landRow(lid, what, button) {
  return el("div", { class: "rowline" }, el("div", { class: "what" }, el("b", {}, lid), " ", what), button);
}

const HELPERS = {
  configure() {
    const s = S.state;
    const box = el("div", { class: "helper form" });
    const existing = s.players.length ? s.players : [{ name: "", spirit: REF.spirits[0].name }];
    let count = existing.length;
    const playersBox = el("div");
    const countSel = el("select", { onchange: () => { count = +countSel.value; drawPlayers(); } },
      [1, 2, 3, 4].map((n) => el("option", { value: n, selected: n === count }, `${n} player${n > 1 ? "s" : ""}`)));
    const inputs = [];
    function drawPlayers() {
      playersBox.replaceChildren(); inputs.length = 0;
      for (let i = 0; i < count; i++) {
        const p = existing[i] || { name: "", spirit: REF.spirits[i % REF.spirits.length].name };
        const name = el("input", { value: p.name, placeholder: `Player ${i + 1}` });
        const style = el("div", { class: "spirit-style" });
        const sp = el("select", { onchange: () => upd() },
          REF.spirits.map((x) => el("option", { value: x.name, selected: x.name === p.spirit }, `${x.name} (${x.complexity})`)));
        const upd = () => { style.textContent = REF.spirits.find((x) => x.name === sp.value).style; };
        upd();
        // Default to the board the camera recognised for player 1, then the others in order.
        const seen = S.vision && S.vision.detected_board;
        const order = seen ? [seen, ...REF.boards.filter((b) => b !== seen)] : REF.boards;
        const boardNow = s.boards[i] || order[i];
        const bd = el("select", {}, REF.boards.map((b) => el("option", { value: b, selected: b === boardNow }, `Board ${b}`)));
        inputs.push({ name, sp, bd });
        playersBox.append(el("div", { class: "player" }, el("label", {}, `Player ${i + 1} name`), name,
          el("label", {}, "Spirit"), sp, style,
          el("label", {}, "Island board (the letter printed on it)"), bd));
      }
    }
    drawPlayers();
    const adv = el("select", {}, REF.adversaries.map((a) => el("option", { value: a, selected: a === s.adversary.name }, a)));
    const lvl = el("input", { type: "number", min: 0, max: 6, value: s.adversary.level, style: "width:5em" });
    const diff = el("input", { type: "number", min: 0, max: 20, value: s.adversary.difficulty, style: "width:5em" });
    box.append(el("h3", {}, "Players"), countSel, playersBox,
      el("label", {}, "Adversary (optional; leave None for now)"), adv,
      el("label", {}, "Adversary level and difficulty (from its panel; used for the score)"),
      el("div", { class: "btngrid" }, lvl, diff),
      el("div", { style: "margin-top:10px" }, el("button", { class: "primary", onclick: () => act({
        type: "configure",
        players: inputs.map((x) => ({ name: x.name.value.trim(), spirit: x.sp.value })),
        boards: inputs.map((x) => x.bd.value),
        adversary: { name: adv.value, level: +lvl.value, difficulty: +diff.value },
      }).then(() => S.state.players.length && toast("Saved. Tap Next.", true)) }, s.players.length ? "Update" : "Save players")));
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
$("btn-undo").onclick = () => act({ type: "undo" });
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
