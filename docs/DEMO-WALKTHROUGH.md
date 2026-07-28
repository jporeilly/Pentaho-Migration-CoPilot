# Crystal Reports — end-to-end demo walkthrough

A scripted 10-minute demo: a customer's Crystal report goes in, a Pentaho
report comes out, and **at no point is a database configured**. Every step
below was run and verified before this script was written.

The demo report is a real harvested account statement
(`samples/crystal/demo/Statement_of_Account.*`):
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
- **Other manual work** — one item on this report. Expand "fixed
  automatically" to show the repairs the pipeline applied and is merely
  telling you about. Talk track: *"The honesty contract: what didn't convert
  says so, with the reason. Estimates come from this list, so it can't be
  allowed to lie — and notice how short it is BECAUSE the list is honest,
  not despite it."*
- **Download** — the effort panel (hours and $ vs a manual rebuild), then
  **👁 PDF preview**: the bundle renders through the real Pentaho engine in a
  popup, WITH the embedded data. Note the conversion-report line: *"53 saved
  data rows recovered from the .rpt and embedded."*
- **Release check** — the download buttons stay locked until it finishes, and
  the progress bar names each stage. It renders the **original through the
  SAP viewer** and the **conversion through the Pentaho engine**, then
  compares the two PDFs four ways: the numbers as a set, the lines of text,
  where each statement breaks across pages, and — page by page — how they
  **look**. This report comes back **⚠ REVIEW**: *36 of 36 statements span
  the same pages as the original*, and the appearance check flags a fill the
  conversion is missing (see the rough edges below).

  Talk track: *"It renders both and compares them, and it is telling you
  about a difference I would otherwise have to hope you didn't notice."*
  Be precise about what it does and does not establish — it checks the data,
  the pagination and the appearance of the pages it compared, and it says how
  many that was. It is not a proof of equivalence, and a clean result is
  evidence rather than a guarantee. Overselling this is the one thing that
  will cost you the room, because the customer will find the exception.
- **Consultant report** (`.html`, `.pdf`, `.md`) — open the HTML. It leads
  with a **prioritised, costed action plan**: what to do first, what it
  costs, what the customer sees if it is skipped, and the Report Designer
  steps to do it. This report: **4 actions, 0.61h**, no P1 blockers. Talk
  track: *"This is what you'd hand a consultant on Monday morning."*

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
| "Something recent, not a 2002 report" | Same flow with `demo/AdventureWorks-TotalSalesByYear` — saved May 2026, AdventureWorks, converts with zero manual work. |
| "Show me a hard one" | `demo/WorldSalesReport` — pie chart, three nested groups, a drill-down design, and Crystal's Top-5-plus-Others group selection, which PRD has no equivalent for. Comes back **⚠ REVIEW** — 6 actions, 2.27h, of which 2 items block release, each naming its fix. The honesty demo. |
| "What about our 3,000 reports?" | **📁 Project** page: 150-report corpus with triage verdicts (filter to ⚠ REVIEW, show reasons), then **📊 Consultant report** — the portfolio document. It leads with the engagement plan (the same actions rolled up by *kind* of work, so you staff against the rows), and **clicking any report in the focus list opens its full plan**. Printable. |
| A specific feature (sub-reports, cross-tabs, images...) | `samples/crystal/by-feature/` — every corpus report filed by what it demonstrates; the README marks the 111 that carry their own data. |

## Known rough edges (say them before they're noticed)

- **The letter's beige background panel is missing**, and the gate says so —
  this is the honest centrepiece, so lead with it rather than hope. Crystal
  paints the letter block on a pale panel; the conversion does not. It is not
  recoverable from what the extractor gives us: there is no beige anywhere in
  the dump, no box, no section background, and the image inside the `.rpt` is
  white-backed. Crystal applies it at render time and RptToXml never exports
  it — the same family as the picture bytes and the cross-tab grids the free
  SAP SDK will not open. Talk track: *"That is the boundary of what the free
  SDK exposes, and the tool tells you where the boundary is instead of
  quietly rendering something close."*
- **The conversion is 58 pages against the original's 74** — and that is the
  conversion being *better*, not worse: all 36 statements span the same pages
  as the original, and the original leaves 37 near-empty spill pages that the
  conversion consolidates. The gate reports the delta as information rather
  than a defect, and says so on the page.
- **Rich text inside one text object loses its runs.** A Crystal text object
  with mixed bold/regular formatting converts with the first run's font
  throughout. The extractor flattens the object to one string and one font,
  so the pipeline cannot currently even *see* the runs — worth saying plainly
  rather than being caught by it.
- **Top-N group selection has no PRD equivalent.** If they ask for the World
  Sales report, its "Top 5 countries + Others" prints as every country. It is
  in the action plan with the SQL recipe (rank in the query, UNION an Others
  row) — a good moment for the honesty contract.
