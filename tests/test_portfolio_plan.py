"""The portfolio report's engagement plan.

A consultant staffs an engagement by KIND of work, not by report, so the
per-report action plans are rolled up here - and each row of the focus list
opens into the full plan for that report. Two things must hold: the roll-up
must add up to the per-report plans it came from, and the page must be
self-contained (it is mailed as one file and opened offline).
"""

import textwrap

from pentaho_migration.reports.action_plan import build_action_plan
from pentaho_migration.reports.portfolio_report import (
    _focus_table, _portfolio_actions, build_portfolio_report_html)
from pentaho_migration.reports.triage import TriageResult, triage_one


def _dump(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _report(name, extra_issue=""):
    return f"""\
<Report Name="{name}" FileName="{name}.rpt">
  <Database><Tables><Table Name="O" Alias="O"><Fields>
    <Field Name="AMT" ValueType="NumberField"/>
  </Fields></Table></Tables></Database>
  <DataDefinition><RecordSelectionFormula/>{extra_issue}</DataDefinition>
  <ReportDefinition><Areas>
    <Area Kind="Detail"><Sections>
      <Section Name="D1" Height="240"><ReportObjects>
        <FieldObject Name="F1" Left="0" Top="0" Width="1440" Height="220"
                     DataSource="{{O.AMT}}"/>
      </ReportObjects></Section>
    </Sections></Area>
  </Areas></ReportDefinition>
</Report>"""


def _triaged(tmp_path, n=3):
    out = []
    for i in range(n):
        dump = _dump(tmp_path, f"r{i}.xml", _report(f"Report{i}"))
        out.append(triage_one(dump, check_sql=False))
    return out


class TestTriageCarriesThePlan:
    def test_triage_captures_each_report_s_actions(self, tmp_path):
        """Built where the model is already parsed - re-parsing the corpus to
        produce the portfolio view would double the wait for numbers already
        computed."""
        result = triage_one(_dump(tmp_path, "r.xml", _report("R")),
                            check_sql=False)
        assert result.actions
        assert all(a.hours > 0 for a in result.actions)

    def test_a_report_that_fails_to_parse_has_no_plan(self, tmp_path):
        """No model, no claims - a broken dump must not contribute invented
        hours to the engagement total."""
        result = triage_one(_dump(tmp_path, "bad.xml", "<not-xml"),
                            check_sql=False)
        assert result.verdict == "BLOCKED"
        assert result.actions == []


class TestRollUp:
    def test_the_rollup_totals_the_per_report_plans(self, tmp_path):
        results = _triaged(tmp_path, 3)
        _table, total = _portfolio_actions(results, 150.0)
        expected = sum(a.hours for r in results for a in r.actions)
        assert round(total, 2) == round(expected, 2)

    def test_one_row_per_kind_of_work_naming_how_many_reports(self, tmp_path):
        results = _triaged(tmp_path, 3)
        table, _ = _portfolio_actions(results, 150.0)
        # three reports all needing the same wiring step = one row, count 3
        assert table.count("Wire up the data source") == 1
        assert ">3<" in table

    def test_an_empty_portfolio_says_nothing_rather_than_zero(self):
        table, total = _portfolio_actions([], 150.0)
        assert table == "" and total == 0.0


class TestFocusListExpands:
    """The focus list already answers "which reports do I open first", so
    each row carries its own plan behind a click rather than a parallel
    section a consultant has to cross-reference."""

    def test_a_row_expands_into_its_full_plan(self, tmp_path):
        results = _triaged(tmp_path, 3)
        for i, r in enumerate(results):      # make the ranking unambiguous
            r.copilot_hours = 10.0 - i
        html = _focus_table(results, 150.0, top_n=2)
        assert 'id="fplan0"' in html and 'id="fplan1"' in html
        assert 'id="fplan2"' not in html
        assert "Why it matters." in html and "How." in html

    def test_every_plan_starts_collapsed(self, tmp_path):
        """Ten expanded plans would bury the table the list exists to be."""
        html = _focus_table(_triaged(tmp_path, 3), 150.0)
        assert 'class="plandetail on"' not in html

    def test_a_report_with_no_plan_is_not_clickable(self):
        html = _focus_table([TriageResult(file="x.xml")], 150.0)
        assert "togglePlan" not in html and "plandetail" not in html

    def test_the_collapsed_row_stays_scannable(self, tmp_path):
        """One clipped reason keeps every row the same height; the full list
        is one click away."""
        results = _triaged(tmp_path, 1)
        results[0].reasons = ["x" * 200, "second", "third"]
        html = _focus_table(results, 150.0)
        assert "x" * 200 not in html
        assert "+2 more" in html


def test_the_whole_page_still_builds(tmp_path):
    html = build_portfolio_report_html(_triaged(tmp_path, 3))
    assert "Priority actions across the portfolio" in html
    assert "function togglePlan" in html
    # self-contained: mailed as one file and opened offline, so nothing may
    # be FETCHED (an xmlns URL is a namespace, not a network request)
    assert "<script src" not in html and "<link" not in html
    assert 'src="http' not in html
    assert html.strip().endswith("</html>")
