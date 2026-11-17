# scribblefactory

Local, offline factory for stickman animated shorts (9:16, 1080x1920, 30fps).
Personal use. No external AI APIs; voice is recorded manually.

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

## Tests

```sh
.venv/Scripts/python -m pytest -q        # pipeline + API (.venv/bin/ on macOS/Linux)
(cd engine && npm test)                  # renderer
(cd web && npx vitest run && npm run typecheck)
```

## Known gaps

- `setup.sh` has only been tested on Windows Git Bash so far, not on macOS or Linux.
- requirements.lock is built on Windows / Python 3.12.
