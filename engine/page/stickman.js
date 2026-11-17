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
// gesture targets [left angle, left bend, right angle, right bend, shoulder lift px]
const GESTURES = {
  palm: [-ARM_REST, 0, 40, 60, 0],     // right forearm out, open palm toward the listener
  chin: [-ARM_REST, 0, 70, 70, 0],     // small point at chin height
  shrug: [-40, -110, 40, 110, 10],      // both forearms up and out, shoulders up
};
const TAU = Math.PI * 2;
const deg = (d) => (d * Math.PI) / 180;

/** Tallest standing figure, feet to the highest point the head outline can reach (full breath, max wobble),
 *  in canvas px. main.js turns it into world units for framing; derived from the constants the drawing uses. */
export const FIGURE_PX = (() => {
  const hip = FEET_Y - LEG * Math.cos(deg(IDLE_LEG)), ry = BODY_RY * (1 + BREATH);
  const headCy = hip + HIP_OVERLAP - 2 * ry - HEAD_R + NECK_OVERLAP;
  return FEET_Y - (headCy - HEAD_R * HEAD_SQUASH * (1 + LUMP * LUMP_SUM + JIT));
})();

// brows per expression: [outer dy, inner dy, arch] (negative = up)
const BROWS = {
  neutral: [0, 0, 8], happy: [-6, -8, 12], sad: [10, -16, 4],
  angry: [-8, 16, 0], surprised: [-12, -12, 14], sleepy: [5, 5, 2],
};

/** closed wobbly loop: stable per-character lumps (shape) + small per-boil jitter (boil) */
function wobble(cx, cy, rx, ry, shape, boil, lump = LUMP, jit = JIT, n = 44) {
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
const jitter = (pts, boil, amp = 2.5) => {
  const d = [boil(), boil(), boil(), boil()].map((v) => amp * (v * 2 - 1)), n = Math.max(1, pts.length - 1);
  return pts.map(([x, y], i) => [x + d[0] + ((d[2] - d[0]) * i) / n, y + d[1] + ((d[3] - d[1]) * i) / n]);
};
const at = ([x, y], ang, len) => [x + Math.sin(ang) * len, y + Math.cos(ang) * len]; // ang from straight down, + toward +x
const quad = (a, c, b, n = 10) => Array.from({ length: n + 1 }, (_, i) => {
  const t = i / n, s = 1 - t;
  return [s * s * a[0] + 2 * s * t * c[0] + t * t * b[0], s * s * a[1] + 2 * s * t * c[1] + t * t * b[1]];
});

/**
 * o: { seed, boil, color, eyes: "dots"|"half_closed", expression, action, phase (walk cycles), lid (0 | 0.5 | 1),
 *      mouth (0..1 open), breath (-1..1), facing: "left"|"right"|"camera", t (seconds),
 *      px (screen px per canvas px; face strokes keep a minimum on-screen width, default 1),
 *      bob (0..1 stressed-word lift), gesture ({ kind: palm|chin|shrug, k: 0..1 } while talking),
 *      pointK (0..1 point arm raised, default 1) }
 */
export function drawStickman(canvas, o) {
  const g = canvas.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, CW, CH);
  if (o.facing === "left") g.setTransform(-1, 0, 0, 1, CW, 0);
  const p = new Pen(g, INK);
  const boil = rng(o.seed, "boil", o.boil);
  const look = o.facing === "camera" ? 0 : 1;
  const moving = o.action === "walk" || o.action === "run";
  const run = o.action === "run";

  // whole-figure lean about the feet
  const lean = run ? deg(9) : o.action === "react" ? deg(-6) : o.action === "walk" ? deg(3) : 0;
  g.translate(CW / 2, FEET_Y); g.rotate(lean); g.translate(-CW / 2, -FEET_Y);

  // legs: walk phase drives the swing; hip height = FEET_Y - LEG cos(angle). A stressed-word bob lifts the hips;
  // the legs reach down to the same planted feet.
  const s = Math.sin(TAU * (o.phase || 0));
  const A = moving ? deg(run ? 34 : 24) * s : deg(IDLE_LEG);
  const hipBase = FEET_Y - LEG * Math.cos(A), hipY = hipBase - BOB_PX * (o.bob || 0);
  for (const [dx, a] of [[-18, -A], [18, A]]) {
    p.stroke(jitter([[CW / 2 + dx, hipY], at([CW / 2 + dx, hipBase], a, LEG)], boil), 10);
  }

  // body: flat outfit-colour blob, breathing scales its height from the hips up
  const ry = BODY_RY * (1 + BREATH * (o.breath || 0)), cy = hipY + HIP_OVERLAP - ry, top = cy - ry;
  p.poly(wobble(CW / 2, cy, BODY_RX, ry, rng(o.seed, "body"), boil), o.color, 12 + boil());

  // arms (screen angles from straight down, + toward +x) and dot hands, over the body
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
  } else if (o.action === "react") {
    aL = deg(-128); aR = deg(128); bendL = deg(-25); bendR = deg(25); // hands up beside the head
  } else {
    aL -= deg(2) * (o.breath || 0); aR += deg(2) * (o.breath || 0);
  }
  const sh = top + 58 - lift, shL = [CW / 2 - 66, sh], shR = [CW / 2 + 66, sh];
  for (const [shp, a, bend] of [[shL, aL, bendL], [shR, aR, bendR]]) {
    const elbow = at(shp, a, ARM * 0.52), hand = at(elbow, a + bend, ARM * 0.48);
    p.stroke(jitter([shp, elbow, hand], boil), 9);
    p.dot(hand[0], hand[1], 15);
  }

  // head last: wobbly white circle, thick outline, sits on the body (raised arms go behind it)
  const hx = CW / 2 + (o.action === "react" ? -10 : 0), hy = top - HEAD_R + NECK_OVERLAP;
  p.poly(wobble(hx, hy, HEAD_R, HEAD_R * HEAD_SQUASH, rng(o.seed, "head"), boil), "#ffffff", 14 + boil() * 1.5);
  face(p, boil, o, hx + 26 * look, hy, look);
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
    : expr === "happy" && o.eyes === "half_closed" ? "arc" // soft upward arcs; dot eyes keep their dots
    : o.eyes === "half_closed" ? "half" : "round";
  for (const x of ex) {
    if (kind === "closed") {
      p.stroke(jitter(ellPts(x, ey - 6, 26, 10, 20, 160, 0, 12), boil, 1.5), w("eye"));  // blink: closed
    } else if (kind === "arc") {
      p.stroke(jitter(ellPts(x, ey + 10, 26, 18, 200, 340, 0, 12), boil, 1.5), w("eye")); // happy: upward arc
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
  const [outer, inner, arch] = BROWS[expr] || BROWS.neutral;
  const by = ey - (big ? 64 : expr === "sleepy" ? 44 : 54);
  for (const [x, side] of [[ex[0], -1], [ex[1], 1]]) {
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
  };
  if (expr === "surprised") p.poly(ellPts(mx, my, 12, 15, 0, 360, 0, 20), null, w("mouth") * 0.9);
  else p.stroke(jitter(M[expr] || M.neutral, boil, 1.2), w("mouth"));
}
