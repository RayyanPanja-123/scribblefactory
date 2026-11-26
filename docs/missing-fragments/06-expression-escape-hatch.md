# 6. Expression escape hatch (last)

**Problem.** Some needs are one-offs that no schema anticipates (a camera path, a strange motion curve).

**Design.** A tiny sandboxed formula language, evaluated by the engine, never arbitrary JavaScript: numbers, `t` / `u`
(time, shot fraction), `sin cos lerp smooth clamp noise`, and named inputs (`subject.x`, `look.y`). It can appear
wherever the data takes a number over time: a camera move's position, a custom action's joint angle, a prop's path.
```json
{"id": "spiral-in", "camera": {"orbit": "120 * smooth(u)", "radius": "lerp(1, 0.5, u)"}}
```
- Parsed to a tree, limited depth and node count, no loops, no access to anything but its inputs: it cannot hang or
  touch files.
- Previewed like everything else before approval.

**Do last.** Only after 01 to 05 show which gaps the data schemas still cannot express.
