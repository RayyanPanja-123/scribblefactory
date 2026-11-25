# Changelog

## Unreleased
- Shots for cast lines (Phase B3). In a story with `kai: line` lines, the speaker is the subject and talks (only
  they move their mouth), everyone else turns to them, and on a narrator line nobody talks (keyword actions and `@do`
  still apply; the narrated subject stays framed). A back-and-forth between cast members plays in one held wide shot
  instead of a cut per voice; a twist or `@cam` still cuts. story.json gets `speech` (each cast line's words and
  speaker) for speaker name tags later. check-story warns when a speaker is not on stage. Stories without cast lines
  plan byte-identically (golden plans unchanged); no engine change.
- Voice timing (Phase B2): `@pause <0-3 s>` before a line sets the silence before it, `@pace slow | fast` speaks
  the next line at 0.85x / 1.15x its voice's speed (TTS parts only; check-story warns on a recorded one). The tts
  stage trims each clip's edge silence so the gap between lines is the gap asked for, and timing keeps those gaps
  (it still shortens long pauses inside a line). A phrase never spans a change of speaker. A recorded voice without
  speaker lines times exactly as before (phrases.json and voice-tight.wav re-made byte-identical on a library copy).
- Voice: cast members speak their own lines (Phase B1). In story.md, `kai: Everyone alive?` (quotes optional,
  `!! kai: ...` for a spoken twist) is Kai's line; every other line is the narrator's. In a TTS part each line is
  made in its speaker's voice (`cast-voice <slug> kai am_adam [--speed 1.1]`; a speaker without one is read by the
  narrator, with a check-story warning) and voice-tts.json names each line's speaker. check-story: a speaker that is
  no cast id, or a voice the server does not have, is a problem. A cast voice is not part of the look (no new
  approval) nor of the series hash. Stories without speaker lines plan and render byte-identically; who moves their
  mouth on a spoken line comes in B3.
- Voice: TTS voices from the in-house Kokoro server (Phase A, single narrator). A part with
  `set-voice-source <slug> <part> tts` gets a new `tts` stage: one clip per story.md line, fetched as one job from
  the server's `/v1/jobs` API (polled; up to 500 lines a job) and cached in `library/_tts-cache` (key: text, voice,
  speed, the server's model and voices hashes, `tts_model_tag`; a new model makes new clips by itself, a fully
  cached script needs no server), joined with `tts_line_gap` silence into
  voice.mp3; every later stage runs as for an upload. A recording already there is kept as voice-recorded.mp3, and a
  server that is down leaves the part untouched. Narrator: `set-voice <slug> --tts am_adam --speed 1.1` (else
  settings `tts_voice`); server: `tts-settings --url http://host:port`; `tts-voices` (the server's 50 voices),
  `tts-cache-prune`.
  Recorded parts, plans and frames are byte-identical (the narrator voice is left out of the series hash).
- World Items: sky lock. In a low angle, sky-layer items (sun, planet) rise to stay high in the sky instead of
  sinking toward the cast (`STYLE.items.skyLock`, 0 = off). Only the sky layer; sets without sky items render as before.
- Story: a walk word moves only a character the phrase names, or one a pronoun points back at ("the saucer came
  back" walks nobody; "he came back" walks the last named). check-story warns on pronoun walks only. No library
  part's plan changes.
- Story: several `@do` lines before one narration line all apply (each to different characters or items; the same
  one twice is an error, "two @do for bob on one line"), instead of the last one replacing the others. A walk word
  that starts a walk or a travel shot gets a check-story warning (`@do <cast>: idle` stops it); nobody seated or
  inside an item walks from a word. A walk over several shots of one sentence keeps its direction (it used to turn
  back on each new shot). Item flights are capped at 4 units/s (`@do ship: fly left slow | fast`: 2 / 8): a short
  line crosses the middle of the view. Re-planning a part with such walks changes its plan once.
- Sets: a placed World Item can have its own spot in 16:9 frames (`at_wide`; set editor: "Own spot in 16:9"),
  so a wide view isn't bunched in the middle. alien-plains has them.
- World Items (Phase C): drawings `sun` and `plant`; an item's drawing options (`params`: main / accent colours,
  planet rings 0..3, plant stalks 1..6) on the World Items page; drawn items are flat like the cast (no shine or
  shading patches; the crystal's glow is two flat blobs). A built item placed in a set can take a colour (its main
  colour swapped: rock variants). Flying `back` items fly higher (overhead in a low angle). An approach walk that
  arrives late in a shot acts in the line's next shot instead of in its last frames. Demo library assets:
  alien-sun, ringed-planet, saucer, alien-rock, alien-plant, glow-crystal (+ prop) and the alien-plains set.
- World Items: a character out of reach of an item walks over first (in the first part of the line, then acts;
  check-story warns when the line is too short for the walk). sit now lasts until the sitter's next `@do`;
  `@do <cast>: stand` gets up. A World Item's held prop must be a real prop (saving it says so, check-story too),
  and a prop an item is held as can't be deleted.
- World Items (Phase B): characters use drawn items: `@do <cast>: pickup | drop | open | close | push | sit | enter |
  exit <tag>`. pickup puts the item's prop in the hand toward it (it vanishes from the stage at the hand-over) until
  drop sets it down at their feet; open / close tween the hatch mid-line; sit seats the hips on the item's seat point;
  enter seats the character inside (cut at the item's rim) and they ride along wherever it flies, until exit. Hands
  reach for the item's handle / pickup point. Stage items stand within reach beside the cast and actors keep clear
  of them; wide shots frame them. Items get capabilities sit and push, anchors, seats, a rim height and a held prop
  (World Items page: Interactions). check-story checks each use (capability, hands, already holding, inside).
  Story packages carry an OBJECTS section, and a World Item a story or set still uses can't be deleted (the
  message names them). New built-in drawings: pod, bench, crystal.
- Library: custom actions saved before keyframe `snap` existed no longer change bytes when saved again (`snap` is
  left out while false).
- World Items (Phase A): the World Objects page is now **World Items**. Besides built items (3D pieces in a set), an
  item can be **drawn**: an ink card from a built-in drawing (`planet`, `saucer`) or its own shapes, on a layer
  (`sky`, `back`, `mid`, `stage`), with states and looping animations (rotate, sway, bob, drift, pulse, blink, flow),
  previewed live on the page. Story directive `@item <tag>: <item> [layer] [spot] [state]` puts one on stage until
  `@item <tag>: remove` or the next `@set`; `@item <tag>: state <s>` switches state; `@do <tag>: fly left | right`
  flies it across the next line. `remove` and `state` are reserved (never state names); check-story checks items,
  states and tags. Sets can place drawn items too (a planet in the sky). story.json shots get `items` only when there
  are some: older plans, catalogs and every stage hash but the render's are unchanged
  (`scripts/golden_hashes.py record | check` proves it on a library). Item drawings are cached per worker (LRU,
  128 MB cap); render log lines show the cache hit rate and peak MB. Sets get an optional `water` flag (yes / no /
  auto by colour) in the set editor.
- Riding: `@ride <rider>: <creature>` puts a person in the saddle from the next line until `@ride <rider>: none` or
  the part's end, and it stays across `@set` changes. The rider is drawn on the mount's card (straddling, the far leg
  hidden, the near leg over its side, on the saddle when worn) and goes wherever the mount walks, runs or staggers;
  in the saddle only idle, talk, point, wave, react, gasp, angry and cheer (other actions fall back to idle,
  check-story warns). story.json actors get an optional `mount`. check-story refuses unknown riders or creatures, a
  humanoid mount, riding two at once and two riders on one creature, and warns when the rider is in an `@car ride`.
  The Director Script editor has a Ride card.
- Stage spacing uses each body's real width: a horse keeps its half width clear of its neighbours (a stage of
  people spaces exactly as before), wide shots fit the whole horse, and the camera rises to frame a mounted pair.
- Wide shots never cut the outermost actor: the framing keeps at least a body's width plus a wide hat's brim
  around a spread-out cast (outdoor wides allowed only 0.6, under the figure's own 0.8). Such wides now sit a
  little further back; re-rendered parts can change there.
- Creatures can wear wardrobe: custom headwear, face, accessory and back items, hung on points worked out from the
  creature's own shapes (top of the skull, eyes, neck, back) and scaled to its head or body. Fit is approximate.
  Tops, legwear, footwear, hair, facial hair and built-in hats are still refused (check-story warns, @look fails).
  New wardrobe item `saddle` (back, brown leather, blanket, small stirrup, colorable). A creature that wears
  nothing draws exactly as before. Note: a creature that already listed an item (the Almond Milk cat's crown) now
  shows it when re-rendered.
- Creatures can burn: a cast entry or look sets `flame` (off, low, high) and optionally `flame_color`. Flat tongues
  in three layers (outer, middle, core) stand on the mane, tail and every hoof, sway and flicker with the line boil,
  and the eyes glow in the core colour. `@look charro-horse: blazing` switches it on. Off or unset draws exactly as
  before and keeps every cast approval. The cast editor has the controls and a live creature preview; check-story
  warns when a humanoid sets a flame (not drawn).
- Shorts are now 30 to 35 s, never over 35: 70 to 83 words (was 110 to 175, up to 58 s). The story rules
  (docs/ai/tts.md) and every story prompt say so, with the hook, intensifier and rehook positions scaled down;
  check-story and finish QA warn above 35 s and below 30 s, the story importer outside 70 to 83 words.
- Story rules: pick a story with a visual cause and effect, build the escalation to one snap line, add one
  consequence line before the twist in true stories, and in real history every fact and joke must be real (no
  plausible guesses).
- Creatures page: every creature is drawn large on its card. Click the drawing (or **All poses**) to open its model
  sheet under the group: the standing drawing big, every pose it can render (walk, run, talk, eat, cheer, stagger,
  lie) and the headless stump, with a colour picker. Esc or the close button folds it away.
- Street set rebuilt and brought to life: a saturated sky, storybook facades (plinth, cream cornice, window sills and
  lintels, shutters, doors with a step, striped awnings, chimneys), an inked curb and a lighter road with a centre
  line. Ambient motion on every frame: pennant strings sway and flutter, chimneys smoke, ink birds flap across, the
  tree crown sways. Clouds in every outdoor sky now drift slowly (`clouds.drift`, 0 = still). Re-render to see it.
- Stickman volume: the head and body get a soft lit spot toward the key light and a cool shadow pooling on the far
  side, so the figure reads round instead of flat (style.js `figure`; `null` = flat fills as before).
- Captions: words now stamp in one by one as they are said (big, then slammed down) instead of the whole chunk at
  once; the line keeps its final layout, so nothing shifts. Bigger font (72 → 90) and lower on 9:16 (baseline 68% →
  74.5% of the height). `@fx none` keeps the word-by-word reveal without the stamp. Re-run finish to apply.
- Sets look painted, not flat (ideas from the reference's paint.ts): every wall / prop texture gets soft tone drift in
  its own hue; outdoor skies get painted clouds (none at night); indoor sets, built in and custom, get a baseboard, a
  wall that darkens toward ceiling and floor, and a contact shadow along the wall foot. Tunables `blotch`, `room`,
  `clouds` in engine/page/style.js. Library data is unchanged; re-render to see it.
- Style presets: `series.json` `style.preset` now does something. `cinematic` and `storybook` add a colour grade
  pass (contrast, saturation, warmth, lifted shadows, vignette) over every frame; `default` is unchanged. Tunables in
  engine/page/style.js (`grade`, `PRESETS`), see docs/style.md. An unknown preset fails the render.
- Story rules (docs/ai/tts.md): one everyday-analogy explanation, an optional Luckily / Unluckily deadpan pair, and
  never narrating what the picture already shows.
- 16:9: a series can be wide (1920x1080) instead of tall. Pick **Frame** on New series, or
  `set-aspect <slug> 16:9` (then re-run parts from shots). Engine, captions (lower on a wide frame), end screen,
  QA, contact sheets, thumbnail picker and the player (a phone on its side) follow `story.width`/`height`.
- Captions: the upload.md textarea is now two cards, YouTube (title, description + tags, pinned comment) and
  Instagram (one caption with everything), each field with a Copy button and a length count. **Write with Gemini**
  (`POST /api/captions`, key in Settings → Gemini API key, write-only) writes them from the story, the next part's opening and the
  new Settings > Brand tags. Gemini is used for captions only; every other AI step stays copy/paste.
- End screen: every part, the last one included, now ends 0.3 s after its last word on a silent 2.5 s black
  "Follow for more" screen with the YouTube / Instagram / Facebook handles from Settings (empty ones left off).
  The voice no longer carries a sign-off: no "To be continued." / "Part n on my profile" line, no stretched pause
  before the last sentence, and the "Part n+1 on my profile 👆" card is gone. check-story warns when a part still
  ends on a sign-off. Editing a handle only re-runs the final stage.
- Art style: two-layer rain, inked and two-tone sets, distance haze, water detail, warm/cool lighting, eased camera
  moves and idle life (all tunables in engine/page/style.js, see docs/style.md); new expression `dead` (X eyes);
  custom action keys take an optional `ease`.
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
