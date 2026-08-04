"""The gate names a PAPER-SIZE mismatch between the two renders.

A Crystal viewer takes its page size from the machine's default printer
when the report asks for DefaultPaperSize, so a reference exported on an
A4 box differs from a Letter conversion in ways that are nobody's
defect. Measured on the statement demo: the footer rule sits 153pt from
the bottom edge in BOTH renders - identical - while its absolute y
differs by the full page-height difference, because page-footer bands
are bottom-anchored. Naming it stops the appearance percentage reading
as a fidelity gap."""

import io

from pentaho_migration.reports.release_check import _paper_finding


def _pdf(width: float, height: float) -> bytes:
    """A one-page PDF of the given point size."""
    from fpdf import FPDF

    pdf = FPDF(unit="pt", format=(width, height))
    pdf.add_page()
    pdf.set_font("helvetica", size=10)
    pdf.cell(0, 12, "x")
    return bytes(pdf.output())


class TestPaperFinding:
    def test_same_paper_says_nothing(self):
        assert _paper_finding(_pdf(612, 792), _pdf(612, 792)) is None

    def test_a4_reference_against_a_letter_conversion_is_named(self):
        f = _paper_finding(_pdf(595, 842), _pdf(612, 792))
        assert f is not None
        assert f.severity == "info"          # the reference's environment
        assert f.code == "paper-size"
        assert "A4" in f.message and "Letter" in f.message
        # it must say WHY it moves content, not just that sizes differ
        assert "bottom edge" in f.message
        assert "clipped" in f.message
        assert any("595" in e for e in f.evidence)

    def test_a_point_of_rounding_still_names_the_sheet(self):
        # A4 comes back 595x841 as often as 595x842
        f = _paper_finding(_pdf(595, 841), _pdf(612, 792))
        assert "A4" in f.message

    def test_the_height_shift_is_quantified(self):
        f = _paper_finding(_pdf(595, 842), _pdf(612, 792))
        assert "50pt" in f.message           # 842 - 792

    def test_an_unknown_sheet_falls_back_to_its_dimensions(self):
        f = _paper_finding(_pdf(500, 700), _pdf(612, 792))
        assert "500x700pt" in f.message

    def test_an_unreadable_pdf_is_silent_not_fatal(self):
        assert _paper_finding(b"not a pdf", _pdf(612, 792)) is None


class TestInTheGate:
    def test_compare_renders_emits_it_without_disturbing_the_verdict(self):
        from pentaho_migration.reports.release_check import compare_renders

        check = compare_renders(_pdf(595, 842), _pdf(612, 792))
        paper = [f for f in check.findings if f.code == "paper-size"]
        assert len(paper) == 1
        # info findings never decide the verdict on their own
        assert not [f for f in check.findings
                    if f.code == "paper-size" and f.severity != "info"]
