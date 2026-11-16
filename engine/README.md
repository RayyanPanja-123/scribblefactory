# engine

Node renderer: three.js r160 scenes rendered in headless Chromium (Playwright) into PNG frames.

    node engine/render.mjs --part <part-dir> --frame N --out file.png
    node engine/render.mjs --part <part-dir> --stills        # frames/stills/<shot>.png + manifest.json
    node engine/render.mjs --series <series-dir> --cast-sheet # cast-frames/<id>-<pose>.png + manifest.json
    npm test                                                  # in engine/

- `render.mjs` serves `page/` and `node_modules/three` on a localhost port and drives the page.
- `page/main.js`: frame n -> time n / 30; all randomness from `rng(seed, keys)`. Same frame -> same bytes.
- `page/stickman.js`: our stickman card (docs/brief.md "Stickman style").
- `page/world.js`: set presets room / office / street (unknown -> room with a warning).
- `page/borrowed.js`: MIT code from mromidev/claude-animated-shorts @ e3b817b (see its header).
- WebGL runs on SwiftShader (software) so frames don't depend on the GPU.
