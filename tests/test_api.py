"""API tests: upload the sample export through the FastAPI layer."""

from pathlib import Path

from fastapi.testclient import TestClient

from pdi_migration.api.main import app

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_index_serves_ui():
    res = client.get("/")
    assert res.status_code == 200
    assert "Migration" in res.text


def test_convert_returns_report_and_ktr():
    with open(SAMPLE, "rb") as f:
        res = client.post("/convert", files={"export": ("m_load_sales.xml", f, "text/xml")})
    assert res.status_code == 200
    (result,) = res.json()
    assert result["report"]["total_steps"] == 5
    assert result["pipeline"]["name"] == "m_load_sales"
    assert "<transformation>" in result["ktr"]


def test_changelog_served_for_version_popup():
    res = client.get("/changelog")
    assert res.status_code == 200
    assert "# Changelog" in res.text


def test_convert_rejects_non_powercenter_xml():
    res = client.post("/convert", files={"export": ("bad.xml", b"<html></html>", "text/xml")})
    assert res.status_code == 422
