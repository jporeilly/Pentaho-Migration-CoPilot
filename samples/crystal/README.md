# Crystal Reports samples

Three folders, three jobs.

| Folder | What it is |
| --- | --- |
| `corpus/` | **All 150 harvested reports**, each as a matched pair: `Foo.rpt` (the Crystal original) and `Foo.xml` (its RptToXml dump). This is what the coverage, gap and portfolio commands run against. |
| `demo/` | The **"Try Crystal Reports"** scenario the UI loads, plus the authored CSCU dump. |
| `by-feature/` | A **generated** index: every corpus report copied into a folder per feature it demonstrates (`charts/`, `sub-reports/`, `cross-tabs/`, `running-totals/`, ...). Pick a demo report by the feature you want to show. |

## Why the pairs

The `.xml` dump is what the converter reads; the `.rpt` is what a customer
actually hands you. Keeping them side by side means one report is one place,
and the viewer launcher can always find the original for a dump you are
reviewing.

**111 of the 150 originals were saved with their data** (`EnableSaveDataWithReport`).
Those render in the Crystal viewer with no database at all — they are the only
ones that can carry a demo end to end without standing up the source system.
The `by-feature/README.md` marks them with `*`.

## The demo path

`demo/Statement_of_Account.*` — a customer account
statement: letterhead, watermark, a scanned signature, two nested groups, a
running total, 74 pages of saved rows.

It was chosen for being **substantial and still landing clean** — 43 elements,
zero manual formulas, and three honest TODOs, all of them the same thing
(Crystal suppresses sections conditionally; PRD merges sections into one band).

Two extremes were tried and rejected, which is worth knowing before you swap it:

| Report | Why not |
| --- | --- |
| `AdventureWorks-TotalSalesByYear` | Converts perfectly — **zero** manual work, saved 2026-05-20 — but it is two elements and a chart. Nothing to be impressed by. Keep it for "show me something recent". |
| `WorldSalesReport` | The richest report in the corpus: live pie chart, three nested groups, 2,191 rows. It is also a **drill-down** report, and drill-down has no PRD equivalent, so it lands with sixteen real TODOs. A good honesty demo, a bad opening one. |

The rest of the corpus is one command away — `by-feature/` groups all 150 by
what they demonstrate, so "show me one with sub-reports" is a folder, not a
search.

```powershell
tools\RptViewer\RptViewer.exe samples\crystal\demo\WorldSalesReport.rpt
pentaho-migrate report samples\crystal\demo\WorldSalesReport.xml -o output --validate
```

Then open the generated `.prpt` in Report Designer. The layout, groups, charts
and formulas come across; **data in PRD needs a live datasource** — the saved
rows live in the `.rpt` and are not carried into the `.prpt`, so point the
`SampleData` JNDI connection at the Xtreme sample database (or any equivalent)
to see rows there.

`demo/branch_transactions.xml` is the older authored CSCU dump. It has no
`.rpt`, so it cannot be opened in the viewer — that is exactly why it stopped
being the Try scenario.

## Regenerating the feature index

```powershell
pentaho-migrate report-classify
```

Defaults to `corpus/` in and `by-feature/` out, copying each report's `.rpt`
in beside its dump so every folder is self-contained. Those copies are
gitignored (they duplicate `corpus/`) — re-run the command after a clone.
