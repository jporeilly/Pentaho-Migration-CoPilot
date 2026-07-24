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

from pdi_migration.api.main import app
from pdi_migration.parser import ParseError, detect_parser
from pdi_migration.reports import load_report_model, write_prpt
from pdi_migration.reports.formula_translator import translate_formula
from pdi_migration.reports.prpt_writer import MIMETYPE

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
    model = load_report_model(SAMPLE, jndi="CSCU_Bank")
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
    assert "CSCU_Bank" in zf.read("datasources/sql-ds.xml").decode()


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
        "/reports/inspect?jndi=CSCU_Bank",
        files={"dump": ("branch.xml", SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    summary = res.json()
    assert summary["name"] == "Branch Transaction Summary"
    assert summary["jndi"] == "CSCU_Bank"
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
