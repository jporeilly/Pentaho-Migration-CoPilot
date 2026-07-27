# Version

**1.35.0** — 2026-07-27

**The Crystal demo now runs end to end.** "Try Crystal Reports" loads a real
harvested report that ships its own `.rpt` and 2,191 saved rows, so the
original opens in the Crystal viewer, converts, and lands in Report Designer
without a database anywhere in the chain. `samples/crystal/` was tidied into
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
