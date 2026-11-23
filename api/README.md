# api

FastAPI backend for the web view. Localhost only, no auth. Run from the repo root:

```sh
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8765       # macOS/Linux
.venv/Scripts/uvicorn api.main:app --host 127.0.0.1 --port 8765   # Windows (Git Bash)
```

Library: `$SCRIBBLE_LIBRARY`, else `./library` (same as the CLI). CORS allows only the Vite dev server
(`http://localhost:5173`). Schema: `docs/openapi.json`, regenerate with `python -m api.main` (a test fails when it drifts).

Files: `main.py` (the app, startup, series/part reads and actions, story packages), `core.py` (library paths, part
and series JSON), `models.py` (response models), `jobs.py` (the job queue), `catalogs.py` (props, creatures,
wardrobe, actions, sets, objects), `sounds.py`, `settings_routes.py`, `captions.py` (Gemini) and `events.py` (SSE).
Each route module has its own `router`, and `main.py` includes them before the web app's catch-all route.

- Reads: `/api/health`, `/api/overview`, `/api/series`, `/api/series/{slug}`, `/api/series/{slug}/parts/{part}`,
  `/api/series/{slug}/parts/{part}/check-story` (same checks as the `check-story` CLI command),
  `/api/media/{slug}/{path}` (mp4/png/jpg/mp3/md/json inside the series folder, Range requests for seeking).
- Actions (409 with `detail` when a gate refuses or a job is running on the part): `approve/{what}`, `approve-cast`,
  `pick-thumbnail`, `mark-posted`, `PUT upload.md`, `clean-frames`, `DELETE /api/series/{slug}/parts/{part}`,
  `DELETE /api/series/{slug}`. They call the CLI commands in-process.
- Jobs: `POST /api/jobs {slug, part, steps}` with steps like `"run --stage audio"`, `"render-stills"`,
  `"test-render"`, `"render"`, `"cast-sheet"`. One worker thread runs them in order as CLI subprocesses and
  stops at the first failure. `GET /api/jobs`, `DELETE /api/jobs/{id}` (cancel, kills the process tree).
  Jobs persist to `library/.jobs.json`: on start, queued jobs resume and a job left running fails
  ("interrupted by restart"; its orphaned process is stopped).
- On start the API also marks every stage stuck at `running` with no live process as failed ("interrupted") and
  stops leftover render workers of stale render locks.
- Web app: with `SCRIBBLE_SERVE_WEB=1` (set by `scripts/serve.sh`) every non-`/api` path serves `web/dist`.
- Live: `GET /api/events` (SSE): `hello`, `job-queued`, `job-started`, `job-step`, `job-output`, `job-finished`,
  `part-changed`, `series-changed`; a ping every 15 s.
