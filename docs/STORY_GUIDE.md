# scribblefactory story guide (for AI assistants)

**Important: do not**

- Use images, cards, tables, headings or other formatting while brainstorming. Plain short chat only.
- Write scripts, cast or assets before the story (premise, parts, twists) is agreed.
- Send the Story Package before the user explicitly says "approved".
- Rename, reorder or skip any `<<<...>>>` marker, split the package across messages or code blocks, or add text
  around it.
- Use an id (set, prop, cast, look, action, body, wardrobe) that is not in the library or created in the package.
- Put digits, symbols or markdown in narration, or narration on a directive line.
- Write a flat script (one `@set`, few directives). Every part must be staged (section 5, **Staging**).
- Call characters by role ("the commander") instead of their cast `name`.

Fill in **Your series** at the end and brainstorm. Each part becomes one vertical Short: a voice reads the narration,
a rule-based planner turns each line into shots of stickmen in a 3D world. `@` lines are silent directives.

## 1. Workflow

1. Brainstorm briefly (premise, cast, parts, each part's twist) as plain chat: a few short lines, one or two
   questions at a time. No images, cards, tables, headings or scripts. Settle the story before cast and assets.
2. Sum up the plan in a short list and wait for an explicit "approved". No package before that.
3. Reply with **only** one Story Package in one fenced `text` block, using exactly this skeleton (full rules in
   **Story Package format** at the end):

```text
<<<SCRIBBLE_PACKAGE v1>>>
<<<META>>>
{"series_title": "Title", "parts": 2}
<<<PROPS>>>
[]
<<<SETS>>>
[]
<<<CREATURES>>>
[]
<<<ACTIONS>>>
[]
<<<WARDROBE>>>
[]
<<<CAST>>>
[{"id": "ava", "name": "Ava", "color": "#3b6ea5"}]
<<<PART 1>>>
<<<SCRIPT>>>
# Part title

@set street
...
<<<VOICE>>>
narration only
<<<PART 2>>>
<<<SCRIPT>>>
...
<<<VOICE>>>
...
<<<END>>>
```

- Every marker exactly as shown, alone on its line, in this order, none skipped (empty sections are `[]`). No
  markdown headings, no extra code blocks, never split across messages.
- Asset sections (PROPS, SETS, CREATURES, ACTIONS, WARDROBE) hold only **new** items; `[]` when none.
- CAST holds every character of the whole series.
- VOICE = its SCRIPT's narration word for word, one line each, without `@` lines, title or `!!`.
- Every id used must exist in the library or the package.

4. The user checks the package and may paste back warnings that start with `staging:` (directives, `@do` density,
   lines with no mood, unused looks, actions or sounds). Fix every one that fits the story and reply with the whole
   corrected package again, never a partial one.

## 2. Script format

```md
# Part title

@set street
@cast alice, bob
Narration line.
```

- Line 1 `# Title`, blank line. One directive per line, alone (never narration on it).
- `@do`, `@face`, `@fx` and `@sfx` affect only the next narration line, which must follow; other directives last until changed.
- Narration: plain text, numbers as words, no digits, symbols, abbreviations, parentheses or markdown.
- Name characters by their cast `name`.

## 3. Writing rules

- **110 to 175 words** (aim under 145), at most 58 seconds (words / 2.6, plus 3 for non-final parts).
- Short lines, one idea each. Never start a line with Then, After that, So, Next, Later.
- **Line 1:** subject plus shocking claim, at most twelve words, concrete, starts with a name or noun. No date,
  setting, question, "Did you know", "Imagine", "This is the story of".
- **Line 2:** proof (a number, cost or odd detail). **Line 3:** flip an expectation ("X should have ended it. It
  didn't."). Lines 1 to 3: at most thirty words, never reveal the twist.
- **Exactly one `!! <line>`** (the twist), last line; non-final parts follow it with `To be continued.`

## 4. Library basics

- Sets: `room`, `office` (indoor), `street`, `dirt_road`, `countryside`, `orchard`, `stadium` (outdoor).
- Props: `clipboard`, `stopwatch`, `bottle`, `syringe`, `apple`, `medal`.
- Bodies: `human` (default), `monkey` (biped), `chicken` (bird), `cat`, `horse` (quadruped), `snake` (crawler).
  Only `human`/humanoid and biped bodies have hands: others cannot hold, eat, give, carry or support.
- More under *Available in this library*.

## 5. Directives

| Directive | Rule |
|---|---|
| `@set <id>` | Required before the first narration line. |
| `@cast a, b` | At most 12; at most 6 named per scene. |
| `@do <cast>: <action> [prop] [target]` | Everyone named must be in `@cast`. |
| `@look <cast>: <look>` | A look from their CAST entry; `default` restores; resets each part. |
| `@face <cast>: <expression>` | Their face for the next line only: `neutral happy sad angry surprised sleepy cheeky exhausted worried`. |
| `@car arrive \| ride \| leave \| off` | `ride` seats at most 3. |
| `@dogs N` / `@runners N` | 0 to 6. |
| `@crowd cheer \| angry \| gasp \| neutral [N]` / `@crowd off` | 1 to 12 extras. |
| `@fx drop \| shake \| pop` | Caption effect. Sparingly. |
| `@weather clear \| rain \| snow \| fog \| wind \| storm [light\|medium\|heavy]` | After its `@set`. |
| `@fx lightning [cast \| prop]` | At most 3 per part. |
| `@sfx <id> [volume 0-1]` | A sound effect for the next line. At most 5 per part. |

`@do` actions: `idle talk point react wave cheer angry gasp walk run stagger lie collapse`, `eat [prop]`,
`give <prop> <target>`, `carry <target>` (exactly 2 carriers), `support <target>` (1 or 2), `car: broken` (car on
stage), or a custom action, optionally aimed at someone on stage (`@do marcus: attack-with-spears neptune`: they
face and move toward the target instead of the middle of the stage). Several: `@do fred: lie, amy: wave`.

### Staging (required)

The video only shows what the directives and names tell it. Without them every shot is people standing and talking.

- **New place, new `@set`** (the Senate, the beach, a ship). Follow it with a `@weather` that fits the mood: `storm`
  for sea, gods, war, villains; `rain` for loss; `fog` for mystery; `snow`, `wind` for journeys.
- **Match the era.** The built-in sets are modern: `street` has apartment blocks, `office` desks, `stadium` a sports
  ground. A story set in the past uses a library set of its time (the library's `roman-street` and `colosseum` for Rome) or adds
  one under SETS.
- **Name a cast member in every line**, by their cast `name`: the planner picks who acts by name.
- **Faces follow the words.** A line's first mood word (angry, furious, stomped, laughed, sobbed, gasped,
  scared...) sets the named character's face from the start of the line, and each later mood word switches it on
  that word: "Caligula grinned, then screamed" goes happy, then angry at "screamed". `@do <cast>: angry`, `gasp`,
  `react` or `cheer` sets it when the line has no mood word, and `@face <cast>: <expression>` fixes it for one line.
  Otherwise they wear their default face (`cheeky` smirks), so give every emotional beat a mood word, an emotional
  `@do` or an `@face`.
- **A `@do` at least every second or third line** for physical beats: point, run, wave, cheer, angry, gasp,
  react, stagger, collapse, give, carry, support, eat, custom actions.
- **Groups are `@crowd`** (an army, senators, a mob) with the reaction that fits; `@dogs` and `@runners` where
  they fit.
- **Objects are seen:** spears, letters, swords are props held through a `@look` switched on when used.
- **Punch:** `@fx shake` or `@fx drop` on line 1, `@fx pop` on line 3, `@fx lightning` on one to three big beats.
- Aim for **ten or more** directives per part besides `@set` and `@cast`.
- **Use what the library has.** Items under *Available in this library* may carry a "use for" note: when a moment
  matches it, use that item. Switch on each cast member's looks where the story calls for them, give characters
  their custom actions (a god raising a trident before `@fx lightning`), and show props in hands rather than
  describing them.

### Sound effects (`@sfx`)

Real ids and what each is for are under *Available in this library* (**Sound effects**). Default set:

| id | use for |
|---|---|
| `fahhh` | attention grab (the hook; plays after its line is said) |
| `camera_flash` | smooth transition |
| `metallic_riser` | tension before a reveal (ends as the line starts) |
| `right` / `wrong` | correct / wrong, positive / negative feedback |
| `vine_boom` | comedy timing, a reaction |
| `bass_impact` | hype, weight before the main reveal |
| `core` | a statement, emphasis |
| `among_us` | an unexpected reveal (a traitor, a fake) |
| `riser` | suspense before a payoff (ends as the line starts) |
| `pop` / `click` | pop-up text, UI elements |
| `glitch` | transition between clips |
| `money` | money and financial moments |

- `@sfx <id>` alone on its line, directly above the narration line it belongs to (next to `@do` / `@fx` is fine).
  An optional volume `0` to `1` overrides the default (`@sfx riser 0.6`).
- Only where it fits the moment: **at most 5 per part**, never two on lines right after each other.
- Risers (`riser`, `metallic_riser`) only right before a payoff, usually the `!!` line. `vine_boom` only for comedy.
  `money` only for money moments.
- A good default: `fahhh` on line 1 of part 1, a `riser` plus `bass_impact` (or `among_us`) on the twist.

## 6. New items

- Every object a character uses (axe, rope, letter) must exist as a prop and be held: cast `"props"`, a look with
  `"props"` switched on via `@look`, or `@do eat` / `give`. One per hand (`left`/`right`).
- Add sets, creatures, wardrobe only if nothing fits. Max per package: 2 sets, 3 props per part, 2 creatures,
  4 wardrobe items. Ids: lowercase a-z, 0-9, dashes, not built-in names.
- Follow the **Library item schemas** at the end. Props: hand at `[0,0]`, y down, canvas px (about -40 to 110).
  Long props (staffs, spears, tridents, flags) get an `"angle"` so they read clearly: degrees like a clock hand,
  top tipped away from the body (`30` = one o'clock, `75` = half past two), and a `"grip"` where the hand holds
  the shaft. A character can hold one at its own angle: cast `"props": [{"kind": "trident", "hand": "right", "angle": 30}]`.
  Sets: actors at y 0, z 0, x -2 to 2; scenery behind z -1.

## 6b. Cast JSON

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

- Distinct `color` per character. `body` defaults to `human`.
- Changes during the story are `"looks"` (only what changes; `"none"` removes an item), never a second character.
- Wardrobe slots (humanoids): `hair`, `facial_hair`, `headwear`, `top`, `legwear`, `footwear`, `back`; lists of up
  to 3 for `accessory`, `face`. Each id fits one slot. Built in: tops `plain suit tank shirt dress`; headwear
  `flat_cap postman_cap bowler straw_hat wide_hat`; legwear `shorts ragged_shorts trousers`.
- Optional: `"default_expression"` (`neutral happy sad angry surprised sleepy cheeky exhausted`),
  `"eyes"` (`dots`, `half_closed`).

## 7. Example (shortened; real parts need 110+ words)

```md
# The Fake Finish

@set dirt_road
@cast fred
@car ride
The Olympic marathon winner rode most of it in a car.
He rode eleven miles in his manager's car.
Cheating should have ended his race. It didn't.
@do car: broken
Eleven miles later, the car broke down.

@set stadium
@car off
@cast fred, daughter, thomas, trainer1, trainer2
@crowd cheer
@do daughter: give medal fred
The president's daughter handed Fred the gold medal.
@crowd angry
A spectator had spotted him in the car.
@do trainer1, trainer2: carry thomas
!! Two men carried Thomas across the line, and he was crowned champion.
To be continued.
```

## Your series

- **What the story is about:**
- **Number of parts:**
- **Tone** and anything to avoid:
