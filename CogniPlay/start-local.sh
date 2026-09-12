#!/usr/bin/env bash
# Starts all three CogniPlay services locally, without Docker.
# Ctrl+C stops everything.
set -u
cd "$(dirname "$0")"
ROOT="$PWD"
pids=()
cleanup() { echo; echo "Stopping..."; for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done; exit 0; }
trap cleanup INT TERM

echo "CogniPlay - starting local services"
echo

# --- Python AI service -------------------------------------------------------
cd "$ROOT/backend-python"
if [ ! -d venv ]; then
  echo "[python] creating venv..."
  python3 -m venv venv
  ./venv/bin/pip install --quiet --upgrade pip
  echo "[python] installing minimal deps (torch/shap are optional, skipped)..."
  ./venv/bin/pip install --quiet fastapi "uvicorn[standard]" numpy pydantic python-multipart
fi
echo "[python] starting on :8000"
./venv/bin/python main.py & pids+=($!)

# --- Node API ----------------------------------------------------------------
cd "$ROOT/backend-node"
[ -f .env ] || cp .env.example .env
[ -d node_modules ] || { echo "[node] npm install..."; npm install --silent; }
echo "[node] starting on :3001"
npm start & pids+=($!)

# --- React frontend ----------------------------------------------------------
cd "$ROOT/frontend"
[ -f .env ] || cp .env.example .env
[ -d node_modules ] || { echo "[web] npm install (this one takes a few minutes)..."; npm install --silent; }
echo "[web] starting on :3000"
npm start & pids+=($!)

echo
echo "All three services launching. Open http://localhost:3000"
echo "Press Ctrl+C to stop everything."
wait
