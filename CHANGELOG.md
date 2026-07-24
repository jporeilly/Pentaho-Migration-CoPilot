# Changelog

All notable changes to Migration Copilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning follows [SemVer](https://semver.org/).

**Versioning policy:** major architectural changes bump the minor version (x.Y.0);
minor feature changes and fixes bump the patch version (x.y.Z). Releases are batched
deliberately — not one per work session.

## [1.11.1] — 2026-07-24

**Reports family, part 2: the guided React flow.**

### Added

- **Crystal reports UI flow** with its own stepper — Upload → Inspect →
  Formulas → Download — reusing the existing visual language (tiles, badges,
  filters, workbench bar). Inspect shows bands, groups, parameters, summaries,
  and the data-source SQL with a provenance badge (from Crystal command vs
  generated — verify joins) plus the record-selection formula warning.
  Formulas is a filterable auto/review/manual table with translated OpenFormula
  and the original Crystal text preserved for manual ones. Download builds the
  .prpt client-side from the base64 response, offers the conversion report,
  and re-converts in place when the JNDI datasource name is changed.
- **Format auto-routing in the UI**: dropping a Crystal RptToXml dump on the
  ordinary upload zone detects the 422 "Reports pipeline" hint from
  `detect_parser` and reroutes the file to `/reports/convert` automatically;
  a "Try the Crystal sample" button sits beside the ETL sample.
- Crystal source badge (SAP gold lettermark), reports workbench bar with
  formula-status chip, masthead updated to "Informatica · Talend → PDI ·
  Crystal → PRD".
- Shared `Markdown` component now renders fenced code blocks, pipe tables,
  and horizontal rules (used by the inline conversion report).

### Changed

- `Stepper` accepts a custom step list (`REPORT_STEPS`) instead of hardcoding
  the ETL five; ETL behavior unchanged.

## [1.11.0] — 2026-07-24

**Reports family: SAP Crystal Reports → Pentaho Report Designer (backend).**

Migration Copilot now covers a second artifact family. Crystal reports are
documents (bands, elements, formulas), not dataflows, so they get their own
pipeline (`src/pdi_migration/reports/`) instead of the ETL IR — folded in from
the standalone CR-PRPT-Migration prototype.

### Added

- **Reports pipeline**: RptToXml dump (SAP .NET SDK) → intermediate ReportModel
  (twips→points, fork-tolerant attributes) → deterministic Crystal→OpenFormula
  translator (recursive descent; statuses auto/review/manual — variables,
  `WhilePrintingRecords`, loops, arrays, and inline aggregates are hard-blocked
  and preserved verbatim, never guessed) → native .prpt bundle writer
  (stored-mimetype ZIP, nested relational groups, page bands in styles.xml,
  parameters + ItemSum/Count/Avg/Max/Min functions + PageOfPagesFunction, JNDI
  SQL datasource; format reverse-engineered from the PRD CE sample reports) →
  markdown conversion report listing every item needing a human.
- **API**: `/reports/inspect`, `/reports/convert` (stateless; .prpt travels
  base64 in the JSON response), `/reports/sample`; wired into the existing
  app with the shared API-key dependency (extracted to `api/security.py`).
- **CLI**: `pdi-migrate report <dump> --out output/crystal --jndi <name>`.
- **Source detection**: `detect_parser` now recognizes RptToXml dumps and
  points ETL uploads of them at the Reports pipeline instead of failing as
  PowerCenter; `SourceTool.CRYSTAL` added.
- **Sample corpus seed**: `samples/crystal/branch_transactions.xml`
  (bank-themed simulated RptToXml dump).
- 22 tests (`tests/test_reports.py`): translator contract, parser, bundle
  shape, detection routing, full API flow.

### Not yet (tracked for the next releases)

- React UI flow for reports (source card + stepper pages).
- LLM translation of `manual` formulas via the existing hybrid pipeline
  (`CRYSTAL_PROMPT` targeting OpenFormula).
- Report-flavored confidence score and PDF report; project-store integration.
- Real-PRD round-trip validation of generated bundles.

## [1.10.0] — 2026-07-17

**Phase 2 begins: multi-source. Talend is the second supported source.**

### Added

- **Talend support end-to-end**: deterministic `.item` parser (typed schemas from
  `<metadata>` columns, FLOW/LOOKUP hops, tMap Java expressions extracted from mapper
  data with passthroughs skipped), `talend_to_pdi.yaml` rules library (v2: 60+
  components, extended from gap analysis on a real corpus), Talend-specific impact
  knowledge (tMap = three PDI concepts in one, sorted-input traps, context-variable
  scoping, connection/commit management), and a Java→JavaScript translation prompt
  selected automatically per expression language. Source auto-detection (content
  sniffing, not extensions) across upload, CLI, and the Project page; `batch`/`gaps`
  glob `.item` files too.
- **Real Talend corpus**: 40 verified jobs from public repos spanning Talend 5.1 →
  8.0.1 (production DWHs, Red Hat oVirt, health informatics, Salesforce REST syncs) —
  all parse with zero failures; 763 steps, 104 distinct components. Rules v2 measured:
  manual steps 207 → 42, avg confidence 53 → 62.
- **🤖 AI-suggested solutions per step**: every impact entry has a "Suggest a solution"
  button — the configured LLM receives the step's real configuration, fields,
  expressions, neighbors, and known behavioral differences, and proposes a concrete
  PDI approach (steps, config, code, pitfalls). Advisory markdown, clearly labeled,
  never auto-applied. `POST /suggest`.
- **Step click-through**: impact entries jump to their row in the steps table and
  table rows jump to (and expand) their impact entry, with a highlight flash.
- **Richer PDF report**: human review checklist with full notes, expressions appendix
  (source + translation state), complete high/medium impact detail, and a data-flow
  listing.

### Fixed

- Hardcoded "Informatica" labels in the comparison heading, Map intro, and stepper;
  uploads now keep their original filename (Talend job names derive from it — no more
  `tmpr5t45a84`).

## [1.9.0] — 2026-07-17

**Phase 0 roadmap complete.**

### Added

- **Workflow → Job conversion**: PowerCenter workflows parse into a Job IR
  (task instances, session→mapping resolution, link conditions) and emit .kjb files —
  sessions become Transformation entries wired to the sibling .ktr files via
  `${Internal.Entry.Current.Directory}`; unconvertible task types (Email, Command, …)
  become labeled placeholders, never silently dropped. Wired into `convert` and `batch`.
  Verified live: a generated .kjb loaded and began executing under Kitchen (PDI 11.0).
- **Remaining step-type configs**: Merge Join (join type + key pairs parsed from the
  Informatica join condition, inputs from hops), Stream Lookup (keys/values from the
  lookup condition, plus an auto-injected Table Input feeding the lookup data),
  Insert/Update (target table from downstream, field values; key columns an explicit
  TODO), and Call DB Procedure — `Stored Procedure` now maps (rules v3), clearing the
  corpus's largest unmapped type.
- **PDI runner**: `pdi-migrate run <file.ktr|.kjb>` executes generated artifacts via
  Pan/Kitchen in a locally detected PDI install (PDI_HOME or common paths), with
  documented exit-code meanings and a log-aware verdict (Windows .bat wrappers can
  swallow Java's exit code — the log is trusted over a false zero).
- **PDF migration report**: branded, per-mapping (score hero with factor bars, source
  facts and warnings, step table with color-coded confidence, impact highlights) —
  `POST /report/pdf` and a "⬇ Report (.pdf)" button on the Validate page.

### Fixed

- "Translation failed: Failed to fetch" on long translations: the ✨ Translate button
  now starts a background job and polls progress (`/translate/start` +
  `/translate/status`), showing "Translating 7/20…" — a browser fetch can no longer
  outlive its timeout while the LLM works. The synchronous `POST /translate` remains
  for scripting small mappings.
- Squashed score-factor layout on the Validate page: two-column grid, detail text on
  its own line, larger bars.

## [1.8.1] — 2026-07-17

### Fixed

- Project table overlap: score chips no longer wrap, timestamps render compactly,
  long mapping/file names ellipsize, and the table scrolls horizontally in its own
  container instead of crowding the card edge.
- Project page has a "← Back to workflow" button (matching Settings).

### Added

- Project rows are clickable: opening a mapping re-runs its conversion from the
  stored source export and drops you into the full stepper workflow (Parse → Map →
  Generate → Validate) with all reports. `GET /project/open`; the store now keeps
  each mapping's source path (auto-migrated).
- `pdi-migrate batch --translate`: run a whole corpus through the configured LLM.
- Swagger /docs shows a "← Back to Migration Copilot" link; the masthead API-docs
  link opens in a new tab.
- Multi-GPU detection: all NVIDIA cards are counted and VRAM aggregates (Ollama
  layer-splits across cards); with 2× RTX 3060 (24 GB) the recommendation steps up
  to qwen2.5-coder:32b with `OLLAMA_SCHED_SPREAD=1`, noting 14b as the faster
  single-card alternative.
- README and INSTALL updated: sandbox kits, project store, diff harness, multi-GPU
  detection, Docker, and hardening are documented.
- Comparison view stacks vertically (source above, converted below) so wide
  pipelines get the full width instead of two cramped panes.

## [1.8.0] — 2026-07-17

### Added

- **Diff harness (measured parity)**: compare the original pipeline's CSV output with
  the converted pipeline's output — numeric-tolerant, key-matched or positional, with
  per-column mismatch counts and row samples. `POST /diff` and an "Output parity
  check" section on the Validate page with PASS / NEAR / FAIL verdicts. The measured
  counterpart to the static confidence score.
- **Project mode**: `pdi-migrate batch <dir>` converts a whole corpus (one output
  subfolder per export file — no more mapping-name collisions), scores every mapping,
  and records it in a SQLite project store; `pdi-migrate project` and the new
  **📁 Project** page show the portfolio with per-mapping review status
  (converted → in review → verified / failed) editable in the UI. First run over the
  real corpus: 148 mappings, avg confidence 64/100.
- **Hardening**: optional API-key auth on all mutating endpoints (set
  `PDI_MIGRATION_API_KEY`), 50 MB upload limit (413), structured request logging.
- **CI**: GitHub Actions — pytest (Python 3.13) and frontend build (Node 20) on every
  push and PR.
- **Docker packaging**: multi-stage `Dockerfile` (UI build → slim Python runtime);
  `docker run -p 8321:8321 migration-copilot` serves API + UI.
- **Rules governance**: `rules/powercenter_to_pdi.yaml` now carries `_meta`
  (version, updated, provenance history); `/health` reports the rules version.
- Favicon; real vendor logos supported via `frontend/public/logos/` (internal tool)
  with lettermark fallback.

### Changed

- Layout breathing room: the stepper is its own band with larger targets; masthead,
  sections, and cards get clear vertical rhythm (user feedback).
- Masthead trimmed to API docs · Project · Settings; the technical-brief link lives in
  the Upload intro and Best practices moved to the Upload page and the Validate
  review checklist.

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
