"""Reports family: Crystal RptToXml -> .prpt pipeline, folded in from
CR-PRPT-Migration. Covers the translator's contract, the parser, the bundle
writer, source-detection routing, and the /reports API."""

import base64
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.parser import ParseError, detect_parser
from pentaho_migration.reports import load_report_model, write_prpt
from pentaho_migration.reports.formula_translator import translate_formula
from pentaho_migration.reports.prpt_writer import MIMETYPE

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "branch_transactions.xml"

client = TestClient(app)


# ---------------------------------------------------------------- formulas

@pytest.mark.parametrize("crystal, expected", [
    ("{Command.FIRST_NAME} + ' ' + {Command.LAST_NAME}",
     '=[FIRST_NAME] & " " & [LAST_NAME]'),
    ('If {Command.AMOUNT} > 10000 Then "REVIEW" Else "OK"',
     '=IF([AMOUNT] > 10000;"REVIEW";"OK")'),
    ('If {O.A} > 100 Then "H" Else If {O.A} > 10 Then "M" Else "L"',
     '=IF([A] > 100;"H";IF([A] > 10;"M";"L"))'),
    ("{O.A} > 1 and {O.B} < 2 or {O.C} = 3",
     "=OR(AND([A] > 1;[B] < 2);[C] = 3)"),
    ("UpperCase(Trim({C.NAME}))", "=UPPER(TRIM([NAME]))"),
    ("{?Branch} & {@FullName}", "=[Branch] & [FullName]"),
    ("{O.N} mod 2", "=MOD([N];2)"),
    ("CurrentDate", "=TODAY()"),
])
def test_formula_translation(crystal, expected):
    f = translate_formula("t", crystal)
    assert f.status in ("auto", "review")
    assert f.translation == expected


def test_instr_swaps_args_and_flags_review():
    f = translate_formula("t", 'InStr({C.EMAIL}, "@")')
    assert f.status == "review"
    assert f.translation == '=FIND("@";[EMAIL])'


@pytest.mark.parametrize("crystal", [
    "WhilePrintingRecords; {O.A}",
    "Shared NumberVar x;\nx := x * 2;\nx",   # variable, but not the accumulator idiom
    "Sum({O.AMOUNT}) + 5",                   # aggregate inside an expression
    "BeforeReadingRecords({O.A})",           # unknown function
])
def test_untranslatable_is_flagged_manual_never_guessed(crystal):
    f = translate_formula("t", crystal)
    assert f.status == "manual"
    assert f.translation == ""
    assert f.notes


@pytest.mark.parametrize("crystal,cls,field,group", [
    # running-total accumulator idiom -> running report function
    ("WhilePrintingRecords;\nShared NumberVar b;\nb := b + {O.AMOUNT};\nb",
     "ItemSumFunction", "AMOUNT", ""),
    ("NumberVar n;\nn := n + 1;\nn", "ItemCountFunction", "", ""),
    # whole-formula aggregates -> total report functions
    ("Sum({O.AMOUNT})", "TotalGroupSumFunction", "AMOUNT", ""),
    ("Sum({O.AMOUNT}, {O.BRANCH})", "TotalGroupSumFunction", "AMOUNT", "BRANCH"),
    ("Count({O.ID}, {O.BRANCH})", "TotalGroupCountFunction", "ID", "BRANCH"),
    ("Maximum({O.AMOUNT})", "TotalItemMaxFunction", "AMOUNT", ""),
])
def test_blocked_idioms_rewritten_as_report_functions(crystal, cls, field, group):
    """Instead of only advising 'use ItemSumFunction', the translator builds
    the PRD function itself and flags it for review."""
    f = translate_formula("t", crystal)
    assert f.status == "review"
    assert f.translation == ""                 # never a fake OpenFormula guess
    assert f.rewrite_class.endswith("." + cls)
    assert f.rewrite_field == field
    assert f.rewrite_group == group
    assert any("rewritten as a PRD" in n for n in f.notes)


# ---------------------------------------------------------------- parser

def test_parse_sample_model():
    model = load_report_model(SAMPLE)
    assert model.name == "Branch Transaction Summary - Prompt"
    assert model.sql.startswith("SELECT")
    assert [g.column for g in model.groups] == ["BRANCH_NAME"]
    assert [p.name for p in model.parameters] == ["Branch"]
    assert {f.status for f in model.formulas.values()} == {"auto", "review", "manual"}
    # the running total arrives pre-rewritten as a report function
    assert model.formulas["RunningBalance"].rewrite_class.endswith("ItemSumFunction")
    detail = model.sections_of("Detail")[0]
    assert detail.height == 17.0  # styled detail band
    assert len(detail.elements) == 7


def test_summary_resolves_to_function_reference():
    model = load_report_model(SAMPLE)
    footer = model.sections_of("GroupFooter")[0]
    total = next(e for e in footer.elements if e.name == "GFVal")
    assert total.column == "Sum_AMOUNT_BRANCH_NAME"


# ---------------------------------------------------------------- writer

def test_prpt_bundle_shape(tmp_path):
    model = load_report_model(SAMPLE, jndi="CSCU")
    out = tmp_path / "branch.prpt"
    write_prpt(model, out)
    zf = zipfile.ZipFile(out)

    first = zf.infolist()[0]
    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED
    assert zf.read("mimetype").decode() == MIMETYPE

    for name in zf.namelist():
        if name.endswith(".xml"):
            ET.fromstring(zf.read(name))  # raises on malformed XML

    dd = zf.read("datadefinition.xml").decode()
    assert "ItemSumFunction" in dd
    assert 'name="PageofPages"' in dd
    # the running total ships as a generated ItemSumFunction, review-flagged
    assert 'name="RunningBalance"' in dd
    assert "TxnRiskBand" not in dd  # truly blocked formula stays out of the bundle
    assert "CSCU" in zf.read("datasources/sql-ds.xml").decode()


# ------------------------------------------------- record-selection folding

def test_fold_maps_command_aliases_to_source_columns():
    """{Command.ALIAS} record selections must fold to the alias's SOURCE
    expression - SQL cannot reference SELECT aliases in WHERE (and there is
    no real table called Command)."""
    from pentaho_migration.reports.model import Parameter, ReportModel
    from pentaho_migration.reports.record_selection import try_fold_record_selection

    model = ReportModel(name="t")
    model.sql = ('SELECT m.mbr_no AS "MBR_NO", t.txn_amt AS "TXN_AMT"\n'
                 "FROM cscu_core.transactions t\n"
                 "JOIN cscu_core.members m ON m.mbr_id = t.mbr_id\n"
                 "ORDER BY m.mbr_no")
    model.record_selection = "{Command.MBR_NO} = {?MemberNo}"
    model.parameters.append(Parameter(name="MemberNo"))

    assert try_fold_record_selection(model)
    assert "WHERE m.mbr_no = ${MemberNo}" in model.sql
    assert "Command" not in model.sql


def test_fold_keeps_real_table_qualifiers_verbatim():
    from pentaho_migration.reports.model import Parameter, ReportModel
    from pentaho_migration.reports.record_selection import try_fold_record_selection

    model = ReportModel(name="t")
    model.sql = ("SELECT branches.br_name FROM cscu_core.branches "
                 "ORDER BY branches.br_name")
    model.record_selection = "{BRANCHES.BR_NAME} = {?Branch}"
    model.parameters.append(Parameter(name="Branch"))

    assert try_fold_record_selection(model)
    assert "WHERE BRANCHES.BR_NAME = ${Branch}" in model.sql


# ---------------------------------------------------------------- routing

def test_detect_parser_rejects_crystal_dump_with_pointer():
    with pytest.raises(ParseError, match="Reports pipeline"):
        detect_parser(SAMPLE)


# ---------------------------------------------------------------- API

def test_reports_sample_served():
    res = client.get("/reports/sample")
    assert res.status_code == 200
    assert "<Report " in res.text


def test_reports_inspect():
    res = client.post(
        "/reports/inspect?jndi=CSCU",
        files={"dump": ("branch.xml", SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    summary = res.json()
    assert summary["name"] == "Branch Transaction Summary - Prompt"
    assert summary["jndi"] == "CSCU"
    assert summary["counts"] == {
        "sections": 7, "elements": 31, "groups": 1, "parameters": 1,
        "summaries": 2, "auto": 2, "review": 1, "manual": 1}


def test_reports_convert_full_flow():
    res = client.post(
        "/reports/convert",
        files={"dump": ("branch.xml", SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "Branch Transaction Summary - Prompt.prpt"
    assert body["report_markdown"].startswith("# Conversion Report")
    assert "RunningBalance" in body["report_markdown"]

    prpt = base64.b64decode(body["prpt_base64"])
    zf = zipfile.ZipFile(BytesIO(prpt))
    assert zf.infolist()[0].filename == "mimetype"


def test_reports_convert_rejects_garbage():
    res = client.post(
        "/reports/convert",
        files={"dump": ("junk.xml", b"definitely not xml", "text/xml")})
    assert res.status_code == 422


def test_etl_convert_gives_helpful_error_for_crystal_upload():
    res = client.post(
        "/convert",
        files={"export": ("branch.xml", SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 422
    assert "Reports pipeline" in res.json()["detail"]


def test_switch_becomes_nested_if():
    f = translate_formula("t", 'Switch({O.T} = "W", "High", {O.T} = "A", "Low")')
    assert f.status == "review"  # NA() fallback note
    assert f.translation == '=IF([T] = "W";"High";IF([T] = "A";"Low";NA()))'


def test_switch_odd_args_manual():
    f = translate_formula("t", 'Switch({O.T} = "W", "High", "orphan")')
    assert f.status == "manual"


def test_datediff_maps_supported_intervals():
    f = translate_formula("t", 'DateDiff("d", {O.START}, {O.END})')
    assert f.status == "review"
    assert f.translation == '=DATEDIF([START];[END];"d")'


def test_datediff_time_interval_stays_manual():
    f = translate_formula("t", 'DateDiff("h", {O.START}, {O.END})')
    assert f.status == "manual"


def test_chr_maps_to_char():
    f = translate_formula("t", "Chr(13)")
    assert f.status == "review"
    assert f.translation == "=CHAR(13)"


def test_string_plus_uses_field_types():
    types = {"FIRST": "StringField", "LAST": "StringField", "A": "NumberField"}
    f = translate_formula("t", "{C.FIRST} + {C.LAST}", field_types=types)
    assert f.translation == "=[FIRST] & [LAST]"
    f = translate_formula("t", "{C.A} + {C.A}", field_types=types)
    assert f.translation == "=[A] + [A]"


def test_percent_operator_is_not_silently_mistranslated():
    f = translate_formula("t", "{O.A} % {O.B}")
    assert f.status == "manual"


def test_unsupported_summary_becomes_todo_not_broken_reference(tmp_path):
    dump = tmp_path / "r.xml"
    dump.write_text(SAMPLE.read_text(encoding="utf-8").replace(
        'Operation="Sum" SummarizedField="{Command.AMOUNT}"/>',
        'Operation="StdDeviation" SummarizedField="{Command.AMOUNT}"/>'),
        encoding="utf-8")
    model = load_report_model(dump)
    assert any("StdDeviation" in issue for issue in model.issues)
    footer = model.sections_of("ReportFooter")[0]
    el = next(e for e in footer.elements if e.name == "RFVal")
    assert el.kind == "unknown"  # rendered as TODO placeholder, not number-field
    out = tmp_path / "r.prpt"
    write_prpt(model, out)
    dd = zipfile.ZipFile(out).read("datadefinition.xml").decode()
    assert "StdDeviation" not in dd


def test_real_dump_suppression_and_margins():
    real = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "real"
    dumps = sorted(real.glob("*.xml"))
    if len(dumps) < 10:
        pytest.skip("extracted corpus not present")
    suppressed = margins = conditional = 0
    for xml in dumps:
        model = load_report_model(xml)
        suppressed += sum(1 for s in model.sections if s.suppressed)
        if model.page.margin_top != 18.0:  # default means "not parsed"
            margins += 1
        conditional += len(model.issues) + sum(
            1 for s in model.sections for e in s.elements
            for n in e.notes if "conditional" in n)
    assert suppressed > 100     # corpus has 201 EnableSuppress="True" formats
    assert margins > 50         # real dumps carry PageMargins children
    assert conditional > 50     # conditional formatting surfaced, not dropped


def test_professional_formatting_carries_through(tmp_path):
    """Colours, borders, band backgrounds and an embedded logo authored in the
    Crystal source must survive parse -> convert into the .prpt."""
    model = load_report_model(SAMPLE, jndi="CSCU")
    mast = model.sections_of("ReportHeader")[0]
    assert mast.bg_color == "#133346"                       # navy band background
    title = next(e for e in mast.elements if e.name == "Title")
    assert title.font.color == "#ffffff" and title.font.bold
    logo = [e for e in mast.elements if e.kind == "image" and e.image_bytes]
    assert logo, "embedded logo image not carried from the dump"

    out = tmp_path / "styled.prpt"
    write_prpt(model, out)
    zf = zipfile.ZipFile(out)
    assert "resources/image1.png" in zf.namelist()          # logo bundled
    assert "image/png" in zf.read("META-INF/manifest.xml").decode()
    layout = zf.read("layout.xml").decode()
    assert "#133346" in layout                              # navy carried
    # Crystal PageHeader lives in the layout as a repeating details-header
    # (below the masthead on page 1), carrying its band background
    assert 'page-band-styles repeat="true"' in layout
    assert layout.count("#133346") >= 2  # masthead + column-header band fills


def test_rich_parameters_become_list_parameters(tmp_path):
    dump = tmp_path / "p.xml"
    dump.write_text(
        '<?xml version="1.0"?><Report Name="P" FileName="p.rpt">'
        '<Database><Tables><Table Name="Command" ClassName="CommandTable">'
        '<Command>SELECT 1 AS "X"</Command><Fields><Field Name="X" ValueType="StringField"/></Fields>'
        '</Table></Tables></Database><DataDefinition><ParameterFieldDefinitions>'
        '<ParameterFieldDefinition Name="Region" ValueType="StringField" PromptText="Pick" '
        'EnableAllowMultipleValue="True" IsOptionalPrompt="False">'
        '<ParameterDefaultValues><ParameterDefaultValue Value="West"/>'
        '<ParameterDefaultValue Value="East"/></ParameterDefaultValues>'
        '</ParameterFieldDefinition>'
        '<ParameterFieldDefinition Name="AsOf" ValueType="DateField" PromptText="As of" '
        'IsOptionalPrompt="True"/>'
        '</ParameterFieldDefinitions></DataDefinition>'
        '<ReportDefinition><Areas><Area Kind="Detail"><Sections><Section Height="100">'
        '<ReportObjects/></Section></Sections></Area></Areas></ReportDefinition></Report>',
        encoding="utf-8")
    model = load_report_model(dump)
    region = next(p for p in model.parameters if p.name == "Region")
    assert region.multi_value and region.default_values == ["West", "East"]
    asof = next(p for p in model.parameters if p.name == "AsOf")
    assert asof.optional
    out = tmp_path / "p.prpt"
    write_prpt(model, out)
    dd = zipfile.ZipFile(out).read("datadefinition.xml").decode()
    assert 'list-parameter name="Region"' in dd
    assert 'allow-multi-selection="true"' in dd
    assert 'value="West"' in dd
    assert 'mandatory="false"' in dd  # AsOf optional prompt


def test_object_suppress_and_can_grow(tmp_path):
    dump = tmp_path / "o.xml"
    dump.write_text(
        '<?xml version="1.0"?><Report Name="O" FileName="o.rpt">'
        '<Database><Tables><Table Name="Command" ClassName="CommandTable">'
        '<Command>SELECT 1 AS "X"</Command><Fields><Field Name="X" ValueType="StringField"/></Fields>'
        '</Table></Tables></Database><DataDefinition/>'
        '<ReportDefinition><Areas><Area Kind="Detail"><Sections><Section Height="200">'
        '<ReportObjects>'
        '<FieldObject Name="Memo" DataSource="{Command.X}" Left="0" Top="0" Width="2000" Height="100">'
        '<ObjectFormat EnableCanGrow="True"/></FieldObject>'
        '<FieldObject Name="Hidden" DataSource="{Command.X}" Left="0" Top="120" Width="2000" Height="80">'
        '<ObjectFormat EnableSuppress="True"/></FieldObject>'
        '</ReportObjects></Section></Sections></Area></Areas></ReportDefinition></Report>',
        encoding="utf-8")
    model = load_report_model(dump)
    det = model.sections_of("Detail")[0]
    assert next(e for e in det.elements if e.name == "Memo").can_grow
    assert not next(e for e in det.elements if e.name == "Hidden").visible
    out = tmp_path / "o.prpt"
    write_prpt(model, out)
    layout = zipfile.ZipFile(out).read("layout.xml").decode()
    assert 'dynamic-height="true"' in layout
    assert 'visible="false"' in layout


def test_fork_field_formats_resolve_by_type(tmp_path):
    """The forked extractor emits <FieldFormat><NumericFieldFormat/DateFieldFormat
    FormatString=..> for EVERY field; the right candidate must be picked by the
    field's (or formula's declared) value type and carried into the .prpt."""
    dump = tmp_path / "f.xml"
    dump.write_text(
        '<?xml version="1.0"?><Report Name="F" FileName="f.rpt">'
        '<Database><Tables><Table Name="Command" ClassName="CommandTable">'
        '<Command>SELECT 1</Command><Fields>'
        '<Field Name="AMT" ValueType="CurrencyField"/>'
        '<Field Name="DT" ValueType="DateField"/>'
        '<Field Name="NM" ValueType="StringField"/></Fields>'
        '</Table></Tables></Database>'
        '<DataDefinition><FormulaFieldDefinitions>'
        '<FormulaFieldDefinition Name="Total" FormulaName="{@Total}" ValueType="NumberField">{Command.AMT} * 2</FormulaFieldDefinition>'
        '</FormulaFieldDefinitions></DataDefinition>'
        '<ReportDefinition><Areas><Area Kind="Detail"><Sections><Section Height="300"><ReportObjects>'
        + "".join(
            f'<FieldObject Name="o{i}" DataSource="{ref}" Left="0" Top="{i*300}" Width="2000" Height="240">'
            '<FieldFormat>'
            '<NumericFieldFormat DecimalPlaces="3" FormatString="#,##0.000;-#,##0.000"/>'
            '<DateFieldFormat FormatString="dd/MM/yyyy"/>'
            '</FieldFormat></FieldObject>'
            for i, ref in enumerate(["{Command.AMT}", "{Command.DT}", "{Command.NM}", "{@Total}"]))
        + '</ReportObjects></Section></Sections></Area></Areas></ReportDefinition></Report>',
        encoding="utf-8")
    model = load_report_model(dump)
    det = model.sections_of("Detail")[0]
    by_name = {e.name: e for e in det.elements}
    assert by_name["o0"].format_string == "#,##0.000;-#,##0.000"   # currency -> numeric
    assert by_name["o1"].format_string == "dd/MM/yyyy"             # date -> date
    assert by_name["o2"].format_string == ""                       # string -> neither
    assert by_name["o3"].format_string == "#,##0.000;-#,##0.000"   # formula w/ declared NumberField
    out = tmp_path / "f.prpt"
    write_prpt(model, out)
    layout = zipfile.ZipFile(out).read("layout.xml").decode()
    assert 'format-string="#,##0.000;-#,##0.000"' in layout
    assert 'format-string="dd/MM/yyyy"' in layout


def test_chart_migrates_to_legacy_chart(tmp_path):
    """A ChartObject with a fork-emitted ChartDefinition becomes a PRD legacy
    chart (dataset collector + chart expression); unsupported styles stay
    honest TODO placeholders."""
    dump = tmp_path / "c.xml"
    dump.write_text(
        '<?xml version="1.0"?><Report Name="C" FileName="c.rpt">'
        '<Database><Tables><Table Name="Command" ClassName="CommandTable">'
        '<Command>SELECT 1</Command><Fields>'
        '<Field Name="BR" ValueType="StringField"/><Field Name="AMT" ValueType="CurrencyField"/>'
        '</Fields></Table></Tables></Database><DataDefinition/>'
        '<ReportDefinition><Areas><Area Kind="ReportFooter"><Sections><Section Height="4000">'
        '<ReportObjects>'
        '<ChartObject Name="Good" Left="0" Top="0" Width="8000" Height="3000">'
        '<ChartDefinition StyleType="crChartStyleTypePie" ChartType="crChartTypeGroup" Title="Mix">'
        '<ConditionFields><Field FormulaName="{Command.BR}" Name="BR"/></ConditionFields>'
        '<DataFields><Field FormulaName="Sum ({Command.AMT})" Name="AMT"/></DataFields>'
        '</ChartDefinition></ChartObject>'
        '<ChartObject Name="Weird" Left="0" Top="3200" Width="8000" Height="600">'
        '<ChartDefinition StyleType="crChartStyleTypeGantt" ChartType="crChartTypeGroup" Title="G"/>'
        '</ChartObject>'
        '</ReportObjects></Section></Sections></Area></Areas></ReportDefinition></Report>',
        encoding="utf-8")
    model = load_report_model(dump)
    footer = model.sections_of("ReportFooter")[0]
    good = next(e for e in footer.elements if e.name == "Good")
    assert good.kind == "chart" and good.chart_type == "pie"
    weird = next(e for e in footer.elements if e.name == "Weird")
    assert weird.kind == "unknown"  # Gantt -> honest TODO
    out = tmp_path / "c.prpt"
    write_prpt(model, out)
    layout = zipfile.ZipFile(out).read("layout.xml").decode()
    assert "legacy-chart" in layout
    assert "PieChartExpression" in layout
    assert "PieDataSetCollector" in layout
    assert "Gantt" in layout  # TODO placeholder text present
