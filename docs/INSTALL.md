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
git clone <repo-url> Pentaho-Migration
cd Pentaho-Migration
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
.venv\Scripts\pentaho-migrate convert samples\m_load_sales.xml -o output
```

## Run the review UI

```powershell
.venv\Scripts\uvicorn pentaho_migration.api.main:app --port 8321
```

Then open <http://127.0.0.1:8321> (UI) or <http://127.0.0.1:8321/docs> (Swagger).

## Optional: LLM expression translation

Install [Ollama](https://ollama.com), start it, then open **⚙ Settings** in the UI —
it detects your hardware (multi-GPU VRAM aggregates), recommends a model, and pulls
it with one click. Settings persist to `config/settings.json`.

## Optional: Crystal Reports migration environment

**Internal shortcut:** `.\scripts\setup-crystal-env.ps1` installs everything
below from this repo's private `crystal-deps-v1` release (needs a logged-in
`gh` CLI) — no SAP registration required. The mirrored runtime MSIs are for
internal private-repo distribution only; if this repository ever goes public,
remove that release pending a license review. Customer machines should follow
the official steps below.

The Crystal pipeline converts RptToXml dumps out of the box. To *extract* dumps
from customer `.rpt` files and to *round-trip validate* generated `.prpt`
bundles, set up the following (then confirm with `pentaho-migrate report-env`):

1. **SAP Crystal Reports .NET runtime** (free) — register and download at
   <https://www.sap.com/registration/trial.9a4afb3b-7eaa-42af-98ce-abeae5deb784.html>
   (the "SAP Crystal Reports, version for Visual Studio" package; latest
   support pack). Install the **64-bit runtime MSI** (`CRRuntime_64bit_13_0_xx.msi`);
   if RptToXml later reports missing `CrystalDecisions` assemblies, also install
   the 32-bit MSI — both coexist. Runtime-only: don't run the full
   VS-integration EXE unless you develop with Crystal in Visual Studio.
2. **RptToXml.exe** — download the release zip from
   <https://github.com/ajryan/RptToXml/releases> and unzip its contents into
   `tools/RptToXml/` (so `tools/RptToXml/RptToXml.exe` exists), or set
   `RPTTOXML_PATH` to wherever it lives.
3. **Pentaho Report Designer + Java** (for `--validate`) — any Pentaho suite
   install works; auto-detected at `C:\Pentaho\design-tools\report-designer`
   or via `PRD_HOME`. Java is found via the suite's bundled JDK, `JAVA_HOME`,
   or PATH.

Then the corpus/engagement workflow is:

```powershell
pentaho-migrate report-env                       # preflight: all four checks green?
.\scripts\extract-rpt.ps1 -InDir C:\customer\rpts -OutDir C:\customer\xml
pentaho-migrate report-scrub C:\customer\xml     # blank credentials RptToXml copies from .rpt files
pentaho-migrate report-gaps  C:\customer\xml     # parse coverage, formula rates, portfolio effort
pentaho-migrate report C:\customer\xml\Foo.xml --jndi MyDS -t --validate
```

## Optional: Docker

```bash
docker build -t migration-copilot .
docker run -p 8321:8321 migration-copilot
```

## Optional: hardening

- `PENTAHO_MIGRATION_API_KEY=<secret>` — requires an `X-API-Key` header on all mutating
  endpoints (unset by default for frictionless local use).
- Uploads are capped at 50 MB.
