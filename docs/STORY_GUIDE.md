# Writing stories for scribblefactory: a guide for AI assistants

Share this whole file with an AI (paste it, or attach it), fill in **Your series** at the end, and ask for a story.
The AI writes **part 1 only**, then waits until you ask for part 2 (and so on).
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
that already exist, by their **id**.

## 2. What to return

Write **one part per answer**: part 1 first. Stop after it and wait. Write part 2 only when the user asks for it
("part 2", "next part"), then part 3 the same way. Never write ahead or sketch later parts unasked.

Every answer has these parts, in this order:

1. **Series title**: one line, `**Series title:** <title>` (the same in every part).
2. **Short description**: two or three plain sentences: what the story is about and what this part covers,
   without giving away its twist.
3. **New sets, props and creatures**: only if this part needs one that does not exist yet: one fenced `text`
   block with the headings `NEW SETS`, `NEW PROPS`, `NEW CREATURES` in that order, each entry with its id and
   name (section 6). Leave out an empty heading, and the whole block when nothing is new. Every prop the
   story's key actions depend on is required (section 6), and must also be attached to the cast member who
   uses it (section 6, **How a character holds a prop**): in the cast JSON for a new series, and in the prop
   lines at the end of the answer.
4. **Cast JSON**: only when **Your series** has no cast yet (a new series), in part 1: one fenced `json` block
   with the whole cast in the format of section 6b (animals with `body`, changes like a lost head or picking up
   an axe as `looks`). It must include **every character of the whole series**, also those who first appear in
   later parts: the dashboard imports the cast only when the series is created, and adding characters later
   needs the command line. Leave it out when the cast already exists.
5. **The script**: one fenced `md` code block containing only the complete `story.md`: the `# Part title`
   line, every `@` directive and the narration (section 3).
6. **Audio script (TTS)**: one fenced `text` code block with only what the voice reads: the narration lines of
   the script, in order, one per line, with every `@` line, the `# title` line and the `!!` markers left out.
   Word for word the same as the script's narration: nothing added, removed or reworded (the voice is matched
   to the script word by word, so any difference breaks the captions and shots).
7. Three lines: `Words: <count>`, `Length: about <seconds> seconds` (words / 2.6, plus 1 for the end card),
   and `Cast: <ids used, comma-separated>`.
8. **Prop lines**: one line per required prop, after the three summary lines, saying which cast id holds it and
   how: `Prop axe: lloyd, look "axe" (@look lloyd: axe)`, `Prop clipboard: sullivan, always (cast props)`,
   `Prop apple: bob, @do eat`. For a series whose cast already exists, these lines tell the user what to add to
   the cast entry (a `props` entry or a look), since you cannot change it yourself.

Nothing else inside the blocks: no explanations, no comments. For example:

````text
**Series title:** The Chicken That Would Not Die

A farm rooster survives the axe and keeps living without a head. Part 1: the night it happens and the trip
to the university that cannot explain it.

```text
NEW PROPS
- id: axe | name: Axe | a wood-chopping axe: long brown handle, grey head with a silver edge, held at the handle end
```

```json
[
  { "id": "lloyd", "name": "Lloyd", "color": "#3b6ea5",
    "looks": { "axe": { "props": [{ "kind": "axe", "hand": "right" }] } } },
  { "id": "clara", "name": "Clara", "color": "#c0567a" },
  { "id": "mike", "name": "Mike", "color": "#f2f2f2", "body": "chicken", "looks": { "headless": { "headless": true } } },
  { "id": "scientist", "name": "Scientist", "color": "#7a8b99" }
]
```

```md
# The Chicken That Would Not Die

@set countryside
@cast lloyd, clara, mike
A chicken lived eighteen months without a head.
...
@look lloyd: axe
Lloyd grabbed a young rooster named Mike and swung his axe.
@look mike: headless
@look lloyd: default
...
```

```text
A chicken lived eighteen months without a head.
...
```

Words: 128
Length: about 50 seconds
Cast: lloyd, clara, mike, scientist
Prop axe: lloyd, look "axe" (@look lloyd: axe)
````

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

- **Length:** **110 to 140 words** per part (see **Target runtime** below).
- **Short sentences, one idea per line** (see **Pacing**). Every line becomes at least one shot; long lines are
  split into several shots automatically.
- **Write numbers as words:** "fifteen eighteen", "four hundred", "the third day". Digits break the word-by-word
  alignment between the voice and the text, and they make poor captions.
- **No symbols or abbreviations:** no %, &, $, "Dr.", "St.", "e.g.", no parentheses, no quotes inside quotes.
  Write what the voice should say.
- **Name characters by their name** as given in the cast list. The planner recognises names (and ids) to decide
  who the shot is about.
- Captions show at most five words at a time; plain wording reads best.
- **Hook first, twist last.** Line one is the hook (see **Hook**). The `!!` twist is the last or second-to-last
  narration line (see **Twist and ending**).

### Hook: the slap in the face

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
- **Line two hits again.** It grounds the claim (the date or place goes here) or raises the stakes; it never
  slows down to explain.

Hook patterns:

| Pattern | Example |
|---|---|
| The impossible fact | Victor sold the Eiffel Tower. Twice. |
| The wrong winner | The man who won the Olympic marathon rode most of it in a car. |
| The body count | A dance killed fifteen people a day. |
| The contradiction | The ship nobody could sink sank on its first trip. |
| The desperate act | Thomas drank rat poison to win a race. |

Never use these openers; they announce a hook instead of being one: "Did you know", "You won't believe",
"Imagine", "Let me tell you", "This is the story of", "Have you ever", or any question the viewer can answer "no".

**The test:** if the video stopped after line one, would someone repeat that sentence to a friend? If not,
rewrite it.

A hook line may use `@fx shake` or `@fx drop` for extra punch; that is the one place the effect is always worth it.

Before (slow, the date comes first):

```md
In nineteen twenty-five, a con man named Victor arrived in Paris.
He read that the Eiffel Tower needed costly repairs.
```

After (the claim comes first, the date follows):

```md
Victor sold the Eiffel Tower. Twice.
It was nineteen twenty-five, and the tower needed costly repairs.
```

### Pacing

- Short sentences. One idea per line.
- No filler transitions: never start a line with "Then", "After that", "So", "Next" or "Later". Cut straight to
  the next beat.
- Every line should move the story forward; if a line only sets up the next one, merge or cut it.
- Long pauses in the voice are trimmed automatically (any pause over 0.4 seconds becomes 0.3), so the delivery
  stays tight; the writing must be tight too.

### Twist and ending

- The `!!` twist line is the **last or second-to-last** narration line. Nothing comes after it except the end line.
- **Non-final parts** end with a short pointer line right after the twist, for example "Part two is on my
  profile." The video then shows "Part 2 on my profile" over the last second and cuts.
- **The final part** ends on the twist itself: no pointer line. The video cuts right after the last word.
- Each part should still make sense on its own.

### Target runtime

**45 to 58 seconds per part**, never over 58. The voice reads about 2.6 words a second, and every non-final part
adds a one-second end card, so 110 to 140 words lands in range. The dashboard's story check estimates the runtime
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
- A cast member can be a **creature** (an animal; **Your series** marks it, e.g. `mike: Mike (chicken, bird;
  looks: headless)`). Creatures have eyes and a mouth only, no facial expressions. By rig:
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

The target of give / carry / support cannot have its own action in the same `@do`.

### `@look <cast>: <look>`: change how someone looks

From the next narration line on, the cast member wears one of its named looks (listed in **Your series**, e.g.
`mike: Mike (chicken, bird; looks: headless)`) until another `@look` for them, for the rest of the part, across
`@set` changes. `@look mike: default` brings back their own look. Several at once: `@look amy, bob: wedding`.
Use it for a change the viewer should see: a lost head, a costume, a disguise, prison clothes, or an object in
hand (a look with props, e.g. `@look lloyd: axe`; section 6). Only looks listed for that cast member exist. A
new part starts in everyone's own look, so repeat the `@look` at its top if the change still holds.

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

Built in: `clipboard`, `stopwatch`, `bottle`, `syringe`, `apple`, `medal`. A series may define more (listed under
**Your series**). Only these can be used with `eat` and `give` or held by a cast member, plus new ones you list
(section 6). How a character holds one: section 6, **How a character holds a prop**.

### Creatures

Animal bodies for cast members (`"body"` in the cast JSON, section 6b), each on a rig that decides how it moves
(section 5, under `@cast`). Built in: `chicken` (bird), `cat` (quadruped), `horse` (quadruped), `monkey` (biped),
`snake` (crawler), or the id of a custom creature from the dashboard's **Creatures** page. Each has a `headless`
version (a neck stump) for a `"headless"` look. An animal that does not exist yet goes in the NEW block
(section 6).

## 6. New sets, props and creatures

- **Sets: prefer what already exists.** Add a new one only when no existing set fits the place.
- **Props: every key object is required.** Any object the narration names that a character uses to do a story
  action (a weapon, a tool, an instrument, a key object: an axe, a knife, a gun, a rope, a key, a letter, an
  eyedropper) must be in the video. If it is not built in or in the library (*Available in this library*), list
  it under `NEW PROPS`, even when no `@do` uses it, and attach it to the character who uses it (below). A
  farmer beheading a chicken needs an `axe`.
- **Creatures:** an animal cast member needs a creature body; add one only when none fits.

List anything new in a block **before the story**, then use its id in `story.md` and the cast JSON (sets,
props) or as a cast member's `body` (creatures):

```text
NEW SETS
- id: bakery | name: Corner Bakery | indoor | a small bakery with a glass counter, bread shelves on the back wall and a red awning window
NEW PROPS
- id: baguette | name: Baguette | a long golden loaf of bread, held at one end
NEW CREATURES
- id: dog | name: Dog | quadruped | a scruffy farm dog with floppy ears and a long tail
```

- At most **2** new sets and **3** new props per part. If the story needs more props, keep the 3 most
  important to the plot. Leave out a heading that has nothing under it, and the whole block when nothing is
  new.
- Every entry starts with `id:` and `name:`. The id is lowercase a-z, 0-9 and single dashes, used exactly as
  written in `story.md`, never a built-in name. The name is what the dashboard shows: plain words, at most 40
  characters.
- Sets: say `indoor` (back wall) or `outdoor` (sky, allows travelling shots), and describe the look in one line:
  the 3 to 6 big objects that make the place recognisable, and its main colours.
- Props: one line on shape and colour, and which end is held. A new prop is needed for `eat`, `give`, or any
  object a character visibly uses or holds in a story action.
- Creatures: say the rig (`bird`, `quadruped`, `biped`, `crawler`, section 5 under `@cast`) and describe the
  look in one line. Say if it needs a headless version (it then gets a neck stump). At most **2** per part.
- The user builds each one before rendering (dashboard **Sets** / **Props** / **Creatures**, *Build with AI*,
  with your id and name and the description); until then the story fails as "unknown set", "unknown prop" or
  "unknown body".

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
- Only people (stickmen) and `biped` creatures have hands. A bird, quadruped or crawler cannot hold a prop,
  `eat` a prop or take part in `give`.
- Every held prop must exist: built in, in the library, or in your NEW PROPS.

## 6b. Cast JSON (new series only)

When **Your series** has no cast yet, design it and return it as a JSON list, one entry per character, in this
format (the dashboard imports it when the series is created):

```json
[
  { "id": "lloyd", "name": "Lloyd", "color": "#3b6ea5" },
  { "id": "clara", "name": "Clara", "color": "#c0567a",
    "top": { "style": "dress", "accent_color": "#f2d16b" }, "headwear": { "kind": "straw_hat", "color": "#e3c27a" } },
  { "id": "mike", "name": "Mike", "color": "#f2f2f2", "body": "chicken",
    "looks": { "headless": { "headless": true } } }
]
```

- `id`: lowercase a-z, 0-9 and single dashes, used in `@cast`, `@do` and `@look`. `name`: how the narration
  says it (the planner finds characters by name). `color`: `#rrggbb`, the outfit, or an animal's fur / feathers.
  Give every character a clearly different colour.
- **Animals:** `"body": "<creature id>"`: a built-in (`chicken` bird, `cat` and `horse` quadruped, `monkey` biped,
  `snake` crawler), one listed under *Available in this library*, or one from your NEW CREATURES block. A person
  has no `body` (it means a stickman).
- **Changes during the story:** never make a second character for the same one. Give it `"looks"`: named
  variants that set only what changes, used with `@look` (section 5): `{"headless": {"headless": true}}` for a
  lost head (creatures only), `{"prison": {"top": {"style": "plain", "color": "#e8e8e8"}}}` for a change of
  clothes. A creature that is headless from the very start instead gets `"headless": true` on the entry itself.
- Optional costume for people: `"top": {"style": "plain" | "suit" | "tank" | "shirt" | "dress", "accent_color":
  "#rrggbb", "number": "31"}`, `"headwear": {"kind": "flat_cap" | "postman_cap" | "bowler" | "straw_hat" |
  "wide_hat", "color": "#rrggbb"}`, `"legwear": {"kind": "shorts" | "ragged_shorts" | "trousers", "color":
  "#rrggbb"}`, `"props": [{"kind": "clipboard", "hand": "right"}]` (always held, at most one per hand; for a
  prop held only in some scenes use a look, section 6),
  `"default_expression": "neutral" | "happy" | "sad" | "angry" | "surprised" | "sleepy" | "cheeky" |
  "exhausted"`, `"eyes": "dots" | "half_closed"`. Animals ignore costume.
- Only characters the story shows. Keep ids short; at most 12 on stage at once (section 5).

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
| Unknown set, action or prop | The shot planner stops (a new set or prop must be in the NEW block) |
| `@do` with no narration line right after it | It is ignored (reported as an error) |
| `@do` naming someone not in the current `@cast` | The shot planner stops |
| More than 12 in `@cast`, or more than 6 named in one scene | Not enough room on stage |
| `@car ride` with more than 3 in `@cast` | The car seats 3 |
| `@do car: broken` with no car on stage | Nothing to break down |
| Digits, symbols, abbreviations in narration | The voice and captions drift apart |
| Over 140 words, or over 58 seconds | Too long for a Short (the story check warns) |
| A date or backstory on line 1 | Viewers scroll away before the hook (the story check warns) |
| Lines after the `!!` other than the end line | The payoff fades before the cut |
| Filler transitions ("Then", "After that", "So") | Dead air between beats |
| More than one `!!` | Only one twist per part |
| A key object named in narration but not listed as a prop | The action happens empty-handed and looks wrong |

## 9. Checklist before answering

1. Line 1 is `# Title`; every directive is alone on its line.
2. A `@set` comes before the first narration line.
3. Only cast ids, looks, sets, actions, props and creatures from this guide and **Your series**, plus new sets,
   props and creatures listed in the NEW block (at most 2 sets, 3 props, 2 creatures).
4. Every `@do` is directly followed by a narration line, and everyone in it is in the current `@cast`.
5. Each `@cast` has at most 12 ids, at most 6 of them named in that scene; `@car ride` at most 3.
6. No digits, symbols or markdown formatting in narration.
7. 110 to 140 words; short lines, no filler transitions.
8. The answer has, in order, the series title, the short description, the NEW block (only if something is new),
   the cast JSON (new series only, animals with `body` and any change as `looks`), the script and the audio
   script (section 2), and
   the audio script is the script's narration word for word, without `@` lines, the title or `!!`.
9. Only the part that was asked for (part 1 unless the user asked for a later one).
10. Every object a character uses in a key action exists: built in, in the library, or in the NEW block, and it
    is attached to that character (cast `props`, a look, or `@do eat` / `give`), with a prop line for each.

### Pre-publish checklist

- [ ] **Hook in line 1:** the twist or most surprising claim, no date or backstory, at most twelve words,
      concrete, and it opens a question the `!!` answers.
- [ ] **Word count:** 110 to 140.
- [ ] **Key props:** every object central to an action is present (e.g. the axe in a beheading).
- [ ] **Single `!!`:** exactly one twist line.
- [ ] **Ends on the twist:** the `!!` line is last, or second-to-last followed only by the pointer line
      (non-final parts).
- [ ] **Runtime under 58 seconds:** words / 2.6, plus 1 for the end card.

## 10. Examples

### A complete part

Part one of a series: hook on line one, the date on line two, the twist second-to-last, then the pointer line.
125 words, about 49 seconds.

```md
# The Fake Finish

@set dirt_road
@cast fred
@car ride
The man who won the Olympic marathon rode most of it in a car.
It was nineteen oh four, in Saint Louis, and the heat was brutal.
Fred quit after nine miles and climbed into his manager's car.
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
Part two is on my profile.
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

## Your series (fill this in before asking)

- **Series title:**
- **What the story is about** (the AI writes part 1 first; ask for part 2 when you want it):
- **Cast** (`id: Name`, one per line; only these ids may be used; for an animal add its creature and rig, and
  list any named looks, e.g. `mike: Mike (chicken, bird; looks: headless)`). Leave it empty for a new series:
  the AI designs the cast and returns it as cast JSON (section 6b):
  - `id: Name`
- **Extra props** (beyond the built-ins), if any:
- **Tone** (funny, eerie, dramatic...) and anything to avoid:
