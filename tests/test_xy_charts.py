"""The XY chart family (gap #5 of the corpus2 list) + the shared scan.

The old platform's XY collectors moved into PRD's legacy-charts module
with their -Function suffix dropped and two API turns the emitter must
speak: x/y/z column properties introspect CAPITALISED (setXValueColumn
-> "XValueColumn", the JavaBeans two-capitals rule), and the old boolean
seriesColumn ("seriesName[i] holds a column") became the indexed
seriesColumn[i]. The time period is now a Class-valued ``timePeriod``.
Everything here is verified against legacy-charts-11.0.0.0-237.jar's own
metadata; the live-render proof (output/xactions/xy_live_proof.pdf) drew
all five shapes from SampleData rows.

The scan itself is SHARED (jfreereport_functions.build_chart_protos):
the chart-types test solution authors the same expressions in the simple
dialect, so both parsers must translate identically.
"""

import zipfile
from pathlib import Path

import pytest

from pentaho_migration.reports.model import Element, PageSetup, ReportModel, Section
from pentaho_migration.reports.prpt_writer import write_prpt
from pentaho_migration.reports.xaction_parser import build_report_model

CORPUS = (Path(__file__).resolve().parents[1] / "samples" / "xactions"
          / "corpus2" / "breadboard" / "customer_360" / "sales_order_capture"
          / "reporting")
CHART_TYPES_DIR = (Path(__file__).resolve().parents[1] / "samples"
                   / "xactions" / "corpus2" / "pentaho-platform-5.0-OLD"
                   / "test-solution" / "test" / "reporting"
                   / "JFreeReportChartTypes")


def _resolver(base):
    def resolver(name):
        p = base / Path(name).name
        if not p.exists():
            raise FileNotFoundError(name)
        return p.read_bytes()
    return resolver


def _charts(model):
    return [el for s in model.sections for el in s.elements
            if el.kind == "chart"]


def _corpus_model(stem, base=None):
    base = base or CORPUS
    xa = base / f"{stem}.xaction"
    if not xa.exists():
        pytest.skip(f"{stem} not present")
    return build_report_model(xa.read_bytes(), resolver=_resolver(base))


class TestXYCorpusReports:
    def test_xyline_report_carries_both_xy_charts(self):
        charts = _charts(_corpus_model("Sales_Orders_wXYLine"))
        assert [c.chart_type for c in charts] == ["xy-line", "scatter"]
        line = charts[0]
        # seriesColumn=true in the old collector: the series NAME is a
        # data column, not a literal label
        assert line.chart_xy == [{"series_col": "PRODUCT_CATEGORY_NAME",
                                  "x": "AVG_TRXN_PRICE_AMT",
                                  "y": "AVG_TRXN_COST_AMT"}]
        assert line.chart_category_axis_label == "Price"
        assert line.chart_value_axis_label == "Cost"

    def test_bubble_report_carries_z_and_its_size_scale(self):
        chart = _charts(_corpus_model("Sales_Orders_wBubble"))[0]
        assert chart.chart_type == "bubble"
        assert chart.chart_xy[0]["z"] == "MARGIN_AMT"
        # maxBubbleSize defaults to 0 in the PRD class - invisible
        # bubbles - so the authored value must ride along
        assert chart.chart_extra["maxBubbleSize"] == "100.0"

    def test_time_series_report_becomes_an_xy_line(self):
        chart = _charts(_corpus_model("Sales_Orders_wTimeSeriesLine"))[0]
        # TimeSeriesChartExpression did not survive into PRD;
        # XYLineChartExpression over the TimeSeriesCollector did - and is
        # how the corpus's own report is authored
        assert chart.chart_type == "xy-line"
        assert chart.chart_xy[0]["time"] is True
        assert chart.chart_xy[0]["period"] == "Day"
        assert chart.chart_xy[0]["x"] == "ORDER_CAPTURE_DATE"


class TestXYEmission:
    def _bundle_layout(self, tmp_path, chart):
        m = ReportModel()
        m.jndi = "SampleData"
        m.sql = "SELECT 1 AS X FROM INFORMATION_SCHEMA.SYSTEM_USERS"
        m.page = PageSetup()
        sec = Section(area_kind="ReportHeader", name="RH", height=200)
        sec.elements.append(chart)
        m.sections.append(sec)
        out = tmp_path / "xy.prpt"
        write_prpt(m, out)
        return zipfile.ZipFile(out).read("layout.xml").decode()

    def _chart(self, ctype, entries, extra=None):
        el = Element(kind="chart", chart_type=ctype, chart_title="T",
                     x=0, y=0, width=500, height=150)
        el.chart_title_literal = True
        el.chart_xy = entries
        el.chart_value = entries[0]["y"]
        el.chart_category_axis_label = "D"
        el.chart_value_axis_label = "R"
        el.chart_extra = dict(extra or {})
        return el

    def test_xy_line_emits_capitalised_column_props(self, tmp_path):
        layout = self._bundle_layout(tmp_path, self._chart(
            "xy-line", [{"series_col": "S", "x": "XC", "y": "YC"}]))
        assert ("org.pentaho.plugin.jfreereport.reportcharts"
                ".XYLineChartExpression") in layout
        assert "collectors.XYSeriesCollector" in layout
        # setXValueColumn introspects as "XValueColumn" (JavaBeans keeps
        # the name as-is when the first two letters are capitals); the
        # engine rejected the lowercase spelling outright
        assert 'name="XValueColumn[0]">XC<' in layout
        assert 'name="YValueColumn[0]">YC<' in layout
        assert 'name="xValueColumn' not in layout

    def test_series_named_by_column_uses_indexed_seriescolumn(self, tmp_path):
        layout = self._bundle_layout(tmp_path, self._chart(
            "scatter", [{"series_col": "STATUS", "x": "X", "y": "Y"}]))
        assert 'name="seriesColumn[0]">STATUS<' in layout
        assert 'name="seriesName[0]"' not in layout
        assert "ScatterPlotChartExpression" in layout

    def test_literal_series_uses_seriesname(self, tmp_path):
        layout = self._bundle_layout(tmp_path, self._chart(
            "scatter", [{"series": "Orders", "x": "X", "y": "Y"}]))
        assert 'name="seriesName[0]">Orders<' in layout
        assert 'name="seriesColumn[0]"' not in layout

    def test_bubble_emits_xyz_collector_and_size(self, tmp_path):
        layout = self._bundle_layout(tmp_path, self._chart(
            "bubble", [{"series": "S", "x": "X", "y": "Y", "z": "Z"}],
            extra={"maxBubbleSize": "100.0"}))
        assert "collectors.XYZSeriesCollector" in layout
        assert 'name="ZValueColumn[0]">Z<' in layout
        assert 'name="maxBubbleSize">100.0<' in layout

    def test_time_series_emits_class_valued_time_period(self, tmp_path):
        layout = self._bundle_layout(tmp_path, self._chart(
            "xy-line", [{"series_col": "S", "x": "D", "y": "V",
                         "time": True, "period": "Day"}]))
        assert "collectors.TimeSeriesCollector" in layout
        assert 'name="timeValueColumn[0]">D<' in layout
        assert 'name="valueColumn[0]">V<' in layout
        # timePeriod takes a CLASS; the engine's ClassValueConverter
        # resolves the org.jfree.data.time name
        assert 'name="timePeriod">org.jfree.data.time.Day<' in layout

    def test_xy_axis_labels_speak_domain_and_range(self, tmp_path):
        layout = self._bundle_layout(tmp_path, self._chart(
            "xy-line", [{"series": "S", "x": "X", "y": "Y"}]))
        assert 'name="domainTitle">D<' in layout
        assert 'name="rangeTitle">R<' in layout
        assert "categoryAxisLabel" not in layout


class TestSimpleDialectCharts:
    """The chart-types solution authors the SAME expressions in the
    simple dialect - the shared scan must translate them there too."""

    def test_chart_types_xaction_converts_its_multipie_pick(self):
        model = _corpus_model("JFreeReport_Chart_ChartTypes",
                              base=CHART_TYPES_DIR)
        charts = _charts(model)
        assert [c.chart_type for c in charts] == ["multi-pie"]
        assert charts[0].chart_category == "DEPARTMENT"
        assert charts[0].chart_values == [("ACTUAL", "Actual"),
                                          ("BUDGET", "Budget")]
        assert not [i for i in model.issues if "no direct PRD" in i]

    def test_multipie_bundle_carries_the_registered_expression(
            self, tmp_path):
        model = _corpus_model("JFreeReport_Chart_ChartTypes",
                              base=CHART_TYPES_DIR)
        out = tmp_path / "mp.prpt"
        write_prpt(model, out)
        layout = zipfile.ZipFile(out).read("layout.xml").decode()
        assert "MultiPieChartExpression" in layout
        assert "CategorySetDataCollector" in layout

    def test_stacked_alternate_definition_rides_the_stacked_prop(self):
        from pentaho_migration.reports.jfreereport_parser import (
            parse_jfreereport)
        source = CHART_TYPES_DIR / "JFreeReport_Chart_StackedBar.xml"
        if not source.exists():
            pytest.skip("chart-types solution not present")
        model = parse_jfreereport(source.read_bytes())
        chart = _charts(model)[0]
        assert chart.chart_type == "bar"
        assert chart.chart_extra["stacked"] == "true"

    def test_a_drawable_without_its_chart_is_flagged(self):
        from pentaho_migration.reports.jfreereport_parser import (
            parse_jfreereport)
        xml = (b'<report name="d" pageformat="LETTER">'
               b'<reportheader height="100">'
               b'<drawable-field x="0" y="0" fieldname="Ghost" width="100" '
               b'height="50"/></reportheader></report>')
        model = parse_jfreereport(xml)
        els = [e for s in model.sections for e in s.elements]
        assert els and els[0].kind == "unknown"
        assert any("rebuild the drawable" in n for n in els[0].notes)
