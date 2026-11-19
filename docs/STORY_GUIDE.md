# scribblefactory story guide (for AI assistants)

## Never
- Formatting while brainstorming (images, cards, tables, headings): plain short chat only.
- Scripts, cast or assets before the story (premise, parts, twists) is agreed.
- The Story Package before the user says "approved".
- Rename, reorder, skip `<<<...>>>` markers; split the package; text around it.
- Ids not in the inventory list, section 4, or the package.
- Digits, symbols or markdown in narration; narration on a directive line.
- Flat scripts (one `@set`, few directives).
- Characters by role ("the commander"): use their cast `name`.

## What this makes
- Each part = one vertical Short: a voice reads the narration, a planner turns each line into stickman shots in 3D.
- `@` lines are silent directives.

## 1. Workflow
1. Brainstorm: premise, cast, parts; per part its hook, rehook and twist (section 3). A few short lines, one or two
   questions at a time.
2. Sum up the plan as a short list (per part: hook, rehook, twist); wait for "approved".
3. Ask for the inventory list ("Please paste your library list: the Copy library list button in Scribble Factory"); wait for it.
   - It has every set, prop, creature, action, wardrobe item, sound and existing cast by id. Never guess ids.
4. Reply with only one Story Package in one fenced `text` block (full rules: **Story Package format**, at the end):

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

   - Markers exactly as shown, alone on their line, in order, none skipped; empty sections `[]`.
   - Asset sections: only new items.
   - CAST: every character of the whole series.
   - VOICE: its SCRIPT's narration word for word, one line each; no `@` lines, title or `!!`.
5. User pastes back `staging:` warnings: fix every one that fits; resend the whole package.

## 2. Script format
- Line 1 `# Title`, then a blank line.
- One directive per line, alone.
- `@do`, `@face`, `@fx`, `@sfx`: next narration line only (one must follow). Others last until changed.
- Narration: plain text, numbers as words; no digits, symbols, abbreviations, parentheses, markdown.

## 3. Writing rules
- 110 to 175 words (aim under 145); at most 58 s (words / 2.6, plus 3 s for non-final parts).
- Short lines, one idea each. Never start with Then, After that, So, Next, Later.
- Every part runs three curiosity loops, then the twist:
  1. **Hook loop** (first 5 s, about 13 words): opens the question the part answers. If it misses, nothing else counts.
     - Line 1: name or noun + shocking claim, at most 12 words. No date, setting, question, "Did you know", "Imagine".
  2. **Intensifier loop** (next ~15 s, to about word 50): doubles down on the hook; every line raises the stakes.
     - Line 2: proof (a number, cost, odd detail).
     - Line 3: flip an expectation ("X should have ended it. It didn't.").
     - Lines 4 on: escalate (worse, bigger, stranger). No backstory, setup or calm lines here.
     - Lines 1 to 3: at most 30 words; never reveal the twist.
  3. **Rehook loop** (halfway, around word 55 to 75): just as curiosity fades, open a new question: a reversal, a new
     threat, a strange detail, a character doing something unexpected. One line, concrete, never the twist itself.
- Exactly one `!! <line>` (the twist), last: it pays off the hook's question. Non-final parts then end with
  `To be continued.`

## 4. Library basics
- Sets: `room`, `office` (indoor); `street`, `dirt_road`, `countryside`, `orchard`, `stadium` (outdoor). All modern.
- Props: `clipboard`, `stopwatch`, `bottle`, `syringe`, `apple`, `medal`.
- Bodies: `human` (default), `monkey` (biped), `chicken` (bird), `cat`, `horse` (quadruped), `snake` (crawler).
- Only humanoid and biped bodies have hands (hold, eat, give, carry, support).
- Everything else: the inventory list.

## 5. Directives
- `@set <id>`: place for the following lines; resets `@crowd`, `@runners`. Required before the first line.
- `@cast a, b`: who is on stage; named / `@do` ones in front. Max 12, max 6 named per scene.
- `@do <cast>: <action> [prop] [target]`: they act through the next line. Must be in `@cast`.
- `@look <cast>: <look>`: switch on a look from their CAST entry (held spear, crown). `default` restores; resets each part.
- `@face <cast>: <expression>`: face for the next line: `neutral happy sad angry surprised sleepy cheeky exhausted worried`.
- `@car arrive | ride | leave | off`: drives in and parks / carries the cast (travel shot) / drives off / gone.
  `ride` seats max 3; no `@do` during `ride` except `car: broken`.
- `@dogs N` (0 to 6): dog pack; chases on travel shots, else idles or barks.
- `@runners N` (0 to 6): background runners; run along on travel shots, else cross behind.
- `@crowd cheer | angry | gasp | neutral [N]`, `@crowd off`: extras behind the stage (army, mob). N 1 to 12, default 8;
  not on travel shots.
- `@fx drop | shake | pop`: next line's caption animation. Sparingly.
- `@fx lightning [cast | prop]`: bolt and flash beside that character or the prop's holder. Max 3 per part.
- `@weather clear | rain | snow | fog | wind | storm [light | medium | heavy]`: until the next `@weather` or `@set`.
  After its `@set`.
- `@sfx <id> [volume 0-1]`: sound on the next line. Max 5 per part; never on back-to-back lines.
- `!! <line>`: the twist: push-in, music stops, low hit; read aloud.

`@do` actions:
- `idle talk point react wave cheer angry gasp walk run stagger lie collapse`
- `eat [prop]`, `give <prop> <target>`, `carry <target>` (exactly 2 carriers), `support <target>` (1 or 2)
- `car: broken` (car on stage)
- Custom actions, optionally aimed: `@do marcus: attack-with-spears neptune` (faces and moves toward them)
- Several: `@do fred: lie, amy: wave`

### Staging (required: the video shows only what directives and names tell it)
- New place, new `@set`, then a fitting `@weather`: `storm` sea, gods, war, villains; `rain` loss; `fog` mystery;
  `snow` / `wind` journeys.
- Match the era: built-in sets are modern. Past stories use a period set from the inventory, or add one under SETS.
- Name a cast member in every line (the planner picks who acts by name).
- Faces:
  - A line's first mood word (angry, laughed, sobbed, gasped, scared...) sets the named character's face; each later
    mood word switches it ("grinned, then screamed" = happy, then angry).
  - No mood word: `@do angry | gasp | react | cheer` or `@face`.
  - Otherwise the default face shows: every emotional beat needs one of these.
- A `@do` every second or third line.
- Groups: `@crowd` with the right mood; `@dogs`, `@runners` where they fit.
- Objects are seen: props held through a `@look` switched on when used.
- Punch: `@fx shake` or `drop` on line 1 (hook), `@fx pop` on line 3, `@fx drop` or a `@sfx` (`camera_flash`,
  `metallic_riser`) on the rehook line, `@fx lightning` on one to three big beats.
- Ten or more directives besides `@set` and `@cast`.
- Use the inventory: follow "use for" notes, switch on cast looks, give characters their custom actions (a god raises
  a trident before `@fx lightning`).

### Sound effects
- Real ids and purposes: inventory list. Defaults:
  - `fahhh`: the hook (plays after its line)
  - `camera_flash`: smooth transition
  - `metallic_riser`, `riser`: tension before a payoff (end as the line starts)
  - `right` / `wrong`: positive / negative
  - `vine_boom`: comedy only
  - `bass_impact`: weight before the main reveal
  - `core`: a statement, emphasis
  - `among_us`: unexpected reveal (traitor, fake)
  - `pop` / `click`: pop-up text, UI
  - `glitch`: transition between clips
  - `money`: money moments only
- `@sfx` goes directly above its narration line (next to `@do` / `@fx` is fine). Volume overrides: `@sfx riser 0.6`.
- Risers only right before a payoff, usually the `!!` line.
- Default: `fahhh` on line 1 of part 1; `riser` + `bass_impact` (or `among_us`) on the twist.

## 6. New items
- Every object a character uses must be a held prop: cast `"props"`, a `@look` with `"props"`, or `@do eat` / `give`.
  One per hand (`left` / `right`).
- Add sets, creatures, wardrobe only if nothing fits.
- Max per package: 2 sets, 3 props per part, 2 creatures, 4 wardrobe items.
- Ids: lowercase a-z, 0-9, dashes; not built-in names.
- Follow the **Library item schemas** at the end.
- Props: hand at `[0,0]`, y down, canvas px (about -40 to 110).
- Long props (staff, spear, trident, flag): `"angle"` in clock-hand degrees, top tipped away (`30` = one o'clock),
  and a `"grip"` where the hand holds. Per character: `"props": [{"kind": "trident", "hand": "right", "angle": 30}]`.
- Sets: actors at y 0, z 0, x -2 to 2; scenery behind z -1.

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

- Distinct `color` each; `body` defaults to `human`.
- Changes during the story are `"looks"` (only what changes; `"none"` removes an item), never a second character.
- Wardrobe slots (humanoids): `hair`, `facial_hair`, `headwear`, `top`, `legwear`, `footwear`, `back`; lists of up to
  3 for `accessory`, `face`. Each id fits one slot.
- Built-in wardrobe: tops `plain suit tank shirt dress`; headwear `flat_cap postman_cap bowler straw_hat wide_hat`;
  legwear `shorts ragged_shorts trousers`.
- Optional: `"default_expression"` (`neutral happy sad angry surprised sleepy cheeky exhausted`), `"eyes"` (`dots`,
  `half_closed`).

## 7. Example (copy the staging, not the story)
- Cast: `fred`, `thomas`, `alice`, `hugh`; `charles` with look `bottle` (`{"props": [{"kind": "bottle", "hand": "right"}]}`).
- 131 words, a name in every line, 24 directives besides `@set` and `@cast`.
- Loops: hook = line 1 (car); intensifier = lines 2 to 5 (eleven miles, should have ended, breaks down, fresh);
  rehook = line 7 at word 68 (a strange drink); twist = the `!!` line.

```md
# The Fake Finish

@set dirt_road
@weather wind light
@cast fred
@car ride
@fx shake
@sfx fahhh
Fred won the Olympic marathon by riding most of it in a car.
Fred rode eleven miles while Thomas ran in the heat.
@fx pop
@face fred: cheeky
That should have ended Fred. It didn't.
@do car: broken
Eleven miles later, the car broke down and Fred laughed.
@car off
@cast fred, thomas, charles
@do fred: run
Fred jogged the last few miles, fresh as a daisy.
@do thomas: stagger
Behind him, Thomas staggered and begged Charles for water.
@look charles: bottle
@do charles: give bottle thomas
@sfx metallic_riser
Charles refused and gave Thomas a strange drink instead.

@set stadium
@weather clear
@cast fred, alice, thomas, charles, hugh
@crowd cheer 8
@do fred: cheer
Fred jogged into the stadium, and the crowd roared for him.
@do alice: give medal fred
Alice handed Fred the gold medal with a proud smile.
@crowd angry 8
@do alice: point
A furious spectator shouted that Fred had ridden in a car.
@face fred: surprised
Fred froze, and the cheering turned to boos.
@do thomas: collapse
Thomas collapsed a mile from the finish.
@sfx riser
@sfx bass_impact
@do charles, hugh: carry thomas
!! Charles and Hugh carried Thomas across the line, and he was crowned champion.
To be continued.
```

## Your series
- **About:**
- **Parts:**
- **Tone / avoid:**
