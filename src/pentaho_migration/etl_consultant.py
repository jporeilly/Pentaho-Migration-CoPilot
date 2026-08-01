"""ONE consultant report per ETL migration (Informatica / Talend).

The document a consultant hands over for a converted mapping: what
converted, what it costs, what the review agent found, and - per
finding - either the fix or the guidance to resolve it. The exact
counterpart of the Crystal per-report consultant document, sharing its
stylesheet, its plan-first structure and its honesty contract:

    migration report    - the step/expression work list
    effort estimate     - hours and $ vs a manual rebuild
    review agent        - deterministic verdict over the converted graph
    LLM annotations     - resolution-or-guidance per finding (advisory)
"""

import html as _html
from dataclasses import dataclass, field
from datetime import datetime

from pentaho_migration.reports.consultant_report import CONSULTANT_CSS
from pentaho_migration.validator.effort import (
    COPILOT_MANUAL_STEP, COPILOT_REVIEW_EXPR, COPILOT_REVIEW_STEP,
    COPILOT_UNTRANSLATED, _vol)

FAMILY_LABELS = {"powercenter": "Informatica PowerCenter",
                 "talend": "Talend", "datastage": "IBM DataStage"}
PRIORITY_LABEL = {1: "Blocks release", 2: "Needed for parity",
                  3: "Verify / polish"}


@dataclass
class EtlAction:
    priority: int
    title: str
    why: str
    how: str
    count: int = 0
    hours: float = 0.0
    where: list = field(default_factory=list)


def _suggestions(pipeline) -> dict:
    from pentaho_migration.mapper import RulesMapper

    try:
        return RulesMapper.for_pipeline(pipeline).suggestions
    except Exception:
        return {}


def build_etl_action_plan(pipeline, check=None) -> list:
    """The prioritised, costed plan - from the pipeline itself plus the
    review agent's findings. Deterministic; hours use the same effort
    constants the estimate panel shows."""
    actions: list[EtlAction] = []

    unmapped: dict = {}
    for step in pipeline.steps:
        if step.pdi_type is None:
            unmapped.setdefault(step.source_type, []).append(step.name)
    suggestions = _suggestions(pipeline) if unmapped else {}
    for source_type, names in sorted(unmapped.items(),
                                     key=lambda kv: -len(kv[1])):
        actions.append(EtlAction(
            priority=1, title=f"Hand-convert {source_type}",
            why=("no PDI mapping exists, so this logic is absent from the "
                 "converted output - the transformation is incomplete "
                 "until it is rebuilt"),
            how=suggestions.get(
                source_type,
                "inspect the component in the source tool and rebuild its "
                "behaviour with PDI steps"),
            count=len(names), hours=_vol(len(names)) * COPILOT_MANUAL_STEP,
            where=names))

    # findings that carry their own work (beyond the unmapped steps)
    for f in (check.findings if check else []):
        if f.code == "sorted-input":
            actions.append(EtlAction(
                priority=1, title="Insert Sort rows upstream of "
                                  "Group By / Merge Join",
                why=("these steps REQUIRE sorted input - unsorted they run "
                     "green and produce silently wrong results, the classic "
                     "migration defect"),
                how=("in Spoon, add a Sort rows step on the group/join keys "
                     "immediately upstream of each listed step"),
                count=len(f.evidence),
                hours=_vol(len(f.evidence)) * COPILOT_REVIEW_STEP,
                where=list(f.evidence)))
        elif f.code == "hops" and f.severity == "error":
            actions.append(EtlAction(
                priority=1, title="Repair the broken hops",
                why="a hop references a step that does not exist - rows "
                    "cannot flow through the break",
                how="re-wire the listed hops in Spoon (or delete them if "
                    "the source tool's diagram carried dead links)",
                count=len(f.evidence), hours=_vol(len(f.evidence)) * 0.2,
                where=list(f.evidence)))
        elif f.code == "sandbox-run" and f.severity == "error":
            actions.append(EtlAction(
                priority=1, title="Fix the Pan load/run failure",
                why="the real engine rejected the converted output - "
                    "nothing downstream matters until it loads",
                how="read the log tail in the findings; the last lines "
                    "name the step and the reason",
                count=1, hours=1.0))
        elif f.code == "parity" and f.severity in ("error", "warning"):
            actions.append(EtlAction(
                priority=1 if f.severity == "error" else 2,
                title="Reconcile the measured output differences",
                why="the converted output does not match the original's "
                    "on the sandbox data - the mismatch samples say where",
                how="work the column list in the parity findings; "
                    "translated expressions and step config are the usual "
                    "suspects",
                count=len(f.evidence) or 1,
                hours=_vol(len(f.evidence) or 1) * COPILOT_REVIEW_STEP,
                where=list(f.evidence)))

    todo_exprs = [(s.name, e.field) for s in pipeline.steps
                  for e in s.expressions if e.translated is None]
    if todo_exprs:
        actions.append(EtlAction(
            priority=2, title="Translate the remaining expressions",
            why="an untranslated expression means the step runs WITHOUT "
                "that logic",
            how="✨ one click in the app translates them all; or port each "
                "by hand (the original source rides in the step notes)",
            count=len(todo_exprs),
            hours=_vol(len(todo_exprs)) * COPILOT_UNTRANSLATED,
            where=[f"{s}.{f_}" for s, f_ in todo_exprs]))

    review_exprs = sum(1 for s in pipeline.steps
                       for e in s.expressions if e.translated is not None)
    if review_exprs:
        actions.append(EtlAction(
            priority=3, title="Verify the translated expressions",
            why="NULL handling differs between the source engine and "
                "JavaScript - a translation can be faithful and still "
                "behave differently on NULL-able inputs",
            how="each translation carries its original as a comment; "
                "compare against rows with NULLs in the sandbox",
            count=review_exprs,
            hours=_vol(review_exprs) * COPILOT_REVIEW_EXPR))

    review_steps = [s.name for s in pipeline.steps
                    if s.pdi_type is not None
                    and s.confidence.value == "review"]
    if review_steps:
        actions.append(EtlAction(
            priority=3, title="Work the review checklist",
            why="these steps converted with an assumption a human should "
                "confirm (sort order, join type, commit sizes, ...)",
            how="the Validate page lists each step's note; tick them off "
                "against the original's settings",
            count=len(review_steps),
            hours=_vol(len(review_steps)) * COPILOT_REVIEW_STEP,
            where=review_steps))

    actions.sort(key=lambda a: (a.priority, -a.hours))
    return actions


def plan_totals(actions) -> dict:
    totals: dict = {}
    for a in actions:
        n, h = totals.get(a.priority, (0, 0.0))
        totals[a.priority] = (n + a.count, h + a.hours)
    totals["total"] = (sum(a.count for a in actions),
                       sum(a.hours for a in actions))
    return totals


def _verdict(check):
    if check is None:
        return ("NOT RUN", "vgrey",
                "the review agent has not been run - the plan below comes "
                "from the conversion itself")
    if check.verdict == "SHIP":
        return ("SHIP", "vgreen",
                "every deterministic check over the converted "
                "transformation passed: no unmapped steps, no untranslated "
                "expressions, the stream is wired, and no sorted-input "
                "hazard. Evidence, not a proof of equivalence - run it "
                "against sandbox data before production.")
    errors = sum(1 for f in check.findings if f.severity == "error")
    return ("REVIEW", "vamber",
            f"{errors} finding(s) block release. Each is listed below with "
            "its evidence and a resolution or the guidance to get there.")


def _findings_html(check, esc) -> str:
    if not check or not check.findings:
        return ""
    rows = []
    for n, f in enumerate(check.findings, 1):
        sev = {"error": ("✋", "sev1"), "warning": ("⚠", "sev2")}.get(
            f.severity, ("ℹ", "sev3"))
        ev = "".join(f"<li><code>{esc(str(e))}</code></li>"
                     for e in f.evidence[:8])
        resolution = (f'<p class="fix"><b>Resolution.</b> '
                      f"{esc(f.resolution)}</p>" if f.resolution else "")
        rows.append(
            f'<div class="finding {sev[1]}"><b>{n}. {sev[0]} '
            f"[{esc(f.code)}]</b> {esc(f.message)}"
            + (f"<ul>{ev}</ul>" if ev else "") + resolution + "</div>")
    return ("<h2>Review findings <span class='sub'>— deterministic checks "
            "over the converted graph; LLM notes are advisory</span></h2>"
            + "".join(rows))


def _plan_html(actions, rate, esc) -> str:
    if not actions:
        return ('<p class="clean">Nothing outstanding — this mapping '
                "converts clean. Open the .ktr in Spoon, point it at the "
                "sandbox connection and run it.</p>")
    rows = []
    for n, a in enumerate(actions, 1):
        where = ""
        if a.where:
            shown = ", ".join(esc(str(w)) for w in a.where[:6])
            more = f" +{len(a.where) - 6} more" if len(a.where) > 6 else ""
            where = f'<div class="where">{shown}{more}</div>'
        rows.append(f"""
<tr class="act">
  <td class="num">{n}</td>
  <td><span class="chip p{a.priority}">{esc(PRIORITY_LABEL[a.priority])}</span></td>
  <td>
    <div class="title">{esc(a.title)}</div>
    <div class="why"><b>Why it matters.</b> {esc(a.why)}</div>
    <div class="how"><b>How.</b> {esc(a.how)}</div>
    {where}
  </td>
  <td class="n">{a.count}</td>
  <td class="n">{a.hours:,.2f}h<div class="muted">${a.hours * rate:,.0f}</div></td>
</tr>""")
    return ("<table class='plan'><tr><th></th><th>Priority</th>"
            "<th>Action</th><th class='n'>Items</th><th class='n'>Effort</th></tr>"
            + "".join(rows) + "</table>")


def _rollup_html(totals, rate, esc) -> str:
    cells = []
    for pri in (1, 2, 3):
        n, h = totals.get(pri, (0, 0.0))
        cells.append(
            f'<div class="roll p{pri}"><b>{h:,.2f}h</b>'
            f'<span>{esc(PRIORITY_LABEL[pri])}</span>'
            f'<span class="muted">{n} item(s) · ${h * rate:,.0f}</span></div>')
    return f'<div class="rolls">{"".join(cells)}</div>'


def build_etl_consultant_report_html(pipeline, report, score, effort,
                                     check=None, rate: float = 150.0,
                                     impact=None) -> str:
    """The per-mapping consultant report: a prioritised, costed ACTION
    PLAN first, then the evidence. Self-contained HTML - prints to PDF,
    mails, survives without the app."""
    esc = _html.escape
    family = FAMILY_LABELS.get(pipeline.source_tool.value,
                               pipeline.source_tool.value.title())
    copilot_h = getattr(effort, "copilot_hours", 0.0) or 0.0
    manual_h = getattr(effort, "manual_hours", 0.0) or 0.0
    saved_h = max(manual_h - copilot_h, 0.0)
    money = lambda h: f"${h * rate:,.0f}"

    actions = build_etl_action_plan(pipeline, check)
    totals = plan_totals(actions)
    plan_hours = totals["total"][1]
    blockers = totals.get(1, (0, 0.0))[0]

    verdict, vclass, verdict_note = _verdict(check)

    checks_html = ""
    if check is not None:
        annotated = sum(1 for f in check.findings if f.resolution)
        cells = (
            f'<div class="ev"><b>{check.steps_checked}</b>'
            "<span>steps checked</span></div>"
            f'<div class="ev"><b>{check.hops_checked}</b>'
            "<span>hops checked</span></div>"
            f'<div class="ev"><b>{len(check.checks_run)}</b><span>'
            f"deterministic check(s): {esc(', '.join(check.checks_run))}"
            "</span></div>")
        if annotated:
            cells += (f'<div class="ev"><b>{annotated}</b><span>finding(s) '
                      "LLM-annotated (advisory)</span></div>")
        checks_html = f'<div class="evs">{cells}</div>'

    counts = {"auto": 0, "review": 0, "manual": 0}
    for s in pipeline.steps:
        counts[s.confidence.value] = counts.get(s.confidence.value, 0) + 1
    exprs_total = sum(len(s.expressions) for s in pipeline.steps)
    exprs_todo = sum(1 for s in pipeline.steps
                     for e in s.expressions if e.translated is None)
    structure = [
        ("Steps", f"{len(pipeline.steps)} — {counts['auto']} auto · "
                  f"{counts['review']} review · {counts['manual']} manual"),
        ("Hops", f"{len(pipeline.hops)}"),
        ("Expressions", f"{exprs_total - exprs_todo} translated · "
                        f"{exprs_todo} to translate"
         if exprs_total else "none"),
        ("Confidence", f"{score.score}/100 (grade {esc(score.grade)})"),
    ]
    structure_html = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>"
                             for k, v in structure)

    risks_html = ""
    top_risks = getattr(getattr(impact, "summary", None), "top_risks", [])
    if top_risks:
        risks_html = ("<h2>Behavioural differences to keep in view</h2><ul>"
                      + "".join(f"<li>{esc(r)}</li>" for r in top_risks)
                      + "</ul>")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Consultant Report — {esc(pipeline.name)}</title>
<style>{CONSULTANT_CSS}</style></head><body>

<div class="masthead">
  <span class="badge {vclass}">{verdict}</span>
  <h1>{esc(pipeline.name)}</h1>
  <p>Consultant report · {esc(family)} → Pentaho Data Integration ·
     generated {datetime.now():%Y-%m-%d %H:%M}</p>
</div>

<p class="lede"><b>{verdict}.</b> {esc(verdict_note)}
{"" if not actions else
 f" There {'is 1 action' if len(actions) == 1 else f'are {len(actions)} actions'} "
 f"below, {plan_hours:,.2f}h ({money(plan_hours)}) in total"
 + (f", of which {blockers} item(s) block release." if blockers else ".")}</p>

<div class="kpis">
  <div class="kpi"><b>{plan_hours:,.2f}h</b><span>to finish this mapping
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

<h2>What the review agent checked</h2>
{checks_html or '<p class="muted">Not run — the plan above comes from the conversion alone.</p>'}

{_findings_html(check, esc)}

<h2>What converted</h2>
<table>{structure_html}</table>

{risks_html}

<footer>Conversion and every review check are deterministic; any LLM
resolution note is advisory and marked as such. Effort is costed at
${rate:,.0f}/h — change the rate in the app and regenerate. Nothing in this
report is a guess: where the pipeline could not prove a conversion it says
so rather than emitting something that looks right.</footer>
</body></html>"""


def build_etl_consultant_report_markdown(pipeline, report, score, effort,
                                         check=None,
                                         rate: float = 150.0) -> str:
    """The same document as Markdown - downloads, prints, diffs in
    review. Generated from the same plan builder as the HTML, so the two
    can never disagree about what the work is or what it costs."""
    family = FAMILY_LABELS.get(pipeline.source_tool.value,
                               pipeline.source_tool.value.title())
    verdict, _cls, verdict_note = _verdict(check)
    actions = build_etl_action_plan(pipeline, check)
    totals = plan_totals(actions)
    total_h = totals["total"][1]

    lines = [f"# Consultant Report: {pipeline.name}", "",
             f"*{family} → Pentaho Data Integration · generated "
             f"{datetime.now():%Y-%m-%d %H:%M}*", "",
             f"**{verdict}** — {verdict_note}", ""]

    lines += ["## Action plan", ""]
    if not actions:
        lines += ["Nothing outstanding - this mapping converts clean.", ""]
    else:
        lines += [f"**{len(actions)} action(s), {total_h:,.2f}h "
                  f"(${total_h * rate:,.0f}) in total.**", "",
                  "| # | Priority | Action | Items | Effort |",
                  "|---|---|---|---|---|"]
        for n, a in enumerate(actions, 1):
            lines.append(f"| {n} | {PRIORITY_LABEL[a.priority]} | {a.title} "
                         f"| {a.count} | {a.hours:,.2f}h "
                         f"(${a.hours * rate:,.0f}) |")
        lines.append("")
        for n, a in enumerate(actions, 1):
            lines += [f"### {n}. {a.title}", "",
                      f"*{PRIORITY_LABEL[a.priority]} · {a.count} item(s) · "
                      f"{a.hours:,.2f}h (${a.hours * rate:,.0f})*", "",
                      f"**Why it matters.** {a.why}", "",
                      f"**How.** {a.how}", ""]
            if a.where:
                lines += ["Where: " + ", ".join(f"`{w}`"
                                                for w in a.where[:8]), ""]

    if check is not None:
        lines += ["## Review findings", "",
                  f"Checks run: {', '.join(check.checks_run)} over "
                  f"{check.steps_checked} step(s) and {check.hops_checked} "
                  "hop(s).", ""]
        if not check.findings:
            lines += ["No findings.", ""]
        for n, f in enumerate(check.findings, 1):
            icon = {"error": "✋", "warning": "⚠"}.get(f.severity, "ℹ")
            lines.append(f"**{n}. {icon} [{f.code}]** {f.message}")
            for ev in f.evidence[:8]:
                lines.append(f"   - `{ev}`")
            if f.resolution:
                lines.append(f"   - **Resolution →** {f.resolution}")
            lines.append("")

    counts = {"auto": 0, "review": 0, "manual": 0}
    for s in pipeline.steps:
        counts[s.confidence.value] = counts.get(s.confidence.value, 0) + 1
    lines += ["## What converted", "",
              f"- Steps: {len(pipeline.steps)} — {counts['auto']} auto · "
              f"{counts['review']} review · {counts['manual']} manual",
              f"- Hops: {len(pipeline.hops)}",
              f"- Confidence: {score.score}/100 (grade {score.grade})",
              f"- Effort: {effort.copilot_hours:,.1f}h with Copilot vs "
              f"{effort.manual_hours:,.1f}h manual rebuild", "",
              "---", "",
              "*Conversion and every review check are deterministic; any "
              "LLM resolution note is advisory and marked as such.*"]
    return "\n".join(lines)
