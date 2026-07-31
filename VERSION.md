# Version

**1.43.0** - 2026-07-31

**Both old Pentaho report dialects now translate — and the whole family is
proven against a live database.** 1.42.0 added `.xaction` sequences whose
simple-format definitions convert; the legacy-EXT dialect (`report-definition`
object graphs, the format the old Report Design Wizard wrote) was honestly
flagged as a rebuild. No longer: styled elements, resource bundles, nested
bands with parent-relative percent sizes, nested sub-reports, chart
expressions and report functions all parse into the same model. All four
Steel Wheels EXT reports convert and render against the SampleData HSQLDB:
Inventory List with its traffic-light stock formatting and HASCHANGED vendor
grouping, invoice with its watermark underlay and one invoice per page,
Variance Report with green/red trend arrows toggling per row, alternating row
shading and a three-series chart, Top Ten with its pie chart inside a nested
sub-report.

**The sequence's own values resolve at conversion time instead of becoming
notes.** Dynamic `{name}` SQL fragments substitute the input's default — the
platform's own text substitution, reproduced; one-line arithmetic JavaScript
(`PrevYear = (YEAR - 1)`) is evaluated by a guarded interpreter and threaded
through the query, bindings, labels and chart columns; a comma-list default
feeding `IN (...)` becomes a PRD multi-select parameter with the values
pre-selected; prompt pick-lists ship their lookup SQL as real query-backed
list parameters; an MDX-fed report gets a typed empty stub query so the
bundle opens and renders for review, with the Mondrian datasource suggested.
Server-hosted images embed when a local install has them, the watermark band
converts as an underlay, and the conversion-notes classifier files all of
this as applied work — "Other manual work" holds only real hand-work. The
Income Statement converts with zero manual notes.

**The emitter is now validated against Report Designer's own output.** PRD
ships 36 known-good sample `.prpt` files — files its own bundle writer
authored. A validation harness sweeps them: every XML tag we emit must appear
in PRD-authored files, unknown expression classes must resolve in the engine
jars, all 36 render through our harness (34 do; two need scripting engines we
don't load), and our conversions are compared structurally against the
shipped re-authorings of the very same Steel Wheels reports — identical group
and band skeletons. The sweep caught a real bug on its first run: static
parameter pick-lists were emitted as `<value-list>`, a shape the engine
parser silently ignores. They are now query-backed list parameters — the only
kind PRD itself authors.

**The workbench understands the whole estate.** The schema assistant
introspects every database PRD has a JDBC driver for — through PRD's own Java
and `lib/jdbc`, read-only — so SampleData browses its 14 tables, validates
converted SQL and previews live rows. The data-source panel picks up the
selected report's connection and tests it. The layout QA pass runs on
xactions and knows a layered stack (mutually-exclusive visibility) from a
real overlap; the wireframe badges layered elements so the design view is
self-explanatory. Estate triage grades legacy-EXT as a translated dialect
with a review sign-off, not a rebuild line.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal Reports,
Talend, and Pentaho Xactions (both definition dialects).
See [CHANGELOG.md](CHANGELOG.md) for history.
