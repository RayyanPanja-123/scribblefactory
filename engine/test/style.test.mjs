// The art style config (page/style.js) and the pure parts of the style code: set outlines (world.js hullGeometry).
import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import { STYLE } from "../page/style.js";
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
