# Changelog

All notable changes to Migration Copilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning follows [SemVer](https://semver.org/).

**Versioning policy:** major architectural changes bump the minor version (x.Y.0);
minor feature changes and fixes bump the patch version (x.y.Z). Releases are batched
deliberately — not one per work session.

## [1.16.0] — 2026-07-24

**Charts migrate.**

### Added

- **Fork walks the Crystal chart model** (RAS `ChartObject.ChartDefinition` /
  `ChartStyle`): emits `<ChartDefinition StyleType ChartType Title>` with
  `ConditionFields` (categories) and `DataFields` (values). Verified on a
  real corpus report: bar chart, title, category and value fields extracted.
- **Converter renders PRD legacy charts**: bar/line/area via
  `CategorySetDataCollector`, pie/doughnut via `PieDataSetCollector`, each
  with the matching JFreeChart expression (title, legend). Chart columns
  resolve through the same field-reference logic as elements; unsupported
  styles (Gantt, gauge, …) stay honest TODO placeholders. Every migrated
  chart carries a note that aggregation semantics should be verified.
- **Live-verified**: ladder rung 2 gained a bar chart ("Deposit balances by
  branch") that renders real CSCU data through the real engine — title,
  legend, six branches, correct values. The Jakub-Syrek corpus report's
  chart now migrates instead of a TODO placeholder.
- 2 tests (179 total).

## [1.15.0] — 2026-07-24

**The forked extractor ships — plus working prompts and Crystal-faithful layout.**

### Added

- **RptToXml fork built and shipped** (`tools/RptToXml-fork/` + `build.ps1`,
  compiled with Roslyn csc straight against the machine .NET Framework — no
  SDK/targeting packs needed). Adds what stock 1.1.7 never exported:
  **per-field `<FieldFormat>` with raw Crystal properties and a computed
  PRD-ready `FormatString`** (`#,##0.00;-#,##0.00`, `MM/dd/yy`, …) and
  best-effort credential redaction at extraction (`RPTTOXML_REDACT=1`;
  `report-scrub` remains the backstop). `extract-rpt.ps1` and `report-env`
  prefer the fork automatically. Corpus re-extracted with it: 150/150 parse,
  real format strings verified flowing into .prpt layouts end-to-end
  (formula fields resolve via their declared result type).
- **Parameter prompts now work**: simple record-selection formulas
  (conjunctions of comparisons against parameters/literals) are folded
  deterministically into the SQL WHERE (`br_name = ${Branch}`), so changing
  the prompt in PRD re-filters the report. Complex selections stay honest
  manual items. Verified live: the flagship renders only the prompted branch.
- 2 tests (fork format resolution incl. formula types; live-verified fold).

### Fixed

- **Column headers now render below the masthead** (Crystal page-1 order):
  Crystal's PageHeader becomes a PRD **repeating details-header** — below the
  report header on page 1, repeated on continuation pages — instead of the
  physical page-header band that always tops the page.
- Effort recalibrated to field reality (user-calibrated): the flagship-class
  report now estimates **~0.5h with Copilot vs ~2h manual**; corpus portfolio
  ~119h vs ~323h (63% saved).

## [1.14.3] — 2026-07-24

**Context-aware upload tiles + the extractor-readiness hook.**

### Added

- **Upload stage tiles now reflect the loaded file** (no toggle): generic
  when nothing is loaded, Reports (Inspect/Formulas/Convert/Download) or ETL
  (Parse/Map/Generate/Validate) once a file of that family is selected —
  driven by state, matching the content-aware stepper and masthead.
- **Field format-string hook**: an explicit per-field PRD format
  (`<FieldFormat FormatString=".."/>` or `<NumericFieldFormat/DateFieldFormat
  FormatString=".."/>`) is read into `Element.format_string` and used over the
  type-based default — the converter-side readiness for a richer extractor.
- **`docs/RPTTOXML-EXTRACTOR.md`**: analysis of what stock RptToXml 1.1.7 does
  not export (per-field formats, image bytes, group sort), three options with
  a recommended focused fork, the exact `RptDefinitionWriter.cs` emissions,
  and confirmation the converter already reads all of them.

## [1.14.2] — 2026-07-24

**More context-awareness + reports module refactor.**

### Added

- **Upload-page family toggle**: an ETL ↔ Reports switch previews either
  pipeline's stages with family-specific descriptions before anything is
  loaded — the landing page now teaches both flows.
- **Context-aware masthead**: the engine line shows all families when idle,
  and narrows to just the loaded one (`Crystal → PRD` / `Informatica · Talend
  → PDI`) once a file is converted — matching the content-aware stepper.

### Changed

- **Reports module refactored** ahead of the extractor work: `rpt_parser.py`
  507→398 + new `rpt_xml.py` (attribute/colour/border/font readers);
  `prpt_writer.py` 491→349 + new `prpt_render.py` (element/style rendering).
  Public API unchanged, 177 tests green.

## [1.14.1] — 2026-07-24

**Parameter and object fidelity — the achievable half of format fidelity.**

### Added

- **Rich parameters**: Crystal multi-value / pick-list (LOV) parameters now
  become PRD **list-parameters** (checkbox for multi-select, dropdown for
  single) with the static value list carried across; optional Crystal prompts
  map to `mandatory=false`. Simple prompts stay plain textboxes.
- **Object-level suppression and can-grow**: a Crystal object's `ObjectFormat`
  `EnableSuppress` -> PRD `visible=false`, `EnableCanGrow` -> `dynamic-height`
  (memo/text fields expand). Read from the real RptToXml `<ObjectFormat>`.
- 2 tests (177 total).

### Known limitation (motivates the extractor work)

- **Per-field number/date/currency format strings** (decimal places, currency
  symbol, date pattern) and **group sort direction** are *not* exported by
  RptToXml 1.1.7 — the Crystal SDK has them, the dumper does not. The writer
  uses sensible type-based defaults; true format fidelity needs a more
  complete extractor (next).

## [1.14.0] — 2026-07-24

**Professional report formatting — carried from the Crystal source, not injected.**

### Added

- **Rich formatting is now migrated**, and it is genuinely *read from the
  Crystal report*: the parser reads RptToXml's real representation — nested
  `<Color>` / `<BackgroundColor>` / `<BorderColor>` (ARGB) elements, `<Border>`
  line styles, `SectionFormat` band backgrounds, vertical alignment, and a
  base64 `<ImageData>` logo. The model carries `bg_color`, `border`, `valign`,
  and embedded image bytes; the writer emits PRD element/band backgrounds,
  borders, filled boxes, and **bundles the logo as a real `resources/*.png`**
  with the correct manifest media type.
- **The CSCU ladder and the flagship UI sample are now polished, professional
  reports**: navy masthead with an embedded CSCU logo, white title + gold
  subtitle, dark column-header row, shaded group bands, gold total rules,
  right-aligned currency, and a confidential footer — verified rendering live
  against CSCU through the real Pentaho engine (screenshots reviewed). The
  `build_ladder.py` generator applies a shared theme using only real RptToXml
  formatting elements, so the polish survives a genuine round-trip.
- Formatting-carry regression test (colours, band background, embedded logo →
  bundled .prpt). 175 tests.

### Notes

- **LLM corpus assist measured**: running the local qwen2.5-coder:32b over the
  150-report corpus flipped **61 of 152 manual formulas to review (40%)** —
  the assisted-coverage headline for Crystal formula translation.

## [1.13.1] — 2026-07-24

**CSCU end-to-end ladder + recalibrated effort estimates.**

### Added

- **`samples/crystal/ladder/`: six authored CSCU reports of increasing
  complexity** (member roster → accounts-by-branch → transaction register →
  member statement → loan portfolio → suspicious-activity), all backed by the
  live `cscu_core` schema. Unlike the GitHub corpus, these **convert AND
  render end-to-end against the real database** — the golden-path regression
  and demo set. Reproducible via `build_ladder.py`; rungs 4-6 deliberately
  exercise the honest-flagging path (running total → manual, StdDev + no PRD
  function, subreport/image/cross-tab → TODO placeholders).
- **`test_crystal_ladder.py`**: converts every rung to a valid bundle,
  asserts each introduces new complexity and that hard cases are flagged not
  dropped; opt-in live render (`CSCU_LIVE=1`). **All six verified rendering
  live CSCU data** through the real Pentaho engine (member names, grouping,
  totals, formulas — proven, not asserted-in-a-vacuum).
- Fixed the UI sample's SQL to the real cscu_core schema (transactions link
  to member/branch only through `accounts`); JNDI `CSCU`.

### Changed

- **Effort estimates recalibrated to real consulting numbers.** Per-artifact
  costs were too high: a moderate report now estimates ~0.5-1h with Copilot
  vs ~3-4h manual (was ~2h/6.5h), a simple roster ~0.5h/1.5h, a complex loan
  report ~1.5h/5.5h. Base/overhead constants lowered on both families
  (reports and ETL); sub-linear volume scaling retained.

## [1.13.0] — 2026-07-24

**Reports join the portfolio; previews land; the UI explains itself.**

### Added

- **Reports in the project store**: `reports` table (auto-created),
  `pentaho-migrate report-batch` converts a corpus and records every report
  (formula counts, TODOs, effort hours, review status), `/project/reports` +
  `/project/report-status` API, and a Crystal reports table on the Project
  page with per-report status tracking. **The portfolio effort banner now
  sums both families** — with the real corpora loaded: 148 mappings + 150
  reports ≈ 8,300h manual vs ~4,240h with Copilot, ~49% saved.
- **Layout wireframe preview** (Inspect page): every band with its elements
  at their true positions/sizes (points from the .rpt) as an SVG — the same
  geometry the .prpt receives, so one wireframe previews source and target.
  Kind-colored, hover for element names, suppressed bands hidden. Backed by
  element geometry now included in `ReportSummary.sections[].items`.
- **Engine PDF preview** (Download page + `/reports/preview`): the .prpt
  rendered through the real Pentaho Reporting engine with an empty dataset
  (tools/PrptRenderer.java) — page setup, bands, and labels exactly as PRD
  shows them, no database needed. 503 with a hint when no local PRD exists.
- **Expandable "What am I looking at?" explanations** on every reports card
  (structure, datasource, parameters, summaries, formulas, download) and the
  Project page — collapsed by default, plain-language when opened.
- Upload-page stage cards and phase strip updated to cover both artifact
  families (Phase 2 marked current: Talend + Crystal shipped).
- 5 new tests (166 total).

### Fixed

- Numeric table headers now right-align with their values (`th.num` had no
  alignment rule while `td.num` was right-aligned).

## [1.12.1] — 2026-07-24

**Crystal correctness fixes — closing the production-review findings.**

### Fixed

- **Silent summary drop (worst finding)**: unmapped summary operations
  (StdDev, Median, …) used to be skipped silently while layout elements still
  referenced the missing function — a broken bundle with no flag. Now: the
  operation map lives in `model.py`, the parser flags unsupported operations
  as issues at load time, referencing elements render as TODO placeholders,
  and a test proves the bundle stays consistent.
- **Suppressed sections were being rendered**: real RptToXml puts suppression
  in `SectionFormat@EnableSuppress`, which the parser never read — 201
  suppressed section formats in the corpus were silently included. Both the
  real location and the legacy `Suppress` attribute are honored now.
- **Conditional-formatting formulas surfaced**: font-color / border / section
  condition formulas (dumped in `*ConditionFormulas` elements — dozens across
  the corpus) were dropped invisibly. Each is now a note on the element or a
  model issue, flowing into the conversion report and the effort estimate —
  which is why corpus effort honestly rose (~1,610h saved, 44%, ~$241k).
- **String `+` is now type-aware**: `{A.FIRST} + {A.LAST}` on string-typed
  database fields becomes `&` (OpenFormula `+` fails on strings at runtime);
  the translator now receives the parsed field-type map.
- **Real-world page margins**: RptToXml's `<PageMargins>` child element is
  parsed (previously only attribute-style margins, so real dumps fell back to
  defaults).
- **`%` no longer mistranslates**: Crystal has no binary `%`, and OpenFormula's
  `%` is postfix percent — the token now routes to manual instead of silently
  changing semantics.
- **Background job registries are bounded** (assist + translate jobs; oldest
  finished entries evicted past 50).
- 4 new tests incl. a real-corpus assertion battery (suppression counts,
  margins parsed, conditional formulas surfaced). 161 total. Real-corpus
  report round-tripped through the engine post-fix.

## [1.12.0] — 2026-07-24

**Project renamed: PDI-Migration → Pentaho-Migration.**

The scope now spans ETL *and* BI reports, not just PDI.

### Changed

- **GitHub repository**: `jporeilly/Pentaho-Migration-CoPilot` (old URLs
  redirect); local folder `C:\Projects\Pentaho-Migration`.
- **Python package**: the old `pdi`-prefixed module → `pentaho_migration`; distribution
  `pentaho-migration` (66-file sweep, guard test keeps it that way).
- **CLI**: `pentaho-migrate`, with `pdi-migrate` kept as a working legacy
  alias — existing muscle memory and scripts keep working.
- **Env vars**: `PENTAHO_MIGRATION_API_KEY` / `PENTAHO_MIGRATION_CONFIG_DIR`;
  the old `PDI_MIGRATION_*` names are honored as fallbacks.
- **Branding**: README masthead, UI masthead, FastAPI title, and CLI help now
  read "Pentaho Migration Copilot" and present both artifact families.
- Unchanged on purpose: `config/` (project store + settings), corpora,
  the `crystal-deps-v1` release (follows the repo), report/PDF outputs.

## [1.11.7] — 2026-07-24

**Real corpus extracted and measured: 150/150 parse, formula coverage 33% → 79%.**

### Added

- **Corpus extracted**: all 150 harvested .rpt files converted to RptToXml
  dumps (`samples/crystal/real/`, 9.2 MB) with **zero extraction failures and
  zero parse failures** — the fork-tolerant parser survived first contact with
  genuine multi-source dumps unchanged. Committed with a corpus regression
  test (every dump must parse; skips where the corpus is absent).
- **Credential scrubbing** (`reports/sanitize.py`, `pentaho-migrate report-scrub`):
  RptToXml copies connection credentials out of .rpt files — the real corpus
  carried **440 credential attributes across 142 of 150 dumps**, all blanked.
  A second regression test asserts the committed corpus stays clean; the
  extract script and docs now point at scrub before share.
- **Translator upgrades driven by corpus frequency analysis**: `Switch()` →
  nested `IF(...;NA())` — one function accounted for 282 of 375 manual
  formulas; `DateDiff("d"/"m"/"yyyy", a, b)` → `DATEDIF`; `Chr`/`ChrW` →
  `CHAR`, `Asc` → `CODE`. Corpus formula coverage moved from 33% auto+review
  to **79%** (manual 375 → 152). Corpus portfolio: ~1,615h with Copilot vs
  ~3,068h manual — saves ~1,454h (47%, ~$218k at $150/h).
- **`scripts/setup-crystal-env.ps1`**: one-command internal setup — pulls the
  SAP runtime MSIs + RptToXml from the repo's private `crystal-deps-v1`
  release (documented license caveat), installs, verifies with `report-env`.
  `tools/RptToXml/` is now gitignored (binaries come from the release).
- **Docs**: full Crystal workflow (runtime install with registration link,
  RptToXml placement, report-env → extract → scrub → gaps → convert
  --validate) added to README, docs/INSTALL.md, and a new reports section in
  docs/BEST_PRACTICES.md.
- 7 new tests (156 total).

## [1.11.6] — 2026-07-24

**Real Crystal corpus + extraction kit.**

### Added

- **`samples/crystal-rpt/`: 150 genuine .rpt binaries from 48 public GitHub
  repositories** (42 MB) — harvested by repository-tree walking (GitHub code
  search cannot see binaries), each verified against the OLE2 magic, deduped
  by content hash, capped at 8 per repo for diversity, with a full provenance
  manifest (repo, path, size, hash). The Crystal counterpart of the
  Informatica/Talend corpora; the 150-file cap was reached, more remain.
- **`scripts/extract-rpt.ps1`**: batch .rpt → RptToXml XML extraction (finds
  RptToXml via RPTTOXML_PATH or tools/RptToXml/, reports per-file failures,
  points at `report-gaps` next). Runs once the free SAP Crystal .NET runtime
  is installed — see `pentaho-migrate report-env` for the preflight.
- **`pentaho-migrate report-gaps [dir]`**: Crystal corpus analyzer — parse
  coverage, formula auto/review/manual rates, TODO placeholders, and
  portfolio effort, mirroring the ETL `gaps` command. The zero-parse-failure
  bar the ETL corpora set now applies to Crystal the moment extraction runs.

## [1.11.5] — 2026-07-24

**Reports round-trip validation — "opens in PRD" is now a measured fact.**

### Added

- **`tools/PrptValidator.java`**: headless loader that parses a .prpt through
  the REAL Pentaho Reporting engine (the exact code path PRD and the Pentaho
  Server use), run via the JDK single-file source launcher — no compile step.
  **The generated sample bundle passed on the first run** (query, group,
  parameter, and data factory all materialize), and a deliberately corrupted
  bundle is correctly rejected — the reverse-engineered bundle format is now
  engine-verified, not sample-inferred.
- **`reports/prpt_validator.py`**: Python wrapper (finds PRD + Java, parses
  OK/FAIL verdicts); `pentaho-migrate report --validate` validates right after
  conversion.
- **`reports/environment.py` + `pentaho-migrate report-env`**: fresh-install
  preflight for the whole Crystal pipeline — Pentaho Report Designer (PRD_HOME
  or common paths), Java (suite-bundled JDK preferred), SAP Crystal .NET
  runtime (registry keys the MSI writes + GAC fallback), and RptToXml.exe
  (RPTTOXML_PATH / tools/RptToXml/ / PATH) — with actionable hints including
  the official free runtime download page.
- 4 new tests (149 total): engine round-trip of a generated bundle,
  corrupted-bundle rejection (both auto-skip without a local PRD), and
  environment-detection shape/tolerance.

## [1.11.4] — 2026-07-24

**Portfolio effort totals — the engagement-level number.**

### Added

- **`effort_from_counts()`** (refactored out of `build_effort`): estimates from
  stored counts alone, so pre-existing project databases need no migration.
  When the true expression total is unknown it is approximated by the
  untranslated count — conservative on both scenarios, and said so in the
  assumptions.
- **`/project` rows** now carry `copilot_hours` / `manual_hours` /
  `saved_hours` per mapping (computed at read time).
- **Project page**: portfolio effort & cost banner (sum across the corpus,
  same editable persisted rate) plus a per-mapping "Saved" column. Measured
  on the real 148-mapping corpus: ~2,150h with Copilot vs ~4,610h manual
  rebuild — **saves ~2,460h (53%), ~$369k at $150/h**.
- **PDF report** gains an "Estimated effort & cost" section (hours, cost at
  the UI-chosen rate, full assumptions); the Validate page passes the
  persisted rate with the request.
- **CLI `project`** prints the portfolio effort line.
- 3 new tests (145 total): counts-approximation conservatism, /project effort
  surface, PDF with/without effort.

## [1.11.3] — 2026-07-24

**Effort & cost estimation — the presales number.**

Every conversion now answers "what does this migration cost?": estimated hours
of remaining human work with Copilot vs a from-scratch manual rebuild, priced
at a configurable consultant rate.

### Added

- **`validator/effort.py`** (ETL) and **`reports/effort.py`** (Crystal):
  transparent static heuristics — per-step/per-formula constants for both the
  with-Copilot and rebuild scenarios plus testing overhead, every constant
  surfaced in an `assumptions` list so the numbers can be defended or adjusted
  in front of a customer. Hours are the server product; money is hours x rate,
  applied client-side. `EffortEstimate` rides on every `ConversionResult`
  (ETL) and `ReportSummary` (reports), so `/convert`, `/project/open`,
  `/reports/convert`, and the assist job all carry it.
- **UI `EffortPanel`** on the ETL Validate page (under the confidence score)
  and the reports Download page: with-Copilot / manual-rebuild / saved columns
  in hours and currency, an editable rate field (default $150/h, shown with
  the 8-hour day equivalent, persisted in localStorage — typical blended
  consultant rates $125–$175/h ≈ $1,000–$1,400/day), and a "How is this
  calculated?" assumptions expander.
- **CLI**: `convert` and `report` print the effort line
  (`~3.5h with Copilot vs ~12h manual rebuild — saves 8.5h (71%, ~$1,275 at $150/h)`);
  `--rate` overrides the rate.
- 6 new tests (142 total): heuristic sanity, scaling with manual work, effort
  drop after formula assist (rebuild cost unchanged), API surface for both
  families.

### Not yet

- Portfolio-level totals on the Project page and effort in the PDF report —
  the "entire corpus saves $X" number — next.

## [1.11.2] — 2026-07-24

**Reports family, part 3: LLM assist for manual formulas.**

The same hybrid contract as ETL expression translation, now for Crystal: the
LLM only sees formulas the deterministic translator could not prove, every
LLM output is flagged `review` for mandatory human verification, and failures
never block.

### Added

- **`CRYSTAL_PROMPT`**: Crystal formula syntax → Pentaho OpenFormula, with an
  authoritative cheat sheet (field refs, `;` argument separators, IF nesting,
  AND()/OR(), function mappings) and explicit no-fake rules: running-total
  variables and aggregates must return an empty translation plus the correct
  PRD rebuild advice (ItemSumFunction et al.); local single-formula aliases
  may be inlined at `medium` confidence.
- **`reports/llm_assist.py`** — `translate_manual_formulas()`: manual → review
  on success (translation prefixed `=`, "AI-translated — verify" note);
  untranslatable formulas keep `manual` but gain the LLM's rebuild advice in
  their notes and the conversion report.
- **API**: `/reports/translate/start` (multipart dump + jndi; background
  thread, progress polling via `/reports/translate/status`) returning a full
  conversion response with assisted formulas baked into the regenerated .prpt.
- **CLI**: `pentaho-migrate report --translate/-t`.
- **UI**: ✨ AI-assist button on the reports Formulas page with n/total
  progress polling (same pattern as the ETL Map page); sample fetches are now
  `cache: no-store`. Formulas step hint updated to "rules + AI".
- Sample gains `{@TxnRiskBand}` (Select Case) so the demo shows both assist
  outcomes. **Verified live against qwen2.5-coder:32b**: Select Case →
  perfect nested `IF([TXN_TYPE] = "WIRE"; …)` flagged review; the shared-variable
  running total correctly stayed manual with ItemSumFunction advice.
- 6 new tests (136 total): mocked-LLM unit flow, advice-only path, provider
  gating, background-job API round-trip.

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
pipeline (`src/pentaho_migration/reports/`) instead of the ETL IR — folded in from
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
- **CLI**: `pentaho-migrate report <dump> --out output/crystal --jndi <name>`.
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
- **PDI runner**: `pentaho-migrate run <file.ktr|.kjb>` executes generated artifacts via
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
- `pentaho-migrate batch --translate`: run a whole corpus through the configured LLM.
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
- **Project mode**: `pentaho-migrate batch <dir>` converts a whole corpus (one output
  subfolder per export file — no more mapping-name collisions), scores every mapping,
  and records it in a SQLite project store; `pentaho-migrate project` and the new
  **📁 Project** page show the portfolio with per-mapping review status
  (converted → in review → verified / failed) editable in the UI. First run over the
  real corpus: 148 mappings, avg confidence 64/100.
- **Hardening**: optional API-key auth on all mutating endpoints (set
  `PENTAHO_MIGRATION_API_KEY`), 50 MB upload limit (413), structured request logging.
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
  Available as `pentaho-migrate sandbox <export.xml>` (writes to
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
- `POST /translate` API; `pentaho-migrate convert --translate` CLI flag; **✨ Translate**
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
- GitHub repository: <https://github.com/jporeilly/Pentaho-Migration-CoPilot> (private).

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
- **Gap analysis**: `pentaho-migrate gaps <dir>` batch-converts a corpus and reports mapper
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
- CLI `pentaho-migrate` with `parse` and `convert` commands.
- FastAPI layer with dark-themed review UI at `/`: drag-and-drop a PowerCenter export,
  inspect steps with confidence badges, download the generated .ktr. Swagger at `/docs`.
- Sample PowerCenter export (`samples/m_load_sales.xml`); 17 tests.

### Not yet implemented (stubs)

- LLM expression translation (Informatica expression language → PDI).
- Runtime diff harness (run old vs. new on sample data, diff outputs).
- Config emission for Merge Join, Stream Lookup, Insert/Update, Switch/Case.
- PowerCenter Workflow/Session (≈ PDI Job) conversion — out of Phase 0 scope.
