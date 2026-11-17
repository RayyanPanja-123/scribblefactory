// Step 5c-7: extras looks and crowd-mood timing (page/extras.js, pure), mood poses, dress + wide hat drawing
// (recording 2D context), and one batch render with a crowd and runners: same frame, same bytes.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { after, before, test } from "node:test";
import { EXTRA_TOPS, MOOD_EXPRESSION, extraLook, moodAt } from "../page/extras.js";
import { FEET_Y, drawStickman, skeleton } from "../page/stickman.js";
import { fixturePart, frames, jobOk, png, renderNamed } from "./batch.mjs";

const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });

/** fake canvas: every fill / stroke with its style and path points (pre-transform canvas px) */
function record(o) {
  const ops = [];
  let pts = [];
  const g = {
    setTransform() {}, clearRect() {}, translate() {}, rotate() {}, save() {}, restore() {}, clip() {}, closePath() {},
    beginPath() { pts = []; }, moveTo(x, y) { pts.push([x, y]); }, lineTo(x, y) { pts.push([x, y]); }, arc(x, y) { pts.push([x, y]); },
    fill() { ops.push({ op: "fill", style: this.fillStyle, pts }); },
    stroke() { ops.push({ op: "stroke", style: this.strokeStyle, pts }); },
  };
  drawStickman({ getContext: () => g }, o);
  return ops;
}
const BASE = { seed: "t:x", boil: 0, eyes: "dots", expression: "neutral", action: "idle", phase: 0, lid: 0, mouth: 0,
  breath: 0, facing: "camera", t: 0 };

test("extra looks are seeded and stable: muted crowd tops, numbered runners in tanks", () => {
  for (let v = 0; v < 50; v++) {
    const c = extraLook("s", { kind: "crowd", variant: v }), r = extraLook("s", { kind: "runner", variant: v });
    assert.deepEqual(c, extraLook("s", { kind: "crowd", variant: v }));
    assert.ok(EXTRA_TOPS.includes(c.top.color) && ["plain", "shirt"].includes(c.top.style) && !c.top.number);
    assert.ok(["none", "flat_cap", "bowler"].includes(c.headwear.kind));
    assert.equal(r.top.style, "tank");
    assert.match(r.top.number, /^[1-9][0-9]$/);
    assert.equal(r.legwear.kind, "shorts");
  }
  const variety = new Set(Array.from({ length: 40 }, (_, v) => JSON.stringify(extraLook("s", { kind: "crowd", variant: v }))));
  assert.ok(variety.size > 20, `only ${variety.size} different crowd looks`);
});

test("crowd moods: deterministic, and each extra on its own timing (never in sync)", () => {
  for (const mood of ["cheer", "angry", "gasp", "neutral"]) {
    assert.deepEqual(moodAt(mood, 1.3, "k1"), moodAt(mood, 1.3, "k1"));
    assert.ok(MOOD_EXPRESSION[mood]);
  }
  const keys = Array.from({ length: 8 }, (_, i) => `s:extra:crowd:${i * 37}`);
  for (const t of [0, 0.4, 1.7]) {
    assert.ok(new Set(keys.map((k) => moodAt("cheer", t, k).k.toFixed(3))).size > 4, `cheer in sync at ${t}`);
    assert.ok(new Set(keys.map((k) => moodAt("angry", t, k).shake.toFixed(3))).size > 4, `fists in sync at ${t}`);
  }
  assert.deepEqual(moodAt("neutral", 3, "k"), { k: 0, bounce: 0, shake: 0 });
});

test("mood poses: cheer hands above the shoulders, angry fists up by the head, gasp hands at the face (over it)", () => {
  const cheer = skeleton({ action: "cheer", mood: { k: 1 } }), idle = skeleton({ action: "idle" });
  for (const [shp, , hand] of cheer.arms) assert.ok(hand[1] < shp[1] - 80, "cheer hand not raised");
  for (const [, , hand] of cheer.arms) assert.ok(Math.abs(hand[0] - cheer.head[0]) > 150, "cheer hand hidden by the head");
  const angry = skeleton({ action: "angry", mood: { k: 1, shake: 0 } });
  for (const [shp, , hand] of angry.arms) assert.ok(hand[1] < shp[1], "fist not up");
  const gasp = skeleton({ action: "gasp", mood: { k: 1, shake: 0 } });
  assert.deepEqual(gasp.late, [0, 1]);
  for (const [, , hand] of gasp.arms) assert.ok(Math.hypot(hand[0] - gasp.head[0], hand[1] - gasp.head[1]) < 140);
  assert.deepEqual(idle.late, []);
});

test("dress: a flared skirt in the top colour from the waist to the knee, legs below, hem swings when walking", () => {
  const look = { top: { style: "dress", color: "#f7f2e8", accent_color: "#c2185b" }, color: "#f7f2e8" };
  const skirtOf = (o) => {
    const fills = record({ ...BASE, ...look, ...o }).filter((x) => x.op === "fill" && x.style === "#f7f2e8");
    return fills.reduce((a, b) => (Math.max(...b.pts.map((p) => p[1])) > Math.max(...a.pts.map((p) => p[1])) ? b : a));
  };
  const s = skirtOf({}), hem = Math.max(...s.pts.map((p) => p[1]));
  const sk = skeleton({ action: "idle" });
  assert.ok(hem > sk.hipY + 60 && hem < FEET_Y - 60, `hem at ${hem}: knee height, legs below`);
  const width = (x) => Math.max(...x.pts.map((p) => p[0])) - Math.min(...x.pts.map((p) => p[0]));
  assert.ok(width(s) > 2 * 92 * 1.2, "skirt flares wider than the body");
  const a = skirtOf({ action: "walk", phase: 0.25 }), b = skirtOf({ action: "walk", phase: 0.75 });
  const mid = (x) => x.pts.reduce((sum, p) => sum + p[0], 0) / x.pts.length;
  assert.ok(Math.abs(mid(a) - mid(b)) > 10, "hem does not move with the stride");
  assert.equal(record({ ...BASE, top: { style: "plain", color: "#f7f2e8" } }).filter((x) => x.style === "#f7f2e8").length, 1);
});

test("wide hat: brim and crown in the hat colour, ribbon and flower in the top's accent colour", () => {
  const ops = record({ ...BASE, top: { style: "dress", color: "#f7f2e8", accent_color: "#c2185b" },
    headwear: { kind: "wide_hat", color: "#eeeeee" } });
  assert.ok(ops.filter((x) => x.op === "fill" && x.style === "#eeeeee").length >= 2);
  assert.ok(ops.filter((x) => x.op === "fill" && x.style === "#c2185b").length >= 6); // band + 5 petals
  const brim = ops.find((x) => x.op === "fill" && x.style === "#eeeeee");
  const span = Math.max(...brim.pts.map((p) => p[0])) - Math.min(...brim.pts.map((p) => p[0]));
  assert.ok(span > 380 && span < 512, `brim span ${span}: wide, inside the card`);
});

// --- batch render: a crowd and runners, twice ---
let R, part;
before(async () => {
  part = fixturePart(temps, (s) => {
    s.shots[0].set = "stadium";
    s.shots[0].extras = Array.from({ length: 8 }, (_, i) => ({ id: `crowd${i + 1}`, kind: "crowd", action: ["cheer", "angry", "gasp", "neutral"][i % 4],
      start_pos: [-2.6 + 0.75 * i, i % 2 ? -1.4 : -2.2], facing: "camera", variant: i * 13 }));
    s.shots[1].extras = [0, 1, 2].map((i) => ({ id: `runner${i + 1}`, kind: "runner", action: "run",
      start_pos: [-3 - i, -1.5 - 0.2 * i], end_pos: [2.2 - i, -1.5 - 0.2 * i], facing: "right", variant: 5 + i }));
    return s;
  });
  R = await renderNamed({ a: frames(part, "30-30", "a"), b: frames(part, "30-30", "b"), a2: frames(part, "90-90", "a"),
    b2: frames(part, "90-90", "b") });
});

test("crowd and runner extras render, and the same frame renders to the same bytes", () => {
  for (const n of ["a", "b", "a2", "b2"]) jobOk(R, n);
  for (const f of [30, 90]) {
    const a = png(path.join(part, "a"), f), b = png(path.join(part, "b"), f);
    assert.ok(a.length > 10000 && a.equals(b), `frame ${f}`);
  }
});
