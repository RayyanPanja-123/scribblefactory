#!/usr/bin/env bash
# Start API + web UI together. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"

[ -d .venv ] && [ -d web/node_modules ] || bash setup.sh
VBIN=.venv/bin; [ -d "$VBIN" ] || VBIN=.venv/Scripts  # Scripts/ on Windows

"$VBIN/uvicorn" api.main:app --host 127.0.0.1 --port 8765 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

(cd web && npm run dev)
