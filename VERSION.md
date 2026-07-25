# Version

**1.20.0** — 2026-07-25

Phase 2 multi-source in progress — Talend + Crystal Reports shipped, with
the agent trio (schema-aware SQL, layout QA, batch triage). New: **Select
Case converts deterministically to nested IF()** (review-flagged PRD
formula, honest manual fallback for ranges), and every review row now shows
its **PRD-side artifact** — the OpenFormula translation or the generated
report function (e.g. `RunningBalance = ItemSumFunction(field: AMOUNT)`) —
in the UI and the conversion report, so there is always something concrete
to review. See [CHANGELOG.md](CHANGELOG.md) for history.
