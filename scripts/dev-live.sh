#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pids=()

cleanup() {
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait || true
}
trap cleanup EXIT INT TERM

start() {
  local name="$1"
  local cwd="$2"
  shift 2

  (
    cd "$cwd"
    echo "[$name] starting in $cwd"
    exec "$@"
  ) &

  pids+=("$!")
}

start "backend" "$ROOT_DIR/backend" uvicorn main:app --reload --host 0.0.0.0 --port 8000
start "track-service" "$ROOT_DIR/track-service" uvicorn main:app --reload --host 0.0.0.0 --port 8001
start "frontend" "$ROOT_DIR/frontend" npm run dev -- --host 0.0.0.0 --port 5173

echo

echo "Live frontend: http://localhost:5173"
echo "Backend API:   http://localhost:8000"
echo "Track API:     http://localhost:8001"
echo "Press Ctrl+C to stop all services"

wait
