// Weather in ink (story @weather, @fx lightning): rain streaks, scribble snowflakes, wind lines, hatched fog bands,
// a storm tint with mild ambient flashes, and one-shot lightning bolts. Deterministic: every particle is a pure
// function of (seed, index, time) from a fixed, capped pool, so a test render of frame n matches the final one.
// The stroke math is pure (node tests import it); paint() and fogCanvas() need a 2D canvas.
import { rng } from "./rng.js";
import { INK, STYLE } from "./style.js";

export const FADE_FRAMES = 15;      // 0.5 s cross-fade when the weather changes mid-scene (a set change wipes instead)
export const BOLT_FRAMES = 4;       // a strike's bolt shows this many frames ...
const FLASH = [0.32, 0.14];  // ... and the screen flashes white this much on its first frames (storm; else x0.7)
export const AMBIENT = { window: 75, gap: 12, alpha: [0.14, 0.06] }; // storm: <= 1 flash per window, never near a strike
const LEVEL = { light: 0, medium: 1, heavy: 2 };
// particles per intensity (light, medium, heavy): the pool size, so the cost per frame is capped. Rain and storm are
// the back + front layers together (style.js rain)
const RAIN = STYLE.rain;
const rainCount = (layer, storm, lv) => Math.round(RAIN[layer].count[lv] * (storm ? RAIN.storm.density : 1));
export const COUNT = { rain: [0, 1, 2].map((lv) => rainCount("back", false, lv) + rainCount("front", false, lv)),
  storm: [0, 1, 2].map((lv) => rainCount("back", true, lv) + rainCount("front", true, lv)),
  snow: [36, 70, 110], wind: [4, 7, 11] };
// r g b, alpha by level: strong enough to read on the stills sheet (a still there is about a fifth of the frame)
const TINT = { storm: [20, 24, 40, [0.24, 0.34, 0.44]], rain: [40, 48, 60, [0.1, 0.14, 0.18]] };
const FOG_ALPHA = [0.45, 0.65, 0.85];
const AMBIENT_P = [0.3, 0.45, 0.6];

const key = (w) => (w ? `${w.kind}:${w.intensity}` : "clear");
export const same = (a, b) => key(a) === key(b);

/** per shot id: { from: weather faded out, at: frame the change began } while a mid-scene change still fades in */
export function fadePlan(shots) {
  const out = new Map();
  let fade = null;
  shots.forEach((s, i) => {
    const p = shots[i - 1];
    if (!p || p.set !== s.set) fade = null;
    else if (!same(p.weather, s.weather)) fade = { from: p.weather || null, at: s.start_frame };
    if (fade && s.start_frame - fade.at >= FADE_FRAMES) fade = null;
    if (fade) out.set(s.id, fade);
  });
  return out;
}

/** the weather layers at frame n: [{ weather, amount 0..1 }] (two during a fade) */
export function layersAt(shot, fade, n) {
  const p = fade ? Math.min(1, Math.max(0, (n - fade.at) / FADE_FRAMES)) : 1;
  return [{ weather: shot.weather || null, amount: p }, ...(p < 1 ? [{ weather: fade.from, amount: 1 - p }] : [])]
    .filter((l) => l.weather && l.amount > 0);
}

const pools = new Map();
/** fixed per-particle constants for one kind and seed (built once, reused every frame) */
function pool(kind, seed, n) {
  const k = `${kind}:${seed}:${n}`;
  if (!pools.has(k)) {
    const R = rng(seed, "weather", kind);
    pools.set(k, Array.from({ length: n }, () => [R(), R(), R(), R(), R()]));
  }
  return pools.get(k);
}

const hits = (r, x0, y0, x1, y1) => Math.min(x0, x1) < r[2] && Math.max(x0, x1) > r[0] && Math.min(y0, y1) < r[3] && Math.max(y0, y1) > r[1];

/** ink strokes for one weather layer at time t (s) on a w x h frame: [{ pts: [[x, y], ...], width, color, alpha, layer }].
 *  Rain and storm come in two layers (layer "back": behind the cast, "front": over it); only = "back" | "front"
 *  returns just that one (snow and wind are front). avoid: screen rects [x0, y0, x1, y1] no front drop may cross. */
export function strokes(weather, seed, t, w, h, amount = 1, { only = null, avoid = [] } = {}) {
  if (!weather || weather.kind === "fog") return [];
  const lv = LEVEL[weather.intensity] ?? 1, kind = weather.kind, out = [];
  const n = COUNT[kind][lv];
  const wrap = (v, m) => ((v % m) + m) % m;
  if (kind === "rain" || kind === "storm") {
    const storm = kind === "storm", slant = storm ? RAIN.storm.slant : RAIN.slant; // storm: wind-driven, strongly slanted
    const len = storm ? RAIN.storm.len : RAIN.len + RAIN.lenPerLevel * lv, speed = h * (storm ? RAIN.storm.speed : RAIN.speed);
    for (const layer of ["back", "front"]) {
      if (only && only !== layer) continue;
      const S = RAIN[layer], back = layer === "back";
      for (const [a, b, c, d] of pool(`${kind}:${layer}`, seed, rainCount(layer, storm, lv))) {
        // back: one length and speed band; front: each drop its own length and speed (varied)
        const L = len * (back ? S.len * (0.7 + 0.6 * c) : S.len[0] + (S.len[1] - S.len[0]) * c), span = h + L;
        const v = speed * (back ? S.speed * (0.85 + 0.3 * d) : S.speed[0] + (S.speed[1] - S.speed[0]) * d) / RAIN.speed;
        const y = wrap(b * span + v * t, span) - L;
        const x = wrap(a * (w + 200) + slant * y, w + 200) - 100;
        if (!back && avoid.some((r) => hits(r, x, y, x + slant * L, y + L))) continue;
        out.push({ pts: [[x, y], [x + slant * L, y + L]], width: S.width + (back ? 0 : 0.5 * lv), color: S.color,
          alpha: S.alpha * amount, layer, ...(back ? {} : { edge: S.edge, edgeAlpha: S.edgeAlpha * amount }) });
      }
    }
  } else if (kind === "snow" && only !== "back") {
    for (const [a, b, c, d, e] of pool(kind, seed, n)) {
      const r = 5 + 6 * c, span = h + 4 * r;
      const y = wrap(b * span + h * (0.06 + 0.06 * d) * t, span) - 2 * r;
      const x = wrap(a * w + 26 * Math.sin(t * (0.8 + d) + 6.28 * e), w);
      const rot = e * 3 + t * (d - 0.5);
      for (let k = 0; k < 3; k++) { // a scribbled asterisk: three crossing ticks
        const ang = rot + (k * Math.PI) / 3, dx = r * Math.cos(ang), dy = r * Math.sin(ang);
        out.push({ pts: [[x - dx, y - dy], [x + dx, y + dy]], width: 2.5, color: INK, alpha: 0.75 * amount, layer: "front" });
      }
    }
  } else if (kind === "wind" && only !== "back") {
    for (const [a, b, c, d] of pool(kind, seed, n)) {
      const len = w * (0.18 + 0.14 * c), span = w + len + 200;
      const x0 = wrap(a * span + w * (0.55 + 0.3 * d) * t, span) - len - 100, y0 = h * (0.12 + 0.7 * b);
      const pts = [];
      for (let k = 0; k <= 10; k++) {
        const u = k / 10;
        pts.push([x0 + len * u, y0 + 14 * Math.sin(6.28 * u + t * 2 + 6.28 * d)]);
      }
      const [ex, ey] = pts[pts.length - 1]; // the curl at the leading end
      for (let k = 1; k <= 8; k++) {
        const ang = -Math.PI / 2 + (k / 8) * 1.6 * Math.PI;
        pts.push([ex + 16 * Math.cos(ang), ey + 16 + 16 * Math.sin(ang)]);
      }
      out.push({ pts, width: 3, color: INK, alpha: 0.5 * amount, layer: "front" });
    }
  }
  return out;
}

/** screen tint for a layer: [r, g, b, alpha] or null (storm darkens, rain greys a little) */
export function tint(weather, amount = 1) {
  const T = weather && TINT[weather.kind];
  return T ? [T[0], T[1], T[2], T[3][LEVEL[weather.intensity] ?? 1] * amount] : null;
}

export const fogAlpha = (weather, amount = 1) => (weather?.kind === "fog" ? FOG_ALPHA[LEVEL[weather.intensity] ?? 1] * amount : 0);

/** the strike drawn at frame n: { strike, index, k frames since it began } or null */
export function strikeAt(strikes, n) {
  for (let i = strikes.length - 1; i >= 0; i--) {
    const k = n - strikes[i].frame;
    if (k >= 0 && k < BOLT_FRAMES) return { strike: strikes[i], index: i, k };
  }
  return null;
}

/** white flash alpha at frame n: a strike's flash, else (storm only) an ambient flash, never near a strike */
export function flashAt(n, seed, weather, strikes) {
  const s = strikeAt(strikes, n);
  if (s) return (FLASH[s.k] ?? 0) * (weather?.kind === "storm" ? 1 : 0.7);
  if (weather?.kind !== "storm") return 0;
  const win = Math.floor(n / AMBIENT.window), R = rng(seed, "ambient", win);
  if (R() >= AMBIENT_P[LEVEL[weather.intensity] ?? 1]) return 0;
  const f = win * AMBIENT.window + Math.floor(R() * (AMBIENT.window - AMBIENT.alpha.length));
  if (strikes.some((x) => Math.abs(x.frame - f) < AMBIENT.gap)) return 0;
  return AMBIENT.alpha[n - f] ?? 0;
}

/** jagged bolt from above the frame down to (x, y): main path + one fork, seeded per strike */
export function bolt(seed, index, x, y) {
  const R = rng(seed, "bolt", index), steps = 9, top = -40, x0 = x + (R() - 0.5) * 220;
  const main = [];
  for (let i = 0; i <= steps; i++) {
    const u = i / steps, j = i === 0 || i === steps ? 0 : (R() - 0.5) * 90;
    main.push([x0 + (x - x0) * u + j, top + (y - top) * u]);
  }
  const at = 3 + Math.floor(R() * 3), [fx, fy] = main[at], dir = R() < 0.5 ? -1 : 1;
  const fork = [[fx, fy]];
  for (let i = 1; i <= 3; i++) fork.push([fx + dir * (40 + R() * 30) * i, fy + (60 + R() * 40) * i]);
  return [main, fork];
}

/** rain's tint is drawn behind the cast (back); a storm's darkening covers everything (front) */
const tintLayer = (weather) => (weather?.kind === "rain" ? "back" : "front");

function drawStrokes(g, list) {
  for (const s of list) {
    const line = () => { g.beginPath(); s.pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke(); };
    if (s.edge) { g.globalAlpha = s.edgeAlpha; g.strokeStyle = s.edge; g.lineWidth = s.width + 3; line(); } // ink rim
    g.globalAlpha = s.alpha; g.strokeStyle = s.color; g.lineWidth = s.width; line();
  }
  g.globalAlpha = 1;
}

/** draw the back weather layer (behind the cast: rain tint, back rain) into a cleared 2D context of w*scale x h*scale.
 *  Returns false when there is nothing to draw (the engine then skips the layer). */
export function paintBack(g, { layers, seed, t, w, h, scale = 1 }) {
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, w * scale, h * scale);
  g.setTransform(scale, 0, 0, scale, 0, 0);
  g.lineCap = g.lineJoin = "round";
  let any = false;
  for (const { weather, amount } of layers) {
    const c = tintLayer(weather) === "back" && tint(weather, amount);
    if (c) { g.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${c[3]})`; g.fillRect(0, 0, w, h); any = true; }
    const list = strokes(weather, seed, t, w, h, amount, { only: "back" });
    drawStrokes(g, list);
    any ||= list.length > 0;
  }
  g.setTransform(1, 0, 0, 1, 0, 0);
  return any;
}

/** draw one frame's front weather overlay into a cleared 2D context (avoid: face rects front drops skip) */
export function paint(g, { layers, seed, t, n, w, h, strikes = [], target = null, avoid = [] }) {
  g.clearRect(0, 0, w, h);
  g.lineCap = g.lineJoin = "round";
  for (const { weather, amount } of layers) {
    const c = tintLayer(weather) === "front" && tint(weather, amount);
    if (c) { g.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${c[3]})`; g.fillRect(0, 0, w, h); }
    drawStrokes(g, strokes(weather, seed, t, w, h, amount, { only: "front", avoid }));
  }
  g.globalAlpha = 1;
  const main = layers.find((l) => l.amount >= 0.5)?.weather || null, hit = strikeAt(strikes, n);
  if (hit && target) {
    const storm = main?.kind === "storm";
    for (const [pi, path] of bolt(seed, hit.index, target[0], target[1]).entries()) {
      for (const [col, lw] of [[INK, storm ? 24 : 18], ["#fff3a6", storm ? 12 : 9]]) { // ink edge, pale core
        g.strokeStyle = col; g.lineWidth = lw * (pi ? 0.6 : 1); // the fork is thinner
        g.beginPath(); path.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke();
      }
    }
  }
  const f = flashAt(n, seed, main, strikes);
  if (f > 0) { g.fillStyle = `rgba(255,253,240,${f})`; g.fillRect(0, 0, w, h); }
  return { flash: f, strike: hit ? hit.index : null };
}

/** hatched fog bands on a transparent canvas, tiling left-right (the engine scrolls it slowly) */
export function fogCanvas(seed, size = 512) {
  const c = document.createElement("canvas");
  c.width = 2 * size; c.height = size;
  const g = c.getContext("2d"), R = rng(seed, "fog"), W = c.width;
  g.lineCap = "round";
  for (const [cy, half] of [[0.22, 0.09], [0.5, 0.11], [0.77, 0.1]]) { // bands clear of the edges: no flat cut
    const ph = R() * 6.28, edge = (x, s) => size * (cy + s * half + 0.05 * Math.sin((x / W) * 4 * Math.PI + ph * s));
    g.fillStyle = "rgba(238,235,228,0.5)";
    g.beginPath();
    for (let x = 0; x <= W; x += 16) g.lineTo(x, edge(x, -1));
    for (let x = W; x >= 0; x -= 16) g.lineTo(x, edge(x, 1));
    g.closePath(); g.fill();
    g.strokeStyle = "rgba(110,106,98,0.42)"; g.lineWidth = 3;
    for (let x = 10; x < W - 40; x += 22 + R() * 26) { // loose diagonal hatch ticks, seeded, never a regular grid
      const top = edge(x, -1), bot = edge(x, 1), y = top + (bot - top) * (0.2 + 0.5 * R()), len = (bot - top) * (0.25 + 0.3 * R());
      g.beginPath(); g.moveTo(x, y + len); g.lineTo(x + len * (0.5 + 0.3 * R()), y); g.stroke();
    }
  }
  return c;
}
