# Backlog

Known gaps and ideas, one line each. Not planned work.

## Known gaps

- Lie against a tree: `lie` is always flat on the ground; no "lying against the oak tree" variant.
- macOS / Linux untested: setup.sh, serve.sh, dev.sh and the process-tree kill paths have only run on Windows Git Bash.
- requirements.lock is built on Windows / Python 3.12; other platforms may need it regenerated.
- Whisper model download needs the network once (setup.sh); everything after is offline.
- check-story maps changed words to story.md lines per line: markdown spanning several lines can lose the line number.
- check-story treats `@car leave` as a car on stage for the whole @car leave stretch (the planner removes it after
  the first shot), so `@do car: broken` there is not flagged.
- A job's output is kept as its last 200 lines, saved on state changes only: a crash loses lines since the last step.
- An API restart stops a job's orphaned process instead of following it to the end.
- No auth: the API binds to 127.0.0.1 only and must stay there.

## Ideas

- Data-driven sets: describe sets in JSON (ground, sky, props, colours) instead of code in engine/page/world.js.
- More sets: beach, kitchen, classroom, forest.
- More animals (cat, horse) and vehicles (bike, bus).
- Several cars at once (`@car` takes an id).
- Per-line camera override (`@cam close`, `@cam low`).
- Voice import from a folder watch instead of an upload.
- Disk budget warning on the overview when library/ passes a size.
- Batch "Run next" across every part of a series.
- Export a series as one long video (compilation).
