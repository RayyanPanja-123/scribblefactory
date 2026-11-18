# Story Package v1

One pasteable blob with everything for a new series: the new library items, the cast, the title, and every
part's script and voice text. Paste it on the dashboard's **Story Writer** page: it is checked, previewed and
imported in one go (all or nothing). This file is the single source of the format; the story guide the dashboard
copies for chat AIs embeds it.

## Format

Plain text. Each marker is **alone on its own line**, in exactly this order:

```text
<<<SCRIBBLE_PACKAGE v1>>>
<<<META>>>
{"series_title": "<title>", "parts": <number of parts>}
<<<PROPS>>>
[ <new prop>, ... ]          [] when there are none
<<<SETS>>>
[ <new set>, ... ]           [] when there are none
<<<CREATURES>>>
[ <new creature>, ... ]      [] when there are none
<<<ACTIONS>>>
[ <new action>, ... ]        [] when there are none
<<<WARDROBE>>>
[ <new wardrobe item>, ... ] [] when there are none
<<<CAST>>>
[ <cast entry>, ... ]        every character of every part
<<<PART 1>>>
<<<SCRIPT>>>
<the complete story.md of part 1>
<<<VOICE>>>
<the narration of part 1, word for word>
<<<PART 2>>>
<<<SCRIPT>>>
...
<<<VOICE>>>
...
<<<END>>>
```

- `<<<PART N>>>`, `<<<SCRIPT>>>`, `<<<VOICE>>>` repeat for N = 1 up to `parts`, in order.
- **META**: JSON object. `series_title` becomes the series title (and its slug); `parts` must equal the number of
  `<<<PART N>>>` sections (1 to 99).
- **PROPS / SETS / CREATURES / ACTIONS / WARDROBE**: JSON arrays of **new** items only, each exactly as the
  dashboard stores it (the schemas in `docs/schemas/props.schema.json`, `sets.schema.json`, `creatures.schema.json`,
  `actions.schema.json`, `wardrobe.schema.json`: one entry of the `props` / `sets` / `creatures` / `actions` /
  `wardrobe` list). Anything that already exists in the library is not repeated: the scripts and the cast just use
  its id. WARDROBE came later: a package without it reads as `[]`.
- **CAST**: JSON array in the cast-import shape (story guide section 6b): `{"id", "name", "color"}` plus the
  optional wardrobe slots (`hair`, `facial_hair`, `headwear`, `top`, `legwear`, `footwear`, `back`, `accessory`,
  `face`), `props`, `body`, `headless` and `looks`. Every character the series ever shows, also those who first
  appear in a later part. Every wardrobe id must exist (built in, in the library, or in WARDROBE) and belong to
  the slot it is worn in.
- **SCRIPT**: the raw `story.md`, unchanged from the usual script format: `# Part title`, directives each alone on
  its line, narration.
- **VOICE**: what the text-to-speech voice reads: the script's narration lines in order, word for word, with no
  `@` lines, no `# title` line and no `!!` marker. It is saved as the part's `script-for-tts.txt`.
- Every id a SCRIPT or the CAST uses (sets, props, creatures, actions, cast ids, looks) must exist in the library or
  be created by this package.

## What the importer does

- Text before `<<<SCRIBBLE_PACKAGE v1>>>` and after `<<<END>>>` is ignored (chat chatter), and so are code fence
  lines (```` ``` ````), Windows line endings, trailing spaces and a byte-order mark.
- **Errors** (nothing is imported): a missing or out-of-order marker, a part count that does not match META, bad
  JSON or an item that does not fit its schema, a wardrobe id that is unknown or worn in the wrong slot, and any
  script problem the dashboard's story check reports
  (unknown set, cast id, action, prop, look or body; bad directive). Each names its section and its line in the
  pasted text.
- **Warnings** (imported anyway): VOICE differs from the script's narration (with the changed words), a word count
  outside 110 to 175, more than one `!!`, a part before the last that does not end with "To be continued.".
- **Never overwrites.** A new item whose id the library already has is imported with a suffix (`lantern-2`), and
  the cast and scripts are rewritten to use it; a taken series slug gets a suffix too.
- **All or nothing.** New items, then the series with its cast and parts. Each part starts at the story step:
  `story.md` and `script-for-tts.txt` are written, the cast still needs approving, and the voice is recorded and
  uploaded as before.

## Example (two parts)

```text
<<<SCRIBBLE_PACKAGE v1>>>
<<<META>>>
{"series_title": "The Liar Lantern", "parts": 2}
<<<PROPS>>>
[{"id": "lantern", "name": "Lantern", "shapes": [
  {"shape": "line", "pts": [[0, 0], [0, -30]], "width": 6},
  {"shape": "rect", "pts": [[-22, -30], [22, 30]], "fill": "#f2d16b"},
  {"shape": "rect", "pts": [[-26, 30], [26, 40]], "fill": "#3a2a1e"}]}]
<<<SETS>>>
[{"id": "bakery", "name": "Corner Bakery", "kind": "indoor", "floor": "#8a6a4a", "back": "#f0e0c0", "pieces": [
  {"shape": "box", "at": [0, 0.5, -2.2], "size": [3, 1, 0.6], "color": "#c9a46b"},
  {"shape": "box", "at": [0, 1.9, -2.55], "size": [2.4, 0.08, 0.3], "color": "#8a6a4a", "backdrop": true}]}]
<<<CREATURES>>>
[]
<<<ACTIONS>>>
[]
<<<WARDROBE>>>
[{"id": "baker_hat", "name": "Baker hat", "slot": "headwear", "colorable": false, "default_color": "#fbf8ef", "layers": [
  {"shape": "rect", "anchor": "head_top", "pts": [[-95, 20], [95, 60]], "fill": "$color"},
  {"shape": "ellipse", "anchor": "head_top", "pts": [[0, -20]], "r": 110, "ry": 55, "fill": "$color"}]}]
<<<CAST>>>
[{"id": "ava", "name": "Ava", "color": "#3b6ea5", "hair": {"id": "long_hair", "color": "#8a4b2a"},
  "looks": {"lit": {"props": [{"kind": "lantern", "hand": "right"}]}}},
 {"id": "ben", "name": "Ben", "color": "#c0567a", "top": "shirt", "hair": "short_hair", "headwear": "baker_hat"}]
<<<PART 1>>>
<<<SCRIPT>>>
# The Lantern Test

@set bakery
@cast ava, ben
@fx shake
Ava found a lantern that only glows for liars.
It blazed the moment her brother Ben walked in.
Ben swore he had never lied. The flame doubled.
@look ava: lit
Ava held it up to his face.
@do ben: react
Ben shrugged and grabbed a loaf of bread.
!! Then the lantern turned toward Ava and roared.
To be continued.
<<<VOICE>>>
Ava found a lantern that only glows for liars.
It blazed the moment her brother Ben walked in.
Ben swore he had never lied. The flame doubled.
Ava held it up to his face.
Ben shrugged and grabbed a loaf of bread.
Then the lantern turned toward Ava and roared.
To be continued.
<<<PART 2>>>
<<<SCRIPT>>>
# Who Lied

@set street
@cast ava, ben
@look ava: lit
Ava ran into the street with the burning lantern.
Ben followed, laughing at her.
@do ava: wave
She waved it at every stranger. It stayed dark.
!! It only ever burned for her, because she had stolen it.
<<<VOICE>>>
Ava ran into the street with the burning lantern.
Ben followed, laughing at her.
She waved it at every stranger. It stayed dark.
It only ever burned for her, because she had stolen it.
<<<END>>>
```

The example is short to keep it readable: real parts have 110 to 175 words (the importer warns below that).
