// @weather and @fx lightning: the pure stroke / flash / fade rules (page/weather.js), plus renders: every weather type
// draws, the same frame renders to the same bytes twice, and a strike shows its bolt on its frame only.
import assert from "node:assert/strict";
import fs from "node:fs";
import { after, before, test } from "node:test";
import { AMBIENT, BOLT_FRAMES, COUNT, FADE_FRAMES, bolt, fadePlan, flashAt, layersAt, strikeAt, strokes } from "../page/weather.js";
import { fixturePart, frames, jobOk, png, renderNamed } from "./batch.mjs";

const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });
const W = (kind, intensity = "medium") => ({ kind, intensity });
const KINDS = ["rain", "snow", "fog", "wind", "storm"];

test("strokes are deterministic, capped per intensity, and differ by kind", () => {
  for (const kind of ["rain", "snow", "wind", "storm"]) {
    for (const [lv, intensity] of ["light", "medium", "heavy"].entries()) {
      const a = strokes(W(kind, intensity), 7, 1.3, 1080, 1920);
      assert.deepEqual(a, strokes(W(kind, intensity), 7, 1.3, 1080, 1920));
      assert.equal(a.length, COUNT[kind][lv] * (kind === "snow" ? 3 : 1)); // snow: three ticks per flake
    }
  }
  assert.notDeepEqual(strokes(W("rain"), 7, 1.3, 1080, 1920), strokes(W("rain"), 8, 1.3, 1080, 1920));
  assert.notDeepEqual(strokes(W("rain"), 7, 1.3, 1080, 1920), strokes(W("rain"), 7, 1.4, 1080, 1920)); // it falls
  assert.deepEqual(strokes(W("fog"), 7, 1, 1080, 1920), []); // fog is a plane behind the cast, not overlay strokes
  assert.deepEqual(strokes(null, 7, 1, 1080, 1920), []);
  const slope = (s) => (s.pts[1][0] - s.pts[0][0]) / (s.pts[1][1] - s.pts[0][1]);
  assert.ok(slope(strokes(W("storm"), 1, 0, 1080, 1920)[0]) > 2 * slope(strokes(W("rain"), 1, 0, 1080, 1920)[0]));
});

test("a weather change mid-scene fades over 0.5 s; a set change does not", () => {
  const sh = (id, a, b, set, weather) => ({ id, start_frame: a, end_frame: b, set, weather });
  const shots = [sh("s01", 0, 30, "room", null), sh("s02", 30, 40, "room", W("rain")), sh("s03", 40, 80, "room", W("rain")),
    sh("s04", 80, 120, "street", W("snow"))];
  const plan = fadePlan(shots);
  assert.deepEqual(plan.get("s02"), { from: null, at: 30 });
  assert.deepEqual(plan.get("s03"), { from: null, at: 30 }); // still fading across the cut
  assert.equal(plan.has("s04"), false);
  assert.deepEqual(layersAt(shots[1], plan.get("s02"), 30), []);
  const mid = layersAt(shots[2], plan.get("s03"), 30 + FADE_FRAMES / 2);
  assert.equal(mid.length, 1); assert.ok(Math.abs(mid[0].amount - 0.5) < 1e-9);
  assert.deepEqual(layersAt(shots[2], plan.get("s03"), 30 + FADE_FRAMES), [{ weather: W("rain"), amount: 1 }]);
  const swap = fadePlan([sh("s01", 0, 30, "room", W("snow")), sh("s02", 30, 60, "room", W("fog"))]);
  assert.deepEqual(layersAt({ weather: W("fog") }, swap.get("s02"), 35).map((l) => l.weather.kind), ["fog", "snow"]);
});

test("lightning: bolt on its frames only, brief mild flash, ambient storm flashes never near a strike", () => {
  const strikes = [{ frame: 100 }, { frame: 200, target: "bob" }];
  assert.equal(strikeAt(strikes, 99), null);
  assert.deepEqual(strikeAt(strikes, 100), { strike: strikes[0], index: 0, k: 0 });
  assert.equal(strikeAt(strikes, 200 + BOLT_FRAMES - 1).index, 1);
  assert.equal(strikeAt(strikes, 200 + BOLT_FRAMES), null);
  const f0 = flashAt(100, 1, W("storm"), strikes), f2 = flashAt(102, 1, W("storm"), strikes);
  assert.ok(f0 > 0 && f0 <= 0.35, `flash ${f0}`); assert.equal(f2, 0);
  assert.ok(flashAt(100, 1, W("rain"), strikes) < f0); // strongest in a storm
  assert.equal(flashAt(150, 1, null, []), 0);
  let ambient = 0;
  for (let seed = 0; seed < 50; seed++) {
    const many = Array.from({ length: 3 }, (_, i) => ({ frame: 40 + 75 * i + seed }));
    for (let n = 0; n < 600; n++) {
      if (strikeAt(many, n)) continue;
      const f = flashAt(n, seed, W("storm", "heavy"), many);
      if (f > 0) {
        ambient++;
        assert.ok(f <= 0.15);
        assert.ok(many.every((s) => Math.abs(s.frame - n) >= AMBIENT.gap - AMBIENT.alpha.length), `seed ${seed} n ${n}`);
      }
    }
    assert.equal(flashAt(77, seed, W("rain", "heavy"), []), 0); // ambient flashes: storm only
  }
  assert.ok(ambient > 0);
  const [main, fork] = bolt(3, 0, 500, 1400);
  assert.deepEqual(main.at(-1), [500, 1400]); // lands on the target point
  assert.ok(main[0][1] < 0 && fork.length === 4);
  assert.deepEqual(bolt(3, 0, 500, 1400), [main, fork]);
});

// renders: frame 30 of the fixture (bob alone, office) under each weather; a strike near bob at frame 70 (shot s02)
let R, part;
const parts = {};
before(async () => {
  for (const k of ["clear", ...KINDS]) {
    parts[k] = fixturePart(temps, (s) => {
      if (k !== "clear") for (const sh of s.shots) sh.weather = W(k, "heavy");
      if (k === "storm") s.lightning = [{ frame: 70, target: "bob" }];
      return s;
    });
  }
  part = parts.storm;
  const jobs = Object.fromEntries(Object.entries(parts).map(([k, p]) => [k, frames(p, "30-30", "a")]));
  R = await renderNamed({ ...jobs, again: frames(part, "30-30", "b"), strike: frames(part, "69-71", "s"),
    strike2: frames(part, "70-70", "t") });
}, { timeout: 300000 });

test("every weather type renders, differently from clear, and the same frame twice is identical", () => {
  for (const k of ["clear", ...KINDS, "again", "strike", "strike2"]) jobOk(R, k);
  const clear = png(parts.clear + "/a", 30);
  for (const k of KINDS) {
    assert.notDeepEqual(png(parts[k] + "/a", 30), clear, `${k} draws nothing`);
    assert.match(R[k].out, new RegExp(`weather ${k} heavy`));
  }
  assert.deepEqual(png(part + "/a", 30), png(part + "/b", 30)); // deterministic: test render == final
});

test("the strike shows on its frame (bolt + flash), not the frame before", () => {
  assert.match(R.strike.out, /000070\.png.*\[lightning 0\] \[flash/);
  assert.doesNotMatch(R.strike.out.split("\n").find((l) => l.includes("000069")), /lightning/);
  assert.deepEqual(png(part + "/s", 70), png(part + "/t", 70));
});
