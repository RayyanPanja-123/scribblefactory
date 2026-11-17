// Frame renderer. Deterministic: frame n -> time n / FPS, every random value from rng(seed, keys).
// render.mjs calls setup(data) once, then renderFrame(n) or renderCast(pose) per image (PNG data URL back).
import * as THREE from "three";
import { dolly, glide } from "./borrowed.js";
import { CH, CW, FEET_Y, FIGURE_PX, drawStickman } from "./stickman.js";
import { DH, DOG_FEET, DW, barkAmount, drawDog, gallopPhase } from "./dog.js";
import { gestureAmount, gesturePlan, mouthCurve, mouthCycles, pointAmount, stressBob, waveAmount } from "./motion.js";
import { CAR_CARD_W, CAR_GROUND, DRIVER_X, RIDER_X, VH, VW, carEase, carSpeedShare, drawCar, seatOffset } from "./car.js";
import { rng, setVariant } from "./rng.js";
import { SETS, VARIANTS, buildSet, loopExcess, scrollSet } from "./world.js";

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
const CAR_CARD_H = CAR_CARD_W * (VH / VW), CAR_SHADOW = { w: 2.6, d: 0.55 }, CAR_HALF = 1.4;
const DUST_SETS = new Set(["dirt_road"]); // sets with a dirt ground: moving cars kick up dust
const DRIVER = { outfit_color: "#8a8a8a", eyes: "dots" }; // generic extra, not cast
const DOG_CARD_W = 1.3, DOG_CARD_H = DOG_CARD_W * (DH / DW), DOG_SHADOW = { w: 0.9, d: 0.26 };
// set change: a marker stroke sweeps left to right over the last HALF frames of the old shot and the first HALF of
// the new one, revealing the new set. band = stroke width px, tilt = how far the bottom trails the top px.
const WIPE = { half: 5, band: 110, tilt: 260, color: "#f2c14e", streak: "#d99a2b", ink: "#1c1a1a" };

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
const CAR_GEO = new THREE.PlaneGeometry(CAR_CARD_W, CAR_CARD_H).translate(0, CAR_CARD_H / 2 - CAR_CARD_H * (1 - CAR_GROUND / VH), 0);
const DOG_GEO = new THREE.PlaneGeometry(DOG_CARD_W, DOG_CARD_H).translate(0, DOG_CARD_H / 2 - DOG_CARD_H * (1 - DOG_FEET / DH), 0);

let data = null, scene = null;
const sets = {}, cards = {}, hiddenByShot = new Map(), variantByShot = new Map();
const comp = Object.assign(document.createElement("canvas"), { width: W, height: H }); // wipe composite
const cg = comp.getContext("2d");

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

function card(id, geo = CARD_GEO, w = CW, h = CH) {
  if (!cards[id]) {
    const cv = document.createElement("canvas");
    cv.width = w; cv.height = h;
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: tex, transparent: true, alphaTest: 0.05, depthWrite: false }));
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

function shotWords(shot) {
  const ph = data.phrases.phrases, [a, b] = shot.phrase_range;
  return data.phrases.words.slice(ph[a].word_start, ph[b].word_end + 1);
}

let mouth = new Float32Array(0); // per-frame mouth opening for the whole part (motion.js), built in setup

/** drawStickman options for cast member id (look from series.json), merged over the per-frame options o */
function figure(id, o) {
  const cast = castOf(id);
  return { seed: charSeed(id), color: cast.outfit_color, eyes: cast.eyes, ...o };
}

function drawCard(id, o) {
  const c = card(id);
  drawStickman(c.cv, figure(id, o));
  c.tex.needsUpdate = true;
  return c.mesh;
}

/** xs: x of every actor at the start and end of the shot. Wide centres on all of them and backs off until the
 *  whole cast fits for the entire shot, including where the move ends (push-in reach, truck shift). */
function shotCamera(shot, sx, xs, u) {
  const A = ANGLES[shot.camera.angle] || ANGLES.medium;
  let pos, look;
  // chase (travel shot with dogs): every angle fits actors + pack like wide, at the angle's own camera height
  // a car pulling up / parked / leaving likewise frames the cast and where the car stands
  const wide = shot.camera.angle === "wide", chase = !!(shot.travel && shot.animals?.length)
    || !!(!shot.travel && shot.vehicles?.length);
  if ((wide || chase) && xs.length) {
    const lo = Math.min(...xs), hi = Math.max(...xs), cx = (lo + hi) / 2;
    const end = shot.camera.speed, tan = Math.tan(rad(A.fov / 2)); // end = move size at u = 1
    const width = hi - lo + WIDE.margin + (shot.camera.move.startsWith("truck") ? 2 * 1.4 * end : 0);
    const reach = shot.camera.move === "push_in" ? 1 - 0.5 * end : 1;
    const fit = width / (2 * tan * (W / H)) / reach;   // whole cast inside the frame edges all shot long
    const notCloser = FIG_H / (2 * tan * WIDE.maxFill); // heads and feet win over size: only ever back off
    pos = [cx, wide ? WIDE.camY : A.pos[1], Math.max(fit, notCloser)]; look = [cx, wide ? WIDE.lookY : A.look[1], 0];
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

/** the shot's set group (its prop variant is fixed for the whole run of shots on that set) in a fresh scene */
function useSet(shot) {
  const v = variantByShot.get(shot.id) ?? 0, key = `${shot.set}:${v}`;
  if (!sets[key]) sets[key] = buildSet(shot.set, data.story.seed, v);
  scene = new THREE.Scene();
  scene.add(sets[key]);
  scene.background = sets[key].userData.background;
  scene.fog = sets[key].userData.fog || null;
  return sets[key];
}

const png = () => renderer.domElement.toDataURL("image/png");

window.setup = (d) => {
  data = d; hiddenByShot.clear(); variantByShot.clear();
  mouth = d.phrases ? mouthCurve(mouthCycles(d.phrases.words, d.phrases.phrases), d.story.duration_frames) : mouth;
  for (const k of Object.keys(sets)) delete sets[k];
  let runStart = null; // variant = hash(set, first shot id of the run): props never jump between cuts on one set
  (d.story.shots || []).forEach((s, i, all) => {
    if (i === 0 || all[i - 1].set !== s.set) runStart = s.id;
    variantByShot.set(s.id, setVariant(s.set, runStart, VARIANTS[s.set] || 1));
  });
};

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
function hiddenFor(shot, subject, span, group) {
  if (hiddenByShot.has(shot.id)) return hiddenByShot.get(shot.id);
  const hidden = new Set(), pieces = group.userData.pieces;
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

/** set-change wipe covering frame n of shot i, or null: { from, to, p } with p in (0, 1], 1 = new set fully shown */
function wipeAt(i, n) {
  const sh = data.story.shots, s = sh[i];
  let from, to;
  if (sh[i + 1] && sh[i + 1].set !== s.set && s.end_frame - n <= WIPE.half) [from, to] = [s, sh[i + 1]];
  else if (sh[i - 1] && sh[i - 1].set !== s.set && n - s.start_frame < WIPE.half) [from, to] = [sh[i - 1], s];
  else return null;
  return { from, to, p: (n - (to.start_frame - WIPE.half) + 1) / (2 * WIPE.half) };
}

/** marker stroke edge: x per y sample for this wipe, ragged but the same shape on every frame of it */
function strokeEdge(w) {
  const R = rng(data.story.seed, "wipe", w.to.id), a = R() * 6.28, b = R() * 6.28, pts = [];
  const M = WIPE.tilt / 2 + WIPE.band / 2 + 70, lead = -M + w.p * (W + 2 * M); // p 0 / 1: stroke fully off left / right
  for (let y = -40; y <= H + 40; y += 32) {
    const v = y / H;
    pts.push([lead + WIPE.tilt * (0.5 - v) + 34 * Math.sin(6 * v + a) + 18 * Math.sin(17 * v + b) + R() * 10, y]);
  }
  return pts;
}

/** both sets: old shot in the WebGL canvas -> composite, then the new shot revealed left of the stroke */
function composite(w, n) {
  drawShot(w.from, n);
  cg.drawImage(canvas, 0, 0);
  const info = drawShot(w.to, n);
  const pts = strokeEdge(w), line = (dx) => { cg.beginPath(); pts.forEach(([x, y], k) => (k ? cg.lineTo(x + dx, y) : cg.moveTo(x + dx, y))); };
  cg.save();
  line(0); cg.lineTo(-10, H + 50); cg.lineTo(-10, -50); cg.closePath(); cg.clip();
  cg.drawImage(canvas, 0, 0);
  cg.restore();
  cg.lineCap = cg.lineJoin = "round";
  line(0); cg.strokeStyle = WIPE.color; cg.lineWidth = WIPE.band; cg.stroke();
  for (const [dx, lw] of [[-38, 7], [-14, 4], [12, 6], [33, 3]]) { line(dx); cg.strokeStyle = WIPE.streak; cg.lineWidth = lw; cg.stroke(); }
  for (const dx of [-WIPE.band / 2, WIPE.band / 2]) { line(dx); cg.strokeStyle = WIPE.ink; cg.lineWidth = 6; cg.stroke(); }
  return info;
}

window.renderFrame = (n) => {
  const { story } = data;
  if (!(n >= 0 && n < story.duration_frames)) throw new Error(`frame ${n} outside 0..${story.duration_frames - 1}`);
  const i = story.shots.findIndex((s) => n >= s.start_frame && n < s.end_frame), w = wipeAt(i, n);
  if (!w) {
    window.lastInfo = drawShot(story.shots[i], n);
    return png();
  }
  const info = composite(w, n);
  window.lastInfo = { ...info, wipe: `${w.from.set}->${w.to.set} ${Math.round(w.p * 100)}%` };
  return comp.toDataURL("image/png");
};

/** render shot at frame n into the WebGL canvas. n may sit up to WIPE.half frames outside the shot (wipe): shot
 *  motion (actors, camera) holds at the shot's edge, while boil, blink and breath keep running on n. */
function drawShot(shot, n) {
  const kf = Math.min(Math.max(n, shot.start_frame), shot.end_frame - 1); // held frame for shot motion
  const u = (kf - shot.start_frame) / (shot.end_frame - shot.start_frame), t = n / FPS;
  const group = useSet(shot);
  const animals = shot.animals || [], vehicles = shot.vehicles || [];
  // riders sit in their car's seats: their spot is the car's spot plus the seat offset
  const seated = new Map();
  for (const v of vehicles) {
    const [cx, cz] = carAt(v, u), sgn = v.facing === "left" ? -1 : 1;
    v.riders.forEach((r, i) => seated.set(r, [cx + sgn * seatOffset(RIDER_X[i]), cz]));
  }
  const place = (a) => seated.get(a.cast_id) || placeAt(a, u);
  const subject = shot.actors.find((a) => a.action !== "idle") || shot.actors[0];
  const span = [...shot.actors.filter((a) => !seated.has(a.cast_id)), ...animals]
    .flatMap((a) => [a.start_pos[0], (a.end_pos || a.start_pos)[0]]);
  for (const v of vehicles) { // where the car stands: arrive its stop, leave its start, else both ends
    const xs = v.action === "arrive" ? [(v.end_pos || v.start_pos)[0]] : v.action === "leave" ? [v.start_pos[0]]
      : [v.start_pos[0], (v.end_pos || v.start_pos)[0]];
    for (const x of xs) span.push(x - CAR_HALF, x + CAR_HALF);
  }
  // travel shot: the world scrolls against the car's (else the actors') facing at travel.speed; props wrap around
  // the band and the near ones are hidden (not hidden-behind-subject: everything moves, so that choice would be stale)
  const dir = shot.travel ? ((vehicles[0] || shot.actors[0])?.facing === "left" ? -1 : 1) : 0;
  const shift = shot.travel ? -dir * shot.travel.speed * ((kf - shot.start_frame) / FPS) : 0;
  const travelHidden = scrollSet(group, shift, !!shot.travel);
  const hidden = shot.travel ? travelHidden : hiddenFor(shot, subject, span, group);
  for (const [id, pc] of group.userData.pieces) for (const m of pc.meshes) m.visible = !hidden.has(id);
  shotCamera(shot, subject ? place(subject)[0] : 0, span, u);
  const gestures = [], riders = new Map(); // riders: cast id -> drawStickman options, drawn inside the car card
  for (const a of shot.actors) {
    const [x, z] = place(a), key = charSeed(a.cast_id);
    const own = a.end_pos ? Math.hypot(a.end_pos[0] - a.start_pos[0], a.end_pos[1] - a.start_pos[1]) : 0;
    const shotLen = (shot.end_frame - shot.start_frame) / FPS;
    const travelled = ((shot.travel ? shot.travel.speed * shotLen : 0) + own) * u; // effective stride distance
    const phase = STRIDE[a.action] ? travelled / STRIDE[a.action] : 0;
    const ts = (kf - shot.start_frame) / FPS, shotSecs = (shot.end_frame - shot.start_frame) / FPS;
    const plan = gesturePlan(data.story.seed, shot.id, a.cast_id, a.action, shotSecs);
    const gesture = plan ? { kind: plan.kind, k: gestureAmount(plan, ts) } : null;
    if (gesture?.k > 0) gestures.push(`${a.cast_id} ${gesture.kind}`);
    camera.updateMatrixWorld();
    const feet = new THREE.Vector3(x, 0, z).project(camera), head = new THREE.Vector3(x, FIG_H, z).project(camera);
    const px = (((head.y - feet.y) / 2) * H) / FIGURE_PX; // screen px per card canvas px
    const o = {
      boil: Math.floor(n / BOIL_FRAMES), action: a.action, expression: a.expression, facing: a.facing, t, phase, px,
      lid: lidAt(n, key),
      breath: Math.sin((2 * Math.PI * t) / 3.4 + 2 * Math.PI * rng(key, "breath")()),
      mouth: a.action === "talk" && n === kf ? mouth[n] : 0, // shut while drawn outside its shot (wipe)
      bob: a.action === "talk" && !seated.has(a.cast_id) ? stressBob(t, shotWords(shot)) : 0,
      gesture, pointK: a.action === "point" ? pointAmount(ts) : 1,
      wave: a.action === "wave" ? waveAmount(ts) : null,
    };
    if (seated.has(a.cast_id)) { riders.set(a.cast_id, figure(a.cast_id, o)); continue; }
    const mesh = drawCard(a.cast_id, o);
    mesh.position.set(x, 0, z);
    mesh.rotation.set(0, Math.atan2(camera.position.x - x, camera.position.z - z), 0);
    // contact shadow: follows the feet, a little wider when the stride lowers the body
    const { shadow } = cards[a.cast_id], k = 1 + SHADOW.bounce * Math.abs(Math.sin(2 * Math.PI * phase));
    shadow.position.set(x, SHADOW.y, z);
    shadow.scale.set(SHADOW.w * k, 1, SHADOW.d * k);
    scene.add(mesh, shadow);
  }
  drawAnimals(shot, animals, n, kf, u);
  const cars = drawVehicles(shot, vehicles, riders, n, u);
  renderer.render(scene, camera);
  const travel = shot.travel ? { travel: `${shot.travel.speed} u/s ${dir < 0 ? "left" : "right"}, shift ${shift.toFixed(2)}`
    + `, loop excess ${(({ excess, row }) => `${excess.toFixed(3)} (row z ${row})`)(loopExcess(group, shift))}` } : {};
  return { angle: shot.camera.angle, hidden: hidden.size, gestures, dogs: animals.length, ...cars, ...travel,
    ...measure(shot.actors.filter((a) => !seated.has(a.cast_id)).map(place)) };
}

/** dog cards: gallop phase from distance travelled (scroll + own move), barks start at the shot's bark cue */
function drawAnimals(shot, animals, n, kf, u) {
  const t = n / FPS, secs = (shot.end_frame - shot.start_frame) / FPS;
  const cue = (data.story.cues || []).find((c) => c.kind === "bark" && c.frame >= shot.start_frame && c.frame < shot.end_frame);
  const barkers = animals.filter((d) => d.action === "bark");
  for (const d of animals) {
    const [x, z] = placeAt(d, u), key = charSeed(`dog:${d.id}`), id = `animal:${d.id}`;
    const own = d.end_pos ? Math.hypot(d.end_pos[0] - d.start_pos[0], d.end_pos[1] - d.start_pos[1]) : 0;
    const phase = d.action === "run" ? gallopPhase(((shot.travel ? shot.travel.speed * secs : 0) + own) * u) : 0;
    const c = card(id, DOG_GEO, DW, DH);
    drawDog(c.cv, {
      seed: key, variant: d.variant, facing: d.facing, action: d.action, phase, t,
      boil: Math.floor(n / BOIL_FRAMES), lid: lidAt(n, key),
      breath: Math.sin((2 * Math.PI * t) / 1.1 + 2 * Math.PI * rng(key, "breath")()), // dogs pant faster
      yap: d.action === "bark" && n === kf ? barkAmount(n, cue ? cue.frame : shot.start_frame, barkers.indexOf(d)) : 0,
    });
    c.tex.needsUpdate = true;
    c.mesh.position.set(x, 0, z);
    c.mesh.rotation.set(0, Math.atan2(camera.position.x - x, camera.position.z - z), 0);
    const k = 1 + SHADOW.bounce * Math.abs(Math.sin(2 * Math.PI * phase));
    c.shadow.position.set(x, SHADOW.y, z);
    c.shadow.scale.set(DOG_SHADOW.w * k, 1, DOG_SHADOW.d * k);
    scene.add(c.mesh, c.shadow);
  }
}

/** car position at shot fraction u: arrive eases to a stop, leave eases out from one, idle stays */
function carAt(v, u) {
  const e = v.end_pos || v.start_pos, k = carEase(v.action, u);
  return [lerp(v.start_pos[0], e[0], k), lerp(v.start_pos[1], e[1], k)];
}

/** car cards with the driver (generic grey extra) and seated riders; wheels turn by the distance driven */
function drawVehicles(shot, vehicles, riders, n, u) {
  const t = n / FPS, secs = (shot.end_frame - shot.start_frame) / FPS, info = [];
  for (const v of vehicles) {
    const [x, z] = carAt(v, u), key = charSeed(`car:${v.id}`), id = `vehicle:${v.id}`;
    const e = v.end_pos || v.start_pos, own = Math.hypot(e[0] - v.start_pos[0], e[1] - v.start_pos[1]);
    const scroll = shot.travel ? shot.travel.speed : 0;
    const distance = scroll * secs * u + own * carEase(v.action, u);
    const speed = scroll + (own / secs) * carSpeedShare(v.action, u); // units/s right now
    const dk = `${key}:driver`;
    const driver = { seed: dk, color: DRIVER.outfit_color, eyes: DRIVER.eyes, action: "idle", expression: "neutral",
      boil: Math.floor(n / BOIL_FRAMES), lid: lidAt(n, dk), t, px: 1,
      breath: Math.sin((2 * Math.PI * t) / 3.4 + 2 * Math.PI * rng(dk, "breath")()) };
    const c = card(id, CAR_GEO, VW, VH);
    drawCar(c.cv, {
      seed: key, variant: v.variant, facing: v.facing, boil: Math.floor(n / BOIL_FRAMES), distance,
      moving: speed > 0.05, dust: DUST_SETS.has(shot.set) ? Math.min(1, speed / 4) : 0,
      driver, riders: v.riders.map((r) => riders.get(r)).filter(Boolean),
    });
    c.tex.needsUpdate = true;
    c.mesh.position.set(x, 0, z);
    c.mesh.rotation.set(0, Math.atan2(camera.position.x - x, camera.position.z - z), 0);
    c.shadow.position.set(x, SHADOW.y, z);
    c.shadow.scale.set(CAR_SHADOW.w, 1, CAR_SHADOW.d);
    scene.add(c.mesh, c.shadow);
    info.push(`${v.id} ${v.action}${v.riders.length ? ` (${v.riders.join(", ")})` : ""} x ${x.toFixed(2)}`);
  }
  return info.length ? { cars: info.join("; ") } : {};
}

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

/** which WebGL implementation is drawing (SwiftShader vs the real GPU): vendor, renderer, GL version strings */
window.glInfo = () => {
  const gl = renderer.getContext(), ext = gl.getExtension("WEBGL_debug_renderer_info");
  return {
    vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
    renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
    version: gl.getParameter(gl.VERSION),
  };
};

/** geometry-only check, no rendering: build every set and variant (buildSet throws on a stage-clearance break) and
 *  sweep the world shift across the whole band; per set/variant/seed the worst loop excess (see world.loopExcess) */
window.loopCheck = ({ seeds = [0, 687360865], steps = 120 } = {}) => {
  const out = [];
  for (const seed of seeds) for (const set of SETS) for (let variant = 0; variant < (VARIANTS[set] || 1); variant++) {
    const g = buildSet(set, seed, variant);
    let worst = { excess: -Infinity, row: "none" };
    for (let k = 0; k < steps; k++) { // 0.237-unit steps: no layout period divides them, ~1.0 band sweep
      const r = loopExcess(g, 0.01 + k * 0.237);
      if (r.excess > worst.excess) worst = r;
    }
    out.push({ set, variant, seed, ...worst });
  }
  return out;
};

window.engineReady = true;
