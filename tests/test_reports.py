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
    "Shared NumberVar balance;\nbalance := balance + {O.AMOUNT};\nbalance",
    "WhilePrintingRecords; {O.A}",
    "Sum({O.AMOUNT})",              # aggregates must become report functions
    "BeforeReadingRecords({O.A})",  # unknown function
])
def test_untranslatable_is_flagged_manual_never_guessed(crystal):
    f = translate_formula("t", crystal)
    assert f.status == "manual"
    assert f.translation == ""
    assert f.notes


# ---------------------------------------------------------------- parser

def test_parse_sample_model():
    model = load_report_model(SAMPLE)
    assert model.name == "Branch Transaction Summary"
    assert model.sql.startswith("SELECT")
    assert [g.column for g in model.groups] == ["BRANCH_NAME"]
    assert [p.name for p in model.parameters] == ["Branch"]
    assert {f.status for f in model.formulas.values()} == {"auto", "manual"}
    detail = model.sections_of("Detail")[0]
    assert detail.height == 16.0  # 320 twips -> 16 points
    assert len(detail.elements) == 6


def test_summary_resolves_to_function_reference():
    model = load_report_model(SAMPLE)
    footer = model.sections_of("GroupFooter")[0]
    total = next(e for e in footer.elements if e.name == "BranchTotal")
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
    assert "RunningBalance" not in dd  # blocked formula stays out of the bundle
    assert "CSCU" in zf.read("datasources/sql-ds.xml").decode()


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
    assert summary["name"] == "Branch Transaction Summary"
    assert summary["jndi"] == "CSCU"
    assert summary["counts"] == {
        "sections": 7, "elements": 21, "groups": 1, "parameters": 1,
        "summaries": 2, "auto": 2, "review": 0, "manual": 2}


def test_reports_convert_full_flow():
    res = client.post(
        "/reports/convert",
        files={"dump": ("branch.xml", SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "Branch Transaction Summary.prpt"
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
    el = next(e for e in footer.elements if e.name == "GrandTotal")
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
