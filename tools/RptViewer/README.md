# RptViewer — look at the original `.rpt`

A small WinForms host around the `CrystalReportViewer` control, so you can put
a customer's **original Crystal report** on screen next to the converted
`.prpt`. Nothing in the conversion pipeline needs it — it is for review and
demos.

**It needs only the free SAP Crystal .NET *runtime*** (the same MSI the
extractor already requires). No Crystal Reports licence, no designer, and no
"Crystal Reports for Visual Studio" developer install: the runtime puts
`CrystalDecisions.Windows.Forms` in the GAC and this is a thin wrapper around
it.

## Build

```powershell
.\tools\RptViewer\build.ps1
```

Needs Roslyn `csc` (VS 2019+ Build Tools) and the Crystal runtime. The binary
is not committed.

## Use

```powershell
.\tools\RptViewer\RptViewer.exe                                   # file-open dialog
.\tools\RptViewer\RptViewer.exe report.rpt                        # view it
.\tools\RptViewer\RptViewer.exe report.rpt --export out.pdf       # headless PDF, no window
.\tools\RptViewer\RptViewer.exe report.rpt --server S --db D --user U --password P
```

## What renders, and what needs a database

| The report was saved… | What you get |
| --- | --- |
| **with data** (`EnableSaveDataWithReport`) | The whole report, rendered from the saved rows — no database needed. `worrallbrian_MajorCitiesInCanadaUSAandMexico.rpt` renders 1,750 pages this way |
| **without data** | Layout, labels and static bands only; the data bands need the report's own database. Pass `--server/--db/--user/--password` to fill them |

A logon failure is reported as one actionable line explaining the report was
saved without data — not a raw Crystal exception.

## Side-by-side review

```powershell
.\tools\RptViewer\RptViewer.exe samples\crystal\corpus\Foo.rpt          # original
pentaho-migrate report samples\crystal\corpus\Foo.xml --jndi MyDS    # converted .prpt -> open in PRD
```

## Alternatives

- **Editing** reports (not just viewing) needs SAP's "Crystal Reports,
  developer version for Visual Studio" installer, or the standalone Crystal
  Reports 2020 designer — see [docs/INSTALL.md](../../docs/INSTALL.md).
- **No SAP runtime at all:** `rpt-rs` (v0.4.0+, `tools/rpt-rs/`) renders
  `.rpt` to PNG/PDF/HTML on any platform
  (`rpt-render report.rpt -f png -o out.png`).
