#!/usr/bin/env bash
# Pentaho Migration Copilot launcher (Linux / macOS / Git Bash).
# Creates the venv on first run, installs the package, builds the frontend
# if needed, shows the consultant what this machine can do, then serves the
# app at http://localhost:8321
set -euo pipefail
cd "$(dirname "$0")"

PORT="${COPILOT_PORT:-8321}"

# colors when on a terminal
if [ -t 1 ]; then
    C_HEAD=$'\033[1;37m'; C_DIM=$'\033[36m'; C_OK=$'\033[32m'
    C_WARN=$'\033[33m'; C_URL=$'\033[1;32m'; C_END=$'\033[0m'
else
    C_HEAD=""; C_DIM=""; C_OK=""; C_WARN=""; C_URL=""; C_END=""
fi
step() { echo "  ${C_DIM}> $1${C_END}"; }
ok()   { echo "  ${C_OK}[OK]${C_END}   $1"; }
warn() { echo "  ${C_WARN}[--]${C_END}   $1"; }

# venv layout differs between POSIX (bin/) and Git Bash on Windows (Scripts/)
if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
    PY=".venv/Scripts/python.exe"
else
    step "First run: creating the Python environment (one-time, ~2 min)"
    python3 -m venv .venv 2>/dev/null || python -m venv .venv
    if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY=".venv/Scripts/python.exe"; fi
    "$PY" -m pip install --upgrade pip --quiet
    "$PY" -m pip install -e ".[api,schema]" --quiet
fi

VERSION="$("$PY" -c 'import pentaho_migration; print(pentaho_migration.__version__)' 2>/dev/null || echo '?')"
echo ""
echo "${C_DIM}==================================================================${C_END}"
echo "  ${C_HEAD}Pentaho Migration Copilot  v${VERSION}${C_END}"
echo "  Informatica + Talend -> PDI   |   SAP Crystal Reports -> PRD"
echo "${C_DIM}==================================================================${C_END}"
echo ""

if ! "$PY" -c "import pentaho_migration, fastapi, uvicorn" >/dev/null 2>&1; then
    step "Installing dependencies"
    "$PY" -m pip install -e ".[api,schema]" --quiet
fi

if [ ! -f "frontend/dist/index.html" ]; then
    step "Building the web UI (first run)"
    (cd frontend && npm install --silent && npm run build >/dev/null)
fi

# ----- capability check: what can THIS machine demo? -----
echo "  ${C_HEAD}Crystal environment on this machine:${C_END}"
ENVJSON="$("$PY" -c 'import json; from pentaho_migration.reports.environment import environment_report; print(json.dumps(environment_report()))' 2>/dev/null || true)"
if [ -n "$ENVJSON" ]; then
    probe() { "$PY" -c "import json,sys; d=json.loads(sys.argv[1]); v=d.get(sys.argv[2]); print(v if v else '')" "$ENVJSON" "$1"; }
    PRD="$(probe prd_home)"; RT="$(probe crystal_runtime)"; RX="$(probe rpttoxml)"
    if [ -n "$PRD" ]; then ok "Report Designer: $PRD  (validate + PDF preview + Open-in-PRD)"
    else warn "Report Designer not found - preview/validate/release-check disabled (PRD_HOME)"; fi
    if [ -n "$RT" ]; then ok "SAP Crystal runtime $RT  (view originals, extract .rpt drops)"
    else warn "SAP Crystal runtime missing - .rpt drag-and-drop and the viewer need it"; fi
    if [ -n "$RX" ]; then ok "RptToXml extractor  (drop the customer's .rpt straight on the app)"
    else warn "RptToXml not found - only pre-extracted .xml dumps will convert"; fi
else
    warn "capability check skipped (package not importable yet?)"
fi
if [ -f "tools/RptViewer/RptViewer.exe" ]; then
    ok "Crystal viewer  (View original .rpt, side-by-side demos)"
else
    warn "Crystal viewer not built - run tools/RptViewer/build.ps1 for side-by-side"
fi
echo ""

echo "  Open the app:      ${C_URL}http://localhost:${PORT}${C_END}"
echo "  Demo walkthrough:  docs/DEMO-WALKTHROUGH.md  (scripted 10-minute demo)"
echo "  Quick start:       click 'Try Crystal Reports' - original opens in the"
echo "                     viewer, converts, release-check gates the download"
echo "  Stop:              Ctrl+C"
echo ""
exec "$PY" -m uvicorn pentaho_migration.api.main:app --port "$PORT"
