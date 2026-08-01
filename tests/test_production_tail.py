"""The production tail (#73): consultant PDF on the ETL review, and the
portable project store (export/import through the sqlite backup API -
file renames lose to Windows handle semantics, content restore wins)."""

from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from pentaho_migration.api.main import app

    return TestClient(app, client=("127.0.0.1", 12345))


def _wait(client, url, tries=300):
    import time

    for _ in range(tries):
        state = client.get(url).json()
        if state.get("status") != "running":
            return state
        time.sleep(0.05)
    raise AssertionError("job never finished")


class TestReviewConsultantPdf:
    def test_the_review_result_carries_a_valid_pdf(self, client):
        import base64

        data = (SAMPLES / "m_load_sales.xml").read_bytes()
        result = client.post(
            "/convert",
            files={"export": ("m_load_sales.xml", data)}).json()["results"][0]
        started = client.post("/review/start", json={
            "pipeline": result["pipeline"], "ktr": result["ktr"],
            "llm": False})
        state = _wait(client, f"/review/status?job={started.json()['job']}")
        assert state["status"] == "done", state.get("detail")
        pdf = base64.b64decode(state["result"]["consultant_report_pdf"])
        assert pdf[:5] == b"%PDF-"

    def test_the_pdf_leads_with_the_review_sections(self):
        from pentaho_migration.generator import KtrGenerator
        from pentaho_migration.mapper import RulesMapper
        from pentaho_migration.parser import detect_parser
        from pentaho_migration.report_pdf import build_pdf_report
        from pentaho_migration.validator import (
            build_effort, build_impact_analysis, build_report, build_score)
        from pentaho_migration.validator.review import review_pipeline

        sample = SAMPLES / "talend_demo" / "branch_balances_0.1.item"
        pipeline = detect_parser(sample).parse_file(sample)[0]
        RulesMapper.for_pipeline(pipeline).apply(pipeline)
        ktr = KtrGenerator().generate(pipeline)
        check = review_pipeline(pipeline, ktr=ktr)
        report = build_report(pipeline)
        impact = build_impact_analysis(pipeline)
        pdf = build_pdf_report(
            None, pipeline, report, build_score(pipeline, impact), impact,
            effort=build_effort(pipeline, report), check=check)
        assert pdf[:5] == b"%PDF-"
        # a Talend pipeline must not claim to be Informatica
        import zlib

        # crude but effective: the header text lives in the first stream
        assert b"Talend" in pdf or any(
            b"Talend" in zlib.decompress(chunk)
            for chunk in _streams(pdf) if _inflatable(chunk))


def _streams(pdf: bytes):
    import re

    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        yield m.group(1)


def _inflatable(chunk: bytes) -> bool:
    import zlib

    try:
        zlib.decompress(chunk)
        return True
    except zlib.error:
        return False


class TestPortableStore:
    def test_export_import_round_trip(self, client):
        data = (SAMPLES / "m_load_sales.xml").read_bytes()
        started = client.post("/project/batch/start",
                              files=[("exports", ("m_load_sales.xml", data))])
        _wait(client, f"/project/estate/status?job={started.json()['job']}")

        exported = client.get("/project/export")
        assert exported.status_code == 200
        assert exported.content[:6] == b"SQLite"

        res = client.post("/project/import",
                          files={"store": ("store.db", exported.content)})
        assert res.status_code == 200
        assert res.json()["mappings"] == 1
        # the pre-import store was backed up beside itself
        from pentaho_migration.project import _db_path

        assert list(_db_path().parent.glob("project.db.bak-*"))

    def test_garbage_is_rejected_with_the_reason(self, client):
        res = client.post("/project/import",
                          files={"store": ("x.db", b"definitely not sqlite")})
        assert res.status_code == 422
        assert "not a sqlite database" in res.json()["detail"]
