# Version

**1.42.0** - 2026-07-31

**A fourth source family: old Pentaho BI-platform reports.** The estates still
on `.xaction` action sequences and their JFreeReport `.report` definitions —
the direct ancestor of PRD's own format — now convert like every other source.
The sequence's lookup becomes the `.prpt` query (`{PREPARE:x}` → `${x}`),
SecureFilter prompts become parameters (query-backed *and* static pick-lists),
the old definition becomes the layout, `$()` message templates carry over
verbatim. Drop an `.xaction` or a zipped solution folder on the same upload
page; the same CLI command converts it; a Try picker offers five corpus demos.
Built corpus-first against 36 steel-wheels-era xactions: 25 report sequences,
zero parse failures.

**Every gap now proposes its own fix.** The principle that already governed
Crystal formulas is wired through every workflow: a converter must suggest the
solution and output it for review, never just log the error. Informatica
transformations with no 1:1 PDI step carry the closest PDI approach from a
versioned `_suggestions` library (Transaction Control → commit size or a job
transaction; Web Services → a lookup or REST step; mapplet ports → the
sub-transformation's input/output specification steps). Xaction bursting
suggests a PDI job, JavaScript suggests a computed column, MDX suggests PRD's
Mondrian datasource. The suggestions reach the Map page, the review checklist,
the markdown and PDF reports, and the consultant portfolio reports.

**Crystal's Top-N is solved, not flagged.** "Top 5 countries with an Others
row" — Crystal's Group Sort Expert — has no PRD group equivalent, so the query
now does it: a per-group total, a dense rank of those totals, and a CASE that
relabels the tail. Nested Top-N ranks within its parent, the pie follows the
same relabelled column for free, and the embedded sample is bucketed too so the
offline `.prpt` matches. Measured against the original World Sales Report,
every figure and percentage agrees: USA $57,573,832 / 36.2% … Others
$51,239,713 / 32.2%.

**An estate is sized by measuring it, not guessing.** `xaction-triage` walks a
whole solutions folder, classifies every sequence, grades every report
Low/Medium/High from its own structure, and applies published Level-of-Effort
bands to produce a costed engagement plan — the T&M model a conversion
proposal needs, from the customer's own files. Nothing is skipped silently: an
unparsable file is a record, and an estate with no report sequences is told so.

Phase 1 remains complete — Informatica PowerCenter, SAP Crystal Reports,
Talend, and now Pentaho Xactions.
See [CHANGELOG.md](CHANGELOG.md) for history.
