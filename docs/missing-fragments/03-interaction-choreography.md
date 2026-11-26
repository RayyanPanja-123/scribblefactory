# 3. Interaction choreography (duels, battles, group moves)

**Problem.** Sword fighting has no structure: one aimed action per attacker (`attack-with-spears <target>`) and a
victim who reacts. No parry, no exchange, no knockback, no formation. `don`, `give` and `carry` were each written as a
separate special case.

**Design.** A *choreography* is a library entry: beats between named roles.
```json
{"id": "duel", "roles": ["a", "b"], "beats": [
  {"t": 0.0, "a": "lunge", "b": "parry", "hit": false},
  {"t": 0.4, "a": "slash", "b": "stagger", "hit": true, "fx": "spark", "shake": 0.5},
  {"t": 0.8, "a": "pose-victory", "b": "collapse"}]}
```
- Each beat gives every role a custom action (existing keyframe actions), whether it lands, and optional effects
  (spark, shake, sound) on the hit frame.
- The writer: `@do aegis: duel kora` (or `@do aegis: duel kora win`). The planner closes the distance, faces them to each
  other, spreads the beats over the line, and picks who wins.
- **Formations** for crowds: `@formation <group>: line|circle|wedge|column`, used by the existing crowd system.
- `don`, `give`, `carry`, `eat` can later be rewritten as choreographies over the same machinery.

**First step.** The `duel` entry type, its schema, the planner step, one worked example (two characters with swords).

**Done when.** A duel renders with strike, parry and a clear winner from one `@do` line and library actions only.
