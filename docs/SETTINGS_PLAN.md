# Plan: Settings page (render performance first)

Goal: a dashboard **Settings** page for machine-level options, starting with how many render workers run, so a
strong PC renders faster. Today the dashboard always uses 2 workers.

## What exists today

- `pipeline/scribble/stages/render.py:37`: `WORKERS = 2`, 150-frame chunks, one long-lived Chromium per worker.
- `pipeline/scribble/cli.py:676`: `--workers` (default `WORKERS`) and `--swiftshader` flags; `cli.py:339` passes
  them to `render_stage.run`.
- `api/main.py:1054`: jobs run `python -m pipeline.scribble.cli <argv> --library=...`; never passes `--workers`.
- `api/main.py:1111-1129`: `library/settings.json` used to hold AI provider keys; `drop_ai_settings()` deletes
  those keys at startup and **deletes the file when nothing else is left**. Must change before reusing the file.
- `pipeline/scribble/stages/timing.py:58`: faster-whisper on `device="cpu"`, `compute_type="int8"` (few seconds;
  low value, leave it out of v1).
- `web/src/App.vue:125`: a utility menu behind the Settings (cog) icon already exists; add the page there.
- Part 1 of the Roman series: about 175 to 250 ms per frame with 2 workers, about 3 minutes per 55 s part.

## Settings (v1)

| Key | Default | Range | Effect |
|---|---|---|---|
| `render_workers` | `auto` (cores / 2, clamped 1 to 8) | `auto` or 1 to 16 | `--workers` for render jobs |
| `force_software_gl` | `false` | bool | `--swiftshader` (debug: no GPU) |

Skip for now (YAGNI): whisper device, ffmpeg presets, chunk size, art style.

## Steps

1. **Storage.** `library/settings.json` as `{"render_workers": "auto", "force_software_gl": false}`.
   Change `drop_ai_settings()` to remove only the old provider keys and never delete the file if other keys
   remain. Read with defaults when the file or a key is missing; ignore unknown keys.
2. **Pipeline.** In `render.py` add `auto_workers()`: `max(1, min(8, (os.cpu_count() or 2) // 2))`.
   CLI `--workers` default: settings value, else `auto_workers()`. Explicit flag still wins.
3. **API.** `GET /api/settings` returns values, defaults and machine info (cpu count, the resolved auto value,
   last renderer seen: GPU name or SwiftShader, from the latest `frames/chunks/worker*.log` READY line or render
   info). `PUT /api/settings` validates with a Pydantic model (range checks) and writes atomically.
   Jobs keep calling the CLI unchanged; the CLI reads settings itself (one place, works from the terminal too).
4. **Web.** `web/src/pages/Settings.vue`, route `/settings`, link in the utility menu. Fields: workers (Auto or a
   number), software GL toggle, a "This PC" box (cores, GPU / SwiftShader, last ms per frame). Save button, toast.
   Follow the existing page style (`raised` sections, same form controls as the editors).
5. **Help text.** One line under workers: more workers help only with a real GPU and enough RAM (each worker is
   one Chromium); if renders fail or slow down, lower it.
6. **Tests.**
   - pipeline: `auto_workers()` clamps; CLI default comes from settings; explicit `--workers` wins.
   - api: GET defaults with no file; PUT validates (0 and 17 rejected); startup no longer deletes a settings file
     that has `render_workers` (extend the existing `drop_ai_settings` test).
7. **Measure.** Render one part with 2, 4 and 8 workers on this PC; note ms per frame and total time in
   CHANGELOG.md. Check the renderer line shows the GPU, not SwiftShader.

## Open questions

- Does the `run` command (full pipeline) also reach `render_stage.run` with `args.workers`? Check `cli.py` before
  step 2 so every render path uses the setting.
- Should a running render pick up a changed setting? Proposal: no, it applies to the next job.
