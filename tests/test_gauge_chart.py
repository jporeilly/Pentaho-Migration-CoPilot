"""Crystal gauge -> PRD thermometer.

PRD has no dial gauge, but its legacy-charts plugin ships a Thermometer -
JFreeChart's meter family - which is what a gauge IS: one value against a
scale with warning/critical sub-ranges. So a gauge converts to a working
thermometer chart rather than a red TODO, flagged as a REVIEW substitution
the consultant approves (a tube is not a dial) or swaps for a KPI field.
"""

import textwrap

from pentaho_migration.reports import load_report_model, write_prpt


def _model(tmp_path, data_fields, style="crChartStyleTypeGauge"):
    dump = f"""\
    <Report Name="G" FileName="g.rpt">
      <Database><Tables><Table Name="T" Alias="T"><Fields>
        <Field Name="EFFICIENCY" ValueType="NumberField"/>
        <Field Name="LATE" ValueType="NumberField"/>
      </Fields></Table></Tables></Database>
      <DataDefinition><RecordSelectionFormula/></DataDefinition>
      <ReportDefinition><Areas>
        <Area Kind="ReportHeader"><Sections><Section Name="RH" Height="2400">
          <ReportObjects>
            <ChartObject Name="G1" Kind="ChartObject" Top="0" Left="0"
                Width="3120" Height="2340">
              <ChartDefinition StyleType="{style}" Title="Order Efficiency">
                <ConditionFields/>
                <DataFields>{data_fields}</DataFields>
              </ChartDefinition>
            </ChartObject>
          </ReportObjects>
        </Section></Sections></Area>
      </Areas></ReportDefinition>
    </Report>"""
    p = tmp_path / "g.xml"
    p.write_text(textwrap.dedent(dump), encoding="utf-8")
    return load_report_model(p)


ONE_VALUE = '<Field FormulaName="{T.EFFICIENCY}" Name="EFFICIENCY"/>'
TWO_VALUES = ('<Field FormulaName="{T.EFFICIENCY}" Name="EFFICIENCY"/>'
              '<Field FormulaName="{T.LATE}" Name="LATE"/>')


class TestGaugeBecomesAThermometer:
    def _chart(self, tmp_path, fields=ONE_VALUE):
        m = _model(tmp_path, fields)
        els = [e for s in m.sections for e in s.elements]
        return m, next(e for e in els if e.kind == "chart")

    def test_a_gauge_is_a_chart_not_a_todo(self, tmp_path):
        _m, chart = self._chart(tmp_path)
        assert chart.chart_type == "thermometer"
        assert chart.chart_value == "EFFICIENCY"

    def test_the_substitution_is_flagged_for_review(self, tmp_path):
        _m, chart = self._chart(tmp_path)
        note = next(n for n in chart.notes if "REVIEW" in n)
        assert "gauge" in note and "thermometer" in note
        assert "approve" in note            # the consultant's call

    def test_a_multi_needle_gauge_says_the_others_are_lost(self, tmp_path):
        _m, chart = self._chart(tmp_path, TWO_VALUES)
        note = next(n for n in chart.notes if "REVIEW" in n)
        assert "2 values" in note and "first" in note

    def test_the_bundle_carries_a_thermometer_expression(self, tmp_path):
        import zipfile
        m = _model(tmp_path, ONE_VALUE)
        out = tmp_path / "g.prpt"
        write_prpt(m, out)
        layout = zipfile.ZipFile(out).read("layout.xml").decode()
        assert "ThermometerChartExpression" in layout
        # fed by the single-value collector, not the category/pie one
        assert "ValueDataSetCollector" in layout
        assert "CategorySetDataCollector" not in layout
        # a KPI meter, so no temperature unit and no legend
        assert 'name="thermometerUnits"' in layout and ">None<" in layout

    def test_an_unmapped_chart_style_still_becomes_a_todo(self, tmp_path):
        """Only the styles we can honestly map convert - an unknown one still
        gets an explicit TODO rather than a silent wrong chart."""
        m = _model(tmp_path, ONE_VALUE, style="crChartStyleTypeRadar")
        els = [e for s in m.sections for e in s.elements]
        assert not [e for e in els if e.kind == "chart"]
        assert any(e.kind == "unknown" for e in els)
