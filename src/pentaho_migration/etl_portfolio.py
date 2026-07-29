"""ETL consultant portfolio report (Informatica / Talend): the engagement
view of a batch-converted mapping portfolio — confidence grades, remaining
manual work by component type, review-load distribution, focus list, and
hours/$ at the engagement rate. Shares the chart language and page shell of
the Crystal portfolio report; every number is deterministic.
"""

from collections import Counter
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from pentaho_migration.reports.portfolio_report import (
    BAD, GOLD, GOOD, LIGHT, NAVY, SLATE, WARN, _hbar_chart, _money, _stacked_bar)

GRADE_COLORS = {"A": GOOD, "B": "#67ad3f", "C": WARN, "D": "#e07b39", "E": BAD}

FAMILY_LABELS = {"informatica": "Informatica PowerCenter",
                 "talend": "Talend"}


def analyze_manual_steps(records):
    """Re-parse each unique source export and count the source types of steps
    with NO PDI mapping plus untranslated expressions — the ETL analogue of
    the Crystal TODO-category breakdown. Deterministic; skips missing files."""
    from pentaho_migration.mapper import RulesMapper
    from pentaho_migration.parser import detect_parser
    from pentaho_migration.project import resolve_source_path

    unmapped: Counter = Counter()
    unmapped_files: dict = {}
    expressions_todo = 0
    seen = set()
    for record in records:
        source = resolve_source_path(record.source_path)
        if source is None or source in seen:
            continue
        seen.add(source)
        try:
            parser = detect_parser(source)
            pipelines = parser.parse_file(source)
        except Exception:
            continue
        for pipeline in pipelines:
            RulesMapper.for_pipeline(pipeline).apply(pipeline)
            for step in pipeline.steps:
                if step.pdi_type is None:
                    unmapped[step.source_type] += 1
                    unmapped_files.setdefault(step.source_type, set()).add(source.name)
                for expr in step.expressions:
                    expressions_todo += expr.translated is None
    return unmapped, unmapped_files, expressions_todo


def build_etl_portfolio_report_html(records, family="informatica", rate=150.0):
    label = FAMILY_LABELS.get(family, family.title())
    title = f"{label} Migration — Consultant Portfolio Report"
    n = len(records) or 1

    grades = Counter(r.grade for r in records)
    auto = sum(r.auto for r in records)
    review = sum(r.review for r in records)
    manual = sum(r.manual for r in records)
    steps_total = (auto + review + manual) or 1
    copilot_h = sum(r.copilot_hours or 0 for r in records)
    manual_h = sum(r.manual_hours or 0 for r in records)
    saved_h = manual_h - copilot_h
    avg_score = round(sum(r.score for r in records) / n)

    load_bins = {"0 (hand over)": 0, "1": 0, "2": 0, "3-5": 0, "6+": 0}
    for r in records:
        key = ("0 (hand over)" if r.manual == 0 else "1" if r.manual == 1
               else "2" if r.manual == 2 else "3-5" if r.manual <= 5 else "6+")
        load_bins[key] += 1

    unmapped, unmapped_files, expr_todo = analyze_manual_steps(records)

    grade_bar = _stacked_bar([(g, grades.get(g, 0), GRADE_COLORS[g])
                              for g in "ABCDE"])
    step_bar = _stacked_bar([("auto", auto, GOOD), ("review", review, WARN),
                             ("manual", manual, BAD)])
    unmapped_items = sorted(
        ((f"{stype}  ({len(unmapped_files[stype])} export(s))", count, GOLD)
         for stype, count in unmapped.items()), key=lambda t: -t[1])[:12]
    unmapped_chart = _hbar_chart(unmapped_items)

    # Each unmapped component with a known category gets its SUGGESTED PDI
    # approach from the rules library - the consultant report proposes the
    # solution, it does not just chart the gap.
    from pentaho_migration.ir import SourceTool
    from pentaho_migration.mapper import RulesMapper
    tool = SourceTool.TALEND if family == "talend" else SourceTool.POWERCENTER
    suggestions = RulesMapper.for_tool(tool).suggestions
    suggestion_rows = "".join(
        f"<tr><td>{escape(stype)}</td><td>{escape(suggestions[stype])}</td></tr>"
        for stype, _count in sorted(unmapped.items(), key=lambda t: -t[1])
        if stype in suggestions)
    suggestions_html = (
        "<h2>Suggested PDI approach per component</h2>"
        "<p class=\"muted\">The closest PDI solution for each component with no "
        "1:1 step — apply and verify, rather than rebuilding from scratch.</p>"
        "<table><thead><tr><th>Component</th><th>Suggested approach</th></tr>"
        f"</thead><tbody>{suggestion_rows}</tbody></table>"
        if suggestion_rows else "")
    load_chart = _hbar_chart([(f"{k} manual step(s)", v, SLATE)
                              for k, v in load_bins.items()])

    focus = sorted(records, key=lambda r: (r.manual, r.copilot_hours or 0),
                   reverse=True)[:10]
    focus_rows = "".join(
        f"<tr><td>{escape(r.mapping)}</td><td>{escape(r.file)}</td>"
        f'<td class="num"><span class="chip" style="color:{GRADE_COLORS.get(r.grade, SLATE)}">{r.score} {r.grade}</span></td>'
        f"<td class='num'>{r.manual}</td>"
        f"<td class='num'>{(r.copilot_hours or 0):.1f}h</td>"
        f"<td class='num'>{_money(r.copilot_hours or 0, rate)}</td></tr>"
        for r in focus)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    from pentaho_migration import __version__

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #22282e; margin: 0; }}
  .page {{ max-width: 900px; margin: 0 auto; padding: 24px 32px 48px; }}
  header.mast {{ background: {NAVY}; color: #fff; padding: 26px 32px; }}
  header.mast h1 {{ margin: 0; font-size: 24px; }}
  header.mast p {{ margin: 6px 0 0; color: {GOLD}; }}
  h2 {{ color: {NAVY}; border-bottom: 2px solid {GOLD}; padding-bottom: 4px; margin-top: 34px; }}
  .cards {{ display: flex; gap: 14px; flex-wrap: wrap; margin-top: 18px; }}
  .kpi {{ flex: 1 1 150px; background: {LIGHT}; border-radius: 10px; padding: 14px 18px; }}
  .kpi b {{ display: block; font-size: 26px; color: {NAVY}; }}
  .kpi.gold b {{ color: {GOLD}; }}
  .kpi span {{ font-size: 12px; color: {SLATE}; }}
  svg .lbl {{ font-size: 12px; fill: #22282e; }}
  svg .val {{ font-size: 12px; fill: {SLATE}; font-weight: bold; }}
  svg .seg {{ font-size: 13px; fill: #fff; font-weight: bold; }}
  .legend {{ margin-top: 8px; font-size: 12.5px; }}
  .legend .key {{ margin-right: 18px; }}
  .legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 10px; }}
  th {{ text-align: left; background: {NAVY}; color: #fff; padding: 7px 9px; }}
  td {{ padding: 6px 9px; border-bottom: 1px solid #dfe5ea; vertical-align: top; }}
  td.num {{ text-align: right; white-space: nowrap; }}
  .chip {{ font-weight: bold; }}
  .muted {{ color: {SLATE}; }}
  footer {{ margin-top: 44px; font-size: 11.5px; color: {SLATE};
            border-top: 1px solid #dfe5ea; padding-top: 10px; }}
  @media print {{ header.mast {{ -webkit-print-color-adjust: exact; }} }}
</style></head><body>
<header class="mast"><h1>{escape(title)}</h1>
<p>{len(records)} mappings · avg confidence {avg_score}/100 · generated {now} · Migration Copilot v{__version__}</p></header>
<div class="page">

<h2>Executive summary</h2>
<div class="cards">
  <div class="kpi"><b>{len(records)}</b><span>mappings batch-converted</span></div>
  <div class="kpi"><b>{avg_score}/100</b><span>average migration confidence</span></div>
  <div class="kpi"><b>{(auto + review) / steps_total:.0%}</b><span>steps mapped mechanically (auto + review)</span></div>
  <div class="kpi"><b>{copilot_h:,.0f}h</b><span>effort with Copilot ({_money(copilot_h, rate)})</span></div>
  <div class="kpi"><b>{manual_h:,.0f}h</b><span>manual rebuild ({_money(manual_h, rate)})</span></div>
  <div class="kpi gold"><b>{_money(saved_h, rate)}</b><span>saved ({saved_h / (manual_h or 1):.0%} · {saved_h:,.0f}h @ ${rate:,.0f}/h)</span></div>
</div>

<h2>Confidence grades</h2>
{grade_bar}

<h2>Step conversion outcome</h2>
<p class="muted">{steps_total} steps across the portfolio — auto converts untouched,
review carries a note, manual has no rules mapping.</p>
{step_bar}

<h2>Remaining manual work by component</h2>
<p class="muted">Source components with no PDI mapping — the consultant's focus
list. {expr_todo} expression(s) also await translation (✨ one click per
mapping in the app).</p>
{unmapped_chart}
{suggestions_html}

<h2>Review load per mapping</h2>
<p class="muted">How many manual steps each mapping carries — the tail is where
the engagement hours live.</p>
{load_chart}

<h2>Focus list — the 10 heaviest mappings</h2>
<table><thead><tr><th>Mapping</th><th>Export</th><th>Score</th><th>Manual steps</th><th>Est. hours</th><th>Est. cost</th></tr></thead>
<tbody>{focus_rows}</tbody></table>

<footer>
Assumptions: hours are the per-mapping Copilot effort estimates (see each
Validate page); rate ${rate:,.0f}/h; grades/steps are deterministic rules
output, no AI. Generated by Pentaho Migration Copilot v{__version__}.
</footer>
</div></body></html>"""
