"""PDF report generation."""

from pathlib import Path

from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import PowerCenterParser
from pentaho_migration.report_pdf import build_pdf_report
from pentaho_migration.validator import (
    assess_source,
    build_impact_analysis,
    build_report,
    build_score,
)

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"


def _everything():
    parser = PowerCenterParser()
    (pipeline,) = parser.parse_file(SAMPLE)
    RulesMapper().apply(pipeline)
    source = assess_source(parser.analyze_export(SAMPLE), [pipeline])
    impact = build_impact_analysis(pipeline)
    return source, pipeline, build_report(pipeline), build_score(pipeline, impact), impact


def test_build_pdf_report_produces_valid_pdf():
    pdf = build_pdf_report(*_everything())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000


def test_pdf_endpoint_downloads():
    client = TestClient(app)
    with open(SAMPLE, "rb") as f:
        convert = client.post("/convert", files={"export": ("m_load_sales.xml", f, "text/xml")})
    body = convert.json()
    res = client.post("/report/pdf", json={"source": body["source"], "result": body["results"][0]})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert "m_load_sales.report.pdf" in res.headers["content-disposition"]
    assert res.content.startswith(b"%PDF")