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
- Changes during the story are `"looks"` (only what changes; `"none"` removes an item), never a second character.
- Wardrobe slots (humanoids): `hair`, `facial_hair`, `headwear`, `top`, `legwear`, `footwear`, `back`; lists of up to
  3 for `accessory`, `face`. Each id fits one slot.
- Built-in wardrobe: tops `plain suit tank shirt dress`; headwear `flat_cap postman_cap bowler straw_hat wide_hat`;
  legwear `shorts ragged_shorts trousers`.
- Creatures only (not humanoids): `"flame"` (`off low high`: fire on the mane, tail and hooves, eyes glowing) and
  `"flame_color"` (hex, the outer flame; unset is fire). Both work in looks: `"looks": { "blazing": { "flame": "high" } }`.
- Optional: `"default_expression"` (`neutral happy cheer sad angry surprised sleepy cheeky exhausted worried dead`), `"eyes"` (`dots`,
  `half_closed`).
