# Migration Copilot (PDI-Migration-CoPilot)

**AI-assisted migration of legacy ETL — Informatica PowerCenter today; SSIS, Talend,
DataStage next — into native Pentaho Data Integration pipelines.**

Version **0.4.0** ([VERSION.md](VERSION.md) · [CHANGELOG.md](CHANGELOG.md)) · Phase 0: internal tool ·
[Technical brief](docs/Migration_Copilot_Technical_Brief.pdf)

Every legacy ETL platform locks customers in with the sunk cost of thousands of
hand-built pipelines — rebuilding 3,000–10,000 mappings by hand is a multi-year,
seven-figure engagement. Migration Copilot turns that migration into an assisted
effort measured in weeks, converting the switching-cost objection into the reason
a prospect moves to Pentaho.

**Design principle:** deterministic where accuracy is non-negotiable, AI only where
semantic judgment is genuinely required. The tool never guesses — anything it cannot
convert is routed to explicit human handoff, never hidden.

```text
PARSE (deterministic) -> MAP (rules + LLM) -> GENERATE (templating) -> VALIDATE (diff + confidence)
```

## The app

A guided dashboard walks each conversion through the pipeline with a stepper:

1. **Upload** — drag-and-drop a PowerCenter XML export (or one click on the bundled sample).
2. **Parse** — *source analysis first*: detected PowerCenter release (8.1–10.5 mapped from
   the repository version), repository/database/codepage facts, object counts, and
   plain-language pre-migration warnings (workflows/sessions not converted, mapplets,
   unmapped step types, SQL overrides, codepage caveats). Then the parsed structure:
   an SVG flow diagram plus every step's fields and expressions.
3. **Map** — KPI tiles and a filterable table of every mapping decision with its
   confidence: `auto` (rules library), `review` (needs a human eye), `manual` (no
   mapping — human converts).
4. **Generate** — preview and download the .ktr; it opens as an editable transformation
   in Spoon, with all TODOs carried into step descriptions.
5. **Validate** — migration report and a human review checklist; the runtime diff
   harness (run old vs. new on sample data, diff outputs) is the next major milestone.

Also in the UI: multi-mapping selector (real exports hold up to 32 mappings per file),
four color themes (Midnight, Slate, Pentaho, Light), a version badge that pops up the
changelog, and a **⚙ Settings** page that auto-detects your hardware (RAM, NVIDIA VRAM),
`OLLAMA_*` environment, and running Ollama server, then recommends and pulls the right
local model for expression translation.

## Architecture

Framework-agnostic Python core driven by a CLI; FastAPI as a thin API layer; React
(Vite) frontend served by FastAPI at `/`.

| Layer | Where | Status |
| --- | --- | --- |
| Parser (Parse) | `src/pdi_migration/parser/` | PowerCenter XML → normalized Pydantic IR; source analysis with version detection. Zero failures across the 50-file real corpus |
| Rules mapper (Map) | `src/pdi_migration/mapper/` + `rules/powercenter_to_pdi.yaml` | 17 transformation-type rules with per-rule confidence; unknown types → explicit manual handoff |
| LLM translator (Map) | `src/pdi_migration/llm/` | Working: deterministic fast-path + constrained Ollama translation (schema-forced JSON, function-mapping prompt); every LLM output flagged `review` |
| KTR generator (Generate) | `src/pdi_migration/generator/` | Steps, hops, layout + real config for Table Input (SQL), Table Output, Sort, Group By (keys + aggregates), script steps |
| Validator (Validate) | `src/pdi_migration/validator/` | Migration report, corpus gap analysis, pre-migration assessment; runtime diff harness stubbed |
| API | `src/pdi_migration/api/` | `/convert`, `/parse`, `/settings`, `/changelog`, `/brief`, `/sample`, `/health` — Swagger at `/docs` |
| UI | `frontend/` | React 18 + Vite, no UI framework, themeable CSS variables |

## Quick start

```powershell
# Windows 11
.\scripts\dev.ps1 setup       # venv + all Python deps
.\scripts\dev.ps1 ui-install  # npm install (Node 18+)
.\scripts\dev.ps1 ui-build    # build the React UI
.\scripts\dev.ps1 run         # http://127.0.0.1:8321
```

```bash
# Linux / macOS (or use ./scripts/dev.sh with the same commands)
make setup ui-install ui-build
make run
```

Full details in [docs/INSTALL.md](docs/INSTALL.md). Helper commands (identical across
`make`, `dev.ps1`, `dev.sh`): `setup · install · test · run · run-dev · convert ·
parse · gaps · ui-install · ui-build · ui-dev · status · clean · distclean`.

## CLI

```powershell
pdi-migrate parse   <export.xml>   # inspect the extracted IR
pdi-migrate convert <export.xml>   # source analysis + .ktr files + report -> output\informatica
pdi-migrate gaps    [directory]    # corpus coverage: auto/review/manual + gap list
```

`convert` prints the source analysis first — tool version, database, and warnings —
so you know what you're dealing with before touching the output.

## Real-world corpus

`samples/informatica/` holds **50 genuine PowerCenter exports (148 mappings, 1,316
steps)** spanning six repository versions (PowerCenter ~9.0 → 10.5), harvested from
public sources: the [HHS/Informatica](https://github.com/HHS/Informatica) production
payroll ETL, a production DWH framework, converter test fixtures, and coursework from
a dozen authors. All 50 parse with zero errors, including a 7.2 MB export with 11,327
connectors.

Current coverage measured on that corpus with `pdi-migrate gaps`: **54% auto**,
45% review (dominated by untranslated expressions — 4,321 of them), and 19 manual
steps across 3 unmapped types (Stored Procedure, Custom Transformation, Transaction
Control).

## Tests

```powershell
.venv\Scripts\python -m pytest      # 31 tests
```

## Roadmap

**Phase 0 — internal tool (PowerCenter only), in progress:**

- [x] Deterministic parser + normalized IR (fields, expressions, hops)
- [x] Rules library with per-step confidence; explicit manual handoff
- [x] KTR generation with per-step-type config (Table In/Out, Sort, Group By, script)
- [x] Guided dashboard UI: stepper, flow diagram, mapping selector, themes
- [x] Pre-migration source analysis with version detection and risk warnings
- [x] Real-export corpus (50 files) + gap analysis
- [x] Ollama settings with hardware-based model recommendation
- [x] LLM expression translation (constrained, confidence-scored, mandatory review) — `--translate` / ✨ button
- [ ] Remaining step-type config: Merge Join, Stream Lookup, Insert/Update, Call DB Procedure
- [ ] Runtime diff harness: run old vs. new on sample data, diff outputs, no auto-deploy
- [ ] Workflow/Session → PDI Job (.kjb) conversion

**Phase 1** — assisted customer product with confidence scoring and mandatory human
review. **Phase 2** — multi-source: SSIS, then Talend / DataStage.

## Project documents

| Document | Purpose |
| --- | --- |
| [VERSION.md](VERSION.md) | Current version |
| [CHANGELOG.md](CHANGELOG.md) | Release history (Keep a Changelog) |
| [docs/INSTALL.md](docs/INSTALL.md) | Installation guide |
| [docs/Migration_Copilot_Technical_Brief.pdf](docs/Migration_Copilot_Technical_Brief.pdf) | Product brief: opportunity, architecture, risks, business case |
