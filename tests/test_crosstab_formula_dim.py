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


class TestFormulaToSql:
    """The narrow Crystal-formula -> SQL translation. Only the date-from-parts
    family, because that is what cross-tab dimensions use and a wrong guess
    ships a query that RUNS and returns the wrong columns."""

    from pentaho_migration.reports import formula_sql

    TABLES = {"variance_xtab": {"Year": "NumberField", "Month": "NumberField"}}

    def test_cdate_from_parts_becomes_a_mysql_date(self):
        out = self.formula_sql.formula_to_sql(
            "cdate({variance_xtab.Year}, {variance_xtab.Month}, 1)",
            self.TABLES)
        assert out == ("STR_TO_DATE(CONCAT_WS('-', variance_xtab.Year, "
                       "variance_xtab.Month, 1), '%Y-%c-%e')")

    def test_fields_are_qualified_by_their_owning_table(self):
        out = self.formula_sql.formula_to_sql(
            "date({variance_xtab.Year}, {variance_xtab.Month}, 1)",
            self.TABLES)
        assert "variance_xtab.Year" in out and "variance_xtab.Month" in out

    def test_a_single_argument_parse_is_not_a_construction(self):
        # CDate("2016-01") parses a string - not the 3-arg from-parts form
        assert self.formula_sql.formula_to_sql(
            "cdate({variance_xtab.Year})", self.TABLES) is None

    def test_a_formula_outside_the_family_returns_none(self):
        assert self.formula_sql.formula_to_sql(
            "left({x}, 3)", self.TABLES) is None

    def test_an_unknown_dialect_returns_none(self):
        # never a silent wrong guess for a database we cannot write for
        assert self.formula_sql.formula_to_sql(
            "cdate({variance_xtab.Year}, {variance_xtab.Month}, 1)",
            self.TABLES, dialect="oracle") is None


class TestTheCrosstabDimensionBecomesASqlColumn:
    """A cross-tab pivots over query columns, so a dimension computed in the
    report (the BOE family's {@date} = cdate(Year, Month, 1)) must become a
    real column or the body renders empty. The whole point of #63: compute
    it in the sub-report's SQL so the pivot has something to spread over.

    Pinned against the real report - the CrossTabObject shape is what made
    this fragile, so a synthetic fixture would test my guess at it, not the
    parser."""

    REPORT = (Path(__file__).resolve().parents[1] / "samples" / "crystal" /
              "corpus" / "ComparativeIncomeStatement.xml")

    def _sub_sql(self, tmp_path):
        import zipfile
        model = load_report_model(self.REPORT)
        write_prpt(model, tmp_path / "r.prpt")
        sub = zipfile.ZipFile(tmp_path / "r.prpt").read(
            "subreport/datasources/sql-ds.xml").decode()
        # the XML-escaped SQL, unescaped enough for substring checks
        sql = sub.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        return model, sql

    @pytest.mark.skipif(not REPORT.is_file(), reason="corpus report absent")
    def test_the_formula_dimension_is_selected_as_a_column(self, tmp_path):
        _model, sql = self._sub_sql(tmp_path)
        assert "STR_TO_DATE(" in sql
        assert "AS `date`" in sql             # aliased to the dimension name

    @pytest.mark.skipif(not REPORT.is_file(), reason="corpus report absent")
    def test_the_crosstab_sorts_by_the_computed_expression(self, tmp_path):
        """PRD cross-tabs need rows pre-sorted by their dimensions, and the
        query cannot order by a bare name the database lacks - so it orders
        by the expression itself, which is what fixed the render."""
        _model, sql = self._sub_sql(tmp_path)
        order = sql.split("ORDER BY")[-1]
        assert "STR_TO_DATE(" in order

    @pytest.mark.skipif(not REPORT.is_file(), reason="corpus report absent")
    def test_the_dialect_assumption_is_flagged_for_review(self, tmp_path):
        model, _sql = self._sub_sql(tmp_path)
        note = next((i for i in model.issues
                     if "is computed in the sub-report" in i), None)
        assert note is not None
        assert "mysql" in note                # names the dialect assumed
        assert "cdate(" in note               # and the Crystal source

    @pytest.mark.skipif(not REPORT.is_file(), reason="corpus report absent")
    def test_the_date_column_header_prints_its_month_not_the_iso_value(self, tmp_path):
        """The computed date is a real java.sql.Date, so a text-field header
        prints the raw 2015-01-01. It renders through a date-field formatted
        MMMM yyyy instead - the month the column stands for, as Crystal shows
        it. The date is always the first of a month, so the format is exact."""
        import zipfile
        model = load_report_model(self.REPORT)
        write_prpt(model, tmp_path / "r.prpt")
        layout = zipfile.ZipFile(tmp_path / "r.prpt").read(
            "subreport/layout.xml").decode()
        # the date dimension's header is a date-field with a month format...
        assert 'core:element-type="date-field"' in layout
        assert 'core:format-string="MMMM yyyy"' in layout
        # ...while the Type dimension stays a plain text-field
        assert "text-field" in layout
