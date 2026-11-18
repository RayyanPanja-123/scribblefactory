# Writing stories for scribblefactory: a guide for AI assistants

Share this whole file with an AI (paste it, or attach it), fill in **Your series** at the end, and start brainstorming.
The AI brainstorms the story with you, then returns the whole series as one **Story Package** you paste on the
dashboard's **Story Writer** page.
The format rules below are what the software enforces; the writing rules (hook, pacing, key props) keep the video
looking right. A story that follows both renders without edits.

---

## 1. What you are writing for

scribblefactory turns one text file, `story.md`, into a finished vertical video (1080x1920, 30 fps) for YouTube Shorts
and Instagram Reels:

1. The narration lines of `story.md` become a script that a text-to-speech voice reads aloud.
2. The voice is aligned to the script word by word (speech recognition), so captions and shots follow the words.
3. A rule-based planner (no AI) turns each phrase into one or more shots: who stands where, what they do, the
   camera angle, the set. Lines starting with `@` steer it and are never read aloud.
4. The video is rendered with marker-drawn stickman characters in a colourful 3D world, with music, sound effects
   and burned-in captions.

A story is a **series** split into **parts** (part 1, part 2...). Each part is one video and one `story.md`.
The characters (the **cast**) belong to the series and are designed beforehand; you can only use cast members
that already exist, by their **id** (or, for a new series, the ones you design in the package's CAST, section 6b).

## 2. How to work, and what to return

Work in three steps:

1. **Brainstorm** with the user: premise, characters, how many parts, the twist of each part. Ask, suggest, keep
   it short. No scripts yet.
2. **Agree on the story**: sum up the plan (title, parts, one line per part, cast, anything new to build) and wait
   for the user to say it is good.
3. **Deliver one Story Package** (the format is under **Story Package format** at the end of this guide): the
   whole series, every part, in **one** fenced `text` code block, and **nothing else** in that answer: no
   greeting, no notes before or after the block.

In the package:

- Only **new** sets, props, creatures, actions and wardrobe items go in PROPS / SETS / CREATURES / ACTIONS /
  WARDROBE, as JSON in the
  dashboard's own format (section 6). Anything in *Available in this library* is used by its id and never
  repeated. Every prop the story's key actions depend on must be created (section 6) and attached to the cast
  member who uses it (section 6, **How a character holds a prop**).
- CAST holds **every character of the whole series**, also those who first appear in later parts (section 6b).
- Each part's SCRIPT is its complete `story.md` (section 3); its VOICE is the narration only: the script's
  narration lines in order, one per line, without `@` lines, the `# title` line or the `!!` marker, word for word
  (the voice is matched to the script word by word, so any difference breaks the captions and shots).
- **Every id a SCRIPT uses must exist in the library or in the package**: sets, props, creatures, actions, cast
  ids and looks.

## 3. File format

```md
# Part title

@set street
@cast alice, bob
First narration line.
Second narration line.
```

- **Line 1** is `# <title>`, then a blank line. Headings are not read aloud.
- Every other line is either **narration** (read aloud) or a **directive** (starts with `@`, silent).
- **One directive per line, alone on its line.** Never put narration on a directive's line:
  `@set streetIn July...` swallows the whole sentence (it is never read aloud) and fails as an unknown set.
- Directives stay in effect until changed, except `@do` and `@fx`, which cover only the next narration line.
- Narration is plain text: no bold, italics, lists, links, emoji, tables or HTML. Markdown is stripped before
  the voice reads it, and anything stripped is silently lost.
- Blank lines between paragraphs are fine.

## 4. Narration: length and style

- **Length:** **110 to 175 words** per part (see **Target runtime** below).
- **Short sentences, one idea per line** (see **Pacing**). Every line becomes at least one shot; long lines are
  split into several shots automatically.
- **Write numbers as words:** "fifteen eighteen", "four hundred", "the third day". Digits break the word-by-word
  alignment between the voice and the text, and they make poor captions.
- **No symbols or abbreviations:** no %, &, $, "Dr.", "St.", "e.g.", no parentheses, no quotes inside quotes.
  Write what the voice should say.
- **Name characters by their name** as given in the cast list. The planner recognises names (and ids) to decide
  who the shot is about.
- Captions show at most five words at a time; plain wording reads best.
- **Hook first, twist last.** Lines one to three are the hook (see **Hook**). The `!!` twist is the last or second-to-last
  narration line (see **Twist and ending**).

### Hook: the triple hook (first three lines)

The first three narration lines form one hook, about eight seconds, at most thirty words together:

- **Line 1, Context:** says what the video is about immediately, plus the shocking claim. No delay: every word
  before the subject raises skip rates. (The line-1 rules below apply.)
- **Line 2, Lean:** builds curiosity with proof. Use one of: a hard number or stat, a specific pain or cost, or an
  unexpected detail. It never explains or slows down. A date or place may go here only if it adds proof;
  otherwise move it to line 4 or later.
- **Line 3, Snapback:** pulls the viewer toward an obvious expectation, then flips it (a pattern interrupt).
  Forms: "You'd think X. Wrong.", "Everyone blamed X. It was Y.", "X should have ended it. It didn't." The flip
  sends the story a new way but must **not** reveal the `!!` twist; the twist still closes the loop at the end.

Line one is the whole video. Viewers decide in about one second whether to keep scrolling, so the first line has
to hit before they can look away. It states the twist or the most surprising claim of the part. Dates, places and
backstory go on line two or later, never on line one. Never open with "In nineteen...", "In twenty...", "Once
upon a time" or any other date or scene-setting phrase (the story check warns).

What makes a hook land:

- **Short.** At most twelve words, ideally under eight (three seconds of voice). Two punches beat one long
  sentence: "Victor sold the Eiffel Tower. Twice."
- **Concrete.** A name, a number, a body, an object. "Thomas drank rat poison to win a race" beats "One runner
  went to extreme lengths".
- **Impossible or wrong.** It should sound like it cannot be true, or like the world got something backwards.
  The viewer stays to find out how.
- **Opens a loop the `!!` closes.** The hook tells *what* happened; the twist reveals *how* or *who*. Do not spend
  the twist on line one; tease it.
- **Strong first word.** Start with the name or the shocking noun, never "So", "This", "There", "It", "Today".
- **Line two hits again.** It follows the **Lean** rule above: proof, never explanation.

Hook patterns:

| Pattern | Example |
|---|---|
| The impossible fact | Victor sold the Eiffel Tower. Twice. |
| The wrong winner | The Olympic marathon winner rode most of it in a car. |
| The body count | A dance killed fifteen people a day. |
| The contradiction | The ship nobody could sink sank on its first trip. |
| The desperate act | Thomas drank rat poison to win a race. |

Never use these openers; they announce a hook instead of being one: "Did you know", "You won't believe",
"Imagine", "Let me tell you", "This is the story of", "Have you ever", or any question the viewer can answer "no".

**The test:** if the video stopped after line one, would someone repeat that sentence to a friend? If not,
rewrite it.

Line one may use `@fx shake` or `@fx drop`, and the Snapback line `@fx pop`, for extra punch; those are the
places the effect is always worth it.

Before (slow, the date comes first):

```md
In nineteen twenty-five, a con man named Victor arrived in Paris.
He read that the Eiffel Tower needed costly repairs.
```

After (Context, Lean, Snapback):

```md
Victor sold the Eiffel Tower. Twice.
Both buyers paid him in cash.
The first one never went to the police. He was too ashamed.
```

1. **Context:** Victor sold the Eiffel Tower. Twice.
2. **Lean:** Both buyers paid him in cash.
3. **Snapback:** The first one never went to the police. He was too ashamed.

### Pacing

- Short sentences. One idea per line.
- No filler transitions: never start a line with "Then", "After that", "So", "Next" or "Later". Cut straight to
  the next beat. "But" is allowed only at the start of the Snapback line (line 3).
- Every line should move the story forward; if a line only sets up the next one, merge or cut it.
- Long pauses in the voice are trimmed automatically (any pause over 0.4 seconds becomes 0.3), so the delivery
  stays tight; the writing must be tight too.

### Twist and ending

- The `!!` twist line is the **last or second-to-last** narration line. Nothing comes after it except the end line.
- **Non-final parts** end with the line "To be continued." right after the twist. The video then shows "Part 2 on
  my profile" over the last second and cuts.
- **The final part** ends on the twist itself: no "To be continued.". The video cuts right after the last word.
- Each part should still make sense on its own.

### Target runtime

**45 to 58 seconds per part**, never over 58. The voice reads about 2.6 words a second, and every non-final part
adds a one-second end card. Write 110 to 175 words; past about 145 the story check warns that the part runs long,
so stay near the low end unless the story needs the room. The dashboard's story check estimates the runtime
from the speed of past renders and warns above 58 seconds; after rendering, QA warns with the exact overage.

## 5. Directives

### `@set <name>`: where the scene is

One of: `room`, `office`, `street`, `dirt_road`, `countryside`, `orchard`, `stadium`, or the id of a custom set
from the dashboard's **Sets** page (e.g. `@set kitchen`). Default: `room`.
Put a `@set` before the first narration line. `room` and `office` are indoors; the other five are outdoors and
allow travelling shots (see section 7). A custom set is indoor or outdoor as it was made. Changing the set adds a
wipe transition and an establishing wide shot. Need a place that does not exist yet? See section 6.

### `@cast a, b, c`: who is on stage

Comma-separated cast ids. Default: the first two cast members of the series.

- Up to **6** stand side by side in one row.
- **7 to 12:** the characters *named in that scene's lines* (or used in an `@do`) stand in front and everyone else
  stands further back, smaller, idle. At most 6 may be named in one scene.
- Never more than **12**. For a large group of people, use `@crowd` instead (extras, not cast).
- Every cast member has a **body**, a creature type: `human` (the default stickman) unless its CAST entry gives
  another `body`, e.g. `"body": "chicken"`. **humanoid** bodies (`human` and custom ones like
  a giant or a child) are stickmen with their own proportions: faces, expressions, costume, hands, every action.
  Every other creature has eyes and a mouth only, no facial expressions. By rig:
  - **bird** (chicken, duck…) flaps its wings to react, cheer, wave or point and pecks to `eat`;
    **quadruped** (cat, horse…) hops and wags its tail, lowers its head to `eat`; **crawler** (snake, worm…)
    ripples along the ground and lifts its head. All three sit down for `lie` / `collapse` and have **no hands**:
    they cannot `give`, be given things, `carry` or `support` (they can be carried or supported).
  - **biped** (monkey, bear…) has arms and hands and can do everything a person can.
  - Every creature walks, runs, staggers, talks (mouth moves) and rides in the car. When one is the focus, the
    camera comes down to its height.

### `@do <cast>: <action> [target | prop]`: force an action

Overrides the guessed action for every shot of the **next narration line only**. The narration line must follow
directly; a second `@do` before it replaces the first. Everyone named must be in the current `@cast`.
Several clauses are comma-separated: `@do fred: lie, amy: wave`.

| Action | Form | Notes |
|---|---|---|
| idle, talk, point, react, wave | `@do amy: wave` | |
| walk, run | `@do amy: run` | walks or runs across the stage |
| stagger | `@do thomas: stagger` | wobbly walk |
| lie | `@do fred: lie` | lies down, eyes closed (sleeping) |
| collapse | `@do fred: collapse` | falls once, then lies for the rest of the line |
| eat | `@do bob: eat apple` | prop optional, default apple |
| give | `@do daughter: give medal fred` | needs one prop and one target; the prop changes hands |
| carry | `@do trainer1, trainer2: carry thomas` | exactly **2** carriers |
| support | `@do trainer1: support thomas` | **1 or 2** helpers hold someone up |
| cheer, angry, gasp | `@do amy: cheer` | crowd-style reactions |
| car: broken | `@do car: broken` | only when a car is on stage |
| a custom action | `@do fred: salute` | listed under *Available in this library*; in place; humanoids only (others stand idle) |

The target of give / carry / support cannot have its own action in the same `@do`.

### `@look <cast>: <look>`: change how someone looks

From the next narration line on, the cast member wears one of its named looks (its CAST entry's `"looks"`, e.g.
`"looks": {"headless": {"headless": true}}`) until another `@look` for them, for the rest of the part, across
`@set` changes. `@look mike: default` brings back their own look. Several at once: `@look amy, bob: wedding`.
Use it for a change the viewer should see: a lost head, a costume, a disguise, prison clothes, or an object in
hand (a look with props, e.g. `@look lloyd: axe`; section 6). A look is a whole outfit: it can set any wardrobe
slots at once (`{"coronation": {"headwear": "crown", "back": "cape", "top": {"id": "robe", "color": "#6b4f8a"}}}`)
and swaps them all on that line; slots it leaves out stay as they were, and `"none"` takes an item off. Only looks
listed for that cast member exist. A new part starts in everyone's own look, so repeat the `@look` at its top if
the change still holds.

```text
Lloyd grabbed a young rooster named Mike and swung his axe.
@look mike: headless
@do mike: stagger
The head dropped. Mike did not.
```

### `@car arrive | ride | leave | off`

- `arrive`: a car drives in and parks beside the main character.
- `ride`: the current `@cast` (at most **3**) sit in the car. Outdoors it is a travelling shot.
  During `@car ride` the only allowed `@do` is `@do car: broken` (it stalls with everyone seated).
- `leave`: the parked car drives off. `off`: no car (default).

### `@dogs N`

0 to 6 dogs. In travelling shots they chase; otherwise they idle or bark at the edges. `@dogs 0` removes them.

### `@crowd <cheer | angry | gasp | neutral> [N]`

Background crowd extras (not cast): N from 1 to 12, default 8. `@crowd off` removes them. Not shown in
travelling shots. A `@set` change resets the crowd.

### `@runners N`

0 to 6 background runners. A `@set` change resets them.

### `@fx drop | shake | pop | none`

Caption effect for the next narration line (for emphasis). Use sparingly.

### `!! <text>`: the twist

Starts a narration line (the text is read aloud). That moment gets a dramatic push-in, the music stops and a
low hit sounds. Use it **exactly once per part**, on the single biggest reveal, on the **last or second-to-last**
narration line. Nothing comes after it except the end line (section 4, **Twist and ending**).

### Props

Built in: `clipboard`, `stopwatch`, `bottle`, `syringe`, `apple`, `medal`. The library may have more (listed under
*Available in this library*). Only these can be used with `eat` and `give` or held by a cast member, plus new ones you list
(section 6). How a character holds one: section 6, **How a character holds a prop**.

### Creatures

Bodies for cast members (`"body"` in the CAST, section 6b, default `human`), each on a rig that decides how
it moves (section 5, under `@cast`). Built in: `human` (humanoid: the stickman), `chicken` (bird), `cat`
(quadruped), `horse` (quadruped), `monkey` (biped), `snake` (crawler), or the id of a custom creature from the
dashboard's **Creatures** page. Every creature but a humanoid has a `headless` version (a neck stump) for a
`"headless"` look. A body that does not exist yet goes in the package's CREATURES (section 6).

## 6. New sets, props, creatures and wardrobe

- **Sets: prefer what already exists.** Add a new one only when no existing set fits the place.
- **Props: every key object is required.** Any object the narration names that a character uses to do a story
  action (a weapon, a tool, an instrument, a key object: an axe, a knife, a gun, a rope, a key, a letter, an
  eyedropper) must be in the video. If it is not built in or in the library (*Available in this library*), list
  it in the package's PROPS, even when no `@do` uses it, and attach it to the character who uses it (below). A
  farmer beheading a chicken needs an `axe`.
- **Creatures:** every cast member has a body (default `human`); add a new one only when none fits.
- **Wardrobe: dress the cast from what exists.** Hair, beards, crowns, robes and so on are listed under
  *Available in this library*; add a new item only for a look the story depends on (a pharaoh's headdress).

Anything new goes in the package as JSON, exactly as the dashboard stores it (the schemas are under **Library
item schemas** at the end of this guide). Use its id in the scripts (sets, props, actions) and the CAST (props,
`body`):

- **PROPS** (`props.schema.json`): drawn in hand space: the hand at `[0, 0]`, y down, x away from the body,
  canvas pixels (the figure is 512 x 1024; built-in props span about -40 to 110). Pieces: `rect`, `circle`,
  `line`, `poly`, drawn in order.
- **SETS** (`sets.schema.json`): `indoor` (floor and back wall) or `outdoor` (floor and sky, allows travelling
  shots), with 3 to 12 pieces (`box`, `cyl`, `ball`, `mound`) in world units: actors stand at y 0, z 0, x -2 to 2;
  anything across the stage sits behind z -1; walls and far scenery are `backdrop`.
- **CREATURES** (`creatures.schema.json`): a rig (`humanoid`, `bird`, `quadruped`, `biped`, `crawler`) and its
  parts; a humanoid only has a `build` (proportions and skin colour). Give a creature that can lose its head a
  `stump` part.
- **ACTIONS** (`actions.schema.json`): keyframes for a humanoid's arms, legs and lean, used with `@do`.
- **WARDROBE** (`wardrobe.schema.json`): one item for a slot (`hair`, `facial_hair`, `headwear`, `top`,
  `legwear`, `footwear`, `back`, `accessory`, `face`): ink layers (`rect`, `circle`, `ellipse`, `line`, `poly`)
  each hung on a body anchor (`head`, `head_top`, `face`, `eyes`, `mouth`, `neck`, `shoulders`, `chest`, `waist`,
  `hips`, `back`, `arms`, `hands`, `legs`, `feet`), canvas pixels around it (head radius 150, body 184 x 300,
  legs 220), x across and y down; `"fill": "$color"` takes the worn colour; `"behind": true` draws it behind the
  head and body (long hair, capes). Paired anchors (shoulders, arms, hands, legs, feet) draw on both sides. Ids
  may use `_`. Worn in the CAST by id (section 6b).

- At most **2** new sets, **3** new props per part, **2** new creatures, **4** new wardrobe items. Ids are lowercase a-z, 0-9 and single
  dashes, never a built-in name; names are plain words, at most 40 characters.
- A new prop is needed for `eat`, `give`, or any object a character visibly uses or holds in a story action.

### How a character holds a prop

A prop shows in a character's hand only in these four ways (there is no other directive for it):

| Way | Held | Use it for |
|---|---|---|
| Cast JSON `"props": [{"kind": "axe", "hand": "right"}]` | In every scene of the series | Something they always carry (a clipboard, a cane) |
| A look with props, `"looks": {"axe": {"props": [{"kind": "axe", "hand": "right"}]}}`, switched on with `@look lloyd: axe` | From that line until the next `@look` for them (`@look lloyd: default` puts it away) | An object used for one scene or one moment |
| `@do bob: eat apple` | While eating, on that line | Food |
| `@do amy: give medal fred` | The giver hands it over on that line; the receiver keeps it for the rest of that set | Handing something over |

- At most two props at once, one per hand (`left` / `right`). A look's `props` replaces the character's own
  props while the look is on; `[]` means empty-handed.
- Only `humanoid` (people) and `biped` bodies have hands. A bird, quadruped or crawler cannot hold a prop,
  `eat` a prop or take part in `give`.
- Every held prop must exist: built in, in the library, or in the package's PROPS.

## 6b. Cast JSON (the package's CAST)

Design the whole cast and put it in the package's CAST as a JSON list, one entry per character, in this format
(the dashboard imports it when the series is created):

```json
[
  { "id": "lloyd", "name": "Lloyd", "color": "#3b6ea5" },
  { "id": "clara", "name": "Clara", "color": "#c0567a",
    "top": { "id": "dress", "accent_color": "#f2d16b" }, "headwear": { "id": "straw_hat", "color": "#e3c27a" },
    "hair": { "id": "long_hair", "color": "#8a4b2a" }, "face": ["blush"] },
  { "id": "nero", "name": "Nero", "color": "#f3efe2", "top": "toga", "hair": "short_hair", "footwear": "sandals",
    "looks": { "crowned": { "headwear": "crown", "back": { "id": "cape", "color": "#6b2a8a" } } } },
  { "id": "mike", "name": "Mike", "color": "#f2f2f2", "body": "chicken",
    "looks": { "headless": { "headless": true } } }
]
```

- `id`: lowercase a-z, 0-9 and single dashes, used in `@cast`, `@do` and `@look`. `name`: how the narration
  says it (the planner finds characters by name). `color`: `#rrggbb`, the outfit, or an animal's fur / feathers.
  Give every character a clearly different colour.
- **Body:** `"body": "<creature id>"`: a built-in (`human` humanoid, `chicken` bird, `cat` and `horse`
  quadruped, `monkey` biped, `snake` crawler), one listed under *Available in this library*, or one from the package's
  CREATURES. Left out, it is `human` (a person: the stickman).
- **Changes during the story:** never make a second character for the same one. Give it `"looks"`: named
  variants that set only what changes, used with `@look` (section 5): `{"headless": {"headless": true}}` for a
  lost head (creatures only), `{"prison": {"top": {"id": "plain", "color": "#e8e8e8"}, "headwear": "none"}}` for
  a change of clothes (a whole outfit at once; `"none"` takes an item off). A creature that is headless from the
  very start instead gets `"headless": true` on the entry itself.
- **Wardrobe** (people / humanoids; other bodies ignore it): each slot takes a wardrobe id, plain
  (`"hair": "wild_hair"`) or with a colour (`"hair": {"id": "wild_hair", "color": "#e8e8e8"}`), or `null` for none.
  Slots: `hair`, `facial_hair`, `headwear`, `top`, `legwear`, `footwear`, `back` (one item each) and `accessory`,
  `face` (a list of up to 3). Use the ids listed under *Available in this library* (each belongs to one slot), or
  design a new item in the package's WARDROBE. Built in: tops `plain`, `suit`, `tank`, `shirt`, `dress`;
  headwear `flat_cap`, `postman_cap`, `bowler`, `straw_hat`, `wide_hat`; legwear `shorts`, `ragged_shorts`,
  `trousers`. The top's colour is the body colour (the entry's `color`); `"top": "robe"` with `"color"` works.
  Extras on the top: `"accent_color"` (suit: the tie; dress: the wide hat's ribbon) and `"number": "31"` (chest
  number). The old `{"kind": ...}` / `{"style": ...}` forms still work. Items scale with any build and move with
  every pose and expression.
- Also optional: `"props": [{"kind": "clipboard", "hand": "right"}]` (always held, at most one per hand; for a
  prop held only in some scenes use a look, section 6),
  `"default_expression": "neutral" | "happy" | "sad" | "angry" | "surprised" | "sleepy" | "cheeky" |
  "exhausted"`, `"eyes": "dots" | "half_closed"`.
- Only characters the whole series shows. Keep ids short; at most 12 on stage at once (section 5).

## 7. How plain narration is interpreted

You do not need `@do` on every line. The planner reads the words:

- **Subject:** the first cast member *named* in a line is the subject; the others on stage turn to watch.
  If nobody is named, the previous subject stays.
- **Actions from verbs:** walked, went, came, left → walk; ran, rushed, chased, sprinted, sprinting → run;
  pointed, shows → point; waved, waving → wave; gasped, froze, shocked, collapsed, dizzy, cramps → react;
  staggered, stumbled, wobbled → stagger; lay, lying, napped → lie; fainted → collapse; ate, eating → eat.
  Anything else → talk.
- **Faces from mood words:** happy, smiled, laughed, grinned, joy → happy; sad, cried, sighed, tears, upset →
  sad; angry, mad, furious, yelled, shouted → angry; surprised, shocked, gasped, stunned, wow → surprised;
  sleepy, tired, yawned, asleep, exhausted → sleepy.
- **Travelling shots:** on an outdoor set, a line with a walk or run verb (and no `@do`, no car) becomes a shot
  where everyone moves and the world scrolls past.
- **Camera:** chosen automatically; never write camera instructions.

Use `@do` where the guess would be wrong, or for actions with no keyword (give, carry, support, cheer, a collapse
at an exact moment).

## 8. Common mistakes (each one fails or looks wrong)

| Mistake | Why it matters |
|---|---|
| Narration on a directive's line | The text is never read aloud; the directive is invalid |
| Cast id not in the series list | The shot planner stops |
| Unknown set, action or prop | The shot planner stops (a new set or prop must be in the package) |
| A wardrobe id in the wrong slot (`"hair": "crown"`) or not in the library / WARDROBE | The import refuses the cast |
| `@do` with no narration line right after it | It is ignored (reported as an error) |
| `@do` naming someone not in the current `@cast` | The shot planner stops |
| More than 12 in `@cast`, or more than 6 named in one scene | Not enough room on stage |
| `@car ride` with more than 3 in `@cast` | The car seats 3 |
| `@do car: broken` with no car on stage | Nothing to break down |
| Digits, symbols, abbreviations in narration | The voice and captions drift apart |
| Over 175 words, or over 58 seconds | Too long for a Short (the story check warns) |
| A date or backstory on line 1 | Viewers scroll away before the hook (the story check warns) |
| Line 2 or 3 spends the twist | The `!!` has nothing left to reveal |
| No flip in the first three lines | Viewers predict the story and scroll |
| Lines after the `!!` other than the end line | The payoff fades before the cut |
| Filler transitions ("Then", "After that", "So") | Dead air between beats |
| More than one `!!` | Only one twist per part |
| A key object named in narration but not listed as a prop | The action happens empty-handed and looks wrong |

## 9. Checklist before answering

1. Line 1 is `# Title`; every directive is alone on its line.
2. A `@set` comes before the first narration line.
3. Only cast ids, looks, sets, actions, props and creatures from this guide, *Available in this library* and your CAST, plus new sets,
   props, creatures and actions created by the package. Every id a SCRIPT uses exists in one of the two.
4. Every `@do` is directly followed by a narration line, and everyone in it is in the current `@cast`.
5. Each `@cast` has at most 12 ids, at most 6 of them named in that scene; `@car ride` at most 3.
6. No digits, symbols or markdown formatting in narration.
7. 110 to 175 words per part; short lines, no filler transitions.
8. The answer is one Story Package in one fenced `text` block and nothing else; markers alone on their lines, in
   order; `parts` in META matches the PART sections; every VOICE is its SCRIPT's narration word for word, without
   `@` lines, the title or `!!`.
9. CAST has every character of every part; asset sections hold only new items (`[]` when none).
10. Every object a character uses in a key action exists: built in, in the library, or in the package's PROPS, and
    it is attached to that character (cast `props`, a look, or `@do eat` / `give`).
11. Triple hook: line 1 Context (subject plus shock, at most twelve words), line 2 Lean (proof, stat or
    unexpected detail), line 3 Snapback (expectation flipped), at most thirty words together, twist not spent.

### Pre-publish checklist

- [ ] **Triple hook:** line 1 Context (subject plus shock, at most twelve words), line 2 Lean (proof, stat or
      unexpected detail), line 3 Snapback (expectation flipped), at most thirty words together, twist not spent.
- [ ] **Word count:** 110 to 175.
- [ ] **Key props:** every object central to an action is present (e.g. the axe in a beheading).
- [ ] **Single `!!`:** at most one twist line per part.
- [ ] **Ends on the twist:** the `!!` line is last, or second-to-last followed only by
      "To be continued." (every part but the last).
- [ ] **Runtime under 58 seconds:** words / 2.6, plus 1 for the end card.

## 10. Examples

### A complete part

Part one of a series: the triple hook on lines one to three (Context, Lean, Snapback), the date on line four, the
twist second-to-last, then "To be continued.". 133 words, about 52 seconds.

```md
# The Fake Finish

@set dirt_road
@cast fred
@car ride
The Olympic marathon winner rode most of it in a car.
He rode eleven miles in his manager's car.
Cheating should have ended his race. It didn't.
It was nineteen oh four, in Saint Louis, and the heat was brutal.
Fred had quit after nine miles.
@do car: broken
Eleven miles later, the car broke down.

@set stadium
@car off
@cast fred, daughter, sullivan
@crowd cheer
Fred stepped out fresh and jogged into the stadium.
@do daughter: give medal fred
The president's daughter handed him the gold medal.
@crowd angry
A spectator had spotted him in the car.
The crowd turned furious, and Fred was banned for life.

@set dirt_road
@crowd off
@cast thomas, trainer1, trainer2
@do thomas: stagger
Miles behind, Thomas was staggering through the dust.
@do trainer1, trainer2: support thomas
His trainers fed him egg whites and brandy to keep him moving.
He begged to lie down. They refused.

@set stadium
@cast thomas, trainer1, trainer2
@crowd cheer
@do trainer1, trainer2: carry thomas
!! Two men carried Thomas across the line, and he was crowned champion.
To be continued.
```

### A crowded scene (front and back rows)

```md
@set street
@cast troffea, husband, physician, councillor, musician, priest, dancer-1, dancer-2, dancer-3
Frau Troffea danced in the middle of the street.
Her husband begged her to stop.
The whole town watched in silence.
```

Troffea and her husband are named, so they stand in front; the other seven stand smaller in the back row.

### Wrong, then right

```md
@set streetA woman danced in the street for six days straight.   <- wrong: narration on a directive line
```

```md
@set street
A woman danced in the street for six days straight.
```

---

## Your series

- **What the story is about:**
- **Number of parts:**
- **Tone** (funny, eerie, dramatic...) and anything to avoid:
