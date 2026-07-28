# Version

**1.38.0** — 2026-07-28

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
