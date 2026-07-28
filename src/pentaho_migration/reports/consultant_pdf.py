"""The consultant report as a PDF - the artifact that gets mailed, printed
and attached to a statement of work.

Same content and the same action plan as the HTML (both read
`action_plan.build_action_plan`, so the three formats cannot disagree about
what the work is or what it costs), laid out for paper: a masthead with the
verdict, the effort roll-up, then one block per action carrying why it
matters, how to do it and what it costs.

Built with fpdf2, already a dependency and already the house style for the
Informatica migration report. Core fonts are latin-1, so text is sanitized
on the way in - a stray em-dash otherwise raises mid-render.
"""

from datetime import datetime

from fpdf import FPDF

NAVY = (19, 51, 70)
GOLD = (201, 162, 74)
SLATE = (91, 113, 133)
INK = (23, 36, 46)
LIGHT = (242, 245, 247)
GREEN = (15, 122, 52)
RED = (192, 57, 43)

PRIORITY_INK = {1: RED, 2: (138, 109, 23), 3: SLATE}
PRIORITY_FILL = {1: (253, 236, 234), 2: (253, 245, 227), 3: (238, 242, 244)}

_SUBSTITUTIONS = {
    "—": "-", "–": "-", "→": "->", "·": "|", "≈": "~", "×": "x", "…": "...",
    "“": '"', "”": '"', "‘": "'", "’": "'", "✅": "", "⚠": "!", "✋": "!",
    "ℹ": "i", "◻": "", "≥": ">=", "≤": "<=",
}


def _s(text) -> str:
    """Latin-1-safe text for the PDF core fonts."""
    text = str(text)
    for src, dst in _SUBSTITUTIONS.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


class _ConsultantPdf(FPDF):
    title_text = ""

    def footer(self):
        self.set_y(-12)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(*SLATE)
        self.cell(0, 8, _s(f"{self.title_text} | Pentaho Migration Copilot "
                           f"| page {self.page_no()}/{{nb}}"), align="C")


def _money(hours, rate):
    return f"${hours * rate:,.0f}"


def _kpi_row(pdf, cards, width):
    """Evenly spaced stat cards. Each card is (big value, caption)."""
    gap, n = 4, len(cards)
    w = (width - gap * (n - 1)) / n
    top = pdf.get_y()
    for i, (value, caption, ink) in enumerate(cards):
        x = pdf.l_margin + i * (w + gap)
        pdf.set_xy(x, top)
        pdf.set_fill_color(*LIGHT)
        pdf.rect(x, top, w, 20, style="F")
        pdf.set_xy(x + 4, top + 3)
        pdf.set_font("helvetica", "B", 15)
        pdf.set_text_color(*ink)
        pdf.cell(w - 8, 7, _s(value))
        pdf.set_xy(x + 4, top + 11)
        pdf.set_font("helvetica", "", 7.5)
        pdf.set_text_color(*SLATE)
        pdf.multi_cell(w - 8, 3.4, _s(caption))
    pdf.set_y(top + 24)


def _heading(pdf, text, sub=""):
    pdf.ln(2)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, _s(text), new_x="LMARGIN", new_y="NEXT")
    if sub:
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(*SLATE)
        pdf.cell(0, 4, _s(sub), new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y() + 1
    pdf.set_draw_color(227, 233, 237)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_y(y + 3)


def _wrapped_lines(pdf, text, avail, size, style=""):
    """How many lines `text` takes at this size in `avail` mm. Measured from
    the font metrics rather than guessed from character counts - a guess left
    a third of a page blank before every long action."""
    pdf.set_font("helvetica", style, size)
    width = pdf.get_string_width(_s(text))
    return max(1, int(width / avail) + 1)


def _block_height(pdf, action, width):
    """Height one action block will occupy, so it can be kept whole. An
    action split across a page break loses the link between its cost and the
    steps that earn it."""
    body = width - 4
    height = 9 + 3      # header bar + trailing gap
    for label, text in (("Why it matters. ", action.why), ("How. ", action.how)):
        height += 4.2 * _wrapped_lines(pdf, label + text, body, 8)
    if action.where:
        height += 3.8 * _wrapped_lines(
            pdf, "Where: " + ", ".join(str(w) for w in action.where[:5]),
            body, 7.5, "I")
    for item in action.items[:6]:
        height += 3.8 * _wrapped_lines(pdf, "- " + str(item)[:300],
                                       width - 6, 7.5)
    if len(action.items) > 6:
        height += 3.8
    return height


def _action_block(pdf, n, action, rate, width):
    """One action. Kept together on a page where it fits - an action split
    across a page break loses the link between its cost and its steps."""
    from pentaho_migration.reports.action_plan import PRIORITY_LABEL

    if pdf.get_y() + _block_height(pdf, action, width) > pdf.h - 20:
        pdf.add_page()

    top = pdf.get_y()
    pdf.set_fill_color(*PRIORITY_FILL[action.priority])
    pdf.rect(pdf.l_margin, top, width, 7.5, style="F")
    pdf.set_xy(pdf.l_margin + 2, top + 1)
    pdf.set_font("helvetica", "B", 9)
    pdf.set_text_color(*PRIORITY_INK[action.priority])
    pdf.cell(10, 5.5, _s(f"{n}."))
    pdf.set_text_color(*NAVY)
    pdf.cell(width - 66, 5.5, _s(action.title))
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(*PRIORITY_INK[action.priority])
    pdf.cell(30, 5.5, _s(PRIORITY_LABEL[action.priority]), align="R")
    pdf.set_text_color(*NAVY)
    pdf.set_font("helvetica", "B", 8.5)
    pdf.cell(24, 5.5, _s(f"{action.hours:,.2f}h {_money(action.hours, rate)}"),
             align="R")
    pdf.set_y(top + 9)

    for label, body in (("Why it matters. ", action.why), ("How. ", action.how)):
        pdf.set_x(pdf.l_margin + 2)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(*INK)
        pdf.cell(pdf.get_string_width(_s(label)) + 1, 4.2, _s(label))
        pdf.set_font("helvetica", "", 8)
        pdf.multi_cell(width - 4 - pdf.get_string_width(_s(label)) - 1, 4.2,
                       _s(body), new_x="LMARGIN", new_y="NEXT")
    if action.where:
        shown = ", ".join(str(w) for w in action.where[:5])
        if len(action.where) > 5:
            shown += f" +{len(action.where) - 5} more"
        pdf.set_x(pdf.l_margin + 2)
        pdf.set_font("helvetica", "I", 7.5)
        pdf.set_text_color(*SLATE)
        pdf.multi_cell(width - 4, 3.8, _s("Where: " + shown),
                       new_x="LMARGIN", new_y="NEXT")
    for item in action.items[:6]:
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_font("helvetica", "", 7.5)
        pdf.set_text_color(*SLATE)
        pdf.multi_cell(width - 6, 3.8, _s("- " + str(item)[:300]),
                       new_x="LMARGIN", new_y="NEXT")
    if len(action.items) > 6:
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_font("helvetica", "I", 7.5)
        pdf.cell(0, 3.8, _s(f"... and {len(action.items) - 6} more "
                            "(full list in the HTML report)"),
                 new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def build_consultant_report_pdf(model, check=None, rate: float = 150.0) -> bytes:
    """The consultant report as PDF bytes."""
    from pentaho_migration.reports.action_plan import (
        PRIORITY_LABEL, build_action_plan, plan_totals)
    from pentaho_migration.reports.effort import build_report_effort

    actions = build_action_plan(model, check)
    totals = plan_totals(actions)
    plan_hours = totals["total"][1]
    effort = build_report_effort(model)
    manual_h = getattr(effort, "manual_hours", 0.0) or 0.0
    copilot_h = getattr(effort, "copilot_hours", 0.0) or 0.0
    saved_h = max(manual_h - copilot_h, 0.0)

    if check is None or getattr(check, "verdict", "") == "UNAVAILABLE":
        verdict, vink = "NOT RUN", SLATE
        note = (getattr(check, "reason", "") or
                "the original .rpt or a local render environment was not "
                "available, so the conversion has not been compared against "
                "the original")
    elif check.verdict == "SHIP":
        verdict, vink = "SHIP", GREEN
        note = ("Both reports were rendered and compared: the conversion "
                "matches the original.")
    else:
        verdict, vink = "REVIEW", GOLD
        note = (f"{len(check.findings)} difference(s) between the rendered "
                "conversion and the rendered original, listed with their "
                "evidence below.")

    pdf = _ConsultantPdf(orientation="P", unit="mm", format="A4")
    pdf.title_text = model.name
    pdf.set_title(f"Consultant Report - {model.name}")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    # masthead
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 28, style="F")
    pdf.set_fill_color(*GOLD)
    pdf.rect(0, 28, pdf.w, 1.4, style="F")
    pdf.set_xy(pdf.l_margin, 7)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 15)
    pdf.cell(width - 34, 8, _s(model.name))
    pdf.set_fill_color(*vink)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(34, 8, _s(verdict), align="C", fill=True)
    pdf.set_xy(pdf.l_margin, 16)
    pdf.set_font("helvetica", "", 8.5)
    pdf.set_text_color(185, 201, 212)
    pdf.multi_cell(width, 4.2, _s(
        "Consultant report | SAP Crystal Reports -> Pentaho Report Designer "
        f"| generated {datetime.now():%Y-%m-%d %H:%M}"))
    pdf.set_y(36)

    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(*INK)
    blockers = totals.get(1, (0, 0.0))[0]
    lede = note
    if actions:
        lede += (f" There {'is 1 action' if len(actions) == 1 else f'are {len(actions)} actions'} "
                 f"below, {plan_hours:,.2f}h ({_money(plan_hours, rate)}) in total")
        lede += (f", of which {blockers} item(s) block release."
                 if blockers else ".")
    pdf.multi_cell(width, 4.6, _s(lede), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    _kpi_row(pdf, [
        (f"{plan_hours:,.2f}h",
         f"to finish this report ({_money(plan_hours, rate)})", NAVY),
        (f"{manual_h:,.1f}h",
         f"to rebuild it by hand instead ({_money(manual_h, rate)})", NAVY),
        (_money(saved_h, rate),
         f"avoided - {saved_h / (manual_h or 1):.0%} of a from-scratch "
         "rebuild", (138, 109, 23)),
    ], width)

    _heading(pdf, "Action plan",
             "highest priority first; within a priority, the heaviest first")
    if not actions:
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(*GREEN)
        pdf.multi_cell(width, 5, _s(
            "Nothing outstanding - this report converts clean. Open it in "
            "Report Designer, point it at the database and publish."),
            new_x="LMARGIN", new_y="NEXT")
    else:
        _kpi_row(pdf, [
            (f"{totals.get(p, (0, 0.0))[1]:,.2f}h",
             f"{PRIORITY_LABEL[p]} | {totals.get(p, (0, 0.0))[0]} item(s) | "
             f"{_money(totals.get(p, (0, 0.0))[1], rate)}",
             PRIORITY_INK[p])
            for p in (1, 2, 3)], width)
        for n, action in enumerate(actions, 1):
            _action_block(pdf, n, action, rate, width)

    # how the renders compare
    if check is not None and getattr(check, "verdict", "") != "UNAVAILABLE":
        _heading(pdf, "How the two renders compare",
                 "the original through the SAP viewer, the conversion "
                 "through the Pentaho engine")
        cards = [(f"{check.original_pages}", "pages, original", NAVY),
                 (f"{check.converted_pages}", "pages, converted", NAVY)]
        if getattr(check, "groups_checked", 0):
            cards.append((f"{check.groups_matching} of {check.groups_checked}",
                          "group(s) span the same pages as the original",
                          GREEN if check.groups_matching == check.groups_checked
                          else GOLD))
        _kpi_row(pdf, cards, width)

        if check.findings:
            _heading(pdf, "Evidence - where the renders differ")
            for n, f in enumerate(check.findings, 1):
                if pdf.get_y() > pdf.h - 40:
                    pdf.add_page()
                pdf.set_font("helvetica", "B", 8.5)
                pdf.set_text_color(*{"error": RED, "warning": (138, 109, 23)}
                                   .get(f.severity, SLATE))
                pdf.multi_cell(width, 4.4, _s(f"{n}. [{f.code}] {f.message}"),
                               new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("helvetica", "", 7.5)
                pdf.set_text_color(*SLATE)
                for ev in f.evidence[:6]:
                    pdf.set_x(pdf.l_margin + 3)
                    pdf.multi_cell(width - 3, 3.8, _s("- " + str(ev)[:220]),
                                   new_x="LMARGIN", new_y="NEXT")
                if f.resolution:
                    pdf.set_x(pdf.l_margin + 3)
                    pdf.set_font("helvetica", "I", 7.5)
                    pdf.set_text_color(*INK)
                    pdf.multi_cell(width - 3, 3.8,
                                   _s("Resolution. " + f.resolution),
                                   new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1.5)

    # what converted
    _heading(pdf, "What converted")
    counts = {"auto": 0, "review": 0, "manual": 0}
    for f in model.formulas.values():
        counts[f.status] = counts.get(f.status, 0) + 1
    rows_n = len(getattr(getattr(model, "saved_rows", None), "rows", []) or [])
    facts = [
        ("Bands", str(len(model.sections))),
        ("Elements", str(sum(len(s.elements) for s in model.sections))),
        ("Groups", str(len(model.groups))),
        ("Parameters", str(len(model.parameters))),
        ("Summaries", str(len(model.summaries))),
        ("Sub-reports", str(len(model.subreports))),
        ("Formulas", f"{counts['auto']} translated | {counts['review']} to "
                     f"check | {counts['manual']} to rebuild"),
        ("Data source", model.jndi or "-"),
        ("Embedded rows", f"{rows_n:,}" if rows_n else "none"),
    ]
    for i, (k, v) in enumerate(facts):
        pdf.set_fill_color(*(LIGHT if i % 2 == 0 else (255, 255, 255)))
        pdf.set_font("helvetica", "", 8.5)
        pdf.set_text_color(*SLATE)
        pdf.cell(50, 5.4, _s("  " + k), fill=True)
        pdf.set_text_color(*INK)
        pdf.cell(width - 50, 5.4, _s(v), fill=True, new_x="LMARGIN",
                 new_y="NEXT")

    pdf.ln(4)
    pdf.set_font("helvetica", "I", 7.5)
    pdf.set_text_color(*SLATE)
    pdf.multi_cell(width, 3.8, _s(
        "Conversion and the render comparison are deterministic; any LLM "
        f"resolution note is advisory and marked as such. Effort is costed at "
        f"${rate:,.0f}/h. Nothing in this report is a guess: where the "
        "pipeline could not prove a conversion it says so rather than "
        "emitting something that looks right."), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
