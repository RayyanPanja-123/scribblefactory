// Our stickman (docs/brief.md "Stickman style"), drawn on a 512 x 1024 canvas, feet at y = FEET_Y.
// Pure function of its options: same options -> same pixels. Facing "right" is the base drawing;
// "left" is the same drawing mirrored; "camera" looks straight out.
import { Pen, ellPts } from "./borrowed.js";
import { rng } from "./rng.js";

export const CW = 512, CH = 1024, FEET_Y = 1000;
const INK = "#1c1a1a";
const HEAD_R = 150;
const HEAD_SQUASH = 0.97; // head height / width
const LEG = 220;         // leg length; hip height follows the leg angle, so feet stay planted
const IDLE_LEG = 6;      // degrees each leg splays when standing
const BODY_RX = 92, BODY_RY = 150;
const BREATH = 0.03;     // body height change at full breath
const HIP_OVERLAP = 12;  // body blob reaches this far below the hips
const NECK_OVERLAP = 24; // head sits this far down into the body
const LUMP = 0.035, JIT = 0.012, LUMP_SUM = 1 + 0.6 + 0.4; // wobble: shape lumps (3 harmonics) + boil jitter
// face strokes: canvas px width, and the minimum width they keep ON SCREEN when the character is drawn small
// (o.px = screen px per canvas px). Thickening is capped so a tiny face doesn't turn into a blot.
const FACE = { brow: [20, 6], eye: [9, 3.5], eyeRim: [7, 3], mouth: [8, 3.5], pupil: [12, 3] };
const FACE_MAX = 2.5;
const ARM = 175;
// arms: angles in degrees from straight down (+ toward +x); bend = forearm turn relative to the upper arm
const ARM_REST = 16;      // idle and talk arms hang this far out
const TALK_SWAY = 3;      // degrees of slow arm sway while talking, at TALK_SWAY_HZ
const TALK_SWAY_HZ = 0.6;
const BOB_PX = 7;         // body lift on a stressed word (canvas px; legs stretch, feet stay planted)
const POINT_ANGLE = 96;   // point arm, fully raised
const WAVE_ARM = [100, 50, 25]; // wave: upper arm angle, forearm bend, forearm swing +- (degrees); clears the head
// gesture targets [left angle, left bend, right angle, right bend, shoulder lift px]
const GESTURES = {
  palm: [-ARM_REST, 0, 40, 60, 0],     // right forearm out, open palm toward the listener
  chin: [-ARM_REST, 0, 70, 70, 0],     // small point at chin height
  shrug: [-40, -110, 40, 110, 10],      // both forearms up and out, shoulders up
};
const TAU = Math.PI * 2;
const deg = (d) => (d * Math.PI) / 180;

// headwear: the band's lower edge sits HAT_BRIM above the head centre (forehead, just over the neutral brows) and
// reaches past the head outline on both sides; nothing rises more than HAT_TOP above the head centre
export const HAT_BRIM = 88, HAT_TOP = 192;

/** Tallest standing figure, feet to the highest point the head outline or any headwear can reach (full breath,
 *  word bob, max wobble), in canvas px. main.js turns it into world units for framing; derived from the drawing's constants. */
export const FIGURE_PX = (() => {
  const hip = FEET_Y - LEG * Math.cos(deg(IDLE_LEG)), ry = BODY_RY * (1 + BREATH);
  const headCy = hip - BOB_PX + HIP_OVERLAP - 2 * ry - HEAD_R + NECK_OVERLAP; // stressed-word bob lifts it too
  return FEET_Y - (headCy - Math.max(HEAD_R * HEAD_SQUASH * (1 + LUMP * LUMP_SUM + JIT), HAT_TOP));
})();

// brows per expression: [outer dy, inner dy, arch] (negative = up)
const BROWS = {
  neutral: [0, 0, 8], happy: [-6, -8, 12], sad: [10, -16, 4],
  angry: [-8, 16, 0], surprised: [-12, -12, 14], sleepy: [5, 5, 2],
  cheeky: [[4, 4, 3], [-12, -8, 12]], // [left brow, right brow]: one brow up
  exhausted: [16, 0, 2],                // droopy: outer ends sag
};

/** closed wobbly loop: stable per-character lumps (shape) + small per-boil jitter (boil) */
export function wobble(cx, cy, rx, ry, shape, boil, lump = LUMP, jit = JIT, n = 44) {
  const ph = [shape() * TAU, shape() * TAU, shape() * TAU];
  const pts = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * TAU;
    const k = 1 + lump * (Math.cos(2 * a + ph[0]) + 0.6 * Math.cos(3 * a + ph[1]) + 0.4 * Math.cos(5 * a + ph[2]))
      + jit * (boil() * 2 - 1);
    pts.push([cx + rx * k * Math.cos(a), cy + ry * k * Math.sin(a)]);
  }
  return pts;
}

/** marker wobble: the stroke drifts smoothly from one random offset at its start to another at its end */
export const jitter = (pts, boil, amp = 2.5) => {
  const d = [boil(), boil(), boil(), boil()].map((v) => amp * (v * 2 - 1)), n = Math.max(1, pts.length - 1);
  return pts.map(([x, y], i) => [x + d[0] + ((d[2] - d[0]) * i) / n, y + d[1] + ((d[3] - d[1]) * i) / n]);
};
const at = ([x, y], ang, len) => [x + Math.sin(ang) * len, y + Math.cos(ang) * len]; // ang from straight down, + toward +x
const quad = (a, c, b, n = 10) => Array.from({ length: n + 1 }, (_, i) => {
  const t = i / n, s = 1 - t;
  return [s * s * a[0] + 2 * s * t * c[0] + t * t * b[0], s * s * a[1] + 2 * s * t * c[1] + t * t * b[1]];
});

/** Pure pose: every joint the drawing (and costumes) hang on, in unrotated canvas px (lean is applied about the
 *  feet when drawing). legs: [[hip, foot] x2], arms: [[shoulder, elbow, hand] left (-x), right (+x)], fore: forearm
 *  angles, head: [hx, hy]. */
export function skeleton(o) {
  const moving = o.action === "walk" || o.action === "run", run = o.action === "run";
  const lean = run ? deg(9) : o.action === "react" ? deg(-6) : o.action === "walk" ? deg(3) : 0;
  // legs: walk phase drives the swing; hip height = FEET_Y - LEG cos(angle). A stressed-word bob lifts the hips;
  // the legs reach down to the same planted feet.
  const s = Math.sin(TAU * (o.phase || 0));
  const A = moving ? deg(run ? 34 : 24) * s : deg(IDLE_LEG);
  const hipBase = FEET_Y - LEG * Math.cos(A), hipY = hipBase - BOB_PX * (o.bob || 0);
  const legs = [[-18, -A], [18, A]].map(([dx, a]) => [[CW / 2 + dx, hipY], at([CW / 2 + dx, hipBase], a, LEG)]);
  // body: breathing scales its height from the hips up
  const ry = BODY_RY * (1 + BREATH * (o.breath || 0)), cy = hipY + HIP_OVERLAP - ry, top = cy - ry;

  // arms (screen angles from straight down, + toward +x)
  let lift = 0, aL = deg(-ARM_REST), aR = deg(ARM_REST), bendL = 0, bendR = 0;
  if (moving) {
    const S = deg(run ? 16 : 13) * s; // both arms sway with the stride; small enough never to cross the body
    aL = deg(-18) + S; aR = deg(18) + S;
    if (run) { bendL = deg(70); bendR = deg(70); }
  } else if (o.action === "talk") {
    // calm by default: arms hang with a slow sway; an optional seeded gesture blends in (o.gesture)
    const sway = deg(TALK_SWAY) * Math.sin(TAU * TALK_SWAY_HZ * (o.t || 0));
    aL += sway; aR += sway;
    const G = o.gesture && GESTURES[o.gesture.kind], k = o.gesture ? o.gesture.k : 0;
    if (G && k > 0) {
      aL += (deg(G[0]) - aL) * k; bendL = deg(G[1]) * k;
      aR += (deg(G[2]) - aR) * k; bendR = deg(G[3]) * k;
      lift = G[4] * k;
    }
  } else if (o.action === "point") {
    aR += (deg(POINT_ANGLE) - aR) * (o.pointK ?? 1); // main.js lowers it again after a moment
  } else if (o.action === "wave") {
    const w = o.wave || { k: 1, swing: 0 };
    aR += (deg(WAVE_ARM[0]) - aR) * w.k;
    bendR = deg(WAVE_ARM[1] + WAVE_ARM[2] * w.swing) * w.k;
  } else if (o.action === "react") {
    aL = deg(-128); aR = deg(128); bendL = deg(-25); bendR = deg(25); // hands up beside the head
  } else {
    aL -= deg(2) * (o.breath || 0); aR += deg(2) * (o.breath || 0);
  }
  // seated in the car (legs and low hands hidden by the side panel): each prop hand comes up to the chest,
  // unless that arm is waving
  if (o.seated) for (const pr of o.props || []) {
    if (pr.hand === "left") { aL = -HOLD[0]; bendL = -HOLD[1]; } else if (o.action !== "wave") { aR = HOLD[0]; bendR = HOLD[1]; }
  }
  const sh = top + 58 - lift;
  const arms = [[[CW / 2 - 66, sh], aL, bendL], [[CW / 2 + 66, sh], aR, bendR]].map(([shp, a, bend]) => {
    const elbow = at(shp, a, ARM * 0.52);
    return [shp, elbow, at(elbow, a + bend, ARM * 0.48)];
  });
  const head = [CW / 2 + (o.action === "react" ? -10 : 0), top - HEAD_R + NECK_OVERLAP];
  return { lean, legs, hipY, cy, ry, top, arms, fore: [aL + bendL, aR + bendR], head };
}

/**
 * o: { seed, boil, color, eyes: "dots"|"half_closed", expression, action, phase (walk cycles), lid (0 | 0.5 | 1),
 *      mouth (0..1 open), breath (-1..1), facing: "left"|"right"|"camera", t (seconds),
 *      px (screen px per canvas px; face strokes keep a minimum on-screen width, default 1),
 *      bob (0..1 stressed-word lift), gesture ({ kind: palm|chin|shrug, k: 0..1 } while talking),
 *      pointK (0..1 point arm raised, default 1), wave ({ k: 0..1 raised, swing: -1..1 } for action wave),
 *      costume (series.json cast v2, all optional): top { style, color, accent_color, number }, headwear { kind, color },
 *      legwear { kind, color }, props [{ kind, hand }] (max one per hand),
 *      seated (in a car: the prop hand is raised into view), mirrored (the card is shown mirrored: keeps the chest
 *      number readable) }
 * action "ride" draws like idle (the car hides the legs). color is the body colour (top.color when a top is given).
 */
export function drawStickman(canvas, o) {
  const g = canvas.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, CW, CH);
  if (o.facing === "left") g.setTransform(-1, 0, 0, 1, CW, 0);
  const p = new Pen(g, INK);
  const boil = rng(o.seed, "boil", o.boil);
  const cos = rng(o.seed, "costume", o.boil); // costume jitter: its own stream, so a plain figure draws as before
  const look = o.facing === "camera" ? 0 : 1;
  const k = skeleton(o);

  // whole-figure lean about the feet
  g.translate(CW / 2, FEET_Y); g.rotate(k.lean); g.translate(-CW / 2, -FEET_Y);

  for (const leg of k.legs) p.stroke(jitter(leg, boil), 10);
  if (o.legwear && o.legwear.kind !== "none") legwear(p, cos, o.legwear, k.legs);

  // body: flat outfit-colour blob (covers the top of the legwear)
  const body = wobble(CW / 2, k.cy, BODY_RX, k.ry, rng(o.seed, "body"), boil), bw = 12 + boil();
  const top = o.top || { style: "plain" };
  p.poly(body, top.color || o.color, bw);
  if (top.style !== "plain" || top.number) {
    g.save(); p.path(body, true); g.clip();
    topDetails(p, cos, top, k);
    if (top.number) chestNumber(p, cos, top.number, k, (o.facing === "left") !== !!o.mirrored);
    g.restore();
    p.poly(body, null, bw); // outline back over the details' edges
  }

  // arms and dot hands over the body; a held prop sits in its hand, under the hand dot
  k.arms.forEach(([shp, elbow, hand], i) => {
    p.stroke(jitter([shp, elbow, hand], boil), 9);
    for (const pr of o.props || []) {
      if ((pr.hand === "left" ? 0 : 1) === i) drawProp(p, cos, pr.kind, hand, k.fore[i], i ? 1 : -1);
    }
    p.dot(hand[0], hand[1], 15);
  });

  // head last: wobbly white circle, thick outline, sits on the body (raised arms go behind it)
  const [hx, hy] = k.head;
  const headPts = wobble(hx, hy, HEAD_R, HEAD_R * HEAD_SQUASH, rng(o.seed, "head"), boil);
  p.poly(headPts, "#ffffff", 14 + boil() * 1.5);
  face(p, boil, o, hx + 26 * look, hy, look);
  if (o.headwear && o.headwear.kind !== "none") headwear(p, cos, o.headwear, headPts, hx, hy, look);
}

// --- costumes (flat colour, thick outline, marker jitter; all in unrotated canvas px) ---
const OL = 8;                                   // costume outline width
const HOLD = [deg(22), deg(108)];               // seated prop arm: upper arm angle, forearm bend (right arm)
const rect = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];

/** tube along a leg from fraction f0 to f1 of hip -> foot, half-width w0 -> w1; ragged: zigzag hem */
export function legTube([hip, foot], f0, f1, w0, w1, ragged = false) {
  const dx = foot[0] - hip[0], dy = foot[1] - hip[1], L = Math.hypot(dx, dy), ux = dx / L, uy = dy / L;
  const P = (f, w) => [hip[0] + dx * f - uy * w, hip[1] + dy * f + ux * w]; // w > 0: one side, < 0: the other
  const teeth = ragged ? 5 : 1, hem = [];
  for (let i = 0; i <= teeth * 2; i++) { // hem from +w1 to -w1; ragged teeth point down the leg
    const w = w1 - (2 * w1 * i) / (teeth * 2), f = f1 + (ragged && i % 2 ? 14 / L : 0);
    if (ragged || i === 0 || i === teeth * 2) hem.push(P(f, w));
  }
  return [P(f0, w0), ...hem, P(f0, -w0)];
}

function legwear(p, cos, lw, legs) {
  const tubes = legs.map((leg) => jitter(lw.kind === "trousers" ? legTube(leg, -0.08, 0.96, 30, 17)
    : legTube(leg, -0.08, 0.42, 31, 27, lw.kind === "ragged_shorts"), cos, 1.5));
  // outlines first, then fills: the two tubes merge into one garment with a single outer outline
  for (const t of tubes) p.poly(t, null, OL * 2);
  for (const t of tubes) p.poly(t, lw.color, 0);
}

function topDetails(p, cos, top, k) {
  const x = CW / 2, t = k.top, J = (pts, a = 1.5) => jitter(pts, cos, a);
  if (top.style === "suit") {
    p.poly(J([[x - 40, t + 10], [x + 40, t + 10], [x, t + 132]]), "#ffffff", 6);           // shirt V
    if (top.accent_color) {                                                                 // tie: knot, blade
      p.poly(J([[x - 11, t + 30], [x + 11, t + 30], [x + 8, t + 48], [x - 8, t + 48]], 1), top.accent_color, 5);
      p.poly(J([[x - 8, t + 48], [x + 8, t + 48], [x + 15, t + 108], [x, t + 126], [x - 15, t + 108]], 1),
        top.accent_color, 5);
    }
    for (const s of [-1, 1]) {                                                              // lapels
      p.poly(J([[x + s * 40, t + 8], [x + s * 70, t + 62], [x + s * 50, t + 74], [x + s * 2, t + 134]]), top.color, 7);
    }
    for (const y of [t + 170, t + 215]) p.dot(x, y, 8);                                     // buttons
  } else if (top.style === "tank") {
    p.poly(J(ellPts(x, t + 6, 50, 64, 0, 360, 0, 24)), "#ffffff", 7);                       // scoop neck
    for (const s of [-1, 1]) p.poly(J(ellPts(x + s * 96, t + 74, 30, 60, 0, 360, 0, 24)), "#ffffff", 7); // armholes
  } else if (top.style === "shirt") {
    p.stroke(J([[x, t + 34], [x, k.cy + k.ry - 16]]), 5);                                   // button line
    for (const f of [0.3, 0.5, 0.7]) p.dot(x + 9, t + 34 + (k.cy + k.ry - 50 - t) * f, 6);
    for (const s of [-1, 1]) p.poly(J([[x + s * 3, t + 24], [x + s * 48, t + 14], [x + s * 30, t + 62]]), top.color, 7);
  }
}

// bold rounded digits: polylines in a 0..1 box (x right, y down)
const ring = (cx, cy, rx, ry) => ellPts(cx, cy, rx, ry, 0, 360, 0, 16);
const SIX = [[[0.8, 0.05], [0.42, 0.1], [0.14, 0.45], [0.12, 0.78], [0.35, 1], [0.68, 1], [0.9, 0.78], [0.86, 0.56],
  [0.58, 0.44], [0.28, 0.48], [0.13, 0.64]]];
export const DIGITS = {
  0: [ring(0.5, 0.5, 0.42, 0.5)],
  1: [[[0.28, 0.2], [0.56, 0], [0.56, 1]]],
  2: [[[0.12, 0.25], [0.3, 0.04], [0.6, 0], [0.86, 0.16], [0.85, 0.38], [0.1, 1], [0.92, 1]]],
  3: [[[0.1, 0.06], [0.86, 0.04], [0.45, 0.42], [0.8, 0.54], [0.9, 0.78], [0.66, 0.98], [0.3, 1], [0.08, 0.86]]],
  4: [[[0.7, 1], [0.7, 0], [0.06, 0.7], [0.95, 0.7]]],
  5: [[[0.88, 0], [0.2, 0], [0.13, 0.42], [0.5, 0.36], [0.85, 0.5], [0.9, 0.75], [0.66, 0.98], [0.3, 1], [0.08, 0.86]]],
  6: SIX,
  7: [[[0.08, 0], [0.92, 0], [0.4, 1]]],
  8: [ring(0.5, 0.24, 0.32, 0.24), ring(0.5, 0.73, 0.4, 0.27)],
  9: SIX.map((s) => s.map(([x, y]) => [1 - x, 1 - y])),
};

/** chest number: black hand-lettered digits on a small white bib; flip: drawn mirrored so it reads on screen */
function chestNumber(p, cos, num, k, flip) {
  const GW = 30, GH = 46, GAP = 10, n = num.length, w = n * GW + (n - 1) * GAP;
  const cx = CW / 2, cy = k.top + 128;
  p.poly(jitter(rect(cx - w / 2 - 18, cy - GH / 2 - 15, cx + w / 2 + 18, cy + GH / 2 + 15), cos, 2), "#ffffff", 6);
  [...num].forEach((d, i) => {
    const x0 = cx - w / 2 + i * (GW + GAP);
    for (const s of DIGITS[d]) {
      const pts = s.map(([u, v]) => [x0 + u * GW, cy - GH / 2 + v * GH]).map(([x, y]) => [flip ? 2 * cx - x : x, y]);
      p.stroke(jitter(pts, cos, 1), 9);
    }
  });
}

/** prop in a hand: local shapes (hand at 0,0, y down, x away from the body) turned partly with the forearm */
function drawProp(p, cos, kind, hand, fore, side) {
  const th = -fore * 0.35, c = Math.cos(th), s = Math.sin(th);
  const T = (pts) => jitter(pts.map(([x, y]) => [hand[0] + x * side * c - y * s, hand[1] + x * side * s + y * c]), cos, 1.2);
  const poly = (pts, fill, w = OL) => p.poly(T(pts), fill, w), line = (pts, w) => p.stroke(T(pts), w);
  const circ = (x, y, r) => ellPts(x, y, r, r, 0, 360, 0, 20);
  if (kind === "clipboard") {
    poly(rect(-6, -48, 74, 58), "#a8743a");
    poly(rect(4, -30, 64, 50), "#fbf8ef", 4);
    poly(rect(22, -56, 46, -40), "#9e9e9e", 6);
    for (const [y, x1] of [[-14, 56], [2, 56], [18, 46]]) line([[12, y], [x1, y]], 4);
  } else if (kind === "stopwatch") {
    poly(rect(2, -66, 14, -54), "#cfd3d6", 6);
    poly(circ(8, -26, 30), "#cfd3d6");
    poly(circ(8, -26, 20), "#ffffff", 4);
    line([[8, -26], [17, -38]], 4);
  } else if (kind === "bottle") {
    poly(rect(-7, -96, 7, -68), "#7fb8d6", 7);
    poly(rect(-9, -108, 9, -96), "#d84a3a", 6);
    poly(rect(-15, -72, 15, 22), "#7fb8d6");
    poly(rect(-15, -42, 15, -14), "#ffffff", 4);
  } else if (kind === "syringe") {
    line([[-10, 0], [-36, 0]], 7); line([[-36, -13], [-36, 13]], 7);
    poly(rect(-10, -12, 70, 12), "#eef6f8", 7);
    poly(rect(22, -6, 66, 6), "#e05656", 0);
    line([[-4, -22], [-4, 22]], 6);
    line([[70, 0], [106, 0]], 3);
  } else if (kind === "apple") {
    line([[6, -48], [10, -66]], 6);
    poly(ellPts(24, -62, 13, 6, 0, 360, -30, 12), "#4f9a3a", 5);
    poly(circ(6, -24, 27), "#d93a2b");
  } else if (kind === "medal") {
    poly(rect(-12, -4, 12, 48), "#2f5fb3", 6);
    poly(circ(0, 70, 24), "#e8b923");
    poly(circ(0, 70, 13), null, 4);
  }
}

const HAT_GRIP = 8; // px the band reaches past the head outline per side

/** where a hat sits on this (wobbly, boiling) head outline: brim y and the outline's x extent at that height */
export function hatFit(headPts, hy) {
  const brim = hy - HAT_BRIM, xs = [];
  headPts.forEach(([x0, y0], i) => {
    const [x1, y1] = headPts[(i + 1) % headPts.length];
    if ((y0 - brim) * (y1 - brim) <= 0 && y0 !== y1) xs.push(x0 + ((brim - y0) / (y1 - y0)) * (x1 - x0));
  });
  return { brim, xl: Math.min(...xs), xr: Math.max(...xs) };
}

/** headwear pulled down onto the wobbly head: sized from the head's own boiling outline, so it bobs and boils with
 *  it. Peaks point the way the figure faces (look 1) or show from the front (look 0). */
function headwear(p, cos, hw, headPts, hx, hy, look) {
  const J = (pts, a = 1.5) => jitter(pts, cos, a), col = hw.color;
  const { brim, xl: hl, xr: hr } = hatFit(headPts, hy), xl = hl - HAT_GRIP, xr = hr + HAT_GRIP;
  const mid = (xl + xr) / 2, half = (xr - xl) / 2;
  if (hw.kind === "flat_cap") {
    // crown hugs the head's top outline, pushed out a little; the band edge closes it below the outline
    const crown = headPts.map(([x, y]) => [hx + (x - hx) * 1.07, hy + (y - hy) * 1.07]).filter(([, y]) => y < brim - 4);
    p.poly([[xl, brim + 2], ...crown, [xr, brim + 2]], col, OL + 2);
    if (look) p.poly(J([[xr - 24, brim - 8], [xr + 70, brim + 2], [xr + 62, brim + 12], [xr - 30, brim + 4]]), col, OL);
    else p.poly(J(ellPts(mid, brim - 2, half + 4, 10, 0, 180, 0, 14)), col, OL);
  } else if (hw.kind === "postman_cap") {
    const f = 6 * look;
    p.poly(J([[xl, brim + 2], [xr, brim + 2], [xr + 10 + f, hy - 178], [xl - 10 + f, hy - 176]]), col, OL + 2);
    p.stroke(J([[xl + 2, brim - 26], [xr - 2, brim - 26]]), 6);                            // band
    p.dot(mid + 60 * look, brim - 50, 11, "#c9a227");                                      // badge
    if (look) p.poly(J([[xr - 24, brim - 6], [xr + 66, brim + 4], [xr + 58, brim + 14], [xr - 30, brim + 6]]), INK, 6);
    else p.poly(J(ellPts(mid, brim - 2, half, 10, 0, 180, 0, 14)), INK, 6);                // visor
  } else if (hw.kind === "bowler") {
    p.poly(J(ellPts(mid, brim, half + 34, 14, 0, 360, 0, 24)), col, OL);
    p.poly(J(ellPts(mid, brim - 2, half + 2, 90, 180, 360, 0, 20)), col, OL + 2);
    p.stroke(J([[mid - half + 4, brim - 16], [mid + half - 4, brim - 16]]), 6);
  } else if (hw.kind === "straw_hat") {
    p.poly(J(ellPts(mid, brim, half + 96, 26, 0, 360, 0, 28)), col, OL);
    p.poly(J([[xl, brim - 2], [xl + 8, hy - 168], [xr - 8, hy - 168], [xr, brim - 2]]), col, OL + 2);
    p.poly(J([[xl + 1, brim - 4], [xl + 3, brim - 30], [xr - 3, brim - 30], [xr - 1, brim - 4]]), "#3b2a1a", 5);
  }
}

function face(p, boil, o, fx, hy, look) {
  const w = (k) => Math.min(FACE[k][0] * FACE_MAX, Math.max(FACE[k][0], FACE[k][1] / (o.px || 1)));
  const ex = [fx - 50, fx + 50], ey = hy - 8;
  const expr = o.expression || "neutral";
  const big = expr === "surprised" || o.action === "react";
  // expression overrides the base eye style; blinks win over everything
  const kind = o.lid >= 1 ? "closed" : o.lid === 0.5 ? "half"
    : expr === "surprised" ? "round"                      // wide open, small pupils, for every character
    : expr === "sleepy" ? "half"                          // flat lids
    : expr === "exhausted" ? "heavy"                      // lids drooping low over the pupils
    : expr === "happy" && o.eyes === "half_closed" ? "arc" // soft upward arcs; dot eyes keep their dots
    : o.eyes === "half_closed" ? "half" : "round";
  for (const x of ex) {
    if (kind === "closed") {
      p.stroke(jitter(ellPts(x, ey - 6, 26, 10, 20, 160, 0, 12), boil, 1.5), w("eye"));  // blink: closed
    } else if (kind === "arc") {
      p.stroke(jitter(ellPts(x, ey + 10, 26, 18, 200, 340, 0, 12), boil, 1.5), w("eye")); // happy: upward arc
    } else if (kind === "heavy") {
      p.poly(ellPts(x, ey, 29, 27, -8, 188, 0, 16), "#ffffff", w("eyeRim"));        // lower half of the eye
      p.dot(x + 6 * look, ey + 12, w("pupil") * 0.85);                                  // pupil under the lid
      p.stroke(jitter([[x - 32, ey - 2], [x, ey + 1], [x + 32, ey + 4]], boil, 1.5), w("eye") * 1.6); // heavy lid
    } else if (kind === "half") {
      p.poly(ellPts(x + 4 * look, ey, 15, 13, 0, 180, 0, 12), "#1c1a1a", 0);           // pupil under the lid
      p.stroke(jitter([[x - 28, ey], [x + 28, ey]], boil, 1.5), w("eye"));             // lid line
    } else {
      const r = big ? 36 : 30;
      p.poly(ellPts(x, ey, r, r, 0, 360, 0, 28), "#ffffff", w("eyeRim"));
      p.dot(x + 8 * look, ey + 2, w("pupil") * (big ? 0.75 : 1));
    }
  }
  // bold curved brows
  const B = BROWS[expr] || BROWS.neutral, sides = Array.isArray(B[0]) ? B : [B, B];
  const by = ey - (big ? 64 : expr === "sleepy" || expr === "exhausted" ? 44 : 54);
  for (const [x, side, [outer, inner, arch]] of [[ex[0], -1, sides[0]], [ex[1], 1, sides[1]]]) {
    const o0 = [x + side * 34, by + outer], i0 = [x - side * 30, by + inner];
    const c = [(o0[0] + i0[0]) / 2, Math.min(o0[1], i0[1]) - arch * 2];
    p.stroke(jitter(quad(o0, c, i0), boil, 1.2), w("brow"));
  }
  // small mouth line; talking opens it
  const mx = fx + 4 * look, my = hy + 74;
  if ((o.mouth || 0) > 0.05) {
    p.poly(ellPts(mx, my, 20, 4 + 18 * o.mouth, 0, 360, 0, 20), "#1c1a1a", 0);
    return;
  }
  const M = {
    neutral: [[mx - 22, my], [mx + 22, my]],
    happy: ellPts(mx, my - 14, 28, 18, 25, 155, 0, 12),
    sad: ellPts(mx, my + 14, 26, 12, 205, 335, 0, 12),
    angry: [[mx - 20, my + 5], [mx, my - 1], [mx + 20, my + 5]],
    sleepy: [[mx - 12, my], [mx + 12, my]],
    cheeky: quad([mx - 22, my + 2], [mx + 2, my + 14], [mx + 28, my - 12]), // lopsided grin
  };
  if (expr === "exhausted") p.poly(ellPts(mx, my + 2, 11, 9, 0, 360, 0, 16), "#1c1a1a", 0); // small open mouth
  else if (expr === "surprised") p.poly(ellPts(mx, my, 12, 15, 0, 360, 0, 20), null, w("mouth") * 0.9);
  else p.stroke(jitter(M[expr] || M.neutral, boil, 1.2), w("mouth"));
}
