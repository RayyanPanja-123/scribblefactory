// World Items drawn as cards: library objects with look "card" (pipeline schemas/library.py WorldObject). A 2D ink
// drawing on a plane, like the car: a built-in drawer (DRAWERS) or the item's own shapes (creatures.js drawShapes).
// Story items (@item: shot.items) are placed every frame by main.js and turn to face the camera; set items are built
// into the set group by world.js and face +z. Both go through updateCard every frame.
// Cost: each layer of a card is drawn once per (item, colours, state, layer, boil step mod BOIL_CYCLE) and kept in an
// LRU cache of at most CACHE_MB, so a long part redraws only on a miss. rotate, sway, bob, drift, pulse and blink move,
// scale or fade the mesh (no redraw); flow scrolls a flow layer's texture. Every value is a pure function of the frame,
// so any chunk renders the same picture as a full run.
import * as THREE from "three";
import { Pen, ellPts } from "./borrowed.js";
import { drawShapes } from "./creatures.js";
import { hash, rng } from "./rng.js";
import { jitter, wobble } from "./stickman.js";
import { INK } from "./style.js";

export const BOIL_FRAMES = 4;   // marker jitter changes every 4 frames (main.js: the cast's boil)
export const BOIL_CYCLE = 4;    // item drawings repeat their boil every BOIL_CYCLE steps: 4 cached drawings per state
export const CACHE_MB = 128;    // texture cache cap per render worker (canvas bytes; the GPU copy is the same size)
// draw order per layer: sky and back before the fog bands (0.5) and the back rain (0.7), mid / stage with the cast (1)
export const LAYER_ORDER = { sky: 0.2, back: 0.4, mid: 1, stage: 1 };
export const LAYER_STEP = 0.001; // a card's layers draw in order; a rider inside one draws between its first and second
export const RIDER_ORDER = 1 + LAYER_STEP / 2;
// open / close: the state flips over TWEEN frames centred on its switch frame, drawn in TWEEN_STEPS steps (cached)
export const TWEEN = 8, TWEEN_STEPS = 4;
const TAU = Math.PI * 2, rad = (d) => (d * Math.PI) / 180;

/** an item's animation at time t (s): { dx, dy (world units), rot (radians), scale, opacity, flow (0..1 scroll) }.
 *  anims: the item's ItemAnim list; only those whose `when` holds the state play. ph: the instance's seeded phase. */
export function animAt(anims, state, t, ph = 0) {
  const o = { dx: 0, dy: 0, rot: 0, scale: 1, opacity: 1, flow: 0 };
  (anims || []).forEach((a, i) => {
    if (a.when && !a.when.includes(state)) return;
    const amp = a.amp ?? 1, hz = a.hz ?? 0.2, s = Math.sin(TAU * hz * t + ph + 1.7 * i);
    if (a.kind === "rotate") o.rot += rad((amp * t) % 360);
    else if (a.kind === "sway") o.rot += rad(amp) * s;
    else if (a.kind === "bob") o.dy += amp * s;
    else if (a.kind === "drift") o.dx += amp * s;
    else if (a.kind === "pulse") o.scale *= 1 + amp * s;
    else if (a.kind === "blink") o.opacity *= 1 - amp * (0.5 + 0.5 * s);
    else if (a.kind === "flow") o.flow = (o.flow + hz * t) % 1;
  });
  return o;
}

// ---- drawers: (p: Pen, g, W, H, o: { main, accent, state, boil: rng, b: boil step 0..BOIL_CYCLE-1, seed }) ----
const shadeOf = (hex, k) => { const c = new THREE.Color(hex).multiplyScalar(k); return `#${c.getHexString()}`; };
const lw = (H, px) => (px * H) / 512; // line widths are given for a 512 px tall card

/** ringed planet: ring back half, a banded surface that scrolls (flow) inside the disc, then shading, the ink outline
 *  and the ring's front half */
const RING = { rx: 0.48, ry: 0.11, tilt: -14 }, DISC = 0.36; // ring radii share of W / H; disc radius share of H
function ring(p, g, W, H, o, back) {
  const pts = ellPts(W / 2, H / 2, RING.rx * W, RING.ry * H, back ? 180 : 0, back ? 360 : 180, RING.tilt, 40);
  p.stroke(jitter(pts, o.boil, 2), lw(H, 34));
  p.stroke(jitter(pts, o.boil, 2), lw(H, 22), o.accent);
  p.stroke(pts, lw(H, 4), shadeOf(o.accent, 0.75));
}
function planetBands(p, g, W, H, o) {
  const R = rng(o.seed, "bands");
  g.fillStyle = o.main; g.fillRect(0, 0, W, H);
  const cols = [shadeOf(o.main, 0.82), shadeOf(o.main, 1.15), o.accent];
  for (let k = 0; k < 7; k++) { // wavy bands: whole sine periods across W, so the tile wraps without a seam
    const y = H * (0.18 + 0.66 * R()), h = H * (0.02 + 0.05 * R()), amp = H * 0.02 * R(), per = 1 + Math.floor(R() * 3);
    g.fillStyle = cols[k % cols.length]; g.globalAlpha = k % 3 === 2 ? 0.45 : 0.8;
    g.beginPath();
    for (let x = 0; x <= W; x += 8) g.lineTo(x, y + amp * Math.sin((TAU * per * x) / W));
    for (let x = W; x >= 0; x -= 8) g.lineTo(x, y + h + amp * Math.sin((TAU * per * x) / W + 1));
    g.fill();
  }
  g.globalAlpha = 1;
  for (let k = 0; k < 6; k++) { // spots, drawn again one tile left / right so they wrap
    const x = W * R(), y = H * (0.25 + 0.5 * R()), r = H * (0.02 + 0.03 * R());
    for (const dx of [-W, 0, W]) p.poly(ellPts(x + dx, y, r * 1.6, r, 0, 360, 0, 20), shadeOf(o.main, 0.7), lw(H, 3));
  }
}
const discPath = (g, W, H) => g.arc(W / 2, H / 2, DISC * H, 0, TAU);
function planetFront(p, g, W, H, o) {
  const cx = W / 2, cy = H / 2, r = DISC * H;
  g.save(); g.beginPath(); g.arc(cx, cy, r, 0, TAU); g.clip(); // shadow side away from the key light (screen left)
  g.fillStyle = "rgba(39,48,77,0.38)"; g.beginPath(); g.arc(cx, cy, r, 0, TAU); g.arc(cx + r * 0.35, cy - r * 0.2, r * 1.05, 0, TAU, true); g.fill();
  g.fillStyle = "rgba(255,248,230,0.35)"; g.beginPath(); g.ellipse(cx + r * 0.4, cy - r * 0.45, r * 0.22, r * 0.12, -0.6, 0, TAU); g.fill();
  g.restore();
  p.poly(wobble(cx, cy, r, r, rng(o.seed, "rim"), o.boil, 0.015, 0.006, 64), null, lw(H, 9));
  ring(p, g, W, H, o, false);
}

/** flying saucer, side view: glass dome, disc body with a rim band and a row of lights. flying: the lights chase
 *  (one in BOIL_CYCLE lit, stepping with the boil); landed: three legs out, every light on. */
function saucer(p, g, W, H, o) {
  const cx = W / 2, cy = H * 0.56, rx = W * 0.46, ry = H * 0.17, landed = o.state === "landed";
  if (landed) for (const k of [-0.55, 0, 0.55]) p.stroke(jitter([[cx + k * rx * 0.8, cy + ry * 0.6], [cx + k * rx * 1.05, H * 0.97]], o.boil, 2), lw(H, 12));
  const dome = ellPts(cx, cy - ry * 0.35, rx * 0.42, H * 0.36, 180, 360, 0, 32);
  p.poly(jitter(dome, o.boil, 2), o.accent, lw(H, 10));
  g.fillStyle = "rgba(255,255,255,0.45)"; g.beginPath(); g.ellipse(cx - rx * 0.16, cy - H * 0.36, rx * 0.08, H * 0.07, -0.5, 0, TAU); g.fill();
  p.poly(wobble(cx, cy, rx, ry, rng(o.seed, "body"), o.boil, 0.01, 0.004, 64), o.main, lw(H, 11));
  p.poly(wobble(cx, cy + ry * 0.25, rx * 0.72, ry * 0.42, rng(o.seed, "rim"), o.boil, 0.01, 0.004, 48), shadeOf(o.main, 0.72), lw(H, 7));
  for (let i = 0; i < 7; i++) {
    const a = rad(200 - i * 36.7), x = cx + rx * 0.86 * Math.cos(a + Math.PI), y = cy + ry * 0.62 * Math.abs(Math.sin(a)) * 0.5;
    const on = landed || (i + o.b) % BOIL_CYCLE === 0;
    p.dot(x, y, lw(H, 15)); p.dot(x, y, lw(H, 10), on ? "#fff3b0" : "#8a7a3a");
  }
}

/** escape pod, side view, standing on its base: an egg hull with an open cockpit (the back layer: hull and cockpit;
 *  the front layer: the lower hull and the hatch, drawn over a rider), two landing feet. The hatch swings down and out
 *  from its bottom hinge as it opens (o.state open, or part way: o.from -> o.state at o.k). */
const POD = { cx: 0.5, cy: 0.56, rx: 0.42, ry: 0.42, rim: 0.5 }; // shares of W / H; rim: the cockpit's lower edge
function openness(o) {
  const at = (s) => (s === "open" ? 1 : 0);
  return o.from == null ? at(o.state) : at(o.from) + (at(o.state) - at(o.from)) * o.k;
}
function podBack(p, g, W, H, o) {
  const cx = W * POD.cx, cy = H * POD.cy, rx = W * POD.rx, ry = H * POD.ry;
  for (const k of [-0.5, 0.5]) p.stroke(jitter([[cx + k * rx, cy + ry * 0.8], [cx + k * rx * 1.25, H - 6]], o.boil, 2), lw(H, 12));
  p.poly(wobble(cx, cy, rx, ry, rng(o.seed, "hull"), o.boil, 0.012, 0.005, 64), o.main, lw(H, 11));
  p.poly(wobble(cx, H * 0.36, rx * 0.72, H * 0.17, rng(o.seed, "cockpit"), o.boil, 0.01, 0.004, 48), shadeOf(o.main, 0.45), lw(H, 8));
}
function podFront(p, g, W, H, o) {
  const cx = W * POD.cx, cy = H * POD.cy, rx = W * POD.rx, ry = H * POD.ry, rim = H * POD.rim;
  g.save(); g.beginPath(); g.rect(0, rim, W, H); g.clip(); // the hull below the cockpit rim, over the rider's legs
  p.poly(wobble(cx, cy, rx, ry, rng(o.seed, "hull"), o.boil, 0.012, 0.005, 64), o.main, lw(H, 11));
  g.restore();
  p.stroke(jitter([[cx - rx * 0.86, rim], [cx + rx * 0.86, rim]], o.boil, 2), lw(H, 9)); // the rim
  // the hatch: hinged at its bottom edge, swinging out toward the viewer (drawn foreshortened downward)
  const x0 = cx - rx * 0.32, x1 = cx + rx * 0.4, top = rim + H * 0.06, bot = H * 0.86, k = openness(o);
  const h = (bot - top) * Math.cos((k * Math.PI) / 2), lean = W * 0.05 * Math.sin((k * Math.PI) / 2);
  if (k > 0) p.poly(jitter([[x0, top], [x1, top], [x1, bot], [x0, bot]], o.boil, 1.5), shadeOf(o.main, 0.3), lw(H, 5)); // the doorway
  p.poly(jitter([[x0 - lean, bot - h], [x1 + lean, bot - h], [x1, bot], [x0, bot]], o.boil, 2), shadeOf(o.main, 0.85), lw(H, 8));
  p.dot(x1 - W * 0.04, bot - h * 0.5, lw(H, 9), o.accent); // the handle
  p.dot(cx + rx * 0.6, cy - ry * 0.05, lw(H, 11), INK); p.dot(cx + rx * 0.6, cy - ry * 0.05, lw(H, 7), o.accent); // a light
}

/** park bench, side-on: a plank seat on two legs with a backrest behind it, standing on its base */
function bench(p, g, W, H, o) {
  const seat = H * 0.55, wood = o.main, dark = shadeOf(o.main, 0.7);
  for (const x of [W * 0.14, W * 0.86]) p.poly(jitter([[x - W * 0.03, seat], [x + W * 0.03, seat], [x + W * 0.03, H - 4], [x - W * 0.03, H - 4]], o.boil, 1.5), o.accent, lw(H, 7));
  for (const x of [W * 0.2, W * 0.8]) p.stroke(jitter([[x, seat], [x, H * 0.08]], o.boil, 1.5), lw(H, 12));
  p.poly(jitter([[W * 0.08, H * 0.1], [W * 0.92, H * 0.1], [W * 0.92, H * 0.3], [W * 0.08, H * 0.3]], o.boil, 2), dark, lw(H, 8));
  p.poly(jitter([[W * 0.04, seat - H * 0.1], [W * 0.96, seat - H * 0.1], [W * 0.96, seat + H * 0.04], [W * 0.04, seat + H * 0.04]], o.boil, 2), wood, lw(H, 9));
}

/** glowing crystal cluster on its base: a soft halo (glow), three ink-outlined shards with a light facet each */
function crystal(p, g, W, H, o) {
  const gl = g.createRadialGradient(W / 2, H * 0.62, 0, W / 2, H * 0.62, W * 0.5);
  gl.addColorStop(0, `${o.accent}cc`); gl.addColorStop(1, `${o.accent}00`);
  g.fillStyle = gl; g.fillRect(0, 0, W, H);
  for (const [dx, h, w, tilt] of [[-0.18, 0.55, 0.16, -0.25], [0.2, 0.5, 0.15, 0.3], [0, 0.82, 0.22, 0]]) {
    const bx = W * (0.5 + dx), by = H - 8, tip = [bx + Math.sin(tilt) * H * h, by - H * h];
    const pts = [[bx - W * w, by], [bx - W * w * 0.8, by - H * h * 0.55], tip, [bx + W * w * 0.8, by - H * h * 0.55], [bx + W * w, by]];
    p.poly(jitter(pts, o.boil, 1.5), o.main, lw(H, 6));
    p.poly(jitter([[bx - W * w * 0.3, by - H * h * 0.2], tip, [bx, by - H * h * 0.5]], o.boil, 1), "rgba(255,255,255,0.55)", 0);
  }
}

/** built-in drawings: aspect (W / H), px (canvas height), base (share of the height from the bottom where the
 *  card's anchor sits: 0.5 = its middle), default colours, layers back to front. A layer: draw; still (no boil:
 *  drawn once per state); flow (its texture scrolls sideways with a flow anim, inside the clip path) */
export const DRAWERS = {
  planet: { aspect: 1.6, px: 512, base: 0.5, main: "#b388eb", accent: "#ffd166", layers: [
    { name: "ring-back", draw: (p, g, W, H, o) => ring(p, g, W, H, o, true) },
    { name: "surface", draw: planetBands, still: true, flow: true, clip: discPath },
    { name: "front", draw: planetFront },
  ] },
  saucer: { aspect: 2.2, px: 320, base: 0.5, main: "#9aa5b1", accent: "#7cf2c6", layers: [{ name: "body", draw: saucer }] },
  pod: { aspect: 1.3, px: 512, base: 0, main: "#e8e4da", accent: "#ff8a3d", layers: [
    { name: "back", draw: podBack }, { name: "front", draw: podFront }] },
  bench: { aspect: 2.0, px: 256, base: 0, main: "#b07a45", accent: "#4a4f57", layers: [{ name: "body", draw: bench }] },
  crystal: { aspect: 0.6, px: 256, base: 0, main: "#7cf2ff", accent: "#b6fbff", layers: [{ name: "body", draw: crystal }] },
};
/** an item's own shapes (ItemShape: canvas px around the base point, like a creature's body) on a 1024 square */
const SHAPES = { aspect: 1, px: 1024, base: 24 / 1024, main: "#8a8a8a", accent: "#3a2a1e", layers: [{ name: "shapes",
  draw: (p, g, W, H, o) => drawShapes(p, o.shapes.filter((s) => !s.when || s.when.includes(o.state)),
    ([x, y]) => [x + W / 2, y + H - 24], { main: o.main, accent: o.accent }, o.boil, o.seed, 0) }] };

// ---- texture cache (LRU over insertion order; an entry used this frame is never evicted) ----
const cache = new Map();
const stats = { hits: 0, misses: 0, evicted: 0, bytes: 0, peak: 0 };
let frame = 0;

function canvasOf(W, H, draw) {
  const c = Object.assign(document.createElement("canvas"), { width: W, height: H });
  draw(c.getContext("2d"));
  return c;
}
function cached(key, W, H, draw, setup) {
  const hit = cache.get(key);
  if (hit) { stats.hits++; cache.delete(key); cache.set(key, hit); hit.used = frame; return hit.tex; }
  stats.misses++;
  const tex = new THREE.CanvasTexture(canvasOf(W, H, draw));
  setup?.(tex);
  const bytes = W * H * 4;
  cache.set(key, { tex, bytes, used: frame });
  stats.bytes += bytes;
  for (const [k, e] of cache) { // oldest first
    if (stats.bytes <= CACHE_MB * 2 ** 20) break;
    if (e.used === frame) continue;
    e.tex.dispose(); cache.delete(k); stats.bytes -= e.bytes; stats.evicted++;
  }
  stats.peak = Math.max(stats.peak, stats.bytes);
  return tex;
}

const masks = new Map(); // drawer -> its flow layer's alpha map: white inside the clip path on black (outside the LRU)
function maskOf(name, W, H, clip) {
  const k = `${name}:${W}x${H}`;
  if (!masks.has(k)) masks.set(k, new THREE.CanvasTexture(canvasOf(W, H, (g) => {
    g.fillStyle = "#000"; g.fillRect(0, 0, W, H); g.fillStyle = "#fff"; g.beginPath(); clip(g, W, H); g.fill();
  })));
  return masks.get(k);
}

/** cache counters since the last reset: { hits, misses, evicted, entries, mb, peakMb } */
export function itemStats(reset = false) {
  const mb = (b) => +(b / 2 ** 20).toFixed(1);
  const out = { hits: stats.hits, misses: stats.misses, evicted: stats.evicted, entries: cache.size, mb: mb(stats.bytes), peakMb: mb(stats.peak) };
  if (reset) Object.assign(stats, { hits: 0, misses: 0, evicted: 0, peak: stats.bytes });
  return out;
}

/** a card for item def (a WorldObject with look "card"): { root (the back layer's mesh; the others are its children),
 *  def, drawer, key, ph, y }. opts: color / accent ($main / $accent; none: the drawing's own), tag + seed (the
 *  animation phase), layer (none: the item's). */
export function itemCard(def, { color = null, accent = null, tag = "", seed = 0, layer = def.layer || "mid" } = {}) {
  const D = def.draw ? DRAWERS[def.draw] : SHAPES;
  if (!D) throw new Error(`unknown item drawing "${def.draw}" (known: ${Object.keys(DRAWERS).join(", ")})`);
  const h = def.size || 1, w = h * D.aspect, H = D.px, W = Math.round(H * D.aspect);
  const geo = new THREE.PlaneGeometry(w, h).translate(0, h / 2 - D.base * h, 0);
  const meshes = D.layers.map((L, i) => {
    const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide,
      fog: layer !== "sky" }));
    m.renderOrder = LAYER_ORDER[layer] + i * LAYER_STEP;
    if (L.clip) m.material.alphaMap = maskOf(def.draw, W, H, L.clip);
    return m;
  });
  meshes.slice(1).forEach((m) => meshes[0].add(m));
  const main = color || D.main, acc = accent || D.accent;
  return { root: meshes[0], meshes, def, drawer: D, W, H, y: 0, ph: phaseOf(seed, tag),
    key: `${hash(JSON.stringify(def))}|${main}|${acc}`, main, accent: acc };
}

/** the state an item shows at frame n: { state, from, k } (from / k: part way from `from` while an open / close
 *  tweens, k in TWEEN_STEPS steps). it: a story item (schema ShotItem: state, switch { frame, to }) */
export function stateAt(it, n) {
  const sw = it.switch;
  if (!sw) return { state: it.state ?? null, from: null, k: 1 };
  const k = Math.round(Math.min(1, Math.max(0, (n - (sw.frame - TWEEN / 2)) / TWEEN)) * TWEEN_STEPS) / TWEEN_STEPS;
  return k >= 1 ? { state: sw.to, from: null, k: 1 } : k <= 0 ? { state: it.state ?? null, from: null, k: 1 }
    : { state: sw.to, from: it.state ?? null, k };
}

/** half the drawn width of an item's card, world units (a drawing doesn't fill its card: pipeline shots.ITEM_FILL) */
export const cardHalf = (def) => 0.5 * 0.8 * (def.size || 1) * (def.draw ? DRAWERS[def.draw]?.aspect ?? 1 : 1);

/** the seeded animation phase of item `tag` (itemCard; main.js seats its riders with the same) */
export const phaseOf = (seed, tag) => rng(seed, "item", tag)() * TAU;

/** draw card c for time t (s) and boil step `boil` (frame / BOIL_FRAMES) in `state` (none: the item's first), part
 *  way there from `from` at k (stateAt): textures from the cache, then the animation on top of where the caller put
 *  it (x added to, y from c.y). facing "left" mirrors it. Returns the state drawn. */
export function updateCard(c, { t, boil, state = null, from = null, k = 1, facing = "right" }) {
  const st = state ?? c.def.states?.[0] ?? null, b = ((boil % BOIL_CYCLE) + BOIL_CYCLE) % BOIL_CYCLE, { W, H } = c;
  frame = boil;
  const A = animAt(c.def.anims, st, t, c.ph), tw = from == null ? "" : `|${from}>${k}`;
  c.drawer.layers.forEach((L, i) => {
    const m = c.meshes[i], step = L.still ? 0 : b;
    const tex = cached(`${c.key}|${st}${tw}|${L.name}|${step}`, W, H, (g) => L.draw(new Pen(g, INK), g, W, H,
      { main: c.main, accent: c.accent, state: st, from, k, boil: rng(c.key, "boil", step), b: step, seed: c.key, shapes: c.def.shapes || [] }),
    (tex) => { tex.colorSpace = THREE.SRGBColorSpace; if (L.flow) tex.wrapS = THREE.RepeatWrapping; });
    if (m.material.map !== tex) { const fresh = !m.material.map; m.material.map = tex; if (fresh) m.material.needsUpdate = true; }
    if (L.flow) tex.offset.x = A.flow;
    m.material.opacity = A.opacity;
  });
  c.root.position.x += A.dx;
  c.root.position.y = c.y + A.dy;
  c.root.rotation.z = A.rot;
  c.root.scale.set((facing === "left" ? -1 : 1) * A.scale, A.scale, 1);
  return st;
}

const previews = new Map(); // dashboard preview layers (previewItem), cleared when it grows past a few items' worth
/** dashboard preview (web ItemPreview.vue), not a render path: item def drawn centred in 2D canvas `out` at time t
 *  with its animation, the same drawers and boil as a render. Throws for an unknown drawing. */
export function previewItem(out, def, { t = 0, state = null, color = null, accent = null } = {}) {
  const D = def.draw ? DRAWERS[def.draw] : SHAPES;
  if (!D) throw new Error(`unknown item drawing "${def.draw}" (known: ${Object.keys(DRAWERS).join(", ")})`);
  const H = D.px, W = Math.round(H * D.aspect), st = state ?? def.states?.[0] ?? null;
  const b = Math.floor((t * 30) / BOIL_FRAMES) % BOIL_CYCLE, A = animAt(def.anims, st, t, 0);
  const key = `${hash(JSON.stringify(def))}|${color || D.main}|${accent || D.accent}`;
  if (previews.size > 64) previews.clear();
  const layer = (L) => {
    const k = `${key}|${st}|${L.name}|${L.still ? 0 : b}`;
    if (!previews.has(k)) previews.set(k, canvasOf(W, H, (g) => L.draw(new Pen(g, INK), g, W, H,
      { main: color || D.main, accent: accent || D.accent, state: st, boil: rng(key, "boil", L.still ? 0 : b), b: L.still ? 0 : b, seed: key, shapes: def.shapes || [] })));
    return previews.get(k);
  };
  const g = out.getContext("2d"), k = Math.min((0.8 * out.width) / W, (0.6 * out.height) / H), unit = (k * H) / (def.size || 1);
  g.clearRect(0, 0, out.width, out.height);
  g.save();
  g.translate(out.width / 2 + A.dx * unit, out.height / 2 + (0.5 - D.base) * H * k - A.dy * unit); // the card's anchor
  g.rotate(-A.rot); g.scale(A.scale, A.scale); g.globalAlpha = A.opacity;
  for (const L of D.layers) {
    let c = layer(L);
    if (L.flow) { // scroll the layer sideways (wrapping) inside its clip path, as the render's offset + alpha map do
      const src = c, x = -A.flow * W;
      c = canvasOf(W, H, (mg) => { mg.beginPath(); L.clip(mg, W, H); mg.clip(); mg.drawImage(src, x, 0); mg.drawImage(src, x + W, 0); });
    }
    g.drawImage(c, (-W * k) / 2, -(1 - D.base) * H * k, W * k, H * k);
  }
  g.restore();
}
