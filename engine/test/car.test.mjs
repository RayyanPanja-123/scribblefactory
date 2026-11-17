// Car motion and wave timing (pure, no browser) plus rendered car frames (arrive, ride).
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { after, before, test } from "node:test";
import { WHEEL_R, carEase, carSpeedShare, wheelAngle } from "../page/car.js";
import { WAVE, waveAmount } from "../page/motion.js";

import { fixturePart, frames, jobOk, png, renderNamed } from "./batch.mjs";

test("wheels turn by distance driven: one radian per wheel radius, nothing without distance", () => {
  assert.equal(wheelAngle(0), 0);
  assert.ok(Math.abs(wheelAngle(WHEEL_R * 3) - 3) < 1e-12);
  assert.equal(wheelAngle(2) * 2, wheelAngle(4));
  // arrive: eased to a stop (all the way there, speed 0 at the end); leave: from a stop; idle never moves
  assert.equal(carEase("arrive", 1), 1); assert.equal(carSpeedShare("arrive", 1), 0);
  assert.equal(carEase("leave", 0), 0); assert.equal(carSpeedShare("leave", 0), 0);
  assert.ok(carEase("arrive", 0.5) > 0.5 && carEase("leave", 0.5) < 0.5);
  for (const u of [0, 0.3, 1]) assert.equal(carEase("idle", u), 0);
  assert.equal(carEase("drive", 0.4), 0.4);
});

test("wave: arm rises, exactly 3 eased waves, then rests", () => {
  const end = WAVE.rise + WAVE.count / WAVE.hz;
  assert.deepEqual(waveAmount(0), { k: 0, swing: 0 });
  let peaks = 0, prev = 0, rising = false;
  for (let ts = 0; ts <= end + 1; ts += 1 / 120) {
    const { k, swing } = waveAmount(ts);
    if (ts > WAVE.rise + 0.01 && ts < end - 0.01) assert.equal(k, 1);
    if (rising && swing < prev && prev > 0.3) peaks++;
    rising = swing > prev; prev = swing;
  }
  assert.equal(peaks, WAVE.count);
  assert.ok(Math.abs(waveAmount(WAVE.rise + 0.01).swing) < 0.05, "swing eases in");
  assert.deepEqual(waveAmount(end + WAVE.fall + 0.01), { k: 0, swing: 0 }); // arm back at rest
});

const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });

/** fixture part: s01 (0-59) bob and amy ride a car on dirt_road (travel 4 u/s, bob waves); s02 (60-119) a car
 *  arrives beside bob. withCar false: the same shots without the cars (bob/amy standing). */
function carPart(withCar = true) {
  return fixturePart(temps, (s) => {
  const [s1, s2] = s.shots;
  Object.assign(s1, { set: "dirt_road", travel: { speed: 4.0 } });
  s1.actors = [{ cast_id: "bob", action: "wave", start_pos: [0, 0], facing: "right", expression: "happy" },
    { cast_id: "amy", action: "ride", start_pos: [0, 0], facing: "right", expression: "neutral" }];
  s2.set = "dirt_road";
  s2.actors = [{ cast_id: "bob", action: "react", start_pos: [0, 0], facing: "camera", expression: "surprised" }];
  if (withCar) {
    s1.vehicles = [{ id: "car1", kind: "car", action: "drive", start_pos: [0, 0], end_pos: [0, 0], facing: "right",
      riders: ["bob", "amy"], variant: "red" }];
    s2.vehicles = [{ id: "car1", kind: "car", action: "arrive", start_pos: [6.9, -0.6], end_pos: [1.9, -0.6],
      facing: "left", riders: [], variant: "navy" }];
  }
  return s;
  });
}

const car = carPart(), none = carPart(false);
let R;
before(async () => {
  const jobs = {};
  for (const n of [20, 75]) {
    jobs[`car${n}`] = frames(car, `${n}-${n}`, "a");
    jobs[`again${n}`] = frames(car, `${n}-${n}`, "b");
    jobs[`none${n}`] = frames(none, `${n}-${n}`, "a");
  }
  R = await renderNamed(jobs);
});

test("car frames (ride, arrive): deterministic, reported, and the car changes the picture", () => {
  for (const n of [20, 75]) for (const k of ["car", "again", "none"]) jobOk(R, `${k}${n}`);
  assert.match(R.car20.out, /frame 20: .*\[car car1 drive \(bob, amy\) x 0\.00\]/);
  assert.match(R.car75.out, /frame 75: .*\[car car1 arrive x [\d.]+\]/);
  for (const n of [20, 75]) {
    assert.ok(png(path.join(car, "a"), n).equals(png(path.join(car, "b"), n)), `car frame ${n} not deterministic`);
    assert.ok(!png(path.join(car, "a"), n).equals(png(path.join(none, "a"), n)), `car missing from frame ${n}`);
  }
});
