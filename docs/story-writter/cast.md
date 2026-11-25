## Cast JSON

```json
[
  {
    "id": "lloyd",
    "name": "Lloyd",
    "color": "#3b6ea5",
    "props": [{ "kind": "clipboard", "hand": "right" }],
    "hair": { "id": "short_hair", "color": "#5a3a22" },
    "top": "suit",
    "legwear": "trousers",
    "looks": {
      "axe": { "props": [{ "kind": "axe", "hand": "right" }] }
    }
  },
  {
    "id": "mike",
    "name": "Mike",
    "color": "#f2f2f2",
    "body": "chicken",
    "looks": { "headless": { "headless": true } }
  }
]
```

- Each character needs a distinct `color`. `body` defaults to `human`.
- Cast voice acting only: optional `"voice": {"id": "bf_emma", "speed": 1.0}`. Use distinct IDs from library TTS VOICES. Applies only to the character's dialogue (`<id>: words`). Speed: 0.5–2.
- Story changes use `looks`, containing only changed properties. Use `"none"` to remove an item. Never create duplicate characters for transformations.
- Humanoid wardrobe slots: `hair`, `facial_hair`, `headwear`, `top`, `legwear`, `footwear`, `back` (one item each); `accessory` and `face` (up to 3 each). Each item ID belongs to one slot.
- Built-in tops: `plain suit tank shirt dress`.
- Built-in headwear: `flat_cap postman_cap bowler straw_hat wide_hat`.
- Built-in legwear: `shorts ragged_shorts trousers`.
- Creatures (cat, horse, etc.) support only custom `headwear`, `face`, `accessory`, `back` items. No humanoid clothing, hair, facial hair, or built-in hats. Fit items roughly to head/body.
- Creatures only: `flame` (`off`, `low`, `high`) and optional hex `flame_color` (default fire). Flames affect mane, tail, hooves and eyes. Both work in `looks`, e.g. `"looks": {"blazing": {"flame": "high"}}`.
- Optional `default_expression`: `neutral happy cheer sad angry surprised sleepy cheeky exhausted worried dead smug proud love excited relieved laughing wink furious annoyed disgusted crying scared embarrassed jealous guilty confused thinking suspicious shocked deadpan bored facepalm_ready dizzy drunk knocked_out evil crazy blank sick`.
- Optional `eyes`: `dots`, `half_closed`.
