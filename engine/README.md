# engine

Node renderer: three.js r160 scenes rendered in headless Chromium (Playwright) into PNG frames.

    node engine/render.mjs --part <part-dir> --frame N --out file.png
    node engine/render.mjs --part <part-dir> --frames A-B --out-dir <dir>   # <dir>/000042.png ...
    node engine/render.mjs --part <part-dir> --stills        # frames/stills/<shot>.png + manifest.json
    node engine/render.mjs --series <series-dir> --cast-sheet # cast-frames/<id>-<pose>.png + manifest.json
    node engine/render.mjs --probe                            # which renderer would be used
    add --swiftshader to force software WebGL, --info-out file.json to record the renderer
    npm test                                                  # in engine/ (always SwiftShader)

- `render.mjs` serves `page/` and `node_modules/three` on a localhost port and drives the page.
- `page/main.js`: frame n -> time n / 30; all randomness from `rng(seed, keys)`. Same frame -> same bytes.
- `page/stickman.js`: our stickman card (docs/brief.md "Stickman style").
- `page/world.js`: set presets room / office / street (unknown -> room with a warning).
- `page/borrowed.js`: MIT code from mromidev/claude-animated-shorts @ e3b817b (see its header).
- WebGL runs on the GPU by default (~5x faster); if WebGL reports a software renderer it falls back to
  SwiftShader with a note. Renders record renderer, GPU name, driver (Windows), Chromium and Playwright versions.
- Full renders (chunks, workers, resume) are driven by `pipeline/scribble/stages/render.py`.
