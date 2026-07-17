#!/usr/bin/env bash
# ============================================================================
# Developer helper for Migration Copilot on Linux (and macOS).
#
# Mirrors the Makefile targets for environments without make.
# Run from anywhere; the script locates the repo root itself.
#
#   ./scripts/dev.sh setup           # create venv + install everything (run once)
#   ./scripts/dev.sh test            # run the test suite
#   ./scripts/dev.sh run             # start the review UI on http://127.0.0.1:8321
#   ./scripts/dev.sh run-dev         # UI with auto-reload
#   ./scripts/dev.sh convert         # convert the sample export into output/
#   ./scripts/dev.sh convert my.xml  # convert a specific PowerCenter export
#   ./scripts/dev.sh gaps            # coverage/gap analysis over samples/informatica
#   ./scripts/dev.sh ui-install      # npm install for the React frontend
#   ./scripts/dev.sh ui-build        # build the React UI (served by `run`)
#   ./scripts/dev.sh ui-dev          # frontend dev server with hot reload
#   ./scripts/dev.sh status          # environment health check
#   ./scripts/dev.sh clean           # remove caches and generated output
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
PYTHON="$VENV/bin/python"
SAMPLE="$ROOT/samples/m_load_sales.xml"
PORT="${PORT:-8321}"

step() { printf '\033[36m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[32m    %s\033[0m\n' "$*"; }
warn() { printf '\033[33m    %s\033[0m\n' "$*"; }

assert_venv() {
    if [[ ! -x "$PYTHON" ]]; then
        warn "Virtual environment not found at $VENV"
        warn "Run: ./scripts/dev.sh setup"
        exit 1
    fi
}

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            echo "$candidate"
            return
        fi
    done
    warn "No python3 found. Install Python 3.11+ (e.g. apt install python3-venv)."
    exit 1
}

cmd_setup() {
    local py; py="$(find_python)"
    step "Creating virtual environment with $py at $VENV"
    "$py" -m venv "$VENV"
    cmd_install
    ok "Setup complete. Try: ./scripts/dev.sh test"
}

cmd_install() {
    assert_venv
    step "Installing pdi-migration (editable) with dev+api extras"
    "$PYTHON" -m pip install --upgrade pip --quiet
    "$PYTHON" -m pip install -e "$ROOT[dev,api]"
    ok "Dependencies installed"
}

case "${1:-help}" in
    help)
        sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
        ;;
    setup)   cmd_setup ;;
    install) cmd_install ;;
    test)
        assert_venv
        step "Running test suite"
        "$PYTHON" -m pytest -q "$ROOT/tests"
        ;;
    test-verbose)
        assert_venv
        "$PYTHON" -m pytest -v "$ROOT/tests"
        ;;
    run)
        assert_venv
        step "Review UI:  http://127.0.0.1:$PORT    (Ctrl+C to stop)"
        step "API docs:   http://127.0.0.1:$PORT/docs"
        "$PYTHON" -m uvicorn pdi_migration.api.main:app --port "$PORT"
        ;;
    run-dev)
        assert_venv
        step "Review UI (auto-reload):  http://127.0.0.1:$PORT"
        "$PYTHON" -m uvicorn pdi_migration.api.main:app --port "$PORT" --reload
        ;;
    convert)
        assert_venv
        file="${2:-$SAMPLE}"
        step "Converting $file -> $ROOT/output"
        "$PYTHON" -m pdi_migration.cli convert "$file" -o "$ROOT/output"
        ;;
    parse)
        assert_venv
        "$PYTHON" -m pdi_migration.cli parse "${2:-$SAMPLE}"
        ;;
    gaps)
        assert_venv
        dir="${2:-$ROOT/samples/informatica}"
        step "Coverage/gap analysis over $dir"
        "$PYTHON" -m pdi_migration.cli gaps "$dir"
        ;;
    ui-install)
        step "Installing frontend dependencies (Node 18+ required)"
        (cd "$ROOT/frontend" && npm install --no-fund --no-audit)
        ;;
    ui-build)
        step "Building React UI into frontend/dist"
        (cd "$ROOT/frontend" && npm run build)
        ok "Built. './scripts/dev.sh run' now serves the UI"
        ;;
    ui-dev)
        step "Frontend dev server with hot reload (start the backend first)"
        (cd "$ROOT/frontend" && npm run dev)
        ;;
    status)
        step "Environment status"
        if [[ -x "$PYTHON" ]]; then
            ok "Python:  $("$PYTHON" --version)"
            version="$("$PYTHON" -m pip show pdi-migration 2>/dev/null | awk '/^Version/{print $2}')"
            if [[ -n "$version" ]]; then ok "Package: pdi-migration $version"
            else warn "Package not installed - run: ./scripts/dev.sh install"; fi
        else
            warn "No venv - run: ./scripts/dev.sh setup"
        fi
        commit="$(git -C "$ROOT" log --oneline -1 2>/dev/null || true)"
        [[ -n "$commit" ]] && ok "Git:     $commit"
        ;;
    clean)
        step "Removing caches and generated output"
        rm -rf "$ROOT/output" "$ROOT/.pytest_cache" "$ROOT/build" "$ROOT/dist" "$ROOT"/src/*.egg-info
        find "$ROOT" -type d -name __pycache__ -not -path "$VENV/*" -exec rm -rf {} + 2>/dev/null || true
        ok "clean"
        ;;
    distclean)
        "$0" clean
        step "Removing virtual environment"
        rm -rf "$VENV"
        ok "removed .venv"
        ;;
    *)
        warn "Unknown command: $1  (try: ./scripts/dev.sh help)"
        exit 1
        ;;
esac
