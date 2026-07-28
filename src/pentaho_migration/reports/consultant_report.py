"""ONE consultant report per migration.

The document a consultant hands over (or works from): what converted, what it
costs, whether the rendered output matches the original, and - per finding -
either the fix or the guidance to resolve it. Composed from pieces that each
already tell the truth:

    conversion report   - the work list (formulas, TODOs, datasource steps)
    effort estimate     - hours and $ vs a manual rebuild
    release check       - rendered original vs rendered conversion (verdict)
    LLM annotations     - resolution-or-guidance per finding (advisory)

Markdown, so it downloads from the app, prints, and diffs in review.
"""

import html as _html
from datetime import datetime

from pentaho_migration.reports.conversion_report import build_conversion_report

NAVY, GOLD, SLATE, LIGHT = "#133346", "#c9a24a", "#5b7185", "#f2f5f7"


PRIORITY_COLOR = {1: "#c0392b", 2: "#c9a24a", 3: "#5b7185"}
PRIORITY_BG = {1: "#fdecea", 2: "#fdf5e3", 3: "#eef2f4"}


def _plan_html(actions, rate, esc):
    """The action plan: the part a consultant actually works from. One row
    per action, priority-ordered, each carrying what it costs and what
    happens if it is skipped."""
    from pentaho_migration.reports.action_plan import PRIORITY_LABEL

    if not actions:
        return ('<p class="clean">Nothing outstanding — this report converts '
                "clean. Open it in Report Designer, point it at the database "
                "and publish.</p>")
    rows = []
    for n, a in enumerate(actions, 1):
        where = ""
        if a.where:
            shown = ", ".join(esc(str(w)) for w in a.where[:6])
            more = f" +{len(a.where) - 6} more" if len(a.where) > 6 else ""
            where = f'<div class="where">{shown}{more}</div>'
        items = ""
        if a.items:
            lis = "".join(f"<li>{esc(str(i))}</li>" for i in a.items[:12])
            extra = (f"<li class='muted'>… and {len(a.items) - 12} more</li>"
                     if len(a.items) > 12 else "")
            items = (f"<details><summary>{len(a.items)} item(s)</summary>"
                     f"<ul>{lis}{extra}</ul></details>")
        rows.append(f"""
<tr class="act">
  <td class="num">{n}</td>
  <td><span class="chip p{a.priority}">{esc(PRIORITY_LABEL[a.priority])}</span></td>
  <td>
    <div class="title">{esc(a.title)}</div>
    <div class="why"><b>Why it matters.</b> {esc(a.why)}</div>
    <div class="how"><b>How.</b> {esc(a.how)}</div>
    {where}{items}
  </td>
  <td class="n">{a.count}</td>
  <td class="n">{a.hours:,.2f}h<div class="muted">${a.hours * rate:,.0f}</div></td>
</tr>""")
    return ("<table class='plan'><tr><th></th><th>Priority</th>"
            "<th>Action</th><th class='n'>Items</th><th class='n'>Effort</th></tr>"
            + "".join(rows) + "</table>")


def _rollup_html(totals, rate, esc):
    from pentaho_migration.reports.action_plan import PRIORITY_LABEL

    cells = []
    for pri in (1, 2, 3):
        n, h = totals.get(pri, (0, 0.0))
        cells.append(
            f'<div class="roll p{pri}"><b>{h:,.2f}h</b>'
            f'<span>{esc(PRIORITY_LABEL[pri])}</span>'
            f'<span class="muted">{n} item(s) · ${h * rate:,.0f}</span></div>')
    return f'<div class="rolls">{"".join(cells)}</div>'


def build_consultant_report_html(model, check=None, rate: float = 150.0) -> str:
    """The per-migration consultant report: a prioritised, costed ACTION PLAN
    first, then the evidence behind it. Self-contained HTML - prints to PDF,
    mails, survives without the app."""
    from pentaho_migration.reports.action_plan import (
        build_action_plan, plan_totals)
    from pentaho_migration.reports.effort import build_report_effort
    from pentaho_migration.reports.todo_kinds import (
        APPLIED, INFO, MANUAL, split_todos)

    esc = _html.escape
    effort = build_report_effort(model)
    copilot_h = getattr(effort, "copilot_hours", 0.0) or 0.0
    manual_h = getattr(effort, "manual_hours", 0.0) or 0.0
    saved_h = max(manual_h - copilot_h, 0.0)
    money = lambda h: f"${h * rate:,.0f}"

    actions = build_action_plan(model, check)
    totals = plan_totals(actions)
    plan_hours = totals["total"][1]
    blockers = totals.get(1, (0, 0.0))[0]

    if check is None or getattr(check, "verdict", "") == "UNAVAILABLE":
        verdict, vclass = "NOT RUN", "vgrey"
        verdict_note = esc(getattr(check, "reason", "") or
                           "the original .rpt or a local render environment "
                           "was not available, so the conversion has not been "
                           "compared against the original")
    elif check.verdict == "SHIP":
        verdict, vclass = "SHIP", "vgreen"
        verdict_note = ("Both reports were rendered and compared - data, "
                        "pagination and the appearance of the pages checked - "
                        "and no difference was found. Evidence, not a proof "
                        "of equivalence.")
    else:
        verdict, vclass = "REVIEW", "vamber"
        verdict_note = (f"{len(check.findings)} difference(s) between the "
                        "rendered conversion and the rendered original. Each "
                        "is listed with its evidence below.")

    # --- evidence: how the two renders compare -------------------------
    pages_html = ""
    if check is not None and getattr(check, "verdict", "") != "UNAVAILABLE":
        spans = ""
        if getattr(check, "groups_checked", 0):
            spans = (f'<div class="ev"><b>{check.groups_matching} of '
                     f"{check.groups_checked}</b><span>group(s) take the same "
                     "<b>number</b> of pages as the original</span></div>")
        if getattr(check, "groups_with_breaks", 0):
            spans += (f'<div class="ev"><b>{check.groups_breaking_alike} of '
                      f"{check.groups_with_breaks}</b><span>multi-page "
                      "group(s) break in the same <b>place</b></span></div>")
        pages_html = (
            '<div class="evs">'
            f'<div class="ev"><b>{check.original_pages}</b><span>pages, '
            "original (SAP Crystal viewer)</span></div>"
            f'<div class="ev"><b>{check.converted_pages}</b><span>pages, '
            "converted (Pentaho engine)</span></div>"
            f"{spans}</div>")

    findings_html = ""
    if check is not None and getattr(check, "findings", None):
        rows = []
        for n, f in enumerate(check.findings, 1):
            sev = {"error": ("✋", "sev1"), "warning": ("⚠", "sev2")}.get(
                f.severity, ("ℹ", "sev3"))
            ev = "".join(f"<li><code>{esc(str(e))}</code></li>"
                         for e in f.evidence[:8])
            resolution = (f'<p class="fix"><b>Resolution.</b> {esc(f.resolution)}</p>'
                          if f.resolution else
                          '<p class="fix muted">No automatic resolution — this '
                          "one needs a consultant's judgement.</p>")
            rows.append(
                f'<div class="finding {sev[1]}"><b>{n}. {sev[0]} '
                f"[{esc(f.code)}]</b> {esc(f.message)}"
                + (f"<ul>{ev}</ul>" if ev else "") + resolution + "</div>")
        findings_html = ("<h2>Evidence — where the renders differ</h2>"
                         + "".join(rows))

    notes = [n for s in model.sections for el in s.elements for n in el.notes]
    notes += model.issues
    buckets = split_todos(notes)
    applied_html = "".join(f"<li>{esc(a)}</li>" for a in buckets[APPLIED][:40])
    info_html = "".join(f"<li>{esc(i)}</li>" for i in buckets[INFO][:40])
    manual_html = "".join(f"<li>{esc(m)}</li>" for m in buckets[MANUAL])

    structure = [("Bands", f"{len(model.sections)}"),
                 ("Elements", f"{sum(len(s.elements) for s in model.sections)}"),
                 ("Groups", f"{len(model.groups)}"),
                 ("Parameters", f"{len(model.parameters)}"),
                 ("Summaries", f"{len(model.summaries)}"),
                 ("Sub-reports", f"{len(model.subreports)}")]
    counts = {"auto": 0, "review": 0, "manual": 0}
    for f in model.formulas.values():
        counts[f.status] = counts.get(f.status, 0) + 1
    structure.append(("Formulas",
                      f"{counts['auto']} translated · {counts['review']} to "
                      f"check · {counts['manual']} to rebuild"))
    structure.append(("Data source", esc(model.jndi or "—")))
    rows_n = len(getattr(getattr(model, "saved_rows", None), "rows", []) or [])
    structure.append(("Embedded rows", f"{rows_n:,}" if rows_n else "none"))
    structure_html = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>"
                             for k, v in structure)

    kinds = {a.kind for a in actions}
    reference_html = _reference_html(kinds, esc)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Consultant Report — {esc(model.name)}</title>
<style>
  :root {{ --navy: {NAVY}; --gold: {GOLD}; --slate: {SLATE}; --light: {LIGHT}; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 15px/1.6 system-ui, "Segoe UI", Roboto, sans-serif;
         color: #17242e; max-width: 1000px; margin: 0 auto 60px;
         padding: 0 22px; background: #fff; }}
  .masthead {{ background: var(--navy); color: #fff; margin: 0 -22px 26px;
               padding: 26px 30px 22px; border-bottom: 4px solid var(--gold); }}
  .masthead h1 {{ margin: 0 0 4px; font-size: 26px; letter-spacing: -.2px; }}
  .masthead p {{ margin: 0; color: #b9c9d4; font-size: 13px; }}
  .badge {{ display: inline-block; float: right; font-weight: 700;
            padding: 7px 16px; border-radius: 999px; font-size: 15px; }}
  .vgreen {{ background: #0f7a34; color: #fff; }}
  .vamber {{ background: var(--gold); color: #2b2107; }}
  .vgrey  {{ background: #48606f; color: #dfe8ee; }}
  h2 {{ color: var(--navy); margin: 34px 0 10px; font-size: 19px;
        border-bottom: 2px solid #e3e9ed; padding-bottom: 6px; }}
  h2 .sub {{ font-weight: 400; font-size: 13px; color: var(--slate); }}
  .lede {{ background: var(--light); border-left: 4px solid var(--gold);
           padding: 12px 16px; border-radius: 0 8px 8px 0; margin: 0 0 18px; }}
  .kpis {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0; }}
  .kpi {{ flex: 1 1 160px; background: var(--light); border-radius: 12px;
          padding: 14px 18px; }}
  .kpi b {{ display: block; font-size: 25px; color: var(--navy);
            line-height: 1.2; }}
  .kpi.gold b {{ color: #8a6d17; }}
  .kpi span {{ font-size: 12px; color: var(--slate); }}
  .rolls {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 14px 0 18px; }}
  .roll {{ flex: 1 1 180px; border-radius: 12px; padding: 12px 16px;
           border: 1px solid #e3e9ed; }}
  .roll b {{ display: block; font-size: 22px; }}
  .roll span {{ display: block; font-size: 12px; color: var(--slate); }}
  .roll.p1 {{ background: {PRIORITY_BG[1]}; }} .roll.p1 b {{ color: {PRIORITY_COLOR[1]}; }}
  .roll.p2 {{ background: {PRIORITY_BG[2]}; }} .roll.p2 b {{ color: #8a6d17; }}
  .roll.p3 {{ background: {PRIORITY_BG[3]}; }} .roll.p3 b {{ color: var(--slate); }}
  .evs {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0 4px; }}
  .ev {{ flex: 1 1 170px; border: 1px solid #e3e9ed; border-radius: 10px;
         padding: 10px 14px; }}
  .ev b {{ display: block; font-size: 20px; color: var(--navy); }}
  .ev span {{ font-size: 12px; color: var(--slate); }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
  th {{ text-align: left; color: var(--slate); font-weight: 600; font-size: 12px;
        text-transform: uppercase; letter-spacing: .4px;
        border-bottom: 2px solid #e3e9ed; padding: 8px; }}
  th.n {{ text-align: right; }}
  td {{ padding: 12px 8px; border-bottom: 1px solid #eef2f4;
        vertical-align: top; }}
  td.n {{ text-align: right; font-variant-numeric: tabular-nums;
          white-space: nowrap; width: 92px; }}
  td.num {{ width: 30px; color: var(--slate); font-weight: 700; }}
  .plan tr.act:hover td {{ background: #fbfcfd; }}
  .plan .title {{ font-weight: 650; color: var(--navy); font-size: 15px;
                  margin-bottom: 3px; }}
  .plan .why, .plan .how {{ font-size: 13.5px; margin: 3px 0; }}
  .plan .how {{ color: #2f4756; }}
  .where {{ font-size: 12px; color: var(--slate); margin-top: 5px;
            font-family: ui-monospace, Consolas, monospace; }}
  .chip {{ display: inline-block; padding: 3px 10px; border-radius: 999px;
           font-size: 11.5px; font-weight: 700; white-space: nowrap; }}
  .chip.p1 {{ background: {PRIORITY_BG[1]}; color: {PRIORITY_COLOR[1]}; }}
  .chip.p2 {{ background: {PRIORITY_BG[2]}; color: #8a6d17; }}
  .chip.p3 {{ background: {PRIORITY_BG[3]}; color: var(--slate); }}
  .finding {{ border-radius: 10px; padding: 12px 16px; margin: 10px 0;
              border-left: 4px solid var(--slate); background: var(--light); }}
  .finding.sev1 {{ border-left-color: {PRIORITY_COLOR[1]}; background: {PRIORITY_BG[1]}; }}
  .finding.sev2 {{ border-left-color: var(--gold); background: {PRIORITY_BG[2]}; }}
  .finding ul {{ margin: 6px 0; }}
  .fix {{ margin: 6px 0 0; }}
  .muted {{ color: var(--slate); }}
  .clean {{ background: #eaf7ee; border-left: 4px solid #0f7a34;
            padding: 12px 16px; border-radius: 0 8px 8px 0; }}
  code {{ background: #fff; padding: 1px 6px; border-radius: 4px;
          font-size: 12.5px; font-family: ui-monospace, Consolas, monospace; }}
  details {{ margin: 8px 0; }}
  summary {{ cursor: pointer; color: var(--slate); font-size: 13px; }}
  .ref dt {{ font-weight: 650; color: var(--navy); margin-top: 10px; }}
  .ref dd {{ margin: 2px 0 0 0; font-size: 13.5px; }}
  footer {{ margin-top: 40px; color: var(--slate); font-size: 12.5px;
            border-top: 2px solid #e3e9ed; padding-top: 12px; }}
  @media print {{
    body {{ max-width: none; }} .masthead {{ margin: 0 0 20px; }}
    tr.act, .finding {{ break-inside: avoid; }}
    details[open] summary ~ * {{ display: block; }}
  }}
</style></head><body>

<div class="masthead">
  <span class="badge {vclass}">{verdict}</span>
  <h1>{esc(model.name)}</h1>
  <p>Consultant report · SAP Crystal Reports → Pentaho Report Designer ·
     generated {datetime.now():%Y-%m-%d %H:%M}</p>
</div>

<p class="lede"><b>{verdict}.</b> {verdict_note}
{"" if not actions else
 f" There {'is 1 action' if len(actions) == 1 else f'are {len(actions)} actions'} "
 f"below, {plan_hours:,.2f}h ({money(plan_hours)}) in total"
 + (f", of which {blockers} item(s) block release." if blockers else ".")}</p>

<div class="kpis">
  <div class="kpi"><b>{plan_hours:,.2f}h</b><span>to finish this report
      ({money(plan_hours)})</span></div>
  <div class="kpi"><b>{manual_h:,.1f}h</b><span>to rebuild it by hand instead
      ({money(manual_h)})</span></div>
  <div class="kpi gold"><b>{money(saved_h)}</b><span>avoided —
      {saved_h / (manual_h or 1):.0%} of a from-scratch rebuild</span></div>
</div>

<h2>Action plan <span class="sub">— highest priority first; within a
    priority, the heaviest first</span></h2>
{_rollup_html(totals, rate, esc)}
{_plan_html(actions, rate, esc)}

<h2>How the two renders compare <span class="sub">— the original through the
    SAP viewer, the conversion through the Pentaho engine</span></h2>
{pages_html or '<p class="muted">Not run — no rendered comparison available.</p>'}

{findings_html}

<h2>What converted</h2>
<table>{structure_html}</table>

{reference_html}

<details><summary>Every remaining note, verbatim ({len(buckets[MANUAL])})</summary>
<ul>{manual_html or "<li>None.</li>"}</ul></details>
<details><summary>Handled automatically ({len(buckets[APPLIED])}) — verify only,
  no action expected</summary><ul>{applied_html or "<li>None.</li>"}</ul></details>
<details><summary>Provenance notes ({len(buckets[INFO])})</summary>
<ul>{info_html or "<li>None.</li>"}</ul></details>

<footer>Conversion and the render comparison are deterministic; any LLM
resolution note is advisory and marked as such. Effort is costed at
${rate:,.0f}/h — change the rate in the app and regenerate. Nothing in this
report is a guess: where the pipeline could not prove a conversion it says so
rather than emitting something that looks right.</footer>
</body></html>"""


_REFERENCE = [
    ("placeholder", "Replacing a TODO placeholder",
     "Insert &gt; Sub-Report for a nested report; Insert &gt; Image for a "
     "picture (the bytes carved from the .rpt travel inside the bundle, so "
     "the image is already there to point at)."),
    ("formula-manual", "Rebuilding a Crystal formula in PRD",
     "Data tab &gt; Functions &gt; Open Formula. Crystal's shared variables "
     "have no direct equivalent — the PRD idiom is a report function "
     "(ItemSumFunction and friends) that accumulates as rows advance."),
    ("suppression", "Conditional suppression",
     "Select the band, then Attributes &gt; style-expression &gt; visible. "
     "PRD's sense is inverted from Crystal's: Crystal asks when to HIDE, PRD "
     "asks when to SHOW."),
    ("summary", "Summaries with no PRD function",
     "Percent-of-total, Nth-largest and the ranked summaries are usually "
     "cheaper to compute in the query as a window function, then bind the "
     "field directly."),
    ("group-sort", "Top-N groups and Others",
     "PRD has no Group Sort Expert. Rank in SQL (ROW_NUMBER() OVER "
     "(ORDER BY SUM(x) DESC)) and UNION an Others row for the tail."),
    ("datasource", "Publishing",
     "File &gt; Publish, or copy the .prpt into the solution repository. The "
     "JNDI name in the bundle must exist on the server — that is the most "
     "common cause of a report that works locally and fails published."),
    ("findings-error", "Comparing against the original",
     "The app's View original button opens the .rpt in the Crystal viewer "
     "while the preview shows the conversion, so both sit side by side at the "
     "same page."),
]


def _reference_html(kinds, esc):
    """A short PRD how-to, limited to the kinds of work THIS report needs -
    a generic cheatsheet is noise."""
    entries = [(t, b) for k, t, b in _REFERENCE if k in kinds]
    if not entries:
        return ""
    body = "".join(f"<dt>{t}</dt><dd>{b}</dd>" for t, b in entries)
    return ("<h2>Doing the work in Report Designer <span class='sub'>— only "
            "the steps this report needs</span></h2>"
            f"<dl class='ref'>{body}</dl>")


_VERDICT_LINE = {
    "SHIP": "**✅ SHIP** — the rendered conversion matches the original.",
    "REVIEW": "**⚠ REVIEW** — differences found; each one is listed below "
              "with a proposed resolution or consultant guidance.",
    "UNAVAILABLE": "**◻ NOT RUN**",
}


def build_consultant_report(model, source_path, prpt_path,
                            check=None) -> str:
    """The consultant report: conversion detail + release verdict + annotated
    findings. `check` is a release_check.ReleaseCheck (or None when the
    environment could not run one)."""
    lines = [f"# Consultant Report: {model.name}", ""]

    if check is None or check.verdict == "UNAVAILABLE":
        reason = getattr(check, "reason", "") or \
            "original .rpt or a local render environment not available"
        lines += ["## Release check", "",
                  f"{_VERDICT_LINE['UNAVAILABLE']} — {reason}.", ""]
    else:
        lines += [
            "## Release check — rendered original vs rendered conversion", "",
            _VERDICT_LINE[check.verdict],
            "",
            f"- Original render: **{check.original_pages} pages** (SAP "
            "Crystal viewer, saved data)",
            f"- Converted render: **{check.converted_pages} pages** "
            "(Pentaho Reporting engine, embedded data)",
            *([f"- Statement pagination: **{check.groups_matching} of "
               f"{check.groups_checked}** group(s) take the same NUMBER of "
               "pages as the original"]
              if getattr(check, "groups_checked", 0) else []),
            *([f"- Page breaks: **{check.groups_breaking_alike} of "
               f"{check.groups_with_breaks}** multi-page group(s) break in "
               "the same PLACE"]
              if getattr(check, "groups_with_breaks", 0) else []),
            ""]
        if check.findings:
            lines += ["### Findings", ""]
            for n, f in enumerate(check.findings, 1):
                icon = {"error": "✋", "warning": "⚠"}.get(f.severity, "ℹ")
                lines.append(f"**{n}. {icon} [{f.code}] {f.message}**")
                for ev in f.evidence[:8]:
                    lines.append(f"   - `{ev}`")
                if f.resolution:
                    lines.append(f"   - **Resolution →** {f.resolution}")
                else:
                    lines.append("   - *No automatic resolution - consultant "
                                 "judgment needed.*")
                lines.append("")
        else:
            lines += ["No differences above threshold.", ""]

    lines += _plan_markdown(model, check)
    lines += ["---", ""]
    lines.append(build_conversion_report(model, source_path, prpt_path))
    return "\n".join(lines)


def _plan_markdown(model, check, rate: float = 150.0) -> list:
    """The same prioritised plan the HTML leads with. Both are generated from
    one function, so the downloaded .md and the .html can never disagree
    about what the work is or what it costs."""
    from pentaho_migration.reports.action_plan import (
        PRIORITY_LABEL, build_action_plan, plan_totals)

    actions = build_action_plan(model, check)
    if not actions:
        return ["## Action plan", "",
                "Nothing outstanding - this report converts clean.", ""]
    totals = plan_totals(actions)
    total_h = totals["total"][1]
    out = ["## Action plan", "",
           f"**{len(actions)} action(s), {total_h:,.2f}h "
           f"(${total_h * rate:,.0f}) in total.** Highest priority first; "
           "within a priority, the heaviest first.", ""]
    for pri in (1, 2, 3):
        if pri in totals:
            n, h = totals[pri]
            out.append(f"- {PRIORITY_LABEL[pri]}: **{h:,.2f}h** "
                       f"(${h * rate:,.0f}) across {n} item(s)")
    out += ["", "| # | Priority | Action | Items | Effort |",
            "|---|---|---|---|---|"]
    for n, a in enumerate(actions, 1):
        out.append(f"| {n} | {PRIORITY_LABEL[a.priority]} | {a.title} | "
                   f"{a.count} | {a.hours:,.2f}h (${a.hours * rate:,.0f}) |")
    out.append("")
    for n, a in enumerate(actions, 1):
        out += [f"### {n}. {a.title}", "",
                f"*{PRIORITY_LABEL[a.priority]} · {a.count} item(s) · "
                f"{a.hours:,.2f}h (${a.hours * rate:,.0f})*", "",
                f"**Why it matters.** {a.why}", "",
                f"**How.** {a.how}", ""]
        if a.where:
            out += ["Where: " + ", ".join(f"`{w}`" for w in a.where[:8]), ""]
        for item in a.items[:12]:
            out.append(f"- {item}")
        if len(a.items) > 12:
            out.append(f"- *… and {len(a.items) - 12} more*")
        out.append("")
    return out
