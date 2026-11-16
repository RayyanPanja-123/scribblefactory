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
- Step 12: Auto finish: final.mp4 + QA (frozen frames, black frames, loudness).
- Step 13: Auto thumbnail candidates + upload text. I pick.
- Step 14: I upload manually, then mark posted with links in the web view.

## Stickman style (locked per series)
- Head: pure white, slightly wobbly hand-drawn circle, thick dark outline.
- Eyes: white circles with black dot pupils, or half-closed black marks.
- Bold curved eyebrows. Small mouth line. NO nose. NO face shading.
- Body: simple flat colored blob (the outfit), thick outline.
- Arms and legs: thin black sticks. Black dot hands. NO shoes.
- Look:
