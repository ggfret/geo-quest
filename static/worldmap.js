// A world map built from /api/map with every country as its own shape.
// Used by the map games: colour countries, drop pins, draw lines, zoom and pan.
//
// Zoomable maps wrap around like a globe: the world is drawn three times side by side
// (the middle copy plus one on each side, via <use>), and the view slides a whole world
// width whenever you pan past the edge, so you can scroll from New Zealand into the
// Pacific and on to South America without ever hitting a wall.
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

class WorldMap {
  // The map data is fetched once per page and cached by the browser.
  static data() {
    if (!WorldMap.cache) WorldMap.cache = fetch("/api/map").then((r) => r.json());
    return WorldMap.cache;
  }

  constructor(container, { zoomable = false, label = "World map" } = {}) {
    this.container = container;
    this.zoomable = zoomable;
    this.wrap = zoomable;
    this.label = label;
    this.onPick = null;   // called with {x, y} when the map is clicked (not dragged)
    this.marks = [];      // {id, cls} currently highlighted, so tiny ones can get a ring
    this.overlays = [];   // pins, resized when zooming
    WorldMap.count = (WorldMap.count || 0) + 1;
    this.id = `world-${WorldMap.count}`;
    // Game maps fill a tall frame (see .map-frame.tall); the view takes the frame's shape.
    if (zoomable) container.classList.add("tall");
  }

  async load() {
    const { width, height, paths, places } = await WorldMap.data();
    Object.assign(this, { W: width, H: height, places, ratio: width / height });
    this.svg = svgEl("svg", { class: "worldmap", role: "img", "aria-label": this.label });
    this.world = svgEl("g", { id: this.id, class: "world" });
    this.land = svgEl("g");
    this.rings = svgEl("g");
    this.top = svgEl("g");
    this.world.append(this.land, this.rings, this.top);
    this.svg.append(this.world);
    if (this.wrap) {
      for (const dx of [-width, width]) this.svg.append(svgEl("use", { href: `#${this.id}`, x: dx }));
    }
    this.paths = {};
    for (const [id, d] of Object.entries(paths)) {
      const p = svgEl("path", { d, class: "country" });
      p.dataset.id = id;
      this.paths[id] = p;
      this.land.append(p);
    }
    this.container.prepend(this.svg);
    this.measure();
    this.reset();
    if (this.zoomable) {
      this.enableZoom();
      // Keep the same centre and zoom when the window (or a hidden board) changes size.
      new ResizeObserver(() => {
        const { x, w, h } = this.view, cy = this.view.y + h / 2;
        if (!this.measure()) return;
        this.setView(x, cy - w / this.ratio / 2, w);
      }).observe(this.container);
    }
    return this;
  }

  // Width / height of the visible map. Returns true if it changed.
  measure() {
    const box = this.container.getBoundingClientRect();
    const ratio = this.zoomable && box.width && box.height ? box.width / box.height : this.W / this.H;
    const changed = Math.abs(ratio - (this.ratio || 0)) > 0.001;
    this.ratio = ratio;
    return changed;
  }

  // The widest view that still fits the map's height (all of it on wide screens, less on phones).
  maxWidth() {
    return Math.min(this.W, this.H * this.ratio);
  }

  // ---------- View ----------
  setView(x, y, w) {
    w = Math.min(Math.max(w, 12), this.maxWidth());
    const h = w / this.ratio;
    if (this.wrap) {
      x -= Math.floor((x + w / 2) / this.W) * this.W;  // keep the centre on the middle copy
    } else {
      x = w >= this.W ? 0 : Math.min(Math.max(x, 0), this.W - w);
    }
    y = h >= this.H ? 0 : Math.min(Math.max(y, 0), this.H - h);
    this.view = { x, y, w, h };
    this.svg.setAttribute("viewBox", `${x} ${y} ${w} ${h}`);
    this.resize();
  }

  // The whole world (or as much as fits), leaning north where most land is.
  reset({ animate = false } = {}) {
    const w = this.maxWidth(), h = w / this.ratio;
    this.goTo(0, Math.max(0, (this.H - h) * 0.35), w, animate);
  }

  // Frame a set of boxes [x0, y0, x1, y1], with some surroundings for context.
  fit(boxes, { pad = 0.6, minW = 90, animate = false } = {}) {
    boxes = boxes.filter(Boolean);
    if (!boxes.length) return this.reset({ animate });
    const x0 = Math.min(...boxes.map((b) => b[0])), y0 = Math.min(...boxes.map((b) => b[1]));
    const x1 = Math.max(...boxes.map((b) => b[2])), y1 = Math.max(...boxes.map((b) => b[3]));
    const w = Math.max(minW, (x1 - x0) * (1 + pad), (y1 - y0) * (1 + pad) * this.ratio);
    this.goTo((x0 + x1) / 2 - w / 2, (y0 + y1) / 2 - w / this.ratio / 2, w, animate);
  }

  // Jump, or glide over ~half a second, to a view. On the wrap-around map it takes the short way round.
  goTo(x, y, w, animate = false) {
    cancelAnimationFrame(this.gliding);
    if (!animate || !this.view) return this.setView(x, y, w);
    const from = { ...this.view };
    if (this.wrap) x = this.closestCopy(x + w / 2, from.x + from.w / 2) - w / 2;
    const started = performance.now(), duration = 500;
    const step = (now) => {
      const t = Math.min(1, (now - started) / duration);
      const e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;  // ease in and out
      this.setView(from.x + (x - from.x) * e, from.y + (y - from.y) * e, from.w + (w - from.w) * e);
      if (t < 1) this.gliding = requestAnimationFrame(step);
    };
    this.gliding = requestAnimationFrame(step);
  }

  box(id) {
    return this.places[id]?.box;
  }

  // A point on the map, moved onto the main copy of the world (x between 0 and the map width).
  normalize(p) {
    return { x: ((p.x % this.W) + this.W) % this.W, y: p.y };
  }

  // The copy of x (x, x ± one world width) closest to `near`: for drawing across the date line.
  closestCopy(x, near) {
    return [x - this.W, x, x + this.W].reduce((best, c) => (Math.abs(c - near) < Math.abs(best - near) ? c : best));
  }

  zoomAt(p, factor) {
    cancelAnimationFrame(this.gliding);
    const w = Math.min(Math.max(this.view.w * factor, 12), this.maxWidth());
    const k = w / this.view.w;
    this.setView(p.x - (p.x - this.view.x) * k, p.y - (p.y - this.view.y) * k, w);
  }

  toMap(clientX, clientY) {
    const pt = new DOMPoint(clientX, clientY).matrixTransform(this.svg.getScreenCTM().inverse());
    return { x: pt.x, y: pt.y };
  }

  // Where a map point is on screen, relative to the map's box (for floating labels like "+10 XP").
  toScreen(x, y) {
    const x2 = this.wrap ? this.closestCopy(x, this.view.x + this.view.w / 2) : x;
    const pt = new DOMPoint(x2, y).matrixTransform(this.svg.getScreenCTM());
    const box = this.container.getBoundingClientRect();
    return { left: pt.x - box.left, top: pt.y - box.top };
  }

  // ---------- Colouring countries ----------
  mark(id, cls) {
    this.paths[id]?.classList.add(cls);
    this.marks.push({ id, cls });
    this.resize();
  }

  unmark(cls) {
    for (const p of Object.values(this.paths)) p.classList.remove(cls);
    this.marks = this.marks.filter((m) => m.cls !== cls);
    this.resize();
  }

  clear() {
    for (const p of Object.values(this.paths)) p.setAttribute("class", "country");
    this.marks = [];
    this.overlays = [];
    this.top.replaceChildren();
    this.resize();
  }

  // ---------- Pins and lines (kept the same size on screen while zooming) ----------
  pin(x, y, cls = "pin") {
    const el = svgEl("circle", { cx: x, cy: y, class: cls });
    this.top.append(el);
    this.overlays.push({ el, kind: "pin" });
    this.resize();
    return el;
  }

  line(x1, y1, x2, y2, cls = "miss-line") {
    const el = svgEl("line", { x1, y1, x2, y2, class: cls });
    this.top.prepend(el);
    return el;
  }

  remove(el) {
    el?.remove();
    this.overlays = this.overlays.filter((o) => o.el !== el);
  }

  // Tiny countries (smaller than ~1.5% of the view) get a ring so you can see them.
  resize() {
    if (!this.view) return;
    const unit = this.view.w / 100;
    for (const o of this.overlays) o.el.setAttribute("r", unit * 0.9);
    this.rings.replaceChildren();
    for (const { id, cls } of this.marks) {
      const place = this.places[id];
      if (!place) continue;
      const [x0, y0, x1, y1] = place.box;
      if (Math.max(x1 - x0, y1 - y0) < unit * 1.5) {
        this.rings.append(svgEl("circle", { cx: place.cx, cy: place.cy, r: unit * 1.6, class: `ring ${cls}` }));
      }
    }
  }

  // ---------- Zoom and pan: wheel/trackpad, drag, pinch, and + / − buttons ----------
  enableZoom() {
    const svg = this.svg;
    svg.classList.add("zoomable");
    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.zoomAt(this.toMap(e.clientX, e.clientY), Math.exp(Math.max(-1, Math.min(1, e.deltaY * 0.002))));
    }, { passive: false });

    const pointers = new Map();
    let start = null;
    const begin = (moved) => ({
      view: { ...this.view }, moved, pts: [...pointers.values()],
      scale: this.view.w / svg.getBoundingClientRect().width,
    });
    svg.addEventListener("pointerdown", (e) => {
      cancelAnimationFrame(this.gliding);
      svg.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      start = begin(pointers.size > 1);
      if (start.pts.length === 2) {
        const [a, b] = start.pts;
        start.mid = this.toMap((a.x + b.x) / 2, (a.y + b.y) / 2);
      }
    });
    svg.addEventListener("pointermove", (e) => {
      if (!pointers.has(e.pointerId) || !start) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const pts = [...pointers.values()];
      if (pts.length === 1) {
        const dx = pts[0].x - start.pts[0].x, dy = pts[0].y - start.pts[0].y;
        if (Math.hypot(dx, dy) > 5) start.moved = true;
        if (start.moved) this.setView(start.view.x - dx * start.scale, start.view.y - dy * start.scale, start.view.w);
      } else if (pts.length === 2 && start.mid) {
        const d0 = Math.hypot(start.pts[0].x - start.pts[1].x, start.pts[0].y - start.pts[1].y);
        const d1 = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
        const w = start.view.w * (d0 / Math.max(d1, 1));
        const k = w / start.view.w;
        this.setView(start.mid.x - (start.mid.x - start.view.x) * k, start.mid.y - (start.mid.y - start.view.y) * k, w);
      }
    });
    const end = (e) => {
      if (!pointers.has(e.pointerId)) return;
      pointers.delete(e.pointerId);
      if (e.type === "pointerup" && pointers.size === 0 && start && !start.moved && this.onPick) {
        this.onPick(this.normalize(this.toMap(e.clientX, e.clientY)));
      }
      // One finger lifted after a pinch: carry on panning with the other one, without a jump.
      start = pointers.size === 1 ? begin(true) : null;
    };
    svg.addEventListener("pointerup", end);
    svg.addEventListener("pointercancel", end);

    const controls = document.createElement("div");
    controls.className = "map-controls";
    controls.innerHTML = `<button type="button" aria-label="Zoom in">+</button>
      <button type="button" aria-label="Zoom out">−</button>
      <button type="button" aria-label="Show the whole world">⟲</button>`;
    const [zin, zout, zreset] = controls.querySelectorAll("button");
    const centre = () => ({ x: this.view.x + this.view.w / 2, y: this.view.y + this.view.h / 2 });
    zin.addEventListener("click", () => this.zoomAt(centre(), 1 / 1.6));
    zout.addEventListener("click", () => this.zoomAt(centre(), 1.6));
    zreset.addEventListener("click", () => this.reset());
    this.container.append(controls);
  }
}
