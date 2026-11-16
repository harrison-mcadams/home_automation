// Couch view: shows the live game for the whole table. Follows the same server as the
// phone, so a tap on the phone shows up here at once. A TV remote or keyboard can also
// step the game on its own (right = next, left = undo, F = +1 fear).
"use strict";

let S = null, REF = null, lastCamStamp = null;
const $ = (id) => document.getElementById(id);

const TRACK = [
  ["spirit.growth", "Growth", "spirit"], ["spirit.energy", "Energy", "spirit"], ["spirit.powers", "Play powers", "spirit"],
  ["fast", "Fast powers", "fast"], ["invader.blighted", "Blighted island", "invader"], ["invader.fear", "Fear cards", "invader"],
  ["invader.ravage", "Ravage", "invader"], ["invader.build", "Build", "invader"], ["invader.explore", "Explore", "invader"],
  ["invader.advance", "Advance cards", "invader"], ["slow", "Slow powers", "slow"], ["time_passes", "Time passes", "spirit"],
];
const SETUP = ["setup.welcome", "setup.players", "setup.island", "setup.spirits", "setup.invader_board",
  "setup.pieces", "setup.cards", "setup.first_explore"];
const SETUP_NAMES = ["Welcome", "Players", "Island", "Spirits", "Invader board", "Pieces", "Cards", "First explore"];
const PIECES = ["explorers", "towns", "cities", "dahan", "blight", "presence"];
const SHORT = { explorers: "explorer", towns: "town", cities: "city", dahan: "Dahan", blight: "blight", presence: "presence" };
const TERRAIN_VAR = { J: "var(--J)", W: "var(--W)", S: "var(--S)", M: "var(--M)", C: "var(--C)" };

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
    if (k === "class") e.className = v;
    else if (k === "style") e.setAttribute("style", v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) e.append(kid.nodeType ? kid : String(kid));
  return e;
}

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.add("hidden"), 1800);
}

const label = (c) => (c ? S.derived.card_labels[c] || c : "—");

function cardFill(card) {
  if (!card) return "";
  const cols = card.split("").map((c) => TERRAIN_VAR[c] || "var(--panel2)");
  return cols.length === 1 ? `background:${cols[0]}` : `background:linear-gradient(135deg, ${cols[0]} 50%, ${cols[1]} 50%)`;
}

function activeSlot(step) {
  return { "invader.ravage": "ravage", "invader.build": "build", "invader.explore": "explore", "setup.first_explore": "explore" }[step];
}

function hitLands() {
  const s = S.state, slot = activeSlot(s.step);
  const card = slot ? s.invaders.slots[slot] : null;
  if (!card) return new Set();
  return new Set(Object.entries(s.lands).filter(([, l]) => (card === "C" ? l.coastal : l.terrain && card.includes(l.terrain)))
    .map(([k]) => k));
}

// ---------- pieces ----------
function renderStatus() {
  const s = S.state, d = S.derived;
  const r = $("s-round").querySelector("span");
  r.textContent = s.status === "setup" ? "Setup" : s.status === "playing" ? s.round : s.status === "won" ? "Won!" : "Lost";

  const pips = $("s-terror").querySelector(".pips"); pips.replaceChildren();
  for (let i = 1; i <= 3; i++) pips.append(el("i", { class: i <= d.terror_level ? "on" : "" }));

  const f = s.fear, pct = f.pool_size ? Math.min(100, (100 * f.generated) / f.pool_size) : 0;
  $("s-fear").querySelector(".meter i").style.width = pct + "%";
  const fs = $("s-fear").querySelector("span");
  fs.replaceChildren(...[`${f.generated} / ${f.pool_size || "–"} to next card`,
    f.unresolved ? el("span", { class: "note" }, `${f.unresolved} fear card${f.unresolved > 1 ? "s" : ""} waiting`) : null].filter(Boolean));

  const b = s.blight, bp = b.start ? Math.max(0, (100 * b.pool) / b.start) : 0;
  $("s-blight").querySelector(".meter i").style.width = bp + "%";
  $("s-blight").querySelector("span").replaceChildren(...[`${b.pool} left`,
    b.card_flipped ? el("span", { class: "note" }, "card flipped") : null].filter(Boolean));
  $("s-blight").classList.toggle("alarm", s.status === "playing" && b.pool <= 2);

  $("s-deck").querySelector("span").textContent = d.invader_cards_left;
  $("s-deck").classList.toggle("alarm", s.status === "playing" && d.invader_cards_left <= 1);
}

function renderTrack() {
  const s = S.state, bar = $("track"); bar.replaceChildren();
  if (s.status === "setup") {
    const i = SETUP.indexOf(s.step);
    SETUP_NAMES.forEach((n, j) => bar.append(el("div", { class: `grp-spirit ${j < i ? "done" : j === i ? "now" : ""}` }, n)));
    return;
  }
  const i = TRACK.findIndex(([st]) => st === s.step);
  TRACK.forEach(([, n, grp], j) => bar.append(el("div", { class: `grp-${grp} ${j < i ? "done" : j === i ? "now" : ""}` }, n)));
}

function focusRows(h) {
  // The helper rows the phone shows as buttons, shown here as a read-out for the table.
  if (!h || !h.rows) return [];
  if (h.kind === "ravage") return h.rows.map((r) => {
    const k = r.invaders_killed, kills = [k.cities && `${k.cities} city`, k.towns && `${k.towns} town`, k.explorers && `${k.explorers} explorer`].filter(Boolean).join(", ");
    return el("div", { class: "focus" + (r.blight ? " bad" : "") }, el("b", {}, r.land), `${r.damage} damage`,
      r.blight ? el("span", { class: "tag" }, r.cascade ? "blight + cascade!" : "adds blight") : el("span", { class: "tag ok" }, "no blight"),
      r.dahan_killed ? el("span", { class: "tag" }, `${r.dahan_killed} Dahan die`) : null,
      r.fight_back ? el("span", { class: "tag ok" }, `Dahan fight back${kills ? ": " + kills : ""}`) : null);
  });
  if (h.kind === "build") return h.rows.map((r) => el("div", { class: "focus" }, el("b", {}, r.land), `builds a ${r.adds === "cities" ? "city" : "town"}`));
  if (h.kind === "reveal") return h.rows.map((r) => el("div", { class: "focus" }, el("b", {}, r.land),
    r.explore === "yes" ? "gets an explorer" : "explorer if a neighbour has a town/city or is ocean"));
  return [];
}

function words(g) {
  if (!REF) return [];
  const text = [g.title, ...(g.do || []), g.why || ""].join(" ").toLowerCase();
  return REF.glossary.filter(([k]) => text.includes(k.toLowerCase().split(/[ (]/)[0])).slice(0, 3)
    .map(([k, v]) => el("div", {}, el("b", {}, k + ": "), v));
}

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
function figure(p, cls) {
  if (p.anim) return el("figure", { class: (cls || "") + " anim" }, animScene(p), el("figcaption", {}, p.caption.split(":")[0]));
  const img = el("img", { src: "/assets/" + p.src, alt: p.caption });
  const fig = el("figure", { class: (cls || "") + (p.mark ? " mark" : "") }, img, el("figcaption", {}, p.caption.split(":")[0].split(" (")[0]));
  img.onerror = () => fig.remove();
  addDiscs(fig, img, p);
  return fig;
}

// Setup steps with pictures hand most of the screen to a gallery: the first wide picture
// (a spirit panel or board) big on top, the cards in a row underneath.
function renderGallery(pics, setup) {
  const on = pics.length > 0;
  document.body.classList.toggle("setup", setup);
  document.body.classList.toggle("gallery", on);
  const gal = $("gallery");
  gal.classList.toggle("hidden", !on);
  // One section per player (pictures carry a group); with several players they share the
  // space equally, each with its panel on the left and its cards beside it.
  const groups = [];
  for (const p of pics) {
    const k = p.group || 0;
    (groups.find((g) => g.k === k) || groups[groups.push({ k, pics: [] }) - 1]).pics.push(p);
  }
  const multi = groups.length > 1;
  gal.classList.toggle("multi", multi);
  gal.replaceChildren(...groups.map(({ pics: gp }) => {
    const heroIdx = gp.findIndex((p) => p.wide);
    const hero = heroIdx >= 0 ? gp[heroIdx] : null;
    const rest = gp.filter((_, i) => i !== heroIdx);
    const sec = el("div", { class: "gsec" });
    if (hero) sec.append(el("div", { class: "g-hero" }, figure(hero, "hero")));
    if (rest.length) {
      const r = el("div", { class: "g-rest" }, ...rest.map((p) => figure(p)));
      // Under a hero (one player), one row whose column widths follow each picture's shape
      // (panels ~1.5:1, cards ~0.7:1) so everything shares one height.
      if (hero && !multi) {
        r.classList.add("row");
        r.style.gridTemplateColumns = rest.map((p) => (p.wide ? "2.1fr" : "1fr")).join(" ");
      }
      r.style.setProperty("--h", (multi ? 15.5 : rest.length <= 3 ? 50 : rest.length === 4 ? 38 : rest.length === 5 ? 31 : 34) + "vh");
      sec.append(r);
    }
    return sec;
  }));
}

function forItem(pics, sub) {
  return (pics || []).filter((p) => !p.items || p.items.includes(sub));
}

// Mark the starting-piece check on the board picture: a tick or the mismatch at each land.
function markCheck(c, h) {
  if (!c || !c.rows.length || !h || !h.points) return;
  const fig = document.querySelector("#gallery figure");
  const img = fig && fig.querySelector("img");
  if (!img) return;
  const layer = el("div", { class: "disc-layer check-layer" });
  for (const r of c.rows) {
    const pt = h.points[r.lid];
    if (!pt) continue;
    const tag = el("div", { class: "check-tag " + (r.ok ? "ok" : "bad") },
      r.ok ? "✓" : el("span", {}, el("b", {}, "should be "), r.want, el("br"), el("b", {}, "sees "), r.got));
    tag.style.left = pt[0] * 100 + "%"; tag.style.top = pt[1] * 100 + "%";
    layer.append(tag);
  }
  const place = () => Object.assign(layer.style, { left: img.offsetLeft + "px", top: img.offsetTop + "px",
    width: img.offsetWidth + "px", height: img.offsetHeight + "px" });
  img.addEventListener("load", place); requestAnimationFrame(place);
  fig.append(layer);
}

function renderNow() {
  const g = S.guide, s = S.state;
  document.body.classList.toggle("over", s.status === "won" || s.status === "lost");
  document.body.classList.toggle("lost", s.status === "lost");
  $("n-phase").textContent = g.phase;
  $("n-title").textContent = g.title;
  // Next walks the numbered items one at a time: the current one is lit, and only its
  // pictures are shown.
  const sub = g.sub || 0;
  $("n-do").replaceChildren(...g.do.map((t, i) => el("li", { class: g.single || i === sub ? "now" : i < sub ? "done" : "" }, t)));
  const focus = focusRows(g.helper);
  const c = g.helper && g.helper.kind === "verify" ? pieceCheck() : null;
  if (c) {
    if (c.note) focus.push(el("div", { class: "focus bad" }, c.note));
    else {
      const bad = c.rows.filter((r) => !r.ok).length;
      focus.push(el("div", { class: "focus" + (c.ok ? "" : " bad") }, el("b", {}, c.ok ? "✓ All good" : `${bad} land${bad > 1 ? "s" : ""} to check`),
        `camera on board ${c.board}${c.settled ? "" : ", still settling"}`));
    }
  }
  if (g.helper && g.helper.kind === "configure") {
    const roster = g.helper.roster || [];
    if (!roster.length) focus.push(el("div", { class: "focus" }, "Add players on the phone."));
    roster.forEach((p, i) => focus.push(el("div", { class: "player-card" },
      el("div", { class: "pc-name" }, p.name, el("span", { class: "pc-board" }, p.board ? `Board ${p.board}` : "")),
      el("div", { class: "pc-spirit" }, p.spirit, p.complexity ? el("span", { class: "tag" }, p.complexity) : null),
      el("div", { class: "pc-style" }, p.style))));
  }
  if (g.helper && g.helper.kind === "fear_cards") focus.push(el("div", { class: "focus" }, el("b", {}, g.helper.left), "fear card(s) to read and resolve"));
  $("n-focus").replaceChildren(...focus);
  renderGallery(forItem(g.pictures, sub), s.status === "setup");
  markCheck(c, g.helper);
  // Build the screen up as the game goes: setup shows only the step itself; the invader
  // cards, lands and camera join at the first explore, the status bar once play starts.
  document.body.classList.toggle("bare", s.status === "setup" && s.step !== "setup.first_explore");
  $("n-why").textContent = g.why || "";
  $("n-why").classList.toggle("hidden", !g.why);
  $("n-words").replaceChildren(...words(g));
}

function renderInvaders() {
  const s = S.state, act = activeSlot(s.step);
  for (const k of ["ravage", "build", "explore"]) {
    const c = s.invaders.slots[k], box = $("c-" + k);
    box.querySelector("span").textContent = label(c);
    box.setAttribute("style", cardFill(c));
    box.classList.toggle("filled", !!c);
    box.classList.toggle("active", act === k);
  }
}

function renderLands() {
  const s = S.state, box = $("lands"); box.replaceChildren();
  const ids = Object.keys(s.lands);
  if (!ids.length) { box.append(el("div", { class: "board-label" }, "Lands appear once players are chosen")); return; }
  const hits = hitLands();
  const camDiff = {};
  // Only changes the camera has held for a few readings; the tracker stays the truth.
  for (const d of (S.vision && S.vision.diffs) || []) if (d.confirmed) camDiff[d.land] = d;
  const multi = s.boards.length > 1;
  for (const b of s.boards) {
    if (multi) box.append(el("div", { class: "board-label" }, `Board ${b}`));
    for (const lid of ids.filter((x) => x.startsWith(b))) {
      const l = s.lands[lid];
      const pcs = PIECES.filter((p) => l[p]).map((p) => el("span", { class: "pc " + p, title: p }, el("i"), l[p]));
      const diff = camDiff[lid];
      const camTxt = diff ? (diff.verdict === "unusual" ? "cam? " : "cam ") +
        Object.entries(diff.delta).map(([p, n]) => `${n > 0 ? "+" : ""}${n} ${SHORT[p]}`).join(", ") : null;
      box.append(el("div", { class: "land" + (hits.has(lid) ? " hit" : ""), style: `border-left-color:${l.terrain ? TERRAIN_VAR[l.terrain] : "var(--line)"}` },
        el("h4", {}, lid, el("small", {}, (l.terrain ? REF.terrains[l.terrain] : "") + (l.coastal ? " · coast" : ""))),
        el("div", { class: "pcs" }, pcs.length ? pcs : el("span", { style: "color:var(--muted);font-size:1.6vh" }, "empty")),
        camTxt ? el("div", { class: "cam" + (diff.verdict === "unusual" ? " odd" : "") }, camTxt) : null));
    }
  }
}

let mapView = null, mapLoaded = false;
async function loadMap() {
  if (mapLoaded) return; mapLoaded = true;
  try {
    const r = await fetch("/api/vision/map");
    if (!r.ok) return;
    mapView = BoardMap.create($("cam-map"));
    BoardMap.setMap(mapView, await r.json());
    if (S) renderCamera();
  } catch (e) { mapLoaded = false; }
}

function drawMap(v) {
  if (!mapView) return;
  const hits = hitLands(), info = {};
  for (const l of mapView.map.lands) {
    const lid = (v.board || "") + l.name, land = S.state.lands[lid];
    info[l.name] = { terrain: land && land.terrain, hit: hits.has(lid) };
  }
  BoardMap.setLands(mapView, info);
  BoardMap.setPieces(mapView, v.pieces || []);
}

function renderCamera() {
  const v = S.vision, img = $("cam-img"), st = $("cam-status");
  if (!v) { $("camera").classList.add("hidden"); return; }
  $("camera").classList.remove("hidden");
  const board = v.view === "board" && v.has_map;
  if (v.has_map) loadMap();
  $("cam-map").classList.toggle("hidden", !board);
  $("cam-view").replaceChildren(...(v.has_map ? [el("span", { class: board ? "" : "on" }, "Photo"), el("span", { class: board ? "on" : "" }, "Drawn board")] : []));
  if (board) drawMap(v);
  if (!v.connected) {
    img.classList.add("hidden");
    st.replaceChildren(el("span", { class: "warn" }, "Board camera is off. "), "Start board_view to see the board here.");
    return;
  }
  img.classList.toggle("hidden", board);
  if (v.stamp && v.stamp !== lastCamStamp) { lastCamStamp = v.stamp; img.src = "/api/vision/board.jpg?" + encodeURIComponent(v.stamp); }
  const n = v.diffs.filter((d) => d.confirmed).length;
  if (v.blind) {
    st.replaceChildren(el("span", { class: "warn" }, "Camera can't see the pieces well (light?) "),
      "· keeping the tracked board as it is");
    return;
  }
  st.replaceChildren(
    el("span", { class: v.settled ? "ok" : "warn" }, v.settled ? "Camera: settled" : "Camera: " + (v.status || "waiting")),
    ` · ${v.stamp || ""} · board ${v.board || "?"}`,
    n ? el("span", { class: "warn" }, ` · ${n} land${n > 1 ? "s" : ""} differ from the tracker${v.auto ? " (auto-sync on)" : ""}`) : " · matches the tracker");
}

function render(snap) {
  if (S && S.boot && snap.boot && S.boot !== snap.boot) { location.reload(); return; }
  S = snap;
  renderStatus(); renderTrack(); renderNow(); renderInvaders(); renderLands(); renderCamera();
}

// ---------- remote / keyboard ----------
let busy = false;
async function act(action, msg) {
  if (busy) return; busy = true;
  try {
    const r = await fetch("/api/action", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...action, source: "tv" }) });
    const data = await r.json();
    if (!r.ok) toast(data.error || "That didn't work"); else { render(data); if (msg) toast(msg); }
  } catch (e) { toast("Can't reach the game server"); }
  setTimeout(() => (busy = false), 500);
}
document.addEventListener("keydown", (e) => {
  if (!S) return;
  const k = e.key;
  if (k === "ArrowRight" || k === "Enter" || k === " " || k === "MediaTrackNext") { e.preventDefault(); act({ type: "next" }, "Next step"); }
  else if (k === "ArrowLeft" || k === "Backspace" || k === "MediaTrackPrevious") { e.preventDefault(); if (S.state.status === "setup") act({ type: "back" }, "Back"); else if (S.can_undo) act({ type: "undo" }, "Undone"); }
  else if (k === "f" || k === "F") { if (S.state.status === "playing") act({ type: "fear", amount: 1 }, "+1 fear"); }
  else if ((k === "v" || k === "V") && S.vision && S.vision.has_map) {
    fetch("/api/vision", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ view: S.vision.view === "board" ? "photo" : "board" }) })
      .then((r) => r.json()).then(render).catch(() => toast("Can't reach the game server"));
  }
});

// ---------- live connection ----------
function connect() {
  const es = new EventSource("/api/events");
  es.onopen = () => $("conn").classList.add("live");
  es.onmessage = (m) => render(JSON.parse(m.data));
  es.onerror = () => $("conn").classList.remove("live");
}

(async function start() {
  REF = await (await fetch("/api/reference")).json();
  render(await (await fetch("/api/state")).json());
  connect();
  try {
    const links = await (await fetch("/api/links")).json();
    $("f-links").textContent = "Phone controls: " + links.phone.join("  or  ");
  } catch (e) { /* footer link is a nicety */ }
})();

// Keep the TV from dimming or sleeping while this page is up. The lock drops whenever the
// page is hidden, so take it again when it comes back.
async function keepAwake() {
  try { if (navigator.wakeLock && document.visibilityState === "visible") await navigator.wakeLock.request("screen"); }
  catch (e) { console.warn("wake lock:", e); }
}
document.addEventListener("visibilitychange", keepAwake);
keepAwake();
