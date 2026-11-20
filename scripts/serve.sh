#!/usr/bin/env bash
# Production: build web/ if web/dist is stale, then serve the API and the web app on one port. Ctrl+C stops it.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] && [ -d web/node_modules ] || bash setup.sh
VBIN=.venv/bin; [ -d "$VBIN" ] || VBIN=.venv/Scripts  # Scripts/ on Windows
PORT=${PORT:-8765}

# stale: no build yet, or any web source (or the engine page code the prop preview imports) is newer than it
if [ ! -f web/dist/index.html ] || [ -n "$(find web/src web/public web/index.html web/package.json web/vite.config.ts \
    web/tsconfig.json engine/page -newer web/dist/index.html -print -quit)" ]; then
  echo "serve: building web/ (web/dist is stale)"
  (cd web && npm run build)
else
  echo "serve: web/dist is up to date"
fi

echo "serve: scribblefactory on http://0.0.0.0:$PORT"
SCRIBBLE_SERVE_WEB=1 exec "$VBIN/uvicorn" api.main:app --host 0.0.0.0 --port "$PORT"
