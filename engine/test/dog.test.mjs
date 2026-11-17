// Dog pose timing (pure, no browser) plus one rendered dog frame.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { after, before, test } from "node:test";
import { BARK, DOG_STRIDE, barkAmount, dogPose, gallopPhase } from "../page/dog.js";

import { fixturePart, jobOk, renderNamed } from "./batch.mjs";

test("gallop is driven by distance: same distance, same legs at any time; no distance, no stride", () => {
  assert.equal(gallopPhase(DOG_STRIDE * 2.5), 2.5);
  const at = (dist, t) => dogPose({ action: "run", phase: gallopPhase(dist), t }).legs;
  assert.deepEqual(at(0.7, 0.1), at(0.7, 3.9));            // time alone never moves the legs
  assert.notDeepEqual(at(0.7, 0.1), at(1.0, 0.1));          // distance does
  // one full gallop cycle per DOG_STRIDE of distance
  for (const v of at(0.3 + DOG_STRIDE, 0).map((v, i) => v - at(0.3, 0)[i])) assert.ok(Math.abs(v) < 1e-9);
  const idle = (t) => dogPose({ action: "idle", t, breath: Math.sin(t) });
  assert.deepEqual(idle(0.2).legs, idle(2.7).legs);         // standing legs never step
  assert.notEqual(idle(0.2).tail, idle(0.4).tail);          // but the tail wags
  assert.ok(dogPose({ action: "run", phase: 0.3 }).tongue && !idle(0).tongue);
});

test("bark: a burst of yaps from the cue frame, staggered per barking dog, shut otherwise", () => {
  assert.equal(barkAmount(99, 100), 0);
  assert.ok(barkAmount(102, 100) > 0.9);
  assert.equal(barkAmount(100 + BARK.open, 100), 0);        // closed between yaps
  assert.equal(barkAmount(100 + BARK.every * BARK.count, 100), 0);
  assert.equal(barkAmount(102, 100, 1), 0);                 // second barker starts 3 frames later
  assert.ok(barkAmount(105, 100, 1) > 0.9);
});

const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });

/** fixture part; s01 becomes a countryside travel shot chased by two dogs, s02 gets a barking dog + bark cue */
function dogPart(withDogs = true) {
  return fixturePart(temps, (s) => {
  Object.assign(s.shots[0], { set: "countryside", travel: { speed: 2.5 } });
  Object.assign(s.shots[0].actors[0], { action: "run", start_pos: [0, 0], end_pos: [0, 0], facing: "right" });
  if (withDogs) {
    s.shots[0].animals = [
      { id: "dog1", kind: "dog", action: "run", start_pos: [-1.6, 0.2], end_pos: [-0.8, 0.2], facing: "right", variant: "brown" },
      { id: "dog2", kind: "dog", action: "run", start_pos: [-2.0, -0.3], end_pos: [-1.2, -0.3], facing: "right", variant: "white_patches" }];
    s.shots[1].animals = [{ id: "dog1", kind: "dog", action: "bark", start_pos: [1.4, 0.2], facing: "right", variant: "black" }];
    s.cues.push({ frame: 62, kind: "bark" });
  }
  return s;
  });
}

const dogs = dogPart(), none = dogPart(false);
const out = (p, tag) => path.join(p, `${tag}.png`);
let R;
before(async () => {
  R = await renderNamed({ a: ["--part", dogs, "--frame", "30", "--out", out(dogs, "a")],
    b: ["--part", dogs, "--frame", "30", "--out", out(dogs, "b")],
    none: ["--part", none, "--frame", "30", "--out", out(none, "a")],
    bark: ["--part", dogs, "--frame", "64", "--out", out(dogs, "bark")] }); // mid-yap
});

test("dog frame: deterministic, reported, and the dogs change the picture", () => {
  for (const n of ["a", "b", "none", "bark"]) jobOk(R, n);
  assert.match(R.a.out, /frame 30: .*\[dogs 2\]/);
  assert.ok(fs.readFileSync(out(dogs, "a")).equals(fs.readFileSync(out(dogs, "b"))), "dog frame not deterministic");
  assert.ok(!fs.readFileSync(out(dogs, "a")).equals(fs.readFileSync(out(none, "a"))), "dogs not drawn");
});
