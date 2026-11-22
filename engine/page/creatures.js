// Cast bodies ("creatures", series.json cast body = a creature id, default "human"). A humanoid is the stickman
// (stickman.js) with a build: proportions and head colour. Every other creature is a drawing (shapes in the
// custom-prop format plus ellipse) hung on one of four built-in rigs, which animate it per action:
//   bird      body, head, wing, leg (x2), tail?      chicken, duck, penguin, crow
//   quadruped body, head, leg_front, leg_back (x2 each), tail?   cat, dog, horse, cow
//   biped     body, head, arm (x2), leg (x2), tail?  monkey, bear, robot: with humanoids, the rigs with hands
//   crawler   body, head?, tail?                     snake, worm, slug: the body ripples as it moves
// Any rig may add a stump: drawn in place of the head when the cast member is headless.
// Coordinates: canvas px, facing right, origin on the ground under the creature, y down (up is negative). The body
// is drawn in that ground space; every other part around its joint (joints[JOINT_OF[part]], ground space), at rest.
// Faces are only eyes (dot, blinks) and a mouth (opens while talking), at face.eye / face.mouth in head space.
// Drawn on a CRW x CH card (twice the stickman's width, same height and world scale), ground at (CRW/2, FEET_Y).
// Pure function of its options, like drawStickman.
import { Pen } from "./borrowed.js";
import { lookup } from "./library.js";
import { rng } from "./rng.js";
import { CH, FEET_Y, drawProp, jitter, wobble } from "./stickman.js";
import { STYLE } from "./style.js";

export const CRW = 1024, GX = CRW / 2;
const INK = "#1c1a1a", TAU = Math.PI * 2, deg = (d) => (d * Math.PI) / 180;
export const RIGS = { // part -> required (keep equal to pipeline schemas RIG_PARTS)
  humanoid: { parts: {}, hands: true }, // a stickman with a build: drawStickman, not drawCreature
  bird: { parts: { body: true, head: true, wing: true, leg: true, tail: false, stump: false }, hands: false },
  quadruped: { parts: { body: true, head: true, leg_front: true, leg_back: true, tail: false, stump: false }, hands: false },
  biped: { parts: { body: true, head: true, arm: true, leg: true, tail: false, stump: false }, hands: true },
  crawler: { parts: { body: true, head: false, tail: false, stump: false }, hands: false },
};
export const JOINT_OF = { head: "neck", stump: "neck", wing: "wing", tail: "tail", leg: "hip", leg_front: "shoulder",
  leg_back: "hip", arm: "shoulder" };
const MOVING = new Set(["walk", "run", "stagger", "carry", "support", "supported", "carried"]);
const SEAT_LINE = 338;   // seated in a car: the body's lowest point is lifted to this height (clears the side panel)
const FAR = { dx: -14, shade: "brightness(0.8)" }; // far limbs: a little behind and darker
const FACE = { eye: 10, mouth: 18 };

// ---- built-in creatures (same format as library/creatures.json; keep ids equal to pipeline BUILTIN_CREATURES) ----
const L = (pts, fill, width) => ({ shape: "line", pts, fill, width });
const E = (x, y, r, ry, fill, width = 10, rot = 0) => ({ shape: "ellipse", pts: [[x, y]], r, ry, rot, fill, width });
const C = (x, y, r, fill, width = 10) => ({ shape: "circle", pts: [[x, y]], r, fill, width });
const P = (pts, fill, width = 10) => ({ shape: "poly", pts, fill, width });
const R = (pts, fill, width = 8) => ({ shape: "rect", pts, fill, width });
const CUT = "#9e1f22", LEGS = "#e8a33a";
const stump = (w, h) => [P([[-w, 8], [-w * 0.8, -h], [w * 0.8, -h + 6], [w, 10]], "$main"), E(0, -h + 3, w * 0.85, 12, CUT, 7, 4)];
const tube = (pts, w) => [L(pts, null, w + 10), L(pts, "$main", w)]; // a $main stroke with an ink edge
const limb = (w, len, foot) => [P([[-w, 0], [w, 0], [w * 0.8, len], [-w * 0.8, len]], "$main", 8), ...foot];

export const BUILTIN = [
  // the default cast body: a humanoid is drawn by drawStickman (stickman.js) with its build, never by drawCreature
  { id: "human", name: "Human", rig: "humanoid", accent: "#3a2a1e", joints: {}, face: {}, parts: {}, build: {} },
  { id: "chicken", name: "Chicken", rig: "bird", accent: "#d23c3c",
    joints: { hip: [0, -120], neck: [80, -240], wing: [40, -225], tail: [-120, -230] },
    face: { eye: [44, -132], mouth: [74, -112] },
    parts: {
      body: [E(-10, -200, 130, 92, "$main", 12, -8)],
      tail: [E(-15, -40, 58, 24, "$main", 10, 40), E(-30, -10, 58, 24, "$main", 10, 20), E(-30, 22, 58, 24, "$main", 10, 2)],
      head: [P([[-2, -150], [2, -190], [20, -168], [32, -204], [46, -170], [64, -192], [62, -150]], "$accent", 9),
        P([[-28, 8], [8, -118], [48, -104], [34, 14]], "$main", 11), C(28, -120, 50, "$main", 11),
        P([[58, -96], [52, -44], [32, -52], [36, -92]], "$accent", 8),
        P([[66, -128], [120, -116], [70, -104]], "#f0b13a", 7)],
      stump: stump(30, 76),
      wing: [P([[0, 0], [-50, -15], [-120, 5], [-135, 30], [-90, 50], [-30, 40]], "$main", 10), L([[-70, 20], [-110, 33]], null, 6)],
      leg: [L([[0, 0], [6, 60], [0, 120]], LEGS, 9), L([[0, 120], [34, 122]], LEGS, 7), L([[0, 120], [26, 110]], LEGS, 7),
        L([[0, 120], [-16, 120]], LEGS, 7)],
    } },
  { id: "cat", name: "Cat", rig: "quadruped", accent: "#e88a9a",
    joints: { hip: [-75, -100], shoulder: [70, -100], neck: [95, -140], tail: [-115, -130] },
    face: { eye: [52, -52], mouth: [76, -22] },
    parts: {
      body: [E(0, -120, 122, 52, "$main", 11)],
      tail: tube([[0, 0], [-40, -30], [-52, -90], [-32, -130]], 14),
      head: [P([[-6, -66], [-2, -122], [32, -84]], "$main", 9), P([[34, -86], [66, -114], [70, -62]], "$main", 9),
        C(30, -40, 52, "$main", 10), C(80, -36, 7, "$accent", 3), L([[86, -26], [122, -32]], null, 3), L([[86, -22], [120, -10]], null, 3)],
      stump: stump(28, 40),
      leg_front: limb(12, 92, [E(5, 94, 17, 9, "$main", 7)]),
      leg_back: limb(13, 92, [E(5, 94, 17, 9, "$main", 7)]),
    } },
  { id: "horse", name: "Horse", rig: "quadruped", accent: "#3a2a1e",
    joints: { hip: [-180, -500], shoulder: [170, -500], neck: [220, -600], tail: [-255, -600] },
    face: { eye: [140, -228], mouth: [222, -150] },
    parts: {
      body: [E(0, -560, 262, 122, "$main", 12)],
      tail: tube([[0, 0], [-40, 60], [-52, 180], [-40, 260]], 22),
      head: [P([[-30, 10], [-66, -8], [40, -248], [70, -224]], "$accent", 8), P([[-50, 20], [60, -230], [130, -200], [60, 60]], "$main", 11),
        P([[92, -262], [104, -324], [128, -258]], "$main", 9), E(150, -196, 98, 50, "$main", 11, 32), C(212, -160, 6, null, 5)],
      stump: stump(60, 120),
      leg_front: limb(22, 470, [R([[-20, 468], [20, 500]], "#3a2a1e")]),
      leg_back: limb(24, 470, [R([[-20, 468], [20, 500]], "#3a2a1e")]),
    } },
  { id: "monkey", name: "Monkey", rig: "biped", accent: "#e8c79a",
    joints: { hip: [0, -262], shoulder: [10, -470], neck: [15, -500], tail: [-60, -300] },
    face: { eye: [48, -96], mouth: [62, -50] },
    parts: {
      body: [E(0, -380, 76, 126, "$main", 11), E(26, -370, 40, 82, "$accent", 6)],
      tail: tube([[0, 0], [-60, 20], [-100, -30], [-90, -90], [-60, -110]], 12),
      head: [C(10, -82, 86, "$main", 11), E(44, -70, 50, 48, "$accent", 7), C(-36, -92, 28, "$accent", 8)],
      stump: stump(34, 30),
      arm: limb(12, 230, [C(0, 236, 17, "$accent", 7)]),
      leg: limb(14, 250, [E(14, 252, 27, 12, "$accent", 7)]),
    } },
  { id: "snake", name: "Snake", rig: "crawler", accent: "#e2c044",
    joints: { neck: [260, -40] },
    face: { eye: [52, -36], mouth: [94, -12] },
    parts: {
      body: [P([[-385, -14], [-300, -40], [-150, -60], [0, -62], [150, -60], [252, -58], [282, -30], [252, -4], [150, -2], [0, -2],
        [-150, -2], [-300, -4]], "$main", 11), C(-250, -28, 11, "$accent", 0), C(-100, -32, 12, "$accent", 0),
        C(50, -32, 12, "$accent", 0), C(180, -32, 11, "$accent", 0)],
      head: [E(40, -20, 62, 38, "$main", 10)],
      stump: [E(0, -28, 14, 30, CUT, 7)],
    } },
];

// ---- a body by id: built in, else library/creatures.json through library.js (unknown: throws) ----
const BUILT = new Map(BUILTIN.map((c) => [c.id, c]));
export const creature = (id) => BUILT.get(id) ?? lookup("creatures", id);

// ---- geometry of a creature at rest (cached per definition) ----
const shapeY = (s) => (s.shape === "circle" || s.shape === "ellipse"
  ? [s.pts[0][1] - Math.max(s.r, s.ry || 0), s.pts[0][1] + Math.max(s.r, s.ry || 0)]
  : [Math.min(...s.pts.map((p) => p[1])), Math.max(...s.pts.map((p) => p[1]))]);
const shapeX = (s) => (s.shape === "circle" || s.shape === "ellipse" ? [s.pts[0][0] - Math.max(s.r, s.ry || 0), s.pts[0][0] + Math.max(s.r, s.ry || 0)]
  : [Math.min(...s.pts.map((p) => p[0])), Math.max(...s.pts.map((p) => p[0]))]);
const extent = (shapes, dy = 0) => shapes.map(shapeY).reduce(([a, b], [c, d]) => [Math.min(a, c + dy), Math.max(b, d + dy)], [Infinity, -Infinity]);
const CACHE = new WeakMap();
/** { top: px from the ground to the highest point at rest (positive), half: widest |x| reach, bottom: the body's lowest y, leg: hip height,
 *  arm: arm length } */
export function measure(def) {
  if (CACHE.has(def)) return CACHE.get(def);
  let top = extent(def.parts.body)[0], half = 0;
  for (const [part, shapes] of Object.entries(def.parts)) {
    const j = part === "body" ? [0, 0] : def.joints[JOINT_OF[part]];
    for (const s of shapes) for (const x of shapeX(s)) half = Math.max(half, Math.abs(x + j[0]));
    if (part !== "body" && part !== "stump") top = Math.min(top, extent(shapes, j[1])[0]);
  }
  const m = { top: -top, half, bottom: extent(def.parts.body)[1], leg: def.joints.hip ? -def.joints.hip[1] : 0,
    arm: def.parts.arm ? extent(def.parts.arm)[1] : 0 };
  CACHE.set(def, m);
  return m;
}

/** pose (degrees, canvas rotation: + turns clockwise, so a hanging limb at + swings backward) from the drawing
 *  options. legs: bird / biped [near, far]; quadruped [front near, front far, back near, back far]. arms [near, far]
 *  (-90 points forward, -170 straight up). wing < 0 raises it. sit 0..1 lowers the body to the ground (lie,
 *  collapse). ripple: crawler body wave amplitude px and its phase. Legs depend only on the gait phase. */
export function creaturePose(rig, o, legLen = 120) {
  const act = o.action, t = o.t || 0, steps = Math.min(3, Math.max(0.7, 220 / (legLen || 220)));
  const ph = TAU * steps * (o.phase || 0), s = Math.cos(ph); // cos: a quarter stride is a full step
  const p = { lift: -2 * (o.breath || 0), pitch: 0, head: 0, tail: 4 * Math.sin(TAU * 0.5 * t), wing: 0,
    legs: [0, 0, 0, 0], arms: [6, -6], sit: 0, ripple: 0, ripplePhase: 0 };
  const mood = o.mood ? o.mood.k : 1, buzz = 0.5 + 0.5 * Math.sin(TAU * 4 * t), hop = Math.abs(Math.sin(TAU * 2 * t));
  const flap = (f) => {
    if (rig === "bird") p.wing = -65 * f;
    else if (rig === "quadruped") p.tail = 28 * Math.sin(TAU * 4 * t) * f;
    else if (rig === "crawler") { p.head = -22 * f; p.lift -= 12 * hop * f; }
  };
  if (MOVING.has(act)) {
    const a = (act === "run" ? 34 : act === "stagger" || act === "supported" ? 20 : 24) * s;
    if (rig === "quadruped") p.legs = act === "run" ? [a, 0.8 * a, -a, -0.8 * a] : [a, -a, -a, a];
    else if (rig === "crawler") { p.ripple = act === "run" ? 16 : 10; p.ripplePhase = ph; }
    else p.legs = [a, -a, 0, 0];
    if (rig === "biped") p.arms = [-0.8 * a, 0.8 * a];
    if (act === "run") { p.pitch = rig === "bird" ? 12 : rig === "biped" ? 8 : 0; if (rig === "quadruped") p.lift -= 10 * Math.abs(Math.sin(ph)); flap(buzz); }
    if (act === "walk" && rig === "bird") p.pitch = 4;
    if (act === "stagger" || act === "supported") {
      const sway = o.stagger ? o.stagger.sway : Math.sin(TAU * 0.7 * t);
      p.pitch += 10 * sway; flap(0.5 + 0.5 * Math.sin(TAU * 3.1 * t));
      if (rig === "biped") p.arms = [-40 + 20 * sway, 40 - 20 * sway];
    }
  }
  if (act === "talk") p.head = -4 * (o.mouth || 0);
  if (act === "react" || act === "gasp") {
    flap(mood * buzz); p.head = -10 * mood;
    if (rig === "quadruped") p.lift -= 12 * mood;
    if (rig === "biped") p.arms = [-140 * mood, -130 * mood];
  }
  if (act === "cheer") {
    flap(mood * buzz);
    if (rig === "quadruped" || rig === "biped") p.lift -= 18 * hop * mood;
    if (rig === "biped") p.arms = [-165 * mood, -155 * mood];
  }
  if (act === "angry") {
    flap(mood * buzz); p.pitch += rig === "bird" ? 15 : 0; p.head = rig === "quadruped" ? 14 : p.head;
    if (rig === "biped") { const sh = 10 * (o.mood ? o.mood.shake : 0); p.arms = [-120 + sh, -115 - sh]; }
  }
  if (act === "wave") {
    const k = o.wave ? o.wave.k : 1;
    if (rig === "biped") p.arms[0] = (-160 + 20 * Math.sin(TAU * 2 * t)) * k; else flap(k * (0.5 + 0.5 * Math.sin(TAU * 2 * t)));
  }
  if (act === "point") {
    const k = o.pointK ?? 1;
    if (rig === "biped") p.arms[0] = -90 * k; else if (rig === "bird") p.wing = -40 * k; else p.head = -14 * k;
  }
  if (act === "eat") {
    const k = o.eat ? o.eat.k : 1;
    if (rig === "bird") { p.head = 50 * Math.abs(Math.sin(TAU * 1.6 * t)); p.pitch = 15; }
    else if (rig === "quadruped") p.head = 35 * k;
    else if (rig === "biped") p.arms[0] = -128 * k; // the food held up in front of the face
  }
  if (rig === "biped" && o.reach && ["give", "receive", "carry", "support"].includes(act)) p.arms[0] = -75 * (o.reach.k ?? 1);
  if (rig !== "biped") p.sit = act === "lie" ? 1 : act === "collapse" ? o.buckle || 0 : 0;
  else if (o.buckle) p.legs = [-16 * o.buckle, 16 * o.buckle, 0, 0];
  return p;
}

const rot = ([x, y], [cx, cy], a) => {
  const c = Math.cos(a), s = Math.sin(a), dx = x - cx, dy = y - cy;
  return [cx + dx * c - dy * s, cy + dx * s + dy * c];
};
const colour = (fill, col) => (fill == null ? null : fill === "$main" ? col.main : fill === "$accent" ? col.accent : fill);

/** draw shapes through T (local point -> canvas point). Circles and ellipses are wobbly marker loops. */
function drawShapes(p, shapes, T, col, boil, seed, light = 1) {
  shapes.forEach((s, i) => {
    const fill = colour(s.fill, col), w = s.width ?? 8;
    if (s.shape === "line") { p.stroke(jitter(s.pts.map(T), boil, 1.5), w, fill || INK); return; }
    let pts;
    if (s.shape === "rect") {
      const [[x0, y0], [x1, y1]] = s.pts;
      pts = jitter([[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(T), boil, 1.5);
    } else if (s.shape === "poly") pts = jitter(s.pts.map(T), boil, 1.5);
    else {
      const [[cx, cy]] = s.pts, a = deg(s.rot || 0), ry = s.shape === "ellipse" ? s.ry : s.r;
      pts = wobble(0, 0, s.r, ry, rng(seed, i), boil, 0.03, 0.01, 36)
        .map(([x, y]) => T([cx + x * Math.cos(a) - y * Math.sin(a), cy + x * Math.sin(a) + y * Math.cos(a)]));
    }
    p.poly(pts, fill, 0);
    if (fill) paintShape(p.g, pts, light);
    p.poly(pts, null, w);
  });
}

/** painted volume inside a filled shape (STYLE.creature): a soft lit spot toward the key light (`light` = its side
 *  in card x, -1 or 1) and the light's shadow colour pooling at the bottom. Clipped to the shape, under the outline. */
function paintShape(g, pts, light) {
  const S = STYLE.creature;
  if (!S) return;
  const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), w = x1 - x0, h = y1 - y0;
  if (w < S.minSize && h < S.minSize) return; // eyes, nostrils, spots: flat
  g.save(); g.clip();
  const sh = g.createLinearGradient(0, y0 + h * S.shade.from, 0, y1);
  sh.addColorStop(0, rgba(STYLE.light.shadow, 0)); sh.addColorStop(1, rgba(STYLE.light.shadow, S.shade.alpha));
  g.fillStyle = sh; g.fillRect(x0, y0, w, h);
  const cx = x0 + w * (0.5 + light * S.lit.x), cy = y0 + h * S.lit.y, r = Math.max(w, h) * S.lit.r;
  const lt = g.createRadialGradient(cx, cy, 0, cx, cy, r);
  lt.addColorStop(0, rgba(S.lit.color, S.lit.alpha)); lt.addColorStop(1, rgba(S.lit.color, 0));
  g.fillStyle = lt; g.fillRect(x0, y0, w, h);
  g.restore();
}
const rgba = (hex, a) => `rgba(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join()},${a})`;

/** o: drawStickman options (top.color = $main, top.accent_color = $accent, else the creature's accent), plus
 *  headless. Uses action, phase, t, boil, breath, mouth, lid, facing, seated, buckle, stagger, mood, wave, pointK,
 *  eat, reach, props (biped hands); ignores expression and costume. */
export function drawCreature(canvas, def, o) {
  const g = canvas.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, CRW, CH);
  if (o.facing === "left") g.setTransform(-1, 0, 0, 1, CRW, 0);
  const m = measure(def), k = creaturePose(def.rig, o, m.leg), parts = def.parts, J = def.joints;
  if (o.seated) g.translate(0, Math.min(0, -SEAT_LINE - m.bottom));
  const p = new Pen(g, INK), boil = rng(o.seed, "boil", o.boil), cos = rng(o.seed, "costume", o.boil);
  const col = { main: (o.top && o.top.color) || o.color || "#888888", accent: (o.top && o.top.accent_color) || def.accent || "#3a2a1e" };
  // the body sinks by the sit amount and by the gait (the more upright leg stays on the ground)
  const plant = m.leg * (1 - Math.cos(deg(Math.min(...k.legs.slice(0, def.rig === "quadruped" ? 4 : 2).map(Math.abs)))));
  const drop = k.sit * m.leg * 0.85 + plant, pivot = J.hip || [0, m.bottom], pa = deg(k.pitch);
  const ripple = ([x, y]) => (k.ripple ? [x, y - k.ripple * Math.sin(x / 70 - k.ripplePhase)] : [x, y]);
  const body = (pt) => { const [x, y] = rot(ripple(pt), pivot, pa); return [GX + x, FEET_Y + y + drop + k.lift]; };
  const at = (part, a = 0, dx = 0) => { // local point of a part -> canvas, the part turned by a degrees about its joint
    const j = J[JOINT_OF[part]], r = deg(a);
    return ([x, y]) => body([j[0] + dx + x * Math.cos(r) - y * Math.sin(r), j[1] + x * Math.sin(r) + y * Math.cos(r)]);
  };
  const legAt = (part, a, dx = 0) => { // legs hang from the moving body but are not pitched with it
    const j = J[JOINT_OF[part]], r = deg(a), [jx, jy] = body(j);
    return ([x, y]) => [jx + dx + x * Math.cos(r) - y * Math.sin(r), jy + x * Math.sin(r) + y * Math.cos(r)];
  };
  const far = (draw) => { g.save(); g.filter = FAR.shade; draw(); g.restore(); };
  const legsShown = k.sit < 0.6, lt = o.facing === "left" ? -1 : 1; // key light stays on screen right (card mirrored)
  const legs = def.rig === "quadruped" ? [["leg_front", 0], ["leg_back", 2]] : parts.leg ? [["leg", 0]] : [];

  if (legsShown) for (const [part, i] of legs) far(() => drawShapes(p, parts[part], legAt(part, k.legs[i + 1], FAR.dx), col, boil, `${o.seed}:${part}`, lt));
  if (parts.arm) far(() => drawArm(1, FAR.dx));
  if (parts.tail) drawShapes(p, parts.tail, at("tail", k.tail), col, boil, `${o.seed}:tail`, lt);
  if (legsShown) for (const [part, i] of legs) drawShapes(p, parts[part], legAt(part, k.legs[i]), col, boil, `${o.seed}:${part}`, lt);
  // head (or stump) before the body, so the body covers the base of the neck
  const head = o.headless ? parts.stump : parts.head;
  if (head) drawShapes(p, head, at("head", k.head), col, boil, `${o.seed}:${o.headless ? "stump" : "head"}`, lt);
  drawShapes(p, parts.body, body, col, boil, `${o.seed}:body`, lt);
  if (parts.wing) drawShapes(p, parts.wing, at("wing", k.wing), col, boil, `${o.seed}:wing`, lt);
  if (parts.arm) drawArm(0, 0);
  if (!o.headless && def.face) face(parts.head ? at("head", k.head) : body);

  function drawArm(i, dx) {
    const T = at("arm", k.arms[i], dx);
    drawShapes(p, parts.arm, T, col, boil, `${o.seed}:arm`, lt);
    const hand = T([0, m.arm]), fore = -deg(k.arms[i]); // fore: radians from straight down, + toward +x
    for (const pr of o.props || []) if ((pr.hand === "left" ? 1 : 0) === i) drawProp(p, cos, pr, hand, fore, 1);
  }
  function face(T) {
    const { eye, mouth } = def.face, open = Math.max(0, Math.min(1, o.mouth || 0));
    if (eye) {
      const [x, y] = T(eye);
      if ((o.lid || 0) >= 0.5) p.stroke(jitter([[x - FACE.eye, y], [x + FACE.eye, y]], boil, 1), 6);
      else {
        p.dot(x, y, FACE.eye);
        if (STYLE.creature?.eye) p.dot(x + FACE.eye * 0.3, y - FACE.eye * 0.35, FACE.eye * STYLE.creature.eye, "#ffffff"); // catchlight
      }
    }
    if (mouth && open > 0.05) { const [x, y] = T(mouth); p.poly(wobble(x, y, FACE.mouth / 2, 3 + 12 * open, rng(o.seed, "mouth"), boil, 0.04, 0.02, 16), INK, 0); }
  }
}
