"""Crystal's "Underlay Following Sections" cascades a chart under every
following section so a group-summary table prints beside it. PRD can't underlay
across group bands, so the summary's header ends up beside the chart and its
rows below - a disjointed table. The converter STACKS the chart instead so the
summary reads as one compact block, and notes what it did.
"""

from pentaho_migration.reports.model import Element, ReportModel, Section
from pentaho_migration.reports.rpt_parser import resolve_underlay_summary


def _model(sections):
    m = ReportModel()
    m.sections = sections
    return m


def _section(kind, group_index=-1, underlay=False, elements=()):
    s = Section(area_kind=kind, group_index=group_index, underlay=underlay)
    s.elements = list(elements)
    return s


def _noted(model):
    return any("underlay" in i.lower() for i in model.issues)


def test_stacks_the_chart_and_notes_it():
    chart = _section("ReportHeader", underlay=True, elements=[Element(kind="chart")])
    model = _model([chart, _section("GroupFooter", group_index=0,
                                    elements=[Element(kind="field", column="Country")])])
    resolve_underlay_summary(model)
    assert chart.underlay is False        # stacked so the summary stays compact
    assert _noted(model)


def test_no_change_when_there_is_no_group_summary():
    chart = _section("ReportHeader", underlay=True, elements=[Element(kind="chart")])
    model = _model([chart])
    resolve_underlay_summary(model)
    assert chart.underlay is True and not _noted(model)


def test_a_watermark_underlay_without_a_chart_is_left_alone():
    # an image underlay (letterhead / watermark) is reproduced fine - untouched
    wm = _section("ReportHeader", underlay=True, elements=[Element(kind="image")])
    model = _model([wm, _section("GroupFooter", group_index=0,
                                 elements=[Element(kind="field", column="Country")])])
    resolve_underlay_summary(model)
    assert wm.underlay is True and not _noted(model)


def test_a_non_underlay_chart_is_left_alone():
    chart = _section("ReportHeader", underlay=False, elements=[Element(kind="chart")])
    model = _model([chart, _section("GroupFooter", group_index=0,
                                    elements=[Element(kind="field", column="Country")])])
    resolve_underlay_summary(model)
    assert not _noted(model)
