#!/usr/bin/env bash
# scribblefactory setup. Idempotent: safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

RESULTS=()
FAILED=0
ok()   { RESULTS+=("OK    $1"); }
fail() { RESULTS+=("FAIL  $1"); FAILED=1; echo "ERROR: $1" >&2; }
summary() { echo; echo "== Summary =="; printf '%s\n' "${RESULTS[@]}"; }

# --- checks ---
PY=""
for c in python3 python; do  # `python` fallback for Git Bash on Windows
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -n "$PY" ]; then ok "python >= 3.11 ($($PY --version 2>&1))"; else fail "python3 >= 3.11 not found (install Python 3.11+)"; fi

if command -v node >/dev/null 2>&1 && [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ]; then
  ok "node >= 20 ($(node --version))"
else
  fail "node >= 20 not found (see .nvmrc; e.g. nvm install)"
fi

for t in npm ffmpeg ffprobe; do
  if command -v "$t" >/dev/null 2>&1; then ok "$t"; else fail "$t not found on PATH"; fi
done

if [ "$FAILED" -ne 0 ]; then summary; exit 1; fi

# --- install ---
[ -d .venv ] || "$PY" -m venv .venv
VBIN=.venv/bin; [ -d "$VBIN" ] || VBIN=.venv/Scripts  # Scripts/ on Windows
"$VBIN/python" -m pip install --quiet --upgrade pip
"$VBIN/python" -m pip install --quiet -r requirements.txt
ok "venv + pip install -r requirements.txt"

(cd engine && npm install --no-fund --no-audit) && ok "npm install engine/"
(cd web && npm install --no-fund --no-audit) && ok "npm install web/"
(cd engine && npx --no-install playwright install chromium) && ok "playwright chromium"

mkdir -p library && ok "library/"

summary
