# 5. AI-authored library items (Gemini)

**Problem.** Every new thing in a story (a crown, a pizza box, an Olympus set, a stroke) is hand-made JSON in the
library. It is slow, and it is where "I need Claude Code" starts.

**Design.**
- A *scan*: check-story already finds unknown ids; extend it to list everything missing, by kind (wardrobe, prop, set,
  action, creature, locomotion mode, choreography).
- A *draft* per item: one Gemini call with the item's schema (structured JSON output) and a few existing items as
  examples. Reuses `api/captions.py` (the key in Settings, the free-model fallback, plain `urllib`).
- *Fuzzy-match first*: "emperor's crown" -> `crown`, so most "missing" items are already there.
- A *check*: the draft is validated against the schema; a failure goes back to the model once. A preview card or a
  one-second test render shows what it looks like.
- A *review*: items land `pending` in the library UI; approve or edit, then the render continues. Nothing enters the
  library unreviewed. Items are JSON only, never code.

**Order of difficulty.** Wardrobe and props (plain ink shapes) -> sets (pieces and a trail) -> actions (keyframes: needs
the preview most) -> locomotion modes and choreographies (once 02 and 03 exist).

**Done when.** A story that names a new prop, set and wardrobe item renders after one approval click per item.
