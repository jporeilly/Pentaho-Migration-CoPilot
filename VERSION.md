# Version

**1.41.0** - 2026-07-29

**The generated SQL runs against a real database, rebuilt from the reports
themselves.** During a PoC there is usually no database to point a converted
report at. `report-sample-db` recovers one: the schema from the field
metadata every `.rpt` declares, the data from the rows Crystal saved inside
them, split back into base tables by the qualified name. Xtreme and the SAP
BOE samples were rebuilt this way, loaded into MySQL, and the demo statement's
own SELECT returns its rows joined correctly. What it cannot recover is stated,
not smoothed over: a column no report selected has no values, a join key no
report saved is synthesized and labelled as such.

**A Crystal table is named by its ALIAS, which fixed one bug wearing three
faces.** Keying tables by the physical name left an XML datasource calling its
table `dataroot/Customer_Query` while every link said `{Customer...}`: the join
silently vanished, the FROM named an XPath no database resolves, and the `/`
forced quoting MySQL rejects. All three gone once the alias — what every field,
formula and link is written against — became the key.

**A modern cross-tab renders its pivot with real data.** The SAP BOE income
statements pivot on a date computed from Year and Month; that dimension is now
computed in the sub-report's SQL, so ComparativeIncomeStatement renders a fully
populated actuals-vs-budget pivot with its month columns labelled — a 2016-era
demo the 2002 statement could not be.

**A Crystal gauge converts to a working chart, not a red TODO.** PRD has no
dial, but its Thermometer chart is the same idea — one value against a scale
with thresholds — so a gauge maps to it and is flagged for the consultant to
approve.

**Open in Report Designer actually opens the report now** (the detached launch
left `cmd` with no console, so the batch's `start` never fired), the PDF and
consultant reports open in their own browser tabs, and the Try button picks any
of five demo reports from a dropdown.

See [CHANGELOG.md](CHANGELOG.md) for the full 1.41.0 list and history.

---

## 1.40.0 - 2026-07-28

**The release gate can see.** It compared extracted text and nothing else, so
a background panel that vanished, a rule the original never draws, or a total
box that lost its fill all left the text identical and it reported SHIP. It
now renders both reports, pairs the pages by content - 74 original against 58
converted, so page N is not page N - and compares how each pair LOOKS. A
difference that appears on most pages is reported once as report-wide,
because it lives in a band that repeats and takes one fix, not one per page.

**Three real layout defects it exists to catch, found and fixed.** Crystal
does not draw a zero-thickness line; white is its "no fill", not an opaque
white; and a picture scales to fill its box. The first put a stray dot and a
trailing underline on every detail row, the second hid the grey Total box
behind the labels in front of it, the third letterboxed the watermark into
two thirds of its width.

**The preview shows the whole report with its navigation** - the PDF itself,
so the browser's own viewer gives every page and the outline panel, instead
of twelve images with no way to reach page 40.

The demo statement now reports **REVIEW**, not SHIP - correctly. Its letter
sits on a beige panel that Crystal paints at render time and RptToXml never
exports, and the gate says so instead of letting it pass.

**The consultant report is now the deliverable.** It leads with a
prioritised, costed action plan - P1 blocks release, P2 correctness, P3
cosmetic - and every action carries why it matters, the concrete Report
Designer steps, where the work lands, and its hours and cost. It downloads as
HTML, **PDF** or markdown, all rendered from one function so the document a
customer receives and the numbers quoted in the app cannot drift apart. The
portfolio report gets the same treatment one level up: actions rolled up by
kind of work, and every row of the focus list opens into that report's own
plan.

**A chart report converts to one page again.** A Crystal section can
legitimately declare a height of zero - that is how a chart report collapses
its per-row detail band - and the parser was raising every section to a 20pt
floor. The AdventureWorks demo printed 187 pages against the original's one.

**Saved-data recovery stopped losing whole reports**: strings decoded with
the wrong byte order, and column types taken from metadata that lied about
holding text. Types now come from the recovered values.

**Conditional suppression not carried is down from 39 to 9** across the
corpus, and the nine that remain are genuine Crystal shared-variable state.
`PercentOfSum` prints a real share instead of the raw total, and generated
SQL quotes the identifiers that need it. The demo statement passes the
release gate: **SHIP**, with 36 of 36 statements spanning the same pages as
the original.

**A chart report converts to one page again.** A Crystal section can
legitimately declare a height of zero — that is how a chart report collapses
its per-row detail band — and the parser was raising every section to a 20pt
floor. The AdventureWorks demo printed 187 pages against the original's one.
It now matches the original exactly.

**Saved-data recovery stopped losing whole reports.** Strings stored as
UTF-16LE came back decoded big-endian, and some `.rpt` files declare every
saved column as an integer while the batches hold text — which made the
engine fail on the first cell and refuse to load the bundle at all. Types
now come from the recovered values rather than from metadata that lies.

**Conditional suppression not carried is down from 39 to 9**, and the nine
that remain are genuine Crystal shared-variable state. `PercentOfSum` prints
a real share instead of the raw total. The demo statement passes the release
gate: **SHIP**, with 36 of 36 statements spanning the same pages as the
original.

**Conditional suppression now survives conversion** — the corpus's largest
fidelity gap (93 dropped conditions) is down to 39, all genuinely manual.
Conditions on merged sections ride their elements; aggregates in conditions
become synthesized report functions. The demo report converts with zero
manual items.

**The converted .prpt now opens in Report Designer showing real data with
no database** — the saved rows inside the .rpt are recovered, typed and
embedded as the report's inline dataset (SQL rides along as `source-sql`).
That was the last gap in the end-to-end story.

**The Crystal demo runs end to end.** "Try Crystal Reports" loads a real
harvested report that ships its own `.rpt` and its own saved rows, so the
original opens in the Crystal viewer, converts, and lands in Report Designer
without a database anywhere in the chain. It is picked for converting clean -
zero manual work. Conversion notes are sorted now too, so repairs the layout
agent already applied stop reading as outstanding work. `samples/crystal/` was tidied into
`corpus/` (all 150 reports as `.rpt` + `.xml` pairs), `demo/` and the
generated `by-feature/` index, which marks the **111 of 150** reports that
carry saved data.

Behind that, two image defects were fixed: pictures spanning more than one
OLE sector were being carved with foreign bytes spliced in (17 corpus dumps
re-carved), and a picture could be handed an image belonging to a different
picture.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal Reports, and
Talend.
See [CHANGELOG.md](CHANGELOG.md) for history.
