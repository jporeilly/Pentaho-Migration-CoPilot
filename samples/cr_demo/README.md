# CSCU Crystal Reports demo set (cr_demo)

Six authored RptToXml dumps of **increasing complexity**, all backed by the
live `cscu_core` credit-union schema so each one **converts and renders
end-to-end** against the real database. This is the pipeline's golden-path
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
| 4 | Member Statement **- Nested Groups & Running Total** | parameter, nested groups | running total → manual (report-function advice) |
| 5 | Loan Portfolio **- Conditional Formatting** | conditional font color, StdDev aggregate | both flagged honestly |
| 6 | Suspicious Activity **- Subreport & Cross-tab** | subreport, image, cross-tab | three TODO placeholders |

The flagship UI sample **Branch Transaction Summary - Prompt**
(`../crystal/branch_transactions.xml`) demonstrates the working parameter
prompt: the record selection folds into the SQL WHERE, so changing the Branch
prompt in Report Designer re-filters the report live.

Rungs 1–4 convert cleanly on the auto/review path; 5–6 deliberately exercise
the honest-flagging path (manual formulas and TODO placeholders) — the tool
never silently drops what PRD can't do mechanically.

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
