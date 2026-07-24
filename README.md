# Pentaho Migration Copilot

**AI-assisted migration of legacy data platforms into Pentaho — ETL and BI reports:**
**Informatica PowerCenter and Talend → native PDI pipelines (SSIS and DataStage next);**
**SAP Crystal Reports → Pentaho Report Designer (.prpt).**

Version **1.18.0** ([VERSION.md](VERSION.md) · [CHANGELOG.md](CHANGELOG.md)) · Phase 0 complete · Phase 2: Talend shipped ·
[Technical brief](docs/Migration_Copilot_Technical_Brief.pdf)

Every legacy data platform locks customers in with the sunk cost of thousands of
hand-built artifacts — ETL mappings and operational reports alike. Rebuilding
3,000–10,000 of them by hand is a multi-year, seven-figure engagement. Migration
Copilot turns that migration into an assisted effort measured in weeks, converting
the switching-cost objection into the reason a prospect moves to Pentaho.

**Design principle:** deterministic where accuracy is non-negotiable, AI only where
semantic judgment is genuinely required. The tool never guesses — anything it cannot
convert is routed to explicit human handoff, never hidden.

```text
PARSE (deterministic) -> MAP (rules + LLM) -> GENERATE (templating) -> VALIDATE (diff + confidence)
```

## The app

A guided dashboard walks each conversion through the pipeline with a stepper —
one flow per artifact family. Uploads are routed by content sniffing, never by
extension: ETL exports enter **Upload → Parse → Map → Generate → Validate**;
Crystal RptToXml dumps enter **Upload → Inspect → Formulas → Download** (report
structure and datasource SQL, per-formula translation with ✨ LLM assist for
what rules cannot prove, engine-verifiable .prpt + conversion report, effort &
cost estimate). Formulas the translator *can* prove but OpenFormula can't
express are rewritten into native PRD report functions instead of being left
manual: running-total variables become `ItemSumFunction` / `ItemCountFunction`
and whole-formula aggregates (`Sum`, `Count`, `Maximum`, `Minimum`) become
`Total*` functions — generated, wired to their referencing elements, and
flagged for review. Simple record selections fold into the SQL `WHERE`
(alias-aware for Command-based reports), so converted parameter prompts filter
live data. The Inspect page carries the **schema-aware SQL agent**: the report
SQL is `EXPLAIN`-validated against the live JNDI target automatically, and a
schema-grounded chat answers join/column questions and proposes corrected SQL
as a reviewable diff — applied only on click, recorded as a review item. The
ETL flow in detail:

1. **Upload** — drag-and-drop a PowerCenter `.xml` or Talend `.item` export (format
   auto-detected by content, never by extension) — or one click on the bundled sample.
2. **Parse** — *source analysis first*: detected tool and release (PowerCenter 8.1–10.5
   from the repository version; Talend from the job file), repository/database/codepage
   facts, object counts, and plain-language pre-migration warnings (orchestration not
   converted, mapplets/joblets, unmapped step types, SQL overrides, codepage caveats).
   Then the parsed structure: an SVG flow diagram plus every step's fields and expressions.
3. **Map** — KPI tiles, a filterable table of every mapping decision with its
   confidence (`auto` / `review` / `manual`), source-vs-converted diagrams, per-step
   impact analysis with click-through navigation, and **🤖 AI-suggested solutions**:
   the LLM proposes a concrete PDI approach (steps, config, code, pitfalls) for any
   step, from its real configuration — advisory, never auto-applied.
4. **Generate** — preview and download the .ktr; it opens as an editable transformation
   in Spoon, with all TODOs carried into step descriptions. PowerCenter workflows also
   emit PDI Jobs (.kjb) with sessions wired to their .ktr files.
5. **Validate** — migration confidence score (0–100, A–E), human review checklist,
   **sandbox test kit** (PDI setup guide, CREATE TABLE DDL inferred from the export's
   field metadata, seeded synthetic test CSVs — so first runs happen safely against a
   sandbox database, never production), **measured output parity** (upload old vs. new
   CSV outputs for a PASS/NEAR/FAIL diff), and report downloads — branded **PDF**,
   markdown, and JSON.

Also in the UI: a **📁 Project** page (the batch-converted portfolio — click any
mapping to walk through its conversion; track review status per mapping), multi-mapping
selector (real exports hold up to 32 mappings per file), four color themes, a version
badge that pops up the changelog, and a **⚙ Settings** page that auto-detects your
hardware (RAM, NVIDIA GPUs — multi-GPU VRAM aggregates), `OLLAMA_*` environment, and
running Ollama server, then recommends and pulls the right local model for expression
translation.

## Architecture

Framework-agnostic Python core driven by a CLI; FastAPI as a thin API layer; React
(Vite) frontend served by FastAPI at `/`.

<img width="1345" height="560" alt="arch_crop" src="https://github.com/user-attachments/assets/3d4ae800-129e-45fd-85b2-1297bfe2e597" />

| Layer | Where | Status |
| --- | --- | --- |
| Parsers (Parse) | `src/pentaho_migration/parser/` | PowerCenter XML and Talend .item → one normalized Pydantic IR; content-sniffing auto-detection; source analysis with version detection. Zero failures across both real corpora (90 files) |
| Rules mappers (Map) | `src/pentaho_migration/mapper/` + `rules/*.yaml` | Per-source rules libraries with governance metadata (PowerCenter v3: 18 types; Talend v2: 60+ components); unknown types → explicit manual handoff |
| LLM (Map) | `src/pentaho_migration/llm/` | Expression translation (Informatica + Java prompts, schema-forced JSON, always flagged `review`), per-step solution suggestions, hardware detection with multi-GPU model recommendation |
| Generators (Generate) | `src/pentaho_migration/generator/` | .ktr with real config for 9 step types (incl. Merge Join keys, Stream Lookup with injected lookup source); .kjb jobs from PowerCenter workflows |
| Validator (Validate) | `src/pentaho_migration/validator/` | Migration report, gap analysis, pre-migration assessment, impact knowledge base (both sources), confidence score, effort & cost estimate (Copilot vs manual rebuild), CSV diff harness (measured parity) |
| Sandbox kits | `src/pentaho_migration/sandbox.py` | Per-mapping setup guide, inferred DDL, seeded synthetic test data |
| Project store | `src/pentaho_migration/project.py` | SQLite portfolio: batch results, scores, per-mapping review status, click-through re-open, portfolio effort/cost totals |
| PDI runner | `src/pentaho_migration/pdi_runner.py` | Executes .ktr/.kjb via Pan/Kitchen in an auto-detected local PDI install |
| PDF reports | `src/pentaho_migration/report_pdf.py` | Branded per-mapping report: score, warnings, checklist, expressions, impact, data flow |
| Reports family | `src/pentaho_migration/reports/` | SAP Crystal Reports → PRD .prpt: RptToXml parser (zero failures on the 150-file real corpus), deterministic Crystal→OpenFormula translator with blocked-idiom rewrites (running totals & aggregates become native PRD report functions, review-flagged) + LLM assist for the remainder, alias-aware record-selection → SQL WHERE folding, engine-verified bundle writer (round-trip validator), chart migration, guided UI flow, credential scrubbing, forked extractor, environment preflight |
| API | `src/pentaho_migration/api/` | convert/parse/translate(+jobs)/suggest/sandbox/diff/project/report/settings + reports (inspect/convert) — Swagger at `/docs`; optional API-key auth |
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
pentaho-migrate parse   <export.xml>        # inspect the extracted IR
pentaho-migrate convert <export.xml>        # source analysis + .ktr + report + confidence score
pentaho-migrate sandbox <export.xml>        # sandbox kit: setup guide + DDL + synthetic test CSVs
pentaho-migrate batch   [directory]         # convert a whole corpus into the project store
pentaho-migrate project                     # portfolio view: every mapping, score, review status
pentaho-migrate gaps    [directory]         # corpus coverage: auto/review/manual + gap list
pentaho-migrate diff    old.csv new.csv -k ID  # measured output parity (exit 0 on PASS)
pentaho-migrate run     <file.ktr|.kjb>     # execute in the local PDI install (Pan/Kitchen)
pentaho-migrate report  <rpttoxml.xml> -t   # Crystal dump -> .prpt + report; -t = LLM-assist manual formulas
pentaho-migrate report ... --validate       # load the .prpt through the real Pentaho Reporting engine
pentaho-migrate report-env                  # preflight: PRD, Java, SAP Crystal runtime, RptToXml
pentaho-migrate report-sql <dump> --jndi <ds> # validate the report SQL against the live JNDI target (EXPLAIN)
pentaho-migrate report-gaps [directory]     # Crystal corpus coverage: parse rate, formula rates, portfolio effort
pentaho-migrate report-scrub [directory]    # blank credentials RptToXml copies out of .rpt files — run before sharing dumps
pentaho-migrate report-batch [directory]    # convert a Crystal corpus into the project store (joins the portfolio)
```

Crystal end-to-end (`.rpt` in hand): install the free SAP Crystal .NET runtime and
RptToXml.exe once (see [docs/INSTALL.md](docs/INSTALL.md)), then
`report-env` → `scripts/extract-rpt.ps1` → `report-scrub` → `report-gaps` →
`report --jndi <ds> -t --validate` per report.

`convert` prints the source analysis first — tool version, database, and warnings —
so you know what you're dealing with before touching the output.

## Real-world corpus

`samples/informatica/` holds **50 genuine PowerCenter exports (148 mappings, 1,316
steps)** spanning six repository versions (PowerCenter ~9.0 → 10.5), harvested from
public sources: the [HHS/Informatica](https://github.com/HHS/Informatica) production
payroll ETL, a production DWH framework, converter test fixtures, and coursework from
a dozen authors. All 50 parse with zero errors, including a 7.2 MB export with 11,327
connectors.

Current coverage measured on that corpus with `pentaho-migrate gaps`: **54% auto**,
45% review (dominated by untranslated expressions — 4,321 of them), and a handful
of manual steps (Custom Transformation, Transaction Control).

`samples/talend/` holds **40 genuine Talend jobs spanning versions 5.1 → 8.0.1** —
production data warehouses, Red Hat's oVirt DWH, health-informatics ETL, Salesforce
REST syncs — 763 steps across 104 distinct components, all parsing with zero errors.
Rules v2 (extended from this corpus's gap analysis) cut manual steps from 207 to 42;
avg confidence 62/100.

`samples/crystal-rpt/` holds **150 genuine Crystal Reports `.rpt` binaries**
harvested from public GitHub repositories, with fork-extracted, credential-scrubbed
dumps in `samples/crystal/real/`. All 150 parse with zero errors; of their 726
formulas, **80% translate deterministically** (auto + review, including idiom
rewrites) before any LLM assist. `samples/cr_demo/` is the demo set: six authored
CSCU credit-union reports of increasing complexity that convert *and render live*
against the CSCU Postgres database — including working parameter prompts, a bar
chart, and a running balance rebuilt as a PRD report function.

## Tests & CI

```powershell
.venv\Scripts\python -m pytest      # 187 tests, incl. docs-consistency enforcement
```

GitHub Actions runs the suite and the frontend build on every push.

## Deployment

```bash
docker build -t migration-copilot .
docker run -p 8321:8321 migration-copilot
```

Optional hardening: set `PENTAHO_MIGRATION_API_KEY` to require an `X-API-Key` header on
all mutating endpoints; uploads are capped at 50 MB.

## Roadmap

**Phase 0 — internal tool (PowerCenter), complete:**

- [x] Deterministic parser + normalized IR (fields, expressions, hops)
- [x] Rules library with per-step confidence; explicit manual handoff
- [x] KTR generation with per-step-type config (Table In/Out, Sort, Group By, script)
- [x] Guided dashboard UI: stepper, flow diagram, mapping selector, themes
- [x] Pre-migration source analysis with version detection and risk warnings
- [x] Real-export corpus (50 files) + gap analysis
- [x] Ollama settings with hardware-based model recommendation
- [x] LLM expression translation (constrained, confidence-scored, mandatory review) — `--translate` / ✨ button
- [x] Diff harness (measured parity): CSV compare with tolerance, key matching, verdicts
- [x] Project mode: batch conversion, SQLite portfolio, review-status tracking
- [x] Hardening (API key, size limits, logging), CI, Docker packaging, rules governance
- [x] Remaining step-type config: Merge Join (keys from join conditions), Stream Lookup (with injected lookup-source step), Insert/Update, Call DB Procedure
- [x] PDI execution: `pentaho-migrate run` drives Pan/Kitchen in a local PDI install (auto-detected), log-aware verdicts
- [x] Workflow/Session → PDI Job (.kjb) conversion: sessions wired to sibling .ktr files, placeholders for unconvertible tasks, link conditions preserved
- [x] PDF migration report (branded, per mapping)

**Phase 2 — multi-source, in progress:**

- [x] Talend (v1.10.0): .item parser, 60+ component rules validated against a 40-job
  real corpus (versions 5.1 → 8.0.1), Java→JavaScript expression translation,
  Talend impact knowledge, 🤖 per-step AI solution suggestions
- [x] SAP Crystal Reports → PRD (v1.11 → 1.18): RptToXml parser, formula
  translator with idiom rewrites, LLM assist, record-selection folding,
  Crystal-faithful layout, charts, engine round-trip validation, forked
  extractor, CSCU live-render demo ladder, schema-aware SQL agent
  (live-database validation + grounded chat)
- [ ] SSIS (.dtsx)
- [ ] IBM DataStage (.dsx)

**Phase 1** — assisted customer product packaging (multi-user, confidence scoring and
mandatory review are already built) — sequenced after Phase 2 sources per demand.

## Project documents

| Document | Purpose |
| --- | --- |
| [VERSION.md](VERSION.md) | Current version |
| [CHANGELOG.md](CHANGELOG.md) | Release history (Keep a Changelog) |
| [docs/INSTALL.md](docs/INSTALL.md) | Installation guide |
| [docs/Migration_Copilot_Technical_Brief.pdf](docs/Migration_Copilot_Technical_Brief.pdf) | Product brief: opportunity, architecture, risks, business case |
