// Side-view dog card in the stickman's marker style: flat-colour body blob with a thick outline, stick legs, round
// head with a dot eye, floppy ear, tail. No shading. Drawn facing right on a DW x DH canvas, paws at y = DOG_FEET;
// "left" mirrors the card. Pure function of its options, like drawStickman.
import { Pen, ellPts } from "./borrowed.js";
import { rng } from "./rng.js";
import { jitter, wobble } from "./stickman.js";

export const DW = 640, DH = 448, DOG_FEET = 428;
export const DOG_STRIDE = 1.2; // world units per gallop cycle: legs follow distance travelled, never time
export const BARK = { every: 9, open: 5, count: 3 }; // a burst of 3 yaps, 9 frames apart, mouth open 5 frames each
const INK = "#1c1a1a", TONGUE = "#ee6f80";
const TAU = Math.PI * 2, deg = (d) => (d * Math.PI) / 180;
const LEG = 118, GALLOP = 38, WAG_HZ = 2.2;
// body, ear (and patch) colours per variant
const COAT = {
  brown: ["#a0652f", "#5e3a1a"], black: ["#3a3532", "#55504b"],
  tan: ["#d8b07a", "#a77a43"], white_patches: ["#f6f3ec", "#7a4a22"],
};

export const gallopPhase = (distance) => distance / DOG_STRIDE;

/** 0..1 jaw opening of a barking dog at frame n: a yap burst starting at the shot's bark cue, the idx-th barking
 *  dog 3 frames later than the one before */
export function barkAmount(n, cueFrame, idx = 0) {
  const rel = n - cueFrame - 3 * idx;
  if (rel < 0 || rel >= BARK.every * BARK.count) return 0;
  const k = rel % BARK.every;
  return k < BARK.open ? Math.sin((Math.PI * (k + 0.5)) / BARK.open) : 0;
}

/** pose angles (degrees) from the action: legs [front near, front far, back near, back far] from straight down
 *  (+ = forward), tail up from straight back, ear swing back, body pitch; legs depend only on the gallop phase */
export function dogPose({ action, phase = 0, t = 0, breath = 0, yap = 0 }) {
  if (action === "run") {
    const s = TAU * phase;
    return {
      legs: [Math.sin(s), Math.sin(s - 0.7), Math.sin(s + Math.PI), Math.sin(s + Math.PI - 0.7)].map((v) => GALLOP * v),
      tail: 20 + 10 * Math.sin(2 * s), ear: 30 + 25 * Math.sin(s + 1), pitch: 4 * Math.sin(s), jaw: 0.35, tongue: true, breath: 0,
    };
  }
  return { legs: [4, -3, -4, 3], tail: 50 + 22 * Math.sin(TAU * WAG_HZ * t), ear: 6 + 3 * breath, pitch: 0,
    jaw: action === "bark" ? yap : 0, tongue: false, breath };
}

/** o: { seed, boil, variant, facing: left|right, action: run|idle|bark, phase, t, breath (-1..1), lid (0|0.5|1), yap } */
export function drawDog(canvas, o) {
  const g = canvas.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, DW, DH);
  if (o.facing === "left") g.setTransform(-1, 0, 0, 1, DW, 0);
  const p = new Pen(g, INK), boil = rng(o.seed, "boil", o.boil), pose = dogPose(o);
  const [coat, ear] = COAT[o.variant] || COAT.brown;
  const legs = pose.legs.map(deg);
  const cx = 300, yAtt = DOG_FEET - LEG * Math.max(...legs.map(Math.cos)); // the most upright leg is planted
  const cy = yAtt - 26, rx = 130, ry = 58 * (1 + 0.04 * pose.breath);
  const legX = [cx + 92, cx + 70, cx - 88, cx - 110];
  const leg = (i) => {
    const foot = [legX[i] + Math.sin(legs[i]) * LEG, yAtt + Math.cos(legs[i]) * LEG];
    p.stroke(jitter([[legX[i], yAtt], foot], boil), 10);
    p.dot(foot[0], foot[1], 8);
  };
  leg(1); leg(3); // far legs behind the body

  g.save();
  g.translate(cx, cy); g.rotate(deg(-pose.pitch)); g.translate(-cx, -cy);
  // tail: curved stroke from the rump, angle up from straight back
  const ta = deg(pose.tail), t0 = [cx - rx + 12, cy - 22];
  const tip = [t0[0] - 92 * Math.cos(ta), t0[1] - 92 * Math.sin(ta)];
  const mid = [(t0[0] + tip[0]) / 2 + 14 * Math.sin(ta), (t0[1] + tip[1]) / 2 - 14 * Math.cos(ta)];
  p.stroke(jitter([t0, mid, tip], boil), 11);
  // body blob (+ seeded patches for the white variant, clipped to the body)
  const body = wobble(cx, cy, rx, ry, rng(o.seed, "dogbody"), boil);
  p.poly(body, coat, 0);
  if (o.variant === "white_patches") {
    const R = rng(o.seed, "patches");
    g.save(); p.path(body, true); g.clip();
    for (let k = 0; k < 2; k++) p.poly(ellPts(cx - 70 + 120 * k + 30 * R(), cy - 30 + 40 * R(), 34 + 16 * R(), 26 + 10 * R()), ear, 0);
    g.restore();
  }
  p.poly(body, null, 12 + boil());
  g.restore();
  leg(0); leg(2);

  g.save();
  g.translate(cx, cy); g.rotate(deg(-pose.pitch)); g.translate(-cx, -cy);
  const hx = cx + 140, hy = cy - 62;
  p.poly(wobble(hx, hy, 54, 52, rng(o.seed, "doghead"), boil), coat, 12 + boil());
  // muzzle, nose, mouth: open jaw (bark / panting) is an ink wedge, tongue hangs out while running
  p.poly(wobble(hx + 52, hy + 18, 34, 22, rng(o.seed, "muzzle"), boil), coat, 10);
  if (pose.jaw > 0.05) {
    const j = 34 * pose.jaw;
    p.poly([[hx + 40, hy + 32], [hx + 86, hy + 30], [hx + 78, hy + 32 + j]], INK, 0); // hinged at the back
    if (pose.tongue) p.poly(ellPts(hx + 66, hy + 52 + 4 * Math.sin(TAU * (o.phase || 0)), 11, 18), TONGUE, 6);
  } else {
    p.stroke(jitter([[hx + 46, hy + 34], [hx + 78, hy + 32]], boil, 1.2), 6);
  }
  p.dot(hx + 84, hy + 10, 11);
  // eye: dot (white rim on a black coat so it reads); blinks close it
  const ex = hx + 16, ey = hy - 14;
  if (o.lid >= 1) p.stroke(jitter([[ex - 12, ey], [ex + 12, ey]], boil, 1.2), 6);
  else {
    if (o.variant === "black") p.dot(ex, ey, 14, "#ffffff");
    if (o.lid === 0.5) { p.dot(ex, ey + 3, 7); p.stroke([[ex - 12, ey], [ex + 12, ey]], 6); }
    else p.dot(ex, ey, 9);
  }
  // floppy ear: a teardrop hanging from the top of the head, swinging back
  const ea = deg(pose.ear), ax = hx - 14, ay = hy - 40;
  p.poly(ellPts(ax - 36 * Math.sin(ea), ay + 36 * Math.cos(ea), 19, 40, 0, 360, pose.ear, 24), ear, 9);
  g.restore();
}
