#!/usr/bin/env bash
# Pramana local DX - install, seed, run API
# Usage: ./scripts/dev.sh [--history] [--skip-install] [--port 8000]

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HISTORY=0
SKIP_INSTALL=0
PORT=8000
while [[ $# -gt 0 ]]; do
  case "$1" in
    --history) HISTORY=1; shift ;;
    --skip-install) SKIP_INSTALL=1; shift ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

echo "== Pramana dev ($ROOT) =="

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "Installing Python deps..."
  python -m pip install -r requirements.txt
fi

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

SEED=(python -m core.db.seed --demo)
if [[ "$HISTORY" -eq 1 ]]; then
  SEED+=(--history)
fi
echo "Seeding demo data..."
"${SEED[@]}"

echo "Starting uvicorn on http://127.0.0.1:${PORT}"
echo "Open / for console (if console/dist built) or /docs for OpenAPI"
exec python -m uvicorn core.app:app --host 127.0.0.1 --port "$PORT" --reload
