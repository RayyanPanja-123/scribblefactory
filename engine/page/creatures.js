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
import { CH, CW, FEET_Y, drawProp, drawStickman, jitter, paintVolume, skeleton, wobble } from "./stickman.js";
import { INK, STYLE } from "./style.js";
import { layerFill, layerPoints, wearing } from "./wardrobe.js";

export const CRW = 1024, GX = CRW / 2;
const TAU = Math.PI * 2, deg = (d) => (d * Math.PI) / 180;
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
/** a rider (@ride): its hip sits this far (px) below the mount's back anchor (into the saddle / onto the back); room:
 *  px of headroom a ridden card adds above the plain creature card (main.js) */
export const RIDE = { sink: 14, room: 420 };
let riderCv = null; // scratch canvas for the rider's stickman

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
    joints: { hip: [-175, -400], shoulder: [170, -400], neck: [215, -540], tail: [-235, -560] },
    face: { eye: [140, -228], mouth: [222, -150] },
    parts: {
      body: [E(0, -480, 265, 150, "$main", 12)],
      tail: [P([[10, -15], [-30, -5], [-62, 60], [-72, 170], [-62, 270], [-30, 305], [-36, 220], [-25, 120], [5, 40]], "$accent", 10),
        L([[-40, 60], [-50, 200]], null, 5)],
      head: [P([[-30, 10], [-66, -8], [40, -248], [70, -224]], "$accent", 8), P([[-50, 20], [60, -230], [130, -200], [60, 60]], "$main", 11),
        P([[92, -262], [104, -324], [128, -258]], "$main", 9), E(150, -196, 98, 50, "$main", 11, 32), C(212, -160, 6, null, 5)],
      stump: stump(60, 120),
      leg_front: [...limb(26, 370, [R([[-24, 366], [24, 400]], "#3a2a1e")]), E(0, 30, 44, 80, "$main", 10)],
      leg_back: [...limb(28, 370, [R([[-26, 366], [26, 400]], "#3a2a1e")]), E(-4, 30, 54, 95, "$main", 10)],
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
export function drawShapes(p, shapes, T, col, boil, seed, light = 1) {
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

const paintShape = (g, pts, light) => paintVolume(g, pts, light, STYLE.creature);

// ---- wardrobe on creatures: custom items of these slots only, hung on anchors worked out from the shapes ----
export const CREATURE_SLOTS = new Set(["headwear", "face", "accessory", "back"]); // keep equal to pipeline io.CREATURE_SLOTS
const half = (s) => { // [x, y] half-extent of a circle / ellipse, its rotation included
  const ry = s.ry ?? s.r, a = deg(s.rot || 0);
  return [Math.hypot(s.r * Math.cos(a), ry * Math.sin(a)), Math.hypot(s.r * Math.sin(a), ry * Math.cos(a))];
};
const box = (shapes) => { // [x0, y0, x1, y1] of shapes in their own space (shapeX / shapeY are rougher on ellipses)
  const pts = shapes.flatMap((s) => {
    if (s.shape !== "circle" && s.shape !== "ellipse") return s.pts;
    const [[x, y]] = s.pts, [hx, hy] = half(s);
    return [[x - hx, y - hy], [x + hx, y + hy]];
  });
  return [Math.min(...pts.map((q) => q[0])), Math.min(...pts.map((q) => q[1])), Math.max(...pts.map((q) => q[0])), Math.max(...pts.map((q) => q[1]))];
};
/** the head's skull: its biggest circle / ellipse (else the head's box): { c: centre, top, R: radius } */
function skull(shapes) {
  const round = shapes.filter((s) => s.shape === "circle" || s.shape === "ellipse");
  if (round.length) {
    const s = round.reduce((a, b) => (b.r * (b.ry ?? b.r) > a.r * (a.ry ?? a.r) ? b : a)), [cx, cy] = s.pts[0];
    return { c: [cx, cy], top: [cx, cy - half(s)[1]], R: Math.sqrt(s.r * (s.ry ?? s.r)) };
  }
  const [x0, y0, x1, y1] = box(shapes);
  return { c: [(x0 + x1) / 2, (y0 + y1) / 2], top: [(x0 + x1) / 2, y0], R: (x1 - x0) / 2 };
}
/** where wardrobe layers hang on a creature at rest: anchor -> [[part ("body" or a part), local point, scale]].
 *  Head anchors scale with the skull (the default human's head radius is 150), body anchors with the body's height
 *  (the human torso is 300 tall). Anchors a creature has no part for are left out; their layers are not drawn. */
export function creatureAnchors(def) {
  const P = def.parts, J = def.joints, [x0, y0, x1, y1] = box(P.body), bs = (y1 - y0) / 300;
  const mid = [(x0 + x1) / 2, (y0 + y1) / 2], out = {
    neck: [["body", J.neck || [x1, y0], bs]], back: [["body", [mid[0], y0], bs]],
    chest: [["body", mid, bs]], waist: [["body", mid, bs]], hips: [["body", mid, bs]],
  };
  if (P.tail) out.tail = [["tail", farthest(P.tail), bs]];
  const legs = Object.keys(P).filter((k) => k === "leg" || k === "leg_front" || k === "leg_back");
  if (legs.length) out.feet = legs.map((k) => [k, [0, lowest(P[k])], bs]);
  const sk = P.head && skull(P.head), hs = sk ? sk.R / 150 : bs, hp = P.head ? "head" : "body";
  if (sk) Object.assign(out, { head: [["head", sk.c, hs]], head_top: [["head", sk.top, hs]] });
  const { eye, mouth } = def.face || {};
  if (eye) out.eyes = [[hp, eye, hs]];
  if (mouth) out.mouth = [[hp, mouth, hs]];
  if (eye || mouth) out.face = [[hp, eye && mouth ? [(eye[0] + mouth[0]) / 2, (eye[1] + mouth[1]) / 2] : eye || mouth, hs]];
  return out;
}

// ---- flame (cast flame: low | high, flame_color): tongues on the mane, tail and hooves, eyes glowing ----
// per level: tongue height (fraction of the creature's height) and tongues on the mane / tail / each hoof
export const FLAME = { low: { h: 0.09, mane: 3, tail: 3, hoof: 2 }, high: { h: 0.16, mane: 5, tail: 5, hoof: 3 },
  layers: [1, 0.64, 0.34], sway: 0.2, swayHz: 1.3, flickerHz: 2.1, lean: -0.18, outline: 5 };
export const FIRE = ["#d8432a", "#f08a24", "#ffd23a"]; // outer, middle, core (no flame_color)
const mixHex = (a, b, k) => "#" + [1, 3, 5].map((i) => Math.round(parseInt(a.slice(i, i + 2), 16) * (1 - k)
  + parseInt(b.slice(i, i + 2), 16) * k).toString(16).padStart(2, "0")).join("");
/** [outer, middle, core] for a flame colour (null: fire); the core is also the glowing eyes' colour */
export const flamePalette = (c) => (c ? [c, mixHex(c, "#ffffff", 0.4), mixHex(c, "#ffffff", 0.75)] : FIRE);
const TONGUE = [[-0.5, 0], [-0.55, -0.35], [-0.25, -0.7], [0.05, -1], [0.3, -0.6], [0.5, -0.3], [0.5, 0], [0, 0.22]];
/** one flame tongue standing on canvas point [bx, by]: h tall, layered outer to core, swaying with t (seeded phase) */
function tongue(p, [bx, by], h, pal, t, R, boil) {
  const ph = TAU * R(), ph2 = TAU * R();
  const a = FLAME.lean + FLAME.sway * Math.sin(TAU * FLAME.swayHz * t + ph);
  const H = h * (0.85 + 0.15 * Math.sin(TAU * FLAME.flickerHz * t + ph2)), W = 0.6 * H;
  FLAME.layers.forEach((k, i) => {
    const pts = TONGUE.map(([x, y]) => { // the tip bends further than the base: a curl, not a tilt
      const lx = x * W * k, ly = y * H * k, b = a * Math.max(0, -y);
      return [bx + lx * Math.cos(b) - ly * Math.sin(b), by + lx * Math.sin(b) + ly * Math.cos(b)];
    });
    p.poly(jitter(pts, boil, 1.5), pal[i], i ? 0 : FLAME.outline);
  });
}
const lowest = (shapes) => extent(shapes)[1];
const farthest = (shapes) => shapes.flatMap((s) => s.pts).reduce((a, q) => (Math.hypot(...q) > Math.hypot(...a) ? q : a), [0, 0]);
const highest = (shapes) => shapes.flatMap((s) => s.pts).reduce((a, q) => (q[1] < a[1] ? q : a), [0, 0]);
/** n points from u0 to u1 of the way along the segment 0 -> q (local space) */
const along = (q, n, u0 = 0.15, u1 = 1) => Array.from({ length: n }, (_, i) => {
  const u = n === 1 ? (u0 + u1) / 2 : u0 + ((u1 - u0) * i) / (n - 1);
  return [q[0] * u, q[1] * u];
});

/** o: drawStickman options (top.color = $main, top.accent_color = $accent, else the creature's accent), plus
 *  headless. Uses action, phase, t, boil, breath, mouth, lid, facing, seated, buckle, stagger, mood, wave, pointK,
 *  eat, reach, props (biped hands), flame (low | high, else none), flame_color and the CREATURE_SLOTS wardrobe
 *  (headwear, face, accessory, back: custom items on creatureAnchors); ignores the rest of the costume. rider:
 *  drawStickman options of a cast member riding it (@ride), room: px of headroom on top for the rider (the canvas
 *  is CRW x CH + room). */
export function drawCreature(canvas, def, o) {
  const g = canvas.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, CRW, CH + (o.room || 0));
  if (o.facing === "left") g.setTransform(-1, 0, 0, 1, CRW, 0);
  if (o.room) g.translate(0, o.room); // a ridden card: headroom on top, the ground stays FEET_Y below it
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
  // flame: its own rng (the creature's own lines boil exactly as without it), never a filter or a blur
  const lvl = FLAME[o.flame], pal = lvl && flamePalette(o.flame_color), fb = lvl && rng(o.seed, "flame", o.boil);
  const fire = (T, pts, scale, key) => { // tongues standing on local points pts of a part placed by T
    const R = rng(o.seed, "flame", key);
    for (const q of pts) tongue(p, T(q), lvl.h * m.top * scale, pal, o.t || 0, R, fb);
  };
  // wardrobe (CREATURE_SLOTS only): its own rng, so a creature that wears nothing draws exactly as before
  const W = wearing(o).filter((w) => CREATURE_SLOTS.has(w.slot)), wcos = W.length && rng(o.seed, "wardrobe", o.boil);
  const A = W.length && creatureAnchors(def), turn = { head: k.head, tail: k.tail };
  const wear = (behind) => {
    for (const w of W) for (const L of w.item.layers) {
      if (!!L.behind !== behind || (L.when && !L.when.includes(o.expression || "neutral"))) continue;
      for (const [part, q, s] of A[L.anchor] || []) {
        if (part === "head" && o.headless) continue;
        const leg = legs.find(([l]) => l === part), a = leg ? k.legs[leg[1]] : turn[part] || 0;
        const T = part === "body" ? body : leg ? legAt(part, a) : at(part, a);
        const fr = { at: T(q), sx: s, sy: s, ang: -(deg(a) + (leg ? 0 : pa)), m: 1 };
        const pts = jitter(layerPoints(L, fr), wcos, 1.2), fill = layerFill(L, w.color, w.accent);
        if (L.shape === "line") p.stroke(pts, L.width ?? 8, fill || INK); else p.poly(pts, fill, L.width ?? 8);
      }
    }
  };
  const hooves = (part, T, key) => lvl && fire(T, along([0, lowest(parts[part]) - 12], lvl.hoof, 1, 1)
    .map(([x, y], i) => [x + (i - (lvl.hoof - 1) / 2) * 20, y]), 0.7, key);

  if (W.length) wear(true); // behind layers (a cape's back) under everything
  if (legsShown) for (const [part, i] of legs) far(() => drawShapes(p, parts[part], legAt(part, k.legs[i + 1], FAR.dx), col, boil, `${o.seed}:${part}`, lt));
  if (legsShown) for (const [part, i] of legs) hooves(part, legAt(part, k.legs[i + 1], FAR.dx), `${part}:far`);
  if (parts.arm) far(() => drawArm(1, FAR.dx));
  if (parts.tail) drawShapes(p, parts.tail, at("tail", k.tail), col, boil, `${o.seed}:tail`, lt);
  if (lvl && parts.tail) fire(at("tail", k.tail), along(farthest(parts.tail), lvl.tail, 0.05, 1), 1, "tail");
  if (legsShown) for (const [part, i] of legs) drawShapes(p, parts[part], legAt(part, k.legs[i]), col, boil, `${o.seed}:${part}`, lt);
  if (legsShown) for (const [part, i] of legs) hooves(part, legAt(part, k.legs[i]), part);
  // head (or stump) before the body, so the body covers the base of the neck
  const head = o.headless ? parts.stump : parts.head;
  if (head) drawShapes(p, head, at("head", k.head), col, boil, `${o.seed}:${o.headless ? "stump" : "head"}`, lt);
  drawShapes(p, parts.body, body, col, boil, `${o.seed}:body`, lt);
  // mane: along the neck crest, from the withers up the back of the head (over the body's edge)
  if (lvl && head) fire(at("head", k.head), along(highest(head).map((v) => v * 0.75), lvl.mane), 1, "mane");
  if (parts.wing) drawShapes(p, parts.wing, at("wing", k.wing), col, boil, `${o.seed}:wing`, lt);
  if (parts.arm) drawArm(0, 0);
  if (!o.headless && def.face) face(parts.head ? at("head", k.head) : body);
  if (W.length) wear(false);
  // rider (@ride; o.rider: drawStickman options): straddling the back, over the body and saddle, moving with the
  // gait. Drawn facing right on its own card (this card mirrors for "left"), hip on the back anchor.
  if (o.rider) {
    const seat = body(creatureAnchors(def).back[0][1].map((v, i) => v + (i ? RIDE.sink : 0)));
    const opts = { ...o.rider, facing: "right", mirrored: o.facing === "left", straddle: true };
    riderCv = riderCv || Object.assign(canvas.ownerDocument.createElement("canvas"), { width: CW, height: CH });
    drawStickman(riderCv, opts);
    g.drawImage(riderCv, seat[0] - CW / 2, seat[1] - skeleton(opts).hipY);
  }

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
      else if (lvl) { p.dot(x, y, FACE.eye + 6); p.dot(x, y, FACE.eye + 2, pal[2]); } // glowing: a big flame-core dot, ink rim
      else {
        p.dot(x, y, FACE.eye);
        if (STYLE.creature?.eye) p.dot(x + FACE.eye * 0.3, y - FACE.eye * 0.35, FACE.eye * STYLE.creature.eye, "#ffffff"); // catchlight
      }
    }
    if (mouth && open > 0.05) { const [x, y] = T(mouth); p.poly(wobble(x, y, FACE.mouth / 2, 3 + 12 * open, rng(o.seed, "mouth"), boil, 0.04, 0.02, 16), INK, 0); }
  }
}
