// Custom actions (library/actions.json): keyframes eased in time, looped or held, and the stickman posed by them.
import assert from "node:assert/strict";
import { test } from "node:test";
import { BUILTIN_ACTIONS, customPose } from "../page/actions.js";
import { skeleton } from "../page/stickman.js";

const SALUTE = { id: "salute", name: "Salute", duration: 2, loop: false, keys: [
  { t: 0 }, { t: 0.5, arms: [[-16, 0], [150, 70]], lean: 4 }] };
const DANCE = { id: "dance", name: "Dance", duration: 1, loop: true, keys: [
  { t: 0, legs: [-20, 6], lean: -10 }, { t: 0.5, legs: [-6, 20], lean: 10 }] };

test("customPose: eased between keys, rest where a key leaves a part out, once holds, loop wraps", () => {
  assert.deepEqual(customPose(SALUTE, 0), { arms: [[-16, 0], [16, 0]], legs: [-6, 6], knees: [0, 0], lean: 0 }); // rest
  const mid = customPose(SALUTE, 0.5); // a quarter in: half way to the 0.5 key, eased (smoothstep 0.5 = 0.5)
  assert.ok(Math.abs(mid.arms[1][0] - 83) < 1e-9 && Math.abs(mid.lean - 2) < 1e-9);
  assert.ok(customPose(SALUTE, 0.2).arms[1][0] < 16 + (150 - 16) * 0.2, "eased: slow start");
  assert.deepEqual(customPose(SALUTE, 9), customPose(SALUTE, 1)); // once: holds the last key
  assert.deepEqual(customPose(DANCE, 0.25), customPose(DANCE, 1.25)); // loop: period = duration
  assert.ok(Math.abs(customPose(DANCE, 0.75).lean) < 0.01, "loop: back toward the first key after the last (a spring's faint tail)");
  assert.ok(!BUILTIN_ACTIONS.has("salute") && BUILTIN_ACTIONS.has("wave"));
});

test("skeleton plays a custom pose: arms, legs (feet planted) and lean", () => {
  const base = { seed: "t", action: "salute", facing: "camera", t: 0 };
  const idle = skeleton({ ...base, action: "idle" }), k = skeleton({ ...base, custom: customPose(SALUTE, 1) });
  assert.ok(k.arms[1][2][1] < idle.arms[1][2][1] - 150, "the right hand is raised");
  assert.ok(Math.abs(k.lean - (4 * Math.PI) / 180) < 1e-9);
  const d = skeleton({ ...base, custom: customPose(DANCE, 0) });
  const feet = d.legs.map((l) => l[1][1]);
  assert.ok(Math.abs(Math.max(...feet) - 1000) < 1e-6, "the more upright foot stands on the ground");
});

test("knees: the shin folds back, the lowest foot stays planted, and lean bends at the hips", () => {
  const base = { seed: "t", action: "kneel", facing: "right", t: 0 };
  const straight = skeleton({ ...base, custom: { arms: [[-16, 0], [16, 0]], legs: [-6, 6], knees: [0, 0], lean: 0 } });
  assert.equal(straight.knees, null, "no bend: legs draw as before");
  assert.equal(straight.hinge, 0);
  const k = skeleton({ ...base, custom: { arms: [[-16, 0], [16, 0]], legs: [0, 90], knees: [90, 90], lean: 20 } });
  assert.ok(Math.abs(k.hipY - (1000 - 110)) < 1e-6, "hips one shin above the ground");
  for (const [i, [, foot]] of k.legs.entries()) {
    assert.ok(Math.abs(foot[1] - 1000) < 1e-6, `foot ${i} on the ground`);
    assert.ok(Math.hypot(k.knees[i][0] - k.legs[i][0][0], k.knees[i][1] - k.legs[i][0][1]) > 100, "knee half way down the leg");
  }
  assert.ok(k.legs[0][1][0] < k.knees[0][0], "back shin folds behind the knee");
  assert.equal(k.hinge, 1);
});

test("built-in knees: a gait bends the swinging leg only (hips don't bob), camera knees bend outward", () => {
  const walk = (phase) => skeleton({ seed: "t", action: "walk", facing: "right", t: 0, phase });
  const passing = walk(0); // right leg swinging forward under the hips: its knee bends, the left stands straight
  assert.ok(passing.knees, "the swinging leg has a knee");
  assert.ok(Math.abs(passing.legs[0][1][1] - 1000) < 1e-6, "the standing foot is on the ground");
  assert.ok(passing.legs[1][1][1] < 1000 - 10, "the swinging foot is lifted");
  assert.ok(Math.abs(walk(0.25).hipY - skeleton({ seed: "t", action: "walk", facing: "right", t: 0, phase: 0.25 }).hipY) < 1e-9);
  assert.equal(skeleton({ seed: "t", action: "idle", facing: "camera", t: 0 }).knees, null, "standing still: straight legs");
  const squat = skeleton({ seed: "t", action: "x", facing: "camera", t: 0, custom: { arms: [[-16, 0], [16, 0]], legs: [-6, 6], knees: [60, 60], lean: 0 } });
  assert.ok(squat.knees[0][0] < squat.legs[0][0][0] && squat.knees[1][0] > squat.legs[1][0][0], "knees point outward");
});

test("ActionKey ease: in-out by default (unchanged), linear, back-out overshoots then settles", async () => {
  const { customPose, EASES } = await import("../page/actions.js");
  const def = (ease) => ({ duration: 1, loop: false, keys: [{ t: 0, lean: 0 }, { t: 1, lean: 20, ...(ease ? { ease } : {}) }] });
  const at = (ease, u) => customPose(def(ease), u).lean;
  assert.equal(at(null, 0.25), at("in-out", 0.25));                       // default = in-out
  assert.ok(Math.abs(at(null, 0.25) - 20 * EASES["in-out"](0.25)) < 1e-9); // = the smoothstep every action used
  assert.ok(Math.abs(at("linear", 0.25) - 5) < 1e-9);
  assert.ok(Math.max(...[0.6, 0.7, 0.8, 0.9].map((u) => at("back-out", u))) > 20, "back-out overshoots");
  assert.equal(at("back-out", 1), 20);                                     // and settles on the key
});

test("customPose spring: a big change dips first and overshoots after, scaled by size; snap, small and crowded keys get none", async () => {
  const { STYLE } = await import("../page/style.js");
  const P = STYLE.stickman.life.spring, d = 1.2, up = (o = {}) => ({ id: "x", name: "X", duration: d, loop: false,
    keys: [{ t: 0 }, { t: 0.5, arms: [[-16, 0], [150, 40]], ...o }] }); // holds the raised arm after 0.6 s
  const arm = (def, f) => customPose(def, f / 30).arms[1][0];
  assert.ok(arm(up(), 2) < 16, "anticipation: the arm dips the other way first");
  assert.ok(arm(up(), 20) > 150, "overshoot past the key");
  assert.ok(Math.abs(arm(up(), 18 + P.settle) - 150) < 1e-6 || arm(up(), 18 + P.settle) < 150, "settled by `settle` frames");
  assert.equal(arm(up({ snap: true }), 20), 150, "snap: lands exactly");
  assert.equal(arm(up({ snap: true }), 2) >= 16, true, "snap: no dip");
  const small = { ...up(), keys: [{ t: 0 }, { t: 0.5, arms: [[-16, 0], [26, 0]] }] }; // a 10 degree change
  assert.equal(arm(small, 20), 26, "a small change gets none");
  const fast = { id: "w", name: "W", duration: 0.4, loop: true, keys: [{ t: 0, arms: [[-16, 0], [100, 50]] }, { t: 0.5, arms: [[-16, 0], [100, -10]] }] };
  for (let f = 0; f < 24; f++) { // 6-frame keys: the next change starts before a spring could settle
    const b = customPose(fast, f / 30).arms[1][1];
    assert.ok(b <= 50 + 1e-9 && b >= -10 - 0.12 * 60 - 1e-9, `fast loop: no overshoot past its keys (frame ${f}: ${b})`);
  }
  const limit = { ...up(), keys: [{ t: 0 }, { t: 0.5, legs: [-90, 90] }] };
  for (let f = 0; f < 40; f++) assert.ok(Math.abs(customPose(limit, f / 30).legs[1]) <= 90, "clamped to the leg range");
  const off = { ...P }; Object.assign(P, { antic: 0, over: 0 });
  try { assert.equal(arm(up(), 20), 150, "knobs at 0: off"); } finally { Object.assign(P, off); }
});
