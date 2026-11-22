// Creatures: rig poses (pure) and every built-in drawn in every action through a recording 2D context.
import assert from "node:assert/strict";
import { test } from "node:test";
import { BUILTIN as ALL_BUILTIN, JOINT_OF, RIGS, creature, creaturePose, drawCreature, measure } from "../page/creatures.js";
import { find, lookup, setLibrary } from "../page/library.js";
import { FEET_Y, FIGURE_PX, drawStickman, figurePx, fitOf, hipPx } from "../page/stickman.js";

const BUILTIN = ALL_BUILTIN.filter((c) => c.rig !== "humanoid"); // humanoids are stickmen, not shape drawings

const grad = () => ({ addColorStop() {} });
function record(def, o, draw = (cv, opts) => drawCreature(cv, def, opts)) {
  const ops = [];
  let pts = [];
  const g = {
    setTransform() {}, clearRect() {}, fillRect() {}, createLinearGradient: grad, createRadialGradient: grad, translate() {}, rotate() {}, scale() {}, save() {}, restore() {}, clip() {}, closePath() {},
    beginPath() { pts = []; }, moveTo(x, y) { pts.push([x, y]); }, lineTo(x, y) { pts.push([x, y]); },
    arc(x, y) { pts.push([x, y]); }, bezierCurveTo(a, b, c, d, x, y) { pts.push([x, y]); }, quadraticCurveTo(a, b, x, y) { pts.push([x, y]); },
    fill() { ops.push({ op: "fill", style: this.fillStyle, pts }); },
    stroke() { ops.push({ op: "stroke", style: this.strokeStyle, pts }); },
  };
  draw({ getContext: () => g }, { seed: "t:c", boil: 0, t: 0.3, top: { color: "#123456" }, ...o });
  return ops;
}

test("library registry: custom items by kind; an unknown id throws, never a silent stand-in", () => {
  setLibrary({ creatures: [{ id: "dog", name: "Dog", rig: "quadruped" }], sets: [{ id: "bakery", kind: "indoor" }] });
  assert.equal(creature("dog").name, "Dog");
  assert.equal(creature("human").rig, "humanoid"); // built in: never needs the library
  assert.equal(find("sets", "bakery").kind, "indoor");
  setLibrary({ props: [] }); // a kind left out keeps its items
  assert.equal(creature("dog").name, "Dog");
  for (const [kind, call] of [["creature", () => creature("nope")], ["set", () => lookup("sets", "nope")],
    ["prop", () => lookup("props", "nope")], ["action", () => lookup("actions", "nope")]])
    assert.throws(call, new RegExp(`unknown ${kind} "nope"`));
  setLibrary({ creatures: [], sets: [] });
});

test("humanoid: human is the built-in default build; a build sets proportions and head colour and fits the card", () => {
  const human = ALL_BUILTIN.find((c) => c.id === "human");
  assert.equal(human.rig, "humanoid");
  assert.equal(figurePx(human.build), FIGURE_PX);
  assert.equal(fitOf({}), 1);
  const big = { head: 1.3, body_w: 1.3, body_h: 1.3, leg: 1.3, arm: 1.3 }, small = { head: 0.7, body_h: 0.7, leg: 0.7 };
  assert.ok(fitOf(big) < 1 && figurePx(big) <= FEET_Y - 8, "the biggest build is shrunk to fit the card");
  assert.ok(figurePx(big) > FIGURE_PX && figurePx(small) < FIGURE_PX);
  assert.ok(hipPx({ leg: 0.7 }) > hipPx({}), "short legs: the hip is lower on the card");
  const draw = (build) => record(null, { action: "idle", eyes: "dots", expression: "neutral", build }, drawStickman);
  assert.ok(draw({ head_color: "#d9a066" }).some((x) => x.op === "fill" && x.style === "#d9a066"), "head in head_color");
  assert.ok(draw({}).some((x) => x.op === "fill" && x.style === "#ffffff"), "default head white");
});
const ACTIONS = ["idle", "talk", "walk", "run", "point", "react", "wave", "stagger", "lie", "collapse", "eat", "give",
  "receive", "carry", "support", "supported", "carried", "cheer", "angry", "gasp", "ride"];

test("every built-in fits its rig: required parts, a joint for every part", () => {
  for (const c of BUILTIN) {
    const rig = RIGS[c.rig];
    for (const [part, need] of Object.entries(rig.parts)) if (need) assert.ok(c.parts[part], `${c.id}: no ${part}`);
    for (const part of Object.keys(c.parts)) {
      assert.ok(part in rig.parts, `${c.id}: ${part} is not a ${c.rig} part`);
      if (part !== "body") assert.ok(c.joints[JOINT_OF[part]], `${c.id}: no ${JOINT_OF[part]} joint for ${part}`);
    }
  }
});

test("every built-in draws in every action, headless or not, in the cast colour, feet on the ground", () => {
  for (const c of BUILTIN) for (const action of ACTIONS) for (const headless of [false, true]) {
    const ops = record(c, { action, headless, phase: 0.3, mouth: action === "talk" ? 0.8 : 0, buckle: 0.5,
      props: c.rig === "biped" ? [{ kind: "apple", hand: "right" }] : [] });
    assert.ok(ops.some((x) => x.op === "fill" && x.style === "#123456"), `${c.id} ${action}: no $main fill`);
    for (const x of ops) for (const [px, py] of x.pts) assert.ok(Number.isFinite(px) && Number.isFinite(py), `${c.id} ${action}`);
  }
  // standing at rest: the lowest point of a legged creature touches the ground
  for (const c of BUILTIN.filter((c) => c.rig !== "crawler")) {
    const low = Math.max(...record(c, { action: "idle" }).flatMap((x) => x.pts.map(([, y]) => y)));
    assert.ok(Math.abs(low - FEET_Y) < 16, `${c.id}: lowest point ${low}, ground ${FEET_Y}`);
  }
});

test("rig poses: legs follow the gait phase only; startled birds flap; only bipeds use arms; non-bipeds sit to lie", () => {
  const walk = (rig, phase, t) => creaturePose(rig, { action: "walk", phase, t }, 120).legs;
  for (const rig of Object.keys(RIGS)) assert.deepEqual(walk(rig, 0.3, 0.1), walk(rig, 0.3, 2.9));
  assert.notDeepEqual(walk("quadruped", 0.3, 0), walk("quadruped", 0.4, 0));
  assert.ok(creaturePose("bird", { action: "react", t: 0.06 }).wing < -30);
  assert.equal(creaturePose("bird", { action: "idle", t: 0.06 }).wing, 0);
  assert.ok(creaturePose("biped", { action: "wave", t: 0 }).arms[0] < -120);
  assert.equal(creaturePose("bird", { action: "lie" }).sit, 1);
  assert.equal(creaturePose("biped", { action: "lie" }).sit, 0);
  assert.ok(creaturePose("crawler", { action: "walk", phase: 0.2 }).ripple > 0);
});

test("measure: height from the drawing, the horse much taller than the cat", () => {
  const by = Object.fromEntries(BUILTIN.map((c) => [c.id, measure(c)]));
  assert.ok(by.horse.top > 3 * by.cat.top && by.cat.top > 150);
  assert.equal(by.chicken.leg, 120);
});
