// Talk gestures, point arm and stressed-word bob: the timing rules (page/motion.js is pure, imported directly),
// plus a render check that a short talk shot shows no gesture and a seeded long one does.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { GESTURE, gestureAmount, gesturePlan, pointAmount, stressBob } from "../page/motion.js";

const ENGINE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FIX = path.join(ENGINE, "..", "pipeline", "tests", "fixtures", "story");
const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });

test("talk shots under 1.5 s never gesture", () => {
  for (let seed = 0; seed < 2000; seed++) {
    assert.equal(gesturePlan(seed, "s01", "bob", "talk", 1.49), null);
  }
});

test("about 35% of eligible talk shots get one gesture of 0.6-1.0 s inside the shot", () => {
  let n = 0;
  for (let seed = 0; seed < 2000; seed++) {
    const p = gesturePlan(seed, "s01", "bob", "talk", 2.0);
    if (!p) continue;
    n++;
    assert.ok(GESTURE.kinds.includes(p.kind));
    assert.ok(p.dur >= 0.6 && p.dur <= 1.0, `dur ${p.dur}`);
    assert.ok(p.start >= 0 && p.start + p.dur <= 2.0);
  }
  assert.ok(n / 2000 > 0.3 && n / 2000 < 0.4, `share ${n / 2000}`);
});

test("never on idle (or other non-talk) actors; same inputs, same plan", () => {
  for (const action of ["idle", "walk", "run", "point", "react"]) {
    for (let seed = 0; seed < 300; seed++) assert.equal(gesturePlan(seed, "s01", "amy", action, 3.0), null);
  }
  assert.deepEqual(gesturePlan(7, "s04", "bob", "talk", 2.5), gesturePlan(7, "s04", "bob", "talk", 2.5));
});

test("gesture eases in and out; point arm lowers after 0.8 s; stressed words bob briefly", () => {
  const plan = { kind: "palm", start: 1.0, dur: 0.8 };
  assert.equal(gestureAmount(plan, 0.9), 0);
  assert.equal(gestureAmount(plan, 1.4), 1);
  assert.ok(gestureAmount(plan, 1.05) > 0 && gestureAmount(plan, 1.05) < 0.5);
  assert.equal(gestureAmount(plan, 1.9), 0);
  assert.equal(pointAmount(0), 0);
  assert.equal(pointAmount(0.5), 1);
  assert.equal(pointAmount(0.8), 1);
  assert.equal(pointAmount(1.1), 0);
  assert.equal(pointAmount(3), 0);
  const words = [{ text: "so", start: 0, end: 0.2 }, { text: "badly,", start: 0.3, end: 0.7 }];
  assert.equal(stressBob(0.1, words), 0);           // short word: no bob
  assert.ok(stressBob(0.42, words) > 0.9);          // long word: lift at its start
  assert.equal(stressBob(0.6, words), 0);           // over after 0.25 s
});

function makePart(mutate) {
  const series = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-motion-"));
  temps.push(series);
  const part = path.join(series, "part-01");
  fs.mkdirSync(part);
  fs.copyFileSync(path.join(FIX, "series.json"), path.join(series, "series.json"));
  fs.copyFileSync(path.join(FIX, "phrases.json"), path.join(part, "phrases.json"));
  const story = mutate(JSON.parse(fs.readFileSync(path.join(FIX, "story.json"), "utf8")));
  fs.writeFileSync(path.join(part, "story.json"), JSON.stringify(story));
  return part;
}
const render = (part, frames) => spawnSync(process.execPath, [path.join(ENGINE, "render.mjs"), "--part", part,
  "--frames", frames, "--out-dir", path.join(part, "f"), "--swiftshader"], { encoding: "utf8" });

test("render: a talk shot under 1.5 s shows no gesture; a seeded 2 s one does", () => {
  // fixture s02 (bob talks) is frames 60-119 = 2 s. Shorten it to 40 frames (1.33 s) for the first case.
  const short = makePart((s) => { s.shots[1].end_frame = 100; s.shots[2].start_frame = 100; s.seed = 1; return s; });
  const r1 = render(short, "60-99");
  assert.equal(r1.status, 0, r1.stderr);
  assert.doesNotMatch(r1.stdout, /gesture:/);

  let seed = 0;
  while (!gesturePlan(seed, "s02", "bob", "talk", 2.0)) seed++;
  const plan = gesturePlan(seed, "s02", "bob", "talk", 2.0);
  const mid = 60 + Math.round((plan.start + plan.dur / 2) * 30);
  const long = makePart((s) => { s.seed = seed; return s; });
  const r2 = render(long, `${mid}-${mid}`);
  assert.equal(r2.status, 0, r2.stderr);
  assert.match(r2.stdout, new RegExp(`gesture: bob ${plan.kind}`));
});
