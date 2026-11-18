# scribblefactory

Local, offline factory for stickman animated shorts (9:16, 1080x1920, 30fps).
Personal use. Runs fully offline. AI help works via copy/paste with any chat AI (ChatGPT, Claude, Gemini).
Voice is recorded manually.

## Layout

| Path        | What                                              |
|-------------|---------------------------------------------------|
| `engine/`   | Node renderer: Three.js r160 + Playwright         |
| `pipeline/` | Python stages                                     |
| `api/`      | FastAPI app                                       |
| `web/`      | Vue 3 + Vite + TypeScript + Tailwind UI           |
| `library/`  | Rendered videos (gitignored)                      |
| `docs/`     | Notes and specs                                   |

## Quick start

Needs Python 3.12+, Node 20.19+, npm, ffmpeg, ffprobe.

```sh
bash setup.sh            # once: venv, npm installs, Whisper model, Chromium
bash scripts/serve.sh    # builds the web app if needed, serves everything on one port
```

Open http://127.0.0.1:8765. Ctrl+C stops it.

Local dev: `npm run dev` (repo root) runs only the backend (uvicorn on :8765, reloading on changes in `api/` and
`pipeline/`) and the Vite dev server (http://localhost:5173, hot reload). Ctrl+C stops both. It refuses to start
when 8765 or 5173 is already taken, instead of talking to a leftover server; `PORT=8780 npm run dev` moves the backend.

How to make a video: [docs/USAGE.md](docs/USAGE.md). Known gaps and ideas: [docs/backlog.md](docs/backlog.md).
API endpoints: [api/README.md](api/README.md).

The venv lives at repo root: `.venv/bin/` on macOS/Linux, `.venv/Scripts/` on Windows.
After changing requirements.txt, rebuild the venv and regenerate requirements.lock.

## Custom actions

The Actions page (`/actions`) holds custom `@do` actions: keyframed arm, leg and lean poses that loop or play once.
An action can face the camera or sideways (turning left/right with the direction of travel), and sideways actions
take a move speed in units/second; a negative speed glides backwards (moonwalk).

## AI help (copy/paste)

There is no AI provider and no API key: the app writes a prompt, you paste it into any chat AI, then paste the
reply back. Everything goes through **AI Creations** (`/ai-creations`, Studio in the sidebar):

1. Pick a type: Prop, Set, Creature, Action or Cast. Each editor's "Build with AI" opens it pre-filled.
2. Describe it. Only the fields a type needs are added (Creature: rig, Cast: which series).
3. Make the prompt, copy it into any chat AI, paste its JSON reply back.
4. Review everything it would create, each marked new or existing; uncheck what you don't want.
5. Import: one button writes it to the library and links to each new item. Nothing existing is overwritten: a
   clashing id gets a suffix.

**Story Writer** (`/story-writer`) makes a whole series in one paste. Make the story guide (docs/STORY_GUIDE.md plus
your library's ids and the [Story Package format](docs/story-package.md)), brainstorm with any chat AI, and paste the
one Story Package it returns. It is checked as you paste (errors and warnings with their section and line), previewed,
and imported all or nothing: new props, sets, creatures and actions, then the series with its cast and every part's
story.md and TTS script (script-for-tts.txt, shown on the part's Voice tab). Voice (FreeTTS) and uploading stay manual.
"Copy story guide" on the Overview copies the same guide.

## Tests

```sh
.venv/Scripts/python -m pytest -q        # pipeline + API (.venv/bin/ on macOS/Linux)
(cd engine && npm test)                  # renderer
(cd web && npx vitest run && npm run typecheck)
```

## Known gaps

- `setup.sh` has only been tested on Windows Git Bash so far, not on macOS or Linux.
- requirements.lock is built on Windows / Python 3.12.
- No auth: the API binds to 127.0.0.1 only and must stay there.
