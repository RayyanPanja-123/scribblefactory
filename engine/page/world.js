// Set presets built from primitives: MeshToonMaterial with a 3-step gradient, seeded canvas-painted textures,
// inverted-hull ink outlines on props. Stage: actors stand on z = 0, x in -2..2; back wall at z = -2.6.
// Stage clearance (enforced in Builder.add): a prop that reaches into |x| < STAGE.x must sit behind z STAGE.behind,
// and no prop may come forward of z STAGE.front, so nothing stands on or in front of the actors.
import * as THREE from "three";
import { rng } from "./rng.js";

export const SETS = ["room", "office", "street"];
const INK = 0x1c1a1a;
const HULL_T = 0.025; // outline thickness in world units
const HULL = new THREE.MeshBasicMaterial({ color: INK, side: THREE.BackSide });
const STAGE = { x: 2.2, behind: -1.0, front: 0.6 };

const GRADIENT = (() => {
  const t = new THREE.DataTexture(new Uint8Array([95, 175, 255]), 3, 1, THREE.RedFormat);
  t.minFilter = t.magFilter = THREE.NearestFilter;
  t.generateMipmaps = false;
  t.needsUpdate = true;
  return t;
})();

/** marker-painted texture: flat base + seeded strokes (strength scales their contrast); pattern adds planks... */
function paint(seed, key, base, pattern = null, strength = 1, size = 256) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d"), R = rng(seed, "paint", key), col = new THREE.Color(base);
  g.fillStyle = col.getStyle(); g.fillRect(0, 0, size, size);
  for (let i = 0; i < 60; i++) {
    const k = 1 + (R() * 0.2 - 0.1) * strength;
    g.strokeStyle = new THREE.Color(col.r * k, col.g * k, col.b * k).getStyle();
    g.globalAlpha = Math.min(0.7, 0.35 * strength); g.lineWidth = 6 + R() * 10; g.lineCap = "round";
    const x = R() * size, y = R() * size, a = R() * Math.PI;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * 40, y + Math.sin(a) * 40); g.stroke();
  }
  g.globalAlpha = 1;
  if (pattern) pattern(g, size, R);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

const lines = (dir, n, col, w) => (g, s) => {
  g.strokeStyle = col; g.lineWidth = w;
  for (let i = 0; i <= n; i++) {
    const v = (i * s) / n;
    g.beginPath();
    if (dir === "h") { g.moveTo(0, v); g.lineTo(s, v); } else { g.moveTo(v, 0); g.lineTo(v, s); }
    g.stroke();
  }
};
/** poster: coloured sheet with one bold seeded shape and a caption bar */
const poster = (ink) => (g, s, R) => {
  g.fillStyle = ink; g.strokeStyle = "#1c1a1a"; g.lineWidth = 8;
  const x = s * (0.3 + R() * 0.4), y = s * (0.3 + R() * 0.3), r = s * (0.15 + R() * 0.1);
  g.beginPath();
  if (R() < 0.5) g.arc(x, y, r, 0, Math.PI * 2); else g.rect(x - r, y - r, 2 * r, 2 * r);
  g.fill(); g.stroke();
  g.fillRect(s * 0.2, s * 0.8, s * 0.6, s * 0.06);
};
const windows = (g, s, R) => {
  for (let y = 0; y < 4; y++) for (let x = 0; x < 3; x++) {
    g.fillStyle = R() < 0.3 ? "#ffe9a8" : "#7fb4d8";
    g.fillRect(24 + x * 76, 20 + y * 60, 50, 38);
    g.strokeStyle = "#1c1a1a"; g.lineWidth = 4; g.strokeRect(24 + x * 76, 20 + y * 60, 50, 38);
  }
};

class Builder {
  constructor(group, seed, strength = 1) { this.group = group; this.seed = seed; this.n = 0; this.strength = strength; }
  mat(color, pattern = null, repeat = [1, 1]) {
    const map = paint(this.seed, this.n++, color, pattern, this.strength);
    map.repeat.set(...repeat);
    return new THREE.MeshToonMaterial({ map, gradientMap: GRADIENT });
  }
  /** centred primitive at pos; outline = inverted hull grown by HULL_T on every side; floor = exempt from clearance */
  add(geo, mat, pos, { outline = true, rot = null, floor = false } = {}) {
    const m = new THREE.Mesh(geo, mat);
    m.position.set(...pos);
    if (rot) m.rotation.set(...rot);
    if (!floor) {
      m.updateMatrixWorld();
      const b = new THREE.Box3().setFromObject(m);
      const onStageX = b.max.x > -STAGE.x && b.min.x < STAGE.x;
      if ((onStageX && b.max.z > STAGE.behind) || b.max.z > STAGE.front) {
        throw new Error(`set prop at [${pos}] breaks stage clearance (|x| < ${STAGE.x} needs z < ${STAGE.behind}, `
          + `nothing in front of z ${STAGE.front})`);
      }
    }
    this.group.add(m);
    if (outline) {
      geo.computeBoundingBox();
      const s = geo.boundingBox.getSize(new THREE.Vector3());
      const h = new THREE.Mesh(geo, HULL);
      h.position.copy(m.position); h.rotation.copy(m.rotation);
      h.scale.set(...[s.x, s.y, s.z].map((v) => (v > 1e-6 ? (v + 2 * HULL_T) / v : 1)));
      this.group.add(h);
    }
    return m;
  }
  box(w, h, d, color, pos, opts = {}) { return this.add(new THREE.BoxGeometry(w, h, d), opts.mat || this.mat(color, opts.pattern, opts.repeat), pos, opts); }
  cyl(r0, r1, h, color, pos, opts = {}) { return this.add(new THREE.CylinderGeometry(r0, r1, h, 20), opts.mat || this.mat(color, opts.pattern), pos, opts); }
  ball(r, color, pos, opts = {}) { return this.add(new THREE.SphereGeometry(r, 20, 14), opts.mat || this.mat(color), pos, opts); }
}

function room(b) {
  b.box(14, 0.1, 12, "#c8935a", [0, -0.05, 2.5], { outline: false, floor: true, pattern: lines("v", 8, "#8a5a32", 3), repeat: [4, 3] });
  b.box(14, 6, 0.2, "#f2d6a2", [0, 3, -2.7], { outline: false, pattern: lines("v", 6, "#e6c48a", 8), repeat: [5, 2] });
  b.cyl(1.6, 1.6, 0.02, "#d9534f", [0, 0.01, 0.2], { outline: false, floor: true }); // rug
  // sofa
  b.box(2.4, 0.45, 0.9, "#5b8bd9", [-1.4, 0.22, -1.9]);
  b.box(2.4, 0.7, 0.25, "#4a76c0", [-1.4, 0.8, -2.3]);
  for (const x of [-2.65, -0.15]) b.box(0.25, 0.65, 0.9, "#4a76c0", [x, 0.33, -1.9]);
  // window, picture, lamp
  b.box(1.4, 1.2, 0.08, "#ffffff", [1.6, 2.2, -2.55]);
  b.box(1.2, 1.0, 0.04, "#9fd3f5", [1.6, 2.2, -2.5], { outline: false });
  b.box(0.8, 0.6, 0.05, "#e8a33d", [-1.4, 2.3, -2.55]);
  b.cyl(0.04, 0.04, 1.6, "#333333", [2.7, 0.8, -1.7]);
  b.cyl(0.18, 0.35, 0.4, "#fff3b0", [2.7, 1.75, -1.7]);
}

function office(b) {
  // warm wall, teal carpet, coloured props at street-set saturation; everything across the stage sits behind z -1
  b.box(14, 0.1, 12, "#4fa39b", [0, -0.05, 2.5], { outline: false, floor: true, pattern: lines("h", 8, "#3f8a83", 3), repeat: [5, 4] });
  b.box(14, 6, 0.2, "#f2bd85", [0, 3, -2.7], { outline: false, pattern: lines("h", 4, "#e3a66a", 10), repeat: [4, 2] });
  b.box(2.4, 1.0, 0.06, "#9fd3f5", [0, 2.4, -2.58], { pattern: lines("h", 10, "#6fa8d0", 5) }); // window blinds
  b.box(0.7, 0.95, 0.04, "#e76f51", [-2.0, 2.3, -2.58], { pattern: poster("#e9c46a") });
  b.box(0.7, 0.95, 0.04, "#2a9d8f", [2.0, 2.3, -2.58], { pattern: poster("#f4a261") });
  const chairs = ["#e63946", "#457b9d"], mugs = ["#ffb703", "#8338ec"];
  [-1.8, 1.8].forEach((x, i) => {
    b.box(1.6, 0.08, 0.8, "#d99a4e", [x, 0.75, -2.05]);                                   // desk top
    for (const dx of [-0.72, 0.72]) b.box(0.08, 0.72, 0.7, "#8a5a32", [x + dx, 0.36, -2.05]);
    b.box(0.62, 0.42, 0.05, "#2d3440", [x, 1.07, -2.3]);                                 // monitor
    b.box(0.52, 0.32, 0.02, "#7ec8e3", [x, 1.07, -2.27], { outline: false });            // screen
    b.box(0.1, 0.12, 0.05, "#2d3440", [x, 0.85, -2.3], { outline: false });
    b.cyl(0.06, 0.06, 0.12, mugs[i], [x + 0.55, 0.85, -1.85]);                           // mug
    b.box(0.5, 0.08, 0.5, chairs[i], [x + 0.2, 0.48, -1.4]);                             // chair seat
    b.box(0.5, 0.6, 0.08, chairs[i], [x + 0.2, 0.8, -1.17]);                             // chair back, facing camera
    b.cyl(0.04, 0.04, 0.44, "#2d3440", [x + 0.2, 0.22, -1.4]);
  });
  b.cyl(0.25, 0.25, 0.9, "#f4f4f4", [3.0, 0.45, -2.1]);                                  // water cooler
  b.cyl(0.18, 0.2, 0.45, "#7fc4ef", [3.0, 1.12, -2.1]);
  b.cyl(0.25, 0.2, 0.4, "#c8553d", [-3.0, 0.2, -2.1]);                                   // plant
  b.ball(0.45, "#43aa8b", [-3.0, 0.75, -2.1]);
  b.cyl(0.2, 0.16, 0.35, "#e9c46a", [0.0, 0.18, -2.3]);                                  // small plant by the wall
  b.ball(0.3, "#2a9d8f", [0.0, 0.6, -2.3]);
}

function street(b, R) {
  b.box(14, 0.1, 5.5, "#c9c3b8", [0, -0.05, -1.0], { outline: false, floor: true, pattern: lines("v", 6, "#a9a397", 3), repeat: [6, 2] });
  b.box(14, 0.08, 9.4, "#5a5a60", [0, -0.08, 6.4], { outline: false, floor: true, pattern: lines("h", 1, "#f2f2f2", 6), repeat: [3, 2] });
  const palette = ["#e07a5f", "#f2cc8f", "#81b29a", "#c97b84", "#7aa6c2", "#e9c46a"];
  let x = -6;
  while (x < 6) {
    const w = 2.2 + R() * 1.2, h = 5 + R() * 3;
    b.box(w, h, 2, palette[Math.floor(R() * palette.length)], [x + w / 2, h / 2, -4.2], { pattern: windows, repeat: [Math.round(w), Math.round(h / 2)] });
    x += w + 0.05;
  }
  b.cyl(0.05, 0.06, 3.2, "#2f3a40", [2.3, 1.6, -1.6]);
  b.ball(0.2, "#fff3b0", [2.3, 3.25, -1.6]);
  b.cyl(0.1, 0.13, 1.4, "#7b5132", [-2.6, 0.7, -2.0]);
  b.ball(0.8, "#4caf50", [-2.6, 1.9, -2.0]);
  b.cyl(0.12, 0.14, 0.45, "#d62828", [3.3, 0.22, -1.2]); // off to the side: behind an actor it reads as a backpack
  b.ball(0.12, "#d62828", [3.3, 0.48, -1.2]);
}

const BACKGROUND = { room: "#f2d6a2", office: "#f2bd85", street: "#9fd3f5" };

/** build one set into a new group; unknown names fall back to "room" with a warning */
export function buildSet(name, seed) {
  if (!SETS.includes(name)) {
    console.warn(`unknown set "${name}", using "room"`);
    name = "room";
  }
  const group = new THREE.Group();
  const b = new Builder(group, `${seed}:${name}`, name === "office" ? 2.2 : 1); // office: visible paint
  ({ room, office, street })[name](b, rng(seed, "set", name));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.set(3, 6, 5);
  group.add(sun, new THREE.AmbientLight(0xffffff, 1.1));
  group.userData.background = new THREE.Color(BACKGROUND[name]);
  return group;
}
