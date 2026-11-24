// World Items (items.js): the animation is a pure function of time, a set's water flag beats the colour guess, and
// card items render the same frame whether it is drawn alone, inside a chunk or after other frames (cache state never
// shows). Run: npm test (in engine/).
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { animAt } from "../page/items.js";
import { isWater } from "../page/world.js";
import { fixturePart, png, render, renderNamed } from "./batch.mjs";

const temps = [];
after(() => { for (const d of temps) fs.rmSync(d, { recursive: true, force: true }); });

const ANIMS = [{ kind: "bob", amp: 0.2, hz: 0.5 }, { kind: "rotate", amp: 30 }, { kind: "blink", amp: 0.5, hz: 1, when: ["on"] },
  { kind: "flow", hz: 0.05 }];

test("animAt: pure, bounded, state-gated", () => {
  assert.deepEqual(animAt(ANIMS, "on", 12.3, 0.4), animAt(ANIMS, "on", 12.3, 0.4)); // same input, same output
  for (const t of [0, 1.7, 450, 900.03]) { // 900 s: a 27k-frame part's end
    const a = animAt(ANIMS, "on", t, 1);
    assert.ok(Math.abs(a.dy) <= 0.2 + 1e-9 && a.opacity >= 0.5 - 1e-9 && a.opacity <= 1);
    assert.ok(a.rot >= 0 && a.rot < 2 * Math.PI && a.flow >= 0 && a.flow < 1);
  }
  assert.equal(animAt(ANIMS, "off", 3, 0).opacity, 1); // blink plays only "on"
  assert.deepEqual(animAt([], null, 5), { dx: 0, dy: 0, rot: 0, scale: 1, opacity: 1, flow: 0 });
});

test("isWater: the set's water flag wins over the blue-floor guess", () => {
  const sea = { kind: "outdoor", floor: "#3a8fb7" };
  assert.equal(isWater(sea), true);
  assert.equal(isWater({ ...sea, water: false }), false);
  assert.equal(isWater({ kind: "outdoor", floor: "#d98a5f", water: true }), true);
  assert.equal(isWater({ kind: "indoor", floor: "#3a8fb7", water: true }), false);
});

// a library with the two test items, a custom outdoor set holding a sky planet, and the fixture story: s01 on that
// set with the saucer flying across it, s02 (frames 60-119) on the plain office
const SAUCER = { id: "saucer", name: "Saucer", category: "scifi", capabilities: [], carry_mode: "none", pieces: [],
  look: "card", draw: "saucer", size: 1.6, layer: "back", states: ["flying", "landed"],
  anims: [{ kind: "bob", amp: 0.15, hz: 0.6, when: ["flying"] }] };
const PLANET = { id: "ringed-planet", name: "Ringed planet", category: "sky", capabilities: [], carry_mode: "none", pieces: [],
  look: "card", draw: "planet", size: 12, layer: "sky", anims: [{ kind: "flow", hz: 0.02 }, { kind: "drift", amp: 0.4, hz: 0.03 }] };
const ALIEN = { id: "alien-plains", name: "Alien plains", kind: "outdoor", floor: "#7a4fa3", back: "#2fb3a0", water: false,
  pieces: [], objects: [{ id: "world", object: "ringed-planet", at: [7, 12, -60], visible: true, accent: "#ff9f6e" }] };
const lib = fs.mkdtempSync(path.join(os.tmpdir(), "scribble-items-"));
temps.push(lib);
fs.cpSync(path.dirname(fixturePart(temps, (s) => {
  s.shots[0].set = "alien-plains";
  s.shots[0].items = [{ id: "ship", object: "saucer", layer: "back", start_pos: [6, -14], end_pos: [-6, -14], y: 3.4, facing: "left" }];
  s.shots[1].items = [{ id: "ship", object: "saucer", layer: "back", start_pos: [-2, -14], y: 3.4, state: "landed" }];
  return s;
})), path.join(lib, "demo"), { recursive: true });
fs.writeFileSync(path.join(lib, "sets.json"), JSON.stringify({ schema_version: 1, sets: [ALIEN] }));
fs.writeFileSync(path.join(lib, "objects.json"), JSON.stringify({ schema_version: 1, objects: [SAUCER, PLANET] }));
const part = path.join(lib, "demo", "part-01");
const dir = (name) => path.join(part, name);

test("card items: a frame is the same alone, inside a chunk and after other frames; the saucer moves", async () => {
  const R = await renderNamed({
    chunk: ["--part", part, "--frames", "20-23", "--out-dir", dir("chunk")],
    later: ["--part", part, "--frames", "50-52", "--out-dir", dir("later")], // other frames first: a warm cache
    again: ["--part", part, "--frames", "22-22", "--out-dir", dir("later")],
    landed: ["--part", part, "--frames", "70-70", "--out-dir", dir("chunk")],
  });
  for (const k of ["chunk", "later", "again", "landed"]) assert.ok(R[k].ok, `${k}: ${R[k].error}`);
  const alone = await render("--part", part, "--frames", "22-22", "--out-dir", dir("alone")); // its own browser
  assert.equal(alone.status, 0, alone.stderr);
  assert.ok(png(dir("chunk"), 22).equals(png(dir("alone"), 22)), "frame 22: chunk vs alone");
  assert.ok(png(dir("chunk"), 22).equals(png(dir("later"), 22)), "frame 22: chunk vs after frames 50-52");
  assert.ok(!png(dir("chunk"), 20).equals(png(dir("chunk"), 23)), "the saucer flies and the planet's bands flow");
});
