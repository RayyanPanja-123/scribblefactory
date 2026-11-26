## Library basics

- Sets: `room`, `office` (indoor); `street`, `dirt_road`, `countryside`, `orchard`, `stadium` (outdoor). All modern.
- Props: `clipboard`, `stopwatch`, `bottle`, `syringe`, `apple`, `medal`.
- Bodies: `human` (default), `monkey` (biped), `chicken` (bird), `cat`, `horse` (quadruped), `snake` (crawler).
- Only humanoids and bipeds have hands for holding, eating, giving, carrying and supporting.
- World items: use `@item` for drawn objects (planets, ships; see script guide). Built objects are set scenery only.
- All other available items are listed in the inventory.

## New items

- Every object used by a character must be a held prop, defined through cast `props`, `@look` props, `@hold`, or `@do eat` / `give`. One item per hand (`left` / `right`).
- During library planning, first list **every cast-owned object** found in TTS scripts, before proposing sets or other categories. Keep this discovery list complete, even beyond the 3-props-per-part package limit. If limits conflict, explain and wait for the user's decision.
- Add sets, creatures or wardrobe only when existing items cannot fit.
- Package limits: 2 sets, 3 props per part, 2 creatures, 4 wardrobe items.
- IDs: lowercase letters, numbers and dashes only; never reuse built-in names.
- Follow the **Library item schemas** below.
- Props: hand position `[0,0]`, y increases downward, canvas pixels (roughly -40 to 110).
- Long props (staff, spear, trident, flag) need `angle` (clock-hand degrees, tip pointing away; `30` = one o'clock) and `grip` (hand attachment point). Example: `"props": [{"kind": "trident", "hand": "right", "angle": 30}]`.
- Sets: actors at y `0`, z `0`, x `-2` to `2`; scenery behind at z `-1`. Anything the cast climbs (a mountain path, stairs, a tower) is a set with a `trail`: its steps as `backdrop` box pieces, and `"trail": {"start": [x, y, z], "end": [x, y, z], "steps": n}` (the foot and the top, in front of the steps; `steps` for stairs). The story then uses `@do <cast>: climb`.
