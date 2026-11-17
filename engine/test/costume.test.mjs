// Cast v2 costumes: pure drawing checks against a recording 2D context, plus rendered cast-sheet / car frames.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { drawStickman, skeleton } from "../page/stickman.js";

const ENGINE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FIX = path.join(ENGINE, "..", "pipeline", "tests", "fixtures", "story");

/** fake canvas: records every fill / stroke with its style and the path points (pre-transform canvas px) */
function record(o) {
  const ops = [];
  let pts = [];
  const g = {
    setTransform() {}, clearRect() {}, translate() {}, rotate() {}, save() {}, restore() {}, clip() {}, closePath() {},
    beginPath() { pts = []; }, moveTo(x, y) { pts.push([x, y]); }, lineTo(x, y) { pts.push([x, y]); },
    arc(x, y) { pts.push([x, y]); },
    fill() { ops.push({ op: "fill", style: this.fillStyle, pts }); },
    stroke() { ops.push({ op: "stroke", style: this.strokeStyle, pts }); },
  };
  drawStickman({ getContext: () => g }, o);
  return ops;
}
const fills = (ops, colour) => ops.filter((x) => x.op === "fill" && x.style === colour);
const mean = (pts) => pts.reduce(([a, b], [x, y]) => [a + x / pts.length, b + y / pts.length], [0, 0]);
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

const BASE = { seed: "t:bob", boil: 0, color: "#3a7bd5", eyes: "dots", expression: "neutral", action: "idle",
  phase: 0, lid: 0, mouth: 0, breath: 0, facing: "camera", t: 0 };
const TOPS = ["plain", "suit", "tank", "shirt"], HATS = ["flat_cap", "postman_cap", "bowler", "straw_hat"];
const LEGS = ["shorts", "ragged_shorts", "trousers"];
const PROPS = { clipboard: "#a8743a", stopwatch: "#cfd3d6", bottle: "#7fb8d6", syringe: "#eef6f8", apple: "#d93a2b",
  medal: "#e8b923" };

test("every top, headwear, legwear, prop and expression builds and draws in its colour", () => {
  for (const style of TOPS) {
    const ops = record({ ...BASE, top: { style, color: "#111111", accent_color: "#b71c1c", number: "31" } });
    assert.ok(fills(ops, "#111111").length >= 1, style);
    if (style === "suit") assert.ok(fills(ops, "#b71c1c").length >= 2, "suit tie");
  }
  for (const kind of HATS) assert.ok(fills(record({ ...BASE, headwear: { kind, color: "#222222" } }), "#222222").length, kind);
  for (const kind of LEGS) assert.equal(fills(record({ ...BASE, legwear: { kind, color: "#333333" } }), "#333333").length, 2, kind);
  for (const [kind, colour] of Object.entries(PROPS)) {
    assert.ok(fills(record({ ...BASE, prop: { kind, hand: "right" } }), colour).length, kind);
  }
  for (const expression of ["cheeky", "exhausted"]) {
    for (const facing of ["camera", "right", "left"]) record({ ...BASE, expression, facing });
  }
  // nothing costume-related is drawn for a plain v1-style figure: same ops with or without "none" costume parts
  const none = { top: { style: "plain", color: BASE.color }, headwear: { kind: "none" }, legwear: { kind: "none" },
    prop: { kind: "none", hand: "right" } };
  assert.deepEqual(record({ ...BASE, ...none }), record(BASE));
});

test("same options, same drawing (determinism); boil changes the jitter", () => {
  const o = { ...BASE, top: { style: "tank", color: "#e53935", number: "31" }, legwear: { kind: "shorts", color: "#2b2b2b" },
    headwear: { kind: "postman_cap", color: "#2e3a59" }, prop: { kind: "clipboard", hand: "right" }, expression: "cheeky" };
  assert.deepEqual(record(o), record(o));
  assert.notDeepEqual(record(o), record({ ...o, boil: 1 }));
});

test("held prop follows its hand through idle, point, wave, run and talk gestures; left hand works too", () => {
  const poses = [{ action: "idle" }, { action: "point" }, { action: "wave", wave: { k: 1, swing: 0.5 } },
    { action: "run", phase: 0.25, facing: "right" }, { action: "talk", gesture: { kind: "shrug", k: 1 } }];
  let prev = null;
  for (const hand of ["right", "left"]) for (const pose of poses) {
    const o = { ...BASE, ...pose, prop: { kind: "clipboard", hand } };
    const k = skeleton(o), h = k.arms[hand === "left" ? 0 : 1][2];
    const [board] = fills(record(o), PROPS.clipboard);
    assert.ok(dist(mean(board.pts), h) < 90, `${hand} ${pose.action}: board ${mean(board.pts)} far from hand ${h}`);
    if (prev && dist(h, prev.h) > 5) assert.ok(dist(mean(board.pts), prev.c) > 5, `${hand} ${pose.action}: prop did not move`);
    prev = { h, c: mean(board.pts) };
  }
});

test("seated: the prop hand comes up to the chest (above the car panel), except a waving prop arm", () => {
  const o = { ...BASE, action: "ride", prop: { kind: "bottle", hand: "right" } };
  const standing = skeleton(o).arms[1][2], seated = skeleton({ ...o, seated: true });
  assert.ok(seated.arms[1][2][1] < standing[1] - 100, "prop hand not raised");
  assert.ok(seated.arms[1][2][1] < seated.hipY - 150);
  const wave = { ...o, action: "wave", wave: { k: 1, swing: 0 } };
  assert.deepEqual(skeleton({ ...wave, seated: true }).arms, skeleton(wave).arms);
});

test("legwear follows the leg animation: each tube lies along its leg at every walk phase", () => {
  let prev = null;
  for (const kind of LEGS) for (const phase of [0, 0.15, 0.3, 0.6, 0.85]) {
    const o = { ...BASE, action: "walk", facing: "right", phase, legwear: { kind, color: "#333333" } };
    const k = skeleton(o), tubes = fills(record(o), "#333333");
    tubes.forEach(({ pts }, i) => {
      const [[hx, hy], [fx, fy]] = k.legs[i], c = mean(pts);
      const off = Math.abs((fx - hx) * (c[1] - hy) - (fy - hy) * (c[0] - hx)) / Math.hypot(fx - hx, fy - hy);
      assert.ok(off < 8, `${kind} phase ${phase} leg ${i}: tube ${off.toFixed(1)} px off the leg`);
      assert.ok(c[1] > hy, `${kind} tube starts below the hip`);
    });
    if (prev && kind === prev.kind) assert.notDeepEqual(tubes[0].pts, prev.pts, "legwear did not move with the leg");
    prev = { kind, pts: tubes[0].pts };
  }
});

// --- rendered ---
const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });
const render = (...args) => spawnSync(process.execPath, [path.join(ENGINE, "render.mjs"), ...args, "--swiftshader"], { encoding: "utf8" });

/** fixture series as v2 with a costumed bob; amy stays a v1 entry (outfit_color): the engine reads both */
function v2Series(dir, bobProp = "clipboard") {
  const s = JSON.parse(fs.readFileSync(path.join(FIX, "series.json"), "utf8"));
  s.schema_version = 2;
  const { outfit_color, ...bob } = s.cast[0];
  s.cast[0] = { ...bob, top: { style: "tank", color: outfit_color, accent_color: null, number: "7" },
    headwear: { kind: "flat_cap", color: "#6d5843" }, legwear: { kind: "shorts", color: "#2b2b2b" },
    prop: { kind: bobProp, hand: "right" }, default_expression: "cheeky" };
  fs.writeFileSync(path.join(dir, "series.json"), JSON.stringify(s));
}

test("cast sheet with costumes (v2 + v1 entries): 22 images, byte-identical on a second run", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-costume-"));
  temps.push(dir);
  v2Series(dir);
  const shots = [];
  for (let i = 0; i < 2; i++) {
    const r = render("--series", dir, "--cast-sheet");
    assert.equal(r.status, 0, r.stderr);
    const m = JSON.parse(fs.readFileSync(path.join(dir, "cast-frames", "manifest.json"), "utf8"));
    assert.equal(m.frames.length, 2 * 11);
    shots.push(m.frames.map((f) => fs.readFileSync(path.join(dir, "cast-frames", f.file))));
  }
  shots[0].forEach((b, i) => assert.ok(b.equals(shots[1][i]), `cast frame ${i} differs between runs`));
  // idle uses the cast default (cheeky), the explicit neutral column does not
  const label = (l) => JSON.parse(fs.readFileSync(path.join(dir, "cast-frames", "manifest.json"), "utf8")).frames.findIndex((f) => f.label === l);
  assert.ok(shots[0][label("bob idle")].equals(shots[0][label("bob cheeky")]));
  assert.ok(!shots[0][label("bob idle")].equals(shots[0][label("bob neutral")]));
});

test("a rider's prop is visible in the car", () => {
  const frames = ["bottle", "none"].map((prop) => {
    const series = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-costume-"));
    temps.push(series);
    const part = path.join(series, "part-01");
    fs.mkdirSync(part);
    v2Series(series, prop);
    fs.copyFileSync(path.join(FIX, "phrases.json"), path.join(part, "phrases.json"));
    const s = JSON.parse(fs.readFileSync(path.join(FIX, "story.json"), "utf8"));
    Object.assign(s.shots[0], { set: "dirt_road", travel: { speed: 4.0 } });
    s.shots[0].actors = [{ cast_id: "bob", action: "ride", start_pos: [0, 0], facing: "left", expression: "neutral" }];
    s.shots[0].vehicles = [{ id: "car1", kind: "car", action: "drive", start_pos: [0, 0], end_pos: [0, 0],
      facing: "left", riders: ["bob"], variant: "red" }];
    fs.writeFileSync(path.join(part, "story.json"), JSON.stringify(s));
    const out = path.join(part, "f.png"), r = render("--part", part, "--frame", "20", "--out", out);
    assert.equal(r.status, 0, r.stderr);
    assert.match(r.stdout, /\[car car1 drive \(bob\)/);
    return fs.readFileSync(out);
  });
  assert.ok(!frames[0].equals(frames[1]), "the held bottle does not show in the car");
});
