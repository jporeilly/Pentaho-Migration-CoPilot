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
    * SAP Crystal Reports and Xactions    ->  Report Designer (.prpt)

  Deterministic where accuracy is non-negotiable, AI only where
  semantic judgment is required. Anything the tool cannot prove
  is flagged for human review - never guessed, never hidden.

EOF

# -- installation type: Complete (everything) or Custom (pick) ----------
MODE="${1:-}"
case "$MODE" in
  --complete|Complete|complete) MODE="Complete" ;;
  --custom|Custom|custom)       MODE="Custom" ;;
  *)                            MODE="" ;;
esac
if [ -z "$MODE" ]; then
    echo "Installation type:"
    echo
    echo "  [1] Complete - full installation (recommended)"
    echo "      Python env + all extras (API, schema agent, LLM providers),"
    echo "      web UI, Crystal environment preflight."
    echo
    echo "  [2] Custom - choose the components"
    echo "      e.g. an ETL-only box without the Crystal environment, or"
    echo "      an API/CLI server without the web UI."
    echo
    printf "Choose [1/2] (Enter = 1): "
    read -r choice || choice=""
    if [ "$choice" = "2" ]; then MODE="Custom"; else MODE="Complete"; fi
fi

ask() {  # ask "prompt" default(Y/N) -> 0 yes / 1 no; Complete = defaults
    if [ "$MODE" = "Complete" ]; then [ "$2" = "Y" ]; return; fi
    if [ "$2" = "Y" ]; then suffix="[Y/n]"; else suffix="[y/N]"; fi
    printf "  %s %s: " "$1" "$suffix"
    read -r a || a=""
    if [ -z "$a" ]; then [ "$2" = "Y" ]; return; fi
    case "$a" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

echo
echo "Components ($MODE):"
echo "  + Python environment + core package (always installed)"
WANT_LLM=0; ask "LLM provider clients (Anthropic/OpenAI - local Ollama needs neither)?" Y && WANT_LLM=1
WANT_UI=0;  ask "Web UI (needs Node.js 18+; skip for an API/CLI-only box)?" Y && WANT_UI=1
WANT_CR=0;  ask "Crystal environment preflight (.rpt extraction + engine validation)?" Y && WANT_CR=1

echo
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
if [ "$WANT_UI" = 1 ]; then
    if command -v npm >/dev/null 2>&1; then
        echo "  + Node.js found: $(node --version) (needed once, to build the web UI)"
    else
        echo "  x Node.js 18+ not found - https://nodejs.org/"
        echo "    (or re-run with Custom and deselect the web UI)"; ok=0
    fi
else
    echo "  - Node.js: not needed (web UI deselected)"
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
EXTRAS="api,schema"
if [ "$WANT_LLM" = 1 ]; then EXTRAS="api,schema,llm"; fi
echo "  installing the package + extras [$EXTRAS]..."
"$PY" -m pip install -e ".[$EXTRAS]" --quiet
echo "  + Python environment ready"

echo
if [ "$WANT_UI" = 1 ]; then
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
else
    echo "[3/4] Web UI: skipped (API + CLI only)"
fi

echo
if [ "$WANT_CR" = 1 ]; then
    echo "[4/4] Crystal Reports environment (only needed to extract"
    echo "      .rpt files and engine-validate .prpt output):"
    "$PY" -m pentaho_migration.cli report-env || true
    echo "      Anything missing above? See docs/INSTALL.md - the app works"
    echo "      without it for RptToXml dumps and all ETL sources."
else
    echo "[4/4] Crystal environment preflight: skipped"
fi

echo
echo "Environment doctor - every moving part, what is ready and what"
echo "is missing (third-party installs are YOUR call - see next steps):"
"$PY" -m pentaho_migration.cli doctor || true

cat <<EOF

=============================================================
  Installed ($MODE). Next steps:

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
