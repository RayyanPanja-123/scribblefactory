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
export const POINT_ARM = { rise: 0.15, hold: 0.8, fall: 0.3 }; // seconds: up, held until 0.8 s, then down
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
