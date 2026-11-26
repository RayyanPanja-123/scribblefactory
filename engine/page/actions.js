// Step 5c-6 actions: timing, gait and placement. Pure functions of (seed, shot, time / distance): no three.js, no
// randomness outside rng(), so Node tests import this file directly (like motion.js). Drawing is in stickman.js.
import { glide } from "./borrowed.js";
import { rng } from "./rng.js";
import { STYLE } from "./style.js";

const TAU = Math.PI * 2;
const clamp = (v, lo = -1, hi = 1) => Math.min(hi, Math.max(lo, v));

// world units per full gait cycle (two steps). Every walking gait is driven by distance, so no distance = no step.
export const STRIDE = { walk: 1.0, run: 1.8, stagger: 0.7, carry: 0.9, support: 0.9, supported: 0.7 };
export const PEDAL_HZ = 1.5;          // carried: legs cycle in the air at this rate (time, not distance)
export const CARRIED_LIFT = 0.22;     // carried: world units the card is lifted (feet never touch the ground)
export const HELD_Z = -0.12;          // carried / supported stand a little behind their holders (draw order)
export const HOLD_GAP = 0.42;         // x from a holder to the actor it holds (pipeline shots.py HOLD_GAP: keep equal)
// lying: card lift (world units, half the figure's thickness), breath period (s), how far a non-wide camera drops
export const LIE = { lift: 0.25, breath: 5.0, drop: 0.65 };
export const COLLAPSE_S = 0.6;        // collapse: standing -> lying over this long, then it lies
export const EAT = { period: 2.6, rise: 0.45, hold: 1.0, fall: 0.45, chewHz: 3 }; // seconds
export const GIVE = { reach: 0.3, swap: 0.5, lower: 0.8 };  // shot fractions: arms out by 0.3, prop swaps at 0.5
export const ZZZ = { every: 3.2, show: 2.2 };             // sleeping: a rising "Z" trail for 2.2 s of every 3.2 s

// every built-in actor action: code in stickman.js / creatures.js / main.js (pipeline schemas ACTIONS: keep equal).
// Any other action is custom: library/actions.json keyframes (library.js), played by customPose.
export const BUILTIN_ACTIONS = new Set(["idle", "walk", "run", "talk", "point", "react", "wave", "ride", "stagger", "lie",
  "collapse", "eat", "give", "receive", "carry", "carried", "support", "supported", "cheer", "angry", "gasp", "salute",
  "pickup", "drop", "open", "close", "push", "sit", "enter", "exit", "stand", "don", "climb"]);
// don <item> (actor.wear: a wardrobe item id, e.g. a crown): both hands rise to the head, the item appears there at `swap`
// (a shot fraction) and the hands lower. Every later shot of the part has it on from the start (the planner keeps a.wear).
export const DON = { swap: 0.5, up: 0.3, down: 0.75, arms: [[-152, -55], [152, 55]] };
/** the don arm motion as a customPose def over a shot of `secs` seconds (times are shot fractions) */
export const donDef = (secs) => ({ duration: secs, loop: false, keys: [{ t: 0 }, { t: DON.up, arms: DON.arms, ease: "back-out" },
  { t: DON.swap + 0.1, arms: DON.arms }, { t: DON.down }, { t: 1 }] });
/** is actor a's worn item (a.wear) on at shot fraction u? A don puts it on at DON.swap; any other action wears it throughout */
export const wearOn = (a, u) => !!a.wear && (a.action !== "don" || u >= DON.swap);
/** height of actor a above the ground at shot fraction u (a @do climb along a set's trail): start_y to end_y, smooth, or
 *  in a.steps stairs (each rises smoothly, then rests): the card goes up with the walk */
export const heightAt = (a, u) => {
  const dy = (a.end_y ?? a.start_y ?? 0) - (a.start_y ?? 0);
  if (!dy) return a.start_y ?? 0;
  const k = a.steps ? (s => { const i = Math.min(a.steps - 1, Math.floor(s)); return (i + EASES["in-out"](s - i)) / a.steps; })(u * a.steps) : u;
  return a.start_y + dy * Math.min(1, Math.max(0, k));
};
// World Item interactions (actor.item: the @item tag): the hand reaches for this anchor of the item (schema
// WorldObject anchors), on giveAt's timing; enter / exit reach for the handle as they step in / out
export const ITEM_REACH = { pickup: "pickup", drop: "pickup", open: "handle", close: "handle", push: "handle",
  enter: "handle", exit: "handle" };
// sit / stand: sitting down after an approach walk takes SIT_LAND of the rest of the shot, getting up STAND_UP of it
export const SIT_LAND = 0.3, STAND_UP = 0.4;
// an approach walk passes behind actors in its way: z dips by PASS.z around each (blocker x), smoothly to 0 at PASS.w
export const PASS = { z: -0.5, w: 0.75 };
/** z offset at world x of a walk passing behind actors at xs (actor.behind): a pure function of x */
export const passBehind = (xs, x) => PASS.z * Math.max(0, ...xs.map((b) => { const d = Math.abs(x - b) / PASS.w; return d < 1 ? (1 - d * d) ** 2 : 0; }));
/** shot share u as an item action's own timeline: after an approach walk (actor.approach) it starts on arrival */
export const actU = (a, u) => (a.approach ? Math.max(0, (u - a.approach) / (1 - a.approach)) : u);
// sit: side on, thighs level, shins hanging (customPose shape; the planner turns the sitter side on). The hips go on
// the item's seat anchor (main.js perchedAt).
export const SIT = { arms: [[-16, 0], [16, 0]], legs: [82, 82], knees: [92, 92], lean: 0 };
/** canvas arm side (-1 / +1) of actor a toward item `it` at the shot's start (sideToward): the hand an item is held in */
export const itemSide = (a, it) => sideToward(a.start_pos[0], it.start_pos[0], a.facing);

export const REST = { arms: [[-16, 0], [16, 0]], legs: [-6, 6], knees: [0, 0], lean: 0 }; // the idle stickman, degrees (stickman.js)
// per-key easing (schema ActionKey.ease): how the pose moves INTO that key from the one before. in-out (default) is
// the smoothstep every custom action always used; back-out overshoots a little and settles
const BACK = 1.70158;
export const EASES = {
  linear: (u) => u,
  "in-out": (u) => u * u * (3 - 2 * u),
  "back-out": (u) => 1 + (BACK + 1) * (u - 1) ** 3 + BACK * (u - 1) ** 2,
  // S-curves for the camera (motion.js cameraProgress, fovPunch); not offered to custom actions (schema ActionKey.ease)
  "cubic-in-out": (u) => (u < 0.5 ? 4 * u ** 3 : 1 - (2 - 2 * u) ** 3 / 2),
  "quintic-out": (u) => 1 - (1 - u) ** 5,
};
const easeOf = (key) => EASES[key.ease] || EASES["in-out"];
/** a custom action (schema CustomAction) at ts seconds into its shot: { arms [[upper, bend] x2], legs [l, r], knees [l, r], lean },
 *  degrees from straight down, + toward +x. Eased between the keys; a key leaving a part out holds it at rest. A
 *  looping action wraps from its last key back to its first; a once action holds its last key. */
export function customPose(def, ts) {
  const keys = def.keys.map((k) => ({ t: k.t, arms: k.arms ?? REST.arms, legs: k.legs ?? REST.legs, knees: k.knees ?? REST.knees, lean: k.lean ?? 0,
    ease: k.ease, snap: !!k.snap }));
  const base = blendPose(def, keys, ts), off = springOffset(def, keys, ts);
  if (!off) return base;
  const v = flat(base).map((x, i) => Math.min(LIMITS[i][1], Math.max(LIMITS[i][0], x + off[i])));
  return { arms: [[v[0], v[1]], [v[2], v[3]]], legs: [v[4], v[5]], knees: [v[6], v[7]], lean: v[8] };
}

// a pose as 9 numbers (arms, legs, knees, lean) and each one's range (schema ActionKey): an overshoot never bends past it
const flat = (k) => [...k.arms.flat(), ...k.legs, ...k.knees, k.lean];
const LIMITS = [[-180, 180], [-180, 180], [-180, 180], [-180, 180], [-90, 90], [-90, 90], [0, 170], [0, 170], [-60, 60]];

/** anticipation + overshoot (style.js stickman.life.spring) on top of the eased blend at ts s, per pose number, or
 *  null when there is none. Each key change of `min`..`full` degrees (its largest joint change) dips the other way
 *  for anticFrames as it starts and springs past the key as it lands (one overshoot, settled in `settle` frames),
 *  both scaled 0..1 by its size; a move quicker than a settle gets no dip, and no spring when the next change
 *  starts before it settles (full from 1.5 settles)
 *  (fast keys, quick loops: no rubbery wobble). A key with snap: true, or eased back-out (its own overshoot), gets
 *  neither. A looping action wraps (its last key springs into the first). Pure in ts. */
function springOffset(def, keys, ts) {
  const P = STYLE.stickman.life.spring, d = def.duration, n = keys.length;
  if (!(P.antic || P.over) || n < 2) return null;
  const moves = [];
  for (let j = 1; j < n + (def.loop ? 1 : 0); j++) { // key j-1 -> key j (the loop's last: key n-1 -> key 0 a cycle on)
    const a = keys[j - 1], b = keys[j % n];
    moves.push({ start: a.t * d, end: (b.t + (j === n ? 1 : 0)) * d, a, b });
  }
  moves.forEach((m, i) => { const nx = moves[i + 1] ?? (def.loop ? moves[0] : null); m.room = nx ? (nx.end - nx.start) : Infinity; });
  const tc = def.loop ? ((ts % d) + d) % d : ts, out = new Array(9).fill(0), S = P.settle / 30;
  let any = false;
  for (const m of moves) {
    if (m.b.snap || m.b.ease === "back-out") continue;
    const delta = flat(m.b).map((v, i) => v - flat(m.a)[i]), size = Math.max(...delta.map(Math.abs));
    const k = Math.min(1, Math.max(0, (size - P.min) / Math.max(1e-6, P.full - P.min)));
    if (!k) continue;
    // fast keys (waves, quick loops): a move shorter than a settle gets no wind-up, and no spring when the next one
    // starts before it could settle; both full from 1.5 settles
    const fit = (len) => (S > 0 ? Math.min(1, Math.max(0, (len - S) / (S / 2))) : 1);
    const A = Math.min(P.anticFrames / 30, (m.end - m.start) / 2), quick = fit(m.end - m.start), room = fit(m.room);
    for (const shift of def.loop ? [0, d] : [0]) {
      const tau = tc + shift - m.start, after = tc + shift - m.end;
      let w = 0;
      if (A > 0 && tau >= 0 && tau < A) w -= P.antic * quick * Math.sin((Math.PI * tau) / A);
      if (S > 0 && after >= 0 && after < S) w += P.over * room * Math.exp((-4 * after) / S) * Math.sin((2 * Math.PI * after) / S);
      if (w) { any = true; delta.forEach((v, i) => { out[i] += v * k * w; }); }
    }
  }
  return any ? out : null;
}

/** the eased blend between keys at ts s (no spring) */
function blendPose(def, keys, ts) {
  const d = def.duration, u = def.loop ? (((ts % d) + d) % d) / d : Math.min(1, Math.max(0, ts / d));
  let i = keys.findIndex((k) => k.t > u);
  if (i === -1) { // past the last key: loop back to the first, or hold
    if (!def.loop || keys.length === 1) return keys[keys.length - 1];
    const a = keys[keys.length - 1], b = { ...keys[0], t: keys[0].t + 1 };
    return mix(a, b, easeOf(b)((u - a.t) / Math.max(1e-6, b.t - a.t)));
  }
  if (i === 0) return keys[0];
  const a = keys[i - 1], b = keys[i];
  return mix(a, b, easeOf(b)((u - a.t) / Math.max(1e-6, b.t - a.t)));
}
const lerp = (a, b, k) => a + (b - a) * k;
/** pose a blended k of the way to pose b (customPose shape): sitting down / getting up */
export const poseMix = (a, b, k) => mix(a, b, k);
const mix = (a, b, k) => ({ arms: a.arms.map((arm, s) => arm.map((v, j) => lerp(v, b.arms[s][j], k))),
  legs: a.legs.map((v, s) => lerp(v, b.legs[s], k)), knees: a.knees.map((v, s) => lerp(v, b.knees[s], k)), lean: lerp(a.lean, b.lean, k) });

/** gait phase (cycles): walking gaits from distance travelled (no gliding), carried legs pedal by time */
export function gaitPhase(action, distance, ts) {
  if (action === "carried") return PEDAL_HZ * ts;
  return STRIDE[action] ? distance / STRIDE[action] : 0;
}

/** stagger at gait phase: sway -1..1 (sideways lean, uneven: two beats that never line up) and buckle 0..1 (knees
 *  dip on seeded steps, about one step in three). Same key and phase -> same pose. */
export function staggerAt(key, phase) {
  const R = rng(key, "stagger"), a = R() * TAU, b = R() * TAU;
  const sway = clamp(0.7 * Math.sin(Math.PI * phase + a) + 0.3 * Math.sin(2.3 * Math.PI * phase + b));
  const step = Math.floor(phase * 2), f = phase * 2 - step; // two steps per cycle
  const buckle = rng(key, "buckle", step)() < 0.35 ? Math.sin(Math.PI * f) : 0;
  return { sway, buckle };
}

/** collapse at shot time ts: buckle 0..1 (knees give way first), fall 0..1 (0 standing, 1 lying; accelerating) */
export function collapseAt(ts) {
  const u = clamp(ts / COLLAPSE_S, 0, 1);
  const fall = u < 0.35 ? 0 : ((u - 0.35) / 0.65) ** 2;
  return { buckle: glide(u / 0.4), fall };
}

/** eat at shot time ts: k 0..1 (prop hand at the mouth), chew 0..1 (mouth opening while at the mouth and just after) */
export function eatAt(ts) {
  const c = ts % EAT.period, top = EAT.rise + EAT.hold;
  const k = Math.min(glide(c / EAT.rise), 1 - glide((c - top) / EAT.fall));
  const chewing = c > EAT.rise * 0.8 && c < top + EAT.fall;
  return { k, chew: chewing ? Math.abs(Math.sin(Math.PI * EAT.chewHz * c)) : 0 }; // locked to the loop
}

/** give / receive at shot fraction u: reach 0..1 (both arms out toward each other), who holds the prop */
export function giveAt(u) {
  const reach = Math.min(glide(u / GIVE.reach), 1 - glide((u - GIVE.lower) / (1 - GIVE.lower)));
  return { reach, held: u < GIVE.swap ? "giver" : "target" };
}

/** sleeping "Z" trail: 0..1 how far it has risen at time t, or null between trails (offset per character) */
export function zzzAt(key, t) {
  const c = (t + rng(key, "zzz")() * ZZZ.every) % ZZZ.every;
  return c < ZZZ.show ? c / ZZZ.show : null;
}

/** canvas arm side (-1 left arm, +1 right arm) that points from world x `from` toward world x `to`, for a figure
 *  facing `facing` ("left" cards are drawn mirrored) */
export const sideToward = (from, to, facing) => (to >= from ? 1 : -1) * (facing === "left" ? -1 : 1);
export const handOf = (side) => (side > 0 ? "right" : "left");

/** who holds which prop at the START of every shot: cast props, then each give hands its prop on for the following
 *  shots of the same run of one set (a set change resets to the cast props). With lookProps(id, look), an actor whose
 *  @look changes takes that look's props; an actor's own props (@hold) win over the look's. Map shot id ->
 *  { cast id: props }. itemProp(story item) -> the prop a World Item is held as after pickup (or null) */
export function propsByShot(shots, castProps, lookProps = null, itemProp = null) {
  const copy = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, v.map((p) => ({ ...p }))]));
  const out = new Map(), looks = {}, NONE = "[null,null]";
  let cur = null, set = null;
  for (const s of shots) {
    if (s.set !== set) { cur = copy(castProps); set = s.set; for (const k of Object.keys(looks)) delete looks[k]; }
    // a new @look or @hold brings its props; a give later in the look still moves them
    for (const a of s.actors) {
      const key = JSON.stringify([lookProps ? a.look ?? null : null, a.props ?? null]);
      if (key === (looks[a.cast_id] ?? NONE)) continue;
      looks[a.cast_id] = key;
      cur[a.cast_id] = (a.props ?? (lookProps ? lookProps(a.cast_id, a.look) : castProps[a.cast_id] ?? [])).map((p) => ({ ...p }));
    }
    out.set(s.id, copy(cur));
    for (const a of s.actors) { // pickup puts the item's prop in the hand toward it; drop takes it away
      const it = a.item && itemProp && (a.action === "pickup" || a.action === "drop") && (s.items || []).find((i) => i.id === a.item);
      const kind = it && itemProp(it);
      if (kind && a.action === "pickup") cur[a.cast_id] = withProp(cur[a.cast_id] || [], kind, handOf(itemSide(a, it)));
      if (kind && a.action === "drop") cur[a.cast_id] = (cur[a.cast_id] || []).filter((p) => p.kind !== kind);
    }
    for (const a of s.actors) {
      if (a.action !== "give" || !a.prop || !a.target) continue;
      cur[a.cast_id] = (cur[a.cast_id] || []).filter((p) => p.kind !== a.prop);
      const mine = cur[a.target] || [], free = ["right", "left"].find((h) => !mine.some((p) => p.hand === h));
      if (free) cur[a.target] = [...mine, { kind: a.prop, hand: free }];
    }
  }
  return out;
}

/** a prop list with `kind` in `hand` (whatever that hand held is put away) */
export const withProp = (props, kind, hand) => [...(props || []).filter((p) => p.hand !== hand && p.kind !== kind), { kind, hand }];

/** carried / supported: [x, z] at shot fraction u = its start spot moved like its holders (their mean), a little
 *  behind them. placeAt(actor, u) -> [x, z]; null when nobody holds it (draw it where it stands). */
export function heldPlace(a, actors, placeAt, u) {
  const role = a.action === "carried" ? "carry" : "support";
  const holders = actors.filter((h) => h.action === role && h.target === a.cast_id);
  if (!holders.length) return null;
  const mean = (pts) => [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length];
  const [x0, z0] = mean(holders.map((h) => placeAt(h, 0))), [x1, z1] = mean(holders.map((h) => placeAt(h, u)));
  return [a.start_pos[0] + x1 - x0, a.start_pos[1] + z1 - z0 + HELD_Z];
}
