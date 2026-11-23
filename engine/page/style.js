// The art style's tunable numbers, all in one place (docs/style.md). Pure data: page code and Node tests import it.
// Change a value here and re-render; nothing else needs touching. Colours are CSS strings.
// the one ink colour: every outline, pupil and mouth, the sets' hulls, the wipe's edge
export const INK = "#1c1a1a";

export const STYLE = {
  // rain and storm: two layers. back sits behind the cast (thin, faint, light, slow, drawn at half resolution so it
  // softens); front is drawn over everything but sparse, and skips any drop that would cross a face.
  // count: drops per intensity [light, medium, heavy]; storm multiplies both layers by storm.density.
  rain: {
    back: { count: [90, 160, 250], width: 2, alpha: 0.48, color: "#56606e", speed: 1.15, len: 0.8, scale: 0.5 },
    front: { count: [6, 10, 16], width: 4.5, alpha: 0.85, color: "#f4f7fb", edge: INK, edgeAlpha: 0.35,
      speed: [1.7, 2.6], len: [0.8, 1.9] },
    storm: { density: 1.35, slant: 0.5, len: 80, speed: 2.4 }, // speed: frame heights per second
    slant: 0.22, len: 44, lenPerLevel: 14, speed: 1.7,
    faceMargin: 0.25, // head box grown by this share per side: front drops never cross it
  },
  // set outlines: width in screen px of the final 1080x1920 frame at any distance (characters' body lines are ~4-6 px
  // in a wide), lump = +- share the width swells and thins along an edge (re-seeded every boil step, like the cast),
  // segment = world units per outline subdivision (shorter: wobblier long edges, more vertices)
  ink: { width: 4.5, lump: 0.6, segment: 0.35 },
  // set two-tone ramp: colour multipliers for tops (normal up), sides facing keyDir (cosine >= keyMin), the rest and undersides
  shade: { top: 1.12, side: 0.95, under: 0.76, keyDir: [0.6, 0.35, 1], keyMin: 0.35 },
  // atmospheric perspective: set surfaces and outlines blend toward the set's background colour with depth behind the
  // stage (-z world units): none at near, max share at far. sky: the sky band's gradient (overhead colour = sky x top;
  // mid / low: where it reaches the sky colour and the horizon colour, 0 = top .. 1 = bottom of the band)
  depth: { near: 4, far: 45, max: 0.55, sky: { top: 0.8, mid: 0.62, low: 0.93 } },
  // water (outdoor custom sets whose floor colour is blue): detection, wave ticks on the floor texture (px of a 256 px
  // tile), foam bands around pieces standing in it (world units), and what main.js draws under the cast
  water: {
    hue: [170, 250], minSat: 0.2, light: [0.25, 0.92],
    wave: { count: 9, len: 11, width: 2, color: "#2b4a5e", alpha: 0.28 },
    foam: { width: 0.45, color: "#f6fbff", alpha: 0.9 },
    // rings on the ground expand from `from` to `to` world units across over `period` s, fading out
    ripple: { period: 1.6, rings: 2, from: 0.3, to: 1.25, alpha: 0.6, color: "#f6fbff" },
    wetRipple: 0.6, // ripples on wet ground (outdoors in rain or storm): this share of the alpha
    reflection: { alpha: 0.2 }, // the cast mirrored in the water under their feet
  },
  // lighting accent (a colour ramp, not lights). outdoor: on for outdoor sets (false: neutral greys everywhere).
  // Set tops take the warm key colour, sides sideWarm of it, faces away / undersides the cool colour. rim: a warm
  // edge inside each cast card's outline on the key side (screen right), `width` screen px wide, starting `inset`
  // card px in from the silhouette (past the ink outline). shadow: contact shadows' colour (never pure black).
  light: {
    outdoor: true, key: "#ffe8c6", sideWarm: 0.35, cool: "#b4c3e8",
    rim: { color: "#ffd28a", alpha: 0.75, width: 5, inset: 15 },
    shadow: "#27304d",
  },
  // camera. wide: outdoor wide shots (lower, closer: the cast fills the middle third; camY / lookY world units,
  // maxFill = never closer than a figure this share of the frame height, margin = extra x room around the cast).
  // move: world units (truck, crane) or distance share (push, pull) a move covers at speed 1. ease: moves ease in and
  // out. reactionHold: seconds a reaction close-up holds still before its move. tilt: max seeded horizon tilt in
  // degrees per shot (0 = level; capped at 2; a twist shot's roll_deg wins).
  camera: {
    wide: { margin: 0.6, maxFill: 0.33, camY: 1.35, lookY: 0.85 },
    move: { push: 0.35, pull: 0.5, truck: 0.9, crane: 1.0 },
    ease: true, reactionHold: 0.4, tilt: 0,
  },
  // character life for standing actors (idle, talk). bob: hip lift share with each breath; shift: degrees of slow
  // weight shift (lean about the feet) over shiftPeriod s; headTilt: degrees the head tilts toward whoever is speaking
  // or being addressed; turn / gaze: two named characters facing the camera angle their cards this many degrees toward
  // each other and glance that way (pupil shift share)
  idle: { bob: 0.35, shift: 1.3, shiftPeriod: 4.5, headTilt: 6, turn: 22, gaze: 0.8 },
  // painted creatures (creatures.js, not humanoids): inside every filled shape at least minSize card px wide or tall,
  // a soft lit spot toward the key light (screen right; x / y its centre as a share of the shape's box from the middle /
  // top, r radius share of the larger side) and light.shadow pooling from `shade.from` (share down the box) to the
  // bottom; eye: catchlight radius share of the eye dot (0 = none). null = flat fills.
  creature: { minSize: 30, lit: { color: "#fff4dc", alpha: 0.32, x: 0.18, y: 0.28, r: 0.55 }, shade: { from: 0.4, alpha: 0.3 }, eye: 0.35 },
  // the stickman's head and body blob get the same painted volume (stickman.js paintVolume); shade.side tilts the
  // shadow toward the side away from the key light, so the head reads as a ball. null = flat fills.
  figure: { minSize: 30, lit: { color: "#fff4dc", alpha: 0.35, x: 0.2, y: 0.25, r: 0.6 }, shade: { from: 0.3, alpha: 0.26, side: 0.7 } },
  // colour grade over the finished frame (weather included, captions are added later by ffmpeg); null = off.
  // contrast / saturation: 1 = unchanged; warmth: + pushes highlights warm and shadows cool; lift: shadow floor
  // (0..0.1, keeps blacks soft like ink on paper); vignette: corner darkening share, from `soft` (0 centre .. 1 corner)
  grade: null,
  // painted surfaces (every set texture): count soft light / dark blotches per tile break up flat colour (tone drift,
  // after the reference's paint.ts), each up to `alpha` strong (floors: times `floor`), radius r0..r1 share of the tile
  blotch: { count: 9, alpha: 0.14, r0: 0.2, r1: 0.45, floor: 0 },
  // indoor sets (built in and custom): a baseboard along the wall foot (`h` units tall, the wall colour's lightness times `tone`, with a lit lip),
  // the wall darkening toward ceiling and floor (`top` / `foot` alpha of the shadow colour), and a contact shadow on
  // the floor along the wall, `depth` units deep, `alpha` strong
  room: { baseboard: { h: 0.16, tone: 0.62 }, wall: { top: 0.13, foot: 0.14 }, floor: { depth: 1.1, alpha: 0.22 } },
  // painted clouds in outdoor skies (after the reference's cloudHD): count per sky, skipped when the sky colour's
  // lightness is under minLight (night); lit / mid / shade are the three painted tones; drift: world units per
  // second they slide right (fading out at one end of their row and back in at the other)
  clouds: { count: 5, minLight: 0.45, lit: "#fbf8f1", mid: "#e1e5f3", shade: "#c3cbe9", alpha: 0.92, drift: 0.6 },
};

// series.json style.preset -> overrides per STYLE section (a section is replaced key by key, not deep-merged)
export const PRESETS = {
  default: {},
  cinematic: { grade: { contrast: 1.08, saturation: 1.12, warmth: 0.05, lift: 0.03, vignette: 0.28, soft: 0.45 } },
  storybook: { grade: { contrast: 0.95, saturation: 0.9, warmth: 0.08, lift: 0.06, vignette: 0.18, soft: 0.55 } },
};

const BASE = structuredClone(STYLE);
/** reset STYLE to the defaults, then apply preset `name` (an unknown name throws: a typo must not render plain) */
export function usePreset(name = "default") {
  const p = PRESETS[name];
  if (!p) throw new Error(`unknown style preset "${name}" (known: ${Object.keys(PRESETS).join(", ")})`);
  const obj = (x) => x !== null && typeof x === "object";
  for (const k of Object.keys(BASE)) {
    const v = structuredClone(k in p && obj(BASE[k]) ? { ...BASE[k], ...p[k] } : k in p ? p[k] : BASE[k]);
    // in place when both are objects: modules that keep `const W = STYLE.water` see the preset too
    // ponytail: in place per section only; a module aliasing a nested object (STYLE.rain.back) keeps the default
    if (obj(STYLE[k]) && obj(v)) { for (const x of Object.keys(STYLE[k])) delete STYLE[k][x]; Object.assign(STYLE[k], v); }
    else STYLE[k] = v;
  }
}
