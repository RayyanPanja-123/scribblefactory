// Our stickman (docs/brief.md "Stickman style"), drawn on a 1024 x 1024 canvas (wide so held props fit; the body uses the middle 512), feet at y = FEET_Y.
// Pure function of its options: same options -> same pixels. Facing "right" is the base drawing;
// "left" is the same drawing mirrored; "camera" looks straight out.
import { Pen, ellPts } from "./borrowed.js";
import { lookup } from "./library.js";
import { rng } from "./rng.js";
import { STYLE } from "./style.js";
import { BUILTIN_WARDROBE, HEAD_ANCHORS, layerFill, layerPoints, slotValue, wearing } from "./wardrobe.js";

export const CW = 1024, CH = 1024, FEET_Y = 1000;
export const BODY_W = 512; // the figure's own width on the card: framing and set-prop hiding measure this, not CW
const INK = "#1c1a1a";
export const HEAD_R = 150;
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
// 5c-6 poses (degrees): carried arms over the holders' shoulders (upper arm, forearm bend: forearms hang down),
// a holder's inner arm at the held actor's shoulder, give / receive arm held out, knee buckle splay at full dip
const OVER_SHOULDER = [122, -77], HOLD_ARM = [68, 35], GIVE_ARM = [80, -10], BUCKLE = 16;
// crowd moods (cast members can take them too): cheer arms up in a V, angry fists up beside the head, gasp hands
// to the cheeks; o.mood { k 0..1, shake -1..1 } animates them (extras.js moodAt)
const CHEER_ARM = 138, FIST = [105, 60], SHAKE = 10; // cheer: hands stay outside the head outline
const MOODS = new Set(["cheer", "angry", "gasp"]);
const GAITS = new Set(["walk", "run", "stagger", "carry", "support", "supported", "carried"]);
const LOOSE = new Set(["stagger", "supported"]); // wobbly gait, loose arms
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));

// headwear: the band's lower edge sits HAT_BRIM above the head centre (forehead, just over the neutral brows) and
// reaches past the head outline on both sides; nothing rises more than HAT_TOP above the head centre
export const HAT_BRIM = 88, HAT_TOP = 192;

// A humanoid creature's build (creatures.json rig "humanoid", schema HumanoidBuild): factors of the default human's
// proportions, and its head colour. {} / undefined is the default human.
const DEFAULT_BUILD = { head: 1, body_w: 1, body_h: 1, leg: 1, arm: 1, head_color: "#ffffff" };
/** canvas px sizes of a build (before fitting the card) */
export function sizes(build) {
  const b = { ...DEFAULT_BUILD, ...build };
  return { b, head: b.head, headR: HEAD_R * b.head, rx: BODY_RX * b.body_w, ry: BODY_RY * b.body_h, leg: LEG * b.leg,
    arm: ARM * b.arm, sh: 66 * b.body_w };
}
const tallest = (S) => { // feet to the highest point the head or any headwear can reach (full breath, bob, max wobble)
  const hip = FEET_Y - S.leg * Math.cos(deg(IDLE_LEG)), ry = S.ry * (1 + BREATH);
  const headCy = hip - BOB_PX + HIP_OVERLAP - 2 * ry - S.headR + NECK_OVERLAP * S.head;
  return FEET_Y - (headCy - S.head * Math.max(HEAD_R * HEAD_SQUASH * (1 + LUMP * LUMP_SUM + JIT), HAT_TOP));
};
const CARD_TOP = FEET_Y - 8; // a build taller than this is drawn smaller (scaled about the feet) to fit the card
/** scale a build is drawn at to fit the card (1 for every build up to the card height) */
export const fitOf = (build) => Math.min(1, CARD_TOP / tallest(sizes(build)));
/** Tallest standing figure of a build in canvas px, fitted to the card. main.js turns it into world units for framing. */
export const figurePx = (build) => tallest(sizes(build)) * fitOf(build);
export const FIGURE_PX = figurePx();
/** standing hip height on the card (canvas px), fitted: car.js seats riders by it */
export const hipPx = (build) => FEET_Y - sizes(build).leg * Math.cos(deg(IDLE_LEG)) * fitOf(build);

// brows per expression: [outer dy, inner dy, arch] (negative = up)
const BROWS = {
  neutral: [0, 0, 8], happy: [-6, -8, 12], cheer: [-8, -10, 14], sad: [10, -16, 4],
  angry: [-8, 16, 0], surprised: [-12, -12, 14], sleepy: [5, 5, 2],
  cheeky: [[4, 4, 3], [-12, -8, 12]], // [left brow, right brow]: one brow up
  exhausted: [16, 0, 2],                // droopy: outer ends sag
  worried: [4, -12, 5],                 // inner ends lift: anxious brow
  dead: [6, 6, 0],                      // flat, slack
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
 *  feet when drawing). legs: [[hip, foot] x2], knees: [knee x2] when a custom pose bends them (else null), arms: [[shoulder, elbow, hand] left (-x), right (+x)], fore: forearm
 *  angles, head: [hx, hy]. */
// built-in knee bends (degrees): the swinging leg of a gait folds (the standing one stays straight, so the hips
// don't bob), knees give in a buckle (stagger dip, collapse), a cheer crouches between hops, a fright flinches
const GAIT_KNEE = { walk: 40, run: 85, stagger: 30, carry: 30, support: 30, supported: 25 };
const BUCKLE_KNEE = 45, CHEER_CROUCH = 30, FLINCH = { react: 14, gasp: 8 }, PEDAL_KNEE = [30, 35];
function builtinKnees(o, act, s, buckle) {
  const c = Math.cos(TAU * (o.phase || 0)), k = [0, 0];
  if (act === "carried") {
    // A dead person is limp while being carried: keep the carried leg pose still instead of pedalling.
    const pedal = o.expression === "dead" ? 0 : c;
    k[0] = PEDAL_KNEE[0] + PEDAL_KNEE[1] * Math.max(0, -pedal);
    k[1] = PEDAL_KNEE[0] + PEDAL_KNEE[1] * Math.max(0, pedal);
  }
  else if (GAIT_KNEE[act] && o.facing !== "camera") { // the leg swinging forward lifts its foot
    k[0] = GAIT_KNEE[act] * Math.max(0, -c); k[1] = GAIT_KNEE[act] * Math.max(0, c);
  }
  const extra = BUCKLE_KNEE * Math.min(1, buckle) + CHEER_CROUCH * (o.mood && act === "cheer" ? o.mood.crouch || 0 : 0)
    + (FLINCH[act] || 0);
  return k.map((v) => deg(v + extra));
}

export function skeleton(o) {
  const S = sizes(o.build), LEG = S.leg, ARM = S.arm;
  const act = o.action, moving = GAITS.has(act), run = act === "run";
  const st = o.stagger || { sway: 0, buckle: 0 }; // stagger / supported: sideways sway and knee dips
  let lean = run ? deg(9) : act === "react" ? deg(-6) : act === "walk" || act === "carry" || act === "support" ? deg(3) : 0;
  if (LOOSE.has(act)) lean = deg(4) + deg(8) * st.sway;
  // legs: gait phase drives the swing; a buckle (stagger dip, collapse) splays both legs outward so the hips drop.
  // The more upright leg stands on FEET_Y. A stressed-word bob lifts the hips; the legs reach the same planted feet.
  const phase = act === "carried" && o.expression === "dead" ? 0 : (o.phase || 0);
  const s = Math.sin(TAU * phase);
  const swing = run ? 34 : act === "carried" ? 30 : LOOSE.has(act) ? 18 : 24;
  const A = moving ? deg(swing) * s : deg(IDLE_LEG), B = deg(BUCKLE) * Math.min(1, (o.buckle || 0) + st.buckle);
  const C = o.custom; // a custom action's pose (actions.js customPose): degrees, + toward +x
  const legA = C ? C.legs.map(deg) : [-A - B, A + B];
  if (C) lean = deg(C.lean);
  lean += deg(o.shift || 0); // idle weight shift (main.js, style.js idle): a slow sway about the feet
  // knees: thigh and shin are half a leg each. Side on, the shin folds back (toward -x) by the knee bend; facing the
  // camera the knees bend outward (the thighs splay by half the bend, the shins fold back in: a front-view squat).
  // The leg that reaches lowest stands on FEET_Y (a straight leg: LEG * cos, as before).
  const kneeA = C ? (C.knees ?? [0, 0]).map(deg) : builtinKnees(o, act, s, B / deg(BUCKLE)), bent = kneeA.some((v) => v);
  const fold = o.facing === "camera" ? [1, -1] : [-1, -1]; // which way each shin turns from its thigh
  if (o.facing === "camera") for (const i of [0, 1]) legA[i] -= (fold[i] * kneeA[i]) / 2;
  const shinA = (i) => legA[i] + fold[i] * kneeA[i];
  const reach = (i) => (LEG / 2) * (Math.cos(legA[i]) + Math.cos(shinA(i)));
  const hipBase = FEET_Y - Math.max(reach(0), reach(1)), hipY = hipBase - BOB_PX * (o.bob || 0);
  const kneeAt = (dx, i) => { const [x, y] = at([CW / 2 + dx, hipBase], legA[i], LEG / 2); return [x, y + (hipY - hipBase) / 2]; };
  const knees = bent ? [kneeAt(-18, 0), kneeAt(18, 1)] : null;
  // custom poses: 0 straight .. 1 from a 30 degree knee, the lean bends at the hips (built-ins lean about the feet)
  const hinge = C ? Math.min(1, Math.max(...kneeA) / deg(30)) : 0;
  const legs = [[-18, 0], [18, 1]].map(([dx, i]) => [[CW / 2 + dx, hipY],
    at(at([CW / 2 + dx, hipBase], legA[i], LEG / 2), shinA(i), LEG / 2)]);
  // body: breathing scales its height from the hips up
  const ry = S.ry * (1 + BREATH * (o.breath || 0)), cy = hipY + HIP_OVERLAP - ry, top = cy - ry;

  // arms (screen angles from straight down, + toward +x)
  let lift = 0, aL = deg(-ARM_REST), aR = deg(ARM_REST), bendL = 0, bendR = 0;
  const arm = (side, a, bend, k = 1) => { // blend one arm (side -1 left, +1 right) toward angle a / bend (radians)
    if (side > 0) { aR += (a - aR) * k; bendR += (bend - bendR) * k; } else { aL += (a - aL) * k; bendL += (bend - bendL) * k; }
  };
  if (C) {
    [[aL, bendL], [aR, bendR]] = C.arms.map((arm) => arm.map(deg));
  } else if (LOOSE.has(act)) { // loose arms, swinging out of step with each other
    const ph = TAU * 0.5 * (o.phase || 0);
    aL = deg(-24) + deg(16) * Math.sin(ph + 1) + deg(10) * st.sway; bendL = deg(-20);
    aR = deg(24) + deg(16) * Math.sin(ph + 2.4) + deg(10) * st.sway; bendR = deg(20);
  } else if (act === "carried") {
    aL = -deg(OVER_SHOULDER[0]); bendL = -deg(OVER_SHOULDER[1]); aR = deg(OVER_SHOULDER[0]); bendR = deg(OVER_SHOULDER[1]);
  } else if (act === "collapse") { // arms fly up as the knees go
    const k = o.buckle || 0;
    aL = deg(-ARM_REST - 50 * k); aR = deg(ARM_REST + 50 * k); bendL = deg(-30 * k); bendR = deg(30 * k);
  } else if (act === "lie") {
    aL = deg(-8); aR = deg(8);
  } else if (act === "cheer") {
    const k = o.mood ? o.mood.k : 1;
    aL += (-deg(CHEER_ARM) - aL) * k; aR += (deg(CHEER_ARM) - aR) * k;
  } else if (act === "angry") {
    const sh = deg(SHAKE) * (o.mood ? o.mood.shake : 0);
    aL = -deg(FIST[0]); bendL = -deg(FIST[1]) + sh; aR = deg(FIST[0]); bendR = deg(FIST[1]) - sh;
  } else if (moving) {
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
  } else if (!["carried", "collapse", "lie", "stagger", "supported", ...MOODS].includes(act)) {
    aL -= deg(2) * (o.breath || 0); aR += deg(2) * (o.breath || 0);
  }
  // one arm toward a partner: o.reach { side, k }. Holders hold the held actor's shoulder; the supported drapes
  // an arm over its supporter; give / receive hold an arm out
  if (o.reach) {
    const { side, k = 1 } = o.reach;
    if (act === "carry" || act === "support") arm(side, side * deg(HOLD_ARM[0]), side * deg(HOLD_ARM[1]), k);
    else if (act === "supported") arm(side, side * deg(OVER_SHOULDER[0] - 7), side * deg(OVER_SHOULDER[1] + 7), k);
    else arm(side, side * deg(GIVE_ARM[0]), side * deg(GIVE_ARM[1]), k);
  }
  // seated in the car (legs and low hands hidden by the side panel): each prop hand comes up to the chest,
  // unless that arm is waving
  if (o.seated) for (const pr of o.props || []) {
    if (pr.hand === "left") { aL = -HOLD[0]; bendL = -HOLD[1]; } else if (o.action !== "wave") { aR = HOLD[0]; bendR = HOLD[1]; }
  }
  const sh = top + 58 - lift;
  const arms = [[[CW / 2 - S.sh, sh], aL, bendL], [[CW / 2 + S.sh, sh], aR, bendR]].map(([shp, a, bend]) => {
    const elbow = at(shp, a, ARM * 0.52);
    return [shp, elbow, at(elbow, a + bend, ARM * 0.48)];
  });
  const hs = S.head, head = [CW / 2 + (o.action === "react" ? -10 : 0), top - S.headR + NECK_OVERLAP * hs];
  // eat: the prop hand comes up to the mouth (two-joint reach); gasp: both hands to the cheeks. Those arms are drawn
  // over the head (late).
  const late = [];
  if (act === "gasp") {
    const tremble = 4 * (o.mood ? o.mood.shake : 0);
    for (const i of [0, 1]) {
      const side = i ? 1 : -1, [up, bend] = reachFor(arms[i][0], [head[0] + side * 78 * hs, head[1] + 52 * hs + tremble], side, ARM);
      const elbow = at(arms[i][0], up, ARM * 0.52);
      arms[i] = [arms[i][0], elbow, at(elbow, up + bend, ARM * 0.48)];
      if (i) { aR = up; bendR = bend; } else { aL = up; bendL = bend; }
      late.push(i);
    }
  }
  if (act === "eat" && o.eat && o.eat.k > 0) {
    const side = o.eat.side ?? 1, i = side > 0 ? 1 : 0, look = o.facing === "camera" ? 0 : 1;
    const target = [head[0] + hs * (30 * look + (look ? 18 : 30 * side)), head[1] + 104 * hs];
    const [up, bend] = reachFor(arms[i][0], target, side, ARM);
    const a0 = i ? aR : aL, b0 = i ? bendR : bendL, ua = a0 + wrap(up - a0) * o.eat.k, ub = b0 + wrap(bend - b0) * o.eat.k;
    const elbow = at(arms[i][0], ua, ARM * 0.52);
    arms[i] = [arms[i][0], elbow, at(elbow, ua + ub, ARM * 0.48)];
    if (i) { aR = ua; bendR = ub; } else { aL = ua; bendL = ub; }
    if (o.eat.k > 0.2) late.push(i);
  }
  return { lean, hinge, legs, knees, hipY, cy, ry, top, arms, fore: [aL + bendL, aR + bendR], head, late, size: S };
}

/** two-joint reach: upper arm angle and forearm bend (radians, from straight down, + toward +x) that put the hand of
 *  an arm from shoulder s on t (or as close as the arm reaches); the elbow points out to the arm's own side */
export function reachFor(s, t, side, ARM = sizes().arm) {
  const L1 = ARM * 0.52, L2 = ARM * 0.48, dx = t[0] - s[0], dy = t[1] - s[1];
  const d = Math.max(1, Math.min(Math.hypot(dx, dy), L1 + L2 - 1)), base = Math.atan2(dx, dy);
  const al = Math.acos(Math.min(1, Math.max(-1, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d))));
  const up = base - side * al, e = at(s, up, L1);
  return [up, wrap(Math.atan2(t[0] - e[0], t[1] - e[1]) - up)];
}

/**
 * o: { seed, boil, color, eyes: "dots"|"half_closed", expression, action, phase (walk cycles), lid (0 | 0.5 | 1),
 *      mouth (0..1 open), breath (-1..1), facing: "left"|"right"|"camera", t (seconds),
 *      px (screen px per canvas px; face strokes keep a minimum on-screen width, default 1),
 *      bob (0..1 stressed-word lift), gesture ({ kind: palm|chin|shrug, k: 0..1 } while talking),
 *      pointK (0..1 point arm raised, default 1), wave ({ k: 0..1 raised, swing: -1..1 } for action wave),
 *      costume (series.json cast, all optional): top { style | id, color, accent_color, number }, headwear and legwear
 *      ({ kind | id, color } or an id), hair, facial_hair, footwear, back ({ id, color } or an id), accessory, face
 *      (one or a list of up to 3): wardrobe items (wardrobe.js), props [{ kind, hand }] (max one per hand),
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
  const k = skeleton(o), S = k.size, fit = fitOf(o.build);
  const [hx, hy] = k.head;
  // custom wardrobe items (library/wardrobe.json): their own jitter stream, so built-in costumes draw as before
  const W = wearing(o), A = W.length ? anchors(k, look) : null, wcos = rng(o.seed, "wardrobe", o.boil);
  const expr = o.expression || "neutral";
  const wear = (pick) => { // every layer of the worn custom items that pick(slot, layer) accepts, in draw order
    for (const w of W) for (const L of w.item.layers) {
      if (!pick(w.slot, L) || (L.when && !L.when.includes(expr))) continue;
      for (const fr of A[L.anchor]) {
        const pts = jitter(layerPoints(L, fr), wcos, 1.2), fill = layerFill(L, w.color, w.accent);
        if (L.shape === "line") p.stroke(pts, L.width ?? OL, fill || INK); else p.poly(pts, fill, L.width ?? OL);
      }
    }
  };
  const head = (L) => HEAD_ANCHORS.has(L.anchor), lower = (slot) => slot === "legwear" || slot === "footwear";

  // a build taller than the card shrinks to fit; whole-figure lean, both about the feet
  // with bent knees (a kneel, a squat) the lean bends at the hips instead (hinge 0..1 blends it in as the knees
  // bend): the legs tip about the feet by the rest, the upper body by the hinge share about the hips
  const hipBend = k.lean * (k.hinge || 0);
  g.translate(CW / 2, FEET_Y); if (fit !== 1) g.scale(fit, fit); g.rotate(k.lean - hipBend); g.translate(-CW / 2, -FEET_Y);
  if (hipBend) { g.translate(CW / 2, k.hipY); g.rotate(hipBend); g.translate(-CW / 2, -k.hipY); }
  const planted = (draw) => { // draw the legs (and what is worn on them) without the hip bend
    if (!hipBend) return draw();
    g.save(); g.translate(CW / 2, k.hipY); g.rotate(-hipBend); g.translate(-CW / 2, -k.hipY); draw(); g.restore();
  };

  if (W.length) { // "behind" layers (long hair, capes, the back of a hood) go under everything
    wear((_, L) => L.behind && !head(L));
    g.save(); headSpace(g, hx, hy, S.head, o.tilt);
    wear((_, L) => L.behind && head(L));
    g.restore();
  }
  const lw = builtin("legwear", o.legwear);
  planted(() => {
    k.legs.forEach(([hip, foot], i) => p.stroke(jitter(k.knees ? [hip, k.knees[i], foot] : [hip, foot], boil), 10));
    if (lw) legwear(p, cos, lw, k.legs, k.knees);
    if (W.length) wear((slot, L) => !L.behind && !head(L) && lower(slot));
  });

  // body: outfit-colour blob (covers the top of the legwear), painted volume (STYLE.figure) over its details
  const body = wobble(CW / 2, k.cy, S.rx, k.ry, rng(o.seed, "body"), boil), bw = 12 + boil();
  const top = o.top ? { ...o.top, style: o.top.style ?? o.top.id ?? "plain" } : { style: "plain" };
  const light = (o.facing === "left") !== !!o.mirrored ? -1 : 1; // key light stays on screen right
  p.poly(body, top.color || o.color, 0);
  if ((BUILTIN_WARDROBE[top.style] === "top" && top.style !== "plain") || top.number) {
    g.save(); p.path(body, true); g.clip();
    topDetails(p, cos, top, k);
    if (top.number) chestNumber(p, cos, top.number, k, (o.facing === "left") !== !!o.mirrored);
    g.restore();
  }
  p.path(body, true); paintVolume(g, body, light, STYLE.figure);
  p.poly(body, null, bw);
  if (top.style === "dress") skirt(p, cos, top.color || o.color, k, o);
  if (W.length) wear((slot, L) => !L.behind && !head(L) && !lower(slot));

  // arms and dot hands over the body. A held prop sits in its hand, under the hand dot, and in front of everything
  // else (head, hair, beard): drawn after the head (held), so a tall staff never vanishes behind the figure
  const held = [];
  const drawArm = ([shp, elbow, hand], i, later = false) => {
    p.stroke(jitter([shp, elbow, hand], boil), 9);
    const pr = (o.props || []).find((x) => (x.hand === "left" ? 0 : 1) === i);
    if (pr && later) return held.push([pr, hand, i]);
    if (pr) drawProp(p, cos, pr, hand, k.fore[i], i ? 1 : -1);
    p.dot(hand[0], hand[1], 15);
  };
  k.arms.forEach((a, i) => { if (!k.late.includes(i)) drawArm(a, i, true); });

  // head last: wobbly white circle, thick outline, sits on the body (raised arms go behind it)
  // the head, face and headwear are drawn at the default size, scaled about the head centre by the build (only when
  // it differs: the extra translate pair alone shifts a leaning figure by float rounding)
  g.save();
  headSpace(g, hx, hy, S.head, o.tilt);
  const headPts = wobble(hx, hy, HEAD_R, HEAD_R * HEAD_SQUASH, rng(o.seed, "head"), boil);
  const headW = 14 + boil() * 1.5;
  p.poly(headPts, S.b.head_color, 0);
  p.path(headPts, true); paintVolume(g, headPts, light, STYLE.figure);
  p.poly(headPts, null, headW);
  face(p, boil, o, hx + 26 * look, hy, look);
  if (W.length) wear((slot, L) => !L.behind && head(L) && slot !== "headwear"); // face, facial hair, hair
  const hw = builtin("headwear", o.headwear);
  if (hw) headwear(p, cos, hw, headPts, hx, hy, look, top.accent_color);
  if (W.length) wear((slot, L) => !L.behind && head(L) && slot === "headwear");
  g.restore();
  for (const [pr, hand, i] of held) {
    drawProp(p, cos, pr, hand, k.fore[i], i ? 1 : -1);
    p.dot(hand[0], hand[1], 15);
  }
  for (const i of k.late) drawArm(k.arms[i], i); // eating / gasping: the hands come up in front of the face
  if (o.zzz != null) zzz(p, g, boil, o, hx, hy);
}

/** painted volume inside the closed shape `pts` whose path is current (S: STYLE.figure / STYLE.creature, null = flat):
 *  the light's shadow colour pooling from `shade.from` down the box toward the bottom, tilted toward the side away
 *  from the light by `shade.side` (0 = straight down), and a soft lit spot toward the key light (`light` = its side in
 *  card x, -1 or 1). Clipped to the shape; the caller draws the outline after. */
export function paintVolume(g, pts, light, S) {
  if (!S) return;
  const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), w = x1 - x0, h = y1 - y0;
  if (w < S.minSize && h < S.minSize) return; // eyes, nostrils, spots: flat
  g.save(); g.clip();
  const tip = light * (S.shade.side || 0) * w / 2, mx = x0 + w / 2;
  const sh = g.createLinearGradient(mx + tip, y0 + h * S.shade.from, mx - tip, y1);
  sh.addColorStop(0, rgba(STYLE.light.shadow, 0)); sh.addColorStop(1, rgba(STYLE.light.shadow, S.shade.alpha));
  g.fillStyle = sh; g.fillRect(x0, y0, w, h);
  const cx = x0 + w * (0.5 + light * S.lit.x), cy = y0 + h * S.lit.y, r = Math.max(w, h) * S.lit.r;
  const lt = g.createRadialGradient(cx, cy, 0, cx, cy, r);
  lt.addColorStop(0, rgba(S.lit.color, S.lit.alpha)); lt.addColorStop(1, rgba(S.lit.color, 0));
  g.fillStyle = lt; g.fillRect(x0, y0, w, h);
  g.restore();
}
const rgba = (hex, a) => `rgba(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join()},${a})`;

/** the head's own space: scaled by the build and tilted (o.tilt radians, + = top toward canvas +x) about its centre;
 *  nothing at all when neither applies (a lone translate pair shifts a leaning figure by float rounding) */
function headSpace(g, hx, hy, scale, tilt) {
  if (scale === 1 && !tilt) return;
  g.translate(hx, hy); if (tilt) g.rotate(tilt); if (scale !== 1) g.scale(scale, scale); g.translate(-hx, -hy);
}

/** a built-in headwear / legwear value as the drawing code takes it ({ kind, color }), or null (none or custom) */
function builtin(slot, v) {
  const s = slotValue(v);
  return s && BUILTIN_WARDROBE[s.id] === slot ? { kind: s.id, color: s.color } : null;
}

/** where wardrobe layers hang, per anchor: frames { at, sx, sy, ang, m } (wardrobe.js layerPoints). Body anchors scale
 *  with the build (torso: body_w x body_h; arms, hands: arm; legs: along the leg; feet: leg); paired ones are [left
 *  (mirrored), right]; head anchors are in head space (drawn inside the head's own scale). Unrotated canvas px. */
export function anchors(k, look = 1) {
  const S = k.size, b = S.b, x = CW / 2, [hx, hy] = k.head, fx = hx + 26 * look;
  const F = (at, sx = 1, sy = 1, ang = 0, m = 1) => ({ at, sx, sy, ang, m });
  const torso = (y) => [F([x, y], b.body_w, b.body_h)];
  const pair = (f) => [f(0, -1), f(1, 1)];
  const angle = (a, c) => Math.atan2(c[0] - a[0], c[1] - a[1]);
  return {
    head: [F([hx, hy])], head_top: [F([hx, hy - HEAD_R * HEAD_SQUASH])], face: [F([fx, hy])],
    eyes: [F([fx, hy - 8])], mouth: [F([fx + 4 * look, hy + 74])],
    neck: torso(k.top), chest: torso(k.top + 0.73 * k.ry), waist: torso(k.cy + 0.25 * k.ry), hips: torso(k.hipY),
    back: torso(k.top + 0.4 * k.ry),
    shoulders: pair((i, m) => F(k.arms[i][0], b.body_w, b.body_h, 0, m)),
    arms: pair((i, m) => F(k.arms[i][0], 1, b.arm, angle(k.arms[i][0], k.arms[i][1]), m)),
    hands: pair((i, m) => F(k.arms[i][2], b.arm, b.arm, 0, m)),
    legs: pair((i, m) => F(k.legs[i][0], 1, b.leg, angle(k.legs[i][0], k.legs[i][1]), m)),
    feet: pair((i, m) => F(k.legs[i][1], b.leg, b.leg, 0, m)),
  };
}

/** sleeping: three marker "Z"s rising away from the head. The card lies rolled 90 degrees (o.zSide: the canvas side
 *  that is "up" on screen), so each glyph is counter-rotated to read upright. o.zzz 0..1: how far the trail rose. */
function zzz(p, g, boil, o, hx, hy) {
  const side = o.zSide || 1, rise = o.zzz;
  [0, 1, 2].forEach((j) => {
    const show = rise * 3 - j; // the glyphs appear one after another
    if (show <= 0) return;
    const size = 26 + 9 * j, cx = hx + side * (168 + 30 * j + 18 * rise), cy = hy - 70 - 40 * j;
    g.save();
    g.translate(cx, cy); g.rotate(-side * Math.PI / 2);
    g.globalAlpha = Math.min(1, show) * (1 - Math.max(0, rise - 0.8) / 0.2);
    p.stroke(jitter([[-size / 2, -size / 2], [size / 2, -size / 2], [-size / 2, size / 2], [size / 2, size / 2]], boil, 1.5), 7);
    g.restore();
  });
}

// --- costumes (flat colour, thick outline, marker jitter; all in unrotated canvas px) ---
const OL = 8;                                   // costume outline width
const HOLD = [deg(22), deg(108)];               // seated prop arm: upper arm angle, forearm bend (right arm)
const rect = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];

/** tube along a leg from fraction f0 to f1 of hip -> foot, half-width w0 -> w1; ragged: zigzag hem */
function legTube([hip, foot], f0, f1, w0, w1, ragged = false) {
  const dx = foot[0] - hip[0], dy = foot[1] - hip[1], L = Math.hypot(dx, dy), ux = dx / L, uy = dy / L;
  const P = (f, w) => [hip[0] + dx * f - uy * w, hip[1] + dy * f + ux * w]; // w > 0: one side, < 0: the other
  const teeth = ragged ? 5 : 1, hem = [];
  for (let i = 0; i <= teeth * 2; i++) { // hem from +w1 to -w1; ragged teeth point down the leg
    const w = w1 - (2 * w1 * i) / (teeth * 2), f = f1 + (ragged && i % 2 ? 14 / L : 0);
    if (ragged || i === 0 || i === teeth * 2) hem.push(P(f, w));
  }
  return [P(f0, w0), ...hem, P(f0, -w0)];
}

function legwear(p, cos, lw, legs, knees) {
  const tubes = knees ? legs.flatMap(([hip, foot], i) => { // bent knees: a tube per segment (fractions doubled), a round knee
    const kn = knees[i], short = lw.kind !== "trousers";
    return [legTube([hip, kn], -0.16, short ? 0.84 : 1, short ? 31 : 30, short ? 27 : 23.5, short && lw.kind === "ragged_shorts"),
      ...(short ? [] : [ellPts(kn[0], kn[1], 23.5, 23.5, 0, 360, 0, 16), legTube([kn, foot], 0, 0.92, 23.5, 17)])];
  }).map((t) => jitter(t, cos, 1.5)) : legs.map((leg) => jitter(lw.kind === "trousers" ? legTube(leg, -0.08, 0.96, 30, 17)
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

/** dress: a flared skirt from the waist (over the fitted top's lower half: the seam reads as a waistline) to the
 *  knee, scalloped hem; stick legs show below it. Walking swings the hem with the stride. */
export function skirt(p, cos, color, k, o) {
  const S = k.size || sizes(), x = CW / 2, waist = k.cy + k.ry * 0.25, hem = k.hipY + S.leg * 0.5, wx = S.rx * 0.86, hw = S.rx * 1.45;
  const sway = GAITS.has(o.action) && o.action !== "carried" ? 14 * Math.sin(TAU * (o.phase || 0)) : 3 * (o.breath || 0);
  const pts = [[x - wx, waist], [x + wx, waist]];
  for (let j = 0; j <= 6; j++) pts.push([x + hw + sway - (j * 2 * hw) / 6, hem + (j % 2 ? 12 : 0)]);
  p.poly(jitter(pts, cos, 1.5), color, OL + 2);
}

// bold rounded digits: polylines in a 0..1 box (x right, y down)
const ring = (cx, cy, rx, ry) => ellPts(cx, cy, rx, ry, 0, 360, 0, 16);
const SIX = [[[0.8, 0.05], [0.42, 0.1], [0.14, 0.45], [0.12, 0.78], [0.35, 1], [0.68, 1], [0.9, 0.78], [0.86, 0.56],
  [0.58, 0.44], [0.28, 0.48], [0.13, 0.64]]];
const DIGITS = {
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

// custom props: library/props.json (schema CustomProp: shapes in hand space) through library.js
const BUILTIN = new Set(["clipboard", "stopwatch", "bottle", "syringe", "apple", "medal"]);

/** the held prop's angle in degrees, like a clock hand with the top tipped away from the body (0 upright, 90 level,
 *  75 = 2:30 in the right hand): the cast's own { angle } wins over the prop's (library/props.json) */
const propAngle = (pr) => pr.angle ?? (BUILTIN.has(pr.kind) ? 0 : lookup("props", pr.kind).angle ?? 0);

/** prop in a hand: local shapes (hand at 0,0, y down, x away from the body) turned partly with the forearm, plus its
 *  angle (propAngle); a custom prop's grip is the point of it the hand holds (default 0,0). pr: { kind, angle? } */
export function drawProp(p, cos, pr, hand, fore, side) {
  const kind = pr.kind, th = -fore * 0.35 + side * propAngle(pr) * Math.PI / 180, c = Math.cos(th), s = Math.sin(th);
  const [gx, gy] = (!BUILTIN.has(kind) && lookup("props", kind).grip) || [0, 0];
  const T = (pts) => jitter(pts.map(([x0, y0]) => [x0 - gx, y0 - gy]).map(([x, y]) =>
    [hand[0] + x * side * c - y * s, hand[1] + x * side * s + y * c]), cos, 1.2);
  const poly = (pts, fill, w = OL) => p.poly(T(pts), fill, w), line = (pts, w) => p.stroke(T(pts), w);
  const circ = (x, y, r) => ellPts(x, y, r, r, 0, 360, 0, 20);
  if (!BUILTIN.has(kind)) {
    for (const s of lookup("props", kind).shapes) {
      if (s.shape === "line") { line(s.pts, s.width ?? OL); continue; }
      const [[x0, y0], [x1, y1] = [0, 0]] = s.pts;
      const pts = s.shape === "rect" ? rect(x0, y0, x1, y1) : s.shape === "circle" ? circ(x0, y0, s.r) : s.pts;
      poly(pts, s.fill ?? null, s.width ?? OL);
    }
  } else if (kind === "clipboard") {
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
function headwear(p, cos, hw, headPts, hx, hy, look, accent) {
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
  } else if (hw.kind === "wide_hat") {
    // wide brim, low crown, a ribbon band and a five-petal flower in the accent colour on the side it faces
    const acc = accent || "#c2185b";
    p.poly(J(ellPts(mid, brim + 4, half + 80, 22, 0, 360, 0, 28)), col, OL);
    p.poly(J([[xl + 4, brim], [xl + 18, hy - 158], [xr - 18, hy - 158], [xr - 4, brim]]), col, OL + 2);
    p.poly(J([[xl + 6, brim - 4], [xl + 9, brim - 30], [xr - 9, brim - 30], [xr - 6, brim - 4]]), acc, 5);
    const fx = look ? xr - 10 : xr - 24, fy = brim - 20;
    for (let a = 0; a < 5; a++) {
      const t = (a * TAU) / 5;
      p.poly(J(ellPts(fx + 13 * Math.cos(t), fy + 13 * Math.sin(t), 11, 11, 0, 360, 0, 12), 1), acc, 4);
    }
    p.dot(fx, fy, 12, "#ffd54a");
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
  const big = expr === "surprised" || o.action === "react" || (o.action === "collapse" && (o.buckle || 0) > 0.3);
  // expression overrides the base eye style; blinks win over everything
  const kind = expr === "dead" ? "x"                      // X eyes; a dead face never blinks
    : o.lid >= 1 ? "closed" : o.lid === 0.5 ? "half"
    : expr === "surprised" ? "round"                      // wide open, small pupils, for every character
    : expr === "sleepy" ? "half"                          // flat lids
    : expr === "exhausted" ? "heavy"                      // lids drooping low over the pupils
    : (expr === "happy" || expr === "cheer") && o.eyes === "half_closed" ? "arc" // soft upward arcs; dot eyes keep their dots
    : o.eyes === "half_closed" ? "half" : "round";
  for (const x of ex) {
    if (kind === "x") {                                                                  // dead: a cross per eye
      for (const s of [-1, 1]) p.stroke(jitter([[x - 24, ey - 24 * s], [x + 24, ey + 24 * s]], boil, 1.5), w("eye") * 1.4);
    } else if (kind === "closed") {
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
      p.dot(x + 8 * look + 10 * (o.gaze || 0), ey + 2, w("pupil") * (big ? 0.75 : 1)); // gaze: a glance sideways
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
    cheer: ellPts(mx, my - 18, 32, 22, 20, 160, 0, 12),
    sad: ellPts(mx, my + 14, 26, 12, 205, 335, 0, 12),
    angry: [[mx - 20, my + 5], [mx, my - 1], [mx + 20, my + 5]],
    sleepy: [[mx - 12, my], [mx + 12, my]],
    cheeky: quad([mx - 22, my + 2], [mx + 2, my + 14], [mx + 28, my - 12]), // lopsided grin
    dead: [[mx - 24, my + 2], [mx - 12, my - 4], [mx, my + 2], [mx + 12, my - 4], [mx + 24, my + 2]], // slack wavy line
    worried: [[mx - 22, my + 5], [mx, my - 4], [mx + 22, my + 5]],
  };
  if (expr === "exhausted") p.poly(ellPts(mx, my + 2, 11, 9, 0, 360, 0, 16), "#1c1a1a", 0); // small open mouth
  else if (expr === "surprised") p.poly(ellPts(mx, my, 12, 15, 0, 360, 0, 20), null, w("mouth") * 0.9);
  else p.stroke(jitter(M[expr] || M.neutral, boil, 1.2), w("mouth"));
}
