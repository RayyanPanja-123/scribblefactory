// Wardrobe: slot values, anchors across builds, draw order, colour override, built-ins drawn as before.
import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";
import { anchors, drawStickman, skeleton } from "../page/stickman.js";
import { setLibrary } from "../page/library.js";
import { BUILTIN_WARDROBE, layerPoints, slotValue, slotsOf, wearing } from "../page/wardrobe.js";

const SEED = JSON.parse(fs.readFileSync(new URL("../../pipeline/scribble/seed/wardrobe.json", import.meta.url), "utf8")).wardrobe;

/** fake canvas: records every fill / stroke with its style and path points */
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
const BASE = { seed: "t:ward", boil: 0, color: "#3a7bd5", eyes: "dots", expression: "neutral", action: "idle",
  phase: 0, lid: 0, mouth: 0, breath: 0, facing: "camera", t: 0, top: { style: "plain", color: "#3a7bd5" } };
const first = (ops, colour) => ops.findIndex((x) => x.op === "fill" && x.style === colour);
const item = (id, slot, layers, extra = {}) => ({ id, name: id, slot, layers, colorable: true, default_color: "#123456", ...extra });

test("slot values: plain id, {id, color}, legacy {kind} / {style}, null and none", () => {
  assert.deepEqual(slotValue("wild_hair"), { id: "wild_hair", color: null, accent: null });
  assert.deepEqual(slotValue({ id: "wild_hair", color: "#e8e8e8" }), { id: "wild_hair", color: "#e8e8e8", accent: null });
  assert.deepEqual(slotValue({ kind: "bowler", color: "#333333" }), { id: "bowler", color: "#333333", accent: null });
  assert.deepEqual(slotValue({ style: "suit", color: "#111111" }), { id: "suit", color: "#111111", accent: null });
  for (const none of [null, undefined, "none", { kind: "none" }, { id: "none" }]) assert.equal(slotValue(none), null);
  // list slots take up to 3, flattened in draw order (back to front)
  const s = slotsOf({ hair: "h", face: ["a", "b", "c", "d"], back: "cape", headwear: { kind: "bowler", color: "#000000" } });
  assert.deepEqual(s.map((x) => x.id), ["cape", "a", "b", "c", "h", "bowler"]);
});

test("built-in ids stay hand-drawn: { id } draws exactly like the original { kind } / { style }", () => {
  setLibrary({ wardrobe: [] });
  const legacy = record({ ...BASE, top: { style: "suit", color: "#1f3a68", accent_color: "#c0392b" },
    headwear: { kind: "bowler", color: "#333333" }, legwear: { kind: "trousers", color: "#222222" } });
  const byId = record({ ...BASE, top: { id: "suit", color: "#1f3a68", accent_color: "#c0392b" },
    headwear: { id: "bowler", color: "#333333" }, legwear: { id: "trousers", color: "#222222" } });
  assert.deepEqual(byId, legacy);
  assert.deepEqual(Object.keys(BUILTIN_WARDROBE).sort(), ["bowler", "dress", "flat_cap", "plain", "postman_cap",
    "ragged_shorts", "shirt", "shorts", "straw_hat", "suit", "tank", "trousers", "wide_hat"]);
});

test("a custom item only adds strokes: the rest of the figure draws as before", () => {
  setLibrary({ wardrobe: SEED });
  const plain = record(BASE), worn = record({ ...BASE, hair: "short_hair" });
  let i = 0; // plain's ops are a subsequence of worn's
  for (const op of worn) if (i < plain.length && JSON.stringify(op) === JSON.stringify(plain[i])) i++;
  assert.equal(i, plain.length);
  assert.ok(worn.length > plain.length);
});

test("draw order: behind layers under everything, legwear under the body, hair over the face, hats over hair", () => {
  const C = { cape: "#aa0001", legs: "#aa0002", hair: "#aa0003", hat: "#aa0004", beard: "#aa0005" };
  setLibrary({ wardrobe: [
    item("cape", "back", [{ shape: "rect", anchor: "neck", pts: [[-80, 0], [80, 300]], fill: "$color", behind: true }]),
    item("kilt", "legwear", [{ shape: "rect", anchor: "hips", pts: [[-60, -10], [60, 90]], fill: "$color" }]),
    item("mop", "hair", [{ shape: "circle", anchor: "head_top", pts: [[0, 20]], r: 60, fill: "$color" }]),
    item("beard", "facial_hair", [{ shape: "circle", anchor: "mouth", pts: [[0, 40]], r: 40, fill: "$color" }]),
    item("tall_hat", "headwear", [{ shape: "rect", anchor: "head_top", pts: [[-60, -80], [60, 30]], fill: "$color" }]),
  ] });
  const ops = record({ ...BASE, back: { id: "cape", color: C.cape }, legwear: { id: "kilt", color: C.legs },
    hair: { id: "mop", color: C.hair }, facial_hair: { id: "beard", color: C.beard }, headwear: { id: "tall_hat", color: C.hat } });
  const body = first(ops, "#3a7bd5"), head = first(ops, "#ffffff");
  const at = Object.fromEntries(Object.entries(C).map(([k, c]) => [k, first(ops, c)]));
  assert.ok(Object.values(at).every((i) => i >= 0));
  assert.ok(at.cape < at.legs && at.legs < body, "cape behind, legwear under the body");
  assert.ok(body < head && head < at.beard && at.beard < at.hair && at.hair < at.hat, "head, beard, hair, hat");
});

test("colour override: a colorable item takes the cast colour, else its default; $color only", () => {
  const it = item("cap", "headwear", [{ shape: "circle", anchor: "head_top", pts: [[0, 0]], r: 40, fill: "$color" },
    { shape: "circle", anchor: "head_top", pts: [[0, 0]], r: 10, fill: "#ffd54a" }]);
  setLibrary({ wardrobe: [it, { ...it, id: "fixed", colorable: false }] });
  assert.equal(wearing({ headwear: { id: "cap", color: "#ff0000" } })[0].color, "#ff0000");
  assert.equal(wearing({ headwear: "cap" })[0].color, "#123456");
  assert.equal(wearing({ headwear: { id: "fixed", color: "#ff0000" } })[0].color, "#123456");
  const ops = record({ ...BASE, headwear: { id: "cap", color: "#ff0000" } });
  assert.ok(first(ops, "#ff0000") >= 0 && first(ops, "#ffd54a") >= 0);
});

test("accent: $accent takes the cast accent (a top's accent_color too), else the item's default_accent", () => {
  const band = { shape: "rect", anchor: "head_top", pts: [[-40, 0], [40, 10]], fill: "$accent" };
  const cap = item("cap", "headwear", [band], { default_accent: "#654321" }), tee = item("tee", "top", [{ ...band, anchor: "chest" }]);
  setLibrary({ wardrobe: [cap, tee, { ...cap, id: "fixed", colorable: false }] });
  assert.equal(wearing({ headwear: { id: "cap", accent: "#00ff00" } })[0].accent, "#00ff00");
  assert.equal(wearing({ headwear: "cap" })[0].accent, "#654321");
  assert.equal(wearing({ headwear: { id: "fixed", accent: "#00ff00" } })[0].accent, "#654321");
  assert.equal(wearing({ top: { style: "tee", color: "#111111", accent_color: "#00ff00" } })[0].accent, "#00ff00");
  assert.equal(wearing({ top: { style: "tee", color: "#111111" } })[0].accent, "#3a2a1e"); // an item saved before accents
  assert.ok(first(record({ ...BASE, headwear: { id: "cap", accent: "#00ff00" } }), "#00ff00") >= 0);
});

test("unknown ids and items in the wrong slot throw", () => {
  setLibrary({ wardrobe: SEED });
  assert.throws(() => wearing({ hair: "mohawk" }), /unknown wardrobe "mohawk"/);
  assert.throws(() => wearing({ hair: "crown" }), /is a headwear, not hair/);
  assert.throws(() => wearing({ headwear: "suit" }), /is a top, not headwear/);
});

test("anchors scale with the build and follow the pose", () => {
  const L = { shape: "rect", anchor: "chest", pts: [[-50, -20], [50, 20]] };
  const width = (build) => { const k = skeleton({ action: "idle", build }), p = layerPoints(L, anchors(k).chest[0]); return p[1][0] - p[0][0]; };
  assert.equal(width({}), 100);
  assert.ok(Math.abs(width({ body_w: 1.3 }) - 130) < 1e-9);
  // feet: one frame per foot, at the foot, the left one mirrored
  for (const build of [{}, { leg: 1.3 }, { leg: 0.7, body_w: 1.2 }]) {
    const k = skeleton({ action: "walk", phase: 0.25, build }), A = anchors(k);
    A.feet.forEach((f, i) => assert.deepEqual(f.at, k.legs[i][1]));
    assert.deepEqual(A.feet.map((f) => f.m), [-1, 1]);
    // a point along the leg lands on the leg line, scaled with the leg length
    const [hip, foot] = k.legs[1], p = layerPoints({ shape: "line", anchor: "legs", pts: [[0, 0], [0, 220]] }, A.legs[1])[1];
    assert.ok(Math.hypot(p[0] - foot[0], p[1] - foot[1]) < 1e-6, `leg end at the foot (${JSON.stringify(build)})`);
    assert.ok(Math.hypot(hip[0] - A.legs[1].at[0], hip[1] - A.legs[1].at[1]) < 1e-9);
  }
  // head anchors sit in head space: the same for every head size (the head's own scale draws them bigger)
  const a = anchors(skeleton({ action: "idle", build: { head: 0.8 } })), b = anchors(skeleton({ action: "idle", build: { head: 1.3 } }));
  assert.equal(a.eyes[0].sx, 1); assert.equal(b.eyes[0].sx, 1);
  // the face turns: profile moves face anchors toward the way it looks
  const k = skeleton({ action: "idle" });
  assert.ok(anchors(k, 1).face[0].at[0] > anchors(k, 0).face[0].at[0]);
});

test("a layer with when shows only with those expressions (blush)", () => {
  setLibrary({ wardrobe: SEED });
  const pink = "#f2a3a3";
  assert.equal(first(record({ ...BASE, face: ["blush"], expression: "neutral" }), pink), -1);
  assert.ok(first(record({ ...BASE, face: ["blush"], expression: "happy" }), pink) >= 0);
});

test("every seed item draws on every build and pose", () => {
  setLibrary({ wardrobe: SEED });
  const POSES = [{ action: "idle" }, { action: "walk", phase: 0.3, facing: "right" }, { action: "run", phase: 0.7, facing: "left" },
    { action: "wave", wave: { k: 1, swing: 0.5 } }, { action: "react" }, { action: "talk", mouth: 0.8 }, { action: "lie" },
    { action: "cheer", mood: { k: 1, bounce: 0, shake: 0 } }];
  for (const w of SEED) for (const build of [{}, { head: 1.3, body_w: 0.7, leg: 1.3 }]) for (const pose of POSES) {
    const slot = w.slot === "top" ? { top: { id: w.id, color: "#3a7bd5" } } : { [w.slot]: w.slot === "face" || w.slot === "accessory" ? [w.id] : w.id };
    const ops = record({ ...BASE, ...pose, build, ...slot });
    assert.ok(ops.every((o) => o.pts.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y))), `${w.id} ${pose.action}`);
  }
});
