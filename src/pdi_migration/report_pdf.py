"""PDF migration report — a shareable, printable artifact per mapping.

Built with fpdf2 (pure Python). Core fonts are latin-1, so text is sanitized;
layout mirrors the Validate page: score hero with factor bars, source facts,
warnings, step table, impact highlights.
"""

from fpdf import FPDF

from pdi_migration.ir import Pipeline, SourceInfo

NAVY = (18, 27, 48)
ACCENT = (57, 135, 229)
INK = (25, 25, 25)
MUTED = (110, 110, 110)
TRACK = (225, 224, 217)
GRADE_COLORS = {
    "A": (12, 130, 12), "B": (12, 130, 12), "C": (200, 140, 20),
    "D": (216, 100, 60), "E": (200, 60, 60),
}
CONFIDENCE_COLORS = {"auto": (12, 130, 12), "review": (200, 140, 20), "manual": (200, 60, 60)}
LEVEL_COLORS = {"info": ACCENT, "warning": (200, 140, 20), "serious": (200, 60, 60)}


def _s(text) -> str:
    """Latin-1-safe text for the PDF core fonts."""
    replacements = {"—": "-", "–": "-", "→": "->", "·": "|", "≈": "~", "×": "x", "…": "..."}
    text = str(text)
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


class _ReportPdf(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 8, f"Migration Copilot - page {self.page_no()}/{{nb}}", align="C")


def build_pdf_report(source: SourceInfo | None, pipeline: Pipeline, report, score, impact) -> bytes:
    pdf = _ReportPdf(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    page_width = pdf.w - pdf.l_margin - pdf.r_margin

    # header band
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, pdf.w, 26, style="F")
    pdf.set_xy(pdf.l_margin, 7)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 7, "Migration Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, _s(f"{pipeline.name} - Informatica PowerCenter -> Pentaho Data Integration"))
    pdf.set_y(32)

    # score hero
    grade_color = GRADE_COLORS.get(score.grade, MUTED)
    pdf.set_text_color(*grade_color)
    pdf.set_font("helvetica", "B", 30)
    pdf.cell(34, 14, f"{score.score}/100")
    pdf.set_font("helvetica", "B", 13)
    pdf.cell(26, 14, f"Grade {score.grade}")
    pdf.set_text_color(*MUTED)
    pdf.set_font("helvetica", "I", 9)
    pdf.cell(0, 14, "migration confidence - static prediction", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*INK)
    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(0, 5, _s(score.verdict), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # factor bars
    bar_width = page_width / 2 - 6
    x0, y0 = pdf.l_margin, pdf.get_y()
    for i, factor in enumerate(score.factors):
        x = x0 + (i % 2) * (bar_width + 12)
        y = y0 + (i // 2) * 14
        pdf.set_xy(x, y)
        pdf.set_font("helvetica", "B", 9)
        pdf.set_text_color(*INK)
        pdf.cell(bar_width - 12, 4, _s(factor.name))
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(12, 4, str(factor.score), align="R")
        pdf.set_xy(x, y + 4.5)
        pdf.set_font("helvetica", "", 7.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(bar_width, 3.5, _s(factor.detail))
        pdf.set_fill_color(*TRACK)
        pdf.rect(x, y + 8.6, bar_width, 1.8, style="F")
        pdf.set_fill_color(*ACCENT)
        pdf.rect(x, y + 8.6, bar_width * factor.score / 100, 1.8, style="F")
    pdf.set_y(y0 + ((len(score.factors) + 1) // 2) * 14 + 4)

    # source facts
    if source:
        _heading(pdf, "Source")
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(*INK)
        facts = (
            f"{source.tool} {source.product_version or '?'} (repository {source.repository_version or '?'})  |  "
            f"DB: {source.database_type or '-'}  |  Codepage: {source.codepage or '-'}  |  "
            f"Exported: {source.creation_date or '-'}\n"
            f"Contents: {source.mappings} mappings, {source.workflows} workflows, "
            f"{source.sessions} sessions, {source.mapplets} mapplets"
        )
        pdf.multi_cell(0, 4.6, _s(facts), new_x="LMARGIN", new_y="NEXT")
        for warning in source.warnings:
            pdf.set_text_color(*LEVEL_COLORS.get(warning.level.value, MUTED))
            pdf.set_font("helvetica", "B", 8.5)
            pdf.cell(18, 4.6, _s(warning.level.value.upper()))
            pdf.set_text_color(*INK)
            pdf.set_font("helvetica", "", 8.5)
            pdf.multi_cell(0, 4.6, _s(warning.text), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    # summary numbers
    _heading(pdf, "Summary")
    pdf.set_font("helvetica", "", 9.5)
    pdf.set_text_color(*INK)
    pct = round(report.auto / report.total_steps * 100) if report.total_steps else 0
    pdf.multi_cell(0, 5, _s(
        f"{report.total_steps} steps  |  auto {report.auto} ({pct}%)  |  "
        f"review {report.review}  |  manual {report.manual}  |  "
        f"expressions to translate {report.untranslated_expressions}"
    ), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # step table
    _heading(pdf, "Steps")
    widths = (44, 34, 32, 18, page_width - 128)
    _row(pdf, ("Step", "Source type", "PDI step", "Conf.", "Notes"), widths, header=True)
    for step in pipeline.steps:
        notes = "; ".join([
            *step.notes,
            *(f"{e.field}={e.translated}" if e.translated else f"TODO {e.field}"
              for e in step.expressions),
        ])
        _row(pdf, (
            step.name, step.source_type, step.pdi_type or "-",
            step.confidence.value, notes,
        ), widths, confidence=step.confidence.value)

    # human review checklist — full, untruncated notes per non-auto step
    review_steps = [s for s in pipeline.steps if s.confidence.value != "auto"]
    if review_steps:
        pdf.ln(2)
        _heading(pdf, f"Human review checklist ({len(review_steps)} steps)")
        for step in review_steps:
            pdf.set_font("helvetica", "B", 8.5)
            pdf.set_text_color(*CONFIDENCE_COLORS.get(step.confidence.value, MUTED))
            pdf.cell(16, 4.6, _s(step.confidence.value.upper()))
            pdf.set_text_color(*INK)
            pdf.multi_cell(
                0, 4.6,
                _s(f"{step.name}  ({step.source_type} -> {step.pdi_type or 'no mapping'})"),
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.set_font("helvetica", "", 8)
            pdf.set_text_color(*MUTED)
            for note in step.notes:
                pdf.multi_cell(0, 4.2, _s(f"    - {note}"), new_x="LMARGIN", new_y="NEXT")

    # expressions appendix — every expression with its translation state
    expressions = [(s, e) for s in pipeline.steps for e in s.expressions]
    if expressions:
        pdf.ln(2)
        _heading(pdf, f"Expressions ({len(expressions)})")
        for step, expr in expressions:
            pdf.set_font("helvetica", "B", 8)
            pdf.set_text_color(*INK)
            pdf.multi_cell(0, 4.4, _s(f"{step.name}.{expr.field}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 7.8)
            pdf.set_text_color(*MUTED)
            pdf.multi_cell(0, 4, _s(f"    source ({expr.language}): {expr.raw}"), new_x="LMARGIN", new_y="NEXT")
            if expr.translated is not None:
                pdf.set_text_color(*LEVEL_COLORS["info"])
                pdf.multi_cell(0, 4, _s(f"    PDI (JavaScript): {expr.translated}"), new_x="LMARGIN", new_y="NEXT")
                if expr.notes:
                    pdf.set_text_color(*MUTED)
                    pdf.multi_cell(0, 4, _s(f"    {expr.notes}"), new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.set_text_color(*LEVEL_COLORS["warning"])
                pdf.multi_cell(0, 4, "    NOT TRANSLATED YET", new_x="LMARGIN", new_y="NEXT")

    # impact analysis — top risks, then every high and medium entry in detail
    if impact and (impact.summary.top_risks or impact.summary.high or impact.summary.medium):
        pdf.ln(2)
        _heading(pdf, "Impact analysis")
        pdf.set_font("helvetica", "", 8.5)
        for risk in impact.summary.top_risks:
            pdf.set_text_color(*LEVEL_COLORS["warning"])
            pdf.cell(5, 4.6, "!")
            pdf.set_text_color(*INK)
            pdf.multi_cell(0, 4.6, _s(risk), new_x="LMARGIN", new_y="NEXT")
        for entry in [e for e in impact.entries if e.impact in ("high", "medium")]:
            level_color = LEVEL_COLORS["serious"] if entry.impact == "high" else LEVEL_COLORS["warning"]
            pdf.ln(1)
            pdf.set_font("helvetica", "B", 8.5)
            pdf.set_text_color(*level_color)
            pdf.multi_cell(
                0, 4.6,
                _s(f"[{entry.impact.upper()}] {entry.step} ({entry.source_type} -> {entry.pdi_type or 'no mapping'})"),
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.set_font("helvetica", "", 8)
            pdf.set_text_color(*INK)
            for difference in entry.differences:
                pdf.multi_cell(0, 4.2, _s(f"   difference: {difference}"), new_x="LMARGIN", new_y="NEXT")
            for action in entry.actions:
                pdf.multi_cell(0, 4.2, _s(f"   action: {action}"), new_x="LMARGIN", new_y="NEXT")

    # data flow
    if pipeline.hops:
        pdf.ln(2)
        _heading(pdf, "Data flow")
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(*MUTED)
        for hop in pipeline.hops[:60]:
            pdf.multi_cell(0, 4, _s(f"{hop.from_step}  ->  {hop.to_step}"), new_x="LMARGIN", new_y="NEXT")
        if len(pipeline.hops) > 60:
            pdf.multi_cell(0, 4, _s(f"... and {len(pipeline.hops) - 60} more hops"), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4.2, _s(
        "Review every step marked review or manual before use. Test in a sandbox only - "
        "never against production. Generated by Migration Copilot."
    ), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _heading(pdf: FPDF, text: str) -> None:
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 7, _s(text), new_x="LMARGIN", new_y="NEXT")


def _row(pdf: FPDF, cells, widths, header: bool = False, confidence: str | None = None) -> None:
    pdf.set_font("helvetica", "B" if header else "", 8)
    if header:
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(255, 255, 255)
    else:
        pdf.set_fill_color(247, 247, 245)
        pdf.set_text_color(*INK)
    height = 5.2
    for i, (cell, width) in enumerate(zip(cells, widths)):
        text = _s(cell)
        # crude truncation keeps rows single-line; the full detail lives in the app
        max_chars = int(width / 1.65)
        if len(text) > max_chars:
            text = text[: max_chars - 1] + "..."
        if not header and i == 3 and confidence:
            pdf.set_text_color(*CONFIDENCE_COLORS.get(confidence, MUTED))
        pdf.cell(width, height, text, fill=True)
        if not header:
            pdf.set_text_color(*INK)
    pdf.ln(height)
