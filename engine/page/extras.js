// Extras (non-cast stickmen): seeded looks and crowd-mood timing. Pure functions (Node-testable): same inputs, same
// look / pose. Drawn with drawStickman like the cast, in the same marker style.
import { rng } from "./rng.js";

const TAU = Math.PI * 2;
// muted tops so the cast stays the colour that reads first
export const EXTRA_TOPS = ["#7a6a58", "#6f7d8c", "#8c7b6b", "#5f6f5e", "#8a6f6f", "#6b6f86", "#9a8f7a", "#7d7d74"];
const HATS = ["#4a4a4a", "#5a4632", "#3d3d46"], TROUSERS = ["#3a3530", "#43464d", "#4d4338"];
export const MOOD_EXPRESSION = { cheer: "happy", angry: "angry", gasp: "surprised", salute: "neutral", neutral: "neutral" };
export const MOOD = { cheerHz: 1.6, shakeHz: 4, offset: 2.0 }; // pumps / shakes per second; up to 2 s timing offset
export const EXTRA_SATURATION = 0.85; // extras' colours at 85% of their palette's saturation: the cast reads first
export const GAP = { crowd: 0.55, runner: 0.6 }; // min x between extras of a kind in one row (planner spacing too)
export const HEAD_GROW = 0.06;                  // cast head boxes grow by 6% per side for the overlap check

/** #rrggbb with its HSL saturation scaled by k */
export function desaturate(hex, k = EXTRA_SATURATION) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
  if (d === 0) return hex.toLowerCase();
  const s = (d / (1 - Math.abs(2 * l - 1))) * k, h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs((h % 2) - 1)), m = l - c / 2;
  const [r1, g1, b1] = h < 1 ? [c, x, 0] : h < 2 ? [x, c, 0] : h < 3 ? [0, c, x] : h < 4 ? [0, x, c] : h < 5 ? [x, 0, c] : [c, 0, x];
  return "#" + [r1, g1, b1].map((v) => Math.round(Math.min(1, Math.max(0, v + m)) * 255).toString(16).padStart(2, "0")).join("");
}

export const CROWD_FIT = { margin: 0.2, rowStep: 0.3 }; // world units: frame margin per side, row depth spacing

/** Crowd re-laid for one shot so every extra is in frame and clear of the cast: rows from the front-most planned z
 *  back to zBack, CROWD_FIT.rowStep apart. In each row the free spots are found first: a FIT_STEP grid across the
 *  visible x range at that depth (rangeAt(z) -> [lo, hi]) minus the margin, keeping only spots where free(x, z) (no
 *  head overlap with the cast), packed left to right GAP.crowd+ apart. Rows then fill front to back in list order,
 *  each row's extras spread evenly over its free spots; whoever is left when every row is full is dropped.
 *  Map id -> { pos: [x, z], bounds: [lo, hi] } or null. */
export const FIT_STEP = 0.05;
export function fitCrowd(crowd, rangeAt, { zBack = -2.8, gap = GAP.crowd, margin = CROWD_FIT.margin, rowStep = CROWD_FIT.rowStep,
  free = () => true } = {}) {
  const out = new Map();
  if (!crowd.length) return out;
  const front = Math.max(...crowd.map((e) => e.start_pos[1])), rows = [];
  for (let z = front; z >= zBack - 1e-9; z -= rowStep) rows.push(Math.round(z * 1000) / 1000);
  if (!rows.length) rows.push(front);
  let next = 0;
  for (const z of rows) {
    if (next >= crowd.length) break;
    const [lo, hi] = rangeAt(z), a = lo + margin, b = hi - margin, slots = [];
    for (let x = a; x <= b + 1e-9; x += FIT_STEP) {
      const xr = Math.round(x * 1000) / 1000;
      if ((!slots.length || xr - slots.at(-1) >= gap - 1e-9) && free(xr, z)) slots.push(xr);
    }
    const n = Math.min(slots.length, crowd.length - next);
    for (let k = 0; k < n; k++) { // spread over the free slots: first and last used when there are two or more
      const s = slots[n === 1 ? Math.floor((slots.length - 1) / 2) : Math.round((k * (slots.length - 1)) / (n - 1))];
      out.set(crowd[next + k].id, { pos: [s, z], bounds: [a, b] });
    }
    next += n;
  }
  for (const e of crowd.slice(next)) out.set(e.id, null);
  return out;
}

const overlaps = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
const grow = (r, k) => { const mx = (r[2] - r[0]) * k, my = (r[3] - r[1]) * k; return [r[0] - mx, r[1] - my, r[2] + mx, r[3] + my]; };

/** Where each extra stands for one shot: Map id -> x shift (0 = as planned), or null = dropped for this shot.
 *  An extra whose head box would overlap any cast member's head box (grown HEAD_GROW) at a sampled moment is moved
 *  along its row (0.1 steps, nearest first, right before left, up to 1.5) keeping GAP from the extras of its kind
 *  and row already placed, or dropped when nothing fits. Deterministic: extras in list order, fixed samples.
 *  setCamera(u): camera at shot fraction u; castRects(u): cast head rects; headRect(e, dx, u): the extra's;
 *  bounds(e) -> [lo, hi] or null: where the extra's x may go (crowd: its row's visible range). */
export function placeExtras(extras, { setCamera, castRects, headRect, bounds = () => null }) {
  const out = new Map(), placed = new Map(); // row key -> x of extras already placed there
  const samples = (e) => (e.kind === "runner" ? Array.from({ length: 11 }, (_, i) => i / 10) : [0, 0.5, 1]);
  const us = [...new Set(extras.flatMap(samples))].sort();
  const cast = new Map(us.map((u) => { setCamera(u); return [u, castRects(u).map((r) => grow(r, HEAD_GROW))]; }));
  const shifts = [0];
  for (let k = 1; k <= 15; k++) shifts.push(k / 10, -k / 10);
  for (const e of extras) {
    const row = `${e.kind}:${e.kind === "crowd" ? (e.start_pos[1] > -2.2 ? "front" : "back") : "all"}`;
    const xs = placed.get(row) || [], gap = GAP[e.kind] ?? 0.55;
    // runners move: test the box swept between neighbouring samples, so no position along the run slips between them
    const box = (dx, u) => { setCamera(u); return headRect(e, dx, u); };
    const swept = (dx, i, ss) => { const a = box(dx, ss[i]), b = i + 1 < ss.length ? box(dx, ss[i + 1]) : a;
      return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])]; };
    const clear = (dx) => samples(e).every((u, i, ss) => {
      const r = e.kind === "runner" ? swept(dx, i, ss) : box(dx, u);
      return !cast.get(u).some((c) => overlaps(r, c)) && (i + 1 >= ss.length || !cast.get(ss[i + 1]).some((c) => overlaps(r, c)));
    });
    const lim = bounds(e), inside = (dx) => !lim || (e.start_pos[0] + dx >= lim[0] - 1e-9 && e.start_pos[0] + dx <= lim[1] + 1e-9);
    const fits = (dx) => inside(dx) && xs.every((x) => Math.abs(e.start_pos[0] + dx - x) >= gap - 1e-9) && clear(dx);
    const dx = shifts.find(fits);
    out.set(e.id, dx ?? null);
    if (dx != null) placed.set(row, [...xs, e.start_pos[0] + dx]);
  }
  return out;
}

/** look of extra e ({ kind, variant }) in series `slug`: crowd: plain or shirt top, maybe a flat cap or bowler,
 *  maybe trousers; runner: tank top with a 2-digit number, dark shorts. Fields as a series.json cast entry. */
export function extraLook(slug, e) {
  const R = rng(slug, "extra", e.kind, e.variant), pick = (xs) => xs[Math.floor(R() * xs.length)];
  const color = desaturate(pick(EXTRA_TOPS)), eyes = R() < 0.25 ? "half_closed" : "dots";
  if (e.kind === "runner") {
    return { top: { style: "tank", color, number: String(10 + Math.floor(R() * 90)) }, eyes,
      headwear: { kind: "none" }, legwear: { kind: "shorts", color: "#2b2b2b" }, props: [] };
  }
  const style = R() < 0.5 ? "plain" : "shirt", h = R();
  const headwear = h < 0.3 ? { kind: "flat_cap", color: desaturate(pick(HATS)) } : h < 0.5 ? { kind: "bowler", color: desaturate(pick(HATS)) } : { kind: "none" };
  const legwear = R() < 0.6 ? { kind: "trousers", color: desaturate(pick(TROUSERS)) } : { kind: "none" };
  // Crowd entries may carry the same wardrobe and held-prop shape as a cast look.
  // The seeded fallback remains unchanged for ordinary crowds.
  return { top: { style, color }, eyes, headwear, legwear, props: [], ...(e.top ? { top: e.top } : {}),
    ...(e.headwear ? { headwear: e.headwear } : {}), ...(e.legwear ? { legwear: e.legwear } : {}),
    ...(e.props?.length ? { props: e.props } : {}) };
}

/** crowd mood pose at time t for the figure keyed `key` (each one's timing offset, so a crowd never moves in sync):
 *  { k 0..1 arms into the mood pose, bounce 0..1 (cheer hops), crouch 0..1 (cheer knees between hops), shake -1..1 (angry fists) } */
export function moodAt(mood, t, key) {
  const tt = t + rng(key, "mood")() * MOOD.offset;
  if (mood === "cheer") {
    const s = Math.sin(TAU * MOOD.cheerHz * tt);
    return { k: 0.85 + 0.15 * s, bounce: Math.max(0, s), crouch: Math.max(0, -s), shake: 0 }; // arms stay high: no sweep into neighbours; knees crouch between hops
  }
  if (mood === "angry" || mood === "fight") return { k: 1, bounce: 0, shake: Math.sin(TAU * MOOD.shakeHz * tt) };
  if (mood === "salute") return { k: 1, bounce: 0, shake: 0 };
  if (mood === "gasp") return { k: 1, bounce: 0, shake: 0.15 * Math.sin(TAU * 7 * tt) }; // a small tremble
  return { k: 0, bounce: 0, shake: 0 };
}
