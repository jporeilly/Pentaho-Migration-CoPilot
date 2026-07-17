# PDI Migration Copilot

AI-assisted migration of legacy ETL (Informatica, SSIS, Talend, DataStage) into native
Pentaho Data Integration pipelines. See `docs/` for the technical brief.

**Design principle:** deterministic where accuracy is non-negotiable, AI only where
semantic judgment is required.

```text
PARSE (deterministic) -> MAP (rules + LLM) -> GENERATE (templating) -> VALIDATE (diff + confidence)
```

## Architecture

The core is a framework-agnostic Python package (`src/pdi_migration/`) driven by a CLI.
FastAPI (`pdi_migration.api`) is a thin layer over it, and a React review UI
(`frontend/`) is served by FastAPI at `/` — dark theme, drag-and-drop upload, KPI
tiles, pipeline flow diagram, filterable step table, .ktr download.

<img width="1345" height="560" alt="arch_crop" src="https://github.com/user-attachments/assets/3d4ae800-129e-45fd-85b2-1297bfe2e597" />



| Module       | Stage    | Status |
|--------------|----------|--------|
| `parser/`    | Parse    | PowerCenter XML exports -> normalized IR |
| `mapper/`    | Map      | Rules library working (`rules/powercenter_to_pdi.yaml`); LLM expression translation stubbed |
| `generator/` | Generate | Emits .ktr files: types, hops, layout, TODO notes, plus real config for Table Input/Output, Sort, Group By, and script steps |
| `validator/` | Validate | Static confidence report working; runtime diff harness stubbed |

Every step carries a confidence level — `auto`, `review`, or `manual` — and the mapper
never guesses: unknown transformation types are routed to manual handoff explicitly.

## Setup

See [docs/INSTALL.md](docs/INSTALL.md). Quick version:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,api]"
```

Version: see [VERSION.md](VERSION.md) · History: see [CHANGELOG.md](CHANGELOG.md)

## Usage

```powershell
# Inspect what the parser extracts
pdi-migrate parse samples\m_load_sales.xml

# Full conversion: .ktr skeletons + migration report
pdi-migrate convert samples\m_load_sales.xml -o output

# Coverage/gap analysis over the real corpus (samples\informatica)
pdi-migrate gaps samples\informatica

# Review UI + API — open http://127.0.0.1:8321 (UI) or /docs (Swagger)
.\scripts\dev.ps1 run        # Windows      (make run on Linux)
```

Everyday tasks are wrapped by `make` (Linux/macOS, or Windows with make installed)
and mirrored helper scripts — `scripts\dev.ps1` (Windows 11), `scripts/dev.sh`
(Linux): `setup · test · run · convert · gaps · ui-build · status · clean`.

## Real-world corpus

`samples/informatica/` holds genuine PowerCenter exports (50 files, 148 mappings,
1,316 steps) spanning six repository versions (~9.0 to 10.5), sourced from public
repos — the [HHS/Informatica](https://github.com/HHS/Informatica) production payroll
ETL, a Russian production DWH framework, and production/coursework exports from a
dozen other authors. Used to measure mapper coverage with `pdi-migrate gaps`
(currently 54% auto). All 50 parse with zero errors, including a 7.2 MB export
with 11,327 connectors.

## Tests

```powershell
.venv\Scripts\python -m pytest
```

## Phase 0 roadmap (internal tool, PowerCenter only)

- [x] Parser: mappings, transformations, fields, expressions, connectors
- [x] Rules library: top transformation types with per-rule confidence
- [x] KTR skeleton generation with confidence + TODO annotations
- [x] Static migration report (auto/review/manual counts)
- [x] Per-step-type KTR config emission: Table Input (SQL), Table Output, Sort keys, Group By keys + aggregates, script placeholder with typed output fields
- [x] Review UI: React (Vite) dashboard served at / by FastAPI — guided stepper (Upload/Parse/Map/Generate/Validate), tiles, flow diagram, step table, .ktr download, themes
- [x] Pre-migration source analysis: PowerCenter version detection + plain-language risk warnings
- [x] Real-export corpus (50 files, 148 mappings, PC ~9.0–10.5) + `gaps` coverage analysis — currently 54% auto, 3 unmapped types (Stored Procedure, Custom, Transaction Control)
- [ ] Per-step-type config for remaining rule types (Merge Join keys, Stream Lookup, Insert/Update)
- [ ] LLM expression translation (Informatica expression language -> PDI), constrained by validated examples — 4,160 real expressions waiting in the corpus
- [ ] Runtime diff harness: run old vs. new on sample data, diff outputs
- [ ] Workflow/Session (PDI Job) conversion — real corpus includes WORKFLOW elements, currently ignored
