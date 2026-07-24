"""Reports in the project store: record/list/status, the /project/reports API,
wireframe geometry in summaries, and the engine PDF preview (skips off-box)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.project import ReportRecord, list_reports, record_report, set_report_status

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "branch_transactions.xml"

client = TestClient(app)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
    return tmp_path


def _record(**overrides):
    base = dict(file="r.xml", name="Test Report", source_path="", formulas_auto=3,
                formulas_review=1, formulas_manual=2, todos=4,
                copilot_hours=5.5, manual_hours=12.0, status="converted", updated_at="")
    base.update(overrides)
    return ReportRecord(**base)


def test_report_store_roundtrip(store):
    record_report(_record())
    (row,) = list_reports()
    assert row.name == "Test Report"
    assert row.manual_hours == 12.0
    # upsert updates, not duplicates
    record_report(_record(formulas_manual=0))
    (row,) = list_reports()
    assert row.formulas_manual == 0


def test_report_status_workflow(store):
    record_report(_record())
    assert set_report_status("r.xml", "verified") is True
    assert list_reports()[0].status == "verified"
    assert set_report_status("missing.xml", "verified") is False
    with pytest.raises(ValueError):
        set_report_status("r.xml", "nonsense")


def test_project_reports_api(store):
    record_report(_record())
    rows = client.get("/project/reports").json()
    assert rows and rows[0]["file"] == "r.xml"
    res = client.post("/project/report-status",
                      json={"file": "r.xml", "status": "in_review"})
    assert res.status_code == 200
    assert client.get("/project/reports").json()[0]["status"] == "in_review"
    assert client.post("/project/report-status",
                       json={"file": "nope.xml", "status": "verified"}).status_code == 404


def test_summary_carries_wireframe_geometry():
    res = client.post("/reports/inspect",
                      files={"dump": ("b.xml", SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    sections = res.json()["sections"]
    detail = next(s for s in sections if s["area"] == "Detail")
    assert len(detail["items"]) == 6
    el = detail["items"][0]
    assert {"kind", "x", "y", "width", "height", "label"} <= set(el)
    assert el["width"] > 0


def test_pdf_preview_endpoint():
    from pentaho_migration.reports.prpt_validator import validator_available

    if not validator_available():
        pytest.skip("no local PRD install + Java")
    res = client.post("/reports/preview",
                      files={"dump": ("b.xml", SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:4] == b"%PDF"
