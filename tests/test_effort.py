"""Effort & cost estimation: heuristic sanity for both families and API
surface. Hours are the server product; cost is client-side (hours x rate),
so no currency assertions here."""

from pathlib import Path

from fastapi.testclient import TestClient

from pdi_migration.api.main import app
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import PowerCenterParser
from pdi_migration.reports import load_report_model
from pdi_migration.reports.effort import build_report_effort
from pdi_migration.validator import build_effort, build_report

ETL_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"
CRYSTAL_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "branch_transactions.xml"

client = TestClient(app)


def _etl_estimate():
    (pipeline,) = PowerCenterParser().parse_file(ETL_SAMPLE)
    RulesMapper().apply(pipeline)
    return pipeline, build_effort(pipeline, build_report(pipeline))


def test_etl_effort_sanity():
    _, effort = _etl_estimate()
    assert effort.copilot_hours > 0
    assert effort.manual_hours > effort.copilot_hours
    assert effort.saved_hours == effort.manual_hours - effort.copilot_hours
    assert 0 < effort.saved_pct <= 100
    assert effort.assumptions  # the numbers must be defensible


def test_etl_effort_scales_with_manual_steps():
    pipeline, base = _etl_estimate()
    for step in pipeline.steps:
        step.confidence = "manual"
    worse = build_effort(pipeline, build_report(pipeline))
    assert worse.copilot_hours > base.copilot_hours


def test_report_effort_sanity():
    model = load_report_model(CRYSTAL_SAMPLE)
    effort = build_report_effort(model)
    assert effort.copilot_hours > 0
    assert effort.manual_hours > effort.copilot_hours
    assert 0 < effort.saved_pct <= 100


def test_report_effort_drops_after_formula_assist():
    model = load_report_model(CRYSTAL_SAMPLE)
    before = build_report_effort(model)
    for f in model.formulas.values():
        if f.status == "manual":
            f.status = "review"
            f.translation = "=[AMOUNT]"
    after = build_report_effort(model)
    assert after.copilot_hours < before.copilot_hours
    # rebuild-from-scratch cost is unchanged by the assist
    assert after.manual_hours == before.manual_hours


def test_effort_in_etl_api():
    res = client.post("/convert",
                      files={"export": ("m.xml", ETL_SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    effort = res.json()["results"][0]["effort"]
    assert effort["manual_hours"] > effort["copilot_hours"]


def test_effort_in_reports_api():
    res = client.post("/reports/convert",
                      files={"dump": ("b.xml", CRYSTAL_SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    effort = res.json()["summary"]["effort"]
    assert effort["manual_hours"] > effort["copilot_hours"]
    assert effort["saved_pct"] > 0
