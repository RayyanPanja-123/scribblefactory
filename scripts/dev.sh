#!/usr/bin/env bash
# npm run dev: the backend (uvicorn on :8765, or $PORT, restarted on code changes) and the Vite dev server (:5173), nothing else.
# Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

VBIN=.venv/bin; [ -d "$VBIN" ] || VBIN=.venv/Scripts  # Scripts/ on Windows
if [ ! -x "$VBIN/watchfiles" ] && [ ! -x "$VBIN/watchfiles.exe" ] || [ ! -d web/node_modules ]; then
  echo "dev: not set up yet: run bash setup.sh first" >&2
  exit 1
fi

PORT=${PORT:-8765}
export SCRIBBLE_API="http://127.0.0.1:$PORT"  # where Vite proxies /api (web/vite.config.ts)
if curl -s -m 2 -o /dev/null "$SCRIBBLE_API/api/health"; then  # it would answer Vite's /api in place of ours
  echo "dev: port $PORT is already in use (a server left running?). Stop it, or: PORT=8780 npm run dev" >&2
  exit 1
fi

# backend, dev mode: restarted on .py changes in api/ and pipeline/ only (never on library/ writes). watchfiles, not
# uvicorn --reload: on Windows uvicorn restarts with a Ctrl+C sent to the whole console, which also kills Vite and npm
export PORT
"$VBIN/python" -m watchfiles --filter python --target-type function api.main.dev api pipeline &
API_PID=$!
stop_api() {
  # Windows: python.exe in a venv is a launcher; the server (and watchfiles) are children: kill the whole tree
  if [ -r "/proc/$API_PID/winpid" ]; then
    taskkill //T //F //PID "$(cat "/proc/$API_PID/winpid")" >/dev/null 2>&1 || true
  else
    kill "$API_PID" 2>/dev/null || true
  fi
}
trap stop_api EXIT INT TERM

echo "dev: backend $SCRIBBLE_API (reload)  app http://localhost:5173"
(cd web && npm run dev -- --host 0.0.0.0 --strictPort)  # LAN access lets a phone scan the mobile download QR
