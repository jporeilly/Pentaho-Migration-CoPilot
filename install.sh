#!/usr/bin/env bash
# Pentaho Migration Copilot - installer (Linux / macOS / Git Bash).
# Sets up everything the app needs and tells you what it found.
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(sed -n 's/^__version__ = "\([0-9.]*\)"/\1/p' src/pentaho_migration/__init__.py)

cat <<EOF

=============================================================
  Pentaho Migration Copilot  v${VERSION}
=============================================================

  AI-assisted migration of legacy data platforms into Pentaho:

    * Informatica PowerCenter and Talend  ->  native PDI (.ktr/.kjb)
    * SAP Crystal Reports                 ->  Report Designer (.prpt)

  Deterministic where accuracy is non-negotiable, AI only where
  semantic judgment is required. Anything the tool cannot prove
  is flagged for human review - never guessed, never hidden.

EOF

echo "[1/4] Checking prerequisites..."
ok=1
if command -v python3 >/dev/null 2>&1; then PYBIN=python3
elif command -v python >/dev/null 2>&1; then PYBIN=python
else PYBIN=""; fi
if [ -n "$PYBIN" ]; then
    echo "  + Python found: $($PYBIN --version 2>&1)"
else
    echo "  x Python 3.11+ not found - https://www.python.org/downloads/"; ok=0
fi
if command -v npm >/dev/null 2>&1; then
    echo "  + Node.js found: $(node --version) (needed once, to build the web UI)"
else
    echo "  x Node.js 18+ not found - https://nodejs.org/"; ok=0
fi
[ "$ok" = 1 ] || { echo; echo "Install the missing prerequisites, then re-run install.sh"; exit 1; }

echo
echo "[2/4] Python environment..."
if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"
else
    echo "  creating .venv..."
    "$PYBIN" -m venv .venv
    if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY=".venv/Scripts/python.exe"; fi
    "$PY" -m pip install --upgrade pip --quiet
fi
echo "  installing the package + API + schema-agent extras..."
"$PY" -m pip install -e ".[api,schema]" --quiet
echo "  + Python environment ready"

echo
echo "[3/4] Web UI..."
if [ ! -d "frontend/node_modules" ]; then
    echo "  npm install (first run)..."
    (cd frontend && npm install --silent)
fi
if [ ! -f "frontend/dist/index.html" ]; then
    echo "  building the React UI..."
    (cd frontend && npm run build --silent)
else
    echo "  + UI already built (frontend/dist)"
fi

echo
echo "[4/4] Crystal Reports environment (optional - only needed to extract"
echo "      .rpt files and engine-validate .prpt output):"
"$PY" -m pentaho_migration.cli report-env || true
echo "      Anything missing above? See docs/INSTALL.md - the app works"
echo "      without it for RptToXml dumps and all ETL sources."

cat <<EOF

=============================================================
  Installed. Next steps:

    ./run.sh                  start the app -> http://localhost:8321
                              then click 'Try the Crystal sample'

    CLI highlights (.venv/bin/pentaho-migrate --help):
      convert <export>        Informatica/Talend -> PDI .ktr
      report <dump> --jndi X  Crystal dump -> PRD .prpt + report
      report-triage <dir>     verdict per report over a corpus
      report-qa <dump>        layout lint before opening PRD

    Docs: README.md - docs/INSTALL.md - docs/BEST_PRACTICES.md
    Uninstall: ./uninstall.sh
=============================================================
EOF
