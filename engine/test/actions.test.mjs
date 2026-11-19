// Step 5c-6 actions: timing / gait / prop rules (page/actions.js is pure, imported directly), carried feet clear of
// the ground (stickman skeleton), and one batch render: every new action, frames identical across two renders.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { after, before, test } from "node:test";
import { CARRIED_LIFT, COLLAPSE_S, GIVE, PEDAL_HZ, STRIDE, collapseAt, eatAt, gaitPhase, giveAt, heldPlace, propsByShot,
  sideToward, staggerAt, withProp, zzzAt } from "../page/actions.js";
import { CH, FEET_Y, skeleton } from "../page/stickman.js";
import { fixturePart, frames, jobOk, png, renderNamed } from "./batch.mjs";

const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });

test("every action timing is deterministic: same inputs, same output", () => {
  for (const ph of [0, 0.37, 1.9, 7.25]) assert.deepEqual(staggerAt("s:fred:s04", ph), staggerAt("s:fred:s04", ph));
  for (const t of [0, 0.3, 0.61, 2.4]) {
    assert.deepEqual(collapseAt(t), collapseAt(t));
    assert.deepEqual(eatAt(t), eatAt(t));
    assert.equal(zzzAt("s:fred", t), zzzAt("s:fred", t));
  }
  for (const u of [0, 0.25, 0.5, 0.9]) assert.deepEqual(giveAt(u), giveAt(u));
  assert.notDeepEqual(staggerAt("s:fred:s04", 0.37), staggerAt("s:amy:s04", 0.37)); // seeded per character / shot
});

test("no gliding: walking gaits step only with distance travelled, at their stride", () => {
  for (const a of ["walk", "stagger", "carry", "support", "supported"]) {
    for (const ts of [0, 1, 5]) assert.equal(gaitPhase(a, 0, ts), 0, `${a} steps without moving`);
    assert.equal(gaitPhase(a, 2 * STRIDE[a], 3), 2);
    assert.ok(gaitPhase(a, 0.5, 0) < gaitPhase(a, 1, 0));
  }
});

test("stagger: sway stays within -1..1, knees buckle on some steps, never on all", () => {
  let buckled = 0, steps = 0;
  for (let k = 0; k < 400; k++) {
    const ph = k * 0.05, s = staggerAt("s:fred:s01", ph);
    assert.ok(s.sway >= -1 && s.sway <= 1 && s.buckle >= 0 && s.buckle <= 1);
    if (k % 10 === 5) { steps++; if (s.buckle > 0) buckled++; } // mid-step samples
  }
  assert.ok(buckled > 0 && buckled < steps, `${buckled} of ${steps} steps buckle`);
});

test("carried: legs pedal at 1.5 Hz in the air, feet never touch the ground", () => {
  assert.equal(gaitPhase("carried", 0, 2), 2 * PEDAL_HZ); // time-driven, no ground contact
  assert.ok(CARRIED_LIFT > 0);
  const worldPerPx = 1.6 / CH; // card height 1.6 world units over the canvas height
  for (let k = 0; k <= 60; k++) {
    const sk = skeleton({ action: "carried", phase: k / 20 });
    for (const [, foot] of sk.legs) {
      const footY = CARRIED_LIFT + (FEET_Y - foot[1]) * worldPerPx;
      assert.ok(footY >= CARRIED_LIFT - 1e-9 && footY > 0.1, `foot at ${footY} (phase ${k / 20})`);
    }
  }
});

test("carried dead: legs stay still instead of pedalling", () => {
  const poses = [0, 0.17, 0.41, 0.83].map((phase) => skeleton({ action: "carried", expression: "dead", phase }));
  for (const pose of poses.slice(1)) {
    assert.deepEqual(pose.legs, poses[0].legs);
    assert.deepEqual(pose.knees, poses[0].knees);
  }
});

test("collapse: buckles first, falls over 0.6 s, then lies", () => {
  assert.deepEqual(collapseAt(0), { buckle: 0, fall: 0 });
  let prev = -1;
  for (let t = 0; t <= COLLAPSE_S + 0.2; t += 0.05) {
    const c = collapseAt(t);
    assert.ok(c.fall >= prev);
    prev = c.fall;
  }
  assert.equal(collapseAt(COLLAPSE_S).fall, 1);
  assert.ok(collapseAt(0.15).buckle > 0 && collapseAt(0.15).fall === 0); // knees go before the body falls
});

test("eat: the hand comes to the mouth on a loop and the mouth chews there", () => {
  const ks = Array.from({ length: 60 }, (_, i) => eatAt(i * 0.1));
  assert.ok(ks.some((e) => e.k === 1) && ks.some((e) => e.k === 0));
  assert.ok(ks.some((e) => e.k > 0.8 && e.chew > 0.5));
  const [e1, e2] = [eatAt(0.7), eatAt(0.7 + 2.6)]; // loops (to float precision)
  assert.ok(Math.abs(e1.k - e2.k) < 1e-9 && Math.abs(e1.chew - e2.chew) < 1e-9);
});

test("give: the prop changes hands at mid-shot", () => {
  assert.equal(giveAt(GIVE.swap - 0.001).held, "giver");
  assert.equal(giveAt(GIVE.swap).held, "target");
  assert.equal(giveAt(0).reach, 0);
  assert.equal(giveAt(GIVE.swap).reach, 1);
});

test("prop ownership follows a give for later shots on the same set, resets on a set change", () => {
  const cast = { amy: [{ kind: "medal", hand: "right" }], tom: [{ kind: "apple", hand: "right" }] };
  const shots = [
    { id: "s01", set: "stadium", actors: [{ cast_id: "amy", action: "give", target: "tom", prop: "medal" }] },
    { id: "s02", set: "stadium", actors: [] },
    { id: "s03", set: "office", actors: [] },
  ];
  const m = propsByShot(shots, cast);
  assert.deepEqual(m.get("s01"), cast);                                               // at the start of the give
  assert.deepEqual(m.get("s02"), { amy: [], tom: [{ kind: "apple", hand: "right" }, { kind: "medal", hand: "left" }] });
  assert.deepEqual(m.get("s03"), cast);                                               // new set: cast props again
  assert.deepEqual(withProp([{ kind: "apple", hand: "right" }], "medal", "right"), [{ kind: "medal", hand: "right" }]);
});

test("held actors move with their holders; arms point the right way for either facing", () => {
  const at = (a, u) => [a.start_pos[0] + ((a.end_pos || a.start_pos)[0] - a.start_pos[0]) * u, a.start_pos[1]];
  const actors = [
    { cast_id: "fred", action: "carried", start_pos: [0, 0] },
    { cast_id: "amy", action: "carry", target: "fred", start_pos: [-0.42, 0], end_pos: [0.98, 0] },
    { cast_id: "tom", action: "carry", target: "fred", start_pos: [0.42, 0], end_pos: [1.82, 0] },
  ];
  const [x, z] = heldPlace(actors[0], actors, at, 0.5);
  assert.ok(Math.abs(x - 0.7) < 1e-9 && z < 0);
  assert.equal(heldPlace({ cast_id: "x", action: "carried", start_pos: [0, 0] }, [], at, 0.5), null);
  assert.equal(sideToward(0, 1, "right"), 1);
  assert.equal(sideToward(0, 1, "left"), -1); // mirrored card: the world-right arm is the canvas-left arm
  assert.equal(sideToward(0, -1, "camera"), -1);
});

// --- one batch render: all new actions in a 3-shot story, rendered twice ---
const SERIES = {
  slug: "act-test", title: "Act", created_at: "2026-11-16T10:00:00Z", voice: { voice_name: "x" }, style: { preset: "default" },
  cast: ["bob", "amy", "cat"].map((id, i) => ({ id, name: id, top: { color: ["#c0392b", "#3a7bd5", "#22aa55"][i] }, eyes: "dots",
    expression: "neutral" })),
};
const actor = (cast_id, action, x, extra = {}) => ({ cast_id, action, start_pos: [x, 0], facing: "camera", expression: "neutral", ...extra });
let R, part;
before(async () => {
  part = fixturePart(temps, (s) => {
    s.shots[0].actors = [actor("bob", "stagger", -0.8, { end_pos: [0.4, 0], facing: "right" }),
      actor("amy", "eat", 0.6, { prop: "apple" }), actor("cat", "lie", 1.6, { expression: "sleepy", facing: "left" })];
    s.shots[1].actors = [actor("bob", "collapse", -0.6), actor("amy", "give", 0.4, { target: "cat", prop: "medal", facing: "right" }),
      actor("cat", "receive", 1.2, { target: "amy", facing: "left" })];
    s.shots[2].set = "dirt_road";
    s.shots[2].actors = [actor("bob", "carried", 0), actor("amy", "carry", -0.42, { target: "bob", end_pos: [0.98, 0], facing: "right" }),
      actor("cat", "carry", 0.42, { target: "bob", end_pos: [1.82, 0], facing: "right" })];
    s.shots[2].vehicles = [{ id: "car1", kind: "car", action: "broken", start_pos: [-2.6, -0.6], facing: "right", riders: [], variant: "red" }];
    return s;
  }, SERIES);
  R = await renderNamed({ a: frames(part, "30-30", "a"), b: frames(part, "30-30", "b"),
    a2: frames(part, "75-75", "a"), b2: frames(part, "75-75", "b"), a3: frames(part, "150-150", "a"), b3: frames(part, "150-150", "b") });
});

test("every new action renders, and the same frame renders to the same bytes", () => {
  for (const n of ["a", "b", "a2", "b2", "a3", "b3"]) jobOk(R, n);
  for (const f of [30, 75, 150]) {
    const a = png(path.join(part, "a"), f), b = png(path.join(part, "b"), f);
    assert.ok(a.length > 10000);
    assert.ok(a.equals(b), `frame ${f} differs between renders`);
  }
  assert.match(R.a3.out, /car1 broken/);
});

test("propsByShot: a new @look brings its props, a set change goes back to the cast props", () => {
  const sh = (id, set, look) => ({ id, set, actors: [{ cast_id: "bob", action: "idle", look }] });
  const cast = { bob: [{ kind: "apple", hand: "right" }] };
  const lookProps = (id, look) => (look === "medic" ? [{ kind: "syringe", hand: "right" }] : cast[id]);
  const m = propsByShot([sh("s1", "room"), sh("s2", "room", "medic"), sh("s3", "room", "medic"), sh("s4", "street")], cast, lookProps);
  assert.deepEqual(["s1", "s2", "s3", "s4"].map((s) => m.get(s).bob[0].kind), ["apple", "syringe", "syringe", "apple"]);
});
