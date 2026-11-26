# 2. Locomotion modes as data

**Problem.** Movement is hard-coded: walk, run, stagger on flat ground. `climb` needed a whole feature (schema, planner,
engine). Swimming, flying and crawling would each need the same.

**Design.** A *locomotion mode* is a library entry; walking is just the default one.
```json
{"id": "swim", "surface": "volume", "speed": [0.4, 1.6], "pose": "swim-stroke", "bob": 0.04,
 "camera": "follow-y", "environment": "water"}
```
- `surface`: `ground` (today), `trail` (what `climb` does: a path with height, steps or a slope), or `volume` (a region
  where x, y and z are all free: water, sky).
- `pose`: a custom-action id played by distance travelled (as the walk gait is), so a stroke or a wingbeat is keyframes
  in the existing custom-action editor.
- The planner turns `@do <cast>: <mode> [to <place>]` into a move along the surface; the engine already supports a
  card at any height (`start_y` / `end_y`, `heightAt`) and a camera that follows it.
- **Volume surface** adds: a depth axis (y free), buoyancy bob, a heading that turns toward the move, bubbles.
- `climb` and `trail` become the `trail` surface of this system (nothing breaks: `climb` stays as its alias).

**First step.** A `volume` surface plus a `swim` mode (the stroke is a custom action). Needs the water environment (04).

**Done when.** An Atlantis scene where a character dives from the surface to the sea floor and swims along it renders
with a stroke, bubbles and depth fog, authored with library entries only.
