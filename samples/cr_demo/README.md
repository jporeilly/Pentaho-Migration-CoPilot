# CSCU Crystal Reports demo set (cr_demo)

Nine authored RptToXml dumps of **increasing complexity**, all backed by the
live `cscu_core` credit-union schema so each one **converts and renders
end-to-end** against the real database. All pages are **A4 portrait**. This is the pipeline's golden-path
regression and demo set; the 150-file GitHub corpus (`samples/crystal/real/`)
stays the parser's real-world *variety* test.

These are authored dumps, not extracted from `.rpt` binaries — the converter
consumes RptToXml XML, so no Crystal Reports Designer is needed to test it.
Regenerate with `python samples/cr_demo/build_ladder.py`.

| # | Report (name = demo feature) | Demonstrates | Convert outcome |
|---|------------------------------|--------------|-----------------|
| 1 | Member Roster **- Basic Layout** | single table, page bands, footer | all auto |
| 2 | Accounts by Branch **- Groups & Chart** | join, group, Sum totals, **migrated bar chart** | all auto |
| 3 | Transaction Register **- Formulas** | multi-join via `accounts`, translated formulas | formulas auto |
| 4 | Member Statement **- Nested Groups & Running Total** | parameter, nested groups | running total → **generated ItemSumFunction** (review) |
| 5 | Loan Portfolio **- Conditional Formatting** | conditional font color → **paint style expression** (delinquent = red, live), conditional suppression → **visible expression** (paid-off rows hidden, live), StdDev aggregate | StdDev flagged honestly |
| 6 | Suspicious Activity **- Subreport & Cross-tab** | **linked subreport → nested PRD sub-report** (member KYC history filtered per row, live), cross-tab | cross-tab stays TODO |
| 7 | Card Program Review **- Select Case, Ranges & Sorts** | multi-value Select Case → IF/OR, `in a to b` range, local-alias inlining, **descending group + record sorts** | all deterministic (auto/review) |
| 8 | Stress Lab **- Boundaries** | 3 nested groups (one on a formula), **two-field-linked subreport**, complex child (own group + summary + cond. format), page-band subreport (engine-forbidden → TODO), query-backed pick-list, full formula zoo | maps the boundaries — see [docs/CRYSTAL-COVERAGE.md](../../docs/CRYSTAL-COVERAGE.md) |
| 9 | Branch Activity Matrix **- Cross-tab** | `<CrossTabDefinition>` block → **live PRD crosstab** (branches × txn types, summed) hosted in a nested sub-report | all auto (review the pivot) |

**Cross-tab recovery is demoed elsewhere.** These dumps are *authored* by
`build_ladder.py`, so there is no `.rpt` binary for `report-crosstabs` to read:
rung 9 carries a hand-written `<CrossTabDefinition>` (the converted path) and
rung 6 deliberately carries none (the manual path). To see a grid recovered
from a real binary, run:

```
python scripts/demo_crosstab_recovery.py
```

which walks `samples/crystal-rpt/ajryan_B1Budget_M.rpt` from "cross-tab is a
TODO" to a live PRD crosstab.

The flagship UI sample **Branch Transaction Summary - Prompt**
(`../crystal/branch_transactions.xml`) demonstrates the working parameter
prompt: the record selection folds into the SQL WHERE, so changing the Branch
prompt in Report Designer re-filters the report live.

Rungs 1–4, 7 and 9 convert cleanly on the auto/review path; 5–6 deliberately
exercise the honest-flagging path (unsupported aggregates and TODO
placeholders) — the tool never silently drops what PRD can't do mechanically.
Rung 6's cross-tab carries NO definition block (the manual-path demo: the
conversion report names the exact XML to add), while rung 9's does — showing
both sides of the cross-tab workflow.
The full feature map is in [docs/CRYSTAL-COVERAGE.md](../../docs/CRYSTAL-COVERAGE.md).

## Rendering against live CSCU

Each converted `.prpt` references the `CSCU` JNDI datasource. To render with
real data (in Report Designer, or headless):

1. Add a `CSCU` datasource to PRD's JNDI config pointing at the cscu_core
   Postgres database (host, port 5433, database `cscu_core`).
2. Convert: `pentaho-migrate report samples/cr_demo/03_transaction_register.xml --jndi CSCU`
3. Open the `.prpt` in Report Designer and Preview, or use `👁 PDF preview`
   in the web UI for an empty-data layout render.

The test suite renders every rung; the live-data render assertion is opt-in:

```
set CSCU_LIVE=1 && pentaho-migrate  ...   # (see tests/test_crystal_ladder.py)
```
