# scribblefactory: project brief

## What we're building
- A local factory for stickman animated shorts.
- Personal use only. Own stories.
- Output: 9:16, 1080x1920, 30fps.
- Published manually to YouTube Shorts and Instagram Reels.
- Stories are split into series with parts 1..n.
- I write the story. The factory turns it into a finished video.
- I only act at a few points: write story, make voice, approve, upload.

## Hard rules
- No external AI API calls in the pipeline.
- Everything runs locally and offline, except manual voice.
- Voice: I generate it on freetts.ai and drop in voice.mp3.
- Fast and light. No Laravel. No heavy frameworks.
- No large datasets or joins.
- Music and SFX: synthesized or royalty-free only.

## Stack
- Backend: Python + FastAPI.
- Frontend: Vue 3 + Vite + TypeScript + Tailwind.
- Renderer: Node + Three.js r160 + Playwright (headless Chromium).
- Audio/video: ffmpeg.
- Timing: local faster-whisper.
- Storage: files on disk are the source of truth.
- SQLite index only if listing gets slow.
- Live progress: Server-Sent Events.
- One background worker. No queue system.

## Repo layout
- engine/   Node renderer
- pipeline/ Python stages
- api/      FastAPI
- web/      Vue app
- library/  videos (gitignored)
- docs/     docs and exported schemas

## Library layout
library/<series-slug>/
- series.json (title, status, part order, voice, style, cast)
- part-01/
  - story.md
  - script-for-tts.txt
  - voice.mp3
  - phrases.json (word/phrase timings)
  - story.json (shot plan)
  - frames/
  - final.mp4
  - upload.md
  - part.json (stage status, approvals, posted links)

## Video flow (per part)
- Step 1: I write story.md.
- Step 2: Auto script prep: clean text, word count, duration, script-for-tts.txt.
- Step 3: I make voice.mp3 on freetts.ai.
- Step 4: Auto import check: plays, duration, silence.
- Step 5: Auto timing with Whisper -> phrases.json.
- Step 6: Auto rule-based shot plan -> story.json, then validator.
- Step 7: I approve cast test sheet (once per character).
- Step 8: I approve stills contact sheet.
- Step 9: I approve a 5-second test render.
- Step 10: Auto full render in parallel chunks, resumable.
- Step 11: Auto sound: synth music + SFX, mixed under voice.
- Step 12: Auto finish: final.mp4 with burned-in captions + QA (frozen frames, black frames, loudness, captions) -> qa.json.
- Step 13: Auto thumbnail candidates + upload text. I pick.
- Step 14: I upload manually, then mark posted with links in the web view.

## Story directives (in story.md, one per line)
- "@set office": set for the following lines until changed. Default "room".
- "@cast bob, karen": cast ids on stage until changed. Must exist in series.json. Default: first 2 cast members.
- "@dogs N": dog pack size (0-6) for the following lines until changed. Travel shots: the pack chases behind. Other shots: dogs idle or bark at the stage edges. "@dogs 0" removes them. Default 0.
- "@car <mode>": arrive | ride | leave | off, for the following lines until changed. arrive: a car drives in and stops beside the subject (then stays parked). ride: the current @cast ride in the car (travel shot on outdoor sets; wave keywords make riders wave). leave: the car drives off-screen. off: no car. Default off.
- "!! text": this line is the twist (push-in with roll, music stops, low hit).
- prep strips directives from script-for-tts.txt. The shot planner reads them.

## Stickman style (locked per series)
- Head: pure white, slightly wobbly hand-drawn circle, thick dark outline.
- Eyes: white circles with black dot pupils, or half-closed black marks.
- Bold curved eyebrows. Small mouth line. NO nose. NO face shading.
- Body: simple flat colored blob (the outfit), thick outline.
- Arms and legs: thin black sticks. Black dot hands. NO shoes.
- Look: marker-drawn, imperfect, not polished.
- World: colorful toon-shaded 3D, ink outlines, painted textures.
- Captions (on by default, series style.captions; set-captions <slug> on|off): burned into final.mp4 only, never into stills, thumbnails or preview.mp4. Fredoka One (OFL, assets/fonts), white with a thick black outline, the spoken word yellow (#ffd54a). Max 5 words, max 2 lines, names never split. Centred, baseline at 68% of the height, clear of the Shorts/Reels UI (bottom 20%, right 15%).
- Costumes vary per story, but always flat colour, thick outline, marker look. Stick limbs stay visible below shorts/sleeves.

## Validator rules
- Max 90 frames per shot.
- No repeated camera angle back to back.
- Camera always creeping, never static.
- Characters face their movement direction.
- Walk phase drives legs. No gliding.
- Idle breathing and blink on every character.
- Twist line: music stops, low hit, push-in with roll.
- Audio: music -6 dB under voice, -14 LUFS, peak -1 dBFS.

## Web view
- Series list with cover thumbnail.
- Part list with stage status.
- Video preview player.
- Disk usage per series.
- Clean frames button (keeps final.mp4).
- Posted tracker (YT/IG, link, date).
- Edit upload.md in browser.
- Approval buttons: cast, stills, test render, final.

## Engine base
- Reference: github.com/mromidev/claude-animated-shorts (MIT), commit e3b817b6afc6cd413466d43f11ba31209e034bbf.
- Do NOT fork. Borrow selected files only: camera math, 2D character card drawing, outline pass, frame QA (short_qa.py), synth audio.
- Copied files keep the MIT header plus a note with the pinned commit.
- Never copy references/ (third-party frames). Never use Remotion or React.
- three@0.160.0 pinned in engine/package.json.
- Characters: 2D marker-drawn cards facing the camera, inside a toon-shaded 3D world.
- Our own: story.json format, render.mjs, timing.py, audio.py, mix.py, finish.sh, sheet.py.

## Build order
- Step 1: Repo skeleton + setup.sh. DONE.
- Step 2: series.json and part.json schemas. DONE.
- Step 3: CLI (new-series, new-part, render). DONE (render is a stub until Step 5).
- Step 4: Pipeline stages.
  - 4a: stage runner, prep, import check. DONE.
  - 4b: timing (Whisper). DONE.
  - 4c: story.json format + rule-based shot planner + validator. DONE.
    - 4c-1: story.json format + validator. DONE.
    - 4c-2: rule-based shot planner (shots stage). DONE.
- Step 5: Render engine, parallel chunks, resume.
  - 5.1: engine core (sets, stickman cards, camera), stills + cast sheets, approvals. DONE.
  - 5.2: test render + chunked, parallel, resumable full render (GPU default, SwiftShader fallback). DONE.
- Step 5b: audio (synth music + SFX), mix, finish + QA. DONE.
  - 5b-1: audio stage: synth music + SFX from cues, mix under voice to -14 LUFS / -1 dBTP. DONE.
  - 5b-2: finish (final.mp4 from frames + mix, burned-in captions, QA -> qa.json), thumbnails + upload.md, pick-thumbnail, mark-posted, clean-frames, set-captions. DONE.
- Step 5c: Content library (per-story characters, same art style).
  - Cast v2 schema: top style (plain, suit, tank, shirt) + colour, accents (tie, chest number), headwear (none, flat_cap, postman_cap), legwear over stick legs (none, shorts, ragged_shorts, trousers), held prop, default expression, eyes. Bump schema_version.
  - New expressions: cheeky, exhausted.
  - Sets: dirt_road, orchard, countryside, stadium (finish line).
  - Props: clipboard, stopwatch, bottle, syringe, apple, medal, oak tree.
  - Vehicles: car (seats for riders, can stop/break down). Animals: dog.
  - Actions: lie, ride, wave, eat, stagger, carried, chase, give.
  - Extras: crowd and background runners (non-cast, generic look).
  - Directives: "@do <cast>: <action> [target]" overrides keyword guessing for that line.
- Step 6: FastAPI + Vue web view.
  - 6.1: FastAPI backend: reads, media with Range, actions, one-worker jobs, SSE, docs/openapi.json. DONE.
- Step 7: Polish and QA.

## Working rules for you
- Do only the task given. No extra features.
- Pick the simplest option when ambiguous. Note it in your report.
- Pin exact dependency versions.
- Every stage must be resumable and idempotent.
- Never overwrite files I made (story.md, voice.mp3) or approvals.
- Writes to JSON files must be atomic (temp file, then replace).
- Never touch the real library/ in tests. Use a temp dir.
- Run and show real verification output before reporting.
- Flag risks. Disagree if something is a bad idea.
- End every task with a report: files created, decisions, issues.
