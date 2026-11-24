## Library basics
- Sets: `room`, `office` (indoor); `street`, `dirt_road`, `countryside`, `orchard`, `stadium` (outdoor). All modern.
- Props: `clipboard`, `stopwatch`, `bottle`, `syringe`, `apple`, `medal`.
- Bodies: `human` (default), `monkey` (biped), `chicken` (bird), `cat`, `horse` (quadruped), `snake` (crawler).
- Only humanoid and biped bodies have hands (hold, eat, give, carry, support).
- World Items: "drawn" ones go on stage with `@item` (planets, ships; see the script guide); "built" ones are set
  scenery only.
- Everything else: the inventory list.


## New items
- Every object a character uses must be a held prop: cast `"props"`, a `@look` with `"props"`, `@hold`, or `@do eat` / `give`.
  One per hand (`left` / `right`).
- During library planning, list every cast-owned object discovered in the TTS scripts before proposing sets or any other category. The three-props-per-part limit applies to the final Story Package format, not to the completeness of the discovery list; if more are needed, explain the conflict and wait for the user's decision.
- Add sets, creatures, wardrobe only if nothing fits.
- Max per package: 2 sets, 3 props per part, 2 creatures, 4 wardrobe items.
- Ids: lowercase a-z, 0-9, dashes; not built-in names.
- Follow the **Library item schemas** at the end.
- Props: hand at `[0,0]`, y down, canvas px (about -40 to 110).
- Long props (staff, spear, trident, flag): `"angle"` in clock-hand degrees, top tipped away (`30` = one o'clock),
  and a `"grip"` where the hand holds. Per character: `"props": [{"kind": "trident", "hand": "right", "angle": 30}]`.
- Sets: actors at y 0, z 0, x -2 to 2; scenery behind z -1.
