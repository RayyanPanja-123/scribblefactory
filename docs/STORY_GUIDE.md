# Writing stories for scribblefactory: a guide for AI assistants

Share this whole file with an AI (paste it, or attach it), fill in **Your series** at the end, and ask for a part.
Every rule below is what the software actually enforces; a story that follows it renders without edits.

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

- First, only if the story uses a set or prop that does not exist yet: one fenced `text` block listing them, each
  with its id and name (see section 6).
- Then one fenced `md` code block containing only the complete `story.md`.
- After the blocks, three short lines: word count, estimated length in seconds (words / 2.6, plus 1 for the end
  card), and the cast ids used.
- Nothing else inside the blocks: no explanations, no comments.

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
- A cast member can be a **chicken** (series.json `"body": "chicken"`, optionally `"headless": true`). A chicken
  walks, runs, staggers, pecks (`eat`), flaps its wings (react, cheer, angry, gasp, wave, point), sits down (`lie`,
  `collapse`), rides in the car and can be supported or carried. It has no hands: it cannot `give`, be given
  things, `carry` or `support`. When the chicken is the focus, the camera comes down to its height.

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
**Your series**). Only these can be used with `eat` and `give`, plus new ones you list (section 6).

## 6. New sets and props

Prefer what already exists. When the story really needs a place or an object that is not among the built-ins or
**Your series**, list it in a block **before the story**, then use its id in `story.md`:

```text
NEW SETS
- id: bakery | name: Corner Bakery | indoor | a small bakery with a glass counter, bread shelves on the back wall and a red awning window
NEW PROPS
- id: baguette | name: Baguette | a long golden loaf of bread, held at one end
```

- At most **2** new sets and **3** new props per part. Leave out a heading that has nothing under it, and the
  whole block when nothing is new.
- Every entry starts with `id:` and `name:`. The id is lowercase a-z, 0-9 and single dashes, used exactly as
  written in `story.md`, never a built-in name. The name is what the dashboard shows: plain words, at most 40
  characters.
- Sets: say `indoor` (back wall) or `outdoor` (sky, allows travelling shots), and describe the look in one line:
  the 3 to 6 big objects that make the place recognisable, and its main colours.
- Props: one line on shape and colour, and which end is held. A new prop is only needed for `eat` and `give`
  (or if a cast member should hold it).
- The user builds each one before rendering (dashboard **Sets** / **Props**, *Build with AI*, with your id and
  name and the description); until then the story fails as "unknown set" or "unknown prop".

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

## 9. Checklist before answering

1. Line 1 is `# Title`; every directive is alone on its line.
2. A `@set` comes before the first narration line.
3. Only cast ids, sets, actions and props from this guide and **Your series**, plus new sets and props listed
   in the NEW block (at most 2 sets, 3 props).
4. Every `@do` is directly followed by a narration line, and everyone in it is in the current `@cast`.
5. Each `@cast` has at most 12 ids, at most 6 of them named in that scene; `@car ride` at most 3.
6. No digits, symbols or markdown formatting in narration.
7. 110 to 140 words; short lines, no filler transitions.

### Pre-publish checklist

- [ ] **Hook in line 1:** the twist or most surprising claim, no date or backstory, at most twelve words,
      concrete, and it opens a question the `!!` answers.
- [ ] **Word count:** 110 to 140.
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
- **Part number and what happens in it:**
- **Cast** (`id: Name`, one per line; only these ids may be used):
  - `id: Name`
- **Extra props** (beyond the built-ins), if any:
- **Tone** (funny, eerie, dramatic...) and anything to avoid:
