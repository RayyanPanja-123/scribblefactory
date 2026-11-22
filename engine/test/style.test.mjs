// The art style config (page/style.js) and the pure parts of the style code: set outlines (world.js hullGeometry).
import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import { PRESETS, STYLE, usePreset } from "../page/style.js";

test("usePreset: applies a preset in place, resets to defaults, refuses unknown names", () => {
  const water = STYLE.water, ink = structuredClone(STYLE.ink);
  assert.equal(STYLE.grade, null);
  usePreset("cinematic");
  assert.deepEqual(STYLE.grade, PRESETS.cinematic.grade);
  assert.equal(STYLE.water, water, "sections are updated in place, so aliases stay live");
  assert.deepEqual(STYLE.ink, ink);
  usePreset();
  assert.equal(STYLE.grade, null);
  assert.throws(() => usePreset("nope"), /unknown style preset "nope"/);
});
import { hullGeometry } from "../page/world.js";

test("style.js: every section exists with sane defaults", () => {
  for (const k of ["rain", "ink", "shade"]) assert.ok(STYLE[k], k);
  assert.ok(STYLE.ink.width > 0 && STYLE.ink.lump >= 0 && STYLE.ink.lump < 1);
  assert.ok(STYLE.shade.top > STYLE.shade.side && STYLE.shade.side > STYLE.shade.under, "tops lightest, undersides darkest");
  assert.ok(STYLE.rain.back.alpha < STYLE.rain.front.alpha && STYLE.rain.back.width < STYLE.rain.front.width);
});

test("set outlines: subdivided hull, gap-free corner normals, deterministic", () => {
  const h = hullGeometry(new THREE.BoxGeometry(3, 1, 1));
  assert.ok(h.attributes.position.count > new THREE.BoxGeometry(3, 1, 1).attributes.position.count, "long edges subdivided");
  const pos = h.attributes.position, ink = h.attributes.inkNormal;
  for (let i = 0; i < pos.count; i++) {
    if (Math.abs(Math.abs(pos.getX(i)) - 1.5) < 1e-6 && Math.abs(Math.abs(pos.getY(i)) - 0.5) < 1e-6 && Math.abs(Math.abs(pos.getZ(i)) - 0.5) < 1e-6) {
      // a corner: the sum of its three face normals, the same on every duplicate of that corner
      assert.deepEqual([ink.getX(i), ink.getY(i), ink.getZ(i)], [Math.sign(pos.getX(i)), Math.sign(pos.getY(i)), Math.sign(pos.getZ(i))]);
    }
  }
  const s = hullGeometry(new THREE.SphereGeometry(1, 28, 12).scale(1, 0.3, 1)); // a mound: its own vertices
  assert.equal(s.attributes.position.count, new THREE.SphereGeometry(1, 28, 12).attributes.position.count);
  assert.deepEqual(hullGeometry(new THREE.CylinderGeometry(0.1, 0.2, 3, 20)).attributes.inkNormal.array,
    hullGeometry(new THREE.CylinderGeometry(0.1, 0.2, 3, 20)).attributes.inkNormal.array);
});

test("water: detected from a blue outdoor floor only; waterline footprints of pieces in it", async () => {
  const { isWater, waterline } = await import("../page/world.js");
  assert.equal(isWater({ kind: "outdoor", floor: "#add8e6" }), true);  // the Romans' beach sea
  assert.equal(isWater({ kind: "outdoor", floor: "#3a8fb7" }), true);
  assert.equal(isWater({ kind: "indoor", floor: "#add8e6" }), false);  // a blue carpet is not a sea
  for (const floor of ["#d6c6a2", "#8cc152", "#5a5a60", "#f2d8a0"]) assert.equal(isWater({ kind: "outdoor", floor }), false, floor);
  assert.ok(Math.abs(waterline({ shape: "mound", at: [0, 0, -25], size: [20, 0.5] }) - 20) < 1e-9);
  assert.ok(Math.abs(waterline({ shape: "mound", at: [0, -1, -25], size: [10, 0.5] }) - Math.sqrt(100 - 4)) < 1e-9);
  assert.equal(waterline({ shape: "box", at: [0, 0.5, -15], size: [30, 0.2, 3] }), null); // floats above the water
  assert.deepEqual(waterline({ shape: "box", at: [0, 0.4, -5], size: [6, 0.8, 2] }), [3, 1]);
  assert.equal(waterline({ shape: "cyl", at: [0, 1.5, -3], size: [0.1, 0.15, 3] }), 0.15);
});

test("lighting accent: warm tops and cool undersides outdoors, neutral indoors, shadows never black", async () => {
  const { toneColors } = await import("../page/world.js");
  const [top, , under] = toneColors(true), [itop, iside, iunder] = toneColors(false);
  assert.ok(top.r > top.b, "outdoor tops are warm"); assert.ok(under.b > under.r, "outdoor undersides are cool");
  for (const c of [itop, iside, iunder]) assert.ok(c.r === c.g && c.g === c.b, "indoor stays neutral");
  for (const c of [...toneColors(true), ...toneColors(false)]) assert.ok(Math.min(c.r, c.g, c.b) > 0.3, "never near black");
  const shadow = new THREE.Color(STYLE.light.shadow);
  assert.ok(shadow.getHSL({}, THREE.SRGBColorSpace).l > 0.1 && shadow.b > shadow.r, "contact shadows are a cool dark, not black");
});
