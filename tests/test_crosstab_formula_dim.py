"""Three failures that stacked up on the BOE income-statement family, each
of which killed a headless render that powers the app's PDF preview and the
release gate. All three were found by loading a real modern report, not by
reasoning about the code.

The report family pivots its columns on {@date} = cdate(Year, Month, 1) - a
date CONSTRUCTED from two columns - and that one design tripped every stage:
the formula translator, the generated ORDER BY, and the crosstab sub-report.
"""

import textwrap
from pathlib import Path

import pytest

from pentaho_migration.reports import load_report_model, write_prpt
from pentaho_migration.reports.formula_translator import translate_formula
from pentaho_migration.reports.rpt_parser import generate_sql


class TestCDateIsArityAware:
    """CDate is dual-form in Crystal: one argument parses a string, three
    CONSTRUCT a date from year, month, day. Mapping it blindly to DATEVALUE
    emitted DATEVALUE(y;m;d), which libformula rejects - 'Invalid number of
    arguments' - failing the whole render."""

    _TYPES = {"Year": "NumberField", "Month": "NumberField"}

    def _out(self, text, field_types=None):
        return translate_formula(
            "f", text, field_types or self._TYPES).translation.lstrip("=")

    def test_three_argument_cdate_constructs_a_date(self):
        assert self._out("cdate({Year}, {Month}, 1)") == "DATE([Year];[Month];1)"

    def test_one_argument_cdate_still_parses(self):
        out = self._out("cdate({d})", {"d": "StringField"})
        assert out.startswith("DATEVALUE(")

    def test_three_argument_datevalue_also_constructs(self):
        assert self._out("datevalue({Year}, {Month}, 1)") == "DATE([Year];[Month];1)"


def _dump(tmp_path, body):
    p = tmp_path / "r.xml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


GROUPED_ON_FORMULA = """\
<Report Name="R" FileName="r.rpt">
  <Database><Tables>
    <Table Name="variance_xtab" Alias="variance_xtab"><Fields>
      <Field Name="Account_Type" LongName="variance_xtab.Account_Type"
             Type="crFieldValueTypeStringField"/>
      <Field Name="Year" LongName="variance_xtab.Year"
             Type="crFieldValueTypeNumberField"/>
      <Field Name="Month" LongName="variance_xtab.Month"
             Type="crFieldValueTypeNumberField"/>
    </Fields></Table>
  </Tables></Database>
  <DataDefinition>
    <RecordSelectionFormula/>
    <FormulaFieldDefinitions>
      <FormulaFieldDefinition FormulaName="{@date}" Name="date"
          ValueType="crFieldValueTypeDateField"
          Text="cdate({variance_xtab.Year}, {variance_xtab.Month}, 1)"/>
    </FormulaFieldDefinitions>
    <Groups>
      <Group Name="G0" ConditionField="{variance_xtab.Account_Type}"/>
      <Group Name="G1" ConditionField="{@date}"/>
    </Groups>
  </DataDefinition>
  <ReportDefinition><Areas>
    <Area Kind="Detail"><Sections><Section Name="D" Height="200">
      <ReportObjects>
        <FieldObject Name="a" Kind="FieldObject" Left="0" Top="0"
            Width="500" Height="200" DataSource="{variance_xtab.Account_Type}"/>
      </ReportObjects>
    </Section></Sections></Area>
  </Areas></ReportDefinition>
</Report>"""


class TestGeneratedOrderByDropsUnresolvableTerms:
    """A group or sort on a formula cannot go into the generated ORDER BY -
    the database has no such column, and 'ORDER BY date' fails the ENTIRE
    query. Dropping the term keeps the report; keeping it loses the report."""

    def test_a_group_on_a_real_column_still_sorts(self, tmp_path):
        model = load_report_model(_dump(tmp_path, GROUPED_ON_FORMULA))
        sql = generate_sql(model)
        assert "ORDER BY" in sql
        assert "Account_Type" in sql.split("ORDER BY")[-1]

    def test_a_group_on_a_formula_is_dropped_from_the_order_by(self, tmp_path):
        model = load_report_model(_dump(tmp_path, GROUPED_ON_FORMULA))
        order = generate_sql(model).split("ORDER BY")[-1]
        assert "date" not in order

    def test_the_dropped_sort_is_reported_not_swallowed(self, tmp_path):
        model = load_report_model(_dump(tmp_path, GROUPED_ON_FORMULA))
        generate_sql(model)
        assert any("computed in the report" in i and "date" in i
                   for i in model.issues)


class TestTheCrosstabDimensionFormulaIsHonest:
    """The cross-tab pivots its columns on that same formula. It cannot come
    out of the query, so the column axis has nothing to spread over and the
    body is empty. That is a real manual step - and it must SAY so, not ship
    a report that renders blank and looks converted.

    Pinned against the real report: the CrossTabObject XML shape is what
    made this fragile in the first place, so a synthetic fixture would be
    testing my guess at it rather than the parser."""

    REPORT = (Path(__file__).resolve().parents[1] / "samples" / "crystal" /
              "corpus" / "ComparativeIncomeStatement.xml")

    def _convert(self, tmp_path):
        model = load_report_model(self.REPORT)
        write_prpt(model, tmp_path / "r.prpt")
        return model

    @pytest.mark.skipif(not REPORT.is_file(), reason="corpus report absent")
    def test_it_is_flagged_as_manual_work(self, tmp_path):
        model = self._convert(tmp_path)
        hits = [i for i in model.issues
                if "pivots on the formula" in i and "date" in i]
        assert hits, "a crosstab pivoting on a formula must be flagged"
        assert "MANUAL" in hits[0]

    @pytest.mark.skipif(not REPORT.is_file(), reason="corpus report absent")
    def test_the_note_names_the_crystal_formula_and_a_recipe(self, tmp_path):
        model = self._convert(tmp_path)
        note = next(i for i in model.issues if "pivots on the formula" in i)
        assert "cdate(" in note              # the actual Crystal source
        assert "SELECT" in note              # what to do about it

    @pytest.mark.skipif(not REPORT.is_file(), reason="corpus report absent")
    def test_the_child_query_does_not_order_by_the_formula(self, tmp_path):
        """The sub-report's own SQL must not carry the term that fails the
        render - that was the 'Unknown column date in order clause' crash."""
        import zipfile
        self._convert(tmp_path)
        sub = zipfile.ZipFile(tmp_path / "r.prpt").read(
            "subreport/datasources/sql-ds.xml").decode()
        order = sub.split("ORDER BY")[-1] if "ORDER BY" in sub else ""
        assert "date" not in order
