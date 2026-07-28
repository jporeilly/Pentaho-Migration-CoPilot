"""Consultant portfolio report: one self-contained HTML page that turns a
triaged Crystal corpus into an engagement plan — where the effort goes, what
it costs, and which reports to touch first.

Charts are inline SVG (no CDN, works offline, prints to PDF for the customer
meeting). Every number is deterministic: triage verdicts, TODO categories,
review-load distribution, formula success rates, and effort hours priced at
the engagement rate.
"""

from datetime import datetime
from xml.sax.saxutils import escape

NAVY = "#133346"
GOLD = "#c9a24a"
SLATE = "#5b778d"
GOOD = "#0ca30c"
WARN = "#e8a413"
BAD = "#d9534f"
LIGHT = "#eef1f4"

VERDICT_COLORS = {"READY": GOOD, "REVIEW": WARN, "BLOCKED": BAD}


def _hbar_chart(items, width=640, bar_h=26, gap=8, color=SLATE):
    """Horizontal bar chart: items = [(label, value, color|None)]."""
    if not items:
        return "<p class='muted'>none</p>"
    peak = max(v for _, v, _ in items) or 1
    label_w = 260
    rows = []
    for i, (label, value, item_color) in enumerate(items):
        y = i * (bar_h + gap)
        w = max(2, (width - label_w - 60) * value / peak)
        rows.append(
            f'<text x="{label_w - 8}" y="{y + bar_h * 0.7:.0f}" text-anchor="end" '
            f'class="lbl">{escape(str(label))}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w:.0f}" height="{bar_h}" rx="4" '
            f'fill="{item_color or color}"/>'
            f'<text x="{label_w + w + 8:.0f}" y="{y + bar_h * 0.7:.0f}" class="val">{value}</text>')
    height = len(items) * (bar_h + gap)
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'style="max-width:{width}px" xmlns="http://www.w3.org/2000/svg">'
            + "".join(rows) + "</svg>")


def _stacked_bar(parts, width=640, height=34):
    """One stacked bar: parts = [(label, value, color)]. Legend below."""
    total = sum(v for _, v, _ in parts) or 1
    x = 0.0
    segs, legend = [], []
    for label, value, color in parts:
        if value <= 0:
            continue
        w = width * value / total
        segs.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{height}" fill="{color}"/>')
        if w > 46:
            segs.append(
                f'<text x="{x + w / 2:.0f}" y="{height * 0.65:.0f}" text-anchor="middle" '
                f'class="seg">{value}</text>')
        legend.append(
            f'<span class="key"><i style="background:{color}"></i>'
            f"{escape(label)}: <b>{value}</b> ({value / total:.0%})</span>")
        x += w
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" style="max-width:{width}px" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(segs)}</svg>'
            f'<div class="legend">{"".join(legend)}</div>')


def _money(hours, rate):
    return f"${hours * rate:,.0f}"


PRIORITY_INK = {1: BAD, 2: "#8a6d17", 3: SLATE}
PRIORITY_BG = {1: "#fdecea", 2: "#fdf5e3", 3: "#eef2f4"}


def _portfolio_actions(results, rate):
    """The same actions the per-report consultant reports carry, rolled up
    across the corpus: one row per kind of work, with how many reports it
    touches and what the whole lot costs. This is the engagement plan - a
    consultant staffs by kind of work, not by report."""
    from pentaho_migration.reports.action_plan import PRIORITY_LABEL

    rolled: dict = {}
    for r in results:
        for a in getattr(r, "actions", None) or []:
            key = (a.priority, a.title)
            entry = rolled.setdefault(key, {
                "how": a.how, "why": a.why, "reports": 0, "items": 0,
                "hours": 0.0})
            entry["reports"] += 1
            entry["items"] += a.count
            entry["hours"] += a.hours
    if not rolled:
        return "", 0.0
    total = sum(e["hours"] for e in rolled.values())
    rows = []
    for (priority, title), e in sorted(
            rolled.items(), key=lambda kv: (kv[0][0], -kv[1]["hours"])):
        rows.append(
            f'<tr><td><span class="pchip" style="background:'
            f'{PRIORITY_BG[priority]};color:{PRIORITY_INK[priority]}">'
            f'{escape(PRIORITY_LABEL[priority])}</span></td>'
            f'<td><b>{escape(title)}</b><div class="muted">{escape(e["how"])}'
            f"</div></td>"
            f'<td class="num">{e["reports"]}</td>'
            f'<td class="num">{e["items"]}</td>'
            f'<td class="num">{e["hours"]:,.1f}h<div class="muted">'
            f'{_money(e["hours"], rate)}</div></td></tr>')
    table = ("<table><thead><tr><th>Priority</th><th>Work</th>"
             "<th class='num'>Reports</th><th class='num'>Items</th>"
             "<th class='num'>Effort</th></tr></thead><tbody>"
             + "".join(rows) + "</tbody></table>")
    return table, total


def _clip(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _plan_detail(actions, rate):
    """One report's action plan, laid out for the row that expands under it:
    a compact ordered list, each action leading with what it costs."""
    from pentaho_migration.reports.action_plan import PRIORITY_LABEL

    blocks = []
    for a in actions:
        where = ""
        if a.where:
            where = ('<div class="where">Where: '
                     + escape(", ".join(str(w) for w in a.where[:6]))
                     + ("" if len(a.where) <= 6
                        else f" +{len(a.where) - 6} more") + "</div>")
        items = "".join(f"<li>{escape(str(x))}</li>" for x in a.items[:6])
        more = ("" if len(a.items) <= 6 else
                f'<li class="muted">and {len(a.items) - 6} more</li>')
        blocks.append(
            f'<li class="act">'
            f'<div class="acthead">'
            f'<span class="pchip" style="background:{PRIORITY_BG[a.priority]};'
            f'color:{PRIORITY_INK[a.priority]}">'
            f'{escape(PRIORITY_LABEL[a.priority])}</span>'
            f'<b>{escape(a.title)}</b>'
            f'<span class="cost">{a.hours:,.2f}h &middot; {_money(a.hours, rate)}</span>'
            f"</div>"
            f'<p><b>Why it matters.</b> {escape(a.why)}</p>'
            f'<p><b>How.</b> {escape(a.how)}</p>'
            f"{where}"
            + (f"<ul>{items}{more}</ul>" if items else "") + "</li>")
    return f'<ol class="plan">{"".join(blocks)}</ol>'


def _focus_table(results, rate, top_n=10):
    """The heaviest reports, each row expanding into its own action plan.

    The plan lives here rather than in a section of its own: the focus list
    is already the answer to "which reports do I open first", so the detail
    belongs behind the report a consultant just picked, not repeated in a
    parallel list they have to cross-reference."""
    focus = sorted(results, key=lambda r: r.copilot_hours, reverse=True)[:top_n]
    rows = []
    for i, r in enumerate(focus):
        actions = getattr(r, "actions", None) or []
        name = escape(r.name or r.file)
        # the collapsed row is for SCANNING - one clipped reason keeps every
        # row the same height, and the full list is one click away
        reasons = escape(_clip(r.reasons[0], 90) if r.reasons else "-")
        if len(r.reasons) > 1:
            reasons += (f'<span class="muted"> +{len(r.reasons) - 1} more'
                        "</span>")
        rows.append(
            f'<tr class="focus{" clickable" if actions else ""}"'
            + (f' onclick="togglePlan({i})" id="frow{i}"' if actions else "")
            + f'><td><span class="caret">{"&#9656;" if actions else "&nbsp;"}'
              f'</span><span class="fname">{name}</span></td>'
            f'<td><span class="chip" style="color:{VERDICT_COLORS[r.verdict]}">'
            f"{r.verdict}</span></td>"
            f'<td class="num">{r.copilot_hours:.1f}h</td>'
            f'<td class="num">{_money(r.copilot_hours, rate)}</td>'
            f"<td>{reasons}</td></tr>")
        if actions:
            total = sum(a.hours for a in actions)
            rows.append(
                f'<tr class="plandetail" id="fplan{i}"><td colspan="5">'
                f'<p class="muted">{len(actions)} action(s) &middot; '
                f"{total:,.2f}h ({_money(total, rate)}) - highest priority "
                "first</p>"
                + _plan_detail(actions, rate) + "</td></tr>")
    return "".join(rows)


def build_portfolio_report_html(results, rate=150.0, jndi="", title="Crystal Reports Migration — Consultant Portfolio Report"):
    """results: list[TriageResult] (triage_corpus output)."""
    n = len(results) or 1
    verdicts = {"READY": 0, "REVIEW": 0, "BLOCKED": 0}
    todo_kinds: dict = {}
    todo_reports: dict = {}
    load_bins = {"0 (hand over)": 0, "1": 0, "2": 0, "3-5": 0, "6+": 0}
    auto = review = manual = 0
    copilot_h = manual_h = 0.0
    sql_valid = sql_invalid = sql_unchecked = 0

    for r in results:
        verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
        for kind, count in r.todo_kinds.items():
            todo_kinds[kind] = todo_kinds.get(kind, 0) + count
            todo_reports.setdefault(kind, set()).add(r.file)
        reasons = len(r.reasons)
        key = ("0 (hand over)" if reasons == 0 else "1" if reasons == 1
               else "2" if reasons == 2 else "3-5" if reasons <= 5 else "6+")
        load_bins[key] += 1
        auto += r.auto
        review += r.review
        manual += r.manual
        copilot_h += r.copilot_hours
        manual_h += r.manual_hours
        if r.sql_status == "valid":
            sql_valid += 1
        elif r.sql_status == "invalid":
            sql_invalid += 1
        else:
            sql_unchecked += 1

    formulas_total = (auto + review + manual) or 1
    saved_h = manual_h - copilot_h

    verdict_bar = _stacked_bar(
        [(v, verdicts.get(v, 0), VERDICT_COLORS[v]) for v in ("READY", "REVIEW", "BLOCKED")])
    formula_bar = _stacked_bar([
        ("auto", auto, GOOD), ("review", review, WARN), ("manual", manual, BAD)])
    todo_chart = _hbar_chart(sorted(
        ((f"{kind}  ({len(todo_reports[kind])} report(s))", count, GOLD)
         for kind, count in todo_kinds.items()), key=lambda t: -t[1]))
    load_chart = _hbar_chart([(f"{k} review item(s)", v, SLATE)
                              for k, v in load_bins.items()])

    plan_table, plan_total = _portfolio_actions(results, rate)
    plan_money = _money(plan_total, rate)
    focus_rows = _focus_table(results, rate)

    sql_line = ""
    if jndi:
        sql_line = (f"<p>SQL validated against <code>{escape(jndi)}</code>: "
                    f"<b style='color:{GOOD}'>{sql_valid} valid</b> · "
                    f"<b style='color:{BAD}'>{sql_invalid} failing</b> · "
                    f"{sql_unchecked} unchecked (database unreachable — not the report's fault).</p>")

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
  .legend {{ margin-top: 8px; font-size: 12.5px; color: #22282e; }}
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
  .pchip {{ display: inline-block; padding: 2px 9px; border-radius: 999px;
            font-size: 11px; font-weight: bold; white-space: nowrap; }}
  tr.focus.clickable {{ cursor: pointer; }}
  tr.focus.clickable:hover td {{ background: {LIGHT}; }}
  tr.focus.on td {{ background: {LIGHT}; font-weight: bold; }}
  .caret {{ display: inline-block; width: 14px; color: {GOLD};
            font-weight: bold; vertical-align: top; }}
  /* a long report name must wrap BESIDE the caret, not under it */
  .fname {{ display: inline-block; vertical-align: top; word-break: break-word;
            max-width: calc(100% - 18px); }}
  tr.plandetail {{ display: none; }}
  tr.plandetail.on {{ display: table-row; }}
  tr.plandetail > td {{ background: #fbfcfd; padding: 14px 18px 18px;
                        border-bottom: 3px solid {NAVY}; }}
  ol.plan {{ margin: 6px 0 0; padding-left: 22px; }}
  li.act {{ margin: 0 0 16px; }}
  li.act::marker {{ color: {SLATE}; font-weight: bold; }}
  .acthead {{ display: flex; align-items: baseline; gap: 10px;
              flex-wrap: wrap; }}
  .acthead b {{ color: {NAVY}; font-size: 14px; }}
  .acthead .cost {{ margin-left: auto; font-size: 12.5px; font-weight: bold;
                    color: {NAVY}; white-space: nowrap; }}
  li.act p {{ margin: 5px 0 0; font-size: 13px; line-height: 1.5; }}
  li.act ul {{ margin: 6px 0 0; font-size: 12.5px; color: {SLATE};
               padding-left: 18px; }}
  .where {{ font-family: ui-monospace, Consolas, monospace; font-size: 11.5px;
            color: {SLATE}; margin-top: 5px; }}
  @media print {{
    header.mast {{ -webkit-print-color-adjust: exact; }}
    tr.plandetail {{ display: table-row; }}
    .caret {{ display: none; }}
    li.act {{ break-inside: avoid; }}
  }}
</style></head><body>
<header class="mast"><h1>{escape(title)}</h1>
<p>{len(results)} reports triaged · generated {now} · Migration Copilot v{__version__}</p></header>
<div class="page">

<h2>Executive summary</h2>
<div class="cards">
  <div class="kpi"><b>{verdicts['READY']}</b><span>READY — convert &amp; hand over ({verdicts['READY'] / n:.0%})</span></div>
  <div class="kpi"><b>{verdicts['REVIEW']}</b><span>REVIEW — targeted touches needed</span></div>
  <div class="kpi"><b>{verdicts['BLOCKED']}</b><span>BLOCKED — needs unblocking first</span></div>
  <div class="kpi"><b>{copilot_h:,.0f}h</b><span>effort with Copilot ({_money(copilot_h, rate)})</span></div>
  <div class="kpi"><b>{manual_h:,.0f}h</b><span>manual rebuild ({_money(manual_h, rate)})</span></div>
  <div class="kpi gold"><b>{_money(saved_h, rate)}</b><span>saved ({saved_h / (manual_h or 1):.0%} · {saved_h:,.0f}h @ ${rate:,.0f}/h)</span></div>
</div>
{sql_line}

<h2>Migration verdicts</h2>
{verdict_bar}

<h2>Formula translation success</h2>
<p class="muted">{formulas_total} formulas across the portfolio — {(auto + review) / formulas_total:.0%} translate
mechanically (auto + review); only the manual slice needs a rebuild or ✨ LLM assist.</p>
{formula_bar}

<h2>Remaining manual work by category</h2>
<p class="muted">Every TODO placeholder across the portfolio, bucketed — this is the
consultant's focus list. Cross-tabs convert live once the 5-line definition
block is added to the dump; images carve automatically at extraction.</p>
{todo_chart}

<h2>Review load per report</h2>
<p class="muted">How many hand-touches each report needs — the tail is where the
engagement hours live.</p>
{load_chart}

<h2>Priority actions across the portfolio</h2>
<p class="muted">The same actions the per-report consultant reports carry,
rolled up by kind of work — {plan_total:,.1f}h ({plan_money}) in total. Staff
by the rows here; the focus list below tells you where each row lands.</p>
{plan_table}

<h2>Focus list — the 10 heaviest reports</h2>
<p class="muted">Where the engagement hours are. <b>Click a report</b> to open
its full action plan — the same detail its own consultant report carries.</p>
<table class="focuslist"><thead><tr><th>Report</th><th>Verdict</th>
<th class="num">Est. hours</th><th class="num">Est. cost</th>
<th>Top reasons</th></tr></thead>
<tbody>{focus_rows}</tbody></table>
<script>
function togglePlan(i) {{
  var row = document.getElementById('fplan' + i);
  var head = document.getElementById('frow' + i);
  var open = row.className.indexOf('on') >= 0;
  row.className = 'plandetail' + (open ? '' : ' on');
  head.className = 'focus clickable' + (open ? '' : ' on');
  head.querySelector('.caret').innerHTML = open ? '\\u25b8' : '\\u25be';
}}
</script>

<footer>
Assumptions: hours are the per-report Copilot effort estimates (parse-time
heuristics, see each conversion report); rate ${rate:,.0f}/h — adjust with
--rate; verdicts and categories are deterministic triage output, no AI.
Generated by Pentaho Migration Copilot v{__version__}.
</footer>
</div></body></html>"""
