// Side-view chicken cast member (series.json cast body "chicken") in the stickman's marker style: flat-colour body
// blob with a thick outline, fan tail, wing, stick legs, round head with comb, beak and wattle; headless swaps the
// head for a neck stump. Drawn on the stickman's CW x CH card with the feet on FEET_Y, so placement, cars and
// lying work unchanged; facing "left" mirrors, "camera" draws the side view. Pure function of its options.
import { Pen } from "./borrowed.js";
import { rng } from "./rng.js";
import { CH, CW, FEET_Y, jitter, wobble } from "./stickman.js";

const INK = "#1c1a1a", LEGS = "#e8a33a", COMB = "#d23c3c", CUT = "#9e1f22", BEAK = "#f0b13a";
const TAU = Math.PI * 2, deg = (d) => (d * Math.PI) / 180;
const LEG = 120, HIP = [256, FEET_Y - LEG], SIT = 100; // SIT: hip drop px when sitting down
// body blob centre (from the hip), size; neck base and head centre (from the body centre, before pitch)
const BODY = { dx: -10, dy: -80, rx: 130, ry: 92 }, NECK = [90, -40], HEAD = [118, -160], HEAD_R = 50;
const STEPS = 2;          // chicken steps per stickman stride: short legs, quick feet
const SWING = { walk: 26, run: 38, stagger: 22 }; // leg swing degrees
const MOVING = new Set(["walk", "run", "stagger", "carry", "support", "supported", "carried"]);
const FLAPPY = new Set(["react", "cheer", "angry", "gasp"]);
/** standing chicken height in canvas px (feet to comb top), for the camera: with and without a head */
export const CHICKEN_PX = { head: LEG - BODY.dy - HEAD[1] + HEAD_R + 32, headless: LEG - BODY.dy - HEAD[1] - 10 };
export const SEAT_LIFT = 230; // seated in a car: lift so the body clears the side panel (stickman hips sit higher)

/** pose from the drawing options: leg angles (deg, + forward), body pitch (deg, + nose down), wing flap 0..1,
 *  hip drop px. Pure; legs depend only on the gait phase. */
export function chickenPose(o) {
  const act = o.action, t = o.t || 0, s = Math.cos(TAU * STEPS * (o.phase || 0)); // a quarter stride is a full step
  const gait = MOVING.has(act) ? (SWING[act] || SWING.walk) * s : 0;
  let pitch = act === "run" ? 12 : act === "walk" ? 4 : 0, flap = 0;
  if (act === "stagger" || act === "supported") {
    const sway = o.stagger ? o.stagger.sway : Math.sin(TAU * 0.7 * t);
    pitch += 10 * sway; flap = 0.5 + 0.5 * Math.sin(TAU * 3.1 * t); // lurching, wings out for balance
  }
  if (act === "run") flap = 0.5 + 0.5 * Math.sin(TAU * 5 * t);
  if (FLAPPY.has(act)) flap = (o.mood ? o.mood.k : 1) * (0.5 + 0.5 * Math.sin(TAU * 4 * t));
  if (act === "wave") flap = (o.wave ? o.wave.k : 1) * (0.5 + 0.5 * Math.sin(TAU * 2 * t));
  if (act === "point") flap = 0.6 * (o.pointK ?? 1);
  if (act === "eat") pitch = 50 * Math.abs(Math.sin(TAU * 1.6 * t)); // pecking at the ground
  // lie / collapse: the chicken sinks onto its belly (buckle 0..1), legs tucked under; the card never rolls
  const sit = act === "lie" ? 1 : o.buckle || 0;
  return { legs: [gait, -gait], pitch, flap, drop: SIT * sit };
}

const rot = ([x, y], [cx, cy], a) => {
  const c = Math.cos(a), s = Math.sin(a), dx = x - cx, dy = y - cy;
  return [cx + dx * c - dy * s, cy + dx * s + dy * c];
};

/** o: drawStickman options plus top.color (feathers) and headless (bool). Uses action, phase, t, boil, breath,
 *  mouth (beak), lid (blink), facing, seated, buckle, stagger, mood, wave, pointK; ignores expression and props. */
export function drawChicken(canvas, o) {
  const g = canvas.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, CW, CH);
  if (o.facing === "left") g.setTransform(-1, 0, 0, 1, CW, 0);
  if (o.seated) g.translate(0, -SEAT_LIFT);
  const p = new Pen(g, INK), boil = rng(o.seed, "boil", o.boil), J = (pts, a = 2.5) => jitter(pts, boil, a);
  const k = chickenPose(o), feather = (o.top && o.top.color) || o.color || "#f2f2f2";
  const hip = [HIP[0], HIP[1] + k.drop], pa = deg(k.pitch);
  const R = (pt) => rot(pt, hip, pa); // body parts pitch about the hip

  // legs with three forward toes; the far leg first, a shade behind
  if (k.drop < SIT * 0.9) [1, 0].forEach((i) => {
    const a = deg(k.legs[i]), len = LEG - k.drop * 0.6, hx = hip[0] + (i ? 12 : -12);
    const foot = [hx + Math.sin(a) * len, Math.min(FEET_Y, hip[1] + Math.cos(a) * len)];
    p.stroke(J([[hx, hip[1]], [(hx + foot[0]) / 2 + 6, (hip[1] + foot[1]) / 2], foot]), 9, LEGS);
    for (const [dx, dy] of [[34, 2], [26, -10], [-16, 0]]) p.stroke(J([foot, [foot[0] + dx, foot[1] + dy]], 1.5), 7, LEGS);
  });

  const bc = [hip[0] + BODY.dx, hip[1] + BODY.dy], ry = BODY.ry * (1 + 0.03 * (o.breath || 0));
  // tail: three rounded feathers fanning up and back from the rump
  [[-125, -70, 40], [-140, -40, 20], [-140, -8, 2]].forEach(([x, y, a], i) => {
    const c = [bc[0] + x, bc[1] + y], f = wobble(c[0], c[1], 58, 24, rng(o.seed, "tail", i), boil, 0.06, 0.02, 24);
    p.poly(f.map((pt) => R(rot(pt, c, deg(a)))), feather, 10);
  });
  // neck (drawn before the body so the body overlaps its base)
  const nb = R([bc[0] + NECK[0], bc[1] + NECK[1]]), hc = R([bc[0] + HEAD[0], bc[1] + HEAD[1]]);
  const nw = 34, nx = (hc[0] - nb[0]), ny = (hc[1] - nb[1]), nl = Math.hypot(nx, ny), ux = -ny / nl, uy = nx / nl;
  const top = o.headless ? [nb[0] + nx * 0.72, nb[1] + ny * 0.72] : hc;
  p.poly(J([[nb[0] - ux * nw, nb[1] - uy * nw], [top[0] - ux * nw * 0.8, top[1] - uy * nw * 0.8],
    [top[0] + ux * nw * 0.8, top[1] + uy * nw * 0.8], [nb[0] + ux * nw, nb[1] + uy * nw]]), feather, 11);
  // body blob (rotated points of a wobbly ellipse)
  const body = wobble(bc[0], bc[1], BODY.rx, ry, rng(o.seed, "body"), boil).map((pt) => R(rot(pt, bc, deg(-8))));
  p.poly(body, feather, 12 + boil());
  // wing: a teardrop on the body that lifts about its front end when flapping
  const sh = R([bc[0] + 50, bc[1] - 25]), wa = -deg(70) * k.flap;
  const wing = [[50, -25], [0, -40], [-70, -20], [-85, 5], [-40, 25], [20, 15]]
    .map(([x, y]) => rot(R([bc[0] + x, bc[1] + y]), sh, wa));
  p.poly(J(wing), feather, 10);
  p.stroke(J([rot(R([bc[0] - 20, bc[1] - 5]), sh, wa), rot(R([bc[0] - 60, bc[1] + 8]), sh, wa)], 1.5), 6);

  if (o.headless) {
    // the cut: a dark red oval capping the stump
    const ang = Math.atan2(ny, nx) + Math.PI / 2;
    const cut = wobble(top[0], top[1], nw * 0.85, 14, rng(o.seed, "cut"), boil, 0.06, 0.03, 20).map((pt) => rot(pt, top, ang));
    p.poly(cut, CUT, 8);
    return;
  }
  // head: comb behind, round head, beak (opens with mouth), wattle, eye
  const [hx, hy] = hc, open = Math.max(0, Math.min(1, o.mouth || 0));
  const comb = [[-30, -30], [-26, -70], [-8, -48], [4, -84], [18, -50], [36, -72], [34, -30]].map(([x, y]) => [hx + x, hy + y]);
  p.poly(J(comb), COMB, 9);
  p.poly(J([[hx + 30, hy + 30], [hx + 22, hy + 82], [hx + 2, hy + 74], [hx + 6, hy + 34]]), COMB, 8);
  p.poly(wobble(hx, hy, HEAD_R, HEAD_R * 0.96, rng(o.seed, "head"), boil), feather, 11);
  const gap = 16 * open;
  p.poly(J([[hx + 40, hy - 6], [hx + 92, hy + 4 - gap * 0.4], [hx + 44, hy + 14]], 1.5), BEAK, 7);
  p.poly(J([[hx + 44, hy + 14], [hx + 82, hy + 12 + gap], [hx + 42, hy + 24]], 1.5), BEAK, 7);
  if ((o.lid || 0) >= 0.5) p.stroke(J([[hx + 6, hy - 10], [hx + 26, hy - 10]], 1), 6);
  else p.dot(hx + 16, hy - 12, 9);
}
