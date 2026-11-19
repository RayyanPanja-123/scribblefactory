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
  assert.ok(Math.abs(customPose(DANCE, 0.75).lean) < 1e-9, "loop: back toward the first key after the last");
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
