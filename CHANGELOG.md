# Changelog

## Unreleased
- Weather: `@weather <clear | rain | snow | fog | wind | storm> [light | medium | heavy]` until the next `@weather`
  or `@set` (a `@set` starts the set's new `default_weather`, else clear), drawn in ink: rain streaks, scribble
  snowflakes, hatched fog bands behind the cast, wind lines; storm adds slanted rain, a darker tint and mild
  ambient flashes. Changes within a scene fade over 0.5 s. Seeded and pooled, so stills, test renders and the
  final match. `@fx lightning [cast | prop]`: one bolt + brief flash at the next line, beside its target, at most
  3 per part. Set editor: default weather and a preview toggle. Story check, package import, Story Guide, package
  doc and Help cover both.
- Wardrobe page: clothing, hair and cosmetics as library items (library/wardrobe.json), worn per slot (hair,
  facial_hair, headwear, top, legwear, footwear, back, accessory, face) as `"hair": "wild_hair"` or
  `{"id", "color"}`. Ink layers anchored to body points scale with any humanoid build and move with every pose;
  `when` layers follow expressions. The original tops, headwear and legwear are built-in items with the same ids
  and draw exactly as before. 23 starter items, a live editor (human + a humanoid creature, any pose), Build with
  AI, a `@look` swaps a whole outfit (`"none"` takes an item off), and the Story Package gains `<<<WARDROBE>>>`.
- Tighter pacing for Shorts / Reels: timing clamps every pause over 0.4 s to 0.3 s and writes voice-tight.wav
  (voice.mp3 untouched); phrases, shots, audio and the preview all follow the tightened voice.
- End card: non-final parts end with "Part n+1 on my profile 👆" over the last second, then a hard cut; the final
  part (series complete, last part) cuts 0.3 s after the last word. Replaces ending on "To be continued.".
- Runtime guard: QA records runtime and word count in qa.json and the dashboard warns above 58 s with the overage;
  check-story estimates runtime from the words per second of past renders (2.6 before any) and warns too.
- check-story warns when the first narration line opens on a date or backstory ("In nineteen...", "Once upon").
- Story Guide: 110 to 140 words, 45 to 58 s, Hook and Pacing sections, the twist last or second-to-last, a
  pointer line instead of "To be continued.", a pre-publish checklist, and an updated example.
- Sets page: custom `@set` locations (library/sets.json, shared by every series). Indoor or outdoor, floor and
  wall/sky colours, box/cylinder/ball/mound pieces, a live preview built by the engine, and Build with AI.
  Stage clearance and travel shots work as for the built-in sets; a set in use by a story can't be deleted.
- Part page: a Next step card names the one thing to do and does it in place (replaces Run next).
- Approving a final cleans the part up: frames, audio stems, preview, test render and captions.ass are deleted
  (final.mp4, voice, story, thumbnails and upload text kept); `cleanup <slug> <part>` does it by hand.

## v1.0.0 (2026-11-17)

First complete version: a story.md and a voice.mp3 in, a captioned, QA-checked final.mp4 out, run from one dashboard.
Build steps as in docs/brief.md.

### Step 1: repo skeleton
- Repo layout (engine, pipeline, api, web, library, docs), idempotent `setup.sh` (checks, venv, Whisper model,
  npm installs, Chromium), pinned Node 20.19 and Python 3.12, locked Python dependencies.

### Step 2: schemas
- series.json and part.json pydantic models with atomic writes (temp file, fsync, replace with retry) that never
  drop an approval or overwrite story.md / voice.mp3; JSON schemas generated into docs/schemas.

### Step 3: CLI
- `new-series`, `new-part`, `status` (stages, approvals, posts, orphan folders), `cast-add`, `set-voice`, `set-style`;
  safe recovery from interrupted runs.

### Step 4: pipeline stages
- Stage runner: status, timestamps and inputs hash in part.json; skips stages whose inputs are unchanged.
- `prep` (story.md to script-for-tts.txt, word count, duration estimate), `import_check` (plays, duration, silence).
- `timing`: local faster-whisper, aligned to the script words, natural phrase breaks.
- story.json format and validator (shot length, no repeated angles, always-creeping camera, facing, gait, speeds).
- Rule-based, seeded shot planner: lexicon for actions and expressions, plural subjects, position carry-over.

### Step 5: render engine
- Three.js r160 world in headless Chromium: marker-drawn stickman cards, toon-shaded sets with ink outlines, camera
  moves, establishing wide shots, contact shadows; cast sheet and stills contact sheet; approvals.
- 5 s test render; full render in parallel chunks, resumable, GPU with SwiftShader fallback; long-lived workers,
  render lock and process-tree cleanup.

### Step 5b: sound and finish
- Synth music and sound effects from cues, mixed under the voice to -14 LUFS / -1 dBTP.
- `finish`: final.mp4 with burned-in captions (pop, drop, shake, punch effects) and QA (resolution, fps, frame
  count, duration, frozen and black frames, loudness, captions) to qa.json.
- Thumbnail candidates, upload.md, `pick-thumbnail`, `mark-posted`, `clean-frames`, `set-captions`.

### Step 5c: content library
- Cast v2: tops (plain, suit, tank, shirt, dress), accents, chest numbers, headwear, legwear, held props, default
  expressions; custom props shared across series (props page, editor, prompt for AI drawing).
- Sets: dirt road, countryside, orchard, stadium, with marker-wipe transitions; travel shots with a scrolling world.
- Dogs (`@dogs`, chase packs), car (`@car` arrive / ride / leave, breakdown), crowd and runner extras
  (`@crowd`, `@runners`).
- Actions: wave, stagger, lie, collapse, eat, give / receive, carry / carried, support / supported, cheer, angry,
  gasp; `@do` to set them per line.

### Step 6: web dashboard
- FastAPI backend: reads, media with Range requests, actions behind the CLI's gates, one-worker job queue, live
  progress over SSE, OpenAPI export.
- Vue 3 dashboard: overview, series and part pages, Run next, jobs drawer, light table, approvals, QA, upload.md
  editor, posting tracker, review and posted tabs; create series and parts, import cast JSON, upload the voice.

### Step 7: polish and QA
- One-command app: `scripts/serve.sh` builds the web app when stale and serves it from FastAPI on one port;
  `scripts/dev.sh` runs API and Vite together.
- Restart safety: jobs persist to library/.jobs.json and resume; interrupted jobs and stages are marked failed;
  leftover render workers are stopped on API start.
- `check-story` (CLI, API, dashboard button): directives, cast, sets, actions, props, @do conflicts, cast
  approvals and changed words, with line numbers, before any voice exists.
- `clean-frames --posted` (dry run by default), small cached cover JPEGs on the dashboard.
- docs/USAGE.md, docs/backlog.md, README quick start; fresh-clone test with a full end-to-end render.
- Fixes from the fresh-clone run: the audio mix of a peaky voice reached only -14.6 LUFS (loudnorm stops at the
  peak ceiling), now its peaks are limited and the try nearest -14 LUFS is kept; the CLI no longer crashes printing
  a non-cp1252 character to a redirected Windows console.
