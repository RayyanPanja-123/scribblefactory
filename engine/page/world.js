// Set presets built from primitives: flat materials with a two-tone ramp from each surface's facing (tops light, sides
// and undersides darker; style.js shade), seeded canvas-painted textures, and inverted-hull ink outlines on props that
// keep a constant on-screen width and wobble and boil like the characters' lines (style.js ink). Stage: actors stand on z = 0, x in -2..2; back wall at z = -2.6.
// Stage clearance (enforced in Builder.add): a prop that reaches into |x| < STAGE.x must sit behind z STAGE.behind,
// and no prop may come forward of z STAGE.front, so nothing stands on or in front of the actors.
import * as THREE from "three";
import { cloudCanvas } from "./borrowed.js";
import { BOIL_FRAMES, itemCard, updateCard } from "./items.js";
import { lookup } from "./library.js";
import { rng } from "./rng.js";
import { INK, STYLE } from "./style.js";

export const SETS = ["room", "office", "street", "dirt_road", "countryside", "orchard", "stadium"];
/** prop-placement variants per set (main.js picks one per run of shots); sets not listed have one */
export const VARIANTS = { dirt_road: 3, countryside: 3, orchard: 3, stadium: 3 };
const STAGE = { x: 2.2, behind: -1.0, front: 0.6 };
const H_PX = 1920; // frame height: the outline width is set in screen px of the final frame

// shared uniforms of every set material and outline (one program each, updated per frame by setInk)
const D = STYLE.depth;
const U = {
  inkPx: { value: STYLE.ink.width }, inkLump: { value: STYLE.ink.lump }, inkBoil: { value: 0 }, inkH: { value: H_PX },
  shadeTop: { value: new THREE.Color() }, shadeSide: { value: new THREE.Color() }, shadeUnder: { value: new THREE.Color() },
  shadeKey: { value: new THREE.Vector3(...STYLE.shade.keyDir).normalize() }, shadeKeyMin: { value: STYLE.shade.keyMin },
  hazeColor: { value: new THREE.Color(0xffffff) }, haze: { value: new THREE.Vector3(D.near, D.far, D.max) },
};
/** per frame: the boil step (main.js: frame / BOIL_FRAMES; outlines re-wobble with the characters' lines) and the
 *  colour far scenery hazes toward (the set's background) */
export function setInk(boil, hazeColor, outdoor = false) {
  U.inkBoil.value = boil;
  if (hazeColor) U.hazeColor.value.copy(hazeColor);
  const [top, side, under] = toneColors(outdoor);
  U.shadeTop.value.copy(top); U.shadeSide.value.copy(side); U.shadeUnder.value.copy(under);
}
/** the shade ramp as colours [top, side, under]: grey multipliers, warmed (key) and cooled (shadow side) outdoors when
 *  style.js light.outdoor is on. Pure colour ramp, no light objects. */
export function toneColors(outdoor) {
  const S = STYLE.shade, L = STYLE.light, warm = outdoor && L.outdoor;
  const tint = (k, col, share) => new THREE.Color(k, k, k).multiply(warm ? new THREE.Color(1, 1, 1).lerp(new THREE.Color(col), share) : new THREE.Color(1, 1, 1));
  return [tint(S.top, L.key, 1), tint(S.side, L.key, L.sideWarm), tint(S.under, L.cool, 1)];
}
setInk(0);

// distance tint (atmospheric perspective): by depth behind the stage (-z), from haze.x (none) to haze.y (haze.z share)
const HAZE_V = ["varying vec3 vInkW;\n", "#include <begin_vertex>\n  vInkW = (modelMatrix * vec4(transformed, 1.0)).xyz;"];
const HAZE_F = ["varying vec3 vInkW;\nuniform vec3 hazeColor, haze;\n",
  "\n  diffuseColor.rgb = mix(diffuseColor.rgb, hazeColor, haze.z * smoothstep(haze.x, haze.y, -vInkW.z));"];

// outline: pushed out along inkNormal (the merged normal at a corner: no gaps) by inkPx screen px, its width lumped by
// three harmonics of world position (like stickman.js wobble), re-seeded every boil step; hazes with distance
function outlineShader(sh) {
  Object.assign(sh.uniforms, U);
  sh.vertexShader = "attribute vec3 inkNormal;\nuniform float inkPx, inkLump, inkBoil, inkH;\n" + HAZE_V[0] + sh.vertexShader
    .replace("#include <begin_vertex>", HAZE_V[1]).replace("#include <project_vertex>", `
    vec4 mvPosition = modelViewMatrix * vec4(transformed, 1.0);
    vec3 wp = vInkW;
    float b = inkBoil * 1.618;
    float lump = 1.0 + inkLump * (sin(dot(wp, vec3(2.9, 1.7, 2.3)) + b) + 0.6 * sin(dot(wp, vec3(-4.3, 3.1, 1.1)) + 2.0 * b)
      + 0.4 * sin(dot(wp, vec3(6.7, -5.3, 3.7)) + 3.0 * b)) / 2.0;
    vec4 clip = projectionMatrix * mvPosition;
    float unitsPerPx = 2.0 * clip.w / (projectionMatrix[1][1] * inkH);
    mvPosition.xyz += normalize(normalMatrix * inkNormal) * inkPx * unitsPerPx * max(0.2, lump);
    gl_Position = projectionMatrix * mvPosition;`);
  sh.fragmentShader = HAZE_F[0] + sh.fragmentShader.replace("#include <map_fragment>", "#include <map_fragment>" + HAZE_F[1]);
}
const HULL = new THREE.MeshBasicMaterial({ color: INK, side: THREE.BackSide });
HULL.onBeforeCompile = outlineShader;

// two-tone: the surface colour (texture included) times a tone from its world normal: up-facing tops light, faces
// toward the key direction mid, faces away and undersides dark. Pure colour ramp, no light objects. Then the distance
// tint. Material defines: INK_FLAT (floors, foam: no tone), INK_SKY (no tone, no haze: the sky keeps its gradient).
function shadeShader(sh) {
  Object.assign(sh.uniforms, U);
  sh.vertexShader = "varying vec3 vInkN;\n" + HAZE_V[0] + sh.vertexShader.replace("#include <begin_vertex>",
    HAZE_V[1] + "\n  vInkN = normalize(mat3(modelMatrix) * normal);");
  sh.fragmentShader = "varying vec3 vInkN;\nuniform float shadeKeyMin;\nuniform vec3 shadeKey, shadeTop, shadeSide, shadeUnder;\n"
    + HAZE_F[0] + sh.fragmentShader.replace("#include <map_fragment>", `#include <map_fragment>
  #if !defined(INK_FLAT) && !defined(INK_SKY)
    vec3 n = normalize(vInkN);
    vec3 tone = n.y > 0.55 ? shadeTop : n.y < -0.4 || dot(n, shadeKey) < shadeKeyMin ? shadeUnder : shadeSide;
    diffuseColor.rgb *= tone;
  #endif
  #ifndef INK_SKY${HAZE_F[1]}
  #endif`);
}
/** a set material: the painted map through the shade ramp; kind "flat" (floors) or "sky" picks a variant */
function setMaterial(map, kind = null) {
  const m = new THREE.MeshBasicMaterial({ map });
  m.onBeforeCompile = shadeShader;
  if (kind === "flat") m.defines = { INK_FLAT: "" };
  if (kind === "sky") m.defines = { INK_SKY: "" };
  return m;
}

/** outline geometry for a piece: subdivided so a long edge wobbles along its length, with inkNormal = the sum of the
 *  distinct normals meeting at each position (a box corner gets (1, 1, 1): each face moves out by the full width) */
export function hullGeometry(geo) {
  const P = geo.parameters, seg = (v) => Math.min(32, Math.max(1, Math.ceil(v / STYLE.ink.segment)));
  let g = geo;
  if (geo.type === "BoxGeometry") g = new THREE.BoxGeometry(P.width, P.height, P.depth, seg(P.width), seg(P.height), seg(P.depth));
  else if (geo.type === "CylinderGeometry") {
    g = new THREE.CylinderGeometry(P.radiusTop, P.radiusBottom, P.height, P.radialSegments, seg(P.height));
  }
  const pos = g.attributes.position, nor = g.attributes.normal, key = (i) => [0, 1, 2].map((k) => pos.array[i * 3 + k].toFixed(4)).join();
  const seen = new Map();
  for (let i = 0; i < pos.count; i++) {
    const k = key(i), n = [nor.getX(i), nor.getY(i), nor.getZ(i)], nk = n.map((v) => v.toFixed(2)).join();
    if (!seen.has(k)) seen.set(k, { sum: [0, 0, 0], dirs: new Set() });
    const e = seen.get(k);
    if (!e.dirs.has(nk)) { e.dirs.add(nk); n.forEach((v, j) => { e.sum[j] += v; }); }
  }
  const out = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) out.set(seen.get(key(i)).sum, i * 3);
  g.setAttribute("inkNormal", new THREE.BufferAttribute(out, 3));
  return g;
}

/** marker-painted texture: flat base + seeded strokes (strength scales their contrast); pattern adds planks... */
function paint(seed, key, base, pattern = null, strength = 1, size = 256, blotch = 1) {
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
  const B = STYLE.blotch, Q = rng(seed, "blotch", key); // own stream: patterns below keep their layouts
  // blotches go on a scratch layer, blurred once onto the tile (smooths the gradient dither a stretched texture shows
  // as a grid). A filter set while filling would blur every one of the 81 fills: ~25x slower in software GL.
  const L = Object.assign(document.createElement("canvas"), { width: size, height: size }), lg = L.getContext("2d");
  for (let i = 0; blotch > 0 && i < B.count; i++) { // blotch: alpha factor (floors: STYLE.blotch.floor, 0 = none) // soft tone drift, wrapped so the tile stays seamless
    const x = Q() * size, y = Q() * size, r = size * (B.r0 + Q() * (B.r1 - B.r0));
    const t = Q() < 0.5 ? col.clone().lerp(new THREE.Color(1, 0.97, 0.9), 0.5) : col.clone().multiplyScalar(0.8); // own hue
    const rgb = [t.r, t.g, t.b].map((v) => Math.round(v * 255)).join(), a = B.alpha * blotch * (0.5 + 0.5 * Q()) * Math.min(1.5, strength);
    for (const dx of [-size, 0, size]) for (const dy of [-size, 0, size]) {
      const gr = lg.createRadialGradient(x + dx, y + dy, 0, x + dx, y + dy, r);
      gr.addColorStop(0, `rgba(${rgb},${a})`); gr.addColorStop(1, `rgba(${rgb},0)`);
      lg.fillStyle = gr; lg.fillRect(x + dx - r, y + dy - r, 2 * r, 2 * r);
    }
  }
  g.filter = "blur(2px)"; g.drawImage(L, 0, 0); g.filter = "none";
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
  g.fillStyle = ink; g.strokeStyle = INK; g.lineWidth = 8;
  const x = s * (0.3 + R() * 0.4), y = s * (0.3 + R() * 0.3), r = s * (0.15 + R() * 0.1);
  g.beginPath();
  if (R() < 0.5) g.arc(x, y, r, 0, Math.PI * 2); else g.rect(x - r, y - r, 2 * r, 2 * r);
  g.fill(); g.stroke();
  g.fillRect(s * 0.2, s * 0.8, s * 0.6, s * 0.06);
};

/** dry-grass / leaf ticks scattered over the base */
const grass = (col, n = 160, len = 14) => (g, s, R) => {
  g.strokeStyle = col; g.lineWidth = 3; g.lineCap = "round";
  for (let i = 0; i < n; i++) {
    const x = R() * s, y = R() * s, a = -Math.PI / 2 + (R() - 0.5) * 0.9;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len); g.stroke();
  }
};
/** stand crowd: two rows of outfit blobs with white heads. One tile is `aspect` times wider than tall in world
 *  units, so shapes are drawn stretched in y here and come out round once mapped. */
const crowd = (aspect) => (g, s, R) => {
  const cols = ["#e63946", "#457b9d", "#f4a261", "#2a9d8f", "#e9c46a", "#8338ec", "#ffffff", "#264653"];
  const per = 6, w = s / per, k = Math.min(aspect, 1 / (0.9 * 0.45 * per / 6)); // keep two rows inside the tile
  g.strokeStyle = INK; g.lineWidth = 3;
  for (const [row, y0] of [[0, 0.55], [1, 0.97]]) {
    for (let i = 0; i < per; i++) {
      const cx = (i + 0.5 + (row ? 0.5 : 0) + (R() - 0.5) * 0.3) * w, y = s * (y0 - R() * 0.06), r = w * 0.36;
      g.fillStyle = cols[Math.floor(R() * cols.length)];
      g.beginPath(); g.ellipse(cx, y, r, r * k, 0, Math.PI, 0); g.fill(); g.stroke();
      g.fillStyle = "#ffffff";
      g.beginPath(); g.ellipse(cx, y - r * k * 1.2, r * 0.5, r * 0.5 * k, 0, 0, Math.PI * 2); g.fill(); g.stroke();
    }
  }
};
/** distant sky band: a deeper sky colour overhead fading through the sky colour to the haze colour at the horizon
 *  (style.js depth.sky: the stops sit in the part of the band a camera sees) */
const haze = (sky, low) => (g, s) => {
  const gr = g.createLinearGradient(0, 0, 0, s), S = STYLE.depth.sky;
  gr.addColorStop(0, new THREE.Color(sky).multiplyScalar(S.top).getStyle());
  gr.addColorStop(S.mid, sky); gr.addColorStop(S.low, low); gr.addColorStop(1, low);
  g.globalAlpha = 0.85; g.fillStyle = gr; g.fillRect(0, 0, s, s); g.globalAlpha = 1;
};

class Builder {
  constructor(group, seed, strength = 1) {
    this.group = group; this.seed = seed; this.n = 0; this.strength = strength;
    this.pieces = new Map(); this.piece_ = null; // piece id -> { meshes, box }: what the engine may hide per shot
    group.userData.pieces = this.pieces;
    // ambient life: fn(t seconds, n frame) run every frame after scrollSet (main.js), so it may add to position.x;
    // everything else it sets absolutely. Pure functions of the frame: frames stay deterministic.
    this.anims = group.userData.anims = [];
  }
  anim(fn) { this.anims.push(fn); }
  /** everything added inside fn is one prop piece (hidden or shown together) */
  piece(fn) { this.piece_ = this.pieces.size; fn(); this.piece_ = null; }
  mat(color, pattern = null, repeat = [1, 1], kind = null) {
    const map = paint(this.seed, this.n++, color, pattern, this.strength, 256, kind === "flat" ? STYLE.blotch.floor : 1);
    map.repeat.set(...repeat);
    return setMaterial(map, kind);
  }
  /** centred primitive at pos; outline = inverted ink hull (hullGeometry); floor = exempt from clearance.
   *  Anything that is not floor or backdrop (walls, windows, posters, buildings) is a prop piece. */
  add(geo, mat, pos, opts = {}) { return this.place(new THREE.Mesh(geo, mat), pos, opts); }
  /** add mesh m (built elsewhere: an item card) like add does */
  place(m, pos, { outline = true, rot = null, floor = false, backdrop = false, travelHide = false, name = "" } = {}) {
    const geo = m.geometry;
    m.name = name; // tests find named parts (e.g. the stadium rail) through window.loopCheck
    m.position.set(...pos);
    m.userData.kind = floor ? "floor" : backdrop ? "backdrop" : "prop";
    m.userData.travelHide = travelHide; // floor/backdrop mark that makes no sense scrolling past (finish line)
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
      const h = new THREE.Mesh(hullGeometry(geo), HULL);
      h.position.copy(m.position); h.rotation.copy(m.rotation);
      this.group.add(h);
      m.userData.hull = h;
    }
    if (!floor && !backdrop) {
      const id = this.piece_ ?? this.pieces.size;
      if (!this.pieces.has(id)) this.pieces.set(id, { meshes: [], box: new THREE.Box3() });
      const pc = this.pieces.get(id);
      pc.meshes.push(m, ...(m.userData.hull ? [m.userData.hull] : []));
      m.updateMatrixWorld();
      pc.box.union(new THREE.Box3().setFromObject(m));
    }
    return m;
  }
  box(w, h, d, color, pos, opts = {}) {
    const kind = opts.floor ? "flat" : opts.sky ? "sky" : null;
    return this.add(new THREE.BoxGeometry(w, h, d), opts.mat || this.mat(color, opts.pattern, opts.repeat, kind), pos, opts);
  }
  cyl(r0, r1, h, color, pos, opts = {}) { return this.add(new THREE.CylinderGeometry(r0, r1, h, 20), opts.mat || this.mat(color, opts.pattern), pos, opts); }
  ball(r, color, pos, opts = {}) { return this.add(new THREE.SphereGeometry(r, 20, 14), opts.mat || this.mat(color), pos, opts); }
  /** squashed sphere (hills, bushes): sy scales the height */
  mound(r, sy, color, pos, opts = {}) {
    return this.add(new THREE.SphereGeometry(r, 28, 12).scale(1, sy, 1), opts.mat || this.mat(color, opts.pattern, opts.repeat), pos, opts);
  }
}

// --- outdoor sets. Floors reach z +12 so wides never see an edge; far scenery is backdrop (never hidden); fog
// hazes everything past ~16 units, far behind any actor. Repeated props share one material (one texture).
function sky(b, color, low) {
  b.box(220, 70, 0.1, color, [0, 30, -75], { outline: false, backdrop: true, sky: true, pattern: haze(color, low) });
  const C = STYLE.clouds;
  if (new THREE.Color(color).getHSL({}).l < C.minLight) return; // night sky: no daytime clouds
  const R = rng(b.seed, "clouds");
  for (let i = 0; i < C.count; i++) { // spread across the sky, a little above the horizon band a wide sees
    const t = new THREE.CanvasTexture(cloudCanvas(R, C));
    t.colorSpace = THREE.SRGBColorSpace;
    const w = 14 + R() * 12, x = -36 + (i + 0.2 + R() * 0.6) * (72 / C.count), y = 9 + R() * 10;
    const m = b.add(new THREE.PlaneGeometry(w, w / 2), new THREE.MeshBasicMaterial({ map: t, transparent: true, opacity: C.alpha,
      depthWrite: false, fog: false }), [x, y, -72], { outline: false, backdrop: true });
    if (C.drift) b.anim((s) => drift(m, x, C.drift * s, [-44, 44], 10, C.alpha));
  }
}

/** slide mesh m (built at x0) `d` units right along a looping row lo..hi, fading out over `fade` units at both ends
 *  (opacity `alpha` inside); added on top of the travel scroll scrollSet already placed it at */
function drift(m, x0, d, [lo, hi], fade, alpha) {
  const x = lo + (((x0 - lo + d) % (hi - lo)) + (hi - lo)) % (hi - lo);
  m.position.x += x - x0;
  m.material.opacity = alpha * Math.min(1, (x - lo) / fade, (hi - x) / fade);
}

/** indoor finish (STYLE.room): baseboard at the wall foot, light falling off toward ceiling and floor on the wall,
 *  a contact shadow on the floor along the wall. Wall front face at z -2.6, floor at y 0. */
function roomFinish(b, wall) {
  const S = STYLE.room, shadow = new THREE.Color(STYLE.light.shadow), hsl = new THREE.Color(wall).getHSL({});
  const board = new THREE.Color().setHSL(hsl.h, hsl.s, hsl.l * S.baseboard.tone), h = S.baseboard.h;
  b.box(14, h, 0.05, board.getStyle(), [0, h / 2, -2.575], { backdrop: true, outline: false });
  b.box(14, 0.025, 0.06, new THREE.Color().setHSL(hsl.h, hsl.s, Math.min(0.95, hsl.l * 1.08)).getStyle(), // lit top lip
    [0, h + 0.0125, -2.57], { backdrop: true, outline: false });
  // vertical alpha ramp of the shadow colour, in vertex colours (a canvas gradient dithers into a visible grid once
  // stretched): stops [[at 0..1 top -> bottom, alpha]...] on a w x len strip, top at +len/2
  const ramp = (len, stops) => {
    const pos = [], col = [], idx = [];
    stops.forEach(([at, a], k) => {
      for (const x of [-7, 7]) { pos.push(x, len / 2 - at * len, 0); col.push(shadow.r, shadow.g, shadow.b, a); }
      if (k) idx.push(2 * k - 2, 2 * k, 2 * k - 1, 2 * k - 1, 2 * k, 2 * k + 1);
    });
    const g = new THREE.BufferGeometry().setIndex(idx);
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(col, 4));
    return g;
  };
  const mat = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false, fog: false, side: THREE.DoubleSide });
  b.add(ramp(6, [[0, S.wall.top], [0.45, 0], [0.85, 0], [1, S.wall.foot]]), mat, [0, 3, -2.595], { outline: false, backdrop: true });
  const d = S.floor.depth;
  b.add(ramp(d, [[0, S.floor.alpha], [1, 0]]).rotateX(-Math.PI / 2), mat, [0, 0.004, -2.6 + d / 2], { outline: false, floor: true });
}

/** posts + two rails from a to b along x (at depth `at`) or along z (at x `at`), in ~5-unit prop pieces so a
 *  close-up only hides the stretch behind the subject */
function fence(b, a, c, at, { h = 0.9, step = 1.6, along = "x", mat }) {
  const n = Math.max(1, Math.round(Math.abs(c - a) / 5)), seg = (c - a) / n;
  const P = (v, y) => (along === "x" ? [v, y, at] : [at, y, v]);
  for (let i = 0; i < n; i++) b.piece(() => {
    const lo = Math.min(a + seg * i, a + seg * (i + 1)), hi = lo + Math.abs(seg);
    for (let v = lo; v <= hi + 1e-6; v += step) b.box(0.1, h, 0.1, null, P(v, h / 2), { mat });
    for (const y of [h * 0.45, h * 0.85]) {
      b.box(along === "x" ? hi - lo : 0.06, 0.08, along === "x" ? 0.06 : hi - lo, null, P((lo + hi) / 2, y), { mat });
    }
  });
}

// Outdoor layouts that repeat along x repeat with a period dividing the scroll band (BAND, 28 units), so a
// travel shot can wrap them around the band without a seam.
const BAND = { lo: -14, hi: 14 };

function dirt_road(b, R, v) {
  // crossroads: the actors' road runs across the frame (travel shots scroll along it), a side road runs off into
  // the distance from the junction; fence behind the near road, telegraph line further back
  const sx = [0, -3, 3][v], poleOff = [3.5, 1, 6][v];
  b.box(140, 0.1, 100, "#dcbc72", [0, -0.07, -38], { outline: false, floor: true, pattern: lines("h", 10, "#c49c50", 5), repeat: [30, 20] });
  b.box(140, 0.1, 3.4, "#c69a68", [0, -0.05, -0.1], { outline: false, floor: true, pattern: lines("h", 3, "#a87b4e", 7), repeat: [40, 1] });
  b.box(3.4, 0.1, 60, "#c69a68", [sx, -0.051, -31.8], { outline: false, floor: true, pattern: lines("v", 3, "#a87b4e", 7), repeat: [1, 18] });
  sky(b, "#bfe0ee", "#f7e7bf");
  for (let i = 0; i < 6; i++) { // distant hills
    b.mound(14 + R() * 10, 0.28, ["#a9b779", "#b9b07a", "#98a86e"][i % 3], [-60 + i * 24 + R() * 8, -1, -48 - R() * 10], { backdrop: true });
  }
  const wood = b.mat("#8a5a32"), pole = b.mat("#6b4a2e"), wire = b.mat("#2b2b2b");
  fence(b, BAND.lo, sx - 1.9, -2.0, { mat: wood }); // gap where the side road leaves
  fence(b, sx + 1.9, BAND.hi, -2.0, { mat: wood });
  for (let x = BAND.lo + poleOff; x < BAND.hi; x += 7) b.piece(() => { // pole, crossbar, wires half-way to each neighbour
    b.cyl(0.07, 0.1, 4.4, null, [x, 2.2, -3.2], { mat: pole });
    b.box(0.09, 0.09, 1.1, null, [x, 4.0, -3.2], { mat: pole });
    for (const dz of [-0.45, 0.45]) b.box(7, 0.03, 0.03, null, [x, 3.92, -3.2 + dz], { mat: wire, outline: false });
  });
  for (let z = -8; z > -50; z -= 7) b.piece(() => { // a second line beside the side road, into the distance
    b.cyl(0.07, 0.1, 4.4, null, [sx + 2.4, 2.2, z], { mat: pole });
    b.box(1.1, 0.09, 0.09, null, [sx + 2.4, 4.0, z], { mat: pole });
  });
  const bush = b.mat("#a3a04f");
  const bushes = [[[-4.5, -3], [5, -7], [-9, -5]], [[4.6, -2.8], [-6.2, -9], [10, -4]], [[-5, -5], [7.8, -4], [-11, -3]]][v];
  for (const [x, z] of bushes) b.piece(() => b.mound(0.6 + R() * 0.3, 0.6, null, [x, 0.15, z], { mat: bush }));
}

function oak(b, x, z) {
  b.piece(() => {
    b.cyl(0.3, 0.45, 2.6, "#6b4429", [x, 1.3, z]);
    const leaf = b.mat("#3d8b3d", grass("#2f6f2f", 60));
    for (const [dx, dy, r] of [[0, 3.4, 1.5], [-1.1, 2.9, 1.1], [1.1, 3.0, 1.15], [-0.5, 4.2, 1.1], [0.6, 4.1, 1.0]]) {
      b.ball(r, null, [x + dx, dy, z - 0.2], { mat: leaf });
    }
  });
}

function farmhouse(b, x, z) {
  b.box(3.2, 2.2, 2.4, "#f4efe4", [x, 1.1, z], { backdrop: true });
  for (const sg of [-1, 1]) b.box(3.6, 0.14, 1.75, "#c0392b", [x, 2.55, z + sg * 0.62], { backdrop: true, rot: [sg * 0.62, 0, 0] });
  b.box(0.5, 0.9, 0.05, "#7a4b2a", [x - 0.6, 0.45, z + 1.22], { backdrop: true });
  b.box(0.6, 0.5, 0.05, "#9fd3f5", [x + 0.7, 1.3, z + 1.22], { backdrop: true });
}

function countryside(b, R, v) {
  const side = [1, -1, 1][v];
  b.box(140, 0.1, 100, "#8cc152", [0, -0.07, -38], { outline: false, floor: true, pattern: grass("#6fa53c"), repeat: [40, 30] });
  sky(b, "#9fd3f5", "#e8f4f0");
  const greens = ["#7db648", "#9cc95a", "#6aa83f", "#b5c96a"];
  for (let i = 0; i < 7; i++) { // rolling fields, some striped like crops
    const crop = R() < 0.4;
    b.mound(8 + R() * 8, 0.3, crop ? "#d9c46a" : greens[i % 4], [-40 + i * 13 + R() * 5, -1.2, -18 - R() * 18],
      { backdrop: true, pattern: crop ? lines("h", 8, "#c2a94c", 6) : grass("#5f9a36", 80), repeat: [3, 3] });
  }
  const [hx, hz] = [[-6, -24], [7, -22], [-3, -28]][v];
  farmhouse(b, hx, hz);
  b.box(2.6, 2.6, 2.6, "#b5442f", [hx + (hx < 0 ? 4.2 : -4.2), 1.3, hz - 1], { backdrop: true }); // barn
  oak(b, side * [4.4, 4.1, 3.7][v], [-2.8, -3.4, -5][v]); // big oak, off-stage to one side
  const bale = b.mat("#e2c15c", lines("v", 6, "#c9a43f", 4));
  const bales = [[[-3.2, -1.6], [-4.2, -3.5], [2.9, -7]], [[3.0, -1.8], [-3.0, -6], [4.5, -5]], [[-3.4, -2.2], [-2.6, -4.6], [3.6, -9]]][v];
  for (const [x, z] of bales) {
    b.piece(() => b.cyl(0.55, 0.55, 1.0, null, [x, 0.55, z], { mat: bale, rot: [0, R() * 0.6, Math.PI / 2] }));
  }
}

function orchard(b, R, v) {
  b.box(140, 0.1, 100, "#7fbf4d", [0, -0.07, -38], { outline: false, floor: true, pattern: grass("#5f9e38"), repeat: [40, 30] });
  sky(b, "#9fd3f5", "#e3f2e6");
  for (let i = 0; i < 5; i++) b.mound(12 + R() * 8, 0.3, "#6aa83f", [-50 + i * 25, -1.5, -45 - R() * 8], { backdrop: true });
  const trunk = b.mat("#7b5132"), leaf = b.mat("#3f9a3a", grass("#2f7d2c", 60)), apple = b.mat("#a6d63c");
  const off = [0, 1.4, 0.7][v], step = 2.8; // 10 trees per row fill the 28-unit band exactly
  for (let row = 0; row < 6; row++) { // rows of apple trees; green apples on the near rows
    const z = -3.2 - row * 3.3, x0 = BAND.lo + ((off + (row % 2) * 1.4) % step);
    for (let k = 0, x = x0; k < 10; x = x0 + ++k * step) b.piece(() => {
      b.cyl(0.12, 0.17, 1.3, null, [x, 0.65, z], { mat: trunk });
      b.ball(0.95, null, [x, 1.95, z], { mat: leaf });
      for (let i = 0; row < 3 && i < 6; i++) { // on the front half of the crown
        const a = (R() - 0.5) * 2.2, e = (R() - 0.4) * 1.1;
        b.ball(0.1, null, [x + Math.sin(a) * Math.cos(e) * 0.95, 1.95 + Math.sin(e) * 0.95, z + Math.cos(a) * Math.cos(e) * 0.95],
          { mat: apple, outline: false });
      }
    });
  }
  const wood = b.mat("#a0703f");
  if (v === 2) fence(b, -1.6, -12, -3.2, { h: 0.6, step: 1.2, along: "z", mat: wood });
  else fence(b, BAND.lo, BAND.hi, -1.6, { h: 0.6, step: 1.2, mat: wood }); // low fence behind the actors
  const cx = [3.2, -3.3, 3.4][v];
  b.piece(() => { // crate of picked apples off to one side
    b.box(0.7, 0.4, 0.5, "#c8935a", [cx, 0.2, -1.3]);
    for (let i = 0; i < 4; i++) b.ball(0.1, null, [cx - 0.17 + (i % 2) * 0.34, 0.45, -1.4 + Math.floor(i / 2) * 0.2], { mat: apple });
  });
}

function stadium(b, R, v) {
  b.box(140, 0.1, 100, "#6cbf4a", [0, -0.07, -38], { outline: false, floor: true, pattern: lines("h", 2, "#5aa83c", 30), repeat: [1, 40] });
  b.box(140, 0.1, 6, "#c4553b", [0, -0.05, -0.4], { outline: false, floor: true, pattern: lines("h", 6, "#f4efe4", 3), repeat: [40, 1] });
  sky(b, "#9fd3f5", "#e8f4f0");
  const fx = [2.7, -2.7, 3.6][v];
  b.box(0.3, 0.1, 6, "#ffffff", [fx, -0.03, -0.4], { outline: false, floor: true, travelHide: true }); // finish line
  b.piece(() => { // finish tape on two posts, across the track
    const post = b.mat("#f4f4f4");
    for (const z of [-2.4, 0.45]) b.cyl(0.05, 0.05, 1.3, null, [fx, 0.65, z], { mat: post });
    b.box(0.03, 0.07, 2.85, "#e63946", [fx, 1.15, -0.975]);
  });
  // low painted rail between the track and the stands: crowd extras stand behind it (z <= -1.8); behind the stage
  // clearance line (z < -1.0), so the stage itself is unchanged
  b.box(140, 0.48, 0.06, "#f4efe4", [0, 0.24, -1.6], { backdrop: true, name: "rail", pattern: lines("v", 10, "#2d6fb3", 6), repeat: [20, 1] });
  b.box(140, 0.06, 0.12, "#c4553b", [0, 0.5, -1.6], { backdrop: true, name: "rail" });
  b.box(140, 1.0, 0.2, "#2d6fb3", [0, 0.5, -4.2], { backdrop: true, pattern: lines("v", 4, "#f4efe4", 6), repeat: [12, 1] });
  for (let i = 0; i < 5; i++) { // stepped stands, a crowd strip on top of each step
    const z = -5 - i * 1.4, h = 1.1 + i * 0.8;
    b.box(140, h, 1.4, "#9aa0a6", [0, h / 2, z], { backdrop: true });
    b.box(140, 0.8, 0.05, "#9aa0a6", [0, h + 0.4, z + 0.62],{ outline: false, backdrop: true, pattern: crowd(2 / 0.8), repeat: [70, 1] });
  }
  const cols = ["#e63946", "#f4a261", "#2a9d8f", "#e9c46a", "#457b9d"], top = 1.1 + 4 * 0.8 + 0.8;
  for (let i = 0; i < 7; i++) { // flags on the top rim, every 4 units across the band
    const x = BAND.lo + i * 4 + [0.5, 2.5, 1.5][v], z = -10.8;
    b.cyl(0.04, 0.04, 2.0, "#f4f4f4", [x, top + 1.0, z], { backdrop: true });
    b.box(0.9, 0.55, 0.03, cols[(i + v) % cols.length], [x + 0.47, top + 1.7, z], { backdrop: true });
  }
}

function room(b) {
  b.box(14, 0.1, 12, "#c8935a", [0, -0.05, 2.5], { outline: false, floor: true, pattern: lines("v", 8, "#8a5a32", 3), repeat: [4, 3] });
  b.box(14, 6, 0.2, "#f2d6a2", [0, 3, -2.7], { outline: false, backdrop: true, pattern: lines("v", 6, "#e6c48a", 8), repeat: [5, 2] });
  roomFinish(b, "#f2d6a2");
  b.cyl(1.6, 1.6, 0.02, "#d9534f", [0, 0.01, 0.2], { outline: false, floor: true }); // rug
  b.piece(() => { // sofa
    b.box(2.4, 0.45, 0.9, "#5b8bd9", [-1.4, 0.22, -1.9]);
    b.box(2.4, 0.7, 0.25, "#4a76c0", [-1.4, 0.8, -2.3]);
    for (const x of [-2.65, -0.15]) b.box(0.25, 0.65, 0.9, "#4a76c0", [x, 0.33, -1.9]);
  });
  // window, picture (backdrop), lamp
  b.box(1.4, 1.2, 0.08, "#ffffff", [1.6, 2.2, -2.55], { backdrop: true });
  b.box(1.2, 1.0, 0.04, "#9fd3f5", [1.6, 2.2, -2.5], { outline: false, backdrop: true });
  b.box(0.8, 0.6, 0.05, "#e8a33d", [-1.4, 2.3, -2.55], { backdrop: true });
  b.piece(() => {
    b.cyl(0.04, 0.04, 1.6, "#333333", [2.7, 0.8, -1.7]);
    b.cyl(0.18, 0.35, 0.4, "#fff3b0", [2.7, 1.75, -1.7]);
  });
}

function office(b) {
  // warm wall, teal carpet, coloured props at street-set saturation; everything across the stage sits behind z -1
  b.box(14, 0.1, 12, "#4fa39b", [0, -0.05, 2.5], { outline: false, floor: true, pattern: lines("h", 8, "#3f8a83", 3), repeat: [5, 4] });
  b.box(14, 6, 0.2, "#f2bd85", [0, 3, -2.7], { outline: false, backdrop: true, pattern: lines("h", 4, "#e3a66a", 10), repeat: [4, 2] });
  roomFinish(b, "#f2bd85");
  b.box(2.4, 1.0, 0.06, "#9fd3f5", [0, 2.4, -2.58], { backdrop: true, pattern: lines("h", 10, "#6fa8d0", 5) }); // blinds
  b.box(0.7, 0.95, 0.04, "#e76f51", [-2.0, 2.3, -2.58], { backdrop: true, pattern: poster("#e9c46a") });
  b.box(0.7, 0.95, 0.04, "#2a9d8f", [2.0, 2.3, -2.58], { backdrop: true, pattern: poster("#f4a261") });
  const chairs = ["#e63946", "#457b9d"], mugs = ["#ffb703", "#8338ec"];
  [-1.8, 1.8].forEach((x, i) => {
    b.piece(() => { // desk with monitor and mug
      b.box(1.6, 0.08, 0.8, "#d99a4e", [x, 0.75, -2.05]);
      for (const dx of [-0.72, 0.72]) b.box(0.08, 0.72, 0.7, "#8a5a32", [x + dx, 0.36, -2.05]);
      b.box(0.62, 0.42, 0.05, "#2d3440", [x, 1.07, -2.3]);
      b.box(0.52, 0.32, 0.02, "#7ec8e3", [x, 1.07, -2.27], { outline: false });
      b.box(0.1, 0.12, 0.05, "#2d3440", [x, 0.85, -2.3], { outline: false });
      b.cyl(0.06, 0.06, 0.12, mugs[i], [x + 0.55, 0.85, -1.85]);
    });
    b.piece(() => { // chair, back facing the camera
      b.box(0.5, 0.08, 0.5, chairs[i], [x + 0.2, 0.48, -1.4]);
      b.box(0.5, 0.6, 0.08, chairs[i], [x + 0.2, 0.8, -1.17]);
      b.cyl(0.04, 0.04, 0.44, "#2d3440", [x + 0.2, 0.22, -1.4]);
    });
  });
  b.piece(() => { // water cooler
    b.cyl(0.25, 0.25, 0.9, "#f4f4f4", [3.0, 0.45, -2.1]);
    b.cyl(0.18, 0.2, 0.45, "#7fc4ef", [3.0, 1.12, -2.1]);
  });
  b.piece(() => { b.cyl(0.25, 0.2, 0.4, "#c8553d", [-3.0, 0.2, -2.1]); b.ball(0.45, "#43aa8b", [-3.0, 0.75, -2.1]); });
  b.piece(() => { b.cyl(0.2, 0.16, 0.35, "#e9c46a", [0.0, 0.18, -2.3]); b.ball(0.3, "#2a9d8f", [0.0, 0.6, -2.3]); });
}

/** one painted window per tile (a tile is ~1.1 x 1.6 units, so the canvas is drawn squashed in y): glass with a
 *  diagonal sheen, a thin mullion cross, a lit sill under it, a darker lintel over it, shutters when given */
const facadeTile = (wall, shutter) => (g, s) => {
  const x0 = s * 0.27, x1 = s * 0.73, y0 = s * 0.2, y1 = s * 0.78, k = new THREE.Color(wall);
  g.fillStyle = k.clone().multiplyScalar(0.82).getStyle(); g.fillRect(x0 - 8, y0 - 16, x1 - x0 + 16, 12); // lintel
  if (shutter) {
    g.fillStyle = shutter; g.strokeStyle = INK; g.lineWidth = 3;
    for (const sx of [x0 - 30, x1 + 4]) { g.fillRect(sx, y0, 26, y1 - y0); g.strokeRect(sx, y0, 26, y1 - y0); }
  }
  g.fillStyle = "#7fbbe6"; g.fillRect(x0, y0, x1 - x0, y1 - y0);
  g.fillStyle = "rgba(255,255,255,0.35)"; // sheen: a pale diagonal band across the upper glass
  g.beginPath(); g.moveTo(x0, y0 + 30); g.lineTo(x0 + 40, y0); g.lineTo(x0 + 70, y0); g.lineTo(x0, y0 + 70); g.fill();
  g.strokeStyle = INK; g.lineWidth = 3;
  g.beginPath(); g.moveTo((x0 + x1) / 2, y0); g.lineTo((x0 + x1) / 2, y1); g.moveTo(x0, y0 + (y1 - y0) * 0.45);
  g.lineTo(x1, y0 + (y1 - y0) * 0.45); g.stroke();
  g.lineWidth = 4; g.strokeRect(x0, y0, x1 - x0, y1 - y0);
  g.fillStyle = "#f6ead2"; g.fillRect(x0 - 10, y1, x1 - x0 + 20, 12); // sill
  g.lineWidth = 2.5; g.strokeRect(x0 - 10, y1, x1 - x0 + 20, 12);
};

/** canvas texture for an unlit sprite plane (flags, birds, smoke): drawn by fn on a w x h canvas */
function sprite(w, h, fn) {
  const c = Object.assign(document.createElement("canvas"), { width: w, height: h });
  fn(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const spriteMat = (map, opts = {}) => new THREE.MeshBasicMaterial({ map, transparent: true, depthWrite: false, fog: false, ...opts });

/** a string of pennants from x0 to x1 sagging from `top` by `sag`, at depth z; each pennant swings and flutters in
 *  the wind (rotation about its top edge), the string segments stay put */
function bunting(b, x0, x1, top, sag, z, R) {
  const cols = ["#e63946", "#f4c430", "#2a9d8f", "#ffffff", "#457b9d"];
  const mats = cols.map((c) => spriteMat(sprite(64, 80, (g, w, h) => {
    g.fillStyle = c; g.strokeStyle = INK; g.lineWidth = 5; g.lineJoin = "round";
    g.beginPath(); g.moveTo(4, 4); g.lineTo(w - 4, 4); g.lineTo(w / 2, h - 5); g.closePath(); g.fill(); g.stroke();
  }), { alphaTest: 0.5, depthWrite: true, transparent: false, side: THREE.DoubleSide }));
  const n = Math.round((x1 - x0) / 0.5), y = (x) => top - sag * (1 - ((2 * (x - x0)) / (x1 - x0) - 1) ** 2);
  const geo = new THREE.PlaneGeometry(0.34, 0.42).translate(0, -0.21, 0); // origin on the top edge: swings from the string
  const wire = b.mat("#2b2b2b");
  for (let i = 0; i < n; i++) {
    const xa = x0 + i * 0.5, xb = xa + 0.5, len = Math.hypot(0.5, y(xb) - y(xa));
    b.box(len, 0.025, 0.025, null, [xa + 0.25, (y(xa) + y(xb)) / 2, z], { mat: wire, outline: false, backdrop: true,
      rot: [0, 0, Math.atan2(y(xb) - y(xa), 0.5)] });
    const xm = xa + 0.25, m = b.add(geo, mats[Math.floor(R() * cols.length)], [xm, y(xm), z], { outline: false, backdrop: true });
    const ph = R() * Math.PI * 2, sp = 2.2 + R() * 1.2;
    b.anim((t) => { m.rotation.x = 0.45 * Math.sin(sp * t + ph) - 0.25; m.rotation.z = 0.12 * Math.sin(0.7 * sp * t + ph * 1.3); });
  }
}

/** chimney smoke: soft puffs (children of the chimney mesh: they scroll with it) rising, drifting right, growing, fading */
function smoke(b, chimney, R) {
  const map = sprite(128, 128, (g, s) => {
    const gr = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
    gr.addColorStop(0, "rgba(246,244,240,0.95)"); gr.addColorStop(0.6, "rgba(232,230,236,0.8)"); gr.addColorStop(1, "rgba(232,230,236,0)");
    g.fillStyle = gr; g.fillRect(0, 0, s, s);
  });
  const N = 5, period = 4 + R() * 1.5, ph = R();
  for (let j = 0; j < N; j++) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.6), spriteMat(map));
    chimney.add(m);
    b.anim((t) => {
      const p = (((t / period + ph + j / N) % 1) + 1) % 1;
      m.position.set(0.7 * p + 0.06 * Math.sin(6 * p + j), 0.5 + 2.4 * p, 0);
      m.scale.setScalar(0.5 + 1.6 * p);
      m.material.opacity = 0.8 * Math.min(1, p * 6) * (1 - p);
    });
  }
}

/** a few ink "v" birds crossing over the street at height y, flapping (the drawing flips through edge-on) */
function birds(b, R, y, z) {
  const map = sprite(128, 64, (g) => {
    g.strokeStyle = INK; g.lineWidth = 7; g.lineCap = "round";
    g.beginPath(); g.moveTo(8, 18); g.quadraticCurveTo(36, 10, 64, 40); g.quadraticCurveTo(92, 10, 120, 18); g.stroke();
  });
  for (let i = 0; i < 3; i++) {
    const x0 = -16 + i * 10.7 + R() * 3, yy = y + R() * 0.8, sp = 1.1 + R() * 0.4, ph = R() * 6;
    const m = b.add(new THREE.PlaneGeometry(0.42, 0.21), spriteMat(map, { side: THREE.DoubleSide }), [x0, yy, z - i * 0.3],
      { outline: false, backdrop: true });
    b.anim((t) => {
      drift(m, x0, sp * t, [-16, 16], 2, 1);
      m.position.y = yy + 0.12 * Math.sin(0.9 * t + ph);
      m.scale.y = Math.cos(9 * t + ph); // wings beat up and down
    });
  }
}

function street(b, R) {
  // floors span 140 so travel shots can scroll them; buildings fill the 28-unit band exactly (last one sized to fit)
  b.box(140, 0.1, 5.5, "#dcd3c2", [0, -0.05, -1.0], { outline: false, floor: true, pattern: lines("v", 6, "#b4a994", 2), repeat: [60, 2] });
  const road = "#727684";
  b.box(140, 0.08, 9.4, road, [0, -0.08, 6.4], { outline: false, floor: true, repeat: [30, 2] });
  b.box(140, 0.12, 0.24, "#c9c0ae", [0, -0.02, 1.8], { floor: true });                     // curb, inked
  b.box(140, 0.02, 0.16, road, [0, -0.035, 3.6], { outline: false, floor: true, repeat: [40, 1], // centre dashes
    pattern: (g, s) => { g.fillStyle = "#f4f1e8"; g.fillRect(0, 0, s * 0.55, s); } });
  sky(b, "#5f9fe4", "#d4eaf8");
  // storybook facades: saturated wall colours, a darker plinth, a cream cornice, shutters, doors with a step,
  // striped awnings, chimneys with smoke
  const palette = ["#e8735a", "#f3c45e", "#7cc49a", "#ef9fb0", "#69aee0", "#f5a25d", "#f2e3c4"];
  const shutters = ["#2f6f8f", "#3d8b5a", "#b5442f", null];
  const stripes = [["#e63946", "#ffffff"], ["#2a9d8f", "#f6ead2"], ["#f4a261", "#ffffff"]];
  const Z = -4.2, FRONT = Z + 1; // building centre depth, front face
  let x = BAND.lo, i = 0;
  while (x < BAND.hi - 0.05) {
    let w = 2.2 + R() * 1.2;
    const h = 3.7 + R() * 1.7, wall = palette[Math.floor(R() * palette.length)], sh = shutters[Math.floor(R() * shutters.length)];
    if (BAND.hi - x - w - 0.05 < 2.2) w = BAND.hi - x - 0.05;
    const cx = x + w / 2, dark = new THREE.Color(wall).multiplyScalar(0.7).getStyle();
    b.box(w, h, 2, wall, [cx, h / 2, Z], { backdrop: true, pattern: facadeTile(wall, sh), repeat: [Math.max(1, Math.round(w / 1.1)), Math.round(h / 1.6)] });
    b.box(w, 0.55, 2.12, dark, [cx, 0.275, Z], { backdrop: true });                 // plinth
    b.box(w, 0.22, 2.24, "#f6ead2", [cx, h - 0.11, Z], { backdrop: true });          // cornice
    if (i % 2 === 0) { // door with a step
      const dx = cx + (R() - 0.5) * (w - 1.2);
      b.box(0.72, 1.4, 0.06, ["#7a4b2a", "#2f6f8f", "#b5442f"][i % 3], [dx, 0.7 + 0.12, FRONT + 0.04], { backdrop: true });
      b.box(0.95, 0.12, 0.32, "#cfc6b4", [dx, 0.06, FRONT + 0.16], { backdrop: true });
    }
    if (i % 3 === 1) { // striped awning over the ground floor, tilted down toward the street
      const [a, c] = stripes[i % stripes.length];
      b.box(w * 0.82, 0.06, 0.9, a, [cx, 2.35, FRONT + 0.38], { backdrop: true, rot: [0.32, 0, 0], pattern: lines("v", 4, c, 32), repeat: [Math.round(w), 1] });
    }
    if (R() < 0.6) { // chimney on the roof, smoking
      const ch = b.box(0.4, 0.8, 0.4, "#b5523b", [cx + (R() - 0.5) * (w - 0.8), h + 0.4, Z - 0.3], { backdrop: true });
      b.box(0.5, 0.1, 0.5, "#8a3e2c", [ch.position.x, h + 0.85, Z - 0.3], { backdrop: true });
      smoke(b, ch, R);
    }
    x += w + 0.05; i++;
  }
  for (let k = 0; k < 4; k++) bunting(b, BAND.lo + 7 * k, BAND.lo + 7 * (k + 1), 3.25, 0.3, -2.9, R); // 4 strings fill the band
  birds(b, R, 5.6, -3.0);
  b.piece(() => { b.cyl(0.05, 0.06, 3.2, "#2f3a40", [2.3, 1.6, -1.6]); b.ball(0.2, "#fff3b0", [2.3, 3.25, -1.6]); });
  b.piece(() => { // tree: the crown sways a little in the wind
    b.cyl(0.1, 0.13, 1.4, "#7b5132", [-2.6, 0.7, -2.0]);
    const crown = b.ball(0.8, null, [-2.6, 1.9, -2.0], { mat: b.mat("#4caf50", grass("#3d8f40", 50)) });
    b.anim((t) => { const dx = 0.05 * Math.sin(1.3 * t) + 0.02 * Math.sin(3.1 * t); crown.position.x += dx; crown.userData.hull.position.x += dx; });
  });
  b.piece(() => { // off to the side: behind an actor it reads as a backpack
    b.cyl(0.12, 0.14, 0.45, "#d62828", [3.3, 0.22, -1.2]);
    b.ball(0.12, "#d62828", [3.3, 0.48, -1.2]);
  });
}

const BACKGROUND = { room: "#f2d6a2", office: "#f2bd85", street: "#d4eaf8",
  dirt_road: "#f3e2b8", countryside: "#cfe8ee", orchard: "#cfe8ee", stadium: "#cfe8ee" };
const STRENGTH = { office: 2.2, dirt_road: 1.6, countryside: 1.6, orchard: 1.6, stadium: 1.4 }; // paint visibility
const FOG = { dirt_road: [16, 80], countryside: [20, 90], orchard: [18, 80], stadium: [25, 100] }; // near, far

// --- custom sets (library/sets.json, schema CustomSet): floor, back wall or sky, and primitive pieces. Indoor: the
// room's floor and wall; outdoor: a floor wide enough to scroll (travel shots) and a sky. From library.js.
/** "indoor" / "outdoor" for any set, built in or custom; throws for an unknown one */
export const setKind = (name) => (SETS.includes(name) ? (INDOOR_SETS.has(name) ? "indoor" : "outdoor") : lookup("sets", name).kind);
const INDOOR_SETS = new Set(["room", "office"]); // built-in sets with a back wall (pipeline: BUILTIN_SETS)

// --- water: an outdoor custom set whose floor is blue is a sea or lake (no set field needed): ink wave ticks on the
// floor, a foam band where each piece meets it, and main.js adds ripples and reflections under the cast
/** true when an outdoor set's floor colour reads as water (style.js water.hue / minSat / light) */
export function isWater(spec) {
  if (spec.kind !== "outdoor") return false;
  if (spec.water != null) return spec.water; // set explicitly: no guessing from the colour
  const W = STYLE.water, hsl = new THREE.Color(spec.floor).getHSL({}), hue = hsl.h * 360;
  return hue >= W.hue[0] && hue <= W.hue[1] && hsl.s >= W.minSat && hsl.l >= W.light[0] && hsl.l <= W.light[1];
}
/** small "~" ink wave ticks scattered over a water tile */
const waves = (g, s, R) => {
  const W = STYLE.water.wave;
  g.strokeStyle = W.color; g.globalAlpha = W.alpha; g.lineWidth = W.width; g.lineCap = "round";
  for (let i = 0; i < W.count; i++) {
    const x = R() * s, y = R() * s, L = W.len * (0.6 + 0.8 * R());
    g.beginPath(); g.moveTo(x - L, y);
    g.quadraticCurveTo(x - L / 2, y - L * 0.35, x, y); g.quadraticCurveTo(x + L / 2, y + L * 0.35, x + L, y);
    g.stroke();
  }
  g.globalAlpha = 1;
};
/** where piece p meets the water surface (y = 0): [x half, z half] for a box, a radius for a round piece, or null */
export function waterline(p) {
  const y = p.at[1], spans = (h) => y - h / 2 <= 0.05 && y + h / 2 >= 0;
  if (p.shape === "box") return spans(p.size[1]) ? [p.size[0] / 2, p.size[2] / 2] : null;
  if (p.shape === "cyl") return spans(p.size[2]) ? Math.max(p.size[0], p.size[1]) : null;
  const r = p.size[0], sy = p.shape === "mound" ? p.size[1] : 1, k = r * r - (y / sy) ** 2;
  return k > 0 ? Math.sqrt(k) : null;
}
/** foam where a piece stands in the water: a scalloped band just outside its waterline, a child of the piece's mesh
 *  (it moves and hides with it) */
function foam(b, p, mesh) {
  const half = waterline(p);
  if (half === null) return;
  const F = STYLE.water.foam, R = rng(b.seed, "foam", ...p.at), n = 48, pts = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2, c = Math.cos(a), s = Math.sin(a), w = F.width * (0.6 + 0.8 * R());
    const k = Array.isArray(half) ? 1 / Math.max(Math.abs(c) / half[0], Math.abs(s) / half[1]) : half;
    pts.push(new THREE.Vector2(c * (k + w), s * (k + w)));
  }
  const m = new THREE.Mesh(new THREE.ShapeGeometry(new THREE.Shape(pts)).rotateX(Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: F.color, transparent: true, opacity: F.alpha, depthWrite: false, side: THREE.DoubleSide }));
  m.position.set(0, 0.012 - p.at[1], 0); // just over the water surface, under the piece
  mesh.add(m);
}

function custom(b, spec, wide = false) {
  const water = isWater(spec);
  b.group.userData.water = water;
  if (spec.kind === "indoor") {
    b.box(14, 0.1, 12, spec.floor, [0, -0.05, 2.5], { outline: false, floor: true, repeat: [4, 3] });
    b.box(14, 6, 0.2, spec.back, [0, 3, -2.7], { outline: false, backdrop: true, repeat: [5, 2] });
    roomFinish(b, spec.back);
  } else {
    b.box(140, 0.1, 100, spec.floor, [0, -0.07, -38], { outline: false, floor: true, repeat: [28, 20], pattern: water ? waves : null });
    sky(b, spec.back, "#f7f1e1");
  }
  for (const p of spec.pieces || []) {
    const opts = { backdrop: p.backdrop, outline: p.outline ?? true };
    b.piece(() => {
      const m = p.shape === "box" ? b.box(...p.size, p.color, p.at, opts) : p.shape === "cyl" ? b.cyl(...p.size, p.color, p.at, opts)
        : p.shape === "ball" ? b.ball(p.size[0], p.color, p.at, opts) : b.mound(p.size[0], p.size[1], p.color, p.at, opts);
      if (water) foam(b, p, m);
    });
  }
  // World Objects are reusable, named scene instances. They are deliberately separate from held props: their
  // geometry is authored in object-local coordinates and translated to the instance placement in the set.
  for (const spot of spec.objects || []) {
    const instance = wide && spot.at_wide ? { ...spot, at: spot.at_wide } : spot; // a 16:9 frame: its wide spot
    const object = lookup("objects", instance.object);
    if (object.look === "card") { setCard(b, object, instance); continue; }
    const recolour = instance.color && object.pieces?.[0]?.color; // a colour variant: the item's main colour, here
    for (const p of object.pieces || []) {
      const at = [p.at[0] + instance.at[0], p.at[1] + instance.at[1], p.at[2] + instance.at[2]];
      const placed = { ...p, at, ...(recolour && p.color === recolour ? { color: instance.color } : {}) };
      const opts = { backdrop: p.backdrop, outline: p.outline ?? true };
      b.piece(() => {
        const col = placed.color;
        const m = p.shape === "box" ? b.box(...p.size, col, at, opts) : p.shape === "cyl" ? b.cyl(...p.size, col, at, opts)
          : p.shape === "ball" ? b.ball(p.size[0], col, at, opts) : b.mound(p.size[0], p.size[1], col, at, opts);
        if (water) foam(b, placed, m);
      });
    }
  }
}

/** a card World Item placed in a set: standing on `at` (a sky / back card: centred on it), facing +z, animated every
 *  frame (items.js updateCard). Sky and back cards are backdrop (never hidden, parallax by depth in travel shots);
 *  the others are prop pieces with the usual stage clearance. */
function setCard(b, def, inst) {
  const c = itemCard(def, { color: inst.color, accent: inst.accent, tag: inst.id, seed: b.seed });
  c.y = inst.at[1];
  const opts = { outline: false, backdrop: def.layer === "sky" || def.layer === "back" };
  if (def.layer === "sky") (b.group.userData.sky ??= []).push(c); // main.js lifts them in low angles (skyLift)
  if (opts.backdrop) b.place(c.root, inst.at, opts);
  else b.piece(() => b.place(c.root, inst.at, opts));
  b.anim((t, n) => updateCard(c, { t, boil: Math.floor(n / BOIL_FRAMES), state: inst.state }));
}

/** build one set (one of its prop variants) into a new group; wide: a 16:9 frame (placed items take their at_wide): built in, else the library's (unknown: throws) */
export function buildSet(name, seed, variant = 0, wide = false) {
  if (!SETS.includes(name)) {
    const spec = lookup("sets", name), group = new THREE.Group();
    custom(new Builder(group, `${seed}:${name}`), spec, wide);
    return finish(group, spec.back, spec.kind === "outdoor" ? [18, 80] : null);
  }
  const group = new THREE.Group();
  const b = new Builder(group, `${seed}:${name}`, STRENGTH[name] ?? 1);
  const v = VARIANTS[name] ? variant % VARIANTS[name] : 0;
  const R = VARIANTS[name] ? rng(seed, "set", name, v) : rng(seed, "set", name); // old sets: unchanged output
  ({ room, office, street, dirt_road, countryside, orchard, stadium })[name](b, R, v);
  return finish(group, BACKGROUND[name], FOG[name]);
}

/** lights, background, fog and travel movers: the same for every set */
function finish(group, background, fog) {
  group.userData.background = new THREE.Color(background);
  if (fog) group.userData.fog = new THREE.Fog(background, ...fog);
  group.updateMatrixWorld(true);
  group.userData.movers = movers(group);
  return group;
}

// --- travel shots: the world scrolls along x past actors running in place.
// Each mover is a prop piece or a floor/backdrop mesh, shifted by f * shift:
//   period: wide floors and long backdrops (>= 50 units) move by the shift modulo one texture tile, so they never
//           run out and look unchanged
//   band:   props and near backdrop inside BAND wrap around it (leave one end, come back at the other)
//   shift:  everything else just moves (far layers, out-of-band items; f < 1 there, so the shift stays small)
// Parallax: floors, props and backdrop nearer than z -12 move at full speed, mid backdrop (fields, farmhouse)
// at 0.35, far hills and sky at 0.1. Props reaching forward of z STAGE.behind are hidden in travel shots: wrapping
// past the actors they would break stage clearance.
const PARALLAX = [[-12, 1], [-40, 0.35], [-Infinity, 0.1]]; // [z centre above, factor]
/** the share of a travel shot's world shift something at depth z moves by (story items: main.js drawItems) */
export const parallaxOf = (z) => PARALLAX.find(([above]) => z > above)[1];
const BAND_W = BAND.hi - BAND.lo;
const mod = (a, n) => ((a % n) + n) % n;
const inBand = (x) => x >= BAND.lo && x < BAND.hi;

function movers(group) {
  const list = [];
  for (const [id, pc] of group.userData.pieces) {
    const cx = pc.box.getCenter(new THREE.Vector3()).x;
    list.push({ meshes: pc.meshes, cx, f: 1, mode: inBand(cx) ? "band" : "shift", piece: id, box: pc.box.clone(),
      near: pc.box.max.z > STAGE.behind });
  }
  for (const m of group.children) {
    const kind = m.userData.kind;
    if (kind !== "floor" && kind !== "backdrop") continue;
    const box = new THREE.Box3().setFromObject(m), c = box.getCenter(new THREE.Vector3()), w = box.max.x - box.min.x;
    const f = kind === "floor" ? 1 : PARALLAX.find(([z]) => c.z > z)[1];
    const mode = w >= 50 ? "period" : f === 1 && inBand(c.x) ? "band" : "shift";
    const period = w / (m.material?.map ? m.material.map.repeat.x : 1);
    list.push({ meshes: [m, ...(m.userData.hull ? [m.userData.hull] : [])], cx: c.x, f, mode, period, box,
      hide: m.userData.travelHide });
  }
  for (const mv of list) mv.base = mv.meshes.map((m) => m.position.x);
  return list;
}

/** x offset of one mover for a world shift (shift 0: exactly 0, so static shots are untouched) */
function moverDx(mv, shift) {
  if (!shift) return 0;
  const d = mv.f * shift;
  if (mv.mode === "band") return BAND.lo + mod(mv.cx + d - BAND.lo, BAND_W) - mv.cx;
  if (mv.mode === "period") return mod(d + mv.period / 2, mv.period) - mv.period / 2;
  return d;
}

/** place the set for a world shift (units, + = world moves right). Returns the prop pieces to hide (travel). */
export function scrollSet(group, shift, travel) {
  const hidden = new Set();
  for (const mv of group.userData.movers) {
    const dx = moverDx(mv, shift);
    mv.meshes.forEach((m, i) => { m.position.x = mv.base[i] + dx; });
    if (mv.hide) for (const m of mv.meshes) m.visible = !travel;
    if (travel && mv.near) hidden.add(mv.piece);
  }
  return hidden;
}

/** seam check for a world shift: rows of band-looping items (same depth, >= 3 items), the widest empty x stretch
 *  around the band now minus the widest one inside the static layout, and that row's z. Excess <= 0 in every row:
 *  the loop adds no gap. */
export function loopExcess(group, shift) {
  const rows = new Map();
  for (const mv of group.userData.movers) {
    if (mv.mode !== "band" || mv.near || mv.hide) continue;
    const z = Math.round(mv.box.getCenter(new THREE.Vector3()).z);
    if (!rows.has(z)) rows.set(z, []);
    rows.get(z).push(mv);
  }
  let worst = -Infinity, at = null;
  for (const [z, items] of rows) {
    if (items.length < 3) continue;
    const merge = (iv) => { // sorted [a, b] intervals -> widest gap between their union's pieces
      iv.sort((p, q) => p[0] - q[0]);
      let end = iv[0][1], gap = 0;
      for (const [a, b] of iv.slice(1)) { gap = Math.max(gap, a - end); end = Math.max(end, b); }
      return { gap, first: iv[0][0], end };
    };
    const inside = merge(items.map((mv) => [mv.box.min.x, mv.box.max.x])).gap;
    const circ = [];
    for (const mv of items) {
      const dx = moverDx(mv, shift), a = BAND.lo + mod(mv.box.min.x + dx - BAND.lo, BAND_W), b = a + mv.box.max.x - mv.box.min.x;
      if (b > BAND.hi) circ.push([a, BAND.hi], [BAND.lo, b - BAND_W]); else circ.push([a, b]);
    }
    const m = merge(circ), around = Math.max(m.gap, m.first + BAND_W - m.end); // incl. the gap across the seam
    if (around - inside > worst) [worst, at] = [around - inside, z];
  }
  return { excess: at === null ? 0 : worst, row: at ?? "none" };  // no rows: nothing loops in a line
}
