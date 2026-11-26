# 4. Registries instead of switch statements

**Problem.** Camera moves are a `switch` in `engine/page/main.js` (orbit was one more case); environments, fog,
weather and effects are the same. Every new one is an engine edit.

**Design.** A registry per kind, each entry data plus a small pure function:
- **camera moves**: `{id, params}` where the engine looks the id up (push, pull, truck, crane, orbit are the first
  five entries). A library entry may define a move as a parametric path (a spiral, a whip pan: keys over `k`).
- **environments**: `water` (tint, caustics, depth fog, bubbles), `space`, `smoke`: a volume look a set or a
  locomotion mode references.
- **effects**: spark, dust, bubbles as particle recipes (count, life, motion), not new code.
- The schema `CamMove` literal, the planner lists and the docs are all generated from the registry (one place to add).

**First step.** Move the camera `switch` to a table in `engine/page/camera.js`, generate `CamMove` and the docs from it.

**Done when.** Adding a camera move (a whip pan) means adding one entry, with no edit to `main.js`, the schema or docs.
