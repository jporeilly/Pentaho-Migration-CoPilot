#!/usr/bin/env bash
# Pentaho Migration Copilot launcher (Linux / macOS / Git Bash).
# Creates the venv on first run, installs the package, builds the frontend
# if needed, then serves the app at http://localhost:8321
set -euo pipefail
cd "$(dirname "$0")"

PORT="${COPILOT_PORT:-8321}"

# venv layout differs between POSIX (bin/) and Git Bash on Windows (Scripts/)
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"
else
    echo "[run] creating virtual environment..."
    python3 -m venv .venv 2>/dev/null || python -m venv .venv
    if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY=".venv/Scripts/python.exe"; fi
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install -e ".[api,schema]"
fi

if ! "$PY" -c "import pentaho_migration, fastapi, uvicorn" >/dev/null 2>&1; then
    echo "[run] installing dependencies..."
    "$PY" -m pip install -e ".[api,schema]"
fi

if [ ! -f "frontend/dist/index.html" ]; then
    echo "[run] building frontend (first run)..."
    (cd frontend && npm install && npm run build)
fi

echo "[run] Pentaho Migration Copilot -> http://localhost:${PORT}"
exec "$PY" -m uvicorn pentaho_migration.api.main:app --port "$PORT"
