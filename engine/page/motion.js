// Timing of talk gestures, the point arm and stressed-word bobs. Pure functions of (seed, shot, time):
// no three.js, no randomness outside rng(), so Node tests can import this file directly.
import { glide } from "./borrowed.js";
import { rng } from "./rng.js";

export const GESTURE = {
  minShot: 1.5,            // seconds: shorter talk shots never gesture
  chance: 0.35,            // share of eligible talk shots that get one gesture
  dur: [0.6, 1.0],         // seconds, gesture length incl. ease in/out
  ease: 0.2,               // seconds of ease at each end
  kinds: ["palm", "chin", "shrug"],
};
const POINT_ARM = { rise: 0.15, hold: 0.8, fall: 0.3 }; // seconds: up, held until 0.8 s, then down
export const STRESS = { minLetters: 5, dur: 0.25 };             // a word this long gets a small body bob

/** At most one gesture per talk shot: { kind, start, dur } in shot-local seconds, or null. Seeded, stable. */
export function gesturePlan(seed, shotId, castId, action, shotSeconds) {
  if (action !== "talk" || shotSeconds < GESTURE.minShot) return null;
  const R = rng(seed, shotId, castId, "gesture");
  if (R() >= GESTURE.chance) return null;
  const kind = GESTURE.kinds[Math.floor(R() * GESTURE.kinds.length)];
  const dur = GESTURE.dur[0] + R() * (GESTURE.dur[1] - GESTURE.dur[0]);
  return { kind, start: R() * (shotSeconds - dur), dur };
}

/** 0..1 how far into its pose the gesture is at shot-local time ts (eased in and out) */
export function gestureAmount(plan, ts) {
  if (!plan || ts < plan.start || ts > plan.start + plan.dur) return 0;
  return glide(Math.min(ts - plan.start, plan.start + plan.dur - ts) / GESTURE.ease);
}

/** 0..1 point arm: rises at the start of the shot, holds until POINT_ARM.hold, then lowers */
export function pointAmount(ts) {
  return Math.min(glide(ts / POINT_ARM.rise), 1 - glide((ts - POINT_ARM.hold) / POINT_ARM.fall));
}

/** 0..1 body bob for a talking actor at time t: a short lift on each stressed (long) word as it starts */
export function stressBob(t, words) {
  for (const w of words) {
    if (t >= w.start && t < w.start + STRESS.dur && w.text.replace(/[^A-Za-z]/g, "").length >= STRESS.minLetters) {
      return Math.sin((Math.PI * (t - w.start)) / STRESS.dur);
    }
  }
  return 0;
}

// Talk mouth: one open-close cycle per syllable group (merged words, about two syllables each), scheduled in frames.
export const MOUTH_MAX_HZ = 4;        // at most this many open-close cycles per second
export const MOUTH_MIN_OPEN_F = 4;    // frames a cycle stays open (at least)
export const MOUTH_MIN_CLOSED_F = 3;  // frames it then stays closed (at least)
const MOUTH_FPS = 30, SHORT_WORD = 3; // words of <= 3 letters merge into a neighbour's cycle
const MOUTH_LONG_F = 15; // a drawn-out syllable group gets one more cycle per ~15 frames instead of one long open
const MOUTH_MIN_PERIOD_F = Math.max(Math.ceil(MOUTH_FPS / MOUTH_MAX_HZ), MOUTH_MIN_OPEN_F + MOUTH_MIN_CLOSED_F);

const letters = (w) => w.text.replace(/[^A-Za-z]/g, "");
const syllables = (s) => Math.max(1, (s.toLowerCase().replace(/e$/, "").match(/[aeiouy]+/g) || []).length);

/** open-close cycles [{ start, open, len }] (frames) from phrases.json words/phrases. Cycles never overlap, never
 *  run faster than MOUTH_MAX_HZ and stay inside their phrase: a cycle whose open part would spill past the phrase's
 *  last word is dropped, so the mouth is shut between phrases. */
export function mouthCycles(words, phrases) {
  const cycles = [];
  let free = 0; // first frame the next cycle may start on
  for (const p of phrases) {
    const ws = words.slice(p.word_start, p.word_end + 1);
    const groups = [];
    let pend = null; // short words before the phrase's first long word wait for it
    for (const w of ws) {
      const L = letters(w), short = L.length <= SHORT_WORD;
      if (short && groups.length) groups.at(-1).end = w.end;
      else if (short) pend = { start: pend ? pend.start : w.start, end: w.end, syl: 1 };
      else { groups.push({ start: pend ? pend.start : w.start, end: w.end, syl: syllables(L) }); pend = null; }
    }
    if (pend) groups.push(pend); // a phrase of only short words: one cycle
    const pEnd = Math.round(ws.at(-1).end * MOUTH_FPS);
    for (const g of groups) {
      const n = Math.max(Math.ceil(g.syl / 2), Math.round(((g.end - g.start) * MOUTH_FPS) / MOUTH_LONG_F)), a = g.start * MOUTH_FPS, step = ((g.end - g.start) * MOUTH_FPS) / n;
      for (let j = 0; j < n; j++) {
        const start = Math.max(Math.round(a + j * step), free);
        const len = Math.max(MOUTH_MIN_PERIOD_F, Math.round(step));
        const open = Math.min(Math.max(Math.round(len / 2), MOUTH_MIN_OPEN_F), len - MOUTH_MIN_CLOSED_F);
        if (start + open > pEnd) break; // no room left in this phrase
        cycles.push({ start, open, len });
        free = start + len;
      }
    }
  }
  return cycles;
}

/** per-frame mouth opening 0..1 for frames 0..total-1. A cycle's open frames ease in and out inside the open
 *  part (0.5, 1, .., 1, 0.5), so the mouth never snaps 0 <-> 1 and open/closed frame counts stay exact. */
export function mouthCurve(cycles, total) {
  const out = new Float32Array(total);
  for (const c of cycles) {
    for (let k = 0; k < c.open && c.start + k < total; k++) out[c.start + k] = k === 0 || k === c.open - 1 ? 0.5 : 1;
  }
  return out;
}

// Wave: the right arm rises, waves side to side WAVE.count times (swing eased in and out), then lowers to rest.
export const WAVE = { rise: 0.25, count: 3, hz: 2.2, ease: 0.2, fall: 0.3 }; // seconds / waves per second

/** { k: 0..1 arm raised, swing: -1..1 forearm side to side } at shot-local time ts */
export function waveAmount(ts) {
  const end = WAVE.rise + WAVE.count / WAVE.hz;
  const k = Math.min(glide(ts / WAVE.rise), 1 - glide((ts - end) / WAVE.fall));
  if (ts < WAVE.rise || ts > end) return { k, swing: 0 };
  const env = glide(Math.min(ts - WAVE.rise, end - ts) / WAVE.ease);
  return { k, swing: env * Math.sin(2 * Math.PI * WAVE.hz * (ts - WAVE.rise)) };
}

// Camera timing (style.js camera): every move eases in and out; a reaction close-up holds still first so the reaction
// lands before the camera creeps.
import { STYLE } from "./style.js";
import { COLLAPSE_S, EASES } from "./actions.js";
const REACTIONS = new Set(["react", "gasp"]);
/** true for a close-up whose shot shows a reaction (an actor reacting or gasping, or a surprised face) */
export const isReactionClose = (shot) => shot.camera.angle === "close"
  && shot.actors.some((a) => REACTIONS.has(a.action) || a.expression === "surprised");
/** 0..1 how far the camera move has gone at shot fraction u: eased in-out, after a reaction close-up's hold */
export function cameraProgress(shot, u) {
  const secs = (shot.end_frame - shot.start_frame) / 30, hold = isReactionClose(shot) ? Math.min(STYLE.camera.reactionHold, secs / 2) : 0;
  const v = hold ? Math.max(0, (u * secs - hold) / (secs - hold)) : u;
  if (!STYLE.camera.ease) return Math.min(1, Math.max(0, v));
  if (STYLE.camera.life.legacyEase) return glide(v);
  return EASES[isFastPush(shot) ? "quintic-out" : "cubic-in-out"](Math.min(1, Math.max(0, v)));
}

/** a push-in fast enough to punch: speed >= life.punch.fastSpeed, or the twist's push */
export const isFastPush = (shot) => shot.camera.move === "push_in"
  && (!!shot.twist || shot.camera.speed >= STYLE.camera.life.punch.fastSpeed);

/** smooth 1D value noise, -1..1: seeded values on the integers (rng over keys + i), smoothstep between. Pure in x. */
export function noise1(x, ...keys) {
  const i = Math.floor(x), f = x - i, s = f * f * (3 - 2 * f);
  const a = 2 * rng(...keys, i)() - 1, b = 2 * rng(...keys, i + 1)() - 1;
  return a + (b - a) * s;
}

/** 0..1 camera trauma at t s: each trigger { t0, strength } falls off linearly over decay s; summed, then clamped */
export function trauma(t, triggers, decay) {
  let s = 0;
  for (const g of triggers) if (t >= g.t0) s += g.strength * Math.max(0, 1 - (t - g.t0) / decay);
  return Math.min(1, s);
}

/** shake triggers of a story.json: [{ t0 s, strength, kind }]. twist: its low_hit cue (finish shakes the captions
 *  there too); impact: every other low_hit cue (a loud hit lands: the camera only); collapse: the moment the body lands; lightning: each strike; fx: story.shakes (@fx shake); cam: a
 *  shot's camera.shake (@cam shake: the camera only, captions stay still). */
export function shakeTriggers(story) {
  const S = STYLE.camera.life.shake.strength, out = [], at = (frame, kind) => out.push({ t0: frame / 30, strength: S[kind], kind });
  for (const sh of story.shots || []) {
    if (sh.twist) at((story.cues || []).find((c) => c.kind === "low_hit" && c.frame >= sh.start_frame && c.frame < sh.end_frame)?.frame ?? sh.start_frame, "twist");
    if (sh.actors?.some((a) => a.action === "collapse")) at(sh.start_frame + COLLAPSE_S * 30, "collapse");
    if (sh.camera?.shake) at(sh.start_frame, "cam"); // @cam shake: the line's first word
  }
  const inTwist = (f) => (story.shots || []).some((sh) => sh.twist && f >= sh.start_frame && f < sh.end_frame);
  for (const c of story.cues || []) if (c.kind === "low_hit" && !inTwist(c.frame)) at(c.frame, "impact");
  for (const l of story.lightning || []) at(l.frame, "lightning");
  for (const f of story.shakes || []) at(f, "fx");
  return out;
}

/** fov degrees over the angle's own at shot-local ts: the punch keys of a fast push (cubic in-out between), plus a
 *  reaction's snap-zoom (snapZoom), else 0 */
export function fovPunch(shot, ts) {
  return pushPunch(shot, ts) + snapZoom(shot, ts);
}

/** snap-zoom of a reaction shot (style.js camera.life.snap): -zoom degrees of fov, reached over `dur` s on easeOutBack
 *  (overshoots, settles), when an actor does one of the snap actions; 0 otherwise */
export function snapZoom(shot, ts) {
  const Z = STYLE.camera.life.snap;
  if (!Z?.zoom || Z.skip.includes(shot.camera.angle) || !shot.actors.some((a) => Z.actions.includes(a.action))) return 0;
  return -Z.zoom * EASES["back-out"](Math.min(1, Math.max(0, ts / Z.dur)));
}

function pushPunch(shot, ts) {
  const P = STYLE.camera.life.punch, k = P.keys;
  if (!isFastPush(shot) || P.skip.includes(shot.camera.angle)) return 0;
  const i = k.findIndex(([t]) => t > ts);
  if (i <= 0) return i === 0 ? k[0][1] : k.at(-1)[1];
  const [t0, a] = k[i - 1], [t1, b] = k[i];
  return a + (b - a) * EASES["cubic-in-out"]((ts - t0) / (t1 - t0));
}

// Idle life (style.js idle): standing actors (idle, talk) breathe with a small bob and shift their weight slowly; each
// actor's phase is seeded, so two characters never sway in step.
const LIFE_ACTIONS = new Set(["idle", "talk"]);
/** { bob 0..1 (hip lift share, on top of a stressed-word bob), shift degrees (lean about the feet) } at time t for a
 *  standing actor, or null for any other action. key: the character's seed key. */
export function idleLife(key, t, action, breath) {
  if (!LIFE_ACTIONS.has(action)) return null;
  const I = STYLE.idle, ph = 2 * Math.PI * rng(key, "shift")();
  return { bob: I.bob * (0.5 + 0.5 * breath), shift: I.shift * Math.sin((2 * Math.PI * t) / I.shiftPeriod + ph) };
}
/** who actor a looks toward in its shot: whom it addresses (target), else the speaker, else (two-handers) the other
 *  one; null when nobody. actors: the shot's standing actors. */
export function lookTarget(a, actors) {
  const others = actors.filter((b) => b.cast_id !== a.cast_id);
  return others.find((b) => b.cast_id === a.target) || others.find((b) => b.action === "talk")
    || (actors.length === 2 ? others[0] : null);
}

// Pose pop (style.js stickman.life.pop): an actor that spawns (not in the previous shot, or on another set), changes
// pose or flips direction squashes then stretches back over `dur` s. idle <-> talk is the same standing pose.
const STANDING = new Set(["idle", "talk"]);
const samePose = (p, a) => p.facing === a.facing && (p.action === a.action || (STANDING.has(p.action) && STANDING.has(a.action)));
/** height share added to the squash `ts` s into actor a's shot; prev: the same cast member in the previous shot of
 *  the same set (or null / undefined: it spawns). Starts at 0, dips (squash), then stretches, damped. */
export function popAt(prev, a, ts) {
  const P = STYLE.stickman.life.pop;
  if (!P?.dur || !P.squash || ts >= P.dur || (prev && samePose(prev, a))) return 0;
  const u = ts / P.dur;
  return -P.squash * Math.sin(2 * Math.PI * u) * (1 - u);
}

/** 0..1 speech envelope at frame n: the mouth curve averaged over +- `span` frames (a smooth head-nod driver) */
export function speechEnv(mouth, n, span = STYLE.stickman.life.nod?.span ?? 3) {
  let s = 0, c = 0;
  for (let f = Math.max(0, n - span); f <= Math.min(mouth.length - 1, n + span); f++) { s += mouth[f]; c++; }
  return c ? s / c : 0;
}

// @mood (style.js mood): the grade shift of a shot. Parameters are the grade shader's (main.js grade): multiplicative
// contrast / saturation / exposure, additive warmth / lift, vignette, and haze of a tint colour.
const MOOD0 = { contrast: 1, saturation: 1, warmth: 0, lift: 0, exposure: 1, vignette: 0, haze: 0, tint: [1, 1, 1] };
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
/** the grade parameters of mood `name` (none / unknown: neutral) */
export function moodParams(name) {
  const m = name && STYLE.mood[name];
  return m && typeof m === "object" ? { ...MOOD0, ...m, tint: rgb(m.tint ?? "#ffffff") } : { ...MOOD0 };
}
/** mood parameters at held frame kf of shots[i]: its own, eased in from the previous shot's over mood.blend s */
export function moodLook(shots, i, kf) {
  const cur = moodParams(shots[i].mood), prev = i > 0 ? shots[i - 1].mood : null;
  if (prev === shots[i].mood) return cur;
  const k = glide(Math.min(1, (kf - shots[i].start_frame) / Math.max(1, STYLE.mood.blend * 30))), from = moodParams(prev);
  const out = {};
  for (const key of Object.keys(MOOD0)) out[key] = key === "tint" ? cur.tint.map((v, j) => from.tint[j] + (v - from.tint[j]) * k) : from[key] + (cur[key] - from[key]) * k;
  return out;
}
