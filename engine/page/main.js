// Frame renderer. Deterministic: frame n -> time n / FPS, every random value from rng(seed, keys).
// render.mjs calls setup(data) once, then renderFrame(n) or renderCast(pose) per image (PNG data URL back).
import * as THREE from "three";
import { dolly, glide } from "./borrowed.js";
import { CH, CW, FEET_Y, drawStickman } from "./stickman.js";
import { rng } from "./rng.js";
import { buildSet } from "./world.js";

const FPS = 30, W = 1080, H = 1920;
const CARD_H = 1.6, CARD_W = CARD_H * (CW / CH);
const BOIL_FRAMES = 4;                 // marker jitter changes every 4 frames (7.5 fps "boil")
const STRIDE = { walk: 1.0, run: 1.8 }; // world units per full walk cycle (two steps)
const LID = [0.5, 1, 1, 0.5];          // 4-frame blink: half, shut, shut, half
const rad = (d) => (d * Math.PI) / 180;
const lerp = (a, b, u) => a + (b - a) * u;

// base framing per angle, relative to the subject at (sx, 0, 0): camera offset, look point, fov, how much x follows
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
const sets = {}, cards = {};

function card(id) {
  if (!cards[id]) {
    const cv = document.createElement("canvas");
    cv.width = CW; cv.height = CH;
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    const mesh = new THREE.Mesh(CARD_GEO, new THREE.MeshBasicMaterial({ map: tex, transparent: true, alphaTest: 0.05, depthWrite: false }));
    cards[id] = { cv, tex, mesh };
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

function shotCamera(shot, sx, u) {
  const A = ANGLES[shot.camera.angle] || ANGLES.medium, fx = sx * A.follow;
  let pos = [fx + A.pos[0], A.pos[1], A.pos[2]], look = [fx + A.look[0], A.look[1], A.look[2]];
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

window.setup = (d) => { data = d; for (const k of Object.keys(sets)) delete sets[k]; };

window.renderFrame = (n) => {
  const { story } = data;
  if (!(n >= 0 && n < story.duration_frames)) throw new Error(`frame ${n} outside 0..${story.duration_frames - 1}`);
  const shot = story.shots.find((s) => n >= s.start_frame && n < s.end_frame);
  const u = (n - shot.start_frame) / (shot.end_frame - shot.start_frame), t = n / FPS;
  useSet(shot.set);
  const place = (a) => {
    const e = a.end_pos || a.start_pos;
    return [lerp(a.start_pos[0], e[0], u), lerp(a.start_pos[1], e[1], u)];
  };
  const subject = shot.actors.find((a) => a.action !== "idle") || shot.actors[0];
  shotCamera(shot, subject ? place(subject)[0] : 0, u);
  for (const a of shot.actors) {
    const [x, z] = place(a), key = charSeed(a.cast_id);
    const travelled = a.end_pos ? Math.hypot(a.end_pos[0] - a.start_pos[0], a.end_pos[1] - a.start_pos[1]) * u : 0;
    const mesh = drawCard(a.cast_id, {
      boil: Math.floor(n / BOIL_FRAMES), action: a.action, expression: a.expression, facing: a.facing, t,
      phase: STRIDE[a.action] ? travelled / STRIDE[a.action] : 0,
      lid: lidAt(n, key),
      breath: Math.sin((2 * Math.PI * t) / 3.4 + 2 * Math.PI * rng(key, "breath")()),
      mouth: a.action === "talk" ? mouthAt(t, shot) : 0,
    });
    mesh.position.set(x, 0, z);
    mesh.rotation.set(0, Math.atan2(camera.position.x - x, camera.position.z - z), 0);
    scene.add(mesh);
  }
  renderer.render(scene, camera);
  return png();
};

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

window.engineReady = true;
