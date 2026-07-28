"""The consultant's action plan: facts turned into prioritised, costed work.

The plan is what a consultant quotes from, so two properties matter more than
any individual rule. It must be DETERMINISTIC - the same report produces the
same plan in the same order every time - and it must never invent work that
the pipeline did not actually find.
"""

import textwrap

import pytest

from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.action_plan import (
    P1, P2, P3, build_action_plan, plan_totals)


def _dump(tmp_path, body):
    p = tmp_path / "r.xml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


CLEAN = """\
<Report Name="Clean" FileName="c.rpt">
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
    def __init__(self, severity, code, message):
        self.severity, self.code, self.message = severity, code, message
        self.evidence, self.resolution = [], ""


class _Check:
    verdict = "REVIEW"
    original_pages = converted_pages = 1
    groups_checked = groups_matching = 0

    def __init__(self, findings):
        self.findings = findings


class TestPriorities:
    def test_a_clean_report_still_names_the_wiring_step(self, tmp_path):
        """Even a perfect conversion is not finished: the data source has to
        be pointed at something real before it publishes."""
        model = load_report_model(_dump(tmp_path, CLEAN))
        actions = build_action_plan(model)
        assert [a.kind for a in actions] == ["datasource"]
        assert actions[0].priority == P2

    def test_render_differences_come_first(self, tmp_path):
        model = load_report_model(_dump(tmp_path, CLEAN))
        check = _Check([_Finding("error", "numbers", "3 values absent"),
                        _Finding("warning", "pages", "page count differs")])
        actions = build_action_plan(model, check)
        assert actions[0].priority == P1
        assert actions[0].kind == "findings-error"
        assert P2 in {a.priority for a in actions}

    def test_the_order_is_stable_across_runs(self, tmp_path):
        """A consultant's estimate must not move because the plan came out in
        a different order today."""
        model = load_report_model(_dump(tmp_path, CLEAN))
        check = _Check([_Finding("error", "numbers", "x"),
                        _Finding("warning", "pages", "y")])
        first = [(a.priority, a.kind, a.hours)
                 for a in build_action_plan(model, check)]
        for _ in range(3):
            assert [(a.priority, a.kind, a.hours)
                    for a in build_action_plan(model, check)] == first

    def test_priority_then_weight_decides_the_order(self, tmp_path):
        model = load_report_model(_dump(tmp_path, CLEAN))
        check = _Check([_Finding("error", "numbers", "x"),
                        _Finding("warning", "pages", "y")])
        actions = build_action_plan(model, check)
        keys = [(a.priority, -a.hours) for a in actions]
        assert keys == sorted(keys)


class TestCosting:
    def test_every_action_carries_hours_and_a_reason(self, tmp_path):
        model = load_report_model(_dump(tmp_path, CLEAN))
        check = _Check([_Finding("error", "numbers", "x")])
        for a in build_action_plan(model, check):
            assert a.hours > 0, a.title
            assert a.why and a.how, a.title

    def test_repeat_items_are_discounted_not_multiplied(self, tmp_path):
        """The second conditional-format fix in a report is not the same job
        as the first; charging full price for each overstates the quote."""
        model = load_report_model(_dump(tmp_path, CLEAN))
        one = build_action_plan(model, _Check(
            [_Finding("error", "numbers", "x")]))[0]
        three = build_action_plan(model, _Check(
            [_Finding("error", "numbers", f"x{i}") for i in range(3)]))[0]
        assert three.hours < one.hours * 3
        assert three.hours > one.hours

    def test_totals_add_up_to_the_actions(self, tmp_path):
        model = load_report_model(_dump(tmp_path, CLEAN))
        check = _Check([_Finding("error", "numbers", "x"),
                        _Finding("warning", "pages", "y")])
        actions = build_action_plan(model, check)
        totals = plan_totals(actions)
        assert totals["total"][1] == pytest.approx(
            sum(a.hours for a in actions), abs=0.01)
        assert totals["total"][0] == sum(a.count for a in actions)


class TestNoInventedWork:
    def test_nothing_is_claimed_that_the_pipeline_did_not_find(self, tmp_path):
        """Every action except the always-present wiring step has to trace
        back to a real note or finding."""
        model = load_report_model(_dump(tmp_path, CLEAN))
        for a in build_action_plan(model):
            assert a.kind == "datasource" or a.items, a.title

    def test_a_note_is_reported_once(self, tmp_path):
        """A note claimed by a specific action must not reappear in the
        catch-all, or the same work gets quoted twice."""
        model = load_report_model(_dump(tmp_path, CLEAN))
        model.issues.append(
            "conditional BackgroundColor formula not carried: whatever")
        actions = build_action_plan(model)
        seen = [i for a in actions for i in a.items]
        assert len(seen) == len(set(seen))
