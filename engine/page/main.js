// Frame renderer. Deterministic: frame n -> time n / FPS, every random value from rng(seed, keys).
// render.mjs calls setup(data) once, then renderFrame(n) or renderCast(pose) per image (PNG data URL back).
import * as THREE from "three";
import { dolly, glide } from "./borrowed.js";
import { CH, CW, FEET_Y, FIGURE_PX, drawStickman } from "./stickman.js";
import { rng } from "./rng.js";
import { buildSet } from "./world.js";

const FPS = 30, W = 1080, H = 1920;
const CARD_H = 1.6, CARD_W = CARD_H * (CW / CH);
const FIG_H = (CARD_H * FIGURE_PX) / CH; // tallest standing figure in world units, from stickman.js
const BOIL_FRAMES = 4;                 // marker jitter changes every 4 frames (7.5 fps "boil")
const STRIDE = { walk: 1.0, run: 1.8 }; // world units per full walk cycle (two steps)
const LID = [0.5, 1, 1, 0.5];          // 4-frame blink: half, shut, shut, half
const rad = (d) => (d * Math.PI) / 180;
const lerp = (a, b, u) => a + (b - a) * u;

// wide shots: fit the cast's x span + margin; never closer than maxFill (it must still read as a wide). Camera sits
// higher and tilts down so less floor/road fills the bottom and less wall/sky sits above the heads.
const WIDE = { margin: 0.8, maxFill: 0.30, camY: 2.1, lookY: 0.75 };
const SUBJECT_MARGIN = 0.05; // props must clear the subject's on-screen card bounds grown by 5% per side
const SHADOW = { w: 0.75, d: 0.3, opacity: 0.32, bounce: 0.08, y: 0.025 }; // y clears the room rug

// base framing per angle, relative to the subject at (sx, 0, 0): camera offset, look point, fov, how much x follows.
// wide frames every actor on stage instead (see shotCamera).
const ANGLES = {
  wide: { pos: [0, 1.5, 6.5], look: [0, 1.35, 0], fov: 50, follow: 0.4 },
  medium: { pos: [0, 1.15, 4.0], look: [0, 0.95, 0], fov: 45, follow: 1 },
  close: { pos: [0, 1.15, 2.2], look: [0, 1.05, 0], fov: 40, follow: 1 },
  low: { pos: [0, 0.3, 3.4], look: [0, 1.0, 0], fov: 48, follow: 1 },
  high: { pos: [0, 4.0, 4.4], look: [0, 0.55, 0], fov: 46, follow: 0.8 },
  over_shoulder: { pos: [-0.9, 1.45, 2.8], look: [0.2, 1.0, 0], fov: 42, follow: 1 },
};

const canvas = document.getElementById("c");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
const camera = new THREE.PerspectiveCamera(45, W / H, 0.05, 100);
const CARD_GEO = new THREE.PlaneGeometry(CARD_W, CARD_H).translate(0, CARD_H / 2 - CARD_H * (1 - FEET_Y / CH), 0);

let data = null, scene = null;
const sets = {}, cards = {}, hiddenByShot = new Map();

/** soft dark ellipse texture for contact shadows (radial gradient, no randomness) */
const SHADOW_TEX = (() => {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d"), grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, "rgba(0,0,0,1)"); grad.addColorStop(0.55, "rgba(0,0,0,0.6)"); grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad; g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
})();
const SHADOW_GEO = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);

function card(id) {
  if (!cards[id]) {
    const cv = document.createElement("canvas");
    cv.width = CW; cv.height = CH;
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    const mesh = new THREE.Mesh(CARD_GEO, new THREE.MeshBasicMaterial({ map: tex, transparent: true, alphaTest: 0.05, depthWrite: false }));
    mesh.renderOrder = 1; // after its shadow
    const shadow = new THREE.Mesh(SHADOW_GEO, new THREE.MeshBasicMaterial({
      map: SHADOW_TEX, transparent: true, opacity: SHADOW.opacity, depthWrite: false }));
    cards[id] = { cv, tex, mesh, shadow };
  }
  return cards[id];
}

const castOf = (id) => data.series.cast.find((c) => c.id === id) || { id, outfit_color: "#888888", eyes: "dots" };
const charSeed = (id) => `${data.series.slug}:${id}`; // same look in every part and on the cast sheet

function lidAt(f, key) {
  const R = rng(key, "blink");
  let s = -Math.floor(60 * R());
  while (s <= f) {
    if (f - s < 4) return LID[f - s];
    s += 15 + Math.floor(55 * R()); // next blink 0.5-2.3 s later
  }
  return 0;
}

function mouthAt(t, shot) {
  const ph = data.phrases.phrases, [a, b] = shot.phrase_range;
  for (let i = ph[a].word_start; i <= ph[b].word_end; i++) {
    const w = data.phrases.words[i];
    if (t >= w.start && t < w.end) return 0.5 - 0.5 * Math.cos(2 * Math.PI * 5 * (t - w.start)); // ~5 flaps/s
  }
  return 0;
}

function drawCard(id, o) {
  const c = card(id), cast = castOf(id), seed = charSeed(id);
  drawStickman(c.cv, { seed, color: cast.outfit_color, eyes: cast.eyes, ...o });
  c.tex.needsUpdate = true;
  return c.mesh;
}

/** xs: x of every actor at the start and end of the shot. Wide centres on all of them and backs off until the
 *  whole cast fits for the entire shot, including where the move ends (push-in reach, truck shift). */
function shotCamera(shot, sx, xs, u) {
  const A = ANGLES[shot.camera.angle] || ANGLES.medium;
  let pos, look;
  if (shot.camera.angle === "wide" && xs.length) {
    const lo = Math.min(...xs), hi = Math.max(...xs), cx = (lo + hi) / 2;
    const end = shot.camera.speed, tan = Math.tan(rad(A.fov / 2)); // end = move size at u = 1
    const width = hi - lo + WIDE.margin + (shot.camera.move.startsWith("truck") ? 2 * 1.4 * end : 0);
    const reach = shot.camera.move === "push_in" ? 1 - 0.5 * end : 1;
    const fit = width / (2 * tan * (W / H)) / reach;   // whole cast inside the frame edges all shot long
    const notCloser = FIG_H / (2 * tan * WIDE.maxFill); // heads and feet win over size: only ever back off
    pos = [cx, WIDE.camY, Math.max(fit, notCloser)]; look = [cx, WIDE.lookY, 0];
  } else {
    const fx = sx * A.follow;
    pos = [fx + A.pos[0], A.pos[1], A.pos[2]]; look = [fx + A.look[0], A.look[1], A.look[2]];
  }
  const k = shot.camera.speed * u; // the camera keeps creeping for the whole shot (speed >= 0.05)
  switch (shot.camera.move) {
    case "push_in": ({ pos, look } = dolly(pos, look, 1 - 0.5 * k)); break;
    case "pull_out": ({ pos, look } = dolly(pos, look, 1 + 0.7 * k)); break;
    case "truck_left": pos[0] -= 1.4 * k; look[0] -= 1.4 * k; break;
    case "truck_right": pos[0] += 1.4 * k; look[0] += 1.4 * k; break;
    case "crane_up": pos[1] += 1.6 * k; look[1] += 0.5 * k; break;
    case "crane_down": pos[1] = Math.max(0.2, pos[1] - 1.6 * k); look[1] -= 0.4 * k; break;
  }
  camera.fov = A.fov;
  camera.position.set(...pos);
  camera.up.set(0, 1, 0);
  camera.lookAt(...look);
  camera.rotateZ(rad((shot.camera.roll_deg || 0) * glide(u / 0.4)));
  camera.updateProjectionMatrix();
}

function useSet(name) {
  if (!sets[name]) sets[name] = buildSet(name, data.story.seed);
  scene = new THREE.Scene();
  scene.add(sets[name]);
  scene.background = sets[name].userData.background;
}

const png = () => renderer.domElement.toDataURL("image/png");

window.setup = (d) => { data = d; hiddenByShot.clear(); for (const k of Object.keys(sets)) delete sets[k]; };

const placeAt = (a, u) => {
  const e = a.end_pos || a.start_pos;
  return [lerp(a.start_pos[0], e[0], u), lerp(a.start_pos[1], e[1], u)];
};

/** screen rect [x0, y0, x1, y1] (NDC) of world points */
function rect(points) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of points) {
    const q = p.clone().project(camera);
    x0 = Math.min(x0, q.x); y0 = Math.min(y0, q.y); x1 = Math.max(x1, q.x); y1 = Math.max(y1, q.y);
  }
  return [x0, y0, x1, y1];
}
const overlap = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];

/** prop pieces to hide for a non-wide shot: any whose screen box overlaps the subject's card (+ margin) at the
 *  shot's start, middle or end. Decided once per shot, so nothing pops in or out mid-shot. */
function hiddenFor(shot, subject, span) {
  if (hiddenByShot.has(shot.id)) return hiddenByShot.get(shot.id);
  const hidden = new Set(), pieces = sets[shot.set].userData.pieces;
  if (subject && shot.camera.angle !== "wide") {
    const bottom = -CARD_H * (1 - FEET_Y / CH);
    for (const u of [0, 0.5, 1]) {
      const [x, z] = placeAt(subject, u);
      shotCamera(shot, x, span, u);
      camera.updateMatrixWorld();
      const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).setY(0).normalize();
      const c = new THREE.Vector3(x, 0, z), pts = [];
      for (const sx of [-1, 1]) for (const y of [bottom, bottom + CARD_H]) {
        pts.push(c.clone().addScaledVector(right, (sx * CARD_W) / 2).setY(y));
      }
      const r = rect(pts), mx = (r[2] - r[0]) * SUBJECT_MARGIN, my = (r[3] - r[1]) * SUBJECT_MARGIN;
      const card = [r[0] - mx, r[1] - my, r[2] + mx, r[3] + my];
      for (const [id, pc] of pieces) {
        if (hidden.has(id)) continue;
        const { min, max } = pc.box, corners = [];
        for (const X of [min.x, max.x]) for (const Y of [min.y, max.y]) for (const Z of [min.z, max.z]) corners.push(new THREE.Vector3(X, Y, Z));
        if (overlap(card, rect(corners))) hidden.add(id);
      }
    }
  }
  hiddenByShot.set(shot.id, hidden);
  return hidden;
}

window.renderFrame = (n) => {
  const { story } = data;
  if (!(n >= 0 && n < story.duration_frames)) throw new Error(`frame ${n} outside 0..${story.duration_frames - 1}`);
  const shot = story.shots.find((s) => n >= s.start_frame && n < s.end_frame);
  const u = (n - shot.start_frame) / (shot.end_frame - shot.start_frame), t = n / FPS;
  useSet(shot.set);
  const place = (a) => placeAt(a, u);
  const subject = shot.actors.find((a) => a.action !== "idle") || shot.actors[0];
  const span = shot.actors.flatMap((a) => [a.start_pos[0], (a.end_pos || a.start_pos)[0]]);
  const hidden = hiddenFor(shot, subject, span);
  for (const [id, pc] of sets[shot.set].userData.pieces) for (const m of pc.meshes) m.visible = !hidden.has(id);
  shotCamera(shot, subject ? place(subject)[0] : 0, span, u);
  for (const a of shot.actors) {
    const [x, z] = place(a), key = charSeed(a.cast_id);
    const travelled = a.end_pos ? Math.hypot(a.end_pos[0] - a.start_pos[0], a.end_pos[1] - a.start_pos[1]) * u : 0;
    const phase = STRIDE[a.action] ? travelled / STRIDE[a.action] : 0;
    camera.updateMatrixWorld();
    const feet = new THREE.Vector3(x, 0, z).project(camera), head = new THREE.Vector3(x, FIG_H, z).project(camera);
    const px = (((head.y - feet.y) / 2) * H) / FIGURE_PX; // screen px per card canvas px
    const mesh = drawCard(a.cast_id, {
      boil: Math.floor(n / BOIL_FRAMES), action: a.action, expression: a.expression, facing: a.facing, t, phase, px,
      lid: lidAt(n, key),
      breath: Math.sin((2 * Math.PI * t) / 3.4 + 2 * Math.PI * rng(key, "breath")()),
      mouth: a.action === "talk" ? mouthAt(t, shot) : 0,
    });
    mesh.position.set(x, 0, z);
    mesh.rotation.set(0, Math.atan2(camera.position.x - x, camera.position.z - z), 0);
    // contact shadow: follows the feet, a little wider when the stride lowers the body
    const { shadow } = cards[a.cast_id], k = 1 + SHADOW.bounce * Math.abs(Math.sin(2 * Math.PI * phase));
    shadow.position.set(x, SHADOW.y, z);
    shadow.scale.set(SHADOW.w * k, 1, SHADOW.d * k);
    scene.add(mesh, shadow);
  }
  window.lastInfo = { angle: shot.camera.angle, hidden: hidden.size, ...measure(shot.actors.map(place)) };
  renderer.render(scene, camera);
  return png();
};

/** smallest figure height as a fraction of frame height, and whether every head, foot and card edge is in frame */
function measure(spots) {
  camera.updateMatrixWorld();
  let figure = 1, inFrame = true;
  for (const [x, z] of spots) {
    const feet = new THREE.Vector3(x, 0, z).project(camera), head = new THREE.Vector3(x, FIG_H, z).project(camera);
    figure = Math.min(figure, (head.y - feet.y) / 2);
    const half = (CARD_W / 2) * (head.y - feet.y) / FIG_H; // card half-width in NDC-ish units at that depth
    inFrame &&= feet.y >= -1 && head.y <= 1 && Math.abs(feet.x) + half * (H / W) <= 1;
  }
  return { figure, inFrame };
}

/** cast sheet image: one character on a plain background. pose: idle | walk | talk; expression for the face */
window.renderCast = ({ castId, pose, expression = "neutral" }) => {
  scene = new THREE.Scene();
  scene.background = new THREE.Color("#f4f1ea");
  const o = { boil: 0, lid: 0, breath: 0, mouth: 0, t: 0.3, phase: 0, action: "idle", facing: "camera", expression };
  if (pose === "walk") Object.assign(o, { action: "walk", facing: "right", phase: 0.25 });
  if (pose === "talk") Object.assign(o, { action: "talk", mouth: 0.8 });
  scene.add(drawCard(castId, o));
  cards[castId].mesh.position.set(0, 0, 0);
  cards[castId].mesh.rotation.set(0, 0, 0);
  camera.fov = 45;
  camera.position.set(0, 0.82, 2.6);
  camera.up.set(0, 1, 0);
  camera.lookAt(0, 0.8, 0);
  camera.updateProjectionMatrix();
  renderer.render(scene, camera);
  return png();
};

/** which WebGL implementation is drawing (SwiftShader vs the real GPU) */
window.glRenderer = () => {
  const gl = renderer.getContext(), ext = gl.getExtension("WEBGL_debug_renderer_info");
  return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
};

window.engineReady = true;
