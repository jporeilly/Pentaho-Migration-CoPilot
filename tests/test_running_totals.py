"""RunningTotalFieldDefinitions -> group-scoped Item* report functions.
The {#name} references resolve through the same summary machinery as the
WhilePrintingRecords variable rewrite (an Item*Function read mid-detail IS
the running value - live-verified mapping)."""

from pathlib import Path

from pentaho_migration.reports import load_report_model

REAL = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "corpus"


def _dump(rt_block):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Report Name="RT" FileName="rt.rpt" HasSavedData="False">
<Database><Tables><Table Name="Command" Alias="Command" ClassName="CommandTable">
<Command>SELECT g AS "G", v AS "V" FROM t</Command>
<Fields><Field Name="G" ValueType="StringField"/><Field Name="V" ValueType="CurrencyField"/></Fields>
</Table></Tables></Database>
<DataDefinition>
<Groups><Group ConditionField="{{Command.G}}"/></Groups>
<SortFields/><FormulaFieldDefinitions/><ParameterFieldDefinitions/>
<RunningTotalFieldDefinitions>{rt_block}</RunningTotalFieldDefinitions>
<SummaryFields/></DataDefinition>
<ReportDefinition><Areas>
<Area Kind="Detail" Name="DArea"><Sections>
<Section Name="D" Height="300"><SectionFormat EnableSuppress="false"/>
<ReportObjects>
<FieldObject Name="RtVal" DataSource="{{#RT1}}" Left="0" Top="0" Width="2000" Height="280"/>
</ReportObjects></Section></Sections></Area>
</Areas></ReportDefinition></Report>
"""


def _load(tmp_path, block):
    p = tmp_path / "rt.xml"
    p.write_text(_dump(block), encoding="utf-8")
    return load_report_model(p)


class TestParsing:
    def test_reset_on_group_becomes_group_scoped_function(self, tmp_path):
        m = _load(tmp_path, (
            '<RunningTotalFieldDefinition Name="RT1" Operation="Sum" '
            'SummarizedField="{Command.V}" EvaluationConditionType="NoCondition" '
            'ResetConditionType="OnChangeOfGroup" ResetCondition="{Command.G}"/>'))
        (rt,) = [s for s in m.summaries if s.name == "RT1"]
        assert (rt.operation, rt.group_field) == ("Sum", "G")
        (el,) = [e for s in m.sections for e in s.elements]
        assert el.kind == "field" and el.column == "RT_RT1"

    def test_engine_entry_without_reset_group_assumes_innermost(self, tmp_path):
        m = _load(tmp_path, (
            '<RunningTotalFieldDefinition Name="RT1" Operation="Sum" '
            'SummarizedField="{Command.V}" EvaluationConditionType="NoCondition" '
            'ResetConditionType="OnChangeOfGroup"/>'))
        (rt,) = [s for s in m.summaries if s.name == "RT1"]
        assert rt.group_field == "G"
        assert any("assumed the innermost group" in i for i in m.issues)

    def test_dedupe_prefers_reset_aware_entry(self, tmp_path):
        m = _load(tmp_path, (
            '<RunningTotalFieldDefinition Name="RT1" Operation="Sum" '
            'SummarizedField="{Command.V}" ResetConditionType="OnChangeOfGroup"/>'
            '<RunningTotalFieldDefinition Name="RT1" Operation="Sum" '
            'SummarizedField="{Command.V}" ResetConditionType="OnChangeOfGroup" '
            'ResetCondition="{Command.G}"/>'))
        (rt,) = [s for s in m.summaries if s.name == "RT1"]
        assert rt.group_field == "G"
        assert not any("assumed" in i for i in m.issues)

    def test_evaluate_condition_stays_honest(self, tmp_path):
        m = _load(tmp_path, (
            '<RunningTotalFieldDefinition Name="RT1" Operation="Sum" '
            'SummarizedField="{Command.V}" EvaluationConditionType="OnFormula" '
            'ResetConditionType="NoCondition"/>'))
        assert not [s for s in m.summaries if s.name == "RT1"]
        assert any("evaluate condition" in i for i in m.issues)


def test_corpus_running_total_resolves():
    """A real corpus report's {#...} reference binds to a generated
    group-scoped report function."""
    dump = REAL / "MostRecentStructuringOfCanadianCities.xml"
    if not dump.exists():
        import pytest
        pytest.skip("corpus not present")
    m = load_report_model(dump)
    els = [e for s in m.sections for e in s.elements
           if (e.field_ref or "").startswith("{#")]
    assert els and all(e.column.startswith("RT_") for e in els)


PERCENT_OF_SUM = """<Report Name="P" FileName="p.rpt">
  <Database><Tables><Table Name="S" Alias="S"><Fields>
    <Field Name="COUNTRY" ValueType="StringField"/>
    <Field Name="AMT" ValueType="NumberField"/>
  </Fields></Table></Tables></Database>
  <DataDefinition>
    <RecordSelectionFormula/>
    <Groups><Group Name="G1" ConditionField="{S.COUNTRY}"/></Groups>
    <SummaryFields>
      <SummaryFieldDefinition Name="PercentOfSum ({S.AMT}, {S.COUNTRY})"
        Operation="Sum" SummarizedField="{S.AMT}" Group="{S.COUNTRY}"/>
    </SummaryFields>
  </DataDefinition>
  <ReportDefinition><Areas>
    <Area Kind="GroupFooter"><Sections>
      <Section Name="GF1" Height="240"><ReportObjects>
        <FieldObject Name="C" Left="0" Top="0" Width="2000" Height="220"
                     DataSource="{S.COUNTRY}"/>
        <FieldObject Name="P" Left="2200" Top="0" Width="2000" Height="220"
                     DataSource="{#PercentOfSum ({S.AMT}, {S.COUNTRY})}"/>
      </ReportObjects></Section>
    </Sections></Area>
  </Areas></ReportDefinition>
</Report>"""


class TestPercentOfSum:
    """Crystal's PercentOfSum divides ONE field across two group SCOPES.
    Emitted as a plain Sum it printed the raw total in a percent column,
    which reads as data rather than as a gap."""

    def _model(self, tmp_path):
        p = tmp_path / "p.xml"
        p.write_text(PERCENT_OF_SUM, encoding="utf-8")
        return load_report_model(p, None)

    def test_the_wider_total_is_recognised(self, tmp_path):
        summary = self._model(tmp_path).summaries[0]
        assert summary.group_field == "COUNTRY"
        assert summary.percent_of == ""      # share of the report total

    def test_three_functions_are_declared(self, tmp_path):
        """The share needs this group's sum, the wider total, and the
        division between them."""
        import zipfile

        from pentaho_migration.reports import write_prpt

        out = tmp_path / "p.prpt"
        write_prpt(self._model(tmp_path), out)
        with zipfile.ZipFile(out) as z:
            dd = z.read("datadefinition.xml").decode("utf-8")
        assert 'name="PercentOfSum_AMT_COUNTRY_part"' in dd
        assert 'name="PercentOfSum_AMT_COUNTRY_whole"' in dd
        assert "[PercentOfSum_AMT_COUNTRY_part] / "                "[PercentOfSum_AMT_COUNTRY_whole] * 100" in dd

    def test_the_note_is_applied_not_manual(self, tmp_path):
        from pentaho_migration.reports.todo_kinds import APPLIED, split_todos

        note = next(i for i in self._model(tmp_path).issues
                    if "percent-of-total" in i)
        assert split_todos([note])[APPLIED] == [note]

    def test_the_engine_computes_the_real_share(self, tmp_path):
        """The construct has to be right in the ENGINE, not just in the XML:
        the built-in quotient function looked like the match and silently
        printed the same percentage on every row."""
        from pentaho_migration.reports import write_prpt
        from pentaho_migration.reports.prpt_validator import (
            render_prpt_pdf_live, validator_available)
        from pentaho_migration.reports.release_check import _pdf_pages_text
        from pentaho_migration.reports.rpt_saved import SavedRows

        if not validator_available():
            pytest.skip("no local PRD install + Java")
        rows = SavedRows(columns=[("COUNTRY", "String"), ("AMT", "Number")],
                         rows=[["A", 250.0], ["A", 250.0], ["B", 500.0]])
        out = tmp_path / "p.prpt"
        write_prpt(self._model(tmp_path), out, saved_rows=rows)
        text = " ".join(_pdf_pages_text(render_prpt_pdf_live(out)))
        # A is 500 of 1000, B is 500 of 1000
        assert "A 50.00" in " ".join(text.split())
        assert "B 50.00" in " ".join(text.split())
