# Migration Copilot (PDI-Migration)

AI-assisted migration of legacy ETL (Informatica, SSIS, Talend, DataStage) into native
Pentaho Data Integration pipelines. See `docs/` for the technical brief.

**Design principle:** deterministic where accuracy is non-negotiable, AI only where
semantic judgment is required.

```text
PARSE (deterministic) -> MAP (rules + LLM) -> GENERATE (templating) -> VALIDATE (diff + confidence)
```

## Architecture

The core is a framework-agnostic Python package (`src/pdi_migration/`) driven by a CLI.
FastAPI (`pdi_migration.api`) is a thin layer over it; the Phase 1 review UI (React)
will consume that API.

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

# Review UI + API — open http://127.0.0.1:8000 (UI) or /docs (Swagger)
.venv\Scripts\uvicorn pdi_migration.api.main:app --reload
```

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
- [x] Review UI (dark, single page) served at / by FastAPI
- [ ] Per-step-type config for remaining rule types (Merge Join keys, Stream Lookup, Insert/Update)
- [ ] LLM expression translation (Informatica expression language -> PDI), constrained by validated examples
- [ ] Runtime diff harness: run old vs. new on sample data, diff outputs
- [ ] Sample study: parse real PowerCenter exports, measure the actual clean-mapping %
