// Drawn board: the camera's board as a clean, animated map. Lands are coloured by the
// terrain tagged in the game, the ocean moves, and pieces sit where the camera saw them.
// When a reading changes, pieces that moved glide to their new spot, new ones pop in and
// removed ones fade out. Used by both the TV and the phone.
"use strict";

const BoardMap = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const TERRAIN = { J: "#3e9a4f", W: "#3f98a6", S: "#d8b45c", M: "#8f949c" };
  const PRESENCE = { magenta: "#d24fc4", yellow: "#f2cf3a", red: "#e0463c", blue: "#3f7fe0", green: "#4fbf5a",
    orange: "#ee8a2e", purple: "#8e5ad8", white: "#f2f2f2" };
  const SIZE = 48;

  function svg(tag, attrs = {}, ...kids) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
    for (const kid of kids) if (kid) e.append(kid);
    return e;
  }

  // Simple silhouettes, centred on 0,0, about SIZE across.
  function shape(p) {
    const s = SIZE;
    switch (p.type) {
      case "explorer": return svg("path", { d: `M0 ${-s * .7} L${s * .45} ${s * .55} L${-s * .45} ${s * .55} Z`, class: "inv" });
      case "town": return svg("path", { d: `M${-s * .55} ${s * .5} V${-s * .05} L0 ${-s * .6} L${s * .55} ${-s * .05} V${s * .5} Z`, class: "inv" });
      case "city": return svg("path", { d: `M${-s * .7} ${s * .55} V${-s * .25} H${-s * .35} V${-s * .7} H${s * .05} V${-s * .25} H${s * .3} V${-s * .5} H${s * .7} V${s * .55} Z`, class: "inv" });
      case "dahan": return svg("circle", { r: s * .48, class: "dahan" });
      case "blight": return svg("path", { d: `M0 ${-s * .6} L${s * .2} ${-s * .2} L${s * .6} ${-s * .25} L${s * .3} ${s * .1} L${s * .5} ${s * .55} L0 ${s * .3} L${-s * .5} ${s * .55} L${-s * .3} ${s * .1} L${-s * .6} ${-s * .25} L${-s * .2} ${-s * .2} Z`, class: "blight" });
      case "presence": return svg("circle", { r: s * .42, class: "presence", fill: PRESENCE[p.colour] || "#b993f5" });
      case "energy": return null;
      default: return svg("circle", { r: s * .3, class: "unknown" });
    }
  }

  function create(container) {
    const root = svg("svg", { class: "boardmap", preserveAspectRatio: "xMidYMid meet" });
    const defs = svg("defs");
    defs.innerHTML = `
      <pattern id="bm-waves" width="80" height="40" patternUnits="userSpaceOnUse">
        <path d="M0 20 Q20 8 40 20 T80 20" fill="none" stroke="rgba(255,255,255,.13)" stroke-width="3"/>
        <animateTransform attributeName="patternTransform" type="translate" from="0 0" to="80 0" dur="9s" repeatCount="indefinite"/>
      </pattern>
      <radialGradient id="bm-sea" cx="50%" cy="50%" r="75%"><stop offset="0" stop-color="#1f5d86"/><stop offset="1" stop-color="#0b2236"/></radialGradient>
      <filter id="bm-shadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-opacity=".55"/></filter>`;
    const sea = svg("g"), lands = svg("g"), labels = svg("g", { class: "labels" }), pieces = svg("g");
    // Everything sits in one group, so the board can be turned to face the player.
    const world = svg("g", {}, sea, lands, labels, pieces);
    root.append(defs, world);
    container.replaceChildren(root);
    return { root, world, sea, lands, labels, pieces, map: null, els: [], rot: 0 };
  }

  // Turn the drawn board by 0, 90, 180 or 270 degrees (clockwise); pieces stay upright.
  function setRotation(v, deg) {
    v.rot = ((deg % 360) + 360) % 360;
    if (v.map) frame(v);
    for (const o of v.els) o.g.querySelector(".upright").setAttribute("transform", `rotate(${-v.rot})`);
  }

  function frame(v) {
    const pad = 40, W = v.map.width + 2 * pad, H = v.map.height + 2 * pad;
    const cx = v.map.width / 2, cy = v.map.height / 2, side = v.rot % 180 !== 0;
    const w = side ? H : W, h = side ? W : H;
    v.root.setAttribute("viewBox", `${cx - w / 2} ${cy - h / 2} ${w} ${h}`);
    v.world.setAttribute("transform", `rotate(${v.rot} ${cx} ${cy})`);
  }

  function setMap(v, map) {
    v.map = map;
    const pad = 40;
    frame(v);
    v.sea.replaceChildren(
      svg("rect", { x: -pad, y: -pad, width: map.width + 2 * pad, height: map.height + 2 * pad, fill: "url(#bm-sea)" }),
      svg("rect", { x: -pad, y: -pad, width: map.width + 2 * pad, height: map.height + 2 * pad, fill: "url(#bm-waves)" }));
    v.lands.replaceChildren(); v.labels.replaceChildren(); v.landEls = {};
    // With art from the real board (a straightened photo of your own copy), lands are
    // drawn see-through on top of it, only lighting up when a step affects them.
    v.root.classList.toggle("art", !!map.has_art);
    if (map.has_art) v.lands.append(svg("image", { href: "/api/vision/board_art.png?b=" + (map.board || "photo") + "-" + map.width + "x" + map.height, x: 0, y: 0,
      width: map.width, height: map.height, preserveAspectRatio: "none", class: "boardart" }));
    for (const l of map.lands) {
      if (l.name === "ocean") continue;
      const poly = svg("polygon", { points: l.points.map((p) => p.join(",")).join(" "), class: "land" });
      v.lands.append(poly);
      v.landEls[l.name] = poly;
      v.labels.append(svg("text", { x: l.centre[0], y: l.centre[1], class: "lnum" }, document.createTextNode(l.name)));
    }
  }

  // lands: {name: {terrain, hit}} from the game.
  function setLands(v, info) {
    for (const [name, poly] of Object.entries(v.landEls || {})) {
      const i = info[name] || {};
      poly.style.fill = TERRAIN[i.terrain] || "#6d6a5c";
      poly.classList.toggle("hit", !!i.hit);
    }
  }

  function setPieces(v, list) {
    const old = v.els.slice(), next = [];
    for (const p of list) {
      if (p.type === "energy") continue;
      const key = p.type + "|" + (p.colour || "");
      // The nearest unclaimed piece of the same kind is the "same" piece, if it's close.
      let best = null, bd = 140;
      for (const o of old) {
        if (o.claimed || o.key !== key) continue;
        const d = Math.hypot(o.x - p.x, o.y - p.y);
        if (d < bd) { bd = d; best = o; }
      }
      if (best) {
        best.claimed = true; best.x = p.x; best.y = p.y;
        best.g.style.transform = `translate(${p.x}px, ${p.y}px)`;
        next.push(best);
      } else {
        const inner = svg("g", { class: "bob" }, svg("g", { class: "upright", transform: `rotate(${-v.rot})` }, shape(p)));
        const g = svg("g", { class: "piece enter " + p.type, filter: "url(#bm-shadow)" }, inner);
        inner.style.animationDelay = (-Math.random() * 4).toFixed(2) + "s";
        g.style.transform = `translate(${p.x}px, ${p.y}px)`;
        v.pieces.append(g);
        requestAnimationFrame(() => requestAnimationFrame(() => g.classList.remove("enter")));
        next.push({ g, key, x: p.x, y: p.y });
      }
    }
    for (const o of old) {
      if (o.claimed) { o.claimed = false; continue; }
      o.g.classList.add("leave");
      setTimeout(() => o.g.remove(), 700);
    }
    for (const n of next) n.claimed = false;
    v.els = next;
  }

  return { create, setMap, setLands, setPieces, setRotation };
})();
