# Changelog

All notable changes to Migration Copilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning follows [SemVer](https://semver.org/).

## [1.7.0] — 2026-07-17

### Added

- **Side-by-side comparison** on the Map page: the original Informatica structure and
  the converted PDI pipeline as twin flow diagrams with matching layouts, plus hover
  tooltips on every diagram node.
- **Impact analysis**: a per-step examination of what converts automatically and how
  PDI's behavior differs from Informatica's — knowledge base covering sorted-input
  requirements (Group By/Merge Join), NULL semantics in translated expressions,
  lookup caching and multiple-match policies, sequence state persistence, update
  strategies, router multi-match, session-level target settings, and more. Each entry
  lists differences, required actions, and an impact level; a summary surfaces the top
  risks per mapping. Shown on the Map page and included in reports.
- **Migration confidence score** for every pipeline examined: a 0–100 static
  prediction (grade A–E) weighted across step mapping, expression translation, config
  completeness, and semantic impact — hero panel on the Validate page, chip in the
  workbench bar, per-mapping in CLI `convert`, and corpus average in `gaps`. Clearly
  labeled static until the diff harness provides measured confidence.
- **Report downloads**: per-mapping migration report as markdown or JSON (source
  analysis, score, step table, expressions, impact) from the Validate page; a
  "Download all .ktr" button for multi-mapping exports.
- **Best-practices guide** (`docs/BEST_PRACTICES.md`, 📘 in the masthead): inventory
  first, migrate the common 80%, sandbox staging, output parity, orchestration
  planning, sequence/state cutover, parallel running, audit trail.
- **Tooltips and explanations everywhere**: stepper stages, KPI tiles, confidence
  badges, PDI step types, diagram nodes, and page intros.
- **Docs-consistency test**: the suite fails if pyproject, `__version__`, VERSION.md,
  and the newest CHANGELOG entry disagree, or required docs are missing — documentation
  updates are now enforced per release.
- Source-tool badge (neutral lettermark) in the workbench bar.

## [1.6.0] — 2026-07-17

### Added

- **Sandbox test kits** — everything needed to run a converted .ktr safely:
  `setup.md` (step-by-step PDI guide: create a sandbox DB connection, wire the empty
  connection placeholders, create tables, load data, run & verify), `setup.sql`
  (CREATE TABLE DDL inferred from the export's field metadata; write-side tables
  derived from upstream fields), and `data_<step>.csv` synthetic test data shaped to
  the real column types (seeded — same seed, same data, reproducible runs).
  Available as `pdi-migrate sandbox <export.xml>` (writes to
  `output/informatica/sandbox/<mapping>/`), `POST /sandbox`, and a
  **🧪 Generate sandbox kit** section on the Validate page with per-file downloads.
- **Source analysis now warns about database setup**: steps that read/write databases
  are counted, with an explicit "connect to a SANDBOX, never production" warning and
  a pointer to the kit.

## [1.5.2] — 2026-07-17

### Changed

- Converted .ktr files now default to `output/informatica/` (CLI, Makefile, helper
  scripts); each file keeps the name of its source mapping, unchanged.

## [1.5.1] — 2026-07-17

### Added

- **LLM expression translation** — the first AI-assisted stage, per the brief's hybrid
  design. Two tiers: a deterministic fast-path passes through expressions that are
  already valid JavaScript (confidence `auto`); everything else goes to the configured
  Ollama model with a constrained function-mapping prompt (IIF, ISNULL, DECODE, SUBSTR
  1-based→0-based, TO_DATE→str2date, …) and schema-forced JSON output. Every LLM
  translation is flagged `review` — never silently trusted. Group By aggregates
  (SUM/AVG/…) are recognized as natively handled, not sent to the LLM. Failures leave
  an explicit TODO; they never block conversion.
- Translated JavaScript is emitted into the generated Modified Java Script step with
  the original Informatica expression and LLM confidence as comments; the .ktr step
  description distinguishes "translated — verify" from TODO.
- `POST /translate` API; `pdi-migrate convert --translate` CLI flag; **✨ Translate**
  button on the Map page showing live progress and updated results.
- Verified live against local Ollama (qwen2.5-coder:14b):
  `IIF(ISNULL(AMOUNT), 0, AMOUNT * 1.2)` → `(AMOUNT == null) ? 0 : AMOUNT * 1.2`.

### Changed

- Settings page: added a clear "← Back to workflow" button; the color-theme picker
  moved from the masthead into a new Appearance section (user feedback).
- Source analysis now counts only *untranslated* expressions in its warning.
- Release numbering restarted at 1.0.0 (previously 0.x); this release was briefly
  numbered 0.5.0/0.5.1.

### Removed

- `mapper/llm.py` stub (superseded by `llm/translate.py`).

## [1.3.0] — 2026-07-17

### Added

- **Workflow dashboard UI**: a guided stepper (Upload → Parse → Map → Generate →
  Validate) with one page per pipeline stage, next/back navigation, a workbench bar
  with mapping selector for multi-mapping exports, and a "New upload" reset.
- **Source analysis before migration**: detects the PowerCenter release from the
  repository version (8.1 → 10.5 map), repository/database/codepage/export-date facts,
  object counts (mappings, workflows, sessions, mapplets), and plain-language
  pre-migration warnings — workflow/session orchestration not converted, mapplets not
  expanded, unmapped step types (Stored Procedure, Custom, Transaction Control), SQL
  overrides needing dialect review, untranslated expressions, old-version cautions,
  workflow-only exports (previously a silent no-op). Shown on the Parse page, in the
  CLI `convert` output, and surfaced even when an export contains no mappings.
- **Color themes**: Midnight (default), Slate, Pentaho, Light — picker persisted in
  localStorage, applied before first paint.
- Upload page explains the product using the technical brief (opportunity, four-stage
  cards, phase roadmap); the brief PDF is served at `/brief` and linked in the masthead.
- Corpus grown to **50 verified real exports** (148 mappings, 1,316 steps) across six
  repository versions (PowerCenter ~9.0 → 10.5); gap analysis: 54% auto, three unmapped
  types remaining. Zero parser failures corpus-wide.

## [1.2.0] — 2026-07-17

### Added

- **Settings page** (⚙ in the masthead): environment detection (platform, RAM, NVIDIA
  GPU/VRAM via nvidia-smi, `OLLAMA_*` env vars, ANTHROPIC_API_KEY presence-only, live
  Ollama probe with installed-model list) and an automatic **model recommendation**
  sized to the hardware (qwen2.5-coder ladder: 1.5b → 32b) with suggested Ollama
  tuning (`OLLAMA_KEEP_ALIVE`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_FLASH_ATTENTION`).
  One-click "Apply recommendation"; pull the model from the UI with live progress.
- API: `GET/PUT /settings`, `POST/GET /settings/ollama/pull`. Settings persist to
  `config/settings.json` (gitignored).
- Expanded real corpus: 24 genuine export files across six repository versions
  (PowerCenter ~9.0 → 10.5), 118 mappings — sources include HHS payroll, a Russian
  production DWH, a Spanish SEPE export, and the viadee i2t converter fixtures.
- GitHub repository: <https://github.com/jporeilly/PDI-Migration-CoPilot> (private).

### Fixed

- `OLLAMA_HOST=0.0.0.0` (a listen address) is now mapped to a connectable loopback
  URL, and a missing port defaults to 11434.

## [1.1.0] — 2026-07-17

### Added

- **React review UI** (Vite + React 18, `frontend/`): dark theme, drag-and-drop upload,
  KPI stat tiles, SVG pipeline flow diagram (longest-path layering, confidence-colored
  nodes), filterable steps table, .ktr preview + download, "Try the sample" button.
  Built bundle served by FastAPI at `/`; replaces the vanilla static page.
- **Real-world corpus**: 11 genuine PowerCenter 10.x exports from the public
  HHS/Informatica GitHub repo in `samples/informatica/` — 110 real mappings, 1,045 steps.
  All parse cleanly (including a 522 KB mapping with 589 connectors).
- **Gap analysis**: `pdi-migrate gaps <dir>` batch-converts a corpus and reports mapper
  coverage — auto/review/manual rates and per-source-type gap list, unmapped types first.
  First run on the real corpus: 53% auto, 1 unmapped type.
- `GET /sample` endpoint; `ConversionResult` API model (pipeline + report + ktr).
- **Build tooling**: `Makefile` (Linux/macOS, or Windows with make) and mirrored helper
  scripts `scripts/dev.ps1` (Windows 11) / `scripts/dev.sh` (Linux) — setup, test, run,
  convert, gaps, ui-install/ui-build/ui-dev, status, clean.

### Fixed

- Rules library: real 10.x exports use transformation type `Sequence`, not
  `Sequence Generator` — both now map to PDI Sequence (found by gap analysis).

### Changed

- Per-step KTR config emission for Table Input (SQL), Table Output, Sort rows,
  Group By (keys + aggregates), and script placeholder steps (was skeleton-only).
- `INSTALL.md` moved to `docs/`.

## [1.0.0] — 2026-07-17

### Added

- Deterministic PowerCenter XML parser: mappings, transformations, fields, port expressions
  (passthrough ports skipped), and instance-level hops into a normalized Pydantic IR.
- Rules-library mapper (`rules/powercenter_to_pdi.yaml`): 16 transformation-type mappings,
  each with `auto` / `review` / `manual` confidence; unknown types routed to manual handoff,
  never guessed. Untranslated expressions downgrade `auto` steps to `review`.
- KTR generator: step types, hops, layout, and confidence/TODO annotations in step
  descriptions.
- Static migration report: auto/review/manual step counts and untranslated-expression count.
- CLI `pdi-migrate` with `parse` and `convert` commands.
- FastAPI layer with dark-themed review UI at `/`: drag-and-drop a PowerCenter export,
  inspect steps with confidence badges, download the generated .ktr. Swagger at `/docs`.
- Sample PowerCenter export (`samples/m_load_sales.xml`); 17 tests.

### Not yet implemented (stubs)

- LLM expression translation (Informatica expression language → PDI).
- Runtime diff harness (run old vs. new on sample data, diff outputs).
- Config emission for Merge Join, Stream Lookup, Insert/Update, Switch/Case.
- PowerCenter Workflow/Session (≈ PDI Job) conversion — out of Phase 0 scope.
