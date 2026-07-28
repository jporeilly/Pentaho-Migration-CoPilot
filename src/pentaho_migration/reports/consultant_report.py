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


def build_consultant_report_html(model, check=None, rate: float = 150.0) -> str:
    """The per-migration consultant report in the SAME dress as the Project
    portfolio report: KPI cards up top (verdict, effort hours, $ saved), then
    the release-check findings with their resolutions, then the work list.
    Self-contained HTML - prints to PDF, mails, survives without the app."""
    from pentaho_migration.reports.effort import build_report_effort
    from pentaho_migration.reports.model import is_todo_element
    from pentaho_migration.reports.todo_kinds import MANUAL, split_todos

    esc = _html.escape
    effort = build_report_effort(model)
    copilot_h = getattr(effort, "copilot_hours", 0.0) or 0.0
    manual_h = getattr(effort, "manual_hours", 0.0) or 0.0
    saved_h = max(manual_h - copilot_h, 0.0)
    money = lambda h: f"${h * rate:,.0f}"

    if check is None or check.verdict == "UNAVAILABLE":
        verdict_html = f'<span style="color:{SLATE}">◻ NOT RUN</span>'
        verdict_note = esc(getattr(check, "reason", "") or
                           "original .rpt / render environment not available")
    elif check.verdict == "SHIP":
        verdict_html = '<span style="color:#0ca30c">✅ SHIP</span>'
        verdict_note = "rendered conversion matches the original"
    else:
        verdict_html = f'<span style="color:{GOLD}">⚠ REVIEW</span>'
        verdict_note = (f"{len(check.findings)} finding(s) - each with a "
                        "resolution or guidance below")

    findings_html = ""
    if check is not None and check.findings:
        rows = []
        for n, f in enumerate(check.findings, 1):
            icon = "✋" if f.severity == "error" else "⚠"
            ev = "".join(f"<li><code>{esc(str(e))}</code></li>"
                         for e in f.evidence[:8])
            resolution = (f'<p class="fix">→ {esc(f.resolution)}</p>'
                          if f.resolution else
                          '<p class="fix muted">No automatic resolution - '
                          "consultant judgment needed.</p>")
            rows.append(
                f'<div class="finding"><b>{n}. {icon} [{esc(f.code)}]</b> '
                f"{esc(f.message)}<ul>{ev}</ul>{resolution}</div>")
        findings_html = "<h2>Release-check findings</h2>" + "".join(rows)

    counts = {"auto": 0, "review": 0, "manual": 0}
    for f in model.formulas.values():
        counts[f.status] = counts.get(f.status, 0) + 1
    notes = [n for s in model.sections for el in s.elements for n in el.notes]
    notes += [f"{s.area_kind}: {el.kind}" for s in model.sections
              for el in s.elements if is_todo_element(el)]
    notes += model.issues
    manual_work = split_todos(notes)[MANUAL]
    work_html = ("".join(f"<li>{esc(w)}</li>" for w in manual_work)
                 or "<li>Nothing - every note was handled automatically.</li>")

    pages_html = ""
    if check is not None and check.verdict != "UNAVAILABLE":
        spans = ""
        if getattr(check, "groups_checked", 0):
            spans = (f" · statement pagination: <b>{check.groups_matching} of "
                     f"{check.groups_checked}</b> groups match the original exactly")
        pages_html = (f"<p>Rendered original: <b>{check.original_pages} "
                      f"pages</b> (SAP viewer) · converted: "
                      f"<b>{check.converted_pages} pages</b> (Pentaho engine)"
                      f"{spans}</p>")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Consultant Report — {esc(model.name)}</title>
<style>
  body {{ font: 14px/1.5 system-ui, "Segoe UI", sans-serif; color: #17242e;
         max-width: 900px; margin: 32px auto; padding: 0 20px; }}
  h1 {{ color: {NAVY}; border-bottom: 3px solid {GOLD}; padding-bottom: 8px; }}
  h2 {{ color: {NAVY}; margin-top: 28px; }}
  .kpis {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 18px 0; }}
  .kpi {{ flex: 1 1 150px; background: {LIGHT}; border-radius: 10px; padding: 14px 18px; }}
  .kpi b {{ display: block; font-size: 24px; color: {NAVY}; }}
  .kpi.gold b {{ color: {GOLD}; }}
  .kpi span {{ font-size: 12px; color: {SLATE}; }}
  .finding {{ background: {LIGHT}; border-radius: 10px; padding: 12px 16px; margin: 10px 0; }}
  .finding ul {{ margin: 6px 0; }}
  .fix {{ margin: 6px 0 0; }}
  .muted {{ color: {SLATE}; }}
  code {{ background: #fff; padding: 1px 5px; border-radius: 4px; font-size: 12px; }}
  footer {{ margin-top: 32px; color: {SLATE}; font-size: 12px; }}
</style></head><body>
<h1>Consultant Report — {esc(model.name)}</h1>
<p class="muted">Generated {datetime.now():%Y-%m-%d %H:%M} · Pentaho Migration Copilot</p>
<div class="kpis">
  <div class="kpi"><b>{verdict_html}</b><span>{verdict_note}</span></div>
  <div class="kpi"><b>{copilot_h:,.1f}h</b><span>effort with Copilot ({money(copilot_h)})</span></div>
  <div class="kpi"><b>{manual_h:,.1f}h</b><span>manual rebuild ({money(manual_h)})</span></div>
  <div class="kpi gold"><b>{money(saved_h)}</b><span>saved ({saved_h / (manual_h or 1):.0%} · {saved_h:,.1f}h @ ${rate:,.0f}/h)</span></div>
  <div class="kpi"><b>{counts['auto']}✓ {counts['review']}⚠ {counts['manual']}✋</b><span>formulas auto / review / manual</span></div>
</div>
{pages_html}
{findings_html}
<h2>Remaining manual work</h2>
<ul>{work_html}</ul>
<footer>Deterministic conversion + comparison; LLM notes are advisory.
Open the .prpt in Pentaho Report Designer, resolve the findings, publish to
the Pentaho Server.</footer>
</body></html>"""


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
               f"{check.groups_checked}** group(s) span exactly the same "
               "pages as the original"]
              if getattr(check, "groups_checked", 0) else []),
            ""]
        if check.findings:
            lines += ["### Findings", ""]
            for n, f in enumerate(check.findings, 1):
                icon = "✋" if f.severity == "error" else "⚠"
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

    lines += ["---", ""]
    lines.append(build_conversion_report(model, source_path, prpt_path))
    return "\n".join(lines)
