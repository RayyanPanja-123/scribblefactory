# Reference engine: mromidev/claude-animated-shorts

Inspected 2026-11-16 from a read-only clone outside the repo.

## Snapshot
- Repo: https://github.com/mromidev/claude-animated-shorts
- Latest commit: `e3b817b6afc6cd413466d43f11ba31209e034bbf`, 2026-11-01T11:56:54+06:00 ("Add 20 reference contact sheets (1,200 frames)").
- History: only 2 commits, both on 2026-11-01. It is a code drop, not a maintained project.
- Contents: it is a Claude skill (`SKILL.md`) plus template sources. It is not a runnable package.
  - No `package.json` and no lockfile. No dependency versions are pinned anywhere.
  - `templates/bridge/`: 13 TS/TSX files, about 4.8k lines. This is the source of one short ("The Bridge That Fell for a Song").
  - `templates/audio/`: 7 Python files, about 2.1k lines (synth SFX, march music, mix).
  - `templates/scripts/`: stills, side-by-side sheet, shot merge, frame QA.
  - `references/`: style bible, 7 measured reports, 38 frames and 20 contact sheets taken from a third-party channel.

## License
- **MIT License**, "Copyright (c) 2026 Mr omi".
- Fork, modify and vendor for personal use: **yes**. The only condition is to keep the copyright and permission notice in copies or substantial portions.
- Exceptions to watch:
  - **`references/frames` and `references/sheets`** are frames from someone else's videos. The README says they are "included for style study only", and SKILL.md says never to upload or publish them. MIT does not cover them, because the author can't license another channel's frames. **Do not vendor `references/`.**
  - **Remotion** (which the code depends on) is not MIT. It has its own Remotion License: free for individuals and small companies, with a paid company license above a size threshold. Personal use is fine today, but it is still an extra license to track. Our stack does not use Remotion anyway (see below).
  - Kenney kit `.glb` models are loaded from `public/bridge/kenney/`. They are CC0, but they are **not in the repo**. You would have to download them yourself.

## Shot plan
- File: `templates/bridge/story.ts`. It is **TypeScript code, not data**: hand-written per short, with closures. There is no JSON and no schema.
- Exports and fields:
  - `FPS = 30`, `TOTAL` (frames).
  - `SHOTS: ShotDef[]` with `{ id, a, b, light: "day"|"golden", crowd: "march"|"fall"|"water"|"bank"|"tourists"|"none", tau: (t)=>storyTime, towns? }`. `a`/`b` are the start and end frames (end exclusive).
  - `XFADE: Record<shotId, frames>`: crossfade into that shot.
  - `FLASH_AT`: frame of a 4-frame white flash.
  - `CAMS: Record<shotId, Key[]>`, with `Key = { f, dur?, cut?, s: (f) => { pos, look, fov?, roll? } }`.
  - `KICKS: [timeSec, gain][]`: impact shakes.
  - `DOF: { f, dur?, cInf, focus?: (f)=>V3 }[]`: lens blur per beat.
  - `FOREGROUND: { a, b, kit, pos, s?, yaw? }[]`: near framing props.
  - It also holds story physics specific to this one short (`front`, `marchPhase`, `amp`, `bridgeState`, `deckY`, ...).
- Example:
  ```ts
  { id: 4, a: 444, b: 534, light: "day", crowd: "march", tau: (t) => t },
  // camera for shot 4
  4: [
    { f: 444, s: S4a },                         // cut on "Halfway"
    { f: 497, cut: true, s: S4b },              // cut on "bouncing"
    { f: 497, dur: 20, s: rolled(S4b, 0.035) }, // 4 deg roll
  ],
  // S4a = f => dolly([13, D0+2.4, F+7], [0, D0+1.2, F+7], pushK(f, 444, 0.002))
  ```
- Timing: everything is hand-keyed to `words.json` frame numbers. Nothing generates the plan.
- The cast is placed in `cast.ts` `stage(id, t, ...)`, which branches on shot id and crowd mode. Story choreography lives in code.

## Rendering
- Entry point: Remotion. The `BridgeShort` composition (`Bridge.tsx`) is registered as 1080x1920 @ 30 fps.
  - Final render: `npx remotion render src/index.ts <Comp> out.mp4 --codec h264 --crf 16 --scale 1.3333` (1440x2560).
  - Stills: `scripts/bridge-stills.mjs` (`@remotion/bundler` + `renderStill`, Chrome with `gl: "angle"`).
- Stack: React + `@remotion/three` (`ThreeCanvas`), `@react-three/fiber`, `@react-three/postprocessing` / `postprocessing`.
  - Post chain: ink pass → lens blur (pre + main) → bloom → NEUTRAL tone map → grade, MSAA 4.
  - Crossfades stack a second canvas.
- Frame capture: Remotion's headless Chrome screenshots each frame, then Remotion encodes with ffmpeg.
- Time: **deterministic**. Everything is a pure function of `useCurrentFrame()`.
  - `World.update(id, f, cam, scene)` poses the whole world for frame f.
  - Blinks and variation use a seeded hash (`hh`/`rnd`). Grain is seeded per frame.
  - Nothing reads wall-clock time.
- Speed noted in SKILL.md: 2K about 4 fps (about 10 min for 67 s). Each bundle copies `public/` (about 1.3 GB) to temp, which once filled the disk.

## Character rig
- Characters are **2D Canvas2D drawings on billboard quads**, not 3D rigs.
  - `toon.ts` has a `Pen` drawing API on a 600x1000 design canvas (soles at y=975).
  - `bodyFront(pen, outfit, FrontOpts)` and `bodySide(pen, outfit, SideOpts)` redraw the whole character from parameters every frame.
  - `cast.ts` `Actor` puts the canvas texture on a yaw-only, camera-facing plane, on the `NOINK` layer so the world ink pass skips it. Lighting comes from `cardshade.ts`.
  - A `Pool` caches one canvas per distinct drawing key, so characters with the same pose share textures.
  - Resolution tiers depend on camera distance.
- Construction: superellipse "bean" heads with a seeded wobble, bean torsos, single-stroke limbs with ink-dot hands, and a plum (#241726) thick-thin outline.
  - There are 14 expressions (`Expr` maps to eye, brow and mouth kinds).
  - Outfit fields: `{ jacket, pants, boots, hat, belt, buttons, rifle, sash, sword, moustache, skin, cap, hair, dress, build }`.
  - Builds: adult, stout, kid.
- Pose: the view is chosen per character from the angle between camera and walk direction (`viewOf`: front or side, mirrored, foreshortened).
  - Options: `phase`, `mode` (march / stroll / stand / sit / fall / swing / push), `look`, `tilt`, `headTilt`, `wave`, `prop`.
- Walk: phase-driven.
  - `marchPhase(tau)` is a 1 Hz cycle (2 steps/s).
  - In side view, a two-bone `ik()` leg keeps the stance foot planted: it slides back at walking speed while the hip bobs. Stride is 370 units × stride (about 0.8 m).
  - The upper body sways ±1.6° per step.
  - Front view uses the same phase. The scale is about 3.5 head-heights.
- Blink: `lidAt(t, i)` with seeded gaps of 0.5–2.3 s.
  - Each blink is 4 frames (half, shut, shut, half).
  - There is also a forced blink on every expression swap to hide the change.
- Breathe: **none**. There is no idle breathing anywhere (grep for breath/idle finds nothing). Idle characters only blink, wave or bob in water.

## Camera
- Each shot has a list of keys in `CAMS`. A key is `{ f, dur?, cut?, s }`, where `s(f)` returns `{ pos, look, fov, roll }`. The function is evaluated per frame, so a framing can track moving subjects.
- `run()`: a `cut` key snaps. Otherwise the camera blends from the previous framing with smootherstep `glide()` over `dur` (default 24 f).
- Helpers:
  - `dolly(pos, look, k)`: move toward the look point.
  - `zoom(pos, look, fov, k)`: FOV push.
  - `pushK(f, f0, rate, punch, n)`: exponential creep, 0.15–0.35 %/f, with a punch burst.
  - `rolled()`: add roll.
- `kickAt()`: impact shake. It flips sign every frame and decays over 7 f.
- The camera is applied in `world.update`: `cam.position.set(...); cam.lookAt(...); cam.rotateZ(roll)`.
- Rules (creeping holds, cuts on big reframes, 4–5° rolls) are **documented in SKILL.md but not enforced in code**. They are followed by hand-authoring each shot.

## Gaps vs docs/brief.md
| Brief item | Reference engine |
|---|---|
| Stack: Node + three r160 + Playwright | Remotion + React + R3F + postprocessing. No Playwright. No three version pinned. |
| 9:16 1080x1920 30fps | Composition is 1080x1920@30, but finals are 1440x2560 (`--scale 1.3333`). Our output is 1080 (scale 1). |
| Rule-based shot plan → story.json | None. The plan is hand-written TS code per short, with no data format and no generator. |
| Validator: max 90 frames/shot | None. Reference shots run 78–209 frames (e.g. shot 12 is 209). |
| Validator: no repeated angle back-to-back | None. |
| Validator: camera always creeping | Only a convention (`pushK` on every framing). It is caught after the fact by `short_qa.py` frozen-span detection (≥12 f), not validated. |
| Validator: characters face movement direction | Partly, by construction: `viewOf` picks side/front and mirroring from the walk direction. Not checked. |
| Validator: walk phase drives legs, no gliding | Yes, by construction (phase + planted-foot IK). Not checked. |
| Validator: idle breathing + blink on every character | Blink yes. **Breathing missing.** |
| Twist line: music stops, low hit, push-in with roll | Pieces exist (punch push, roll, kicks, audio cues) but the combo is hand-placed. No rule. |
| Audio: music −6 dB under voice, −14 LUFS, peak −1 dBFS | Its own mix (music +3 dB, SFX −6 dB, ducking). Loudness is measured in QA, not targeted to our numbers. |
| Chunked parallel resumable render | None. One Remotion render. No chunks, no resume. |
| Stickman style (white wobbly head, no nose, blob body, stick limbs, dot hands, no shoes) | Close but different: skin-coloured bean heads, plum ink, boots, outfits with hats and props. `toon.ts` needs a restyle. |
| Cast test sheet / stills contact sheet / 5 s test | Stills script + `sbs_sheet.py` + `short_qa.py` contact sheets. These can be adapted. |
| Pinned deps, offline | No manifest. Kenney GLBs not included. |

## What is worth borrowing
- `story.ts` camera math: `glide`, `pushK`, `dolly`, `zoom`, `kickAt`, keyed `run()`. It is small, pure and framework-free.
- `toon.ts` `Pen` + head/blob/limb/face construction, and `cast.ts` billboard + canvas pool + `lidAt` + `viewOf`. This is mostly plain three.js plus Canvas2D, and it runs in our Playwright page as is.
- `ink.ts` (outline pass) and `shade.ts` / `lights.ts` / `paint.ts` for the toon world look. These need porting off the R3F/postprocessing wrappers.
- `short_qa.py`: frozen/black/pop frame and loudness QA. This maps directly to our Step 12.
- `templates/audio/*`: synth SFX and music. Retarget the mix to our dB/LUFS numbers.

## Recommendation
**Borrow ideas and selected files. Don't fork it as the base.**
- It is a one-off short (bridge-specific physics and crowd modes hard-coded through `story.ts`, `cast.ts` and `world.ts`), not an engine.
- It is built on Remotion + React + R3F, which conflicts with the brief's "Node + three r160 + Playwright, no heavy frameworks". It also adds the Remotion license and the 1.3 GB-per-bundle temp problem.
- There is no data shot format, validator, chunked render or dependency manifest. Those are the parts we need to build anyway.
- Plan: copy the MIT files we need into `engine/` with the license header and a note pinning commit `e3b817b`. Then:
  - Drive them from our own `story.json` + `render.mjs` (Playwright, deterministic frame index → `page.screenshot`).
  - Restyle `toon.ts` to the brief's stickman.
  - Add idle breathing.
  - Never copy `references/`.
- This changes the brief's "Fork it, pin the commit" line. Update the brief if you agree.
