"""Crystal's "Underlay Following Sections" cascades a chart under every
following section so a group-summary table prints beside it. PRD only underlays
the next band, so the summary can flow below the chart. The converter flags
this up front (with the fix) rather than leaving it to the release gate's
after-the-fact visual diff.
"""

from pentaho_migration.reports.model import Element, ReportModel, Section
from pentaho_migration.reports.rpt_parser import flag_underlay_layout


def _model(sections):
    m = ReportModel()
    m.sections = sections
    return m


def _section(kind, group_index=-1, underlay=False, elements=()):
    s = Section(area_kind=kind, group_index=group_index, underlay=underlay)
    s.elements = list(elements)
    return s


def _flagged(model):
    flag_underlay_layout(model)
    return any("underlay" in i.lower() for i in model.issues)


def test_flags_an_underlay_chart_over_a_group_summary():
    model = _model([
        _section("ReportHeader", underlay=True, elements=[Element(kind="chart")]),
        _section("GroupFooter", group_index=0,
                 elements=[Element(kind="field", column="Country")]),
    ])
    assert _flagged(model)


def test_no_flag_when_there_is_no_group_summary():
    model = _model([
        _section("ReportHeader", underlay=True, elements=[Element(kind="chart")]),
    ])
    assert not _flagged(model)


def test_a_watermark_underlay_without_a_chart_does_not_trip_it():
    # an image underlay (letterhead / watermark) is reproduced fine - no flag
    model = _model([
        _section("ReportHeader", underlay=True, elements=[Element(kind="image")]),
        _section("GroupFooter", group_index=0,
                 elements=[Element(kind="field", column="Country")]),
    ])
    assert not _flagged(model)


def test_a_non_underlay_chart_does_not_trip_it():
    model = _model([
        _section("ReportHeader", underlay=False, elements=[Element(kind="chart")]),
        _section("GroupFooter", group_index=0,
                 elements=[Element(kind="field", column="Country")]),
    ])
    assert not _flagged(model)
