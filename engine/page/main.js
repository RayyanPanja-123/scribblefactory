// Frame renderer. Deterministic: frame n -> time n / FPS, every random value from rng(seed, keys).
// render.mjs calls setup(data) once, then renderFrame(n) or renderCast(pose) per image (PNG data URL back).
import * as THREE from "three";
import { dolly, glide } from "./borrowed.js";
import { BODY_W, CH, CW, FEET_Y, FIGURE_PX, HAT_TOP, HEAD_R, drawStickman, figurePx, skeleton } from "./stickman.js";
import { CRW, creature, drawCreature, measure as creatureSize } from "./creatures.js";
import { lookup, setLibrary } from "./library.js";
import { DH, DOG_FEET, DW, barkAmount, drawDog, gallopPhase } from "./dog.js";
import { gestureAmount, gesturePlan, mouthCurve, mouthCycles, pointAmount, stressBob, waveAmount } from "./motion.js";
import { BUILTIN_ACTIONS, CARRIED_LIFT, HELD_Z, HOLD_GAP, LIE, collapseAt, customPose, eatAt, gaitPhase, giveAt, handOf, heldPlace,
  propsByShot, sideToward, staggerAt, withProp, zzzAt } from "./actions.js";
import { CAR_CARD_W, CAR_GROUND, DRIVER_X, RIDER_X, VH, VW, carEase, carSpeedShare, drawCar, seatOffset } from "./car.js";
import { HEAD_GROW, MOOD_EXPRESSION, extraLook, fitCrowd, moodAt, placeExtras } from "./extras.js";
const growRect = (r, k) => { const mx = (r[2] - r[0]) * k, my = (r[3] - r[1]) * k; return [r[0] - mx, r[1] - my, r[2] + mx, r[3] + my]; };
import { rng, setVariant } from "./rng.js";
import { SETS, VARIANTS, buildSet, loopExcess, scrollSet, setKind } from "./world.js";
import { fadePlan, fogAlpha, fogCanvas, layersAt, paint, strikeAt } from "./weather.js";

const FPS = 30, W = 1080, H = 1920;
const CARD_H = 1.6, CARD_W = CARD_H * (CW / CH); // the whole canvas, held props included
const BODY_CARD_W = CARD_H * (BODY_W / CH);       // just the figure: what framing and set-prop hiding measure
const FIG_H = (CARD_H * FIGURE_PX) / CH; // tallest standing figure in world units, from stickman.js
const BOIL_FRAMES = 4;                 // marker jitter changes every 4 frames (7.5 fps "boil")
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
// weather (weather.js): fog bands are planes behind the cast; rain, snow, wind, tint, flashes and lightning are a 2D
// overlay drawn over the rendered frame by a second, flat pass
const wcv = Object.assign(document.createElement("canvas"), { width: W, height: H }), wg = wcv.getContext("2d");
const wtex = new THREE.CanvasTexture(wcv);
wtex.colorSpace = THREE.SRGBColorSpace;
const overlay = new THREE.Scene().add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2),
  new THREE.MeshBasicMaterial({ map: wtex, transparent: true, depthTest: false, depthWrite: false })));
const flatCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
const FOG = { z: -1.05, y: 1.5, w: 40, h: 3.2, tile: 8 }; // behind the front row and back row (z -0.9), before the crowd
let fogTex = null, fadeByShot = new Map();
const fogMeshes = [];
const sets = {}, cards = {}, hiddenByShot = new Map(), variantByShot = new Map(), extrasByShot = new Map();
let ownedProps = new Map(); // shot id -> { cast id: props held at the shot's start } (give hands props on)
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

const NO_COSTUME = { headwear: { kind: "none" }, legwear: { kind: "none" }, props: [], default_expression: "neutral" };
/** cast entry with every v3 field; older files read the same as the pipeline migrates them: a v1 entry
 *  (outfit_color) is a plain top in that colour, a v2 single prop becomes the props list */
const castOf = (id, look) => {
  const c = data.series.cast.find((c) => c.id === id) || { id, outfit_color: "#888888", eyes: "dots" };
  const props = c.props || (c.prop && c.prop.kind !== "none" ? [c.prop] : []);
  const base = { ...NO_COSTUME, top: { style: "plain", color: c.outfit_color }, ...c, props };
  // a named look (@look) replaces only the fields it sets
  const L = look && c.looks?.[look];
  return L ? { ...base, ...Object.fromEntries(Object.entries(L).filter(([, v]) => v != null)) } : base;
};
/** story expression "neutral" means the cast member's default expression (in its current look) */
const expressionOf = (id, e, look) => (!e || e === "neutral" ? castOf(id, look).default_expression : e);
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
  const cast = castOf(id, o.look);
  const { top, headwear, legwear, props, eyes, headless = false, hair, facial_hair, footwear, back, accessory, face } = cast;
  return { seed: charSeed(id), color: top.color, top, headwear, legwear, props, eyes, headless,
    hair, facial_hair, footwear, back, accessory, face, // wardrobe slots (wardrobe.js); a look's "none" takes one off
    creature: creatureOf(id), build: bodyOf(id).build, ...o };
}

/** the cast member's body definition (creatures.js): every cast member has one, default human. A legacy "stickman"
 *  body is the human. */
const bodyOf = (id) => { const b = castOf(id).body; return creature(!b || b === "stickman" ? "human" : b); };
/** the cast member's drawn creature (creatures.js drawCreature), or null for a humanoid (drawStickman with its build) */
const creatureOf = (id) => { const d = bodyOf(id); return d.rig === "humanoid" ? null : d; };
/** a creature that sits down for lie / collapse (every rig but biped, which lies down like a stickman) */
const sits = (id) => creatureOf(id)?.rig !== undefined && creatureOf(id).rig !== "biped";
/** world units a non-wide camera comes down to frame a subject shorter than the default human at its own height */
const creatureDrop = (id) => {
  const d = creatureOf(id), top = d ? creatureSize(d).top : figurePx(bodyOf(id).build);
  return Math.max(0, (CARD_H * (FIGURE_PX - top)) / CH * 0.85);
};
const CREATURE_GEO = new THREE.PlaneGeometry(CARD_W * (CRW / CW), CARD_H).translate(0, CARD_H / 2 - CARD_H * (1 - FEET_Y / CH), 0);

function drawCard(id, o) {
  const d = creatureOf(id), c = d ? card(id, CREATURE_GEO, CRW, CH) : card(id);
  if (d) drawCreature(c.cv, d, figure(id, o)); else drawStickman(c.cv, figure(id, o));
  c.tex.needsUpdate = true;
  return c.mesh;
}

/** xs: x of every actor at the start and end of the shot. Wide centres on all of them and backs off until the
 *  whole cast fits for the entire shot, including where the move ends (push-in reach, truck shift). */
function shotCamera(shot, sx, xs, u, drop = 0) {
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
  // a lying subject: the framing comes down with it (drop: world units, 0 standing)
  if (drop) { pos[1] = Math.max(0.3, pos[1] - drop); look[1] -= drop; }
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
  data = d; hiddenByShot.clear(); variantByShot.clear(); extrasByShot.clear();
  fadeByShot = fadePlan(d.story.shots || []);
  fogTex?.dispose(); fogTex = null;
  setLibrary(d); // library/{props,sets,creatures,actions}.json: every custom item, one registry (library.js)
  ownedProps = propsByShot(d.story.shots || [], Object.fromEntries((d.series.cast || []).map((c) => [c.id, castOf(c.id).props])),
    (id, look) => castOf(id, look).props);
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
        pts.push(c.clone().addScaledVector(right, (sx * BODY_CARD_W) / 2).setY(y));
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
  const place = (a) => seated.get(a.cast_id) || heldPlace(a, shot.actors, placeAt, u) || placeAt(a, u);
  const owned = ownedProps.get(shot.id) || {}, wide = shot.camera.angle === "wide";
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
  // a give / receive is framed on the pair's midpoint, so neither the giver nor the receiver is cut off
  const pair = subject && (subject.action === "give" || subject.action === "receive")
    ? shot.actors.find((b) => b.cast_id === subject.target) : null;
  const focusX = (pl) => (pair ? (pl(subject)[0] + pl(pair)[0]) / 2 : pl(subject)[0]);
  const drop = (kk) => (subject ? Math.max(LIE.drop * lying(subject, kk, shot), wide || seated.has(subject.cast_id) ? 0 : creatureDrop(subject.cast_id)) : 0);
  const camAt = (uu) => shotCamera(shot, subject ? focusX((a) => placeAt2(a, uu)) : 0, span, uu,
    drop(shot.start_frame + uu * (shot.end_frame - shot.start_frame - 1)));
  const placeAt2 = (a, uu) => seated.get(a.cast_id) || heldPlace(a, shot.actors, placeAt, uu) || placeAt(a, uu);
  const extraShift = extrasFor(shot, camAt, placeAt2);
  shotCamera(shot, subject ? focusX(place) : 0, span, u, drop(kf));
  const gestures = [], riders = new Map(); // riders: cast id -> drawStickman options, drawn inside the car card
  const ownMove = (a) => (a.end_pos ? Math.hypot(a.end_pos[0] - a.start_pos[0], a.end_pos[1] - a.start_pos[1]) : 0);
  for (const a of shot.actors) {
    const [x, z] = place(a), key = charSeed(a.cast_id);
    // carried / supported move with their holders: their stride distance is the holders' move
    const holder = shot.actors.find((h) => h.target === a.cast_id && (h.action === "carry" || h.action === "support"));
    const own = holder && (a.action === "carried" || a.action === "supported") ? ownMove(holder) : ownMove(a);
    const shotLen = (shot.end_frame - shot.start_frame) / FPS;
    const travelled = ((shot.travel ? shot.travel.speed * shotLen : 0) + own) * u; // effective stride distance
    const ts = (kf - shot.start_frame) / FPS, shotSecs = (shot.end_frame - shot.start_frame) / FPS;
    const phase = gaitPhase(a.action, travelled, ts);
    const plan = gesturePlan(data.story.seed, shot.id, a.cast_id, a.action, shotSecs);
    const gesture = plan ? { kind: plan.kind, k: gestureAmount(plan, ts) } : null;
    if (gesture?.k > 0) gestures.push(`${a.cast_id} ${gesture.kind}`);
    camera.updateMatrixWorld();
    const feet = new THREE.Vector3(x, 0, z).project(camera), head = new THREE.Vector3(x, FIG_H, z).project(camera);
    const px = (((head.y - feet.y) / 2) * H) / FIGURE_PX; // screen px per card canvas px
    const o = {
      boil: Math.floor(n / BOIL_FRAMES), action: a.action, expression: expressionOf(a.cast_id, a.expression, a.look), facing: a.facing, t, phase, px, look: a.look,
      lid: lidAt(n, key),
      breath: Math.sin((2 * Math.PI * t) / 3.4 + 2 * Math.PI * rng(key, "breath")()),
      mouth: a.action === "talk" && n === kf ? mouth[n] : 0, // shut while drawn outside its shot (wipe)
      bob: a.action === "talk" && !seated.has(a.cast_id) ? stressBob(t, shotWords(shot)) : 0,
      gesture, pointK: a.action === "point" ? pointAmount(ts) : 1,
      wave: a.action === "wave" ? waveAmount(ts) : null,
      props: owned[a.cast_id] || castOf(a.cast_id, a.look).props,
    };
    const roll = actionPose(shot, a, o, x, u, ts, n);
    if (seated.has(a.cast_id)) { riders.set(a.cast_id, figure(a.cast_id, o)); continue; }
    const mesh = drawCard(a.cast_id, o), yaw = Math.atan2(camera.position.x - x, camera.position.z - z);
    // lying (lie, the end of a collapse): the card rolls 90 degrees about the feet in its own plane and lifts so the
    // body rests on the floor; carried: lifted clear of the ground
    // the lying body is centred on the actor's spot (feet half a figure one way, head the other), so it stays in
    // frame and clear of its neighbours as far as it can
    const reach = roll.k * (FIG_H / 2), hx = -roll.sign * reach * Math.cos(yaw), hz = roll.sign * reach * Math.sin(yaw);
    const hop = o.mood ? MOOD_HOP * o.mood.bounce : 0; // cheering bounces
    mesh.position.set(x - hx, a.action === "carried" ? CARRIED_LIFT : LIE.lift * roll.k + hop, z - hz);
    mesh.rotation.set(0, yaw, roll.sign * roll.k * Math.PI / 2);
    // contact shadow: follows the feet, a little wider when the stride lowers the body; under a lying body it
    // stretches along it
    const { shadow } = cards[a.cast_id], k = 1 + SHADOW.bounce * Math.abs(Math.sin(2 * Math.PI * phase));
    shadow.position.set(x, SHADOW.y, z);
    shadow.scale.set(SHADOW.w * k * (1 + 1.3 * roll.k) * (a.action === "carried" ? 0.7 : 1), 1, SHADOW.d * k);
    scene.add(mesh, shadow);
  }
  drawAnimals(shot, animals, n, kf, u);
  const extras = drawExtras(shot, n, kf, u, extraShift);
  const cars = drawVehicles(shot, vehicles, riders, n, u);
  const layers = layersAt(shot, fadeByShot.get(shot.id), n);
  drawFog(layers, t, shift);
  renderer.render(scene, camera);
  const weather = drawWeather(shot, layers, n, t, place);
  const travel = shot.travel ? { travel: `${shot.travel.speed} u/s ${dir < 0 ? "left" : "right"}, shift ${shift.toFixed(2)}`
    + `, loop excess ${(({ excess, row }) => `${excess.toFixed(3)} (row z ${row})`)(loopExcess(group, shift))}` } : {};
  return { angle: shot.camera.angle, hidden: hidden.size, gestures, dogs: animals.length, ...extras, ...cars, ...travel, ...weather,
    ...measure(shot.actors.filter((a) => !seated.has(a.cast_id)).map(place)) };
}

/** fog layers: a hatched band plane per layer, behind the cast, drifting slowly (and with a travel shot's scroll) */
function drawFog(layers, t, shift) {
  layers.filter((l) => fogAlpha(l.weather)).forEach((l, i) => {
    if (!fogTex) {
      fogTex = new THREE.CanvasTexture(fogCanvas(data.story.seed));
      fogTex.colorSpace = THREE.SRGBColorSpace;
      fogTex.wrapS = THREE.RepeatWrapping;
      fogTex.repeat.set(FOG.w / FOG.tile / 2, 1); // one canvas tile is two FOG.tile wide
    }
    fogMeshes[i] ??= new THREE.Mesh(new THREE.PlaneGeometry(FOG.w, FOG.h),
      new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false }));
    const m = fogMeshes[i];
    m.material.map = fogTex; m.material.opacity = fogAlpha(l.weather, l.amount); m.material.needsUpdate = true;
    fogTex.offset.x = t * 0.012 - shift / (2 * FOG.tile);
    m.position.set(camera.position.x, FOG.y, FOG.z);
    m.renderOrder = 0.5; // over the set, under the cards
    scene.add(m);
  });
}

/** the 2D weather overlay over the frame just rendered; a strike lands beside its target (else behind the stage) */
function drawWeather(shot, layers, n, t, place) {
  const strikes = data.story.lightning || [];
  const live = strikeAt(strikes, n)?.strike;
  if (!layers.length && !live) return { weather: "clear" };
  let target = null;
  if (live) {
    const a = live.target && shot.actors.find((x) => x.cast_id === live.target);
    const [x, z] = a ? place(a) : [(rng(data.story.seed, "strike", live.frame)() - 0.5) * 3.2, -2.4];
    const side = a && a.facing === "left" ? -0.35 : 0.35; // beside the target, not on its head
    camera.updateMatrixWorld();
    const v = new THREE.Vector3(x + side, 0, z - 0.25).project(camera);
    target = [Math.min(W - 80, Math.max(80, ((v.x + 1) / 2) * W)), Math.min(H, ((1 - v.y) / 2) * H)]; // kept in frame
  }
  const info = paint(wg, { layers, seed: data.story.seed, t, n, w: W, h: H, strikes, target });
  wtex.needsUpdate = true;
  renderer.autoClear = false;
  renderer.render(overlay, flatCam);
  renderer.autoClear = true;
  const w = layers[0]?.weather;
  return { weather: w ? `${w.kind} ${w.intensity}${layers.length > 1 ? " (fading)" : ""}` : "clear",
    ...(info.flash ? { flash: +info.flash.toFixed(2) } : {}), ...(info.strike !== null ? { strike: info.strike } : {}) };
}

/** 0..1 how far actor a lies at frame kf of shot (lie 1, collapse its fall, else 0): framing follows it down */
const lying = (a, kf, shot) => (a.action === "lie" ? 1 : a.action === "collapse"
  ? collapseAt((kf - shot.start_frame) / FPS).fall : 0);

/** per-action drawing options for actor a (mutates o); returns the card roll { k 0..1 of 90 degrees, sign } */
function actionPose(shot, a, o, x, u, ts, n) {
  const key = `${charSeed(a.cast_id)}:${shot.id}`, other = shot.actors.find((b) => b.cast_id === a.target);
  const partnerX = (b) => (b ? (b.end_pos ? lerp(b.start_pos[0], b.end_pos[0], u) : b.start_pos[0]) : x);
  const sleepy = o.expression === "sleepy";
  let roll = { k: 0, sign: a.facing === "left" ? 1 : -1 }; // head toward the way it faced
  // a custom action (library/actions.json): its keyframed pose; humanoids play it, other creatures stand idle
  if (!BUILTIN_ACTIONS.has(a.action)) o.custom = customPose(lookup("actions", a.action), ts);
  if (a.action === "stagger" || a.action === "supported") o.stagger = staggerAt(key, o.phase);
  if (MOOD_EXPRESSION[a.action]) o.mood = moodAt(a.action, n / FPS, charSeed(a.cast_id));
  if (a.action === "carry" || a.action === "support") o.reach = { side: sideToward(x, partnerX(other), a.facing), k: 1 };
  if (a.action === "supported") {
    const h = shot.actors.find((b) => b.action === "support" && b.target === a.cast_id);
    if (h) o.reach = { side: sideToward(x, partnerX(h), a.facing), k: 1 };
  }
  if (a.action === "eat") {
    const props = o.props.some((p) => p.kind === a.prop) ? o.props : withProp(o.props, a.prop || "apple", "right");
    const e = eatAt(ts), hand = props.find((p) => p.kind === (a.prop || "apple")).hand;
    Object.assign(o, { props, eat: { ...e, side: hand === "left" ? -1 : 1 }, mouth: e.k > 0.8 ? 0.35 * e.chew : 0 });
  }
  if (a.action === "give" || a.action === "receive") {
    const g = giveAt(u), side = sideToward(x, partnerX(other), a.facing);
    o.reach = { side, k: g.reach };
    const mine = (a.action === "give") === (g.held === "giver"), kind = a.action === "give" ? a.prop : other?.prop;
    if (kind) o.props = mine ? withProp(o.props, kind, handOf(side)) : o.props.filter((p) => p.kind !== kind);
  }
  if ((a.action === "collapse" || a.action === "lie") && sits(a.cast_id)) {
    o.buckle = a.action === "collapse" ? collapseAt(ts).fall : 1; // sinks onto its belly, no roll
  } else if (a.action === "collapse" || a.action === "lie") {
    const c = a.action === "collapse" ? collapseAt(ts) : { buckle: 0, fall: 1 };
    roll = { ...roll, k: c.fall };
    o.buckle = c.fall < 1 ? c.buckle : 0;
    o.facing = "camera"; // drawn face-on: the card itself lies down
    if (c.fall >= 1) {
      o.action = "lie";
      o.breath = Math.sin((2 * Math.PI * ts) / LIE.breath);
      if (sleepy) { o.lid = 1; o.zzz = zzzAt(charSeed(a.cast_id), n / FPS); o.zSide = roll.sign > 0 ? 1 : -1; }
    }
  }
  return roll;
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

const MOOD_HOP = 0.06; // world units a cheering figure bounces
// head box on a card (world units over the feet): head outline plus the tallest hat and a brim's reach
const HEAD_BOX = (() => {
  const s = CARD_H / CH, [, hy] = skeleton({ action: "idle" }).head;
  return { lo: (FEET_Y - hy - HEAD_R) * s, hi: (FEET_Y - hy + HAT_TOP) * s, hw: (HEAD_R + 40) * s };
})();

/** screen rect (NDC) of a head box at world (x, z) for the current camera, lifted by y */
function headRect(x, z, y = 0) {
  camera.updateMatrixWorld();
  const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).setY(0).normalize(), pts = [];
  for (const sx of [-1, 1]) for (const h of [HEAD_BOX.lo, HEAD_BOX.hi]) {
    pts.push(new THREE.Vector3(x, y + h, z).addScaledVector(right, sx * HEAD_BOX.hw));
  }
  return rect(pts);
}

const INDOOR_BACK = -2.5; // the back wall stands at -2.6

/** x range at depth z where a figure's feet and head both stay in frame, for the whole shot (camera at u 0, .5, 1) */
function visibleRange(z, camAt) {
  let lo = -Infinity, hi = Infinity;
  const ndcX = (x, y) => new THREE.Vector3(x, y, z).project(camera).x;
  const solve = (y, target) => { // projected x rises with world x: bisect for ndc x = target
    let a = -30, b = 30;
    for (let i = 0; i < 40; i++) { const m = (a + b) / 2; if (ndcX(m, y) < target) a = m; else b = m; }
    return (a + b) / 2;
  };
  for (const u of [0, 0.5, 1]) {
    camAt(u);
    camera.updateMatrixWorld();
    for (const y of [0.05, FIG_H]) { lo = Math.max(lo, solve(y, -1)); hi = Math.min(hi, solve(y, 1)); }
  }
  return [lo, hi];
}

/** per shot, once: Map extra id -> { start, dx } (where it stands, or its run's shift) or null (dropped for this
 *  shot), plus .dropped. The crowd is first re-laid across the visible width (extras.js fitCrowd); then no extra's
 *  head may overlap a cast member's head or hat on screen (cast box + 6%): see extras.js placeExtras. */
function extrasFor(shot, camAt, placeAt2) {
  if (extrasByShot.has(shot.id)) return extrasByShot.get(shot.id);
  const list = shot.extras || [], heads = shot.actors.filter((a) => a.action !== "lie" && a.action !== "collapse");
  const castRects = (uu) => heads.map((a) => { const [x, z] = placeAt2(a, uu); return headRect(x, z, a.action === "carried" ? CARRIED_LIFT : 0); });
  const castAt = new Map([0, 0.5, 1].map((uu) => { camAt(uu); return [uu, castRects(uu).map((r) => growRect(r, HEAD_GROW))]; }));
  const free = (x, z) => [0, 0.5, 1].every((uu) => { camAt(uu); const r = headRect(x, z); return !castAt.get(uu).some((c) => overlap(r, c)); });
  const fit = fitCrowd(list.filter((e) => e.kind === "crowd"), (z) => visibleRange(z, camAt),
    { zBack: setKind(shot.set) === "indoor" ? INDOOR_BACK : -2.8, free });
  const laid = list.filter((e) => e.kind !== "crowd" || fit.get(e.id))
    .map((e) => (e.kind === "crowd" ? { ...e, start_pos: fit.get(e.id).pos } : e));
  const res = placeExtras(laid, {
    setCamera: camAt,
    castRects,
    headRect: (e, dx, uu) => { const [x, z] = placeAt(e, uu); return headRect(x + dx, z); },
    bounds: (e) => (e.kind === "crowd" ? fit.get(e.id).bounds : null),
  });
  const out = new Map();
  for (const e of list) {
    const l = laid.find((x) => x.id === e.id), dx = l ? res.get(e.id) : null;
    out.set(e.id, dx == null ? null : { start: l.start_pos, dx });
  }
  out.dropped = [...out.values()].filter((v) => v === null).length;
  extrasByShot.set(shot.id, out);
  return out;
}

/** extras: crowd rows in a mood (each with its own timing offset) and background runners (gait from distance:
 *  scroll + own move, like the cast). Looks are seeded per series and extra variant (extras.js). */
function drawExtras(shot, n, kf, u, shift) {
  const t = n / FPS, secs = (shot.end_frame - shot.start_frame) / FPS;
  const list = (shot.extras || []).filter((e) => shift.get(e.id)).map((e) => ({ ...e, start_pos: shift.get(e.id).start, dx: shift.get(e.id).dx }));
  let out = 0; // drawn extras whose feet or head fall outside the frame
  for (const e of list) {
    const [x0, z] = placeAt(e, u), x = x0 + e.dx, key = `${data.series.slug}:extra:${e.kind}:${e.variant}`, look = extraLook(data.series.slug, e);
    const own = e.end_pos ? Math.hypot(e.end_pos[0] - e.start_pos[0], e.end_pos[1] - e.start_pos[1]) : 0;
    const phase = e.action === "run" ? gaitPhase("run", ((shot.travel ? shot.travel.speed * secs : 0) + own) * u, 0) : 0;
    const mood = e.kind === "crowd" ? moodAt(e.action, t, key) : null;
    camera.updateMatrixWorld();
    const feet = new THREE.Vector3(x, 0, z).project(camera), head = new THREE.Vector3(x, FIG_H, z).project(camera);
    if (e.kind === "crowd" && [feet, head].some((p) => Math.abs(p.x) > 1 || Math.abs(p.y) > 1)) out++;
    const c = card(`extra:${e.id}`);
    drawStickman(c.cv, { seed: key, ...look, color: look.top.color, boil: Math.floor(n / BOIL_FRAMES), lid: lidAt(n, key),
      breath: Math.sin((2 * Math.PI * t) / 3.4 + 2 * Math.PI * rng(key, "breath")()), mouth: 0, t, phase, mood,
      px: (((head.y - feet.y) / 2) * H) / FIGURE_PX, action: e.action === "neutral" ? "idle" : e.action, facing: e.facing,
      expression: MOOD_EXPRESSION[e.action] || "neutral" });
    c.tex.needsUpdate = true;
    c.mesh.position.set(x, mood ? MOOD_HOP * mood.bounce : 0, z);
    c.mesh.rotation.set(0, Math.atan2(camera.position.x - x, camera.position.z - z), 0);
    const k = 1 + SHADOW.bounce * Math.abs(Math.sin(2 * Math.PI * phase));
    c.shadow.position.set(x, SHADOW.y, z);
    c.shadow.scale.set(SHADOW.w * k, 1, SHADOW.d * k);
    scene.add(c.mesh, c.shadow);
  }
  return (shot.extras || []).length ? { extrasDropped: shift.dropped, extrasOut: out } : {};
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
      seed: key, variant: v.variant, facing: v.facing, boil: Math.floor(n / BOIL_FRAMES), distance, t,
      broken: v.action === "broken",
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
    const half = (BODY_CARD_W / 2) * (head.y - feet.y) / FIG_H; // figure half-width in NDC-ish units at that depth
    inFrame &&= feet.y >= -1 && head.y <= 1 && Math.abs(feet.x) + half * (H / W) <= 1;
  }
  return { figure, inFrame };
}

const EXTRA = { color: "#8a8a8a", eyes: "dots" }; // generic grey extras (cast sheet carriers), not cast

/** cast sheet image: one character on a plain background. pose: idle | walk | talk | stagger | lie | eat | give |
 *  carried (between two grey extras); expression for the face (none given: the cast member's default) */
window.renderCast = ({ castId, pose, look: castLook = null, expression = castOf(castId, castLook).default_expression }) => {
  scene = new THREE.Scene();
  scene.background = new THREE.Color("#f4f1ea");
  const props = castOf(castId, castLook).props;
  const o = { boil: 0, lid: 0, breath: 0, mouth: 0, t: 0.3, phase: 0, action: "idle", facing: "camera", expression, props, look: castLook };
  let cam = [0, 0.82, 2.6], look = [0, 0.8, 0], y = 0, roll = 0;
  if (pose === "walk") Object.assign(o, { action: "walk", facing: "right", phase: 0.25 });
  if (pose === "talk") Object.assign(o, { action: "talk", mouth: 0.8 });
  if (pose === "cheer") Object.assign(o, { action: "cheer", mood: { k: 1, bounce: 0, shake: 0 } });
  if (pose === "angry") Object.assign(o, { action: "angry", mood: { k: 1, bounce: 0, shake: 0.5 } });
  if (pose === "stagger") Object.assign(o, { action: "stagger", facing: "right", phase: 0.3, stagger: { sway: 0.7, buckle: 0.6 } });
  if (pose === "lie" && sits(castId)) Object.assign(o, { action: "lie" });
  else if (pose === "lie") { Object.assign(o, { action: "lie" }); roll = -Math.PI / 2; y = LIE.lift; cam = [0, 0.62, 2.9]; look = [0, 0.3, 0]; }
  if (pose === "eat") {
    const kind = "apple", has = props.find((p) => p.kind === kind);
    const ps = has ? props : withProp(props, kind, "right"), side = (has?.hand || "right") === "left" ? -1 : 1;
    Object.assign(o, { action: "eat", facing: "right", props: ps, eat: { k: 1, chew: 0.6, side }, mouth: 0.25 });
  }
  if (pose === "give") {
    const kind = props[0]?.kind || "medal";
    Object.assign(o, { action: "give", facing: "right", props: withProp(props, kind, "right"), reach: { side: 1, k: 1 } });
  }
  if (pose === "carried") {
    Object.assign(o, { action: "carried", phase: 0.2 });
    y = CARRIED_LIFT; cam = [0, 1.0, 3.3]; look = [0, 0.95, 0];
    for (const [id, x] of [["extra:left", -HOLD_GAP], ["extra:right", HOLD_GAP]]) {
      const c = card(id), side = x < 0 ? 1 : -1;
      drawStickman(c.cv, { seed: `${data.series.slug}:${id}`, ...EXTRA, boil: 0, lid: 0, breath: 0, mouth: 0, t: 0.3,
        phase: 0, action: "carry", facing: "camera", expression: "neutral", reach: { side, k: 1 } });
      c.tex.needsUpdate = true;
      c.mesh.position.set(x, 0, 0); c.mesh.rotation.set(0, 0, 0);
      scene.add(c.mesh);
    }
  }
  const cd = creatureOf(castId);
  if (cd && pose !== "carried") { // frame the creature at its own size: centred on it, backed off for a big one
    const m = creatureSize(cd), h = (CARD_H * m.top) / CH, w = (CARD_H * m.half) / CH, z = Math.max(1, w / 0.42, h / 1.3);
    cam = [0, h * 0.5 + 0.02, 2.6 * z]; look = [0, h * 0.5, 0];
  }
  scene.add(drawCard(castId, o));
  const tall = (CARD_H * (cd ? creatureSize(cd).top : figurePx(bodyOf(castId).build))) / CH;
  cards[castId].mesh.position.set(pose === "lie" && !sits(castId) ? -tall / 2 : 0, y, pose === "carried" ? HELD_Z : 0);
  cards[castId].mesh.rotation.set(0, 0, roll);
  camera.fov = 45;
  camera.position.set(...cam);
  camera.up.set(0, 1, 0);
  camera.lookAt(...look);
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
    const g = buildSet(set, seed, variant), named = [];
    g.traverse((m) => { if (m.name && !named.includes(m.name)) named.push(m.name); });
    let worst = { excess: -Infinity, row: "none" };
    for (let k = 0; k < steps; k++) { // 0.237-unit steps: no layout period divides them, ~1.0 band sweep
      const r = loopExcess(g, 0.01 + k * 0.237);
      if (r.excess > worst.excess) worst = r;
    }
    out.push({ set, variant, seed, ...worst, named });
  }
  return out;
};

window.engineReady = true;
