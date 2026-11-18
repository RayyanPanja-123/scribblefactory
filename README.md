# scribblefactory

Local, offline factory for stickman animated shorts (9:16, 1080x1920, 30fps).
Personal use. Runs fully offline. AI providers are optional add-ons; voice is recorded manually.

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

## Optional AI features

Nothing below is required: every AI feature has a manual path, and the app works the same without a provider.

Providers (Settings): OmniRoute (local gateway, started and stopped from the navbar switch), Google Gemini and
OpenRouter. API keys stay on the server; the UI only shows their last four characters.

| Feature | With a provider | Without one |
|---|---|---|
| Build with AI (Props, Sets, Creatures, Actions) | One click generates the item into the editor | "Prompt for AI" gives a prompt to copy into any chat AI and paste the reply back, or fill the editor by hand |
| Story Writer (Gemini or OpenRouter only) | Plans a multi-part series, creates the props, sets, creatures and actions it needs, then the series and parts | "Copy story guide" on the Overview for any chat AI, or write each part's story yourself |

Voice (FreeTTS) and uploading stay manual either way.

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
