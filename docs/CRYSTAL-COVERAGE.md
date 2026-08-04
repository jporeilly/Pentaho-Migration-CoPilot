# Crystal Reports → Pentaho Report Designer: feature coverage

What the Copilot migrates, what it becomes in PRD, and **how** it is
converted. Three methods, in order of preference (the product's design
principle — deterministic where accuracy is non-negotiable, AI only where
semantic judgment is required):

- **Deterministic** — rule-based, repeatable, no AI involved. `auto` needs
  no review; `auto → review` means the mapping is mechanical but a human
  glance is warranted (the note says why).
- **✨ LLM-assisted** — only what rules cannot prove is sent to the local
  LLM; every result is flagged `review` with the model's self-reported
  confidence shown. Never silently applied.
- **Manual (flagged)** — no faithful equivalent; converted as an explicit
  TODO placeholder or review note. The tool never guesses.

## Structure & layout — deterministic

| Crystal feature | Report Designer equivalent | Method |
| --- | --- | --- |
| Report/Page/Group/Detail bands | The same banded model (report-header, group bands, itemband, page-footer) | Deterministic |
| PageHeader | PRD's **physical page-header**, so the letterhead tops every page as Crystal prints it (it used to be mapped to a details-header inside the innermost group, where it never rendered at all) | Deterministic |
| **Conditionally suppressed sections** | Each Crystal section becomes a **nested collapsing sub-band**, so a hidden section takes no height — three mutually-exclusive letter variants occupy one slot, exactly like Crystal, instead of leaving two bands of blank space | Deterministic |
| A section with a declared height of **zero** | Height zero, honoured. A chart report collapses its per-row detail band this way; a 20pt floor turned 5,000 invisible rows into 187 blank pages against the original's one | Deterministic |
| **Underlay Following Sections** | The underlay's elements are painted *behind* the sections that follow, shifted into each one's coordinate space, and the underlay band itself is dropped — a watermark sits behind the letter instead of pushing it half a page down. Conditional variants share one runtime slot, so the copy lands in whichever variant renders | Deterministic → review |
| Groups (incl. nested) | Relational groups (nested via sub-group-body), named after their column so functions reset correctly | Deterministic |
| Group sort direction | `ORDER BY ... [DESC]` in the generated query | Deterministic |
| Record sort fields | `ORDER BY` after the group columns | Deterministic |
| Element geometry (twips) | Points, position-faithful | Deterministic |
| Fonts, colors, borders, alignment, band/element backgrounds | text/content/border styles | Deterministic |
| Per-field number & date format strings | `format-string` on number/date fields (needs the forked extractor) | Deterministic |
| Object/section static suppression | `visible="false"` / band excluded | Deterministic |
| **Conditional formatting** (font color, background) | **Style expressions** (`paint`, `background-color`) with the condition translated | Deterministic → review |
| **Conditional suppression** (object & section) | **`visible` style expression** (`=NOT(condition)`) on the element/band. Crystal's own dialect resolves too: special fields written bare in a formula (`PageNumber = 1`, `GroupNumber <> 1`, `RecordNumber`) become **declared PRD report functions** referenced by name, since libformula has no `PAGE()`; `CurrentFieldValue` resolves to the element's own value, including a summary field's; `DrillDownGroupLevel` folds to **0**, because a converted report only ever *is* the top-level view | Deterministic → review |
| **Conditional font style** (`crBold` / `crItalic` / `crBoldItalic`) | Crystal returns one combined value where PRD carries two independent keys, so the formula is read twice — into **`font-bold`** and **`font-italic`** | Deterministic → review |
| Conditional alignment, strikeout, underline | `alignment` / `font-strikethrough` / `font-underline` style expressions | Deterministic → review |
| `Color(r, g, b)` with literal components | Folded to a hex colour. Components only known at render time stay an honest note — libformula has no decimal-to-hex conversion, and a wrong colour is worse than a flagged gap | Deterministic |
| Conditional **ToolTipText / Hyperlink** | Recorded as information, not work: paged output cannot show either, so they do not belong in a consultant's estimate | Deterministic |
| Page size, orientation, margins | page-definition | Deterministic |
| Embedded images (logo etc.) | Embedded bundle resource. Bytes come from `report-images`: the free SAP SDK cannot read picture bytes (`PictureData` is null in the embedded RAS — verified), so the raster is **carved from the .rpt binary** (PNG/JPEG/DIB signature scan, decode-proven with Pillow, converted to PNG) and matched to its PictureObject by aspect ratio. 83 images recovered across all 44 image-bearing corpus reports, zero misses. Auto-run by `extract-rpt.ps1` | Deterministic → review (verify the matched picture) |
| Charts (bar, line, area, pie, doughnut) | Legacy-chart element + dataset collector + JFreeChart expression | Deterministic → review (verify aggregation) |
| **Gauge** | PRD has no dial, so it maps to the legacy-charts **Thermometer** (JFreeChart's meter family) — one value against a scale with warning/critical sub-ranges, fed by the single-value collector. Renders. | Deterministic → **review**: a tube not a dial, a single needle only — the consultant approves the substitution or swaps a KPI text field |
| Special fields (page N of M, print date) | PageOfPagesFunction / report.date message fields | Deterministic |

## Data & queries — deterministic

| Crystal feature | Report Designer equivalent | Method |
| --- | --- | --- |
| SQL Command objects | Query passed through verbatim; datasource replaced by a named JNDI connection | Deterministic |
| Linked tables (no SQL in the report) | SELECT generated from the columns the layout uses; the Database Expert's **visual links become `JOIN ... ON`**, with `ORDER BY` for groups/sorts (⚠ verify). Identifiers are quoted only where they must be — Crystal names columns `Last Name` and tables `dataroot/Customer_Query`, which emitted bare is not parseable SQL; each part of a dotted name is quoted separately, so a plain `CUSTOMER.COUNTRY` still reads the way you would write it by hand | Deterministic → review |
| **Saved data cached in the `.rpt`** | Recovered with [rpt-rs](https://github.com/MrSrsen/rpt-rs) and embedded as a PRD **inline-table datasource**, so the converted report opens in Report Designer and renders **real rows with no database at all** — the original SQL rides along as the `source-sql` query for going live. Cell encodings are calibrated against reports whose true values are known independently (the binary holds Number/Currency ×100 — rpt-rs v0.4.0+ un-scales them itself; Date arrives as a midnight Julian Day Number, DateTime packed as JDN + seconds). Column types come from the recovered **values**, not the metadata: some files declare every column an integer while the batches hold text, which made the engine fail on the first cell and refuse the bundle. Strings stored UTF-16LE but decoded big-endian are repaired by their zero-low-byte signature | Deterministic → review |
| Record selection formula | Folded into the SQL `WHERE` (alias-aware for `{Command.X}` refs) — converted prompts filter live | Deterministic |
| Parameters (prompts) | PRD parameters; static pick-lists → list-parameters; multi-value → `IN (${p})`; a folded prompt becomes a **query-backed dropdown** (`SELECT DISTINCT` on the live database) | Deterministic |
| Summary fields (Sum, Count, Avg, Max, Min, DistinctCount) | Item*/CountDistinct report functions, group-scoped (count functions correctly fieldless) | Deterministic |
| **`PercentOfSum` summaries** | This group's sum, the wider total it is a share of (the outer group, or the report's grand total), and a formula dividing them ×100. The engine's own `TotalGroupSumQuotientPercentFunction` looks like the match but divides two *fields* inside one group where Crystal divides one field across two group *scopes* — wired to it, every row printed the same percentage. Emitted as a plain `Sum` (the old behaviour) a percent column printed the raw total: a wrong number that reads as data rather than as a gap | Deterministic → review |
| **StdDev / Variance summaries** (incl. population variants) | PRD has no such function — folded into a **windowed SQL column** (`STDDEV_SAMP(col) OVER (PARTITION BY group)`, report SQL wrapped in a subquery, group ordering re-applied) that the footer field binds to. Live-verified. Dialect note: SQL Server uses `STDEV`/`VAR` | Deterministic → review |
| **RunningTotalField objects** (`{#name}`) | Group-scoped **Item\* report functions** — the same live-verified mapping as the running-total variable rewrite (an `ItemSumFunction` read mid-detail IS the running value). Reset-on-group carried from the RAS model (fork); engine-emitted defs that lose the group assume the innermost one with a verify note. Evaluate conditions / non-group resets stay honest TODOs | Deterministic → review |
| Currency symbol text | The REAL symbol from the RAS model (`NumericFieldFormat.CurrencySymbol` — readable, unlike PictureData) lands in the computed `FormatString`; "$" only as fallback when a symbol is enabled but unnamed | Deterministic |
| **Layout auto-fit** | Page-overflow bands scale proportionally to the printable width; text boxes shorter than their font grow to fit (each repair is a review issue). Overlaps stay flagged — an image under text is usually intentional | Deterministic → review |
| **Subreports** (linked & unlinked) | **Nested PRD sub-report bundles**: the child converts through the full pipeline (own query, groups, formulas, formatting); Crystal `Pm-<field>` links become `input-parameter` mappings and the child's record selection folds to a parameterized `WHERE` | Deterministic → review |
| **Cross-tabs** (with a `<CrossTabDefinition>` block in the dump) | **Live PRD crosstab** hosted in a nested sub-report: row/column dimension groups + `wizard:aggregation-type` cells (Sum/Count/Average/Max/Min), child query auto-`ORDER BY`-ed over the dimensions (the crosstab runtime requires sorted data); the bundle declares prpt-spec 5.0 | Deterministic → review |

## Formulas

| Crystal feature | Report Designer equivalent | Method |
| --- | --- | --- |
| Formula language (If/Then/Else, operators, ~40 function mappings, string `+`→`&` by field type) | OpenFormula | Deterministic (`auto`, or `review` when a mapping has a caveat) |
| `Select Case` (incl. multi-value branches, `a To b` ranges, `Is <op>` tests) | Nested `IF(...)` / `OR(...)` / `AND(...)` | Deterministic → review |
| `x in a to b` range test | `AND(x >= a; x <= b)` | Deterministic |
| Binary `%` ("percentage of": `x % y`) | `x * 100 / y` — rewritten explicitly, never passed to OpenFormula's postfix percent | Deterministic |
| `Else crNoColor` / `Else DefaultAttribute` / If-without-Else in condition formulas | **2-arg `IF(cond;value)`** — the engine keeps the element's static style when the expression yields no value (live-verified: red branch fires, all other rows keep static ink) | Deterministic → review |
| Running-total variable idiom (`x := x + {F}`) | **Generated `ItemSumFunction`/`ItemCountFunction`** wired to referencing elements | Deterministic → review |
| Whole-formula aggregates (`Sum({F}, {G})` …) | Generated `Total*` report functions | Deterministic → review |
| Single-assignment local variable (readability alias) | Inlined into the expression | Deterministic → review |
| Everything else rules cannot prove (multi-variable state, unusual functions) | OpenFormula proposal with a color-coded **confidence chip** (high/medium/low) | ✨ LLM-assisted → review |
| Untranslatable even by the LLM | Original preserved + concrete rebuild advice (e.g. "use ItemSumFunction") | Manual (flagged) |

## Honestly manual — flagged, never guessed

| Crystal feature | What you get |
| --- | --- |
| Subreports **in page bands** | TODO placeholder + note — the engine hard-forbids sub-reports in page headers/footers (verified) |
| Subreports with no definition in the dump | TODO placeholder (re-extract with the fork) |
| **Cross-tabs — grid recovered automatically** | `report-crosstabs` reads the row/column dimensions and measures **straight from the .rpt binary** with [rpt-rs](https://github.com/MrSrsen/rpt-rs) (the SAP SDK seals them behind reserved COM slots) and injects a `<CrossTabDefinition>` into the dump, so the report converts to a live PRD crosstab with no hand-editing. Handles Crystal's stored-name escaping (`_x0020_`), duplicate-usage suffixes (`Field1`), formula dimensions, and repeated levels. Every recovered grid is review-flagged. **Corpus: 12 cross-tabs across 10 reports recovered** | Deterministic → review |
| Cross-tabs **without** a definition block | TODO placeholder + issue naming the exact `<CrossTabDefinition>` XML to hand-add. **The free SAP .NET SDK cannot export cross-tab grids** (rows/columns/summaries sit behind reserved COM slots — verified by reflection; nothing surfaces in the DataDefinition either, across all 12 corpus cross-tab reports). Run `report-crosstabs` first (recovers it from the binary); if rpt-rs cannot decode that report, read the grid off the Crystal designer (~5 lines of XML), re-convert, and the pivot goes live |
| RunningTotalField objects with an **evaluate condition** or non-group reset | Issue note + unresolved reference — no mechanical PRD equivalent (plain running totals **convert**, see the data table) |
| Arrays, loops, multi-variable formula state | Original text preserved, `manual` status, LLM advice |
| Group Sort Expert / Top N (groups ordered by a summary) | Review note — order in the query or rebuild with PRD group sorting |
| Median / other summaries with no PRD function or SQL window aggregate | Review note + TODO placeholder for referencing elements (StdDev/Variance **convert** — see the data table above) |
| Dynamic / cascading parameter pick-lists | Textbox parameter + note (rebuild as query-backed parameters) |
| `crNoColor` / `DefaultAttribute` in a position with no keep-static equivalent (e.g. bare, outside an If branch) | Condition kept as a note — the common `Else crNoColor` / `Else DefaultAttribute` / missing-Else forms **convert** to 2-arg IFs (engine keeps the static style, live-verified) |

## Proof, not promises

Every conversion can be verified mechanically:

- **Release gate** (`report-release-check`): renders the **original `.rpt`
  through the SAP Crystal viewer** and the **conversion through the real
  Pentaho engine**, then diffs the two PDFs — page count, every number as a
  multiset, lines of the original that never appear (wrap- and
  spacing-insensitive, so a paragraph that re-wraps is not a defect), content
  that moved pages, near-empty widowed pages, and whether each group spans
  the same pages as the original, and - page by page, pairing them by
  content because the two renders have different page counts - how they
  **LOOK**. That last one is what catches a fill, rule or box the text
  comparison is blind to; a difference that appears on most compared pages
  is reported once as **report-wide**, because it lives in a band that
  repeats and takes one fix, not one per page. Verdict **SHIP** or
  **REVIEW**, with the evidence, and the gate always says how many pages it
  compared so a sampled check cannot read as a whole one. Every comparison is deterministic; the LLM only ever *annotates*
  a finding with a resolution, it never decides the verdict.
- **Consultant report** (HTML, PDF and markdown, all from one function so
  they cannot disagree): a **prioritised, costed action plan** — P1 blocks
  release, P2 correctness, P3 cosmetic — each action carrying why it matters,
  the concrete PRD steps, where the work lands, and hours and cost. The
  portfolio version rolls the same actions up by *kind* of work across a
  corpus, and each row of the focus list opens into that report's own plan.
- **Engine round-trip** (`--validate`): the .prpt loads in the real Pentaho
  Reporting engine.
- **Layout QA agent** (`report-qa`): geometry lint + optional rendered-PDF
  label verification.
- **Schema agent**: the SQL is `EXPLAIN`ed against the live JNDI target;
  the grounded chat proposes fixes as reviewable diffs.
- **Output parity** (`report-parity`): the rendered report's numbers are
  diffed against the customer's Crystal export — PASS / NEAR / FAIL.
- **Batch triage** (`report-triage`): READY / REVIEW / BLOCKED verdict per
  report across a whole corpus.
- **Cross-tab recovery walkthrough** (`python scripts/demo_crosstab_recovery.py`):
  runs a real corpus report from "the SDK cannot see this grid, so it is a TODO"
  through recovery to a live PRD crosstab, printing the recovered rows, columns
  and measures at each step.

## Known boundaries (found by the Stress Lab, verified against the engine)

`samples/cr_demo/08_stress_lab.xml` deliberately stacks complexity to map
where conversion stops being mechanical:

1. **Sub-reports in page bands**: the engine throws *"SubReports cannot be
   started for page headers"* at render time — the converter guards this
   and emits an honest TODO instead of a broken bundle.
2. **Count summaries**: PRD's count functions have **no `field` property**
   (they count rows) — the writer emits them fieldless; the engine rejects
   the bundle otherwise.
3. **Mandatory prompts without defaults** block headless rendering (parity,
   PDF preview with data). Interactive PRD prompts fine; give demo reports
   defaults. This is a conversion the pipeline got *right* — Crystal asked
   for the values too — so it is reported as one sentence naming the
   parameters, not as an engine stack trace.
4. **Groups on formulas** convert and render, but the query cannot
   `ORDER BY` the formula — groups re-emit on every value change unless the
   query is sorted by the formula's SQL equivalent.
5. **Group-scoped summaries referenced outside their group** show the last
   group's value (Crystal semantics trap, not a converter defect) — use a
   grand-total summary in report footers.
6. Multi-link subreports (two `Pm-` fields) convert and filter correctly —
   verified live.
7. **The demo statement's "beige panel" is an artifact of the REFERENCE
   render, not a lost feature.** Settled to the byte: the letter image
   inside the `.rpt` is pure white-backed - our carve and rpt-rs's
   independent decode of the picture record produce byte-identical
   histograms (227,093 px of `#ffffff`, 17,078 of tyre-track tan). The
   SAP viewer's PDF export quantises that image to a 256-colour indexed
   palette and lands its background on `#fffdfa`; the reference PDF's own
   embedded copy carries 225,936 px of `#fffdfa` and no pure white at all.
   Our bundle embeds the picture losslessly in DeviceRGB, so white stays
   white. **The conversion is the faithful one** - there is nothing to
   recover, and nothing to apologise for. (Same lesson, same report: the
   `.rpt` specifies Letter - 11,720 + 520 twips = 612x792pt - while the
   viewer renders A4, because it takes the paper size from the machine's
   default printer.) When comparing against any viewer export, expect
   palette and paper differences that belong to the reference.
8. **Sub-reports reach past the saved data.** Crystal caches rows for the
   MASTER report only, so a report whose sub-reports carry their own queries
   renders its own bands from the embedded rows and then asks the database
   for the rest. Reported in one sentence, like the prompts above. Across the
   corpus, these two account for **every** render that needs a live
   connection — 38 of the 52 saved-data reports render with no database at
   all, 11 more are genuinely parameterised, 3 have sub-report queries.
9. **Rich text runs inside one text object are flattened at extraction.** A
   Crystal text object with mixed formatting — a bold word inside a regular
   sentence — is exported by RptToXml as one `<Text>` string and one `<Font>`.
   The per-run formatting is gone before the pipeline sees it, and nothing in
   the dump even marks that the object *was* formatted, so it cannot be
   flagged per-report. The object converts with its single exported font,
   which is faithful to what the extractor gives us but not to Crystal.
   Recovering the runs means reading the RTF the way `report-images` reads
   picture bytes and `report-crosstabs` reads grids — the same free-SDK
   boundary, addressable only in the C# fork (parked). The other side of
   #44 — per-statement variance and true underlay (a watermark behind
   mutually-exclusive letter variants) — is done and regression-tested.

Live demo set: `samples/cr_demo/` — eight CSCU reports of increasing
complexity, every one converting AND rendering against the live CSCU
database. Real-world reports classified by feature for demo-picking:
`samples/crystal/by-feature/` (`pentaho-migrate report-classify`).
