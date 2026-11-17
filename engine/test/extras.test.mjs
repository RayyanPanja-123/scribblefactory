// Step 5c-7: extras looks and crowd-mood timing (page/extras.js, pure), mood poses, dress + wide hat drawing
// (recording 2D context), and one batch render with a crowd and runners: same frame, same bytes.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { after, before, test } from "node:test";
import { EXTRA_SATURATION, EXTRA_TOPS, GAP, MOOD_EXPRESSION, desaturate, extraLook, fitCrowd, moodAt, placeExtras } from "../page/extras.js";
import { CW, FEET_Y, drawStickman, skeleton } from "../page/stickman.js";
import { fixturePart, frames, jobOk, png, render, renderNamed } from "./batch.mjs";

const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });

/** fake canvas: every fill / stroke with its style and path points (pre-transform canvas px) */
function record(o) {
  const ops = [];
  let pts = [];
  const g = {
    setTransform() {}, clearRect() {}, translate() {}, rotate() {}, save() {}, restore() {}, clip() {}, closePath() {},
    beginPath() { pts = []; }, moveTo(x, y) { pts.push([x, y]); }, lineTo(x, y) { pts.push([x, y]); }, arc(x, y) { pts.push([x, y]); },
    fill() { ops.push({ op: "fill", style: this.fillStyle, pts, lw: this.lineWidth }); },
    stroke() { ops.push({ op: "stroke", style: this.strokeStyle, pts, lw: this.lineWidth }); },
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
    assert.ok(EXTRA_TOPS.map((x) => desaturate(x)).includes(c.top.color) && ["plain", "shirt"].includes(c.top.style) && !c.top.number);
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

// --- arm count: every pose draws exactly two arms (no rest pose underneath) ---
/** arm strokes: width 9, three points (shoulder, elbow, hand), starting at a shoulder (x = CW/2 +- 66, jittered) */
const armStrokes = (ops) => ops.filter((x) => x.op === "stroke" && x.pts.length === 3 && x.lw === 9
  && x.pts[0][0] && Math.min(Math.abs(x.pts[0][0] - (CW / 2 - 66)), Math.abs(x.pts[0][0] - (CW / 2 + 66))) < 6);

test("cheer / angry / gasp (and every other pose) draw exactly two arms, for extras and cast", () => {
  const extra = { ...extraLook("s", { kind: "crowd", variant: 3 }) };
  const cast = { top: { style: "tank", color: "#e53935", number: "31" }, legwear: { kind: "shorts", color: "#2b2b2b" },
    props: [{ kind: "clipboard", hand: "right" }, { kind: "stopwatch", hand: "left" }] };
  for (const look of [extra, cast]) {
    for (const action of ["idle", "talk", "walk", "cheer", "angry", "gasp", "eat", "give", "carried", "stagger"]) {
      for (const k of [0, 0.5, 1]) {
        const ops = record({ ...BASE, ...look, color: look.top.color, action, mood: { k, shake: 0.4, bounce: 0 },
          eat: { k, side: 1 }, reach: { side: 1, k } });
        assert.equal(armStrokes(ops).length, 2, `${action} k=${k}: ${armStrokes(ops).length} arms`);
      }
    }
  }
});

test("cheer pump keeps the arms high (no sweep into neighbours)", () => {
  for (let t = 0; t < 2; t += 0.05) assert.ok(moodAt("cheer", t, "k").k >= 0.7);
});

// --- head-overlap rule (fake camera: screen x = world x, head rect from x and z depth) ---
const fakeRect = (x, z) => { const s = 1 / (3 - z); return [x - 0.3 * s, 0.5, x + 0.3 * s, 0.9]; }; // farther: smaller
const castAt = (xs) => ({ setCamera() {}, castRects: () => xs.map((x) => fakeRect(x, 0)),
  headRect: (e, dx) => fakeRect(e.start_pos[0] + dx, e.start_pos[1]) });
const crowdE = (id, x, z = -1.9) => ({ id, kind: "crowd", action: "cheer", start_pos: [x, z], facing: "camera", variant: 1 });

test("an extra whose head would overlap a cast head moves along its row, keeping its gap; else it is dropped", () => {
  const extras = [crowdE("crowd1", -1.2), crowdE("crowd2", 0.05), crowdE("crowd3", 1.2)];
  const r = placeExtras(extras, castAt([0]));
  assert.equal(r.get("crowd1"), 0);
  assert.equal(r.get("crowd3"), 0);
  const moved = 0.05 + r.get("crowd2");
  assert.ok(r.get("crowd2") !== 0 && r.get("crowd2") !== null);
  assert.ok(Math.abs(moved) >= 0.3 * (1 + 0.12) / 3 + 0.3 / 4.9, `still over the cast head at ${moved}`); // cleared
  for (const x of [-1.2, 1.2]) assert.ok(Math.abs(moved - x) >= GAP.crowd - 1e-9);
  // boxed in: cast heads everywhere along the row -> dropped for the shot
  const all = placeExtras([crowdE("crowd1", 0)], castAt(Array.from({ length: 25 }, (_, i) => -1.8 + i * 0.15)));
  assert.equal(all.get("crowd1"), null);
  // deterministic
  assert.deepEqual([...placeExtras(extras, castAt([0]))], [...r]);
});

test("runner heads are checked along their whole run; rows keep the runner gap", () => {
  const runner = (id, x0, x1, z) => ({ id, kind: "runner", action: "run", start_pos: [x0, z], end_pos: [x1, z], facing: "right", variant: 2 });
  const opts = { setCamera() {}, castRects: () => [fakeRect(0, 0)],
    headRect: (e, dx, u) => fakeRect(e.start_pos[0] + (e.end_pos[0] - e.start_pos[0]) * u + dx, e.start_pos[1]) };
  const r = placeExtras([runner("runner1", -3, 3, -2.2), runner("runner2", 2.4, 4, -2.2), runner("runner3", 2.5, 4, -2.2)], opts);
  assert.equal(r.get("runner1"), null);            // crosses right behind the cast head: dropped
  assert.equal(r.get("runner2"), 0);
  assert.ok(Math.abs(2.5 + r.get("runner3") - 2.4) >= GAP.runner - 1e-9); // pushed 0.6 clear of runner2
});

test("extras draw at 85% saturation: the cast's own colours are untouched", () => {
  assert.equal(EXTRA_SATURATION, 0.85);
  assert.equal(desaturate("#ff0000", 1), "#ff0000");
  assert.equal(desaturate("#808080"), "#808080");                 // greys stay grey
  const sat = (hex) => { const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2; return (mx - mn) / (1 - Math.abs(2 * l - 1)); };
  for (const c of EXTRA_TOPS) assert.ok(Math.abs(sat(desaturate(c)) - 0.85 * sat(c)) < 0.03, c);
});

// --- crowd fits the visible frame ---
test("fitCrowd: rows span only the visible width (minus margin), extra rows absorb the rest, the rest drop", () => {
  const crowd = Array.from({ length: 12 }, (_, i) => crowdE(`crowd${i + 1}`, -2.8 + 0.5 * i, i % 2 ? -2.5 : -1.9));
  const narrow = (z) => [-0.9 + 0.1 * z, 0.9 - 0.1 * z];             // ~1.8 wide, a little wider further back
  const r = fitCrowd(crowd, narrow, { zBack: -2.8 });
  const placed = [...r.values()].filter(Boolean);
  const rows = new Map();
  for (const p of placed) rows.set(p.pos[1], [...(rows.get(p.pos[1]) || []), p.pos[0]]);
  assert.ok(rows.size >= 3, `only ${rows.size} rows`);                           // rows absorb what one cannot hold
  for (const [z, xs] of rows) {
    const [lo, hi] = narrow(z);
    for (const x of xs) assert.ok(x >= lo + 0.2 - 1e-9 && x <= hi - 0.2 + 1e-9, `x ${x} outside the frame at z ${z}`);
    xs.sort((a, b) => a - b);
    assert.ok(xs.every((x, i) => !i || x - xs[i - 1] >= GAP.crowd - 1e-9), `row ${z} too tight: ${xs}`);
    assert.ok(z <= -1.9 + 1e-9 && z >= -2.8 - 1e-9);
  }
  assert.equal(placed.length + [...r.values()].filter((v) => v === null).length, 12);
  assert.deepEqual([...fitCrowd(crowd, narrow, { zBack: -2.8 })], [...r]);      // deterministic
  const wide = fitCrowd(crowd, () => [-3, 3], { zBack: -2.8 });
  assert.ok([...wide.values()].every(Boolean));                                  // room for everyone: nobody dropped
  const none = fitCrowd(crowd, () => [0, 0.3], { zBack: -2.8 });                 // no room at all: all dropped
  assert.ok([...none.values()].every((v) => v === null));
});

test("fitCrowd skips spots over a cast head (free = false) and uses deeper rows instead of dropping", () => {
  // rows 1-2 (z -1.9, -2.2) keep only the sides free: 4 spots each; the other 2 go one row deeper
  const crowd = Array.from({ length: 10 }, (_, i) => crowdE(`crowd${i + 1}`, 0, -1.9));
  const blocked = (x, z) => !(Math.abs(x) < 0.7 && z > -2.3);                    // a head covers the middle of rows 1-2
  const r = fitCrowd(crowd, () => [-1.6, 1.6], { zBack: -2.8, free: blocked });
  const placed = [...r.values()].filter(Boolean);
  assert.equal(placed.length, 10, "nobody needs dropping: deeper rows are free in the middle");
  for (const p of placed) assert.ok(blocked(...p.pos), `extra on a blocked spot ${p.pos}`);
  assert.ok(placed.some((p) => p.pos[1] < -2.3), "a deeper row was used");
});

// --- the stadium rail (geometry only) ---
let loop;
before(async () => { loop = await render("--loop-check"); });

test("the stadium has a low painted rail between the track and the stands, in every variant", () => {
  assert.equal(loop.status, 0, loop.stderr);
  const res = JSON.parse(loop.stdout.slice(loop.stdout.indexOf("[")));
  const stadium = res.filter((r) => r.set === "stadium");
  assert.ok(stadium.length >= 2 && stadium.every((r) => r.named.includes("rail")));
  assert.ok(res.filter((r) => r.set !== "stadium").every((r) => !r.named.includes("rail")));
});

// --- batch render: a crowd and runners, twice ---
let R, part, fit;
before(async () => {
  part = fixturePart(temps, (s) => {
    s.shots[0].set = "stadium";
    s.shots[0].extras = Array.from({ length: 8 }, (_, i) => ({ id: `crowd${i + 1}`, kind: "crowd", action: ["cheer", "angry", "gasp", "neutral"][i % 4],
      start_pos: [-2.6 + 0.75 * i, i % 2 ? -1.4 : -2.2], facing: "camera", variant: i * 13 }));
    s.shots[1].extras = [0, 1, 2].map((i) => ({ id: `runner${i + 1}`, kind: "runner", action: "run",
      start_pos: [-3 - i, -1.5 - 0.2 * i], end_pos: [2.2 - i, -1.5 - 0.2 * i], facing: "right", variant: 5 + i }));
    return s;
  });
  // 12 cheering extras on the stadium (as the planner lays them: two rows), s01 wide, s02 medium on bob at x 2.4
  fit = fixturePart(temps, (s) => {
    const crowd = Array.from({ length: 12 }, (_, i) => ({ id: `crowd${i + 1}`, kind: "crowd", action: "cheer",
      start_pos: [-2.4 + 0.8 * (i % 7) + (i >= 7 ? 0.4 : 0), i >= 7 ? -2.5 : -1.95], facing: "camera", variant: i * 7 }));
    for (const [k, angle] of [[0, "wide"], [1, "medium"]]) {
      Object.assign(s.shots[k], { set: "stadium", extras: crowd });
      s.shots[k].camera.angle = angle;
    }
    s.shots[2].set = "stadium";
    return s;
  });
  R = await renderNamed({ a: frames(part, "30-30", "a"), b: frames(part, "30-30", "b"), a2: frames(part, "90-90", "a"),
    b2: frames(part, "90-90", "b"), wide: frames(fit, "0-59", "w"), wide2: frames(fit, "0-59", "v"),
    medium: frames(fit, "60-119", "m") });
});

test("a 12-extra stadium crowd lands wholly in frame in wide and medium shots; dropped extras are logged", () => {
  for (const n of ["wide", "medium"]) {
    jobOk(R, n);
    const lines = R[n].out.split("\n").filter((l) => l.includes(" ms -> ")); // one per rendered frame
    assert.equal(lines.length, 60, `${n}: ${lines.length} frame lines`);
    for (const l of lines) {
      assert.match(l, /\[extras dropped: \d+\]/, `${n}: no dropped count in: ${l}`);
      assert.doesNotMatch(l, /OUT OF FRAME/, `${n}: ${l}`);
    }
  }
  // the same frames twice: same bytes, same log
  jobOk(R, "wide2");
  for (const f of [0, 29, 59]) assert.ok(png(path.join(fit, "w"), f).equals(png(path.join(fit, "v"), f)), `frame ${f}`);
  const counts = (o) => o.split("\n").map((l) => l.match(/extras dropped: (\d+)/)?.[1]).filter(Boolean);
  assert.deepEqual(counts(R.wide.out), counts(R.wide2.out));
});

test("crowd and runner extras render, and the same frame renders to the same bytes", () => {
  for (const n of ["a", "b", "a2", "b2"]) jobOk(R, n);
  for (const f of [30, 90]) {
    const a = png(path.join(part, "a"), f), b = png(path.join(part, "b"), f);
    assert.ok(a.length > 10000 && a.equals(b), `frame ${f}`);
  }
});
