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
  assert.deepEqual(customPose(SALUTE, 0), { arms: [[-16, 0], [16, 0]], legs: [-6, 6], lean: 0 }); // rest
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
