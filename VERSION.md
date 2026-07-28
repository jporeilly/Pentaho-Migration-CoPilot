# Version

**1.39.3** - 2026-07-28

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
