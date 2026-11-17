#!/usr/bin/env bash
# Development: API (:8765) + Vite dev server (:5173, hot reload) together. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] && [ -d web/node_modules ] || bash setup.sh
VBIN=.venv/bin; [ -d "$VBIN" ] || VBIN=.venv/Scripts  # Scripts/ on Windows

"$VBIN/uvicorn" api.main:app --host 127.0.0.1 --port 8765 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT INT TERM

echo "dev: API http://127.0.0.1:8765  web http://localhost:5173"
(cd web && npm run dev)
