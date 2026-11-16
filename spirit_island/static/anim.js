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
  const scenes = { pool: poolScene, stack: stackScene, blight: blightScene };
  (scenes[p.anim] || (() => {}))(svg, p);
  return svg;
}

function fearToken(x, y, r) {
  return svgEl("g", {},
    svgEl("circle", { cx: x, cy: y, r, fill: "#6d4fb3", stroke: "#e9ddff", "stroke-width": 6 }),
    svgEl("text", { x, y: y + r * 0.35, "text-anchor": "middle", "font-size": r, fill: "#f4ecff", "font-weight": 700 }, "✷"));
}

function poolScene(svg, p) {
  const n = p.count || 4;
  svg.append(svgEl("rect", { x: 300, y: 170, width: 1000, height: 480, rx: 240, fill: "rgba(140,110,200,.18)",
    stroke: "#b993f5", "stroke-width": 8, "stroke-dasharray": "24 16" }));
  svg.append(svgEl("text", { x: 800, y: 130, "text-anchor": "middle", "font-size": 64, fill: "#d9c8ff", "font-weight": 700 },
    p.label || "Fear pool"));
  const gap = Math.min(170, 800 / n);
  for (let i = 0; i < n; i++) {
    const x = 800 - ((n - 1) * gap) / 2 + i * gap;
    svg.append(dropIn(fearToken(x, 410, 62), 0.4 + i * 0.5));
  }
  svg.append(dropIn(svgEl("text", { x: 800, y: 790, "text-anchor": "middle", "font-size": 58, fill: "#f1f5ee" },
    `${n} fear marker${n > 1 ? "s" : ""}`), 0.4 + n * 0.5, "fade"));
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
