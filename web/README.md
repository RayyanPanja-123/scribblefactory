# web

Vue 3 + Vite + TypeScript + Tailwind dashboard. Design system: `docs/design.md`.

```sh
npm run dev          # http://localhost:5173, /api proxied to the API on 127.0.0.1:8765
npm run typecheck
npm run build && npm run preview   # http://localhost:4173, same proxy
npm run gen:api      # regenerate src/api/types.ts after docs/openapi.json changes (python -m api.main)
node scripts/screenshots.mjs       # API + preview running: screenshots -> ../library/_review/dashboard-*.png
```

Start the API first (see `api/README.md`). The screenshot script reuses the engine's Playwright.
