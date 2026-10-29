// The knowledge graph as a star map (D128): every entity is a point, placed once by graph
// structure (scripts/build_starmap.py), and what a question finds is lit as the answer is
// worked out. The page sends the server's progress events here; nothing in an answer depends
// on this view, and without WebGL or a built map the page answers as before.
"use strict";

const StarMap = (() => {
  const FOV = 40 * Math.PI / 180, FOLDED = 92;
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const ease = x => 1 - Math.pow(1 - clamp(x), 3);
  const smooth = x => { x = clamp(x); return x * x * (3 - 2 * x); };
  const lerp = (a, b, u) => a + (b - a) * u;
  const hash = n => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
  const noise = x => { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return hash(i) * (1 - u) + hash(i + 1) * u; };
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]], add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s], dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = a => { const l = Math.hypot(...a) || 1; return scale(a, 1 / l); };
  const SERIF = '"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif';
  const SANS = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  const TINT = { Disease: "182,86,62", Drug: "62,94,138", Phenotype: "178,128,52", Gene: "90,90,96" };

  function perspective(fovy, aspect, near, far) { const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far); return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0]; }
  function lookAt(eye, c, up) { const z = norm(sub(eye, c)), x = norm(cross(up, z)), y = cross(z, x); return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -dot(x, eye), -dot(y, eye), -dot(z, eye), 1]; }
  function mul(a, b) { const o = new Array(16); for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) { let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k]; o[c * 4 + r] = s; } return o; }
  function makePath(pts) { const cum = [0]; for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])); return { pts, cum, len: cum[cum.length - 1] || 1 }; }
  function at(P, f) {
    const L = clamp(f) * P.len, c = P.cum; let lo = 0, hi = c.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (c[m] <= L) lo = m; else hi = m; }
    const a = P.pts[lo], b = P.pts[hi], u = (L - c[lo]) / ((c[hi] - c[lo]) || 1);
    return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
  }

  // ---------- the map ----------
  let MAP = null, loading = null;
  function decode(b64, Type) { const s = atob(b64), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return new Type(u.buffer); }
  function load() {
    if (!loading) loading = fetch("/starmap").then(r => r.ok ? r.json() : null).then(raw => {
      if (!raw) return null;
      const pos = decode(raw.pos, Float32Array), type = decode(raw.type, Uint8Array), region = decode(raw.region, Uint8Array), n = raw.count;
      const nebulae = raw.types.map((name, t) => {
        let s = [0, 0, 0], k = 0, total = 0;
        for (let i = 0; i < n; i++) if (type[i] === t) { total++; if (i % 7 === 0) { s = add(s, [pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]]); k++; } }
        const c = scale(s, 1 / Math.max(1, k)), d = [];
        for (let i = 0; i < n; i += 5) if (type[i] === t) d.push(Math.hypot(pos[i * 3] - c[0], pos[i * 3 + 2] - c[2]));
        d.sort((a, b) => a - b);
        return { name: { Drug: "Drugs", Disease: "Diseases", Phenotype: "Phenotypes", Gene: "Genes" }[name] || name, c, total, rim: (d[Math.floor(d.length * .9)] || .5) * 1.12 };
      });
      const areas = raw.areas.map(([t, name, x, y, z, count]) => ({ t, name, c: [x, y, z], count, r: raw.regions.indexOf(name) + 1 }));
      MAP = { n, pos, type, region, nebulae, areas, P: i => [pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]] };
      return MAP;
    }).catch(() => null);
    return loading;
  }

  // ---------- one question's trail, built from its events ----------
  function frameShot(t, dur, pts, o = {}) {
    let c = [0, 0, 0]; pts.forEach(p => { c = add(c, p); }); c = scale(c, 1 / Math.max(1, pts.length));
    const d = pts.map(p => Math.hypot(...sub(p, c))).sort((a, b) => a - b);
    const r = Math.max(o.minR || .25, d[Math.floor((d.length - 1) * .85)] || 0);
    return { t, dur, target: c, dist: r / Math.sin(FOV / 2) * (o.pad || 1.15), yaw: o.yaw, pitch: o.pitch ?? .32, blur: o.blur ?? .9, labels: o.labels ?? 1 };
  }
  function arc(a, b, bow = .22) {
    const d = sub(b, a), len = Math.hypot(...d), side = norm(cross(d, [0, 1, 0]));
    const c = add(add(scale(add(a, b), .5), scale(side, len * .12)), [0, len * bow, 0]);
    const pts = []; for (let k = 0; k <= 40; k++) { const u = k / 40, v = 1 - u; pts.push([0, 1, 2].map(i => v * v * a[i] + 2 * v * u * c[i] + u * u * b[i])); }
    return pts;
  }
  class Trail {
    constructor() {
      this.nodes = new Map(); this.edges = []; this.steps = []; this.yaw = .5;
      this.shots = [{ t: 0, dur: 1, target: [0, 0, 0], dist: 4.4, yaw: .5, pitch: .42, blur: .2, labels: 0 }];
      this.said = [[0, "Reading the question among " + MAP.n.toLocaleString("en") + " entities"]];
      this.cursor = .6; this.end = null; this.found = 0; this.passages = 0;
    }
    node(i, o) { let n = this.nodes.get(i); if (!n) { n = { i, p: MAP.P(i), seed: i % 97 }; this.nodes.set(i, n); } Object.assign(n, o); return n; }
    from(now) { this.cursor = Math.max(this.cursor, now); return this.cursor; }
    say(t, text) { this.said.push([t, text]); }
    shot(t, dur, pts, o) { this.yaw += .1; this.shots.push(frameShot(t, dur, pts, { yaw: this.yaw, ...o })); }
    edge(a, b, start, dur, fizzle = false) { this.edges.push({ a, b, start, dur, fizzle, pts3: arc(this.nodes.get(a).p, this.nodes.get(b).p), seed: this.edges.length * 7.31 + 1.7 }); }
    linked(ev, now) {
      const list = ev.entities.filter(e => e.i != null); if (!list.length) return;
      const t = this.from(now);
      list.forEach((e, k) => this.node(e.i, { kind: "anchor", label: e.name, tag: e.label.toUpperCase(), tint: e.label, litAt: t + k * .35 }));
      this.shot(t, 1.3, list.map(e => MAP.P(e.i)), { labels: 0, blur: .6, minR: .2 });
      this.say(t, "Found " + list.map(e => `${e.name}, ${e.label.toLowerCase()}`).join("; "));
      this.cursor = t + .9 + .35 * (list.length - 1);
    }
    thinking(now) { this.say(Math.max(now, this.cursor), this.steps.length ? "Deciding what to look up next" : "Deciding what to look up"); }
    writing(now) { this.say(this.from(now), "Writing the answer from what was found"); }
    step(ev, now) {
      this.steps.push(ev);
      const t = this.from(now), placed = list => (list || []).filter(x => x.i != null);
      const results = placed(ev.results), found = new Set(results.map(r => r.i));
      const earlier = (ev.within || []).flatMap(k => placed(this.steps[k - 1]?.results));
      const before = new Set(earlier.map(r => r.i));
      // A lookup over an earlier one's results that returns mostly the same entities is a filter:
      // what it returns is confirmed, the rest stays dark.
      const filter = earlier.length > 0 && results.length > 0 && results.filter(r => before.has(r.i)).length >= results.length / 2;
      let sources = placed(ev.sources).map(s => s.i);
      sources.forEach(i => { if (!this.nodes.has(i)) this.node(i, { kind: "mid", label: "", litAt: t }); });
      if (!filter && !sources.length) sources = [...before].filter(i => this.nodes.has(i));
      if (ev.kind === "text" || ev.kind === "overview" || ev.kind === "count") {
        sources.forEach(i => { this.nodes.get(i).readAt = t; });
        if (ev.kind === "text") this.passages += ev.rows;
        this.say(t, ev.kind === "text" ? `Reading ${ev.rows} passages` : (ev.description || "Counting the records"));
        if (sources.length) this.shot(t - .1, 1.2, sources.map(i => this.nodes.get(i).p), { minR: .3 });
        this.cursor = t + 1.1;
        return;
      }
      const near = i => sources.reduce((best, s) => best == null || Math.hypot(...sub(this.nodes.get(s).p, MAP.P(i))) < Math.hypot(...sub(this.nodes.get(best).p, MAP.P(i))) ? s : best, null);
      const shown = results.slice(0, 80), stagger = Math.min(.14, 1.6 / Math.max(1, shown.length));
      let last = t + .4;
      const every = sources.length <= 3;
      shown.forEach((r, k) => {
        const n = this.node(r.i, { label: r.name, kind: this.nodes.get(r.i)?.kind === "anchor" ? "anchor" : "mid" });
        const start = t + k * stagger, from = every ? sources : [near(r.i)];
        let arrive = start + .3;
        from.forEach((s, j) => { if (s != null && s !== r.i) { this.edge(s, r.i, start + j * .12, 1.15); arrive = Math.max(arrive, start + j * .12 + 1.15); } });
        if (filter && before.has(r.i)) n.confirmAt = arrive; else if (n.litAt == null) n.litAt = arrive;
        last = Math.max(last, arrive);
      });
      const dark = [];
      if (filter) earlier.forEach(r => { if (!found.has(r.i) && !dark.includes(r.i)) dark.push(r.i); });
      placed(ev.expected).forEach(x => { if (!found.has(x.i)) { if (!this.nodes.has(x.i)) this.node(x.i, { kind: "mid", label: "", litAt: t }); dark.push(x.i); } });
      dark.forEach((i, k) => {
        const n = this.nodes.get(i), from = near(i), start = t + k * stagger;
        if (from != null && from !== i) this.edge(from, i, start, 1.15, true);
        n.rejectAt = start + .95; if (n.litAt == null) n.litAt = start + .2;
        last = Math.max(last, start + 1.1);
      });
      this.found += results.length;
      const pts = [...sources, ...shown.map(r => r.i), ...dark].map(i => this.nodes.get(i).p);
      if (pts.length) this.shot(t - .1, 1.4, pts, { pad: 1.15, blur: 1.1 });
      // "The rows are drugs indicated for X." -> "Drugs indicated for X"
      const said = (ev.description || "Looking it up").replace(/^The rows (are|give the number of) /, "").replace(/\.$/, "");
      const what = said.charAt(0).toUpperCase() + said.slice(1);
      this.say(t, filter ? `${what} · ${results.length} of ${before.size}` : `${what} · ${ev.found} found`);
      this.cursor = last + .25;
    }
    finish(now, result) {
      const t = this.from(now), lit = [...this.nodes.values()].map(n => n.p);
      const lookups = this.steps.length;
      this.say(t, lookups ? `Answered in ${lookups} lookup${lookups === 1 ? "" : "s"}` : "Answered");
      if (lit.length) {
        let c = [0, 0, 0]; lit.forEach(p => { c = add(c, p); }); c = scale(c, .5 / lit.length);
        this.shots.push({ t, dur: 1.8, target: c, dist: 3.5, yaw: this.yaw + .1, pitch: .4, blur: .3, labels: .25 });
      }
      this.end = t + 1.4;
      this.route = this.caption(result);
    }
    caption(result) {
      const anchors = [...this.nodes.values()].filter(n => n.kind === "anchor").map(n => n.label);
      const confirmed = [...this.nodes.values()].filter(n => n.confirmAt != null).length;
      const named = anchors.slice(0, 3), parts = [named.length > 1 ? named.slice(0, -1).join(", ") + " and " + named.at(-1) : named.join("")];
      if (this.steps.length) parts.push(this.found ? `${this.found} found` + (confirmed ? `, ${confirmed} kept` : "")
        : this.passages ? `${this.passages} passages read` : "nothing found");
      return { text: parts.filter(Boolean).join(" → "), meta: `${this.steps.length} lookup${this.steps.length === 1 ? "" : "s"} · ${Number(result?.latency_s ?? 0).toFixed(1)} s` };
    }
  }
  function level(n, t) {
    if (n.kind === "anchor") return t < n.litAt ? 0 : ease((t - n.litAt) / .4);
    if (n.litAt == null || t < n.litAt) return 0;
    let I = ease((t - n.litAt) / .4) * .6;
    if (n.confirmAt != null && t >= n.confirmAt) I = .6 + .4 * ease((t - n.confirmAt) / .4);
    if (n.rejectAt != null && t >= n.rejectAt) I = .6 - .53 * ease((t - n.rejectAt) / 1.1);
    return I;
  }
  const rejected = (n, t) => n.rejectAt != null && t >= n.rejectAt;

  // ---------- the one live view, moved to the question being answered ----------
  const VS = `
attribute vec3 aPos; attribute float aType; attribute float aSeed;
uniform mat4 uVP; uniform vec3 uEye; uniform float uFocus, uBlur, uSize, uTime, uDpr, uGain;
uniform vec3 uCol0, uCol1, uCol2, uCol3;
varying vec3 vCol; varying float vA;
void main() {
  gl_Position = uVP * vec4(aPos, 1.0);
  float d = distance(aPos, uEye);
  float size = max(uSize * uDpr / d, 1.1 * uDpr);
  float coc = min(abs(d - uFocus) * uBlur * uDpr * 5.0, 26.0 * uDpr);
  float s = size + coc;
  gl_PointSize = s;
  float tw = 0.8 + 0.2 * sin(uTime * (0.4 + aSeed * 1.3) + aSeed * 50.0);
  vA = clamp(pow(size / s, 1.15) * tw * uGain, 0.0, 1.0);
  vCol = aType < 0.5 ? uCol0 : aType < 1.5 ? uCol1 : aType < 2.5 ? uCol2 : uCol3;
}`;
  const FS = `
precision mediump float;
varying vec3 vCol; varying float vA;
void main() {
  vec2 c = gl_PointCoord * 2.0 - 1.0; float r2 = dot(c, c);
  if (r2 > 1.0) discard;
  float a = exp(-r2 * 3.2) * vA;
  gl_FragColor = vec4(vCol * a, a);
}`;
  const LOOK = {
    night: { cols: [[1, .86, .7], [1, .7, .6], [1, .8, .5], [.72, .8, 1]], gain: .85, add: true, size: 3.2 },
    atlas: { cols: [[.16, .22, .34], [.42, .2, .15], [.4, .29, .12], [.22, .22, .22]], gain: .8, add: false, size: 3.0 },
  };
  const theme = matchMedia("(prefers-color-scheme: dark)");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let view = null;

  function makeView() {
    const scene = document.createElement("div"); scene.className = "starmap-scene";
    scene.setAttribute("role", "img"); scene.setAttribute("aria-label", "Star map of the knowledge graph");
    const bg = document.createElement("canvas"), glc = document.createElement("canvas"), ov = document.createElement("canvas");
    scene.append(bg, glc, ov);
    const gl = glc.getContext("webgl", { premultipliedAlpha: true, antialias: false, alpha: true });
    if (!gl) return null;
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const prog = gl.createProgram(); gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
    // Phones draw every third point of the background; what a question lights is drawn apart.
    const stride = matchMedia("(pointer: coarse)").matches || innerWidth < 620 ? 3 : 1, count = Math.ceil(MAP.n / stride);
    const data = new Float32Array(count * 5);
    for (let i = 0, j = 0; i < MAP.n; i += stride, j++) { data.set([MAP.pos[i * 3], MAP.pos[i * 3 + 1], MAP.pos[i * 3 + 2], MAP.type[i], hash(i * .013)], j * 5); }
    const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    const v = { scene, bg, glc, ov, gl, prog, buf, count, ctx: ov.getContext("2d"), owner: null, W: 0, H: 0, DPR: 1, raf: 0, user: { yaw: 0, pitch: 0, zoom: 1 } };
    interactions(v);
    return v;
  }

  class Live {
    constructor(stage, status) {
      this.stage = stage; this.status = status; this.trail = new Trail(); this.clock = 0; this.rate = 1; this.last = null;
      this.folded = false; this.ready = null; this.focus = null; this.cam = null;
      stage.classList.add("starmap");
      const fold = document.createElement("div"); fold.className = "starmap-fold";
      const cap = document.createElement("div"); cap.className = "starmap-cap";
      this.routeEl = document.createElement("div"); this.routeEl.className = "starmap-route";
      this.metaEl = document.createElement("div"); this.metaEl.className = "starmap-meta";
      cap.append(this.routeEl, this.metaEl);
      const acts = document.createElement("div"); acts.className = "starmap-acts";
      this.toggle = button("Show the map", () => { this.attach(); this.setFold(!this.folded); });
      acts.append(this.toggle, button("Replay", () => this.replay()));
      fold.append(cap, acts);
      this.tip = document.createElement("div"); this.tip.className = "starmap-tip";
      this.hint = document.createElement("div"); this.hint.className = "starmap-hint"; this.hint.textContent = "Drag to turn · pinch or Ctrl + scroll to zoom · double-click to reset";
      stage.append(fold, this.tip, this.hint);
      this.recorded = [];
      this.attach();
    }
    attach() {
      if (view.owner === this) return;
      if (view.owner) view.owner.detach();
      view.owner = this; this.snapshot?.remove(); this.snapshot = null;
      this.stage.prepend(view.scene); this.layout(); seen.observe(this.stage); kick();
    }
    detach() {
      // A still of the map stays in place of the live view.
      const v = view, still = document.createElement("canvas");
      still.width = v.ov.width; still.height = v.ov.height; still.className = "starmap-still";
      this.draw(this.clock, performance.now() / 1000);
      const c = still.getContext("2d"); c.drawImage(v.bg, 0, 0); c.drawImage(v.glc, 0, 0); c.drawImage(v.ov, 0, 0);
      still.style.width = v.W + "px"; still.style.height = v.H + "px";
      still.style.transform = this.folded ? `scale(${FOLDED / v.H})` : "none";
      this.snapshot = still; this.stage.prepend(still); view.scene.remove(); view.owner = null; seen.unobserve(this.stage);
      // An earlier question's map folds away when the next one is asked.
      if (!this.folded) this.setFold(true);
    }
    layout() {
      const v = view, W = Math.round(this.stage.clientWidth); if (!W) return;
      v.W = W; v.H = W < 620 ? 400 : 460; v.DPR = Math.min(W < 620 ? 1.5 : 2, devicePixelRatio || 1);
      for (const c of [v.glc, v.ov]) { c.width = v.W * v.DPR; c.height = v.H * v.DPR; c.style.width = v.W + "px"; c.style.height = v.H + "px"; }
      v.scene.style.width = v.W + "px"; v.scene.style.height = v.H + "px";
      paintBg(v); this.setFold(this.folded, true);
    }
    setFold(on, instant) {
      this.folded = on; const v = view, s = FOLDED / (v.H || 460);
      if (instant) this.stage.style.transition = "none";
      this.stage.classList.toggle("folded", on);
      this.stage.style.height = (on ? FOLDED : v.H) + "px";
      const target = this.snapshot || v.scene; target.style.transform = on ? `scale(${s})` : "none";
      this.stage.querySelector(".starmap-fold").style.paddingLeft = ((v.W || 600) * s + 16) + "px";
      this.toggle.textContent = on ? "Show the map" : "Fold";
      if (instant) { this.stage.offsetHeight; this.stage.style.transition = ""; }
      kick();
    }
    // Events arrive in real time; each starts no earlier than the end of the last one.
    event(kind, data) {
      this.recorded.push([kind, data]);
      if (kind === "linked") this.trail.linked(data, this.clock);
      else if (kind === "step") this.trail.step(data, this.clock);
      else if (kind === "thinking") this.trail.thinking(this.clock);
      else if (kind === "writing") this.trail.writing(this.clock);
      kick();
    }
    // The answer is shown once the trail has caught up; a backlog is played faster, never held long.
    finish(result) {
      this.result = result;
      if (!this.trail.nodes.size) { this.close(); return Promise.resolve(); }
      this.trail.finish(this.clock, result);
      this.routeEl.textContent = this.trail.route.text; this.metaEl.textContent = this.trail.route.meta;
      if (reduced.matches) this.clock = this.trail.end;
      const backlog = this.trail.end - 1 - this.clock;
      this.rate = backlog > 2.6 ? Math.min(6, backlog / 2.6) : 1;
      kick();
      // Also on a timer: a hidden tab draws nothing, and the answer must not wait for it.
      return new Promise(resolve => {
        this.ready = resolve;
        setTimeout(() => { if (this.ready === resolve) { this.ready = null; resolve(); } }, (backlog / this.rate + 2) * 1000);
      });
    }
    close() { if (view.owner === this) { view.scene.remove(); view.owner = null; } this.stage.remove(); }
    replay() {
      this.attach(); const events = this.recorded; this.recorded = [];
      this.trail = new Trail(); this.clock = 0; this.rate = 1; this.last = null; this.held = false;
      Object.assign(view.user, { yaw: 0, pitch: 0, zoom: 1 });
      this.setFold(false);
      // The recorded events again, at the pace they first came in.
      let delay = 0;
      for (const [kind, data] of events) { delay += .5; setTimeout(() => this.event(kind, data), delay * 1000); }
      setTimeout(() => this.finish(this.result), (delay + .6) * 1000);
    }
    link(root) {
      root.querySelectorAll(".chips li").forEach(chip => {
        chip.addEventListener("mouseenter", () => { if (view.owner !== this || this.folded) return; this.focus = chip.textContent.trim(); kick(); });
        chip.addEventListener("mouseleave", () => { this.focus = null; kick(); });
      });
      this.chips = root;
    }
    tick(now) {
      const dt = this.last == null ? 0 : Math.min(.1, (now - this.last) / 1000); this.last = now;
      this.clock += dt * this.rate;
      const trail = this.trail;
      if (trail.end != null && this.ready && this.clock >= trail.end - 1) { const r = this.ready; this.ready = null; r(); }
      if (trail.end != null && this.clock >= trail.end - .9) this.rate = 1;
      if (trail.end != null && this.clock >= trail.end + 1.2 && !this.folded && !this.held) { this.held = true; this.setFold(true); }
      this.draw(this.clock, now / 1000);
      const said = trail.said.filter(([t]) => t <= this.clock).pop();
      if (said && this.status && this.status.textContent !== said[1]) { this.status.textContent = said[1]; view.scene.setAttribute("aria-label", "Star map: " + said[1]); }
      this.hint.classList.toggle("show", trail.end != null && this.clock >= trail.end && !this.folded);
      return !(this.folded && trail.end != null && this.clock >= trail.end);
    }
    camera(t, a) {
      const S = this.trail.shots; let i = 0; while (i + 1 < S.length && S[i + 1].t <= t) i++;
      const cur = S[i], prev = S[Math.max(0, i - 1)], u = i === 0 ? 1 : smooth((t - cur.t) / cur.dur), U = view.user;
      const c = { target: [0, 1, 2].map(k => lerp(prev.target[k], cur.target[k], u)), dist: Math.exp(lerp(Math.log(prev.dist), Math.log(cur.dist), u)),
                  yaw: lerp(prev.yaw, cur.yaw, u), pitch: lerp(prev.pitch, cur.pitch, u), blur: lerp(prev.blur, cur.blur, u), labels: lerp(prev.labels, cur.labels, u) };
      c.yaw += a * .018 + U.yaw; c.pitch = clamp(c.pitch + U.pitch, -1.1, 1.45); c.dist *= U.zoom;
      const cp = Math.cos(c.pitch), v = view;
      c.eye = add(c.target, scale([cp * Math.sin(c.yaw), Math.sin(c.pitch), cp * Math.cos(c.yaw)], c.dist));
      c.vp = mul(perspective(FOV, v.W / v.H, .02, 60), lookAt(c.eye, c.target, [0, 1, 0]));
      return c;
    }
    draw(t, a) {
      const v = view; if (!v.W) return;
      const cam = this.cam = this.camera(t, a), night = theme.matches;
      dust(v, cam, a, night);
      const ctx = v.ctx; ctx.setTransform(v.DPR, 0, 0, v.DPR, 0, 0); ctx.clearRect(0, 0, v.W, v.H);
      const project = p => {
        const m = cam.vp, x = m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12], y = m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13], w = m[3] * p[0] + m[7] * p[1] + m[11] * p[2] + m[15];
        return w < .05 ? null : [(x / w * .5 + .5) * v.W, (1 - (y / w * .5 + .5)) * v.H, w];
      };
      const persp = n => clamp(1.6 / Math.hypot(...sub(n.p, cam.eye)), .45, 1.5);
      graticule(ctx, project, night);
      nebulaLabels(ctx, project, cam, night);
      const nodes = [...this.trail.nodes.values()], screen = new Map(nodes.map(n => [n, project(n.p)]));
      const pathOf = e => { const out = []; for (const p of e.pts3) { const s = project(p); if (s) out.push(s); } return out.length > 1 ? makePath(out) : null; };
      if (night) {
        ctx.globalCompositeOperation = "lighter"; ctx.lineCap = "round";
        for (const n of nodes) { const s = screen.get(n), I = level(n, t); if (s && I > 0) glow(ctx, s[0], s[1], (n.kind === "anchor" ? 170 : 60) * persp(n), "255,160,80", "255,150,70", (n.kind === "anchor" ? .06 : .025) * I); }
        for (const e of this.trail.edges) nightEdge(ctx, e, t, pathOf);
        for (const n of nodes) { const s = screen.get(n); if (s) (n.kind === "anchor" ? nightAnchor : nightNode)(ctx, n, s, t, a, persp(n)); }
        ctx.globalCompositeOperation = "source-over";
      } else {
        ctx.lineCap = "round"; ctx.lineJoin = "round";
        for (const e of this.trail.edges) penLine(ctx, e, t, pathOf);
        for (const n of nodes) { const s = screen.get(n); if (s) atlasNode(ctx, n, s, t, persp(n)); }
      }
      if (this.focus) for (const n of nodes) {
        const s = screen.get(n); if (!s || n.label !== this.focus) continue;
        ctx.strokeStyle = night ? "rgba(255,214,165,.9)" : "rgba(168,67,47,.85)"; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(s[0], s[1], 9 + 3 * Math.sin(a * 5), 0, 7); ctx.stroke();
      }
      labels(ctx, this, nodes, screen, t, night, persp, cam, project);
      this.screen = screen;
    }
  }

  function button(text, onClick) { const b = document.createElement("button"); b.type = "button"; b.className = "link"; b.textContent = text; b.addEventListener("click", onClick); return b; }

  function paintBg(v) {
    const night = theme.matches, g = v.bg.getContext("2d");
    v.bg.width = v.W * v.DPR; v.bg.height = v.H * v.DPR; v.bg.style.width = v.W + "px"; v.bg.style.height = v.H + "px";
    let seed = 97; const R = () => (seed = (seed * 16807) % 2147483647) / 2147483647, big = Math.max(v.W, v.H);
    g.setTransform(v.DPR, 0, 0, v.DPR, 0, 0);
    g.fillStyle = night ? "#050506" : "#f1ebe0"; g.fillRect(0, 0, v.W, v.H);
    if (night) {
      const c = g.createRadialGradient(v.W / 2, v.H / 2, 0, v.W / 2, v.H / 2, big * .75); c.addColorStop(0, "rgba(24,19,15,.7)"); c.addColorStop(1, "rgba(0,0,0,0)");
      g.fillStyle = c; g.fillRect(0, 0, v.W, v.H);
    } else {
      for (let i = 0; i < 24; i++) { const x = R() * v.W, y = R() * v.H, r = 80 + R() * 220, m = g.createRadialGradient(x, y, 0, x, y, r); m.addColorStop(0, `rgba(170,150,118,${.015 + R() * .02})`); m.addColorStop(1, "rgba(170,150,118,0)"); g.fillStyle = m; g.fillRect(0, 0, v.W, v.H); }
      for (let i = 0; i < v.W * v.H / 420; i++) { const x = R() * v.W, y = R() * v.H, l = 3 + R() * 9, a = R() * Math.PI; g.strokeStyle = `rgba(120,100,70,${.03 + R() * .04})`; g.lineWidth = .5; g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l); g.stroke(); }
    }
    const img = g.getImageData(0, 0, v.bg.width, v.bg.height), d = img.data;
    for (let i = 0; i < d.length; i += 4) { const n = (R() - .5) * 7; d[i] += n; d[i + 1] += n; d[i + 2] += n; }
    g.putImageData(img, 0, 0);
  }
  function dust(v, cam, a, night) {
    const gl = v.gl, L = LOOK[night ? "night" : "atlas"], p = v.prog;
    gl.viewport(0, 0, v.glc.width, v.glc.height); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(p); gl.bindBuffer(gl.ARRAY_BUFFER, v.buf);
    const attr = (name, size, offset) => { const l = gl.getAttribLocation(p, name); gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, size, gl.FLOAT, false, 20, offset); };
    attr("aPos", 3, 0); attr("aType", 1, 12); attr("aSeed", 1, 16);
    const u = n => gl.getUniformLocation(p, n);
    gl.uniformMatrix4fv(u("uVP"), false, new Float32Array(cam.vp)); gl.uniform3fv(u("uEye"), cam.eye);
    gl.uniform1f(u("uFocus"), cam.dist); gl.uniform1f(u("uBlur"), cam.blur); gl.uniform1f(u("uSize"), L.size);
    gl.uniform1f(u("uTime"), a); gl.uniform1f(u("uDpr"), v.DPR); gl.uniform1f(u("uGain"), L.gain);
    L.cols.forEach((c, i) => gl.uniform3fv(u("uCol" + i), c));
    gl.enable(gl.BLEND); if (L.add) gl.blendFunc(gl.ONE, gl.ONE); else gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.drawArrays(gl.POINTS, 0, v.count);
  }
  function glow(ctx, x, y, r, c0, c1, a) {
    if (a <= .002 || r <= .1) return;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, `rgba(${c0},${Math.min(1, a)})`); g.addColorStop(.3, `rgba(${c1},${Math.min(1, a) * .45})`); g.addColorStop(1, `rgba(${c1},0)`);
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
  }
  function trace(ctx, P, f0, f1) {
    const a = at(P, f0), L0 = f0 * P.len, L1 = f1 * P.len;
    ctx.beginPath(); ctx.moveTo(a[0], a[1]);
    for (let i = 0; i < P.pts.length; i++) if (P.cum[i] > L0 && P.cum[i] < L1) ctx.lineTo(P.pts[i][0], P.pts[i][1]);
    const b = at(P, f1); ctx.lineTo(b[0], b[1]);
  }
  function graticule(ctx, project, night) {
    const R = 4.2; ctx.lineWidth = .6; ctx.strokeStyle = night ? "rgba(255,210,160,.045)" : "rgba(70,58,44,.11)";
    const line = pts => { let open = false; ctx.beginPath(); for (const p of pts) { const s = project(p); if (!s) { open = false; continue; } open ? ctx.lineTo(s[0], s[1]) : ctx.moveTo(s[0], s[1]); open = true; } ctx.stroke(); };
    for (const lat of [-60, -30, 0, 30, 60]) { const pts = [], la = lat * Math.PI / 180; for (let k = 0; k <= 96; k++) { const lo = k / 96 * Math.PI * 2; pts.push([R * Math.cos(la) * Math.cos(lo), R * Math.sin(la), R * Math.cos(la) * Math.sin(lo)]); } line(pts); }
    for (let m = 0; m < 12; m++) { const pts = [], lo = m * Math.PI / 6; for (let k = 0; k <= 64; k++) { const la = -Math.PI / 2 + k / 64 * Math.PI; pts.push([R * Math.cos(la) * Math.cos(lo), R * Math.sin(la), R * Math.cos(la) * Math.sin(lo)]); } line(pts); }
  }
  function nebulaLabels(ctx, project, cam, night) {
    const k = 1 - cam.labels * 1.6; if (k <= 0) return;
    ctx.save(); ctx.textAlign = "center";
    for (const nb of MAP.nebulae) {
      const s = project(nb.c); if (!s) continue;
      ctx.font = night ? `500 11px ${SANS}` : `italic 15px ${SERIF}`;
      ctx.fillStyle = night ? `rgba(255,226,196,${.55 * k})` : `rgba(48,42,36,${.75 * k})`;
      ctx.fillText(night ? nb.name.toUpperCase() : nb.name, s[0], s[1] - 4);
      ctx.font = night ? `300 10.5px ${SANS}` : `13px ${SERIF}`;
      ctx.fillStyle = night ? `rgba(255,200,150,${.4 * k})` : `rgba(168,67,47,${.7 * k})`;
      ctx.fillText(nb.total.toLocaleString("en"), s[0], s[1] + 12);
    }
    ctx.restore();
  }
  function comet(ctx, P, head, fade, tailPx, width) {
    const tail = tailPx / P.len;
    for (let s = 0; s < 7; s++) {
      const f0 = Math.max(0, head - tail * (1 - s / 7)), f1 = Math.max(0, head - tail * (1 - (s + 1) / 7));
      if (f1 <= f0) continue;
      ctx.strokeStyle = `rgba(255,214,165,${(.05 + .1 * s) * fade})`; ctx.lineWidth = width * (.5 + s * .12); trace(ctx, P, f0, f1); ctx.stroke();
    }
    const [x, y] = at(P, head); glow(ctx, x, y, 10, "255,250,236", "255,196,128", .95 * fade);
  }
  function nightEdge(ctx, e, t, pathOf) {
    const p = clamp((t - e.start) / e.dur); if (p <= 0) return;
    const P = pathOf(e); if (!P) return;
    let head = ease(p), fade = 1;
    // A light that never arrives slows, thins and goes out before the node.
    if (e.fizzle) { head = .6 * ease(p / .9); fade = 1 - smooth((p - .45) / .5); }
    const arrived = !e.fizzle && p >= 1, after = arrived ? t - (e.start + e.dur) : 0;
    ctx.strokeStyle = `rgba(255,206,150,${e.fizzle ? .05 * fade : .1 + (arrived ? .16 * Math.exp(-after / .7) : 0)})`; ctx.lineWidth = .8; trace(ctx, P, 0, head); ctx.stroke();
    if (!arrived && fade > 0) comet(ctx, P, head, fade, 150, 1.6);
  }
  function nightAnchor(ctx, n, s, t, a, z) {
    if (t < n.litAt) return;
    const k = t - n.litAt, I = ease(k / .45), br = .94 + .06 * Math.sin(a * 1.7 + n.seed), [x, y] = s;
    const flare = k < .7 ? 1 + 1.4 * (1 - k / .7) * (k < .35 ? (noise(t * 30 + n.seed) > .3 ? 1 : .55) : 1) : 1;
    const read = n.readAt != null && t >= n.readAt ? Math.exp(-(t - n.readAt) / .9) : 0;
    glow(ctx, x, y, (120 + 60 * read) * z, "255,188,120", "255,140,60", (.2 + .15 * read) * I * br);
    glow(ctx, x, y, 34 * z, "255,232,198", "255,182,110", .6 * I * br * Math.min(flare, 1.5));
    glow(ctx, x, y, 9 * z * Math.min(flare, 1.6), "255,255,250", "255,238,214", I);
    ctx.save(); ctx.translate(x, y); ctx.rotate(a * .03 + n.seed);
    for (let r = 0; r < 8; r++) {
      const len = (24 + 30 * noise(r * 3.1 + a * .5)) * I * z * Math.min(flare, 1.8), ang = r * Math.PI / 4 + .2 * Math.sin(a * .3 + r);
      const gx = Math.cos(ang) * len, gy = Math.sin(ang) * len, g = ctx.createLinearGradient(0, 0, gx, gy);
      g.addColorStop(0, `rgba(255,230,190,${.11 * I})`); g.addColorStop(1, "rgba(255,200,140,0)");
      ctx.strokeStyle = g; ctx.lineWidth = .7; ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(gx, gy); ctx.stroke();
    }
    ctx.restore();
    if (k > .5) for (let e = 0; e < 10; e++) {
      const period = 2.6 + hash(e * 3.3 + n.seed) * 1.6, life = ((a + hash(n.seed * 10 + e) * period) % period) / period;
      glow(ctx, x + (hash(e * 7.7 + n.seed) - .5) * 16 * z + Math.sin(a * 1.4 + e) * 7 * life, y - (10 + life * (55 + 30 * hash(e + n.seed))) * z, 3, "255,226,170", "255,140,60", Math.sin(Math.PI * life) * .5 * ease((k - .5) / .8));
    }
  }
  function nightNode(ctx, n, s, t, a, z) {
    if (n.litAt == null || t < n.litAt) return;
    const I = level(n, t), k = t - n.litAt, flare = k < .35 ? 1 + .9 * (1 - k / .35) : 1, [x, y] = s, big = n.confirmAt != null && t >= n.confirmAt;
    if (rejected(n, t)) { ctx.strokeStyle = `rgba(255,220,180,${.3 * ease((t - n.rejectAt) / .8)})`; ctx.lineWidth = .8; ctx.beginPath(); ctx.arc(x, y, 4.5 * z, 0, 7); ctx.stroke(); }
    glow(ctx, x, y, (big ? 32 : 24) * z, "255,224,180", "255,166,86", .32 * I * flare);
    glow(ctx, x, y, (big ? 5.5 : 4.5) * z, "255,253,244", "255,228,186", Math.min(1, I * flare));
  }
  function penLine(ctx, e, t, pathOf) {
    const p = clamp((t - e.start) / e.dur); if (p <= 0) return;
    const P = pathOf(e); if (!P) return;
    const cut = e.fizzle ? .58 : 1, head = Math.min(ease(p), cut), L = head * P.len;
    for (const pass of [0, 1]) {
      ctx.beginPath(); let started = false;
      for (let i = 0; i < P.pts.length && P.cum[i] <= L; i++) {
        const s = P.cum[i] / P.len, a = P.pts[Math.max(0, i - 1)], b = P.pts[Math.min(P.pts.length - 1, i + 1)], ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
        const j = (noise(s * 9 + e.seed + pass * 13) - .5) * (pass ? 1.8 : .9), x = P.pts[i][0] - Math.sin(ang) * j, y = P.pts[i][1] + Math.cos(ang) * j;
        started ? ctx.lineTo(x, y) : (ctx.moveTo(x, y), started = true);
      }
      const [hx, hy] = at(P, head); ctx.lineTo(hx, hy);
      ctx.setLineDash(e.fizzle ? [3, 4] : []);
      ctx.strokeStyle = `rgba(${e.fizzle ? "96,90,82" : "42,38,34"},${pass ? (e.fizzle ? .12 : .2) : (e.fizzle ? .32 : .66)})`;
      ctx.lineWidth = pass ? .6 : 1; ctx.stroke();
    }
    ctx.setLineDash([]);
  }
  function wash(ctx, x, y, r, seed, tint, a) {
    if (a <= 0 || r <= 0) return;
    for (let k = 0; k < 2; k++) {
      const ox = (hash(seed + k) - .5) * r * .35, oy = (hash(seed + k + 9) - .5) * r * .35;
      const g = ctx.createRadialGradient(x + ox, y + oy, r * .1, x + ox, y + oy, r * (1.05 - k * .2));
      g.addColorStop(0, `rgba(${tint},${a * (k ? .6 : 1)})`); g.addColorStop(.75, `rgba(${tint},${a * .55})`); g.addColorStop(1, `rgba(${tint},0)`);
      ctx.fillStyle = g; ctx.beginPath();
      for (let i = 0; i <= 24; i++) { const ang = i / 24 * Math.PI * 2, rr = r * (1 + .12 * Math.sin(3 * ang + seed + k) + .06 * Math.sin(7 * ang + seed)); const px = x + ox + Math.cos(ang) * rr, py = y + oy + Math.sin(ang) * rr; i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); }
      ctx.closePath(); ctx.fill();
    }
  }
  // An open brush circle drawn in one movement.
  function enso(ctx, x, y, r, seed, k) {
    if (k <= 0) return;
    const a0 = -2.3 + hash(seed) * .6, n = Math.max(2, Math.ceil(60 * k)), outer = [], inner = [];
    for (let i = 0; i <= n; i++) {
      const u = i / n, ang = a0 + 5.95 * k * u, rr = r * (1 + .05 * Math.sin(3 * ang + seed)), w = .5 + 1.9 * Math.pow(Math.sin(Math.PI * Math.min(1, u * k / .98)), .7);
      outer.push([x + Math.cos(ang) * (rr + w / 2), y + Math.sin(ang) * (rr + w / 2)]); inner.push([x + Math.cos(ang) * (rr - w / 2), y + Math.sin(ang) * (rr - w / 2)]);
    }
    ctx.beginPath(); outer.forEach(([px, py], i) => i ? ctx.lineTo(px, py) : ctx.moveTo(px, py));
    for (let i = inner.length - 1; i >= 0; i--) ctx.lineTo(inner[i][0], inner[i][1]);
    ctx.closePath(); ctx.fillStyle = "rgba(36,32,28,.82)"; ctx.fill();
  }
  function atlasNode(ctx, n, s, t, z) {
    const [x, y] = s;
    if (n.kind === "anchor") {
      if (t >= n.litAt + .45) wash(ctx, x + 2, y + 1.5, 17 * z * ease((t - n.litAt - .45) / .9), n.seed, TINT[n.tint] || TINT.Gene, .24);
      enso(ctx, x, y, 14 * z, n.seed, ease((t - n.litAt) / .7));
      return;
    }
    if (n.litAt == null || t < n.litAt) return;
    const k = ease((t - n.litAt) / .35), off = rejected(n, t);
    if (n.confirmAt != null && t >= n.confirmAt) wash(ctx, x, y, 8.5 * z * ease((t - n.confirmAt) / .6), n.seed, TINT.Drug, .26);
    ctx.beginPath(); ctx.arc(x, y, 4 * z, -1.9, -1.9 + (Math.PI * 2 + .35) * k);
    ctx.setLineDash(off ? [2, 2.5] : []); ctx.strokeStyle = `rgba(42,38,34,${off ? .3 : .75})`; ctx.lineWidth = .9; ctx.stroke(); ctx.setLineDash([]);
  }
  // Names right of their point, else left, above or below; one that fits nowhere waits for hover.
  function labels(ctx, live, nodes, screen, t, night, persp, cam, project) {
    const W = view.W, H = view.H, boxes = [];
    const fits = b => b[0] > 4 && b[2] < W - 4 && b[1] > 4 && b[3] < H - 4 && !boxes.some(o => b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]);
    ctx.save(); ctx.textBaseline = "alphabetic"; ctx.textAlign = "left"; ctx.lineJoin = "round";
    for (const n of nodes) {
      if (n.kind !== "anchor") continue;
      const s = screen.get(n), k = ease((t - n.litAt - .2) / .7); if (!s || k <= 0) continue;
      ctx.font = `${night ? 500 : 600} 22px ${SERIF}`;
      const w = ctx.measureText(n.label).width, z = persp(n), x = clamp(s[0] - w / 2, 6, W - w - 6);
      const below = s[1] + 22 + 16 * z, above = s[1] - 18 - 16 * z;
      const y = fits([x - 4, below - 22, x + w + 4, below + 20]) || !fits([x - 4, above - 22, x + w + 4, above + 20]) ? below : above;
      boxes.push([x - 4, y - 22, x + w + 4, y + 20]);
      ctx.strokeStyle = night ? "rgba(4,4,5,.75)" : "rgba(241,235,224,.85)"; ctx.lineWidth = 5; ctx.strokeText(n.label, x, y);
      ctx.fillStyle = night ? `rgba(255,240,220,${k})` : `rgba(30,27,23,${.92 * k})`; ctx.fillText(n.label, x, y);
      ctx.font = `600 9.5px ${SANS}`; const tw = ctx.measureText(n.tag).width;
      ctx.fillStyle = night ? `rgba(255,190,120,${.7 * k})` : `rgba(${TINT[n.tint] || TINT.Gene},${.9 * k})`; ctx.fillText(n.tag, x + (w - tw) / 2, y + 16);
    }
    const vis = Math.max(cam.labels, live.focus ? 1 : 0);
    if (vis > .05) {
      ctx.font = night ? `${W < 620 ? 11.5 : 12.5}px ${SANS}` : `${W < 620 ? 14 : 15}px ${SERIF}`;
      const items = nodes.filter(n => n.kind !== "anchor" && n.label && n.litAt != null && t >= n.litAt && screen.get(n))
        .sort((p, q) => (q.label === live.focus) - (p.label === live.focus) || (q.confirmAt != null) - (p.confirmAt != null) || p.litAt - q.litAt);
      for (const n of items) {
        const s = screen.get(n), w = ctx.measureText(n.label).width, off = rejected(n, t), on = n.confirmAt != null && t >= n.confirmAt;
        const spot = [[s[0] + 10, s[1] + 4], [s[0] - 10 - w, s[1] + 4], [s[0] - w / 2, s[1] - 10], [s[0] - w / 2, s[1] + 18]].find(([x, y]) => fits([x - 2, y - 12, x + w + 2, y + 4]));
        if (!spot) continue;
        const [x, y] = spot, k = ease((t - n.litAt) / .6) * Math.min(1, vis * 1.2); boxes.push([x - 2, y - 12, x + w + 2, y + 4]);
        ctx.strokeStyle = night ? `rgba(4,4,5,${.6 * k})` : `rgba(241,235,224,${.9 * k})`; ctx.lineWidth = 4; ctx.strokeText(n.label, x, y);
        ctx.fillStyle = night ? `rgba(255,238,215,${(off ? .25 : on ? .95 : .75) * k})` : `rgba(${off ? "120,112,100" : "30,27,23"},${(off ? .6 : .92) * k})`;
        ctx.fillText(n.label, x, y);
        if (off && !night) { const u = ease((t - n.rejectAt) / .5); ctx.strokeStyle = "rgba(168,67,47,.65)"; ctx.lineWidth = 1.1; ctx.beginPath(); ctx.moveTo(x - 2, y - 4); ctx.lineTo(x + w * u + 2, y - 4); ctx.stroke(); }
      }
      areaLabels(ctx, nodes, t, night, cam, project, fits, boxes);
    }
    ctx.restore();
  }
  // The body regions where something is lit, named on their nebula's rim.
  function areaLabels(ctx, nodes, t, night, cam, project, fits, boxes) {
    if (cam.dist > 5.2) return;
    const k0 = smooth((5.2 - cam.dist) / 1.2), lit = new Map();
    for (const n of nodes) if (n.kind !== "anchor" && level(n, t) > .3 && MAP.region[n.i]) { const key = MAP.type[n.i] * 100 + MAP.region[n.i]; lit.set(key, (lit.get(key) || 0) + 1); }
    ctx.font = night ? `500 9.5px ${SANS}` : `italic 14px ${SERIF}`;
    const shown = MAP.areas.filter(ar => ar.t !== 0 && lit.has(ar.t * 100 + ar.r)).sort((a, b) => lit.get(b.t * 100 + b.r) - lit.get(a.t * 100 + a.r));
    for (const ar of shown) {
      const nb = MAP.nebulae[ar.t], dx = ar.c[0] - nb.c[0], dz = ar.c[2] - nb.c[2], L = Math.hypot(dx, dz) || 1;
      const s = project([nb.c[0] + dx / L * nb.rim, nb.c[1], nb.c[2] + dz / L * nb.rim]), sc = project(nb.c); if (!s || !sc) continue;
      const text = night ? ar.name.toUpperCase() : ar.name, w = ctx.measureText(text).width;
      const x = s[0] > sc[0] + 12 ? s[0] : s[0] < sc[0] - 12 ? s[0] - w : s[0] - w / 2, y = s[1] + 3, box = [x - 3, y - 10, x + w + 3, y + 3];
      if (!fits(box)) continue; boxes.push(box);
      ctx.fillStyle = night ? `rgba(255,206,150,${.62 * k0})` : `rgba(168,67,47,${.72 * k0})`; ctx.fillText(text, x, y);
    }
  }

  // ---------- drawing loop and pointer ----------
  let raf = 0, visible = true;
  function kick() { if (!raf) raf = requestAnimationFrame(frame); }
  function frame(now) {
    raf = 0;
    const live = view?.owner; if (!live || !visible) return;
    if (live.tick(now)) raf = requestAnimationFrame(frame);
  }
  function interactions(v) {
    const ov = v.ov, pointers = new Map(); let pinch0 = 0, zoom0 = 1;
    ov.addEventListener("pointerdown", e => {
      ov.setPointerCapture(e.pointerId); pointers.set(e.pointerId, [e.clientX, e.clientY]);
      if (pointers.size === 2) { const [a, b] = [...pointers.values()]; pinch0 = Math.hypot(a[0] - b[0], a[1] - b[1]); zoom0 = v.user.zoom; }
      ov.classList.add("dragging"); v.owner?.hint.classList.add("gone");
    });
    ov.addEventListener("pointermove", e => {
      if (pointers.has(e.pointerId)) {
        const prev = pointers.get(e.pointerId); pointers.set(e.pointerId, [e.clientX, e.clientY]);
        if (pointers.size === 1) { v.user.yaw -= (e.clientX - prev[0]) * .005; v.user.pitch = clamp(v.user.pitch + (e.clientY - prev[1]) * .004, -.9, .9); }
        else if (pointers.size === 2) { const [a, b] = [...pointers.values()]; v.user.zoom = clamp(zoom0 * pinch0 / Math.max(20, Math.hypot(a[0] - b[0], a[1] - b[1])), .3, 3); }
        kick(); return;
      }
      hover(v, e);
    });
    ["pointerup", "pointercancel"].forEach(t => ov.addEventListener(t, e => { pointers.delete(e.pointerId); if (!pointers.size) ov.classList.remove("dragging"); }));
    ov.addEventListener("pointerleave", () => { const live = v.owner; if (live) { live.tip.classList.remove("show"); mark(live, null); } });
    // A plain scroll still scrolls the page; Ctrl or a pinch zooms.
    ov.addEventListener("wheel", e => { if (!e.ctrlKey && !e.metaKey) return; e.preventDefault(); v.user.zoom = clamp(v.user.zoom * Math.exp(e.deltaY * .0015), .3, 3); kick(); }, { passive: false });
    ov.addEventListener("dblclick", () => { Object.assign(v.user, { yaw: 0, pitch: 0, zoom: 1 }); kick(); });
  }
  function hover(v, e) {
    const live = v.owner; if (!live?.screen) return;
    const r = v.ov.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    let best = null, bd = 10;
    for (const [n, s] of live.screen) { if (!s || !n.label || n.litAt == null || live.clock < n.litAt) continue; const d = Math.hypot(s[0] - x, s[1] - y); if (d < bd) { bd = d; best = n; } }
    if (best) {
      const s = live.screen.get(best);
      live.tip.textContent = best.label + (rejected(best, live.clock) ? " · not found by the last lookup" : "");
      live.tip.style.left = s[0] + "px"; live.tip.style.top = s[1] + "px"; live.tip.classList.add("show");
    } else live.tip.classList.remove("show");
    mark(live, best && best.label);
  }
  function mark(live, name) { live.chips?.querySelectorAll(".chips li").forEach(c => c.classList.toggle("lit", !!name && c.textContent.trim() === name)); }
  // Nothing is drawn while the live stage is scrolled out of sight.
  const seen = new IntersectionObserver(es => { for (const e of es) if (view && e.target === view.owner?.stage) { visible = e.isIntersecting; if (visible) kick(); } });
  theme.addEventListener("change", () => { if (view?.owner) { view.owner.layout(); kick(); } });
  addEventListener("resize", () => { if (view?.owner) { view.owner.layout(); kick(); } });

  // A live view in this stage, or null when the map or WebGL is unavailable.
  async function start(stage, status) {
    const map = await load(); if (!map) return null;
    if (!view) view = makeView(); if (!view) return null;
    return new Live(stage, status);
  }
  return { start, load };
})();
