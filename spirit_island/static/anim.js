// Little animated scenes for the setup steps, drawn as SVG so they scale to any screen.
// Shared by the phone (app.js) and the TV (tv.js). Every scene loops every 10 seconds.
//   {anim: "pool", count, label}                 tokens dropping into the fear pool
//   {anim: "stack", layers: [{src, count, label, removed}]}  a deck built bottom-up,
//                                                drawn top layer first
//   {anim: "blight", src, count}                 blight dropping onto the blight card

const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}, ...kids) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}

function dropIn(node, delay, kind = "drop") {
  node.setAttribute("class", "a-" + kind);
  node.style.animationDelay = delay + "s";
  return node;
}

function animScene(p) {
  const svg = svgEl("svg", { viewBox: "0 0 1600 900", class: "scene", preserveAspectRatio: "xMidYMid meet" });
  const scenes = { pool: poolScene, stack: stackScene, blight: blightScene, board: boardScene, photo: photoScene, setup: setupScene };
  (scenes[p.anim] || (() => {}))(svg, p);
  return svg;
}

// A fear marker: a round cardboard token with the fear mask printed on it.
function fearToken(x, y, r) {
  return svgEl("g", {},
    svgEl("circle", { cx: x, cy: y + r * 0.08, r, fill: "#7a5a3a" }),
    svgEl("circle", { cx: x, cy: y, r, fill: "#e8cfa0", stroke: "#a07a4a", "stroke-width": r * 0.08 }),
    svgEl("image", { href: "/assets/components/fear_icon.png", x: x - r * 0.68, y: y - r * 0.68, width: r * 1.36, height: r * 1.36 }));
}

function poolScene(svg, p) {
  // The real invader board, zoomed on the fear pool, with the markers dropping in.
  const n = p.count || 4;
  svg.setAttribute("viewBox", "250 0 500 300");
  svg.append(svgEl("image", { href: "/assets/components/invader_board_art.jpg", x: 0, y: 0, width: 1000, height: 907 }));
  svg.append(svgEl("rect", { x: 250, y: 0, width: 500, height: 300, fill: "rgba(0,0,0,.25)" }));
  const gap = Math.min(70, 300 / n);
  for (let i = 0; i < n; i++) {
    const x = 500 - ((n - 1) * gap) / 2 + i * gap;
    svg.append(dropIn(fearToken(x, 150, 28), 0.4 + i * 0.5));
  }
  svg.append(dropIn(svgEl("text", { x: 500, y: 270, "text-anchor": "middle", "font-size": 30, fill: "#fff", "font-weight": 700,
    stroke: "#000", "stroke-width": 1 }, `${n} fear marker${n > 1 ? "s" : ""} in the pool`), 0.4 + n * 0.5, "fade"));
}

function stackScene(svg, p) {
  const layers = p.layers || [];
  const rowH = Math.min(170, 780 / layers.length), cardH = rowH - 22, cardW = cardH * 0.71;
  const top = 450 - (layers.length * rowH) / 2;
  svg.append(svgEl("text", { x: 70, y: top + 40, "font-size": 40, fill: "#86dc93", "font-weight": 700 }, "TOP"));
  svg.append(svgEl("text", { x: 70, y: top + layers.length * rowH - 10, "font-size": 40, fill: "#a3b3a5", "font-weight": 700 }, "BOTTOM"));
  svg.append(svgEl("line", { x1: 120, y1: top + 60, x2: 120, y2: top + layers.length * rowH - 50, stroke: "#4c6b58",
    "stroke-width": 6, "marker-end": "none" }));
  // Built from the bottom up, so the bottom layer lands first.
  layers.forEach((L, i) => {
    const y = top + i * rowH + 10, order = layers.length - 1 - i, delay = 0.5 + order * 1.1;
    const g = svgEl("g", {});
    const count = L.count || 1;
    for (let k = 0; k < count; k++) {
      g.append(svgEl("image", { href: "/assets/" + L.src, x: 220 + k * cardW * 0.42, y, width: cardW, height: cardH,
        preserveAspectRatio: "xMidYMid slice" }));
    }
    const labelX = 220 + (count - 1) * cardW * 0.42 + cardW + 40;
    g.append(svgEl("text", { x: labelX, y: y + cardH / 2 + 18, "font-size": Math.min(52, rowH * 0.34), fill: "#f1f5ee",
      "font-weight": 600 }, L.label || ""));
    svg.append(dropIn(g, delay));
    if (L.removed) {
      const r = svgEl("g", {},
        svgEl("image", { href: "/assets/" + L.src, x: 1300, y, width: cardW, height: cardH }),
        svgEl("text", { x: 1300 + cardW / 2, y: y + cardH + 4, "text-anchor": "middle", "font-size": 26, fill: "#ff9c8f" },
          `${L.removed} removed, unseen`));
      svg.append(dropIn(r, delay + 0.4, "remove"));
    }
  });
}

function blightBlob(x, y, s) {
  const d = `M ${x - s} ${y} q ${s * 0.2} ${-s * 0.9} ${s} ${-s * 0.8} q ${s * 0.9} ${-s * 0.1} ${s} ${s * 0.7}` +
            ` q ${s * 0.1} ${s * 0.9} ${-s} ${s * 0.9} q ${-s * 0.9} 0 ${-s} ${-s * 0.8} z`;
  return svgEl("path", { d, fill: "#56677d", stroke: "#2b3542", "stroke-width": 5 });
}

function blightScene(svg, p) {
  const h = 760, w = h * 0.714, x = 800 - w / 2, y = 70;
  svg.append(dropIn(svgEl("image", { href: "/assets/" + p.src, x, y, width: w, height: h }), 0.2, "fade"));
  const n = p.count || 3;
  for (let i = 0; i < n; i++) {
    const bx = 800 - ((n - 1) * 110) / 2 + i * 110;
    svg.append(dropIn(blightBlob(bx, 610, 46), 1.2 + i * 0.6));
  }
  svg.append(dropIn(svgEl("text", { x: 800, y: 880, "text-anchor": "middle", "font-size": 50, fill: "#f1f5ee" },
    `${n} blight on the card`), 1.2 + n * 0.6, "fade"));
}

// A labelled diagram of the base-game invader board, laid out like the real one (square,
// four folds): fear cards down the left, fear pool and generated fear in the middle, terror
// level and blight on the right, invader slots along the bottom. Areas light up in turn.
function boardScene(svg) {
  svg.setAttribute("viewBox", "0 0 1000 1000");
  svg.append(svgEl("rect", { x: 10, y: 10, width: 980, height: 980, rx: 24, fill: "#2a3a2c", stroke: "#8a6a3c", "stroke-width": 8 }));
  svg.append(svgEl("line", { x1: 500, y1: 14, x2: 500, y2: 986, stroke: "rgba(0,0,0,.35)", "stroke-width": 4 }));
  svg.append(svgEl("line", { x1: 14, y1: 500, x2: 986, y2: 500, stroke: "rgba(0,0,0,.35)", "stroke-width": 4 }));
  const card = (x, y, w, h, label, sub, c) => ({ x, y, w, h, label, sub, c });
  const zones = [
    card(40, 40, 200, 290, "Fear deck", "face down", "#b993f5"),
    card(370, 40, 260, 110, "Fear pool", "markers start here", "#b993f5"),
    { ...card(400, 230, 200, 260, "Generated", "fear", "#b993f5"), round: true },
    card(40, 350, 200, 290, "Earned fear", "cards", "#b993f5"),
    card(40, 660, 200, 300, "Fear discard", "", "#8f949c"),
    card(780, 40, 180, 280, "Terror level", "I → II → III", "#b993f5"),
    card(780, 340, 180, 280, "Blight card", "blight on top", "#e08a5f"),
    card(270, 690, 210, 160, "Discard", "", "#8f949c"),
    card(520, 690, 130, 220, "Ravage", "", "#ff7a6b"),
    card(680, 690, 130, 220, "Build", "", "#f3c862"),
    card(840, 670, 130, 220, "Invader deck", "on Explore", "#86dc93"),
  ];
  svg.append(svgEl("rect", { x: 290, y: 545, width: 420, height: 100, rx: 18, fill: "#e9d8b0", opacity: .85 }));
  svg.append(svgEl("text", { x: 500, y: 605, "text-anchor": "middle", "font-size": 30, fill: "#4a3a20", "font-weight": 700 }, "Phase order scroll"));
  for (const z of zones) {
    svg.append(z.round
      ? svgEl("ellipse", { cx: z.x + z.w / 2, cy: z.y + z.h / 2, rx: z.w / 2, ry: z.h / 2, fill: "rgba(0,0,0,.25)", stroke: z.c, "stroke-width": 5, "stroke-dasharray": "12 9" })
      : svgEl("rect", { x: z.x, y: z.y, width: z.w, height: z.h, rx: 14, fill: "rgba(0,0,0,.25)", stroke: z.c, "stroke-width": 5, "stroke-dasharray": "12 9" }));
    const fs = z.w < 150 ? 21 : z.w <= 210 ? 28 : 34;
    svg.append(svgEl("text", { x: z.x + z.w / 2, y: z.y + z.h / 2 + (z.sub ? -4 : 10), "text-anchor": "middle", "font-size": fs, fill: "#f1f5ee", "font-weight": 700 }, z.label));
    if (z.sub) svg.append(svgEl("text", { x: z.x + z.w / 2, y: z.y + z.h / 2 + 30, "text-anchor": "middle", "font-size": 21, fill: "#cfd8cc" }, z.sub));
  }
  for (const x of [500, 660, 820]) svg.append(svgEl("text", { x: x + 5, y: 815, "text-anchor": "middle", "font-size": 40, fill: "#f1f5ee" }, "‹"));
  zones.forEach((z, i) => {
    const hl = z.round
      ? svgEl("ellipse", { cx: z.x + z.w / 2, cy: z.y + z.h / 2, rx: z.w / 2, ry: z.h / 2, fill: "rgba(255,210,80,.22)", stroke: "#ffd23a", "stroke-width": 8 })
      : svgEl("rect", { x: z.x, y: z.y, width: z.w, height: z.h, rx: 14, fill: "rgba(255,210,80,.22)", stroke: "#ffd23a", "stroke-width": 8 });
    hl.setAttribute("class", "a-spot");
    hl.style.animationDuration = zones.length * 1.6 + "s";
    hl.style.animationDelay = i * 1.6 + "s";
    svg.append(hl);
  });
}

// A photo with labelled areas lighting up in turn: {src, zones: [{x, y, w, h, label}]}
// (fractions of the photo).
function photoScene(svg, p) {
  const H = 1000 * (p.aspect || 1);
  svg.setAttribute("viewBox", `0 0 1000 ${H}`);
  svg.append(svgEl("image", { href: "/assets/" + p.src, x: 0, y: 0, width: 1000, height: H }));
  const n = (p.zones || []).length;
  (p.zones || []).forEach((z, i) => {
    const x = z.x * 1000, y = z.y * H, w = z.w * 1000, h = z.h * H;
    const g = svgEl("g", {},
      svgEl("rect", { x, y, width: w, height: h, rx: 14, fill: "rgba(255,210,80,.18)", stroke: "#ffd23a", "stroke-width": 7 }),
      svgEl("rect", { x: x + w / 2 - 120, y: y + h / 2 - 28, width: 240, height: 56, rx: 12, fill: "rgba(0,0,0,.78)" }),
      svgEl("text", { x: x + w / 2, y: y + h / 2 + 12, "text-anchor": "middle", "font-size": 34, fill: "#fff", "font-weight": 700 }, z.label));
    g.setAttribute("class", "a-spot");
    g.style.animationDuration = Math.max(10, n * 1.6) + "s";
    g.style.animationDelay = (i * 1.6) + "s";
    svg.append(g);
  });
}

// The invader board filling up as setup goes: {step: 1 pool, 2 fear deck, 3 blight, 4 invader
// deck, fear, deck: [n top, n mid, n bottom], blight}. Earlier steps' pieces sit in place; the
// current step's pieces animate into their space, with a note of what's going in.
function setupScene(svg, p) {
  const W = 1000, H = 907, step = p.step || 1;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.append(svgEl("image", { href: "/assets/components/invader_board_art.jpg", x: 0, y: 0, width: W, height: H }));
  const now = (k) => k === step;
  const notes = [];
  // The current step plays once and then holds still.
  const anim = (node, k, delay, kind) => (now(k) ? dropIn(node, delay, (kind || "drop") + "1") : node);

  // 1. fear markers in the pool
  if (step >= 1) {
    const n = p.fear || 4, gap = 46;
    for (let i = 0; i < n; i++) {
      const x = 510 - ((n - 1) * gap) / 2 + i * gap;
      svg.append(anim(fearToken(x, 45, 20), 1, 0.4 + i * 0.45));
    }
    if (now(1)) notes.push([`${n} fear markers`, 0.4]);
  }
  // 2. fear deck, built bottom up in the fear deck space
  if (step >= 2) {
    const [top, mid, bot] = p.deck || [3, 3, 3];
    const layers = [];
    for (let i = 0; i < bot; i++) layers.push(["fear_back", "fear card"]);
    layers.push(["terror_3", "Terror III divider"]);
    for (let i = 0; i < mid; i++) layers.push(["fear_back", "fear card"]);
    layers.push(["terror_2", "Terror II divider"]);
    for (let i = 0; i < top; i++) layers.push(["fear_back", "fear card"]);
    layers.forEach(([src], i) => {
      const off = i * 2.2;
      svg.append(anim(svgEl("image", { href: `/assets/components/${src}.jpg`, x: 22 + off, y: 24 - off, width: 192, height: 268,
        preserveAspectRatio: "xMidYMid slice" }), 2, 0.3 + i * 0.42));
    });
    if (now(2)) {
      let t = 0.3;
      notes.push([`${bot} fear cards`, t]); t += bot * 0.42;
      notes.push(["Terror III divider", t]); t += 0.42;
      notes.push([`${mid} fear cards`, t]); t += mid * 0.42;
      notes.push(["Terror II divider", t]); t += 0.42;
      notes.push([`${top} fear cards on top`, t]);
    }
  }
  // 3. blight card with blight on it
  if (step >= 3) {
    svg.append(anim(svgEl("image", { href: "/assets/components/blight_healthy.jpg", x: 788, y: 322, width: 192, height: 270,
      preserveAspectRatio: "xMidYMid slice" }), 3, 0.3));
    const n = p.blight || 3;
    for (let i = 0; i < n; i++) svg.append(anim(blightBlob(884 - ((n - 1) * 52) / 2 + i * 52, 470, 24), 3, 1.2 + i * 0.5));
    if (now(3)) { notes.push(["Blight card, Healthy side", 0.3]); notes.push([`${n} blight on it`, 1.2]); }
  }
  // 4. invader deck on the Explore space, built bottom up
  if (step >= 4) {
    const stages = [["stage3_back", 5, "Stage III"], ["stage2_back", 4, "Stage II"], ["stage1_back", 3, "Stage I"]];
    let i = 0, t = 0.3;
    for (const [src, n, label] of stages) {
      if (now(4)) {
        const gone = svgEl("image", { href: `/assets/components/${src}.jpg`, x: 846, y: 652, width: 131, height: 200 });
        svg.append(dropIn(gone, t, "remove1"));
        notes.push([`${label}: ${n} cards (1 to the box)`, t]);
      }
      for (let k = 0; k < n; k++, i++) {
        const off = i * 1.6;
        svg.append(anim(svgEl("image", { href: `/assets/components/${src}.jpg`, x: 846 + off, y: 652 - off, width: 131, height: 200,
          preserveAspectRatio: "xMidYMid slice" }), 4, t + 0.25 + k * 0.28));
      }
      t += 0.5 + n * 0.28;
    }
  }
  // What's going in, over the middle of the board, then (for the decks) a still picture of
  // the finished stack, top to bottom.
  const rows = step === 2 ? fearRows(p.deck || [3, 3, 3]) : step === 4 ? invaderRows() : [];
  if (notes.length) {
    const lineH = 38, rowH = 46;
    const textH = 30 + notes.length * lineH, picH = rows.length ? 50 + rows.length * rowH : 0;
    const top = 150;
    svg.append(svgEl("rect", { x: 260, y: top, width: 480, height: textH + picH + 16, rx: 18, fill: "rgba(10,18,14,.88)",
      stroke: "#ffd23a", "stroke-width": 3 }));
    notes.forEach(([text, delay], i) => svg.append(dropIn(svgEl("text", { x: 500, y: top + 40 + i * lineH, "text-anchor": "middle",
      "font-size": 26, fill: "#f1f5ee", "font-weight": 600 }, text), delay, "fade1")));
    if (rows.length) {
      const y0 = top + textH + 20;
      svg.append(svgEl("line", { x1: 280, y1: y0 - 8, x2: 720, y2: y0 - 8, stroke: "#4c6b58", "stroke-width": 2 }));
      svg.append(svgEl("text", { x: 285, y: y0 + 22, "font-size": 18, fill: "#86dc93", "font-weight": 700 }, "TOP"));
      svg.append(svgEl("text", { x: 285, y: y0 + rows.length * rowH - 4, "font-size": 18, fill: "#a3b3a5", "font-weight": 700 }, "BOTTOM"));
      rows.forEach(([src, count, label], i) => {
        const y = y0 + i * rowH;
        for (let k = 0; k < count; k++) {
          svg.append(svgEl("image", { href: `/assets/components/${src}.jpg`, x: 370 + k * 16, y, width: 29, height: 40,
            preserveAspectRatio: "xMidYMid slice" }));
        }
        svg.append(svgEl("text", { x: 370 + (count - 1) * 16 + 42, y: y + 28, "font-size": 23, fill: "#f1f5ee" }, label));
      });
    }
  }
}

function fearRows([top, mid, bot]) {
  return [["fear_back", top, `${top} fear cards`], ["terror_2", 1, "Terror II divider"],
          ["fear_back", mid, `${mid} fear cards`], ["terror_3", 1, "Terror III divider"],
          ["fear_back", bot, `${bot} fear cards`]];
}

function invaderRows() {
  return [["stage1_back", 3, "Stage I: 3 cards"], ["stage2_back", 4, "Stage II: 4 cards"], ["stage3_back", 5, "Stage III: 5 cards"]];
}
