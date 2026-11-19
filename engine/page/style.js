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
};
