# Changelog

All notable changes to Migration Copilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning follows [SemVer](https://semver.org/).

**Versioning policy:** major architectural changes bump the minor version (x.Y.0);
minor feature changes and fixes bump the patch version (x.y.Z). Releases are batched
deliberately — not one per work session.

## [1.38.0] — 2026-07-28

### Changed

- **Every Crystal section is now a collapsing PRD sub-band** (nested `<band>`
  elements, block-stacked inside each report band). A conditionally
  suppressed section takes NO height when hidden — Crystal's three
  mutually-exclusive letter variants render as one letter, not one letter
  and two blanks. This replaces the push-down-of-conditions-to-elements
  approach, which hid the ink but kept the space.
- **Crystal "Underlay Following Sections" is reproduced**: the underlay
  section's elements paint BEHIND the following section (placed by best
  span-overlap; geometry-sharing conditional variants each get a copy), and
  the underlay's own height disappears — a watermark sits behind the letter
  instead of pushing it half a page down.
- **Group footers un-swapped.** Crystal nests bands, so footer areas arrive
  innermost-first; assigning them in encounter order handed the per-customer
  "Total + Remit + new page" footer to the outermost group (it rendered once
  per COUNTRY). Reversed when the full footer set is present.
- **EnableNewPageAfter → `pagebreak-after`** on the section's sub-band, and
  **"Suppress Blank Section"** is honored: empty spacer sections drop, and
  data-bound ones get a provable `NOT(ISBLANK(...))` visibility so a blank
  ADDRESS2 line collapses like Crystal.
- **Currency formats survive**: Crystal often stores number formats as parts
  (DecimalPlaces + CurrencySymbol) with no FormatString — now assembled
  (symbol-bearing only, so invoice ids don't grow ".00"), applied to detail
  fields and INSIDE message prose ("The total amount due is $ 43.50").
- Statement demo now renders each customer's address, letter, watermark and
  invoice table on ONE page like the original (68 pages vs 74; the customer
  footer still slips on tight pages — known).
- UI: JNDI field stays inside its card (action rows wrap), the page reserves
  its scrollbar gutter, and the PDF preview modal shows engine-rendered page
  images with the embedded data.

## [1.37.0] — 2026-07-28

### Changed

- **🔍 PDF preview shows the report pages as images in a popup, with the
  embedded data.** It rendered into a new browser tab (dead under popup
  blockers and in embedded panes), with an empty dataset even when the bundle
  carried rows, and then — as an inline PDF — with a second scrollbar fighting
  the page and a black void where browsers lack a PDF plugin. Now: the engine
  renders live when saved rows are embedded, the pages come back as PNG
  images (pypdfium2, in the [api] extra), and the modal has one scrollbar.
  Falls back to the browser's PDF display if the rasterizer is absent.
- **🔍 Open in Report Designer** button on the Download step: converts and
  launches the result straight into the local PRD — the demo's closing beat,
  one click instead of download-then-file-open. Same bounds as the Crystal
  viewer launcher: local callers only, fixed executable, bundle written only
  into `output/prd-open/`.
- The Crystal viewer window now opens **in the foreground** (TopMost flash on
  show) — launched from the web server it used to appear behind the browser.
- View-style buttons use 🔍 consistently.
- **docs/DEMO-WALKTHROUGH.md** — the scripted 10-minute end-to-end demo, every
  step verified live before it was written.

- **Light is the default color theme.** First paint is light too (the bare
  CSS `:root` now carries the light palette, so there is no dark flash before
  the theme script runs). A previously saved theme choice still wins — anyone
  who picked Midnight keeps Midnight; the picker in ⚙ Settings is unchanged,
  with Light listed first.

### Added

- **The converted .prpt opens in Report Designer showing REAL DATA, with no
  database anywhere.** A report saved with its data carries the cached rowset
  inside the .rpt; it is now recovered and embedded as a PRD inline-table
  dataset answering the report query, with the report SQL riding along as the
  `source-sql` query — going live is picking a query, not rebuilding a
  datasource. Applies to raw `.rpt` drops, to dump uploads whose original is
  known (the Try button included), and to the CLI when the `.rpt` sits beside
  the dump. Verified live: the demo statement renders 83 pages of real
  customers through the engine with no datasource configured. Rows cap at
  5,000 (a demo dataset, not a warehouse) with a note.
- The stored cell encodings were calibrated against independently known
  values (the SAP viewer render, AdventureWorks/Xtreme data, a MilkoScan
  report whose milk-fat percentages are physical reality): Number/Currency
  doubles hold the value **x100**; Date is a midnight-based Julian Day
  Number; DateTime packs the JDN in the low 32 bits and seconds-since-
  midnight in the high; the engine's date-family bean converters parse
  exactly `yyyy-MM-dd'T'HH:mm:ss.SSSZ`. All pinned by tests.
- The "View original .rpt" button now works for drag-and-dropped binaries
  too — uploads are kept in `output/uploaded-rpt/` inside the viewer's
  allowed roots.

### Fixed

- **rpt-rs fork: the fixed-width saved-data reader typed every cell as i32**,
  so a memo-less unpacked report (AdventureWorks: one DateTime + one Currency
  column) decoded to garbage integers — the low half of every double. The
  reader now decodes each inline field per its declared type, sharing the
  packed reader's cell codecs. Column types also fall back to the bare field
  name when the saved catalog qualifies fields with a table the report does
  not use (`Customer.Country` vs a `Customer_Query` table) — that was every
  column of World Sales arriving as `Int32s`.

## [1.36.1] — 2026-07-27

### Added

- **Drag & drop the `.rpt` itself.** The Crystal flow started from an
  RptToXml dump, but a customer's file is the binary — asking them to run a
  command-line extractor first is a step that loses people. Uploads are now
  routed by CONTENT (the OLE compound-file magic, never the extension): an
  `.rpt` is extracted server-side with the same chain the corpus scripts use
  (RptToXml fork → credential scrub → cross-tab recovery) and then continues
  through the normal pipeline. Works on convert, inspect and PDF preview
  alike. Needs the extraction environment (`pentaho-migrate report-env`);
  without it the upload fails with one actionable sentence.

### Fixed

- **Crystal's PageHeader now renders — it maps to PRD's physical page-header
  band.** It was being emitted into a repeating details-header, which lives
  inside the innermost group: a letterhead rendered above each detail block
  or, on grouped reports, not visibly at all — while the page FOOTER (already
  on the physical band) worked. The one known difference is called out as a
  conversion note: on page 1 PRD prints the page header above the report
  header, where Crystal prints it below; every other page is identical.
- **Special fields embedded bare in text objects are interpolated.** RptToXml
  flattens `"Page " + {PageNumber}` to the literal text "Page PageNumber",
  which the braced-marker scan never saw — it printed verbatim at the
  customer. Bare `PageNumber`/`TotalPageCount`/`PrintDate` (and friends) now
  become `$(PageofPages)` / `$(report.date, ...)` message interpolations,
  whole-word matched, with the page function emitted whenever a template
  references it. The demo report's footer reads "Page 1 / 3" instead of
  "Page PageNumber".

## [1.36.0] — 2026-07-27

### Fixed

- **The conditional-EnableSuppress gap — 93 dropped conditions down to 39.**
  The largest fidelity gap in the corpus, closed from three directions:
  - **Sections merging into one band (52 cases).** Crystal allows several
    sections per band area with per-section suppression; PRD has one band, so
    the condition had nowhere to live and was dropped. It now moves onto the
    section's own elements — same condition, same rows, evaluated per element.
    The one visible difference (Crystal collapses the suppressed section's
    height; PRD keeps the band height and shows blank space) stays called out.
  - **Aggregates inside conditions ("suppress unless Sum(...) > 0").**
    OpenFormula has no windowed Sum, but the writer emits every summary as a
    PRD report function — so the aggregate is synthesized as one and the
    condition references it by name. The same synthesis now also resolves
    inline aggregates in text-object prose, which closes the demo report's
    last TODO: it converts with **zero manual items**.
  - **Translator false positives.** A '[' inside a parameter NAME
    ("{?$[FROMDATE]}") was refused as an array subscript — field references
    are now masked before the blocker scan. A single trailing ';' (legal in
    Crystal) no longer fails tokenization; two statements still refuse.
- What remains of the 39 is genuinely manual: runtime state PRD does not have
  (drilldowngrouplevel, currentfieldvalue, pagenumber-in-conditions) and
  multi-statement variable formulas.

## [1.35.0] — 2026-07-27

### Added

- **Conversion notes are sorted into what a consultant must actually do.**
  Every note landed in one "Other manual work" list, so repairs the layout
  agent had already applied ("7 text boxes grown to fit their font — verify")
  read as outstanding work and buried the few entries that genuinely need a
  decision. Notes are now classified — **manual** (a Crystal behaviour with no
  PRD equivalent), **applied** (done, worth a glance) and **info**
  (provenance) — with the latter two folded away, in the UI **and in the
  generated conversion report**. Statement of Account drops from 16 alarming
  bullets to 3 real ones. Classification is deterministic:
  an estimate should not move because a model felt differently today.
- **A filter over the Crystal Reports table on the Project page** — verdict
  chips (READY / REVIEW / BLOCKED / not triaged, each with its count) and a
  name search. A real engagement lands 150+ reports there, which is a scroll
  rather than a worklist; the effort strip recalculates for whatever is
  filtered, so "how long for just the REVIEW ones" is one click. Reports that
  have never been triaged get their own bucket instead of hiding inside "all".
- The layout wireframe opens **scaled to fit** for reports taller than the
  viewport, with an "Actual detail" toggle. A single 440pt chart band used to
  draw thousands of pixels tall, so the reviewer scrolled past acres of one
  rectangle and never saw the shape of the report.

### Fixed

- **Summary fields could collapse onto one report function.** RptToXml writes
  the .NET *type* name (`CrystalDecisions...DatabaseFieldDefinition`) when it
  cannot resolve the object, so every summary in such a report read as the
  same field grouped the same way — six distinct PRD functions became one
  name, and the layout elements all referenced whichever survived. The field
  and group are now recovered from the summary's own name, and the generated
  name distinguishes `PercentOfSum` from `Sum` (Crystal stores both as "Sum").
  A percent-of-total summary is now flagged rather than silently totalling.
- **Crystal's `GroupName` special field is carried across** instead of being
  reported as an unresolved reference. It prints the value the report is
  currently grouped by, which in PRD is simply that column in the group
  header. Only bound when the report really does group by that column.
- An element whose field reference is empty in the dump now says so, rather
  than reporting `Unresolved field reference: ''`.

- **Embedded pictures were being torn by the compound-file layout.** An `.rpt`
  is an OLE compound file: a stream's bytes are chained through 512-byte
  sectors that need not be adjacent on disk. The carver scanned raw file bytes,
  so any picture larger than one sector had foreign sector data spliced into
  it — the DIB still decoded, and rendered as a rolled or torn image. Carving
  now runs per stream (`Embedding N/CONTENTS`), falling back to raw bytes only
  when the file is not a readable compound file. **17 corpus dumps carried
  corrupted image bytes and have been re-carved.**
- **A picture could be assigned an image that belonged to another picture.**
  Matching was greedy per box, so the best-matching image could be spent twice
  while a different image went unused — a scanned signature came out as a
  second copy of the company logo. Confident pairs now claim each other first;
  reuse only happens once the images genuinely run out (a logo repeated per
  band).

### Changed

- **`samples/crystal/` tidied into three folders with one job each.**
  `corpus/` holds all 150 harvested reports as `.rpt` + `.xml` pairs (the
  binaries moved in from the old `samples/crystal-rpt/`); `demo/` holds the
  curated showcase reports; `by-feature/` stays the generated index. See
  [samples/crystal/README.md](samples/crystal/README.md).
- **"Try Crystal Reports" now loads a real report that has its own data.** It
  was an authored dump with no `.rpt`, so the demo could not start in the
  Crystal viewer. It is now the Xtreme World Sales Report — 2,191 saved rows,
  three nested groups, two charts, images — so the full path works: open the
  original in the viewer, convert it, open the `.prpt` in Report Designer.
  Two alternates ship beside it for the images story and for "show me
  something recent" (AdventureWorks, saved 2026-05-20).
- `report-classify` gained `--rpt-dir` and now copies each report's `.rpt` in
  beside its dump, so every feature folder is a self-contained demo. The
  generated index marks the **111 of 150** reports that carry saved data and
  therefore render in the viewer with no database. Those copies are gitignored
  (they duplicate `corpus/`) — re-run the command after a clone.

## [1.34.0] — 2026-07-25

### Added

- **Cross-tab grids recovered automatically** (`report-crosstabs`). The SAP
  SDK seals a cross-tab's rows/columns/measures behind reserved COM slots,
  so until now every cross-tab needed a hand-written
  `<CrossTabDefinition>`. They are now read **straight from the .rpt
  binary** with [rpt-rs](https://github.com/MrSrsen/rpt-rs) and injected
  into the dump, after which the ordinary pipeline produces a live PRD
  crosstab. **Corpus: 12 cross-tabs across 10 reports recovered — all
  convert**; corpus TODO placeholders 26 → 14 and triage 98 → 105 READY
  of 150.
- Cross-tab resolution now handles what real reports actually contain:
  **formula dimensions** (`{@Name}`), Crystal's **stored-name escaping**
  (`_x0020_` → space → the RptToXml underscore form), **duplicate-usage
  suffixes** (a field grouped twice is stored as `Field1`), and **repeated
  levels** (the same field grouped at two granularities is deduped with a
  note explaining that PRD needs a derived column per granularity).
  Every recovered grid is review-flagged; anything that cannot be bound to
  a query column stays an honest TODO.
- rpt-rs integration is optional and self-describing: located via
  `RPT_RS_PATH`, `tools/rpt-rs/`, the cargo build, or `PATH`; when absent,
  cross-tabs keep their hand-add TODO and nothing else changes.

### Fixed

- **Upstream contribution**: rpt-rs decoded nothing on Windows because the
  OLE root component (`\` there, `/` on Unix) survived its stream-path
  filter, so `Contents` was never recognised. One-line fix plus a
  regression test submitted as
  [MrSrsen/rpt-rs#1](https://github.com/MrSrsen/rpt-rs/pull/1); with it,
  their own fixture decodes 1,475 records and 600 of their tests pass.
  (An earlier changelog entry called this tool "broken on Windows and
  parked" — that conclusion was wrong and is corrected here.)

## [1.33.0] — 2026-07-25

### Added

- **Talend rules v4 — 190+ components**, extended from the gap analysis of
  the now 150-job corpus. Database families completed
  (Teradata/Greenplum/HSQLDb/MSSql/Mysql connection-commit-rollback,
  Snowflake, BigQuery, tSqlRow, tMongoDBOutput); **big data and object
  storage map through PDI's own mechanisms rather than invented steps** —
  Hive over JDBC, HDFS over VFS (`hdfs://` URLs on ordinary file steps),
  S3/Azure through VFS connections; plus files/fields/utilities
  (tExtractDelimitedFields, tAddCRCRow, tSynonymSearch, tSleep,
  tFileDelete, JSON writers). Corpus effect: **manual steps 293 → 167**,
  avg confidence 65 → 68.
- **Every unmapped component now carries its reason.** New
  documented-manual rule form (`pdi_type: null` + the why) covers Talend
  ESB Mediation Route components (Apache Camel) and service endpoints —
  Pentaho has no Camel/ESB engine, so the review list says so and points
  at the real path (rebuild the route on an integration platform, call
  PDI via Carte). In-house **custom components and joblets are detected
  by naming convention** and named as such, since no rules library can
  enumerate them. A regression test asserts no corpus step is ever left
  unexplained.
- **ESB route detection in the source analysis**: a job carrying Camel
  components is flagged SERIOUS *before* conversion as a different
  artifact kind, instead of trickling through as unmapped-step noise.

### Changed

- **SSIS removed from the roadmap** (not required). Phase 2 is now IBM
  DataStage only.
- Talend corpus documentation refreshed: 150 jobs, 1,668 steps, 220+
  distinct components, provenance in `samples/talend/MANIFEST.md`.

## [1.32.0] — 2026-07-25

### Added

- **CSCU Talend demo set** (`samples/talend_demo/`): four authored .item
  jobs on the live cscu_core schema — members_export (query → sort →
  file), branch_balances (aggregate; the new **Try Talend** sample),
  high_value_txns (filter), and cscu_nightly (tPrejob + three tRunJob
  calls → a real .kjb). The ETL twin of the Crystal demo ladder; all four
  convert at 88/100 average.
- **ETL consultant portfolio report** (`GET /project/portfolio?family=`,
  📊 button per family): confidence-grade distribution, step-outcome bar,
  **remaining manual work by source component** (with affected-export
  counts, re-parsed live), review-load histogram, 10 heaviest mappings,
  hours/$ at the engagement rate — the Informatica/Talend counterpart of
  the Crystal report.
- **Project page is context-aware and per-family**: separate cards for
  Informatica pipelines, Talend jobs and Crystal reports, each with its
  **own** effort/cost summary; opening the page while an artifact is
  loaded shows that family first (one click to show everything).
- Try buttons moved under the drop panel and split by source:
  **Try Informatica · Try Talend · Try Crystal Reports**.

### Fixed

- **Stale source paths after the repo rename**: the project store held
  dead `PDI-Migration` absolute paths, so the walkthrough click ("source
  export not found") and Crystal triage could not reach their sources.
  Paths now self-heal on read — exact path, rebase from the `samples`
  segment onto the current repo root, then basename search across the
  sample directories — and the healed value is written back. All 148
  stored ETL mappings resolve again.

## [1.31.0] — 2026-07-25

### Added

- **Talend production pass — Phase 1 complete.** (1) Component configs
  carried from the .item into the .ktr: tFileInputDelimited → CSV input
  (filename, separator, enclosure, header, typed schema),
  tFileOutputDelimited → Text file output, tFilterRow → Filter rows
  (simple conditions incl. IS NULL, AND/OR; advanced Java mode stays an
  honest TODO), tSortRow criteria with direction, tAggregateRow
  GROUPBYS/OPERATIONS → Group By aggregates. (2) **tRunJob → .kjb**: jobs
  that call other jobs generate a PDI Job with TRANS entries wired to the
  called jobs' .ktr files, ordered by the OnSubjobOk/... links (traversed
  through intermediate components; success links map to follow-on-success)
  — 12 orchestration jobs in the corpus convert; the assess warning
  becomes an INFO. (3) **Rules v3** (95 components): Excel output,
  property files, HSQLDb, Vertica/rollback connection management, AMC
  logging → Write to log, tMemorizeRows → Analytic Query, tSOAP → Web
  services lookup, tLibraryLoad; ESB/service-host components stay
  honestly manual. Corpus: manual steps 42 → 28, avg confidence 62 → 64.
- Generator fix: step descriptions are now built AFTER the config
  emitters run, so emitter honesty notes land in the .ktr.

## [1.30.0] — 2026-07-25

### Added

- **Consultant portfolio report** (`report-portfolio` CLI, GET
  /project/reports/portfolio, 📊 button on the Project page): one
  self-contained HTML page (inline SVG charts, prints to PDF) with the
  verdict split, formula-translation success bar, **remaining manual work
  bucketed by category** (cross-tab / subreport / image / unsupported
  summary / unmapped component, with affected-report counts), a
  **review-load histogram** (reports needing 0/1/2/3-5/6+ touches), the
  10 heaviest reports with reasons and cost, and hours/$ at a
  configurable rate. TriageResult now carries todo_kinds.
- **Backdrop images auto-repair**: a fade/watermark image overlapping the
  text it sits behind is the intentional Crystal pattern — the layout
  agent now moves such images to the front of the band (PRD paints in
  document order, first = behind) and the lint stops flagging
  backdrop-vs-content pairs as defects.
- Talend groundwork for the production pass: TABLE-style component
  parameters (filter CONDITIONS, aggregate GROUPBYS/OPERATIONS, sort
  CRITERIA) now parse into structured JSON rows on the step.

## [1.29.0] — 2026-07-25

### Added

- **Running totals convert** (`{#name}`). RunningTotalFieldDefinitions —
  present in the dumps (and now also emitted from the RAS model by the
  fork, which carries the reset GROUP the engine walk loses) — become
  group-scoped Item* report functions: the same live-verified mapping as
  the running-total variable rewrite. Entries dedupe by name preferring
  reset-aware ones; engine-only defs assume the innermost group with a
  verify note; evaluate conditions / non-group resets stay honest TODOs.
- **Binary `%` translates**: Crystal's `x % y` means "percentage of" —
  rewritten explicitly as `x * 100 / y` (never passed through to
  OpenFormula's postfix divide-by-100).
- **`crNoColor` / `DefaultAttribute` branches convert**: `Else crNoColor`,
  `Else DefaultAttribute` and If-without-Else in condition formulas become
  **2-arg IFs** — the engine keeps the element's static style when the
  expression yields no value (live-verified: the red branch fires, every
  other row keeps its static ink). Unexpressible positions stay honest.
- **Real currency symbols**: the fork reads `NumericFieldFormat
  .CurrencySymbol` from the RAS model (readable, unlike PictureData) and
  bakes the actual symbol into the computed `FormatString` — "$" is now
  only the fallback for an enabled-but-unnamed symbol.
- **Text de-overlap in the layout auto-fit**: overlapping always-visible
  labels/fields are nudged apart (same-row neighbours spread right, stacks
  become rows, otherwise minimal displacement); elements with visibility
  conditions are never moved (Crystal stacks mutually-exclusive fields).
  Corpus triage after this round: **98 READY / 52 REVIEW** of 150 (was 7/143 three releases ago); todo-placeholders 61 -> 26.

## [1.28.0] — 2026-07-25

### Added

- **Project-page agents.** The 📁 Project page's Crystal table now runs the
  **batch-triage agent** in place (🔎 Run triage, optional JNDI for live
  SQL validation): persistent ✓ READY / ⚠ REVIEW / ✋ BLOCKED chips with
  click-to-expand reasons (layout lint findings, manual formulas, TODOs,
  SQL verdict), and **per-report output parity** — upload the customer's
  Crystal export (PDF/CSV) for a persistent PASS/NEAR/FAIL chip. New
  endpoints POST /project/reports/triage and /project/report-parity;
  verdicts stored in the project DB (auto-migrated columns).
- **StdDev/Variance summaries convert.** PRD has no such report function,
  so they fold into a **windowed SQL column** — the report SQL wraps in a
  subquery selecting `STDDEV_SAMP(col) OVER (PARTITION BY group)` (sample
  variants, matching Crystal; population variants map to `*_POP`), the
  group ordering is re-applied outside, and the footer field binds to the
  column. Live-verified against CSCU. Elements carry a dialect note
  (SQL Server: STDEV/VAR); ops with no window equivalent (Median) stay
  honest TODOs.
- **Layout auto-fit.** Two mechanically-safe lint classes now repair
  themselves at load: page-overflow bands scale proportionally to the
  printable width, and text boxes shorter than their font grow to fit.
  Every repair is a review issue; overlaps stay flagged (an image under
  text is usually an intentional watermark). **Corpus effect: triage went
  from 7 READY / 143 REVIEW to 82 READY / 68 REVIEW.**
- Conversion report shows the datasource SQL **line by line** (one
  select-list column per line — mirrors the Inspect page's formatter).

## [1.27.0] — 2026-07-25

### Added

- **Embedded images carved from .rpt binaries** (`report-images`, auto-run
  by `extract-rpt.ps1`). Investigation finding: the RAS model declares
  `ISCRPictureObject.PictureData`, but it returns **null in the embedded
  in-proc RAS** the free runtime uses (verified with typed access) — the
  same SDK truncation family as cross-tab grids. So the raster is recovered
  from the .rpt file itself: signature-scan for PNG/JPEG/DIB blobs, prove
  every candidate by decoding it with Pillow (DIBs get a BITMAPFILEHEADER
  and convert to PNG), dedupe multi-bit-depth renditions, and match blobs
  to `PictureObject`s by aspect ratio (greedy best-score — layout boxes
  stretch; single-box/single-image matches unconditionally; Crystal's
  page-shaped preview thumbnails never win). Injected as
  `<ImageData Carved="true">`, which the parser/writer already consume;
  each carved image carries a "verify it is the right picture" note.
  **Corpus result: 83 images recovered across all 44 image-bearing
  reports, zero misses**; live-verified end-to-end (LarsBusk_GeneralIrma's
  213×39 logo renders in the converted .prpt). Pillow promoted to a core
  dependency.

## [1.26.0] — 2026-07-25

### Added

- **Cross-tabs → live PRD crosstabs.** A `CrossTabObject` carrying a
  `<CrossTabDefinition>` block (RowFields/ColumnFields/SummaryFields)
  converts to a real PRD crosstab — row/column dimension groups with
  `wizard:aggregation-type` cells (Sum/Count/Average/Max/Min) — hosted in a
  nested sub-report that shares the parent's datasource and SQL. The XML
  shapes were generated by the engine's own `CrosstabBuilder` + bundle
  writer (tools/CrosstabRef*.java) and live-verified against CSCU
  (branches × transaction types, correctly aggregated). Two engine
  requirements discovered and handled: the crosstab runtime needs data
  sorted by row-then-column dimensions (child SQL gets an automatic
  `ORDER BY`), and crosstab table layouts need `prpt-spec.version >= 4.0`
  in meta.xml (declared as 5.0.0 only for bundles containing a crosstab —
  everything else keeps its verified legacy layout mode). **The free SAP
  .NET SDK cannot export cross-tab grids** (reserved COM slots; verified by
  reflection and across all 12 corpus cross-tab dumps) — cross-tabs without
  the block stay honest TODOs, and the conversion report names the exact
  ~5-line XML to hand-add from the Crystal designer. New demo rung 9
  "Branch Activity Matrix - Cross-tab"; rung 6 keeps the no-definition
  path on show.
- **Demo set is now A4 portrait.** All nine cr_demo rungs + the flagship
  re-laid out portrait (`PAGE_W`-anchored bands, proportional column
  auto-fit) — all engine-validated, layout-lint clean, and live-rendered.

### Fixed

- **Per-side border fidelity.** Crystal borders are per-side; the parser
  collapsed them into a full box, so PRD drew vertical lines between
  column-header cells that Crystal never showed. Borders now parse with
  their sides and emit as PRD per-edge attributes (`border-bottom-*` etc.).

## [1.25.0] — 2026-07-25

### Added

- **Cloud LLM providers — Anthropic, OpenAI, Google, Azure.** Settings now
  offers Anthropic (Claude, default `claude-opus-5`), OpenAI (GPT, default
  `gpt-4o`), Google (Gemini via its OpenAI-compatible endpoint, default
  `gemini-1.5-pro`) and Microsoft (Azure OpenAI, deployment + resource
  endpoint) alongside local Ollama. One shared dispatch
  (`llm/translate.py: chat_json/chat_text/check_provider`) powers **every**
  AI feature: Informatica/Talend expression translation, Crystal Reports
  formula translation, the schema-SQL assistant, triage briefs, and per-step
  AI suggestions — the old "Anthropic not implemented yet" gates in the SQL
  assistant and solution suggester are gone. API keys come from Settings
  (stored locally, gitignored) or the provider's environment variable
  (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
  `AZURE_OPENAI_API_KEY`); the Environment card reports presence-only for
  all four. `pip install .[llm]` now installs both the `anthropic` and
  `openai` SDKs.
- **Insert/Update key inference.** The match keys for an Update Strategy →
  Insert/Update conversion are traced through the graph to the downstream
  target's PRIMARY KEY fields (parsed from the export's `<TARGET>`
  definitions) — keys and non-key update columns are emitted instead of a
  TODO. Verified against the real corpus (`hhs_cpm_afps.xml`).
- **Workflow Email/Command tasks → real PDI job entries.** Email tasks
  become Mail entries (recipient/subject/body carried over; SMTP server
  left to configure), Command tasks become Shell entries with the actual
  ordered command script — no more labeled placeholders.
- **Informatica mapplet expansion.** Mapplet instances are expanded inline
  into the parent pipeline: internal transformations become
  `instance.step`-prefixed steps, connectors are rerouted through the
  Input/Output boundaries, and the assessment warning drops from WARNING to
  INFO. Verified 0 dangling hops across the corpus.

## [1.24.0] — 2026-07-25

### Added

- **Tabbed layout preview for subreports**: a report with converted
  subreports now shows a *Main report* tab plus one tab per subreport
  (`▸ name 🔗` for linked ones), each rendering the subreport's own bands
  in the same wireframe — so you can see the nested report's layout, not
  just a box where it sits. The API summary carries each child's sections
  (`subreports[]`).

### Fixed

- **PK/FK badges were invisible to the app's own database user.** The
  PostgreSQL key-discovery query read `information_schema.table_constraints`,
  which PostgreSQL privilege-filters — a read-only report user (the JNDI
  account a report runs as) sees *none* of the constraints, even its own
  tables'. Rewrote it against `pg_catalog.pg_constraint` (visible to every
  role), pairing composite keys via `WITH ORDINALITY`. Verified live against
  CSCU as `pdc_user`: `accounts.mbr_id → members.mbr_id`,
  `accounts.br_id → branches.br_id`, etc. now surface. A regression test
  pins the query away from `information_schema`. (MySQL/SQL Server/Oracle use
  each vendor's catalog, which respects the user's `SELECT` grants — only
  PostgreSQL's `information_schema` needed this.)
- **FK badges are now unmistakable**: `🔗 FK → table.column` (was a faint
  amber arrow that read as decoration).
- **Layout preview is no longer squashed**: report bands are wide and short,
  so scaling the SVG to the card width collapsed the height — the vertical
  axis now has a 2.2× schematic stretch (column x-positions stay 1:1, so
  header/data alignment still reads true) and larger band/element labels.

## [1.23.0] — 2026-07-25

### Added

- **Connection panel on the Inspect page**: a dropdown of the JNDI
  connections discovered from the same simple-jndi config the reporting
  engine reads; picking one re-converts the report, so the schema
  assistant, previews, and the .prpt all follow. **⚙ Manage** adds full
  save / edit / delete, persisted to
  `~/.pentaho/simple-jndi/default.properties` (driver class inferred from
  the JDBC URL; passwords never returned by the listing API; connections
  owned by the PRD install's config are usable but not deletable here).
  Fixes "drag-dropped reports default to SampleData with no way to switch".
- **Multi-database dialect adapters** (`reports/db_dialects.py`): schema
  introspection, SQL validation, and key discovery now speak
  **PostgreSQL** (live-verified against CSCU), **MySQL** (`pymysql`,
  EXPLAIN), **SQL Server** (`python-tds`,
  `sp_describe_first_result_set`), and **Oracle** (`oracledb`,
  `EXPLAIN PLAN FOR`) — each with its own JDBC URL parser; a missing
  driver reports the exact `pip install`, and unsupported URLs (hsqldb...)
  stay an honest "not supported".
- **Schema browser**: 📚 Browse the schema inside the assistant card —
  every table with its columns and types, plus **🔑 PK and → FK badges**
  showing the join relationships (also fed to the LLM context as
  `[PK]` / `[FK -> table.column]` markers, so chat join advice follows the
  real constraints). The CSCU demo database currently defines no
  constraints — `samples/cscu/add_constraints.sql` is ready to run as the
  table owner.
- **Live dataset preview**: ▶ Run query executes the report's SELECT
  (SELECT-only guard, parameters substituted with their defaults) and
  shows the first 50 rows in a sticky-header grid — verified live against
  CSCU showing the flagship's exact filtered dataset.
- **Line-by-line SQL display**: the Inspect page pretty-prints the query —
  one select-list column per line, FROM/JOIN/WHERE/AND/ORDER BY on their
  own lines (display only; the bundle's SQL is untouched).

## [1.22.0] — 2026-07-25

### Added

- **Subreports convert into nested PRD sub-report bundles.** RptToXml dumps
  carry the full child report definitions; the parser now recurses into
  `<SubReports>` (detached first, so child tables/formulas never leak into
  the parent), runs each child through the complete pipeline (formula
  translation, SQL generation, WHERE folding), and the writer emits the
  nested bundle exactly as PRD's own samples do: `subreport/layout.xml`
  (root `element-type="sub-report"`), `parameter-mapping` in the child's
  data definition, the subreport manifest media-type, and a
  `<sub-report href>` element with `input-parameter` mappings in the parent
  band. Crystal's `Pm-<field>` linked parameters are sanitized to PRD-safe
  names and rewritten through the child's record selection, which then folds
  to a parameterized `WHERE`. **Live-verified**: the SAR demo's per-member
  KYC history filters correctly row by row; a two-field link (member AND
  branch) also verified. Corpus impact: TODO placeholders drop 176 → 133.
- **Visual table links → real JOINs**: linked-tables reports (no SQL
  command) now generate `JOIN ... ON` from the Database Expert's links
  instead of a cross join.
- **Query-backed parameter pick-lists**: a prompt whose record selection
  folded against a known column becomes a PRD dropdown backed by
  `SELECT DISTINCT <col>` over the report's own FROM clause — converted
  prompts offer real values from the live database.
- **Stress Lab (demo rung 8)** — deliberate boundary hunting, every finding
  verified against the real engine and documented in
  docs/CRYSTAL-COVERAGE.md: (1) count functions have no `field` property —
  writer fixed to emit them fieldless; (2) sub-reports in page bands make
  the engine throw — the converter now guards them into honest TODOs;
  (3) mandatory prompts without defaults block headless rendering;
  (4) formula groups render in data order; (5) group-scoped summaries
  referenced outside their group show the last group's value.
- **`report-classify`**: classifies a corpus by migration feature into
  `by-feature/` folders (a multi-feature report appears in each) with a
  generated README index — pick real-world demo reports by feature
  (this corpus: 22 with subreports, 35 with conditional formatting,
  12 with cross-tabs, ...).
- Formula stragglers: `DateSerial(y,m,d)` → `DATE(y;m;d)`;
  `DateAdd("d", n, date)` → date arithmetic (other intervals honestly
  manual).

## [1.21.1] — 2026-07-25

### Added

- **`bootstrap.ps1` — the one-command installer**: downloads the app from
  GitHub into `C:\Pentaho-Migration` (git clone, or a zip snapshot when
  git is absent; safe re-run pulls the latest), runs the guided
  `install.ps1` (venv, dependencies, web UI, Crystal preflight), detects
  the hardware — NVIDIA VRAM aggregated across GPUs via `nvidia-smi`, or
  CPU RAM — and writes `config/settings.json` with the matching
  qwen2.5-coder model and Ollama tuning env, mirroring the app's own
  recommendation ladder exactly (24 GB+ → 32b, 12 GB+ → 14b, 6 GB+ → 7b,
  CPU 32 GB+ → 7b, 16 GB+ → 3b, else 1.5b; multi-GPU adds
  `OLLAMA_SCHED_SPREAD`). Existing settings are never overwritten;
  `-PullModel` also downloads the model; `-InstallDir`/`-Branch` override
  the defaults. Verified end-to-end on this machine: fresh clone →
  install → 2× RTX 3060 detected → 32b configured → settings parsed by
  the app. README Quick start now leads with it (`irm ... | iex`).
  Fixed along the way: PowerShell 5.1's `Out-File -Encoding utf8` writes
  a BOM that the app's strict JSON parser rejects — the bootstrap writes
  BOM-less UTF-8.

## [1.21.0] — 2026-07-25

### Added

- **Conditional formatting → PRD style expressions**: Crystal conditional
  font colors and backgrounds now convert into `paint` /
  `background-color` style expressions on the element, with the condition
  run through the deterministic translator (Crystal color constants map to
  hex; `crNoColor`/`DefaultAttribute` honestly stay notes). *Live-proven
  against CSCU: the Delinquent30 loan balance renders red.*
- **Conditional suppression → visibility expressions**: object- and
  section-level Suppress formulas become `visible` style expressions
  (`=NOT(condition)`) on elements and bands (sections merging into one PRD
  band keep the honest note). *Live-proven: the PaidOff loan row is absent
  from the rendered report.*
- **Output-parity harness** (`reports/parity.py`, `pentaho-migrate
  report-parity <prpt|dump> <export.pdf|csv>`, `POST /reports/parity`):
  renders the converted report against the live JNDI database and diffs
  its **numbers** (normalized: currency stripped, accounting negatives
  folded, multiset compare) against the customer's Crystal export —
  PASS / NEAR / FAIL with the missing values listed. Live-verified:
  self-parity passes; a simulated customer CSV export of CSCU-100501's
  transactions matches the converted Member Statement.
- **Translator sharpeners**: `x in a to b` → `AND(x >= a; x <= b)`;
  Select Case range values (`1 To 5`) and `Is <op>` tests convert;
  single-assignment local variables (readability aliases) are inlined
  deterministically (multi-variable state stays honestly manual).
- **Group & record sort directions**: consumed from the dump's SortField
  list; the generated SQL now carries `ORDER BY` for groups (honoring
  descending) and record sorts — previously generated SQL had no ORDER BY
  at all, which PRD's relational groups silently depend on. Group Sort
  Expert / Top N is flagged as a review note.
- **Demo rung 7 — "Card Program Review - Select Case, Ranges & Sorts"**:
  every new translator feature in one live-rendering report (DEBIT group
  before CREDIT, newest cards first, multi-value Select Case, expiry-window
  range, inlined holder alias).
- **docs/CRYSTAL-COVERAGE.md**: the full Crystal→PRD feature map — what
  converts, into what, and whether it is deterministic, ✨ LLM-assisted
  (with confidence), or honestly manual.

## [1.20.1] — 2026-07-25

### Added

- **LLM provenance + confidence, back and structured**: formulas translated
  by ✨ AI-assist now carry `source: llm` and the model's self-reported
  confidence as fields (parsed out of the note text). The Formulas page
  shows a color-coded chip — *✨ LLM-translated · confidence: medium* —
  (green high / amber medium / red low) and the conversion report row says
  *✨ LLM-translated, confidence **medium***. Deterministic translations
  stay unmarked: if there is no chip, rules produced it.

### Changed

- **Phase messaging corrected — this is Phase 1, not Phase 2**: Informatica
  PowerCenter and SAP Crystal Reports are the completed sources; Talend's
  core shipped but a production-completion pass is outstanding, and known
  Informatica gaps are now listed honestly in the roadmap (mapplets,
  Email/Command workflow tasks as placeholders, Insert/Update key
  inference, Anthropic provider). README masthead, roadmap, and the
  Upload-page phase strip all updated.

## [1.20.0] — 2026-07-25

### Added

- **Select Case → nested IF(), deterministically**: a whole-formula
  `Select {x} Case v1: r1 Case v2, v3: r2 Default: rd` now translates to
  the real PRD formula (`IF(...;...;IF(...))`, multi-value cases become
  `OR(...)`), review-flagged with a branch-semantics note — the reviewer
  sees the actual Report Designer formula instead of "rebuild by hand".
  A missing Default returns `NA()` (noted, mirrors Crystal's Null); range
  cases (`1 To 5`, `Is < x`) honestly stay manual.
- **Every review row now shows its PRD-side artifact** (`Formula.
  prd_target()`), in the UI and the conversion report: the OpenFormula
  translation when there is one, or the generated report function —
  `RunningBalance = ItemSumFunction(field: AMOUNT) — report function
  generated in the bundle (Data tab > Functions in PRD)`. This closes the
  gap where an idiom rewrite displayed only its note (and the conversion
  report showed an empty backtick), leaving nothing concrete to review.
- The flagship demo gained `{@AuditNote}` (local string variable — genuinely
  manual) so the ✨ AI-assist flow still has something to demonstrate now
  that `{@TxnRiskBand}` converts on its own.

## [1.19.1] — 2026-07-25

### Added

- **Guided install/uninstall scripts**: `install.ps1` / `install.sh` (+
  `.bat` delegator) print what the app is and its version, check
  prerequisites (Python, Node) with download links, set up the venv +
  extras + UI build, run the Crystal-environment preflight (`report-env`)
  with an "optional — the app works without it" explanation, and finish
  with next steps (run script, sample, CLI highlights, docs).
  `uninstall.ps1` / `uninstall.sh` list exactly what they will remove and
  what they keep, confirm before acting, and support `-Force`/`--force`,
  `-DryRun`/`--dry-run`, and `-All`/`--all` (also removes converted
  output and the project database — kept by default).

### Fixed

- **The Crystal source is now shown on review-status formulas** — an idiom
  rewrite like `{@RunningBalance}` displayed only its note, so there was
  nothing to actually review; the original formula text now appears on
  every row that needs a human (review and manual).
- **Status badges no longer wrap** (the ✋ sat above the word "manual");
  the status column keeps a minimum width.
- **Embedded images are no longer counted as manual work anywhere** — the
  API todos list, effort estimate, conversion report, and `report-gaps`
  now share the triage rule (`is_todo_element`): an image whose bytes were
  migrated into the bundle is converted work; only byte-less images are
  TODOs. The flagship no longer lists its own logo as "other manual work".

## [1.19.0] — 2026-07-25

### Added

- **Layout QA agent** (`reports/layout_qa.py`, `pentaho-migrate report-qa`):
  deterministic geometry lint over every band — elements overflowing the
  printable page width, elements taller than their band, colliding fields
  (>40% overlap), fonts too large for their box, charts missing data
  columns, TODO placeholders — plus optional `--render` verification through
  the real engine (design-time PDF rendered and scanned so every label is
  proven to appear; needs a local PRD + pypdf). Findings carry
  error/warning/info severities; errors exit nonzero for CI use.
  *It earned its keep immediately: it found six real page-overflow defects
  in our own authored demo reports (rules and fields ending at 810–900pt on
  an 806pt page), all fixed at the source — the demo set now lints clean.*
- **Batch triage agent** (`reports/triage.py`, `pentaho-migrate
  report-triage <dir> --jndi <ds> [-t]`): sweeps a corpus and drafts the
  review verdict per report — **BLOCKED** (SQL fails against the live
  target, or parse failure), **REVIEW** (manual formulas, idiom rewrites to
  verify, TODO placeholders, layout findings), **READY** (clean + SQL
  proven). Combines the schema agent's EXPLAIN validation, the layout QA
  lint, formula stats, and effort into one markdown triage report with a
  sortable verdict table; an unreachable database never penalizes a report
  (SQL marked `unchecked`, noted in the header). Optional `--llm` adds a
  two-to-four-sentence "what to check first" brief per non-READY report.
  Demo set: 3 READY / 3 REVIEW (the intentional manual-work rungs); the
  150-file real corpus triages in seconds.
- **One-command launchers**: `run.sh`, `run.bat`, `run.ps1` — create the
  venv and install extras on first run, build the frontend if missing, then
  serve the app on port 8321 (`COPILOT_PORT` overrides).

### Changed

- **Schema assistant moved to its own full-width card** on the Inspect page
  (it was squashed into the half-width Data source card): spacious
  validation banner, larger chat bubbles with sensible max-widths, and a
  full-width input row.
- Triage/QA no longer count embedded images as TODOs — an image with
  migrated bytes is converted work, not manual work.

## [1.18.0] — 2026-07-24

### Added

- **Schema-aware SQL agent** (`reports/schema_agent.py`) — deterministic
  first, per the product's design principle:
  - **JNDI resolution**: connections are read from the same simple-jndi
    `default.properties` files the reporting engine uses (`~/.pentaho` and
    the PRD install), so the agent validates against exactly the database
    the report will run on. PostgreSQL targets are introspected
    (`information_schema`); other drivers get an honest "not supported"
    instead of a guess.
  - **Deterministic validation**: the report SQL is `EXPLAIN`ed against the
    live database with `${Param}` placeholders substituted by their
    defaults — missing tables, wrong columns, and dialect errors surface on
    the Inspect page *before* the report ever opens in PRD.
  - **Schema-grounded chat** on the Inspect page: the LLM sees the real
    schema, the report SQL, and the validation verdict. Proposed SQL is a
    reviewable diff — **Apply & re-convert** regenerates the bundle with
    `sql_override` and records the substitution as a review item; nothing
    is ever auto-applied. (Live-verified against CSCU + qwen2.5-coder:32b:
    correctly answered that `transactions` has no `mbr_id` and joins go
    through `accounts`.)
  - New API: `GET /reports/schema`, `POST /reports/sql/check`,
    `POST /reports/sql/chat`; `POST /reports/convert` gains `sql_override`.
  - New CLI: `pentaho-migrate report-sql <dump> --jndi <name>` — batch-able
    preflight that exits nonzero when the SQL fails against the target.
  - Optional dependency: `pip install .[schema]` (psycopg2-binary).

## [1.17.0] — 2026-07-24

### Added

- **Blocked Crystal idioms are now rewritten, not just flagged**: when the
  deterministic translator recognizes an untranslatable formula as a known
  idiom, it generates the equivalent native PRD report function itself and
  flags it `review` — answering "it suggests ItemSumFunction, so why doesn't
  it give it a go?". Recognized today:
  - the running-total variable idiom (`Shared NumberVar x; x := x + {T.F}; x`)
    → `ItemSumFunction` over the field (`+ 1` counters → `ItemCountFunction`),
    with a note to verify reset semantics;
  - whole-formula aggregates (`Sum({T.F})`, `Sum({T.F}, {T.G})`, `Count`,
    `Maximum`, `Minimum`) → `TotalGroupSumFunction` / `TotalGroupCountFunction`
    / `TotalItemMaxFunction` / `TotalItemMinFunction`, group-scoped when the
    Crystal call is.
  Elements referencing the formula bind to the generated function
  automatically — the flagship's `{@RunningBalance}` Balance column now
  renders live values against CSCU (verified: per-row accumulation matches
  the account total). All function classes verified present in PRD's
  classic-core jar. The same rewrite framework is the landing place for
  further idioms (Select Case chains, `%`, running averages).

### Fixed

- **Record-selection folding now maps `{Command.ALIAS}` to the alias's source
  column**: SQL cannot reference SELECT aliases in `WHERE` (and there is no
  real table named `Command`), so `{Command.MBR_NO} = {?MemberNo}` now folds
  to `WHERE m.mbr_no = ${MemberNo}`. Previously only record selections that
  referenced real table.column names filtered correctly.
- **Group functions now actually reset per group**: layout groups are named
  after their group column, matching the `group` property the generated
  summary/rewrite functions reference. Before, groups were named `GroupN`
  while functions referenced the column — so `ItemSumFunction` never reset
  and multi-group totals silently accumulated across the whole report
  (invisible in single-group demos filtered by a prompt).

### Changed

- **Member Statement demo defaults to a real member** (`CSCU-100501`, the
  busiest member — 5 transactions), so the parameterized statement renders
  meaningful rows and a visible running balance out of the box.

## [1.16.2] — 2026-07-24

### Changed

- **Demo reports are feature-tagged**: each CSCU report's name now states
  what it demonstrates — *Member Roster - Basic Layout*, *Accounts by Branch -
  Groups & Chart*, *Transaction Register - Formulas*, *Member Statement -
  Nested Groups & Running Total*, *Loan Portfolio - Conditional Formatting*,
  *Suspicious Activity - Subreport & Cross-tab*, and the flagship *Branch
  Transaction Summary - Prompt*. The tag flows everywhere the name goes:
  .prpt filename, PRD title bar, report masthead subtitle ("Demo: …"),
  conversion report, and the Project page.

## [1.16.1] — 2026-07-24

### Changed

- **CSCU demo reports moved to `samples/cr_demo/`** (was
  `samples/crystal/ladder/`): the six authored Crystal reports that resolve
  against the live CSCU database — the demo/golden-path set — now live in a
  clearly-named folder. The flagship UI sample stays at
  `samples/crystal/branch_transactions.xml` (the `/reports/sample` endpoint
  serves it); the generator writes both.

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
