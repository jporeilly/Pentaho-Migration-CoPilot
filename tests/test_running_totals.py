"""RunningTotalFieldDefinitions -> group-scoped Item* report functions.
The {#name} references resolve through the same summary machinery as the
WhilePrintingRecords variable rewrite (an Item*Function read mid-detail IS
the running value - live-verified mapping)."""

from pathlib import Path

from pentaho_migration.reports import load_report_model

REAL = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "real"


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
    dump = REAL / "worrallbrian_MostRecentStructuringOfCanadianCities.xml"
    if not dump.exists():
        import pytest
        pytest.skip("corpus not present")
    m = load_report_model(dump)
    els = [e for s in m.sections for e in s.elements
           if (e.field_ref or "").startswith("{#")]
    assert els and all(e.column.startswith("RT_") for e in els)
