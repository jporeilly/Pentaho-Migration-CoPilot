"""Crystal's date SPECIAL fields keep the format the report authored.

Print date / data date / modification date carry a `DateFieldFormat`
like any other date column, but they have no `value_type` to match on -
so the authored pattern used to be dropped and the render fell back to
a default. The demo statement says "August 04, 2026"; we printed
"Aug 4, 2026". Note the authored pattern CONTAINS A COMMA, which has to
survive PRD's comma-delimited `$(name, type, format)` template - proven
by rendering it through the real engine."""

import textwrap
import zipfile

from pentaho_migration.reports import load_report_model, write_prpt


def _dump(tmp_path, fmt_attr: str, name="PrintDate6"):
    xml = f"""\
    <Report Name="D" FileName="d.rpt">
      <Database><Tables><Table Name="T" Alias="T"><Fields>
        <Field Name="AMOUNT" ValueType="NumberField"/>
      </Fields></Table></Tables></Database>
      <DataDefinition><RecordSelectionFormula/></DataDefinition>
      <ReportDefinition><Areas>
        <Area Kind="ReportHeader"><Sections><Section Name="RH" Height="400">
          <ReportObjects>
            <FieldObject Name="{name}" Kind="FieldObject" Top="0" Left="0"
                Width="2000" Height="300" DataSource="PrintDate">
              <FieldFormat>{fmt_attr}</FieldFormat>
            </FieldObject>
          </ReportObjects>
        </Section></Sections></Area>
      </Areas></ReportDefinition>
    </Report>"""
    p = tmp_path / "d.xml"
    p.write_text(textwrap.dedent(xml), encoding="utf-8")
    return load_report_model(p)


LONG = ('<DateFieldFormat DayFormat="LeadingZeroNumericDay" '
        'MonthFormat="LongMonth" YearFormat="LongYear" '
        'FormatString="MMMM dd, yyyy" />')


class TestAuthoredFormatSurvives:
    def test_the_parser_promotes_a_special_date_format(self, tmp_path):
        model = _dump(tmp_path, LONG)
        el = next(e for s in model.sections for e in s.elements
                  if e.kind == "special")
        assert el.column == "printdate"
        assert el.format_date == "MMMM dd, yyyy"
        # the promotion is what used to be missing: no value_type to match
        assert el.value_type == ""
        assert el.format_string == "MMMM dd, yyyy"

    def test_the_bundle_carries_it_into_the_message_template(self, tmp_path):
        model = _dump(tmp_path, LONG)
        out = tmp_path / "d.prpt"
        write_prpt(model, out)
        layout = zipfile.ZipFile(out).read("layout.xml").decode()
        assert "$(report.date, date, MMMM dd, yyyy)" in layout
        assert "MMM d, yyyy)" not in layout        # the old default is gone

    def test_a_report_that_authored_nothing_keeps_the_default(self, tmp_path):
        model = _dump(tmp_path, "")
        out = tmp_path / "d.prpt"
        write_prpt(model, out)
        layout = zipfile.ZipFile(out).read("layout.xml").decode()
        assert "$(report.date, date, MMM d, yyyy)" in layout

    def test_the_demo_statement_matches_crystals_wording(self):
        """The report this was found on."""
        from pathlib import Path

        import pytest

        dump = (Path(__file__).resolve().parents[1] / "samples" / "crystal"
                / "demo" / "Statement_of_Account.xml")
        if not dump.is_file():
            pytest.skip("demo dump not present")
        model = load_report_model(dump)
        el = next(e for s in model.sections for e in s.elements
                  if e.kind == "special" and e.column == "printdate")
        assert el.format_string == "MMMM dd, yyyy"
