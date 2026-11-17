// Extras (non-cast stickmen): seeded looks and crowd-mood timing. Pure functions (Node-testable): same inputs, same
// look / pose. Drawn with drawStickman like the cast, in the same marker style.
import { rng } from "./rng.js";

const TAU = Math.PI * 2;
// muted tops so the cast stays the colour that reads first
export const EXTRA_TOPS = ["#7a6a58", "#6f7d8c", "#8c7b6b", "#5f6f5e", "#8a6f6f", "#6b6f86", "#9a8f7a", "#7d7d74"];
const HATS = ["#4a4a4a", "#5a4632", "#3d3d46"], TROUSERS = ["#3a3530", "#43464d", "#4d4338"];
export const MOOD_EXPRESSION = { cheer: "happy", angry: "angry", gasp: "surprised", neutral: "neutral" };
export const MOOD = { cheerHz: 1.6, shakeHz: 4, offset: 2.0 }; // pumps / shakes per second; up to 2 s timing offset

/** look of extra e ({ kind, variant }) in series `slug`: crowd: plain or shirt top, maybe a flat cap or bowler,
 *  maybe trousers; runner: tank top with a 2-digit number, dark shorts. Fields as a series.json cast entry. */
export function extraLook(slug, e) {
  const R = rng(slug, "extra", e.kind, e.variant), pick = (xs) => xs[Math.floor(R() * xs.length)];
  const color = pick(EXTRA_TOPS), eyes = R() < 0.25 ? "half_closed" : "dots";
  if (e.kind === "runner") {
    return { top: { style: "tank", color, number: String(10 + Math.floor(R() * 90)) }, eyes,
      headwear: { kind: "none" }, legwear: { kind: "shorts", color: "#2b2b2b" }, props: [] };
  }
  const style = R() < 0.5 ? "plain" : "shirt", h = R();
  const headwear = h < 0.3 ? { kind: "flat_cap", color: pick(HATS) } : h < 0.5 ? { kind: "bowler", color: pick(HATS) } : { kind: "none" };
  const legwear = R() < 0.6 ? { kind: "trousers", color: pick(TROUSERS) } : { kind: "none" };
  return { top: { style, color }, eyes, headwear, legwear, props: [] };
}

/** crowd mood pose at time t for the figure keyed `key` (each one's timing offset, so a crowd never moves in sync):
 *  { k 0..1 arms into the mood pose, bounce 0..1 (cheer hops), shake -1..1 (angry fists) } */
export function moodAt(mood, t, key) {
  const tt = t + rng(key, "mood")() * MOOD.offset;
  if (mood === "cheer") {
    const s = Math.sin(TAU * MOOD.cheerHz * tt);
    return { k: 0.75 + 0.25 * s, bounce: Math.max(0, s), shake: 0 };
  }
  if (mood === "angry") return { k: 1, bounce: 0, shake: Math.sin(TAU * MOOD.shakeHz * tt) };
  if (mood === "gasp") return { k: 1, bounce: 0, shake: 0.15 * Math.sin(TAU * 7 * tt) }; // a small tremble
  return { k: 0, bounce: 0, shake: 0 };
}
