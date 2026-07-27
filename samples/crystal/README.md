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

`demo/workcontrolgit_WorldSalesReport.*` — the Xtreme World Sales Report,
harvested from GitHub. It was picked because it is both **viewer-ready**
(2,191 saved rows) and **feature-dense**: three nested groups, two charts,
images, summaries, conditional formatting and a record-selection formula.
Page one alone puts a live pie chart, a summary table and branded headers on
screen, which is what makes the before/after land.

Two curated alternates sit beside it for when the conversation goes elsewhere:

| Report | Reach for it when |
| --- | --- |
| `souvikduttachoudhury_Statement_of_Account` | The talk is about **images and fidelity** — logo, watermark and a scanned signature, all carved out of the `.rpt` and embedded in the `.prpt`. 74 pages, and **no manual formulas at all**. |
| `ljokhan_AdventureWorks-TotalSalesByYear` | Someone says the corpus looks dated. Saved **2026-05-20**, AdventureWorks, one clean chart. |

The rest of the corpus is one command away — `by-feature/` groups all 150 by
what they demonstrate, so "show me one with sub-reports" is a folder, not a
search.

```powershell
tools\RptViewer\RptViewer.exe samples\crystal\demo\workcontrolgit_WorldSalesReport.rpt
pentaho-migrate report samples\crystal\demo\workcontrolgit_WorldSalesReport.xml -o output --validate
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
