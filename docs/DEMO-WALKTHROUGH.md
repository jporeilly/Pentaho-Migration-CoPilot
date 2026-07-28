# Crystal Reports — end-to-end demo walkthrough

A scripted 10-minute demo: a customer's Crystal report goes in, a Pentaho
report comes out, and **at no point is a database configured**. Every step
below was run and verified before this script was written.

The demo report is a real harvested account statement
(`samples/crystal/demo/souvikduttachoudhury_Statement_of_Account.*`):
letterhead, watermark, a scanned signature, two nested groups, a running
total, 74 pages of data saved inside the `.rpt`.

## Before the audience arrives

```bash
.venv/Scripts/pentaho-migrate report-env
```

All four checks green (PRD, Java, SAP Crystal runtime, RptToXml). Start the
app (`run.ps1` or the "copilot-web" launch entry) and open
<http://127.0.0.1:8321>. Have Pentaho Report Designer closed but ready.

## Act 1 — "This is what you have today" (2 min)

Click **Try Crystal Reports**. On the Inspect page, click
**🔍 View original .rpt**.

The SAP Crystal viewer opens **as a desktop window, front and center**, showing
the statement with real data — no database, because the report was saved with
its rows. Scroll a page or two. Talk track: *"This is your report, running on
the tool you're leaving."*

(If you demo with a customer's own file: drag the `.rpt` itself onto the drop
zone — extraction runs server-side — and the View-original button works for
uploads too.)

## Act 2 — "This is the conversion, and it hides nothing" (4 min)

Walk the stepper:

- **Inspect** — the wireframe is the parsed layout (bands, elements, the
  page-header letterhead), the generated SQL sits under Data source, and the
  connection panel/schema assistant are live if a JNDI target exists. Nothing
  here came from an LLM.
- **Formulas** — this report: **3 auto, 2 review, 0 manual**. Open a review
  row: the original Crystal formula and the OpenFormula translation sit side
  by side. Talk track: *"Deterministic where accuracy matters; the LLM only
  gets what rules can't prove, and everything it touches is flagged."*
- **Other manual work** — three items, all the same root cause (Crystal
  suppresses sections conditionally; PRD merges sections into one band).
  Expand "fixed automatically" to show the folded repairs. Talk track:
  *"The honesty contract: what didn't convert says so, with the reason.
  Estimates come from this list, so it can't be allowed to lie."*
- **Download** — the effort panel (hours and $ vs a manual rebuild), then
  **👁 PDF preview**: the bundle renders through the real Pentaho engine in a
  popup, WITH the embedded data. Note the conversion-report line: *"53 saved
  data rows recovered from the .rpt and embedded."*

## Act 3 — "And this is it in Pentaho, with your data" (3 min)

Click **🎨 Open in Report Designer**. PRD launches on this machine with the
converted report loaded (first launch takes a moment - say so). Hit preview.

**Real rows appear — customers, addresses, amounts — with no datasource
configured.** The saved data recovered from the `.rpt` ships inside the bundle
as the report's dataset. Point at the Data tab: the original SQL is right
there as the **`source-sql`** query. Talk track: *"Going live is picking that
query and giving it a JNDI connection — the layout doesn't change."*

Close by putting the Crystal viewer and PRD side by side on screen: same
letterhead, same watermark and signature, same $43.50.

## If the conversation turns

| They ask for... | Do this |
| --- | --- |
| "Something recent, not a 2002 report" | Same flow with `demo/ljokhan_AdventureWorks-TotalSalesByYear` — saved May 2026, AdventureWorks, converts with zero manual work. |
| "Show me a hard one" | `demo/workcontrolgit_WorldSalesReport` — pie chart, three nested groups, and **sixteen honest TODOs**, because it is a drill-down report and drill-down has no PRD equivalent. The honesty demo. |
| "What about our 3,000 reports?" | **📁 Project** page: 150-report corpus with triage verdicts (filter to ⚠ REVIEW, show reasons), then **📊 Consultant report** — the portfolio effort/cost document, printable. |
| A specific feature (sub-reports, cross-tabs, images...) | `samples/crystal/by-feature/` — every corpus report filed by what it demonstrates; the README marks the 111 that carry their own data. |

## Known rough edges (say them before they're noticed)

- The PRD preview's page count differs slightly from Crystal's (83 vs 74):
  band heights and the page-1 header order are not identical, by design —
  Crystal prints page 1 as ReportHeader-then-PageHeader; PRD tops every page
  with the page header.
- Message-field amounts print unformatted ("43.5", not "$43.50") — number
  formatting inside interpolated prose is a known gap.
- Crystal's *collapse* of a suppressed section leaves blank space in PRD (the
  elements hide; the band keeps its height). It's in the manual-work list.
