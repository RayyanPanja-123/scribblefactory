# Art style config

Every tunable number of the renderer's look lives in one object: `STYLE` in [engine/page/style.js](../engine/page/style.js).
Change a value, re-render a still (`node engine/render.mjs --part <part> --frame N --out x.png`), compare. Nothing else
needs touching, and no story, set or series file changes: every style feature derives from what is already there.

| Section | What it controls |
|---|---|
| `rain` | Two rain layers. `back` is behind the cast (thin, faint, slow, half resolution); `front` is sparse, bright, varied, and skips any drop crossing a head box (`faceMargin`). `count` = drops per intensity `[light, medium, heavy]`; `storm.density` scales both for storms. Rain's grey tint sits behind the cast too. |
| `ink` | Set outlines: `width` in screen px of the final frame at any distance, `lump` = how much the width swells and thins along an edge (re-wobbles every 4 frames like the characters), `segment` = outline subdivision length. |
| `shade` | Set two-tone ramp from each surface's facing: `top` (up-facing), `side` (facing `keyDir`, cosine at least `keyMin`), `under` (away from the key, and undersides). Floors and the sky are not toned. |
| `depth` | Atmospheric perspective: surfaces and outlines blend toward the set's background colour from `near` to `far` world units behind the stage (`max` share). `sky` sets the sky band's gradient stops. |
| `water` | An outdoor custom set whose floor colour is blue (`hue`, `minSat`, `light`) is water: ink wave ticks on the floor, a foam band where pieces meet it, ripples and a fading reflection under the cast. `wetRipple`: ripple strength on wet ground (outdoors in rain or storm). |
| `light` | Colour ramp, not lights. `outdoor: false` turns it off. Outdoor set tops take the warm `key`, sides `sideWarm` of it, undersides the `cool` colour; cast cards get a warm `rim` just inside the outline on screen right; contact shadows use `shadow` (never black). |
| `camera` | Outdoor wides (`wide`: camera height, look height, minimum figure size, x margin), move sizes at speed 1 (`move`), `ease` (moves ease in and out), `reactionHold` (seconds a reaction close-up holds still before moving), `tilt` (seeded horizon tilt per shot in degrees, 0 = off, capped at 2). |
| `idle` | Standing actors: breathing `bob`, weight `shift` (degrees over `shiftPeriod` s), `headTilt` toward whoever they look at (addressed, else the speaker, else the other of two), and `turn` / `gaze` for two named characters facing the camera, who angle toward each other. |
| `blotch` | Soft light / dark tone drift painted into every set texture (in the surface's own hue, wrapped so tiles stay seamless): `count` per tile, `alpha`, radius `r0`..`r1` of the tile; floors take `floor` times it (0 = none: a repeating floor shows a blotch as a stain). |
| `room` | Indoor sets, built in and custom: a `baseboard` (`h` tall, the wall's lightness times `tone`, with a lit lip), the wall darkening toward the ceiling (`wall.top`) and floor (`wall.foot`) in the light's shadow colour, and a contact shadow on the floor along the wall (`floor.depth`, `floor.alpha`). |
| `clouds` | Painted clouds in every outdoor sky (`count`, three tones `lit` / `mid` / `shade`, `alpha`); none when the sky colour's lightness is under `minLight` (night skies). Drawn by `cloudCanvas` in borrowed.js (the reference's cloudHD). |
| `grade` | Colour grade over the finished frame (weather included; captions come later, from ffmpeg). `null` = off. `contrast`, `saturation` (1 = unchanged), `warmth` (warm highlights, cool shadows), `lift` (shadow floor), `vignette` (corner darkening) starting at `soft` (0 centre .. 1 corner). |

## Presets (per series)

`series.json` → `style.preset` picks an entry of `PRESETS` in style.js, applied over `STYLE` when a part renders:
`default` (no grade), `cinematic` (punchier contrast and colour, warm highlights, a vignette), `storybook` (softer,
warmer, lifted shadows). Set it with `set-style <slug> --preset cinematic` (refused once the style is locked); the
render stage re-runs because series.json is one of its inputs. An unknown name fails the render instead of rendering
plain. A preset replaces keys inside the sections it names; add a preset by adding an entry there.

Custom actions take an optional `ease` per key (`in-out` default, `linear`, `back-out`): how the pose moves into that key.

Everything stays deterministic: randomness is seeded (rain pools, outline boil, idle phase, foam edges), so the same
frame renders the same bytes. Tests: `engine/test/style.test.mjs` plus the rain, camera and idle cases in
`weather.test.mjs` and `motion.test.mjs`.
