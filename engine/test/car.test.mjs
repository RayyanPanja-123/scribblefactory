// Car motion and wave timing (pure, no browser) plus rendered car frames (arrive, ride).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { WHEEL_R, carEase, carSpeedShare, wheelAngle } from "../page/car.js";
import { WAVE, waveAmount } from "../page/motion.js";

const ENGINE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FIX = path.join(ENGINE, "..", "pipeline", "tests", "fixtures", "story");

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
  const series = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-car-"));
  temps.push(series);
  const part = path.join(series, "part-01");
  fs.mkdirSync(part);
  fs.copyFileSync(path.join(FIX, "series.json"), path.join(series, "series.json"));
  fs.copyFileSync(path.join(FIX, "phrases.json"), path.join(part, "phrases.json"));
  const s = JSON.parse(fs.readFileSync(path.join(FIX, "story.json"), "utf8"));
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
  fs.writeFileSync(path.join(part, "story.json"), JSON.stringify(s));
  return part;
}

const render = (...args) => spawnSync(process.execPath, [path.join(ENGINE, "render.mjs"), ...args, "--swiftshader"], { encoding: "utf8" });
const png = (dir, n) => fs.readFileSync(path.join(dir, `${String(n).padStart(6, "0")}.png`));

test("car frames (ride, arrive): deterministic, reported, and the car changes the picture", () => {
  const car = carPart(), none = carPart(false);
  const r = render("--part", car, "--frames", "20-20", "--out-dir", path.join(car, "a"));
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /frame 20: .*\[car car1 drive \(bob, amy\) x 0\.00\]/);
  const r2 = render("--part", car, "--frames", "75-75", "--out-dir", path.join(car, "a"));
  assert.equal(r2.status, 0, r2.stderr);
  assert.match(r2.stdout, /frame 75: .*\[car car1 arrive x [\d.]+\]/);
  for (const n of [20, 75]) {
    assert.equal(render("--part", car, "--frames", `${n}-${n}`, "--out-dir", path.join(car, "b")).status, 0);
    assert.equal(render("--part", none, "--frames", `${n}-${n}`, "--out-dir", path.join(none, "a")).status, 0);
    assert.ok(png(path.join(car, "a"), n).equals(png(path.join(car, "b"), n)), `car frame ${n} not deterministic`);
    assert.ok(!png(path.join(car, "a"), n).equals(png(path.join(none, "a"), n)), `car missing from frame ${n}`);
  }
});
