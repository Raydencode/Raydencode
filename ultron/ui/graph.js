/*
 * graph.js — force-directed canvas graph. No libraries.
 *
 * Canvas, not SVG: SVG needs a DOM node per element and stalls past ~1,500
 * nodes. Repulsion uses a spatial grid with a distance cutoff so cost stays
 * near-linear instead of O(n^2).
 */

const REPULSION_CUTOFF = 260;      // px — nodes further apart than this don't repel
const REPULSION_STRENGTH = 2600;
const SPRING_LENGTH = 130;
const SPRING_STRENGTH = 0.02;
const CENTER_STRENGTH = 0.0035;
const DAMPING = 0.86;
const IDLE_JITTER = 0.12;          // keeps the graph "breathing" instead of freezing solid — small on purpose, or nodes drift enough to dodge clicks
const MIN_RADIUS = 7;
const RADIUS_PER_DEGREE = 1.9;
const MAX_RADIUS = 34;
const LABEL_ZOOM_MIN = 0.55;       // don't draw labels when zoomed out past this
const PULSE_INTERVAL_MS = 3200;
const PULSE_DURATION_MS = 950;

const TYPE_COLORS = {
  client: "#ff7a33",
  project: "#4fb3ff",
  invoice: "#63d47a",
  note: "#a79bff",
  proposal: "#ffd166",
};
function colorForType(t) {
  return TYPE_COLORS[t] || "#9aa0a8";
}

class SpatialGrid {
  constructor(cellSize) {
    this.cellSize = cellSize;
    this.cells = new Map();
  }
  key(cx, cy) { return `${cx},${cy}`; }
  clear() { this.cells.clear(); }
  insert(node) {
    const cx = Math.floor(node.x / this.cellSize);
    const cy = Math.floor(node.y / this.cellSize);
    const k = this.key(cx, cy);
    let arr = this.cells.get(k);
    if (!arr) { arr = []; this.cells.set(k, arr); }
    arr.push(node);
  }
  nearby(node) {
    const cx = Math.floor(node.x / this.cellSize);
    const cy = Math.floor(node.y / this.cellSize);
    const out = [];
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const arr = this.cells.get(this.key(cx + dx, cy + dy));
        if (arr) out.push(...arr);
      }
    }
    return out;
  }
}

export class Graph {
  constructor(canvas, { onFocus } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onFocus = onFocus || (() => {});

    this.nodes = [];
    this.nodesById = new Map();
    this.edges = [];
    this.adjacency = new Map();

    this.activeTypes = new Set();
    this.hoveredNode = null;
    this.focusedNode = null;
    this.secondFocusedNode = null;
    this.pathNodeIds = new Set();
    this.pathEdgeKeys = new Set();

    this.transform = { scale: 1, x: 0, y: 0 };
    this.dragging = null; // { kind: 'pan'|'node', ... }
    this.lastPulseAt = performance.now();
    this.pulse = null; // { edge, start }

    this.grid = new SpatialGrid(REPULSION_CUTOFF);

    this._resize = this._resize.bind(this);
    window.addEventListener("resize", this._resize);
    this._resize();

    this._bindInput();
    this._tick = this._tick.bind(this);
    requestAnimationFrame(this._tick);
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = window.innerWidth * dpr;
    this.canvas.height = window.innerHeight * dpr;
    this.canvas.style.width = window.innerWidth + "px";
    this.canvas.style.height = window.innerHeight + "px";
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (this.transform.x === 0 && this.transform.y === 0) {
      this.transform.x = window.innerWidth / 2;
      this.transform.y = window.innerHeight / 2;
    }
  }

  setData(payload) {
    const degreeById = new Map();
    for (const e of payload.edges) {
      degreeById.set(e.source, (degreeById.get(e.source) || 0) + 1);
      degreeById.set(e.target, (degreeById.get(e.target) || 0) + 1);
    }

    this.nodes = payload.nodes.map((n, i) => {
      const angle = (i / payload.nodes.length) * Math.PI * 2;
      const r = 120 + Math.random() * 140;
      const degree = degreeById.get(n.id) || 0;
      return {
        ...n,
        degree,
        x: Math.cos(angle) * r,
        y: Math.sin(angle) * r,
        vx: 0, vy: 0,
        radius: Math.min(MAX_RADIUS, MIN_RADIUS + degree * RADIUS_PER_DEGREE),
      };
    });
    this.nodesById = new Map(this.nodes.map((n) => [n.id, n]));

    this.edges = payload.edges
      .map((e) => ({ source: this.nodesById.get(e.source), target: this.nodesById.get(e.target) }))
      .filter((e) => e.source && e.target);

    this.adjacency = new Map();
    for (const n of this.nodes) this.adjacency.set(n.id, new Set());
    for (const e of this.edges) {
      this.adjacency.get(e.source.id).add(e.target.id);
      this.adjacency.get(e.target.id).add(e.source.id);
    }

    this.activeTypes = new Set(this.nodes.map((n) => n.type));

    // run the simulation hot for a bit so it "settles on load"
    for (let i = 0; i < 160; i++) this._step();
  }

  setTypeActive(type, active) {
    if (active) this.activeTypes.add(type);
    else this.activeTypes.delete(type);
  }

  typeCounts() {
    const counts = {};
    for (const n of this.nodes) counts[n.type] = (counts[n.type] || 0) + 1;
    return counts;
  }

  topHubs(limit = 10) {
    return [...this.nodes].sort((a, b) => b.degree - a.degree).slice(0, limit);
  }

  focusById(id) {
    const n = this.nodesById.get(id);
    if (n) this._focus(n);
  }

  // -- input ----------------------------------------------------------

  _bindInput() {
    const c = this.canvas;
    c.addEventListener("mousedown", (e) => {
      const world = this._screenToWorld(e.clientX, e.clientY);
      const node = this._nodeAt(world.x, world.y);
      if (node) {
        this.dragging = { kind: "node", node };
      } else {
        this.dragging = { kind: "pan", startX: e.clientX, startY: e.clientY, ox: this.transform.x, oy: this.transform.y };
      }
    });
    window.addEventListener("mousemove", (e) => {
      if (this.dragging?.kind === "node") {
        const world = this._screenToWorld(e.clientX, e.clientY);
        this.dragging.node.x = world.x;
        this.dragging.node.y = world.y;
        this.dragging.node.vx = 0;
        this.dragging.node.vy = 0;
      } else if (this.dragging?.kind === "pan") {
        this.transform.x = this.dragging.ox + (e.clientX - this.dragging.startX);
        this.transform.y = this.dragging.oy + (e.clientY - this.dragging.startY);
      } else {
        const world = this._screenToWorld(e.clientX, e.clientY);
        this.hoveredNode = this._nodeAt(world.x, world.y);
        c.style.cursor = this.hoveredNode ? "pointer" : "grab";
      }
    });
    window.addEventListener("mouseup", () => { this.dragging = null; });

    c.addEventListener("click", (e) => {
      if (this._didDrag) { this._didDrag = false; return; }
      const world = this._screenToWorld(e.clientX, e.clientY);
      const node = this._nodeAt(world.x, world.y);
      if (!node) return;
      if (e.shiftKey && this.focusedNode && node !== this.focusedNode) {
        this.secondFocusedNode = node;
        this._computePath();
      } else {
        this._focus(node);
      }
    });

    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.08 : 0.92;
      const before = this._screenToWorld(e.clientX, e.clientY);
      this.transform.scale = Math.max(0.15, Math.min(4, this.transform.scale * factor));
      const after = this._screenToWorld(e.clientX, e.clientY);
      this.transform.x += (after.x - before.x) * this.transform.scale;
      this.transform.y += (after.y - before.y) * this.transform.scale;
    }, { passive: false });
  }

  _focus(node) {
    this.focusedNode = node;
    this.secondFocusedNode = null;
    this.pathNodeIds.clear();
    this.pathEdgeKeys.clear();
    this.onFocus(node);
  }

  _computePath() {
    this.pathNodeIds.clear();
    this.pathEdgeKeys.clear();
    if (!this.focusedNode || !this.secondFocusedNode) return;
    const start = this.focusedNode.id;
    const goal = this.secondFocusedNode.id;
    const prev = new Map();
    const visited = new Set([start]);
    const queue = [start];
    while (queue.length) {
      const cur = queue.shift();
      if (cur === goal) break;
      for (const next of this.adjacency.get(cur) || []) {
        if (!visited.has(next)) {
          visited.add(next);
          prev.set(next, cur);
          queue.push(next);
        }
      }
    }
    if (!visited.has(goal)) return;
    let cur = goal;
    const chain = [cur];
    while (cur !== start) {
      cur = prev.get(cur);
      if (cur === undefined) return;
      chain.push(cur);
    }
    chain.forEach((id) => this.pathNodeIds.add(id));
    for (let i = 0; i < chain.length - 1; i++) {
      this.pathEdgeKeys.add(this._edgeKey(chain[i], chain[i + 1]));
    }
  }

  _edgeKey(a, b) { return a < b ? `${a}|${b}` : `${b}|${a}`; }

  _screenToWorld(sx, sy) {
    const rect = this.canvas.getBoundingClientRect();
    const x = (sx - rect.left - this.transform.x) / this.transform.scale;
    const y = (sy - rect.top - this.transform.y) / this.transform.scale;
    return { x, y };
  }

  _nodeAt(x, y) {
    let best = null, bestD = Infinity;
    for (const n of this.nodes) {
      if (!this.activeTypes.has(n.type)) continue;
      const d = Math.hypot(n.x - x, n.y - y);
      if (d <= n.radius + 4 && d < bestD) { best = n; bestD = d; }
    }
    return best;
  }

  // -- physics ----------------------------------------------------------

  _step() {
    this.grid.clear();
    for (const n of this.nodes) this.grid.insert(n);

    for (const n of this.nodes) {
      let fx = 0, fy = 0;
      for (const other of this.grid.nearby(n)) {
        if (other === n) continue;
        let dx = n.x - other.x, dy = n.y - other.y;
        let dist = Math.hypot(dx, dy) || 0.01;
        if (dist < REPULSION_CUTOFF) {
          const force = REPULSION_STRENGTH / (dist * dist);
          fx += (dx / dist) * force;
          fy += (dy / dist) * force;
        }
      }
      fx += -n.x * CENTER_STRENGTH;
      fy += -n.y * CENTER_STRENGTH;
      fx += (Math.random() - 0.5) * IDLE_JITTER;
      fy += (Math.random() - 0.5) * IDLE_JITTER;
      n.vx = (n.vx + fx) * DAMPING;
      n.vy = (n.vy + fy) * DAMPING;
    }

    for (const e of this.edges) {
      const dx = e.target.x - e.source.x, dy = e.target.y - e.source.y;
      const dist = Math.hypot(dx, dy) || 0.01;
      const force = (dist - SPRING_LENGTH) * SPRING_STRENGTH;
      const fx = (dx / dist) * force, fy = (dy / dist) * force;
      e.source.vx += fx; e.source.vy += fy;
      e.target.vx -= fx; e.target.vy -= fy;
    }

    for (const n of this.nodes) {
      if (this.dragging?.kind === "node" && this.dragging.node === n) continue;
      n.x += n.vx;
      n.y += n.vy;
    }
  }

  // -- render ----------------------------------------------------------

  _tick(now) {
    this._step();
    this._maybeStartPulse(now);
    this._render(now);
    requestAnimationFrame(this._tick);
  }

  _maybeStartPulse(now) {
    if (this.pulse && now - this.pulse.start < PULSE_DURATION_MS) return;
    if (now - this.lastPulseAt < PULSE_INTERVAL_MS) return;
    this.lastPulseAt = now;
    if (!this.edges.length) return;
    const edge = this.edges[Math.floor(Math.random() * this.edges.length)];
    this.pulse = { edge, start: now };
  }

  _render(now) {
    const ctx = this.ctx;
    const w = window.innerWidth, h = window.innerHeight;
    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(this.transform.x, this.transform.y);
    ctx.scale(this.transform.scale, this.transform.scale);

    const highlightActive = !!(this.hoveredNode || this.focusedNode);
    const litIds = this._litNodeIds();

    // edges
    for (const e of this.edges) {
      if (!this.activeTypes.has(e.source.type) || !this.activeTypes.has(e.target.type)) continue;
      const key = this._edgeKey(e.source.id, e.target.id);
      const onPath = this.pathEdgeKeys.has(key);
      const lit = onPath || (litIds.has(e.source.id) && litIds.has(e.target.id));
      let alpha = 0.16;
      if (highlightActive) alpha = lit ? 0.85 : 0.04;
      if (onPath) alpha = 1;
      ctx.strokeStyle = onPath ? "#ffffff" : `rgba(180,185,195,${alpha})`;
      ctx.lineWidth = onPath ? 2 / this.transform.scale : 1 / this.transform.scale;
      ctx.beginPath();
      ctx.moveTo(e.source.x, e.source.y);
      ctx.lineTo(e.target.x, e.target.y);
      ctx.stroke();
    }

    // idle pulse
    if (this.pulse) {
      const t = Math.min(1, (now - this.pulse.start) / PULSE_DURATION_MS);
      const { source, target } = this.pulse.edge;
      const px = source.x + (target.x - source.x) * t;
      const py = source.y + (target.y - source.y) * t;
      const alpha = Math.sin(t * Math.PI);
      ctx.beginPath();
      ctx.fillStyle = `rgba(255,122,51,${alpha})`;
      ctx.shadowColor = "rgba(255,122,51,0.8)";
      ctx.shadowBlur = 12;
      ctx.arc(px, py, 3 / this.transform.scale, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    // nodes
    const placedLabels = [];
    const sorted = [...this.nodes].sort((a, b) => b.degree - a.degree);
    for (const n of sorted) {
      if (!this.activeTypes.has(n.type)) continue;
      const lit = litIds.has(n.id) || this.pathNodeIds.has(n.id);
      let alpha = 1;
      if (highlightActive) alpha = lit ? 1 : 0.1;

      const isHover = n === this.hoveredNode;
      const isFocus = n === this.focusedNode || n === this.secondFocusedNode;
      const r = n.radius * (isHover || isFocus ? 1.18 : 1);

      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.fillStyle = colorForType(n.type);
      if (isFocus || isHover) {
        ctx.shadowColor = colorForType(n.type);
        ctx.shadowBlur = 18;
      } else {
        ctx.shadowBlur = 0;
      }
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      if (isFocus) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2 / this.transform.scale;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      if (alpha > 0.3 && this.transform.scale > LABEL_ZOOM_MIN) {
        this._drawLabel(ctx, n, r, placedLabels, lit || !highlightActive);
      }
    }

    ctx.restore();
  }

  _litNodeIds() {
    const ids = new Set();
    const focus = this.hoveredNode || this.focusedNode;
    if (focus) {
      ids.add(focus.id);
      for (const nb of this.adjacency.get(focus.id) || []) ids.add(nb);
    }
    for (const id of this.pathNodeIds) ids.add(id);
    return ids;
  }

  _drawLabel(ctx, n, r, placed, fullOpacity) {
    const fontSize = Math.max(10, 12 / Math.max(0.6, this.transform.scale)) ;
    ctx.font = `${fontSize}px -apple-system, sans-serif`;
    const text = n.title.length > 28 ? n.title.slice(0, 27) + "…" : n.title;
    const metrics = ctx.measureText(text);
    const boxW = metrics.width + 10;
    const boxH = fontSize + 6;
    const bx = n.x - boxW / 2;
    const by = n.y + r + 4;

    for (const box of placed) {
      if (bx < box.x + box.w && bx + boxW > box.x && by < box.y + box.h && by + boxH > box.y) {
        return; // collides with an already-placed label — skip it
      }
    }
    placed.push({ x: bx, y: by, w: boxW, h: boxH });

    ctx.globalAlpha = fullOpacity ? 0.95 : 0.35;
    ctx.fillStyle = "#d7d5d0";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText(text, n.x, by + 3);
    ctx.globalAlpha = 1;
  }
}
