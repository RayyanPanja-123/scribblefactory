# api

FastAPI backend for the web view. Localhost only, no auth. Run from the repo root:

```sh
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8765       # macOS/Linux
.venv/Scripts/uvicorn api.main:app --host 127.0.0.1 --port 8765   # Windows (Git Bash)
```

Library: `$SCRIBBLE_LIBRARY`, else `./library` (same as the CLI). CORS allows only the Vite dev server
(`http://localhost:5173`). Schema: `docs/openapi.json`, regenerate with `python -m api.main` (a test fails when it drifts).

- Reads: `/api/health`, `/api/overview`, `/api/series`, `/api/series/{slug}`, `/api/series/{slug}/parts/{part}`,
  `/api/media/{slug}/{path}` (mp4/png/mp3/md/json inside the series folder, Range requests for seeking).
- Actions (409 with `detail` when a gate refuses or a job is running on the part): `approve/{what}`, `approve-cast`,
  `pick-thumbnail`, `mark-posted`, `PUT upload.md`, `clean-frames`. They call the CLI commands in-process.
- Jobs: `POST /api/jobs {slug, part, steps}` with steps like `"run --stage audio"`, `"render-stills"`,
  `"test-render"`, `"render"`, `"cast-sheet"`. One worker thread runs them in order as CLI subprocesses and
  stops at the first failure. `GET /api/jobs`, `DELETE /api/jobs/{id}` (cancel, kills the process tree).
  Jobs live in memory only: a restart forgets them (their output files stay).
- Live: `GET /api/events` (SSE): `hello`, `job-queued`, `job-started`, `job-step`, `job-output`, `job-finished`,
  `part-changed`, `series-changed`; a ping every 15 s.
