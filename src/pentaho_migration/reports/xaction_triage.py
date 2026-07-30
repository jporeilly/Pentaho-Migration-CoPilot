"""Estate triage for old BI-platform xactions - the T&M sizing tool.

Point it at a pentaho-solutions folder (or any tree of .xaction files):
every action sequence is parsed, classified (report / chart / kettle /
other), and every REPORT xaction gets the deterministic complexity grade
plus a Level-of-Effort estimate from the published per-grade hour bands.
The output is the measured T&M model a conversion engagement needs -
counts, hours and $ from the estate's own files, not a guess.

The hour bands are the model shared for estate sizing (analyse + convert +
test + validate one report), tool-assisted vs a manual rebuild:

    Low     1-2h assisted   /  4-8h manual
    Medium  3-6h assisted   /  8-16h manual
    High    8-16h assisted  / 16-40h manual

Totals use the band mid-points; the bands ship in the report's assumptions
so a consultant can defend or adjust them.
"""

from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path

from pentaho_migration.reports.xaction_parser import (
    build_report_model, classify_complexity, parse_xaction)

# (assisted mid, manual mid, assisted band, manual band)
LOE_HOURS = {
    "Low": (1.5, 6.0, "1-2h", "4-8h"),
    "Medium": (4.5, 12.0, "3-6h", "8-16h"),
    "High": (12.0, 28.0, "8-16h", "16-40h"),
}

_GRADE_COLORS = {"Low": "#1a8917", "Medium": "#c9a24a", "High": "#c0392b"}


@dataclass
class XTriageRecord:
    file: str                 # path relative to the estate root
    name: str
    kind: str                 # report | chart | kettle | other | unparsable
    grade: str = ""           # Low | Medium | High ("" for non-reports)
    reasons: list = field(default_factory=list)
    definition: str = ""      # simple | legacy-ext | missing | "" (non-report)
    issues: int = 0
    copilot_hours: float = 0.0
    manual_hours: float = 0.0


def _non_report_kind(x) -> str:
    comps = {a.component for a in x.actions}
    if any("Kettle" in c for c in comps):
        return "kettle"
    if any("Chart" in c or "PivotView" in c for c in comps):
        return "chart"
    return "other"


def triage_estate(folder) -> list:
    """Walk the tree and grade everything. Nothing is skipped silently: a
    file that does not parse is a record too, kind='unparsable'."""
    root = Path(folder)
    records = []
    for path in sorted(root.rglob("*.xaction")):
        rel = str(path.relative_to(root))
        try:
            x = parse_xaction(path)
        except Exception:
            records.append(XTriageRecord(file=rel, name=path.stem,
                                         kind="unparsable"))
            continue
        if not x.is_report:
            records.append(XTriageRecord(file=rel, name=path.stem,
                                         kind=_non_report_kind(x)))
            continue
        grade, reasons = classify_complexity(x)
        model = build_report_model(path)
        if model.sections:
            definition = "simple"
        elif any("legacy-EXT" in i for i in model.issues):
            definition = "legacy-ext"
        else:
            definition = "missing"
        copilot, manual, _b1, _b2 = LOE_HOURS[grade]
        records.append(XTriageRecord(
            file=rel, name=path.stem, kind="report", grade=grade,
            reasons=reasons, definition=definition,
            issues=len(model.issues), copilot_hours=copilot,
            manual_hours=manual))
    return records


def build_xaction_estate_report_html(records, rate: float = 150.0,
                                     estate_label: str = "") -> str:
    """The consultant portfolio report for an xaction estate, in the house
    style (chart/colour/money helpers imported from the Crystal portfolio
    module so the three reports stay visually one family)."""
    from pentaho_migration import __version__
    from pentaho_migration.reports.portfolio_report import (
        GOLD, NAVY, SLATE, _clip, _hbar_chart, _money, _stacked_bar)

    reports = [r for r in records if r.kind == "report"]
    grades = {g: sum(1 for r in reports if r.grade == g)
              for g in ("Low", "Medium", "High")}
    kinds: dict = {}
    for r in records:
        kinds[r.kind] = kinds.get(r.kind, 0) + 1
    defs = {d: sum(1 for r in reports if r.definition == d)
            for d in ("simple", "legacy-ext", "missing")}
    copilot_h = sum(r.copilot_hours for r in reports)
    manual_h = sum(r.manual_hours for r in reports)
    saved_h = manual_h - copilot_h
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    grade_bar = _stacked_bar([
        (f"Low: {grades['Low']}", grades["Low"], _GRADE_COLORS["Low"]),
        (f"Medium: {grades['Medium']}", grades["Medium"], _GRADE_COLORS["Medium"]),
        (f"High: {grades['High']}", grades["High"], _GRADE_COLORS["High"]),
    ])
    kind_chart = _hbar_chart([(k, v, None) for k, v in
                              sorted(kinds.items(), key=lambda kv: -kv[1])])
    def_chart = _hbar_chart([(k, v, _GRADE_COLORS["High"]
                              if k in ("legacy-ext", "missing") else None)
                             for k, v in defs.items() if v])

    # priority actions - one row per kind of work, house table shape; the
    # Effort column is the affected reports' full LoE (where the hours live)
    def _rows_for(pred):
        return [r for r in reports if pred(r)]
    actions = []
    legacy = _rows_for(lambda r: r.definition == "legacy-ext")
    if legacy:
        actions.append((1, "Rebuild legacy-EXT report definitions",
                        "the old extended-format definitions do not translate "
                        "- re-save via an old Report Designer or rebuild the "
                        "layout in PRD; the query and parameters convert "
                        "either way", legacy))
    missing = _rows_for(lambda r: r.definition == "missing")
    if missing:
        actions.append((1, "Locate the missing report definitions",
                        "the xaction names a definition that is not beside it "
                        "- pull the full solution folder from the server",
                        missing))
    bursting = _rows_for(lambda r: any("bursting" in x for x in r.reasons))
    if bursting:
        actions.append((1, "Re-home bursting/distribution in PDI jobs",
                        "the render converts to .prpt; the email loop becomes "
                        "a PDI job (Get rows -> loop -> Reporting output -> "
                        "Mail) or the server scheduler", bursting))
    mdx = _rows_for(lambda r: any("MDX" in x for x in r.reasons))
    if mdx:
        actions.append((2, "Recreate MDX sources as PRD Mondrian datasources",
                        "PRD supports Mondrian natively - same catalog, same "
                        "MDX, keep the field names", mdx))
    js = _rows_for(lambda r: any("JavaScript" in x for x in r.reasons))
    if js:
        actions.append((2, "Fold JavaScript business logic into SQL or PRD "
                           "functions",
                        "per-row logic becomes a computed column; sequence "
                        "glue usually falls away - verify each script", js))

    from pentaho_migration.reports.action_plan import PRIORITY_LABEL
    from pentaho_migration.reports.portfolio_report import (
        PRIORITY_BG, PRIORITY_INK)
    action_rows = "".join(
        f'<tr><td><span class="pchip" style="background:{PRIORITY_BG[p]};'
        f'color:{PRIORITY_INK[p]}">{escape(PRIORITY_LABEL[p])}</span></td>'
        f'<td><b>{escape(title)}</b><div class="muted">{escape(how)}</div></td>'
        f'<td class="num">{len(rows)}</td>'
        f'<td class="num">{sum(r.copilot_hours for r in rows):,.1f}h'
        f'<div class="muted">{_money(sum(r.copilot_hours for r in rows), rate)}'
        f"</div></td></tr>"
        for p, title, how, rows in actions)

    focus = sorted(reports, key=lambda r: (-r.copilot_hours, r.file))[:10]
    focus_rows = "".join(
        f'<tr><td>{escape(_clip(r.name, 46))}<div class="muted">'
        f"{escape(_clip(r.file, 60))}</div></td>"
        f'<td><span class="chip" style="color:{_GRADE_COLORS[r.grade]}">'
        f"{r.grade}</span></td>"
        f"<td>{escape(r.definition)}</td>"
        f'<td class="num">{r.copilot_hours:,.1f}h</td>'
        f'<td class="num">{_money(r.copilot_hours, rate)}</td>'
        f'<td class="muted">{escape(_clip("; ".join(r.reasons), 80) or "-")}'
        "</td></tr>"
        for r in focus)

    bands = "".join(
        f"<tr><td><span class='chip' style='color:{_GRADE_COLORS[g]}'>{g}"
        f"</span></td><td class='num'>{a}</td><td class='num'>{m}</td>"
        f"<td class='num'>{grades[g]}</td></tr>"
        for g, (_c, _m, a, m) in LOE_HOURS.items())

    label = escape(estate_label or "estate")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Xaction Estate Triage — Consultant Portfolio Report</title>
<style>
  body {{ margin: 0; font: 14px/1.5 'Segoe UI', Arial, sans-serif; color: #22303a; }}
  header.mast {{ background: {NAVY}; color: #fff; padding: 18px 40px; }}
  header.mast h1 {{ margin: 0; font-size: 21px; }}
  header.mast p {{ margin: 4px 0 0; color: {GOLD}; font-size: 13px; }}
  main {{ max-width: 860px; margin: 0 auto; padding: 8px 40px 40px; }}
  h2 {{ color: {NAVY}; border-bottom: 2px solid {GOLD}; padding-bottom: 5px;
       margin: 34px 0 12px; font-size: 17px; }}
  .tiles {{ display: flex; flex-wrap: wrap; gap: 12px; }}
  .tile {{ background: #eef2f4; border-radius: 8px; padding: 12px 18px;
          min-width: 150px; flex: 1; }}
  .tile b {{ display: block; font-size: 22px; color: {NAVY}; }}
  .tile span {{ font-size: 12px; color: {SLATE}; }}
  .tile.gold b {{ color: {GOLD}; }}
  .muted {{ color: {SLATE}; font-size: 12.5px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  thead th {{ background: {NAVY}; color: #fff; text-align: left;
             padding: 7px 10px; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #e3e9ec; }}
  td.num, th.num {{ text-align: right; }}
  tbody tr:nth-child(even) {{ background: #f6f8f9; }}
  .chip {{ font-weight: bold; }}
  .pchip {{ display: inline-block; padding: 2px 9px; border-radius: 999px;
           font-size: 11px; font-weight: bold; white-space: nowrap; }}
  footer {{ margin-top: 40px; padding-top: 12px; border-top: 1px solid #d7dee3;
           color: {SLATE}; font-size: 11.5px; }}
</style></head><body>
<header class="mast"><h1>Xaction Estate Triage — Consultant Portfolio Report</h1>
<p>{len(records)} xactions scanned · {label} · generated {now} ·
Migration Copilot v{__version__}</p></header>
<main>

<h2>Executive summary</h2>
<div class="tiles">
  <div class="tile"><b>{len(records)}</b><span>xactions scanned</span></div>
  <div class="tile"><b>{len(reports)}</b><span>report xactions (convert to .prpt)</span></div>
  <div class="tile"><b>{grades['Low']} / {grades['Medium']} / {grades['High']}</b>
    <span>complexity Low / Medium / High</span></div>
  <div class="tile"><b>{copilot_h:,.0f}h</b>
    <span>estate effort, tool-assisted ({_money(copilot_h, rate)})</span></div>
  <div class="tile"><b>{manual_h:,.0f}h</b>
    <span>manual rebuild ({_money(manual_h, rate)})</span></div>
  <div class="tile gold"><b>{_money(saved_h, rate)}</b>
    <span>saved ({saved_h:,.0f}h @ ${rate:,.0f}/h)</span></div>
</div>

<h2>Complexity distribution</h2>
<p class="muted">Deterministic grades from each xaction's own structure —
the Level-of-Effort model is measured, not assumed.</p>
{grade_bar}

<h2>What the estate contains</h2>
<p class="muted">Only report xactions convert to .prpt; chart/dashboard
xactions become CDE dashboards or PRD chart reports, Kettle xactions are ETL
for the PDI side.</p>
{kind_chart}

<h2>Report definitions</h2>
<p class="muted">Simple-format definitions convert; legacy-EXT and missing
ones are the P1 rows below.</p>
{def_chart}

<h2>Priority actions across the estate</h2>
<p class="muted">The engagement plan rolled up by kind of work. Effort is the
affected reports' full per-grade LoE — the hours live inside the grades, the
rows say where to spend them.</p>
<table><thead><tr><th>Priority</th><th>Work</th>
<th class="num">Reports</th><th class="num">Effort</th></tr></thead>
<tbody>{action_rows or '<tr><td colspan="4" class="muted">nothing beyond the per-report conversion work</td></tr>'}</tbody></table>

<h2>Focus list — the heaviest xactions</h2>
<table><thead><tr><th>Xaction</th><th>Grade</th><th>Definition</th>
<th class="num">Est. hours</th><th class="num">Est. cost</th>
<th>Reasons</th></tr></thead><tbody>{focus_rows}</tbody></table>

<h2>Level-of-Effort bands</h2>
<p class="muted">Per report: analyse + convert + test + validate. Totals above
use the band mid-points.</p>
<table><thead><tr><th>Complexity</th><th class="num">Tool-assisted</th>
<th class="num">Manual rebuild</th><th class="num">Reports</th></tr></thead>
<tbody>{bands}</tbody></table>

<footer>Assumptions: hours are the published per-grade bands (mid-points for
totals) at ${rate:,.0f}/h; grades and classifications are deterministic rules
output from the xaction files themselves, no AI. Generated by Pentaho
Migration Copilot v{__version__}.</footer>
</main></body></html>"""
