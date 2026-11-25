## Cast JSON

```json
[
  { "id": "lloyd", "name": "Lloyd", "color": "#3b6ea5",
    "props": [{ "kind": "clipboard", "hand": "right" }],
    "hair": { "id": "short_hair", "color": "#5a3a22" }, "top": "suit", "legwear": "trousers",
    "looks": { "axe": { "props": [{ "kind": "axe", "hand": "right" }] } } },
  { "id": "mike", "name": "Mike", "color": "#f2f2f2", "body": "chicken",
    "looks": { "headless": { "headless": true } } }
]
```

- Distinct `color` each; `body` defaults to `human`.
- Cast voice acting only: `"voice": {"id": "bf_emma", "speed": 1.0}`, the TTS voice of the character's own lines
  (`<id>: words`), from TTS VOICES in the library list; a distinct voice per speaking character. Speed 0.5 to 2.
- Changes during the story are `"looks"` (only what changes; `"none"` removes an item), never a second character.
- Wardrobe slots (humanoids): `hair`, `facial_hair`, `headwear`, `top`, `legwear`, `footwear`, `back`; lists of up to
  3 for `accessory`, `face`. Each id fits one slot.
- Built-in wardrobe: tops `plain suit tank shirt dress`; headwear `flat_cap postman_cap bowler straw_hat wide_hat`;
  legwear `shorts ragged_shorts trousers`.
- Creatures (cat, horse...) wear only custom `headwear`, `face`, `accessory` and `back` items (e.g. `crown`,
  `saddle`), fitted roughly to their head and body; no top, legwear, footwear, hair, facial hair or built-in hat.
- Creatures only (not humanoids): `"flame"` (`off low high`: fire on the mane, tail and hooves, eyes glowing) and
  `"flame_color"` (hex, the outer flame; unset is fire). Both work in looks: `"looks": { "blazing": { "flame": "high" } }`.
- Optional: `"default_expression"` (`neutral happy cheer sad angry surprised sleepy cheeky exhausted worried dead
  smug proud love excited relieved laughing wink furious annoyed disgusted crying scared embarrassed jealous guilty confused thinking suspicious shocked deadpan bored facepalm_ready dizzy drunk knocked_out evil crazy blank sick`), `"eyes"` (`dots`,
  `half_closed`).
