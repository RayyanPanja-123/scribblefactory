// Talk gestures, point arm and stressed-word bob: the timing rules (page/motion.js is pure, imported directly),
// plus a render check that a short talk shot shows no gesture and a seeded long one does.
import assert from "node:assert/strict";
import fs from "node:fs";
import { after, before, test } from "node:test";
import { GESTURE, MOUTH_MAX_HZ, MOUTH_MIN_CLOSED_F, MOUTH_MIN_OPEN_F, gestureAmount, gesturePlan, mouthCurve, mouthCycles,
  pointAmount, stressBob } from "../page/motion.js";

import { fixturePart, frames, jobOk, renderNamed } from "./batch.mjs";
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

// fixture s02 (bob talks) is frames 60-119 = 2 s. short: cut to 40 frames (1.33 s), so it never plans a gesture
// (the pure test above covers every frame); a few rendered frames across it must report none.
const short = fixturePart(temps, (s) => { s.shots[1].end_frame = 100; s.shots[2].start_frame = 100; s.seed = 1; return s; });
let seed = 0;
while (!gesturePlan(seed, "s02", "bob", "talk", 2.0)) seed++;
const plan = gesturePlan(seed, "s02", "bob", "talk", 2.0);
const mid = 60 + Math.round((plan.start + plan.dur / 2) * 30);
const long = fixturePart(temps, (s) => { s.seed = seed; return s; });
let R;
before(async () => {
  R = await renderNamed({ s61: frames(short, "61-61", "f"), s80: frames(short, "80-80", "f"), s99: frames(short, "99-99", "f"),
    long: frames(long, `${mid}-${mid}`, "f") });
});

test("render: a talk shot under 1.5 s shows no gesture; a seeded 2 s one does", () => {
  for (const n of ["s61", "s80", "s99", "long"]) jobOk(R, n);
  for (const n of ["s61", "s80", "s99"]) assert.doesNotMatch(R[n].out, /gesture:/);
  assert.match(R.long.out, new RegExp(`gesture: bob ${plan.kind}`));
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

test("camera: moves ease in and out; a reaction close-up holds ~0.4 s before its move", async () => {
  const { cameraProgress, isReactionClose } = await import("../page/motion.js");
  const shot = (angle, action) => ({ start_frame: 0, end_frame: 60, camera: { angle }, actors: [{ action, expression: "neutral" }] });
  const med = shot("medium", "talk");
  assert.equal(cameraProgress(med, 0), 0); assert.equal(cameraProgress(med, 1), 1);
  assert.ok(Math.abs(cameraProgress(med, 0.5) - 0.5) < 1e-9);
  assert.ok(cameraProgress(med, 0.1) < 0.1 && cameraProgress(med, 0.9) > 0.9, "eased, not linear");
  const rc = shot("close", "react");
  assert.equal(isReactionClose(rc), true); assert.equal(isReactionClose(shot("close", "talk")), false);
  assert.equal(cameraProgress(rc, 0.39 / 2), 0);       // 0.39 s into a 2 s shot: still holding
  assert.ok(cameraProgress(rc, 0.5 / 2) > 0);           // moving by 0.5 s
  assert.equal(cameraProgress(rc, 1), 1);
});

test("idle life: seeded, standing actions only; looks at the addressed, else the speaker, else the other of two", async () => {
  const { idleLife, lookTarget } = await import("../page/motion.js");
  assert.deepEqual(idleLife("a", 1.3, "idle", 0.2), idleLife("a", 1.3, "idle", 0.2));
  assert.notDeepEqual(idleLife("a", 1.3, "idle", 0.2), idleLife("b", 1.3, "idle", 0.2)); // never in step
  assert.equal(idleLife("a", 1, "walk", 0), null);
  const l = idleLife("a", 2, "talk", 1);
  assert.ok(l.bob > 0 && Math.abs(l.shift) <= 2);
  const A = { cast_id: "a", action: "idle" }, B = { cast_id: "b", action: "talk" }, C = { cast_id: "c", action: "idle", target: "a" };
  assert.equal(lookTarget(A, [A, B]), B);
  assert.equal(lookTarget(B, [A, B]), A);        // two-hander: the speaker looks at the other one
  assert.equal(lookTarget(C, [A, B, C]), A);     // whom it addresses wins
  assert.equal(lookTarget(A, [A, { cast_id: "d", action: "idle" }, C]), null); // nobody talking, three people
});

test("camera life: seeded continuous noise, clamped trauma, shake triggers, fov punch on fast pushes only", async () => {
  const { noise1, trauma, shakeTriggers, fovPunch, cameraProgress } = await import("../page/motion.js");
  const { STYLE } = await import("../page/style.js");
  for (let x = 0; x < 5; x += 0.01) {
    assert.equal(noise1(x, 7, "a"), noise1(x, 7, "a")); // pure
    assert.ok(Math.abs(noise1(x, 7, "a")) <= 1);
    assert.ok(Math.abs(noise1(x + 0.01, 7, "a") - noise1(x, 7, "a")) < 0.05, "continuous");
  }
  const g = [{ t0: 1, strength: 0.7 }, { t0: 1.1, strength: 0.8 }];
  assert.equal(trauma(0.99, g, 0.6), 0);
  assert.equal(trauma(1.1, g, 0.6), 1, "summed then clamped");
  assert.ok(trauma(1.5, g, 0.6) < trauma(1.3, g, 0.6) && trauma(1.8, g, 0.6) === 0, "decays to 0");
  const shot = (o) => ({ id: "s01", start_frame: 30, end_frame: 90, actors: [], camera: { angle: "medium", move: "push_in", speed: 0.9 }, ...o });
  const T = shakeTriggers({ shots: [shot({ twist: true, actors: [{ action: "collapse" }] })], cues: [{ kind: "low_hit", frame: 30 }],
    lightning: [{ frame: 60 }], shakes: [75] });
  assert.deepEqual(T.map((x) => [x.kind, +x.t0.toFixed(3), x.strength]), [["twist", 1, 1], ["collapse", 1.6, 0.7], ["lightning", 2, 0.6], ["fx", 2.5, 0.8]]);
  assert.deepEqual(shakeTriggers({ shots: [shot()] }), [], "an old story.json: no fields, no shake");
  const peak = STYLE.camera.life.punch.keys[1];
  assert.equal(fovPunch(shot(), peak[0]), peak[1]);
  assert.equal(fovPunch(shot(), 5), 0, "settles back to the base fov");
  for (const angle of ["wide", "over_shoulder"]) assert.equal(fovPunch(shot({ camera: { angle, move: "push_in", speed: 0.9 } }), peak[0]), 0);
  assert.equal(fovPunch(shot({ camera: { angle: "close", move: "push_in", speed: 0.3 } }), peak[0]), 0, "slow push: no punch");
  assert.ok(cameraProgress(shot(), 0.2) > 0.5, "fast push: quintic out front-loads the move");
  STYLE.camera.life.legacyEase = true;
  try { assert.ok(Math.abs(cameraProgress(shot(), 0.2) - 0.05792) < 1e-4, "legacy: smootherstep"); } finally { STYLE.camera.life.legacyEase = false; }
});

test("camera life: an @cam shake triggers at its shot's start with its own strength", async () => {
  const { shakeTriggers } = await import("../page/motion.js");
  const { STYLE } = await import("../page/style.js");
  const shot = { id: "s02", start_frame: 40, end_frame: 90, actors: [], camera: { angle: "close", move: "hold", speed: 0.2, shake: true, forced: true } };
  assert.deepEqual(shakeTriggers({ shots: [shot] }), [{ t0: 40 / 30, strength: STYLE.camera.life.shake.strength.cam, kind: "cam" }]);
});

test("pose pop: spawn / pose change / flip squashes then stretches over 0.18 s; the same pose, idle <-> talk, none", async () => {
  const { popAt } = await import("../page/motion.js");
  const idle = { action: "idle", facing: "camera" };
  assert.ok(Math.abs(popAt(null, idle, 0)) < 1e-9, "starts at rest");
  assert.ok(popAt(null, idle, 0.045) < 0, "squashes first");
  assert.ok(popAt(null, idle, 0.135) > 0, "then stretches");
  assert.equal(popAt(null, idle, 0.18), 0, "settled");
  assert.ok(Math.abs(popAt(null, idle, 0.045)) <= 0.08);
  assert.equal(popAt({ action: "talk", facing: "camera" }, idle, 0.045), 0, "idle <-> talk is the same pose");
  assert.ok(popAt({ action: "walk", facing: "camera" }, idle, 0.045) < 0, "pose change");
  assert.ok(popAt({ action: "idle", facing: "left" }, idle, 0.045) < 0, "flip");
  assert.equal(popAt(idle, { ...idle }, 0.045), 0, "unchanged");
});

test("speech envelope: smooth mouth average, 0 outside speech; snap-zoom: easeOutBack on reaction shots, not on wides", async () => {
  const { speechEnv, snapZoom, fovPunch } = await import("../page/motion.js");
  const { STYLE } = await import("../page/style.js");
  const mouth = new Float32Array(40); mouth.fill(1, 10, 20);
  assert.equal(speechEnv(mouth, 2), 0);
  assert.equal(speechEnv(mouth, 15), 1);
  assert.ok(speechEnv(mouth, 8) > 0 && speechEnv(mouth, 8) < 1, "ramps at the edge");
  const shot = (angle, action) => ({ camera: { angle, move: "hold", speed: 0.2 }, actors: [{ action }] });
  const Z = STYLE.camera.life.snap;
  assert.ok(Math.abs(snapZoom(shot("close", "react"), 0)) < 1e-9);
  assert.ok(Math.abs(snapZoom(shot("close", "shock-jump"), Z.dur) + Z.zoom) < 1e-9, "settles at the zoom");
  const dips = [];
  for (let ts = 0; ts <= Z.dur; ts += 0.01) dips.push(snapZoom(shot("medium", "gasp"), ts));
  assert.ok(Math.min(...dips) < -Z.zoom, "overshoots past the zoom, then settles");
  assert.equal(snapZoom(shot("wide", "react"), 0.1), 0);
  assert.equal(snapZoom(shot("close", "talk"), 0.1), 0);
  assert.ok(Math.abs(fovPunch(shot("close", "react"), 1) + Z.zoom) < 1e-9, "added to the punch: none here");
});

test("@mood: neutral without one, own params with one, eased in from the previous shot's; impact shake on loud hits", async () => {
  const { moodLook, moodParams, shakeTriggers } = await import("../page/motion.js");
  const { STYLE } = await import("../page/style.js");
  const n = moodParams(undefined);
  assert.deepEqual([n.contrast, n.saturation, n.exposure, n.haze, n.vignette], [1, 1, 1, 0, 0]);
  assert.deepEqual(moodParams("nope"), n, "unknown: neutral");
  const shots = [{ start_frame: 0 }, { start_frame: 30, mood: "dark" }, { start_frame: 60, mood: "dark" }];
  assert.equal(moodLook(shots, 0, 0).exposure, 1);
  assert.equal(moodLook(shots, 1, 30).exposure, 1, "blends in from neutral");
  assert.equal(moodLook(shots, 1, 30 + STYLE.mood.blend * 30).exposure, STYLE.mood.dark.exposure);
  assert.equal(moodLook(shots, 2, 60).exposure, STYLE.mood.dark.exposure, "same mood twice: no blend");
  assert.ok(moodLook(shots, 1, 35).exposure < 1 && moodLook(shots, 1, 35).exposure > STYLE.mood.dark.exposure);
  const cues = [{ kind: "low_hit", frame: 120 }, { kind: "pop", frame: 130 }];
  const sh = [{ id: "s1", start_frame: 0, end_frame: 90, actors: [], camera: { angle: "close", move: "hold", speed: 0.2 } }];
  assert.deepEqual(shakeTriggers({ shots: sh, cues }), [{ t0: 4, strength: STYLE.camera.life.shake.strength.impact, kind: "impact" }]);
});

test("render: @mood + a library reaction action render deterministically, the mood changes the frame, the snap zooms the shot", async () => {
  const os = await import("node:os"), path = await import("node:path");
  const { FIX, png } = await import("./batch.mjs");
  const lib = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-mood-"));
  temps.push(lib);
  fs.copyFileSync(path.join(FIX, "..", "..", "..", "scribble", "seed", "actions.json"), path.join(lib, "actions.json"));
  const make = (name, mood, action) => {
    const dir = path.join(lib, name, "part-01");
    fs.mkdirSync(dir, { recursive: true });
    fs.copyFileSync(path.join(FIX, "series.json"), path.join(lib, name, "series.json"));
    fs.copyFileSync(path.join(FIX, "phrases.json"), path.join(dir, "phrases.json"));
    const story = JSON.parse(fs.readFileSync(path.join(FIX, "story.json"), "utf8"));
    for (const sh of story.shots) { if (mood) sh.mood = mood; if (action) sh.actors[0].action = action; }
    fs.writeFileSync(path.join(dir, "story.json"), JSON.stringify(story));
    return dir;
  };
  const jobs = {};
  for (const [name, mood, action] of [["plain", null, null], ["dark", "dark", null], ["jump", null, "shock-jump"]]) {
    const dir = make(name, mood, action);
    jobs[`${name}1`] = frames(dir, "6-6", "a"); jobs[`${name}2`] = frames(dir, "6-6", "b");
  }
  const R = await renderNamed(jobs);
  for (const k of Object.keys(jobs)) jobOk(R, k);
  const bytes = (name, d) => png(path.join(lib, name, "part-01", d), 6);
  for (const name of ["plain", "dark", "jump"]) assert.ok(bytes(name, "a").equals(bytes(name, "b")), `${name}: same frame, same bytes`);
  assert.ok(!bytes("plain", "a").equals(bytes("dark", "a")), "@mood dark changes the frame");
  assert.ok(!bytes("plain", "a").equals(bytes("jump", "a")), "the reaction action changes the frame");
});
