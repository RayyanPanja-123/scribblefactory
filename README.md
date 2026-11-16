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

Needs Python 3.11+, Node 20.19+, npm, ffmpeg, ffprobe.

```sh
bash setup.sh
.venv/bin/uvicorn api.main:app        # http://127.0.0.1:8000/health
(cd web && npm run dev)
```
