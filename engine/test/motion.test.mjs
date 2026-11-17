// Talk gestures, point arm and stressed-word bob: the timing rules (page/motion.js is pure, imported directly),
// plus a render check that a short talk shot shows no gesture and a seeded long one does.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { GESTURE, MOUTH_MAX_HZ, MOUTH_MIN_CLOSED_F, MOUTH_MIN_OPEN_F, gestureAmount, gesturePlan, mouthCurve, mouthCycles,
  pointAmount, stressBob } from "../page/motion.js";

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

// --- talk mouth ---
/** phrases.json-like timing: sentences of words (word_s each, 0.05 s apart), 0.6 s pause between sentences */
function timing(sentences, word_s) {
  const words = [], phrases = [];
  let t = 0.2;
  for (const s of sentences) {
    const first = words.length;
    for (const text of s.split(" ")) { words.push({ text, start: t, end: t + word_s }); t += word_s + 0.05; }
    phrases.push({ word_start: first, word_end: words.length - 1 });
    t += 0.6;
  }
  return { words, phrases, total: Math.ceil((t + 0.3) * 30) };
}
const SPEECH = [
  timing(["The nineteen-oh-four Olympic marathon in Saint Louis was so badly organized", "that almost nobody finished it"], 0.3),
  timing(["a dog and a cat sat on it", "Unbelievably extraordinary organizational difficulties", "go"], 0.12), // fast
  timing(["So he placed only one single water well along the entire course"], 0.45),                      // slow
];

test("mouth: no cycle shorter than the minimums, never faster than MOUTH_MAX_HZ, eased, deterministic", () => {
  for (const { words, phrases, total } of SPEECH) {
    const cycles = mouthCycles(words, phrases);
    assert.ok(cycles.length > 0);
    for (const c of cycles) assert.ok(c.open >= MOUTH_MIN_OPEN_F && c.len - c.open >= MOUTH_MIN_CLOSED_F, JSON.stringify(c));
    for (const [a, b] of cycles.slice(0, -1).map((c, i) => [c, cycles[i + 1]])) {
      assert.ok(b.start >= a.start + a.len, "cycles overlap");
      assert.ok(b.start - a.start >= 30 / MOUTH_MAX_HZ, `${b.start - a.start} frames between opens`);
    }
    const curve = mouthCurve(cycles, total);
    let run = 0, open = curve[0] > 0, first = true;
    for (let f = 0; f <= total; f++) { // the drawn curve: open runs >= MIN_OPEN, closed gaps >= MIN_CLOSED
      const o = f < total && curve[f] > 0;
      if (o !== open || f === total) {
        if (open) assert.ok(run >= MOUTH_MIN_OPEN_F, `open for ${run} frames at ${f}`);
        else if (!first && f < total) assert.ok(run >= MOUTH_MIN_CLOSED_F, `closed for ${run} frames at ${f}`);
        if (!open) first = false;
        open = o; run = 0;
      }
      run++;
      if (f > 0 && f < total) assert.ok(Math.abs(curve[f] - curve[f - 1]) <= 0.5, `mouth snaps at frame ${f}`);
    }
    assert.deepEqual(mouthCycles(words, phrases), cycles);
  }
});

test("mouth: short words share a neighbour's cycle; flaps stop between phrases", () => {
  const count = (s, w = 0.12) => { const t = timing([s], w); return mouthCycles(t.words, t.phrases).length; };
  assert.equal(count("elephants to a giraffes", 0.3), count("elephants giraffes", 0.3)); // short words add no cycle
  assert.equal(count("a dog and a cat sat on it"), 3); // 8 short words, ~1.3 s: one group, not 8 opens
  const { words, phrases, total } = timing(["a dog and a cat sat on it"], 0.3);
  for (const { words: w, phrases: ps, total: n } of [...SPEECH, { words, phrases, total }]) {
    const curve = mouthCurve(mouthCycles(w, ps), n);
    const spans = ps.map((p) => [Math.round(w[p.word_start].start * 30), Math.round(w[p.word_end].end * 30)]);
    for (let f = 0; f < n; f++) {
      const inside = spans.some(([a, b]) => f >= a && f < b);
      if (!inside) assert.equal(curve[f], 0, `mouth open at frame ${f}, between phrases`);
    }
  }
});
