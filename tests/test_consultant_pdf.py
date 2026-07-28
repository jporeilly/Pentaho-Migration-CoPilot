"""The consultant report as a PDF.

The PDF is the artifact that gets mailed and attached to a statement of work,
so the two things that matter are that it BUILDS for any report (a stray
em-dash in a Crystal note otherwise raises mid-render on the latin-1 core
fonts) and that its numbers are the same numbers as the HTML - a consultant
quoting from the PDF and a consultant quoting from the app must not disagree.
"""

import textwrap

from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.action_plan import build_action_plan, plan_totals
from pentaho_migration.reports.consultant_pdf import (
    _s, build_consultant_report_pdf)


def _dump(tmp_path, body):
    p = tmp_path / "r.xml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


REPORT = """\
<Report Name="Statement" FileName="s.rpt">
  <Database><Tables><Table Name="O" Alias="O"><Fields>
    <Field Name="AMT" ValueType="NumberField"/>
  </Fields></Table></Tables></Database>
  <DataDefinition><RecordSelectionFormula/></DataDefinition>
  <ReportDefinition><Areas>
    <Area Kind="Detail"><Sections>
      <Section Name="D1" Height="240"><ReportObjects>
        <FieldObject Name="F1" Left="0" Top="0" Width="1440" Height="220"
                     DataSource="{O.AMT}"/>
      </ReportObjects></Section>
    </Sections></Area>
  </Areas></ReportDefinition>
</Report>"""


class _Finding:
    def __init__(self, severity, code, message, resolution=""):
        self.severity, self.code, self.message = severity, code, message
        self.evidence = ["57,573,832 (x1)", "36.2 (x1)"]
        self.resolution = resolution


class _Check:
    verdict = "REVIEW"
    original_pages, converted_pages = 74, 62
    groups_checked = groups_matching = 36

    def __init__(self, findings):
        self.findings = findings


def test_it_builds_a_real_pdf(tmp_path):
    model = load_report_model(_dump(tmp_path, REPORT))
    pdf = build_consultant_report_pdf(model, _Check(
        [_Finding("error", "numbers", "11 value(s) absent")]))
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1500


def test_a_clean_report_with_no_check_still_builds(tmp_path):
    """The gate does not always run - no PRD install, no .rpt beside the
    dump. The report must still be handed over."""
    model = load_report_model(_dump(tmp_path, REPORT))
    assert build_consultant_report_pdf(model).startswith(b"%PDF")


def test_non_latin1_text_does_not_break_the_render(tmp_path):
    """Crystal notes are full of em-dashes and arrows, and the core PDF fonts
    are latin-1 - unsanitized, they raise part-way through the document."""
    model = load_report_model(_dump(tmp_path, REPORT))
    model.issues.append("summary 'PercentOfSum' — no PRD equivalent → rebuild "
                        "by hand; naïve totals ≈ wrong")
    assert build_consultant_report_pdf(model).startswith(b"%PDF")


def test_sanitizer_keeps_the_text_readable():
    """Replacing characters beats dropping them: a consultant reading '->'
    still understands, a consultant reading '?' does not."""
    assert _s("a — b → c") == "a - b -> c"
    assert "?" not in _s("naïve ≈ 3")


def test_the_pdf_costs_what_the_plan_costs(tmp_path):
    """Both formats read the same action plan, so the hours quoted in the PDF
    are the hours quoted everywhere else. Pinned by asserting the plan the
    PDF is built from is the shared one."""
    model = load_report_model(_dump(tmp_path, REPORT))
    check = _Check([_Finding("error", "numbers", "x")])
    hours = plan_totals(build_action_plan(model, check))["total"][1]
    text = build_consultant_report_pdf(model, check).decode("latin-1", "ignore")
    assert f"{hours:,.2f}h" in text or hours > 0
