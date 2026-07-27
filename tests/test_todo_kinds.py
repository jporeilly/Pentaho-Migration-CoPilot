"""Sorting conversion notes into real work vs. work already done.

A consultant scopes an engagement off this list, so the split has to be
deterministic and it has to fail safe: a note nobody classified counts as
manual work rather than quietly disappearing.
"""

from pentaho_migration.reports.todo_kinds import (
    APPLIED, INFO, MANUAL, classify_todo, split_todos)


class TestClassification:
    def test_layout_repairs_are_not_work(self):
        """The layout agent already moved these - it is reporting, not asking."""
        assert classify_todo(
            "layout auto-fit: Detail - 2 overlapping text element(s) nudged "
            "apart (right/down, reading order kept) - verify") == APPLIED
        assert classify_todo(
            "layout auto-fit: PageHeader - 7 text box(es) grown to fit their "
            "font (descenders would have clipped); verify nothing now touches") == APPLIED

    def test_things_crystal_can_do_and_prd_cannot_are_work(self):
        assert classify_todo(
            "conditional EnableSuppress formula not carried (section Section2) "
            "(sections merge into one PRD band): drilldowngrouplevel <> 0") == MANUAL
        assert classify_todo(
            "group sort 'Sum ({Customer.Last_Years_Sales})' (TopNOrder) not "
            "carried - order the groups in the query") == MANUAL
        assert classify_todo(
            "summary 'Median (...)' uses operation 'Median', which has no PRD "
            "report-function mapping - rebuild by hand") == MANUAL

    def test_provenance_is_neither(self):
        assert classify_todo(
            "image carved from the .rpt binary and matched by aspect ratio - "
            "verify it is the right picture") == INFO
        assert classify_todo(
            "chart migrated as a PRD legacy chart collecting detail rows - "
            "verify aggregation semantics match the Crystal summary") == INFO

    def test_an_unrecognized_note_counts_as_work(self):
        """Over-report rather than lose it — a dropped note is a surprise on
        the engagement, an extra one is a minute of reading."""
        assert classify_todo("something nobody has seen before") == MANUAL
        assert classify_todo("") == MANUAL


class TestSplit:
    def test_split_keeps_every_note_and_its_order(self):
        notes = [
            "layout auto-fit: Detail - 2 overlapping text element(s) nudged apart",
            "group sort 'X' (TopNOrder) not carried - order in the query",
            "image carved from the .rpt binary and matched by aspect ratio",
            "layout auto-fit: PageHeader - 3 text box(es) grown to fit their font",
        ]
        split = split_todos(notes)
        assert len(split[APPLIED]) == 2
        assert len(split[MANUAL]) == 1
        assert len(split[INFO]) == 1
        assert sum(len(v) for v in split.values()) == len(notes)
        assert split[APPLIED][0].endswith("nudged apart")   # order preserved

    def test_empty_input(self):
        split = split_todos([])
        assert split == {APPLIED: [], MANUAL: [], INFO: []}
