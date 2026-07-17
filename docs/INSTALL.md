# Installation

## Requirements

- Windows / macOS / Linux
- Python 3.11+ (developed against 3.13 64-bit)
- Node.js 18+ (only for building/developing the React review UI)
- No database or PDI installation required for parsing/conversion; Pentaho Data
  Integration (Spoon) is only needed to open the generated .ktr files.

## Setup

The short way — helper scripts do everything below:

```powershell
.\scripts\dev.ps1 setup      # Windows 11
.\scripts\dev.ps1 ui-install
.\scripts\dev.ps1 ui-build
```

```bash
./scripts/dev.sh setup       # Linux (or: make setup ui-install ui-build)
./scripts/dev.sh ui-install
./scripts/dev.sh ui-build
```

Manually:

```powershell
git clone <repo-url> PDI-Migration
cd PDI-Migration
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,api]"
cd frontend; npm install; npm run build; cd ..
```

Extras:

- `dev` — pytest + httpx (tests)
- `api` — FastAPI, uvicorn, python-multipart (review UI + API)
- `llm` — anthropic SDK (expression translation; not yet used)

## Verify the install

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\pdi-migrate convert samples\m_load_sales.xml -o output
```

## Run the review UI

```powershell
.venv\Scripts\uvicorn pdi_migration.api.main:app --port 8321
```

Then open <http://127.0.0.1:8321> (UI) or <http://127.0.0.1:8321/docs> (Swagger).

## Optional: LLM expression translation

Install [Ollama](https://ollama.com), start it, then open **⚙ Settings** in the UI —
it detects your hardware (multi-GPU VRAM aggregates), recommends a model, and pulls
it with one click. Settings persist to `config/settings.json`.

## Optional: Docker

```bash
docker build -t migration-copilot .
docker run -p 8321:8321 migration-copilot
```

## Optional: hardening

- `PDI_MIGRATION_API_KEY=<secret>` — requires an `X-API-Key` header on all mutating
  endpoints (unset by default for frictionless local use).
- Uploads are capped at 50 MB.
