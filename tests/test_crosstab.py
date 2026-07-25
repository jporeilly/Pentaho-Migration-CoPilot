"""Cross-tab conversion: CrossTabDefinition parsing, PRD crosstab child
bundle emission, and the honest-TODO path when the definition is absent
(the free SAP .NET SDK cannot export it)."""

import zipfile
from pathlib import Path

from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.prpt_writer import write_prpt

LADDER = Path(__file__).resolve().parents[1] / "samples" / "cr_demo"


def _dump(crosstab_block):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Report Name="XT" FileName="xt.rpt" HasSavedData="False">
<Database><Tables><Table Name="Command" Alias="Command" ClassName="CommandTable">
<ConnectionInfo QE_DatabaseName="db" QE_DatabaseType="PostgreSQL" UserName="" Password=""/>
<Command>SELECT b AS "B", t AS "T", v AS "V" FROM x</Command>
<Fields>
<Field Name="B" ValueType="StringField"/>
<Field Name="T" ValueType="StringField"/>
<Field Name="V" ValueType="CurrencyField"/>
</Fields></Table></Tables></Database>
<DataDefinition><Groups></Groups><SortFields></SortFields>
<FormulaFieldDefinitions></FormulaFieldDefinitions>
<ParameterFieldDefinitions></ParameterFieldDefinitions>
<SummaryFields></SummaryFields></DataDefinition>
<ReportDefinition><Areas>
<Area Kind="ReportHeader" Name="RHArea"><Sections>
<Section Name="RH" Height="3000"><SectionFormat EnableSuppress="false"/>
<ReportObjects>
<CrossTabObject Name="XT1" Left="0" Top="0" Width="8000" Height="2400">
{crosstab_block}
</CrossTabObject>
</ReportObjects></Section></Sections></Area>
</Areas></ReportDefinition></Report>
"""


GOOD_DEF = """<CrossTabDefinition>
<RowFields><Field FieldName="{Command.B}"/></RowFields>
<ColumnFields><Field FieldName="{Command.T}"/></ColumnFields>
<SummaryFields><Field FieldName="{Command.V}" Operation="Sum"/></SummaryFields>
</CrossTabDefinition>"""


def _model(tmp_path, block):
    p = tmp_path / "xt.xml"
    p.write_text(_dump(block), encoding="utf-8")
    return load_report_model(p)


class TestParsing:
    def test_definition_parses_and_resolves(self, tmp_path):
        model = _model(tmp_path, GOOD_DEF)
        (el,) = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
        assert el.crosstab_rows == ["B"]
        assert el.crosstab_columns == ["T"]
        assert el.crosstab_summaries == [("V", "Sum")]

    def test_missing_definition_is_honest_todo_with_instructions(self, tmp_path):
        model = _model(tmp_path, "")
        (el,) = [e for s in model.sections for e in s.elements]
        assert el.kind == "unknown"
        assert "definition not in dump" in el.text
        assert any("CrossTabDefinition" in i for i in model.issues)

    def test_unsupported_operation_downgrades(self, tmp_path):
        block = GOOD_DEF.replace('Operation="Sum"', 'Operation="DistinctCount"')
        model = _model(tmp_path, block)
        (el,) = [e for s in model.sections for e in s.elements]
        assert el.kind == "unknown"
        assert any("DistinctCount" in n for n in el.notes)

    def test_unknown_field_downgrades(self, tmp_path):
        block = GOOD_DEF.replace("{Command.B}", "{Command.NOPE}")
        model = _model(tmp_path, block)
        (el,) = [e for s in model.sections for e in s.elements]
        assert el.kind == "unknown"
        assert any("NOPE" in n for n in el.notes)


class TestWriter:
    def test_crosstab_child_bundle(self, tmp_path):
        model = _model(tmp_path, GOOD_DEF)
        out = tmp_path / "xt.prpt"
        write_prpt(model, out)
        z = zipfile.ZipFile(out)

        child = z.read("subreport/layout.xml").decode()
        # engine-verified structure (tools/CrosstabRef.java reference)
        assert '<crosstab-row-group core:name="B" core:field="B"' in child
        assert '<crosstab-column-group core:name="T" core:field="T"' in child
        assert 'wizard:aggregation-type="Sum (Running)"' in child
        assert 'core:field="V"' in child

        # child SQL must be sorted by row then column dims (crosstab runtime
        # rejects unsorted data)
        ds = z.read("subreport/datasources/sql-ds.xml").decode()
        assert 'ORDER BY "B", "T"' in ds

        # parent hosts the pivot as a sub-report element
        parent = z.read("layout.xml").decode()
        assert 'sub-report href="/subreport/content.xml"' in parent

        # crosstabs need table layouts -> bundle must declare prpt-spec >= 4.0
        meta = z.read("meta.xml").decode()
        assert "prpt-spec.version.major" in meta

        manifest = z.read("META-INF/manifest.xml").decode()
        assert "classic.subreport" in manifest

    def test_banded_report_stays_legacy_mode(self, tmp_path):
        """No crosstab -> no spec declaration: every existing conversion keeps
        the legacy layout mode it was verified under."""
        model = _model(tmp_path, "")  # crosstab downgraded to TODO
        out = tmp_path / "plain.prpt"
        write_prpt(model, out)
        meta = zipfile.ZipFile(out).read("meta.xml").decode()
        assert "prpt-spec.version" not in meta


class TestLadderRung9:
    def test_rung9_converts_to_live_crosstab(self):
        model = load_report_model(LADDER / "09_branch_activity_matrix.xml")
        xt = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
        assert len(xt) == 1
        assert xt[0].crosstab_rows == ["BR_NAME"]
        assert xt[0].crosstab_columns == ["TXN_TYPE"]
        assert xt[0].crosstab_summaries == [("TXN_AMT", "Sum")]

    def test_rung6_pivot_stays_honest_todo(self):
        """Rung 6's cross-tab has NO definition - it demos the manual path."""
        model = load_report_model(LADDER / "06_suspicious_activity.xml")
        assert any("CrossTabDefinition" in i for i in model.issues)
