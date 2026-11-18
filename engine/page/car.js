// Early-1900s open car, side view, in the stickman's marker style: boxy flat-colour body with a thick outline, big
// spoked wheels, bench seats, no roof. Drawn facing right on a VW x VH canvas, tyres on y = CAR_GROUND; "left" mirrors
// the card. Riders and the driver are drawStickman figures seated behind the side panel (legs hidden).
import { Pen, ellPts } from "./borrowed.js";
import { rng } from "./rng.js";
import { CH, CW, FEET_Y, drawStickman, jitter, wobble } from "./stickman.js";
import { drawChicken } from "./chicken.js";

export const VW = 1024, VH = 640, CAR_GROUND = 620;
export const CAR_CARD_W = 2.8;                    // world units across the card
const PX = VW / CAR_CARD_W;                       // canvas px per world unit
const WR = 118;                                   // wheel radius px
export const WHEEL_R = WR / PX;                   // wheel radius in world units
const WHEELS = [250, 780], WY = CAR_GROUND - WR;  // wheel centre x (rear, front), y
const SEAT_Y = 410;                               // seated hip height
export const DRIVER_X = 570, RIDER_X = [380, 280, 180]; // seat x (canvas px), riders front to back
const RIDER_SCALE = PX / (CH / 1.6);              // stickman canvas -> car canvas (same world scale as actors)
const HIP_PX = FEET_Y - 220 * Math.cos((6 * Math.PI) / 180); // standing hip height on the stickman canvas
const BOUNCE = { px: 3, every: 0.7 };            // body bobs 3 px per 0.7 world units driven
const INK = "#1c1a1a", LEATHER = "#4a2e1c", BRASS = "#c9a227", DUST = "#d9c7a0", SMOKE = "#9a9a9a";
// broken: grey marker puffs rise from the bonnet on a loop (seeded phase), the car shakes a little
export const BROKEN = { puffs: 3, rise: 1.6, height: 190, x: 760, y: 352, shake: [2.2, 1.4] };
export const CAR_COLOURS = { red: "#c0392b", green: "#2e7d4f", navy: "#2c3e72", yellow: "#e2b33c" };

/** wheel turn (radians) after driving `distance` world units: rolling, never sliding */
export const wheelAngle = (distance) => distance / WHEEL_R;

/** 0..1 share of the way driven at shot fraction u: arrive eases to a stop, leave eases out from one */
export function carEase(action, u) {
  if (action === "arrive") return 1 - (1 - u) * (1 - u);
  if (action === "leave") return u * u;
  return action === "drive" ? u : 0;
}

/** current speed as a share of the average (for dust): arrive 2 -> 0, leave 0 -> 2, drive 1, idle 0 */
export function carSpeedShare(action, u) {
  return action === "arrive" ? 2 * (1 - u) : action === "leave" ? 2 * u : action === "drive" ? 1 : 0;
}

/** world x offset of a seat from the car centre (facing right; mirror for left) */
export const seatOffset = (seatX) => (seatX - VW / 2) / PX;

let tmp = null; // scratch canvas for one seated figure

/** o: { seed, boil, variant, facing, distance (driven, world units), moving (bool), dust (0..1), broken (bool), t (s),
 *       driver: drawStickman options, riders: [drawStickman options] front to back } */
export function drawCar(canvas, o) {
  const g = canvas.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, VW, VH);
  if (o.facing === "left") g.setTransform(-1, 0, 0, 1, VW, 0);
  const p = new Pen(g, INK), boil = rng(o.seed, "boil", o.boil), body = CAR_COLOURS[o.variant] || CAR_COLOURS.red;
  const dist = o.distance || 0;
  const dy = o.moving ? BOUNCE.px * Math.sin((2 * Math.PI * dist) / BOUNCE.every) : 0;
  const J = (pts, amp = 2) => jitter(pts, boil, amp);
  const t = o.t || 0, sh = o.broken ? [BROKEN.shake[0] * Math.sin(t * 37), BROKEN.shake[1] * Math.sin(t * 29 + 1)] : [0, 0];

  // dust: a few marker puffs behind the rear wheel while driving on dirt
  if (o.dust > 0.02) {
    const R = rng(o.seed, "dust", o.boil);
    g.save(); g.globalAlpha = 0.85 * Math.min(1, o.dust);
    for (let k = 0; k < 3; k++) {
      const r = (16 + 9 * k) * (0.6 + 0.4 * o.dust) * (0.9 + 0.2 * R());
      p.poly(wobble(118 - 46 * k, CAR_GROUND - 22 - 10 * k, r, r * 0.8, rng(o.seed, "puff", k), boil, 0.08, 0.04, 20),
        DUST, 5);
    }
    g.restore();
  }

  g.save(); g.translate(sh[0], dy + sh[1]);
  // seat backs (behind the figures)
  p.poly(J([[140, 340], [148, 240], [204, 236], [210, 340]]), LEATHER, 10);
  p.poly(J([[468, 380], [474, 282], [516, 280], [522, 380]]), LEATHER, 10);
  // seated figures, clipped above the panel's lower edge so their legs never show
  g.save(); g.beginPath(); g.rect(0, 0, VW, 440); g.clip();
  const seat = (fig, x) => {
    tmp = tmp || Object.assign(canvas.ownerDocument.createElement("canvas"), { width: CW, height: CH });
    // the whole card mirrors for "left"; seated raises a held prop above the panel
    (fig.body === "chicken" ? drawChicken : drawStickman)(tmp, { ...fig, facing: "right", seated: true, mirrored: o.facing === "left" });
    g.drawImage(tmp, x - (CW / 2) * RIDER_SCALE, SEAT_Y - HIP_PX * RIDER_SCALE, CW * RIDER_SCALE, CH * RIDER_SCALE);
  };
  // driver first, then riders back to front: a rider's raised (waving) arm stays in front of the driver
  if (o.driver) seat(o.driver, DRIVER_X);
  (o.riders || []).map((r, i) => [r, RIDER_X[i]]).reverse().forEach(([r, x]) => seat(r, x));
  g.restore();
  // steering column and wheel (edge-on) in front of the driver
  p.stroke(J([[660, 400], [618, 300]]), 9);
  p.poly(ellPts(612, 296, 10, 34, 0, 360, -20, 20), null, 9);
  // body: rear tub, low middle, hood, brass radiator, under-frame
  p.poly(J([[128, 352], [150, 326], [472, 326], [476, 470], [136, 470]]), body, 12 + boil());
  p.poly(J([[470, 404], [648, 404], [650, 470], [470, 470]]), body, 12);
  p.poly(J([[640, 372], [876, 362], [884, 470], [644, 470]]), body, 12);
  p.poly(J([[876, 346], [912, 346], [914, 470], [880, 470]]), BRASS, 10);
  p.stroke(J([[150, 470], [904, 470]]), 14);
  p.dot(918, 334, 17, INK); p.dot(918, 334, 10, BRASS);  // headlamp
  // fenders over the wheels
  for (const x of WHEELS) p.stroke(J(ellPts(x, WY, WR + 20, WR + 20, 195, 345, 0, 16)), 13, body);
  for (const x of WHEELS) p.stroke(J(ellPts(x, WY, WR + 20, WR + 20, 195, 345, 0, 16)), 5);
  g.restore();

  if (o.broken) smoke(p, g, o.seed, boil, t);

  // wheels: tyre, rim, 10 spokes turned by the distance driven, hub
  const turn = wheelAngle(dist);
  for (const x of WHEELS) {
    p.poly(ellPts(x, WY, WR - 9, WR - 9, 0, 360, 0, 36), null, 18);
    p.poly(ellPts(x, WY, WR - 26, WR - 26, 0, 360, 0, 36), null, 5);
    for (let k = 0; k < 10; k++) {
      const a = turn + (k * Math.PI) / 5;
      p.stroke([[x + 16 * Math.cos(a), WY + 16 * Math.sin(a)], [x + (WR - 26) * Math.cos(a), WY + (WR - 26) * Math.sin(a)]], 5);
    }
    p.dot(x, WY, 17, INK); p.dot(x, WY, 8, BRASS);
  }
}

/** broken down: BROKEN.puffs grey puffs, each rising from the bonnet and growing as it fades, staggered in time */
function smoke(p, g, seed, boil, t) {
  const off = rng(seed, "smoke")();
  for (let k = 0; k < BROKEN.puffs; k++) {
    const u = (t / BROKEN.rise + off + k / BROKEN.puffs) % 1, r = 18 + 42 * u;
    g.save(); g.globalAlpha = 0.85 * (1 - u);
    p.poly(wobble(BROKEN.x - 24 * u + 10 * Math.sin(6 * u + k), BROKEN.y - BROKEN.height * u, r, r * 0.85,
      rng(seed, "smoke", k), boil, 0.08, 0.04, 20), SMOKE, 5);
    g.restore();
  }
}
