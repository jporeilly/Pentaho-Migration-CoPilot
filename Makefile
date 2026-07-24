# ============================================================================
# Migration Copilot — developer Makefile
#
# Works on Linux/macOS out of the box, and on Windows 11 when make is
# installed (e.g. `winget install ezwinports.make` or `choco install make`).
# No make on Windows? Use the equivalent helper script instead:
#     scripts\dev.ps1 <target>        (same target names)
#
# Usage:
#     make            # shows help
#     make setup      # create venv + install everything
#     make test       # run the test suite
#     make run        # start the review UI on http://127.0.0.1:8321
#     make convert    # convert the sample export into output/
# ============================================================================

ifeq ($(OS),Windows_NT)
    PY       := py -3.13
    VENV_BIN := .venv/Scripts
else
    PY       := python3
    VENV_BIN := .venv/bin
endif

PYTHON  := $(VENV_BIN)/python
PORT    ?= 8321
SAMPLE  ?= samples/m_load_sales.xml
OUT     ?= output/informatica

.DEFAULT_GOAL := help
.PHONY: help setup venv install test test-verbose run run-dev convert parse gaps ui-install ui-build ui-dev status clean distclean

help: ## Show this help
	@echo "Migration Copilot - available targets:"
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup: venv install ## Create venv and install all dependencies (run once)
	@echo "Setup complete. Try: make test"

venv: ## Create the virtual environment (.venv)
	$(PY) -m venv .venv

install: ## Install the package editable with dev+api extras
	$(PYTHON) -m pip install --upgrade pip --quiet
	$(PYTHON) -m pip install -e ".[dev,api]"

test: ## Run the test suite
	$(PYTHON) -m pytest -q

test-verbose: ## Run tests with full output
	$(PYTHON) -m pytest -v

run: ## Start the review UI + API on http://127.0.0.1:$(PORT)
	$(PYTHON) -m uvicorn pentaho_migration.api.main:app --port $(PORT)

run-dev: ## Start the UI with auto-reload (development)
	$(PYTHON) -m uvicorn pentaho_migration.api.main:app --port $(PORT) --reload

convert: ## Convert SAMPLE (default: sample export) into OUT/
	$(PYTHON) -m pentaho_migration.cli convert $(SAMPLE) -o $(OUT)

parse: ## Parse SAMPLE and print the extracted IR
	$(PYTHON) -m pentaho_migration.cli parse $(SAMPLE)

gaps: ## Coverage/gap analysis over samples/informatica (real corpus)
	$(PYTHON) -m pentaho_migration.cli gaps samples/informatica

ui-install: ## Install frontend dependencies (requires Node 18+)
	cd frontend && npm install --no-fund --no-audit

ui-build: ## Build the React UI into frontend/dist (served by `make run`)
	cd frontend && npm run build

ui-dev: ## Frontend dev server with hot reload (backend must be running)
	cd frontend && npm run dev

status: ## Show environment status (python, venv, deps, git)
	@echo "Python:    " && $(PYTHON) --version || echo "  venv missing - run: make setup"
	@echo "Package:   " && $(PYTHON) -m pip show pentaho-migration | grep -E "^(Name|Version|Location)" || true
	@echo "Git:       " && git log --oneline -1

clean: ## Remove build artifacts, caches, and generated output
	-rm -rf output .pytest_cache build dist src/*.egg-info
	-find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true

distclean: clean ## clean + remove the virtual environment
	-rm -rf .venv
