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

if command -v node >/dev/null 2>&1 && node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>20||(a===20&&b>=19)?0:1)'; then
  ok "node >= 20.19 ($(node --version))"
else
  fail "node >= 20.19 not found (Vite 8 requirement; e.g. nvm install 20)"
fi

for t in npm ffmpeg ffprobe; do
  if command -v "$t" >/dev/null 2>&1; then ok "$t"; else fail "$t not found on PATH"; fi
done

if [ "$FAILED" -ne 0 ]; then summary; exit 1; fi

# --- install ---
[ -d .venv ] || "$PY" -m venv .venv
VBIN=.venv/bin; [ -d "$VBIN" ] || VBIN=.venv/Scripts  # Scripts/ on Windows
"$VBIN/python" -m pip install --quiet --upgrade pip
"$VBIN/python" -m pip install --quiet -r requirements.lock
ok "venv + pip install -r requirements.lock"

# Whisper model for the timing stage (offline at run time). Downloaded once.
WHISPER_DIR=models/faster-whisper-base.en
if [ -f "$WHISPER_DIR/model.bin" ]; then
  ok "whisper base.en (already in $WHISPER_DIR)"
elif "$VBIN/python" -c "from faster_whisper import download_model; download_model('base.en', output_dir='$WHISPER_DIR')"; then
  ok "whisper base.en -> $WHISPER_DIR"
else
  fail "whisper base.en download failed"
fi

(cd engine && npm install --no-fund --no-audit) && ok "npm install engine/"
(cd web && npm install --no-fund --no-audit) && ok "npm install web/"
(cd engine && npx --no-install playwright install chromium) && ok "playwright chromium"

mkdir -p library && ok "library/"

summary
exit "$FAILED"
