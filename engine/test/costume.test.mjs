// Cast costumes: pure drawing checks against a recording 2D context, plus rendered cast-sheet / car frames (one batch).
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { FEET_Y, FIGURE_PX, HAT_BRIM, drawStickman, hatFit, skeleton } from "../page/stickman.js";
import { setLibrary } from "../page/library.js";
import { FIX, fixturePart, jobOk, renderNamed } from "./batch.mjs";

/** fake canvas: records every fill / stroke with its style and the path points (pre-transform canvas px) */
function record(o) {
  const ops = [];
  let pts = [];
  const g = {
    setTransform() {}, clearRect() {}, translate() {}, rotate() {}, scale() {}, save() {}, restore() {}, clip() {}, closePath() {},
    fillRect() {}, createLinearGradient: () => ({ addColorStop() {} }), createRadialGradient: () => ({ addColorStop() {} }),
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
const ys = (pts) => pts.map(([, y]) => y), xsNear = (pts, y, d) => pts.filter(([, py]) => Math.abs(py - y) < d).map(([x]) => x);

const BASE = { seed: "t:bob", boil: 0, color: "#3a7bd5", eyes: "dots", expression: "neutral", action: "idle",
  phase: 0, lid: 0, mouth: 0, breath: 0, facing: "camera", t: 0 };
const TOPS = ["plain", "suit", "tank", "shirt"], HATS = ["flat_cap", "postman_cap", "bowler", "straw_hat"];
const LEGS = ["shorts", "ragged_shorts", "trousers"];
const PROPS = { clipboard: "#a8743a", stopwatch: "#cfd3d6", bottle: "#7fb8d6", syringe: "#eef6f8", apple: "#d93a2b",
  medal: "#e8b923" };
const POSES = [{ action: "idle" }, { action: "point" }, { action: "wave", wave: { k: 1, swing: 0.5 } },
  { action: "run", phase: 0.25, facing: "right" }, { action: "walk", phase: 0.6, facing: "left" },
  { action: "talk", gesture: { kind: "shrug", k: 1 } }, { action: "react" }, { action: "ride", seated: true }];

test("every top, headwear, legwear, prop and expression builds and draws in its colour", () => {
  for (const style of TOPS) {
    const ops = record({ ...BASE, top: { style, color: "#111111", accent_color: "#b71c1c", number: "31" } });
    assert.ok(fills(ops, "#111111").length >= 1, style);
    if (style === "suit") assert.ok(fills(ops, "#b71c1c").length >= 2, "suit tie");
  }
  for (const kind of HATS) assert.ok(fills(record({ ...BASE, headwear: { kind, color: "#222222" } }), "#222222").length, kind);
  for (const kind of LEGS) assert.equal(fills(record({ ...BASE, legwear: { kind, color: "#333333" } }), "#333333").length, 2, kind);
  for (const [kind, colour] of Object.entries(PROPS)) {
    assert.ok(fills(record({ ...BASE, props: [{ kind, hand: "right" }] }), colour).length, kind);
  }
  for (const expression of ["cheeky", "exhausted", "dead"]) {
    for (const facing of ["camera", "right", "left"]) record({ ...BASE, expression, facing });
  }
  // nothing costume-related is drawn for a plain figure: same ops with or without "none" costume parts
  const none = { top: { style: "plain", color: BASE.color }, headwear: { kind: "none" }, legwear: { kind: "none" }, props: [] };
  assert.deepEqual(record({ ...BASE, ...none }), record(BASE));
});

test("custom props (library/props.json) draw every shape in its colour, in either hand; an unknown kind throws", () => {
  setLibrary({ props: [{ id: "flag", name: "Flag", shapes: [
    { shape: "line", pts: [[0, 40], [0, -120]], width: 6 },
    { shape: "rect", pts: [[0, -120], [70, -80]], fill: "#123456" },
    { shape: "circle", pts: [[0, -124]], r: 8, fill: "#abcdef" },
    { shape: "poly", pts: [[0, -80], [40, -60], [0, -40]], fill: "#fedcba", width: 0 },
  ] }] });
  for (const hand of ["left", "right"]) {
    const ops = record({ ...BASE, props: [{ kind: "flag", hand }] });
    for (const c of ["#123456", "#abcdef", "#fedcba"]) assert.ok(fills(ops, c).length, `${hand}: ${c}`);
  }
  assert.throws(() => record({ ...BASE, props: [{ kind: "nope", hand: "right" }] }), /unknown prop "nope"/);
  setLibrary({ props: [] });
});

test("same options, same drawing (determinism); boil changes the jitter", () => {
  const o = { ...BASE, top: { style: "tank", color: "#e53935", number: "31" }, legwear: { kind: "shorts", color: "#2b2b2b" },
    headwear: { kind: "postman_cap", color: "#2e3a59" }, expression: "cheeky",
    props: [{ kind: "clipboard", hand: "right" }, { kind: "stopwatch", hand: "left" }] };
  assert.deepEqual(record(o), record(o));
  assert.notDeepEqual(record(o), record({ ...o, boil: 1 }));
});

test("every hat sits down on the head: band past the outline at forehead level, top covered, inside the framing height", () => {
  for (const kind of HATS) for (const seed of ["a:x", "b:y", "marathon-1904:carvajal", "s:fred"])
    for (let boil = 0; boil < 8; boil++) for (const breath of [-1, 1]) for (const [action, facing, bob] of
      [["idle", "camera", 0], ["talk", "right", 1], ["react", "camera", 0], ["idle", "left", 0]]) {
      const o = { ...BASE, seed, boil, breath, bob, action, facing, headwear: { kind, color: "#222222" } };
      const ops = record(o), [, hy] = skeleton(o).head, at = `${kind} ${seed} boil ${boil} breath ${breath} ${action}`;
      const head = ops.find((x) => x.op === "fill" && x.style === "#ffffff" && x.pts.length === 44).pts;
      const hat = fills(ops, "#222222").flatMap((x) => x.pts), fit = hatFit(head, hy);
      assert.equal(fit.brim, hy - HAT_BRIM);
      assert.ok(fit.brim < hy - 80 && fit.brim > Math.min(...ys(head)) + 40, `${at}: brim not at the forehead`);
      assert.ok(Math.max(...ys(hat)) >= fit.brim - 2, `${at}: hat floats above the brim line`);
      const band = xsNear(hat, fit.brim, 14);
      assert.ok(Math.min(...band) <= fit.xl - 4 && Math.max(...band) >= fit.xr + 4,
        `${at}: band ${Math.min(...band).toFixed(0)}..${Math.max(...band).toFixed(0)} inside the head outline `
        + `${fit.xl.toFixed(0)}..${fit.xr.toFixed(0)}`);
      assert.ok(Math.min(...ys(hat)) < Math.min(...ys(head)), `${at}: head top pokes out of the hat`);
      assert.ok(Math.min(...ys(hat)) - 8 >= FEET_Y - FIGURE_PX, `${at}: hat above the framing height`);
    }
});

test("two props: each follows its own arm through every pose, seated in the car included", () => {
  const props = [{ kind: "clipboard", hand: "right" }, { kind: "stopwatch", hand: "left" }];
  const prev = {};
  for (const pose of POSES) {
    const o = { ...BASE, ...pose, props }, k = skeleton(o), ops = record(o);
    for (const [i, { kind }] of [[1, props[0]], [0, props[1]]]) {
      const hand = k.arms[i][2], [shape] = fills(ops, PROPS[kind]);
      const c = mean(shape.pts);
      assert.ok(dist(c, hand) < 90, `${kind} in ${pose.action}: ${c} far from hand ${hand}`);
      if (prev[kind] && dist(hand, prev[kind].hand) > 5) assert.ok(dist(c, prev[kind].c) > 5, `${kind} did not move in ${pose.action}`);
      prev[kind] = { hand, c };
    }
  }
});

test("seated: prop hands come up to the chest (above the car panel); a waving right arm keeps waving", () => {
  const props = [{ kind: "bottle", hand: "right" }, { kind: "apple", hand: "left" }];
  const o = { ...BASE, action: "ride", props }, standing = skeleton(o), seated = skeleton({ ...o, seated: true });
  for (const i of [0, 1]) {
    assert.ok(seated.arms[i][2][1] < standing.arms[i][2][1] - 100, `prop hand ${i} not raised`);
    assert.ok(seated.arms[i][2][1] < seated.hipY - 150);
  }
  const wave = { ...o, action: "wave", wave: { k: 1, swing: 0 } };
  assert.deepEqual(skeleton({ ...wave, seated: true }).arms[1], skeleton(wave).arms[1]);
  assert.ok(skeleton({ ...wave, seated: true }).arms[0][2][1] < skeleton(wave).arms[0][2][1] - 100);
});

test("legwear follows the leg animation: each tube lies along its leg at every walk phase", () => {
  let prev = null;
  for (const kind of LEGS) for (const phase of [0, 0.15, 0.3, 0.6, 0.85]) {
    const o = { ...BASE, action: "walk", facing: "right", phase, legwear: { kind, color: "#333333" } };
    const k = skeleton(o), tubes = fills(record(o), "#333333");
    // each piece (a straight leg's tube, or a bent leg's thigh, knee and shin) sits on a segment of a leg
    const segs = k.legs.flatMap(([hip, foot], i) => (k.knees ? [[hip, k.knees[i]], [k.knees[i], foot]] : [[hip, foot]]));
    const toSeg = ([px, py], [[ax, ay], [bx, by]]) => {
      const u = Math.max(0, Math.min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)));
      return Math.hypot(px - ax - u * (bx - ax), py - ay - u * (by - ay));
    };
    tubes.forEach(({ pts }, i) => {
      const c = mean(pts), off = Math.min(...segs.map((sg) => toSeg(c, sg)));
      assert.ok(off < 8, `${kind} phase ${phase} piece ${i}: ${off.toFixed(1)} px off the leg`);
      assert.ok(c[1] > k.hipY, `${kind} piece starts below the hip`);
    });
    if (prev && kind === prev.kind) assert.notDeepEqual(tubes[0].pts, prev.pts, "legwear did not move with the leg");
    prev = { kind, pts: tubes[0].pts };
  }
});

// --- rendered (one batch) ---
const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });

/** fixture series as v3 with a costumed bob; amy stays a v1 entry (outfit_color): the engine reads both.
 *  bobProps: v3 props list, or { prop } for a v2-style single prop */
function series(bobProps) {
  const s = JSON.parse(fs.readFileSync(path.join(FIX, "series.json"), "utf8"));
  s.schema_version = 3;
  const { outfit_color, ...bob } = s.cast[0];
  s.cast[0] = { ...bob, top: { style: "tank", color: outfit_color, accent_color: null, number: "7" },
    headwear: { kind: "flat_cap", color: "#6d5843" }, legwear: { kind: "shorts", color: "#2b2b2b" },
    default_expression: "cheeky", ...(Array.isArray(bobProps) ? { props: bobProps } : bobProps) };
  return s;
}
const TWO = [{ kind: "bottle", hand: "right" }, { kind: "medal", hand: "left" }];
const sheetDir = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-costume-"));
temps.push(sheetDir);
fs.writeFileSync(path.join(sheetDir, "series.json"), JSON.stringify(series(TWO)));
/** s01: bob rides a left-facing car on a dirt road */
const ride = (bobProps) => fixturePart(temps, (s) => {
  Object.assign(s.shots[0], { set: "dirt_road", travel: { speed: 4.0 } });
  s.shots[0].actors = [{ cast_id: "bob", action: "ride", start_pos: [0, 0], facing: "left", expression: "neutral" }];
  s.shots[0].vehicles = [{ id: "car1", kind: "car", action: "drive", start_pos: [0, 0], end_pos: [0, 0],
    facing: "left", riders: ["bob"], variant: "red" }];
  return s;
}, series(bobProps));
const rides = { two: ride(TWO), none: ride([]), v2: ride({ prop: { kind: "bottle", hand: "right" } }),
  one: ride([TWO[0]]) };
const rideJob = (k, tag = "f") => ["--part", rides[k], "--frame", "20", "--out", path.join(rides[k], `${tag}.png`)];
let R;
before(async () => {
  R = await renderNamed({ sheet: ["--series", sheetDir, "--cast-sheet"], two: rideJob("two"), again: rideJob("two", "g"),
    none: rideJob("none"), v2: rideJob("v2"), one: rideJob("one") });
});
const img = (k, tag = "f") => fs.readFileSync(path.join(rides[k], `${tag}.png`));

test("cast sheet with costumes (v3 + v1 entries): one image per pose each; idle uses the cast default expression", () => {
  jobOk(R, "sheet");
  const m = JSON.parse(fs.readFileSync(path.join(sheetDir, "cast-frames", "manifest.json"), "utf8"));
  assert.equal(m.frames.length, 2 * 19); // render.mjs POSES: idle, walk, talk, 9 expressions, 5 actions, 2 moods
  const f = (l) => fs.readFileSync(path.join(sheetDir, "cast-frames", m.frames.find((x) => x.label === l).file));
  assert.ok(f("bob idle").equals(f("bob cheeky")));
  assert.ok(!f("bob idle").equals(f("bob neutral")));
});

test("riders' props show in the car (both hands), deterministic; a v2 single prop reads like a one-item list", () => {
  for (const k of ["two", "again", "none", "v2", "one"]) jobOk(R, k);
  assert.match(R.two.out, /\[car car1 drive \(bob\)/);
  assert.ok(img("two").equals(img("two", "g")), "costumed car frame not deterministic");
  assert.ok(!img("two").equals(img("none")), "held props do not show in the car");
  assert.ok(!img("two").equals(img("one")), "the second prop does not show in the car");
  assert.ok(img("v2").equals(img("one")), "v2 prop differs from the same prop as a list");
});

test("held props draw in front of the head, hair and beard; angle tips them outward like a clock hand; grip moves the hold", () => {
  const STAFF = "#5a3a1e", TIP = "#e0b03c";
  setLibrary({ props: [{ id: "staff", name: "Staff", shapes: [
    { shape: "rect", pts: [[-5, -200], [5, 40]], fill: STAFF }, { shape: "circle", pts: [[0, -210]], r: 10, fill: TIP }] }] });
  const ops = record({ ...BASE, props: [{ kind: "staff", hand: "right" }] });
  const staff = ops.findIndex((x) => x.op === "fill" && x.style === STAFF);
  const head = ops.findIndex((x) => x.op === "fill" && x.style === "#ffffff"); // the head's white fill
  assert.ok(head >= 0 && staff > head, "the prop is drawn after the head");
  const tip = (o) => mean(fills(record({ ...BASE, ...o }), TIP)[0].pts);
  const up = tip({ props: [{ kind: "staff", hand: "right" }] });
  const right = tip({ props: [{ kind: "staff", hand: "right", angle: 75 }] }); // half past two
  const left = tip({ props: [{ kind: "staff", hand: "left", angle: 75 }] });
  assert.ok(right[0] > up[0] + 100 && right[1] > up[1], "right hand: tips out to the right and down");
  const leftUp = tip({ props: [{ kind: "staff", hand: "left" }] });
  assert.ok(left[0] < leftUp[0] - 100, "left hand: mirrored, out to the left");
  setLibrary({ props: [{ id: "staff", name: "Staff", angle: 75, shapes: [
    { shape: "rect", pts: [[-5, -200], [5, 40]], fill: STAFF }, { shape: "circle", pts: [[0, -210]], r: 10, fill: TIP }] }] });
  assert.deepEqual(tip({ props: [{ kind: "staff", hand: "right" }] }), right, "the prop's own angle; a cast angle overrides it");
  assert.deepEqual(tip({ props: [{ kind: "staff", hand: "right", angle: 0 }] }), up);
  setLibrary({ props: [{ id: "staff", name: "Staff", grip: [0, -100], shapes: [
    { shape: "rect", pts: [[-5, -200], [5, 40]], fill: STAFF }, { shape: "circle", pts: [[0, -210]], r: 10, fill: TIP }] }] });
  const gripped = tip({ props: [{ kind: "staff", hand: "right" }] });
  assert.ok(Math.abs(gripped[1] - (up[1] + 100)) < 25, "held 100 px further up the staff: the tip sits 100 px lower");
  setLibrary({ props: [] });
});
