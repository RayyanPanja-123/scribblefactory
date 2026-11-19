# Making a video

From an idea to a posted short. The dashboard does every step; the CLI equivalent is given where it helps.
CLI: `.venv/Scripts/python -m pipeline.scribble.cli <command>` (`.venv/bin/` on macOS/Linux), written `cli` below.

## 0. Start

```sh
bash scripts/serve.sh      # http://127.0.0.1:8765
```

## 1. Series and cast (once per story)

1. Dashboard: **Series → New series**. Give a slug (`marathon-1904`), a title and the cast. Paste cast JSON
   (shape: `web/public/cast-reference.json`) or add people one by one.
   CLI: `cli new-series <slug> --title "..."`, `cli cast-add <slug> <id> --name Fred --color "#3a7bd5"`,
   then `cli cast-edit <slug> <id> --top suit --headwear flat_cap --props "medal:right" ...`.
2. Custom props (anything beyond clipboard, stopwatch, bottle, syringe, apple, medal): **Props** page.
   Custom sets (places beyond the seven built in, e.g. a kitchen or a beach): **Sets** page. A set is a floor, a back
   wall or sky, and simple pieces (boxes, cylinders, balls, mounds) with a live preview; *Build with AI* drafts one.
   Saved in library/sets.json, shared by every series; stories use it by id (`@set kitchen`).
3. **Cast**: the series page shows one card per character (its idle pose). *Render* draws that character in every
   pose (`cli cast-sheet <slug> <id>`; no id: everyone); click the picture to check them all, then *Approve*
   (`cli approve-cast <slug> <id>`). *Edit* opens the character page (props, wardrobe, body, live preview). A new look
   clears the approval and only that character needs a re-render before it can be approved again.

## 2. Write story.md

**Series → New part** (`cli new-part <slug> --title "..."`), then write `library/<slug>/part-NN/story.md`.
Plain text is the narration. Lines starting with `@` are directives: never read aloud, they steer the shots.
`# Title` lines and markdown syntax are dropped from the narration too. Aim for 50-70 s (about 150 words a minute).

### Directives

One per line. A directive holds until it is changed, except `@do` and `!!`, which cover only the next line.

| Directive | What it does | Example |
|---|---|---|
| `@set <name>` | Set for the following lines: room, office, street, dirt_road, countryside, orchard, stadium, or a custom set from the Sets page. Default room. A set change resets `@crowd` and `@runners`. | `@set stadium` |
| `@cast a, b` | Cast on stage (ids from series.json). Default: the first two cast members. Up to 6 stand in one row; with more (up to 12), whoever the scene's lines name or `@do` directs stands in front and the rest stand behind in the gaps, smaller and idle. For a big group, use `@crowd`. | `@cast fred, daughter` |
| `@dogs N` | Dog pack (0-6). Travel shots: they chase. Otherwise they idle or bark at the edges. | `@dogs 3` |
| `@car <mode>` | `arrive` (drives in, parks beside the subject), `ride` (the @cast ride, max 3; travel shot outdoors), `leave` (drives off), `off`. | `@car ride` |
| `@do <cast>: <action> ...` | Overrides the guessed action for every shot of the next line. Actions: idle, talk, walk, run, point, react, wave, stagger, lie, collapse, eat [prop], give &lt;prop&gt; &lt;target&gt;, carry &lt;target&gt; (2 carriers), support &lt;target&gt; (1-2), cheer, angry, gasp; and `car: broken`. Several clauses: comma-separated. | `@do trainer1, trainer2: carry thomas` |
| `@crowd <mood> [N]` | Crowd extras behind the stage: cheer, angry, gasp or neutral; N 1-12 (default 8). `@crowd off`. Not in travel shots. | `@crowd cheer 10` |
| `@runners N` | Background runners (0-6): run along in travel shots, cross the background otherwise. | `@runners 4` |
| `@fx <effect>` | Caption effect for the next line: drop, shake, pop or none. | `@fx shake` |
| `@fx lightning [target]` | One lightning strike (bolt + brief flash) at the next line, beside a cast id on stage or whoever holds a prop id. At most 3 per part. | `@fx lightning poseidon` |
| `@weather <type> [intensity]` | clear, rain, snow, fog, wind or storm; light, medium or heavy (default medium). Until the next `@weather` or `@set`; a `@set` starts the set's default weather (custom sets), else clear. | `@weather storm heavy` |
| `!! text` | The twist line: push-in with roll, music stops, low hit. The text is read aloud. | `!! And he won gold.` |

Example:

```md
# The Fake Finish

@set dirt_road
@cast fred
@car ride
After riding eleven miles in a car, Fred rejoined the marathon.

@do car: broken
His car broke down just outside the stadium.
@set stadium
@car off
@cast fred, daughter
@crowd cheer
@do daughter: give medal fred
He jogged across the line and accepted a gold medal.
!! It was all a joke.
```

Without `@do`, actions and expressions are guessed from the words (walked, ran, waved, laughed, shocked...).

Having an AI write the series: Story Writer gives it the story guide; paste back its
[Story Package](story-package.md) to create everything at once.

## 3. Check the story

Part detail → **Check story**, or `cli check-story <slug> <part>` (exit 0 = ready, 1 = problems).
It lists, with line numbers: unknown directives, cast ids, sets, actions and props; `@do` conflicts (actor not on
stage, `@do` during `@car ride`, `car: broken` with no car, an `@do` with no line after it); cast not approved yet;
and words changed since the voice was recorded. Fix everything before making the voice.

## 4. Voice

1. **Run next** runs `prep`, which writes `script-for-tts.txt` (the narration without directives).
2. Paste it into freetts.ai with the series voice, download the mp3.
3. Part detail → Voice → **Upload mp3** (or save it as `part-NN/voice.mp3`). An import check runs.

Edited story.md after recording? Check story tells you which words no longer match: re-record, or undo the edit.

## 5. Dashboard flow

**Run next** queues every automatic step up to the next thing only you can do, and says where it stops.
Progress shows live in the jobs drawer. The stops, in order:

1. **Cast approval** (if a new cast member appears): cast sheet, then approve.
2. **Stills approval**: one still per shot on the light table. Approve the stills, or fix story.md and run again.
3. **Final approval**: Run next renders all frames (parallel, resumable: a crash or restart continues where it
   stopped), adds music and sound effects, burns in captions, runs QA (qa.json) and makes three thumbnails.
   Watch final.mp4 to the end and check the QA card, then approve the final.

Optional: **Test render (5 s)** in the part's Tools renders a 5 s clip with voice before the full render (a new
machine, a new set, a sync worry). It never blocks anything; approving it is optional too.

Any stage can be re-run from its chip menu. Captions on or off: `cli set-captions <slug> on|off`, then re-run finish.

## 6. Thumbnail, upload text, posting

1. Light table: click a polaroid to pick the thumbnail (`cli pick-thumbnail <slug> <part> 1|2|3`).
2. Edit **upload.md** (title, description, hashtags) in the browser; Ctrl+S saves.
3. Upload final.mp4 to YouTube Shorts and Instagram Reels by hand.
4. **Mark posted** with each link (`cli mark-posted <slug> <part> youtube --url https://...`).

## 7. Cleaning up

Rendered frames are large (about 1-2 GB a part). final.mp4 does not need them.

- **Automatic**: approving the final deletes everything that only made final.mp4: `frames/`, `audio/` (music,
  sfx and mix stems), preview.mp4, test-render.mp4, captions.ass and end-card.png. Kept: final.mp4, qa.json, voice.mp3,
  story.md, script, phrases.json, story.json, thumbs/, upload.md, the stills sheet. Changing the video afterwards
  means rendering it again. Approved before this existed, or the cleanup was skipped: `cli cleanup <slug> <part>`.
- Frames only, before approving: Disk card → **Clean frames** (`cli clean-frames <slug> <part>`), once finish is done.
- Every posted part: `cli clean-frames --posted [<slug>]` lists what it would delete (approved final, posted on
  both platforms); add `--yes` to delete. It prints the space freed.

A later re-render needs the frames again (it re-renders them all).

## Deleting

- A part: part page → Disk → **Delete part** (`cli delete-part <slug> <part> --yes`; without `--yes` it only
  lists what would go). Its whole folder goes: story.md, voice.mp3, videos, frames. Other parts keep their numbers.
- A series: series page → **Delete series** (`cli delete-series <slug> --yes`). Every part, the cast and its sheet.
  Custom props (library/props.json) and sets (library/sets.json) are kept.
- Both are refused while a job is queued or running on it. Neither can be undone.

## When something goes wrong

- A stage failed: its chip turns red; hover for the error, fix, re-run.
- The API was stopped mid-job: on restart, queued jobs resume, the interrupted job and stage are marked failed
  ("interrupted"), and leftover render browsers are stopped. Run next continues from there.
- `cli status <slug>` prints every part's stages, approvals and posts (and fixes stages stuck at running).
