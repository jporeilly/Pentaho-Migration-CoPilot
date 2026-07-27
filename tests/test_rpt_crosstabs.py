"""Cross-tab recovery: lifting grid definitions the SAP SDK will not export
out of the .rpt binary (via rpt-rs) and into an RptToXml dump, plus the
resolver rules that make a recovered grid usable — or an honest TODO."""

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.rpt_crosstabs import (
    _normalise_ref, describe_availability, enrich_dump, extract_definitions,
    find_rpt_rs)

REPO = Path(__file__).resolve().parents[1]
RPT_DIR = REPO / "samples" / "crystal-rpt"
REAL = REPO / "samples" / "crystal" / "real"

needs_rpt_rs = pytest.mark.skipif(
    find_rpt_rs() is None, reason="rpt-rs CLI not installed")


def _stripped_copy(source: Path, tmp_path: Path) -> Path:
    """A copy of a corpus dump with any existing <CrossTabDefinition> removed,
    so recovery is exercised regardless of whether the checked-in corpus has
    already been enriched."""
    tree = ET.parse(source)
    for obj in tree.getroot().iter("CrossTabObject"):
        for existing in obj.findall("CrossTabDefinition"):
            obj.remove(existing)
    target = tmp_path / source.name
    tree.write(target, encoding="utf-8", xml_declaration=True)
    return target


DUMP = """<?xml version="1.0" encoding="utf-8"?>
<Report Name="XT" FileName="xt.rpt" HasSavedData="False">
<Database><Tables><Table Name="Data" Alias="Data" ClassName="CommandTable">
<Command>SELECT br AS "BR", ty AS "TY", amt AS "AMT" FROM t</Command>
<Fields><Field Name="BR" ValueType="StringField"/><Field Name="TY" ValueType="StringField"/>
<Field Name="AMT" ValueType="CurrencyField"/></Fields></Table></Tables></Database>
<DataDefinition><Groups/><SortFields/>
<FormulaFieldDefinitions>
<FormulaFieldDefinition Name="Label" FormulaName="{@Label}" ValueType="StringField">{Data.BR}</FormulaFieldDefinition>
</FormulaFieldDefinitions>
<ParameterFieldDefinitions/><SummaryFields/></DataDefinition>
<ReportDefinition><Areas>
<Area Kind="ReportHeader" Name="A"><Sections>
<Section Name="S" Height="3000"><SectionFormat EnableSuppress="false"/>
<ReportObjects>
<CrossTabObject Name="CrossTab1" Left="0" Top="0" Width="8000" Height="2400">{block}</CrossTabObject>
</ReportObjects></Section></Sections></Area>
</Areas></ReportDefinition></Report>
"""


def _write(tmp_path, block=""):
    p = tmp_path / "xt.xml"
    p.write_text(DUMP.replace("{block}", block), encoding="utf-8")
    return p


def _definition(rows, cols, sums, recovered=True):
    rows_xml = "".join(f'<Field FieldName="{r}" />' for r in rows)
    cols_xml = "".join(f'<Field FieldName="{c}" />' for c in cols)
    sums_xml = "".join(f'<Field FieldName="{f}" Operation="{op}" />' for f, op in sums)
    attr = ' Recovered="rpt-rs"' if recovered else ""
    return (f'<CrossTabDefinition{attr}><RowFields>{rows_xml}</RowFields>'
            f'<ColumnFields>{cols_xml}</ColumnFields>'
            f'<SummaryFields>{sums_xml}</SummaryFields></CrossTabDefinition>')


class TestNormalisation:
    def test_bare_refs_gain_braces(self):
        assert _normalise_ref("Data.Date") == "{Data.Date}"
        assert _normalise_ref("@Total") == "{@Total}"

    def test_braced_refs_pass_through(self):
        assert _normalise_ref("{Data.Date}") == "{Data.Date}"

    def test_empty_stays_empty(self):
        assert _normalise_ref("") == "" and _normalise_ref(None) == ""


class TestResolverRules:
    """The recovered grid still has to bind to something the query exposes."""

    def test_formula_dimension_resolves(self, tmp_path):
        dump = _write(tmp_path, _definition(["{@Label}"], ["{Data.TY}"],
                                            [("{Data.AMT}", "Sum")]))
        model = load_report_model(dump)
        (el,) = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
        assert el.crosstab_rows == ["Label"]      # formulas are valid dimensions
        assert el.crosstab_columns == ["TY"]

    def test_crystal_duplicate_usage_suffix_is_stripped(self, tmp_path):
        dump = _write(tmp_path, _definition(["{Data.BR}"], ["{Data.TY1}"],
                                            [("{Data.AMT}", "Sum")]))
        model = load_report_model(dump)
        (el,) = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
        assert el.crosstab_columns == ["TY"]
        assert any("grouped more than once" in n for n in el.notes)

    def test_xml_escaped_field_names_are_decoded(self, tmp_path):
        """rpt-rs reports the raw stored name using the XML name-escape
        convention (`_x0020_` = space); RptToXml normalises those to
        underscores. Without decoding, real reports bind to nothing."""
        dump = tmp_path / "xt.xml"
        dump.write_text(
            DUMP.replace("{block}",
                         _definition(["{Data.BR}"], ["{Data.TY}"],
                                     [("{Data.AMT}", "Sum")]))
            .replace('Name="TY"', 'Name="T_Y"')
            .replace('<Field FieldName="{Data.TY}" />',
                     '<Field FieldName="{Data.T_x0020_Y}" />'),
            encoding="utf-8")
        model = load_report_model(dump)
        (el,) = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
        assert el.crosstab_columns == ["T_Y"]

    def test_repeated_level_is_deduped_with_a_note(self, tmp_path):
        dump = _write(tmp_path, _definition(["{Data.BR}"], ["{Data.TY}", "{Data.TY1}"],
                                            [("{Data.AMT}", "Sum")]))
        model = load_report_model(dump)
        (el,) = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
        assert el.crosstab_columns == ["TY"]      # not ["TY", "TY"]
        assert any("more than once on the column axis" in n for n in el.notes)

    def test_recovered_grid_is_flagged_for_verification(self, tmp_path):
        dump = _write(tmp_path, _definition(["{Data.BR}"], ["{Data.TY}"],
                                            [("{Data.AMT}", "Sum")]))
        model = load_report_model(dump)
        (el,) = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
        assert any("recovered from the .rpt binary" in n for n in el.notes)

    def test_hand_written_grid_carries_no_recovery_note(self, tmp_path):
        dump = _write(tmp_path, _definition(["{Data.BR}"], ["{Data.TY}"],
                                            [("{Data.AMT}", "Sum")], recovered=False))
        model = load_report_model(dump)
        (el,) = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
        assert not any("recovered from the .rpt" in n for n in el.notes)

    def test_unresolvable_binding_stays_an_honest_todo(self, tmp_path):
        dump = _write(tmp_path, _definition(["{Data.NOPE}"], ["{Data.TY}"],
                                            [("{Data.AMT}", "Sum")]))
        model = load_report_model(dump)
        assert not [e for s in model.sections for e in s.elements if e.kind == "crosstab"]


class TestEnrichment:
    def test_missing_tool_or_binary_is_a_no_op(self, tmp_path):
        dump = _write(tmp_path)
        assert enrich_dump(dump, tmp_path / "absent.rpt") == 0
        assert "CrossTabDefinition" not in dump.read_text(encoding="utf-8")

    def test_availability_message_is_actionable(self):
        message = describe_availability()
        assert "rpt-rs" in message
        assert ("cannot be recovered" in message) == (find_rpt_rs() is None)

    @needs_rpt_rs
    def test_real_report_recovers_and_converts(self, tmp_path):
        """End-to-end on a real corpus cross-tab: the SDK could not export the
        grid, rpt-rs recovers it, and the report converts to a live crosstab."""
        source = REAL / "ajryan_B1Budget_M.xml"
        binary = RPT_DIR / "ajryan_B1Budget_M.rpt"
        if not (source.exists() and binary.exists()):
            pytest.skip("corpus report not present")
        dump = _stripped_copy(source, tmp_path)
        assert "CrossTabDefinition" not in dump.read_text(encoding="utf-8")

        assert enrich_dump(dump, binary) == 1
        model = load_report_model(dump)
        (el,) = [e for s in model.sections for e in s.elements if e.kind == "crosstab"]
        assert el.crosstab_rows and el.crosstab_columns and el.crosstab_summaries
        assert all(op == "Sum" for _, op in el.crosstab_summaries)

    @needs_rpt_rs
    def test_existing_definition_is_never_overwritten(self, tmp_path):
        source = REAL / "ajryan_B1Budget_M.xml"
        binary = RPT_DIR / "ajryan_B1Budget_M.rpt"
        if not (source.exists() and binary.exists()):
            pytest.skip("corpus report not present")
        dump = _stripped_copy(source, tmp_path)
        enrich_dump(dump, binary)
        assert enrich_dump(dump, binary) == 0      # idempotent

    @needs_rpt_rs
    def test_extraction_reports_axes_and_operations(self):
        binary = RPT_DIR / "ajryan_B1Budget_M.rpt"
        if not binary.exists():
            pytest.skip("corpus .rpt not present")
        definitions = extract_definitions(binary)
        assert definitions, "expected a recovered cross-tab definition"
        definition = next(iter(definitions.values()))
        assert definition.findall("RowFields/Field")
        assert definition.findall("ColumnFields/Field")
        for field in definition.findall("SummaryFields/Field"):
            assert field.get("Operation")
            assert field.get("FieldName", "").startswith("{")
