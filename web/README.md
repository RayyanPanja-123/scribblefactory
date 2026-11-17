# web

Vue 3 + Vite + TypeScript + Tailwind dashboard. Design system: `docs/design.md`.

```sh
npm run dev          # http://localhost:5173, /api proxied to the API on 127.0.0.1:8765
npm run typecheck
npm test             # vitest: next-steps planning, progress parsing, SSE reconnect
npm run build && npm run preview   # http://localhost:4173, same proxy
npm run gen:api      # regenerate src/api/types.ts after docs/openapi.json changes (python -m api.main)
node scripts/screenshots.mjs [--demo]   # after build: screenshots + AA contrast check -> ../library/_review/dashboard-v3-*.png
```

Start the API first for dev (see `api/README.md`). The screenshot script starts its own API (:8766) and preview
(:4174); `--demo` points them at a temp library from `scripts/make-demo-library.py` (4 series, running and failed
stages, a year of posts, 3 approvals waiting), deleted afterwards. It reuses the engine's Playwright.

The real-library run only looks. `--demo` also clicks through actions (pick a thumbnail, approve stills, re-run
prep from a stage chip and open the job drawer) on the throwaway demo library.
