// The art style's tunable numbers, all in one place (docs/style.md). Pure data: page code and Node tests import it.
// Change a value here and re-render; nothing else needs touching. Colours are CSS strings.
export const STYLE = {
  // rain and storm: two layers. back sits behind the cast (thin, faint, light, slow, drawn at half resolution so it
  // softens); front is drawn over everything but sparse, and skips any drop that would cross a face.
  // count: drops per intensity [light, medium, heavy]; storm multiplies both layers by storm.density.
  rain: {
    back: { count: [90, 160, 250], width: 2, alpha: 0.48, color: "#56606e", speed: 1.15, len: 0.8, scale: 0.5 },
    front: { count: [6, 10, 16], width: 4.5, alpha: 0.85, color: "#f4f7fb", edge: "#1c1a1a", edgeAlpha: 0.35,
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
};
