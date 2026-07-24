"""Project store + API + hardening (API key, upload limit)."""

import pytest
from fastapi.testclient import TestClient

from pentaho_migration.api.main import MAX_UPLOAD_BYTES, app
from pentaho_migration.project import MappingRecord, list_mappings, record_mapping, set_status


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))


def _record(name="m_test", file="test.xml", score=72):
    return MappingRecord(
        mapping=name, file=file, steps=10, auto=6, review=3, manual=1,
        expressions=4, score=score, grade="B", status="converted", updated_at="",
    )


class TestStore:
    def test_record_list_and_upsert(self):
        record_mapping(_record())
        record_mapping(_record(score=90))  # same key -> update, not duplicate
        rows = list_mappings()
        assert len(rows) == 1
        assert rows[0].score == 90
        assert rows[0].status == "converted"

    def test_status_transitions(self):
        record_mapping(_record())
        assert set_status("test.xml", "m_test", "verified")
        assert list_mappings()[0].status == "verified"
        assert not set_status("nope.xml", "missing", "verified")
        with pytest.raises(ValueError):
            set_status("test.xml", "m_test", "bogus")


class TestProjectAPI:
    def test_roundtrip_and_status_update(self):
        client = TestClient(app)
        record_mapping(_record())
        rows = client.get("/project").json()
        assert rows[0]["mapping"] == "m_test"

        res = client.post("/project/status", json={
            "file": "test.xml", "mapping": "m_test", "status": "in_review",
        })
        assert res.status_code == 200
        assert client.get("/project").json()[0]["status"] == "in_review"

    def test_invalid_status_rejected(self):
        client = TestClient(app)
        record_mapping(_record())
        res = client.post("/project/status", json={
            "file": "test.xml", "mapping": "m_test", "status": "bogus",
        })
        assert res.status_code == 422


class TestProjectOpen:
    SAMPLE = __import__("pathlib").Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"

    def test_open_rebuilds_full_result(self):
        client = TestClient(app)
        record_mapping(_record(name="m_load_sales", file="m_load_sales.xml").model_copy(
            update={"source_path": str(self.SAMPLE)}
        ))
        res = client.get("/project/open", params={"file": "m_load_sales.xml", "mapping": "m_load_sales"})
        assert res.status_code == 200
        body = res.json()
        assert body["results"][0]["pipeline"]["name"] == "m_load_sales"
        assert body["results"][0]["score"]["grade"] in "ABCDE"
        assert "<transformation>" in body["results"][0]["ktr"]

    def test_open_unknown_mapping_404(self):
        client = TestClient(app)
        res = client.get("/project/open", params={"file": "x.xml", "mapping": "nope"})
        assert res.status_code == 404

    def test_open_moved_source_410(self):
        client = TestClient(app)
        record_mapping(_record(name="m_gone", file="gone.xml").model_copy(
            update={"source_path": "C:/does/not/exist.xml"}
        ))
        res = client.get("/project/open", params={"file": "gone.xml", "mapping": "m_gone"})
        assert res.status_code == 410


class TestHardening:
    def test_api_key_enforced_when_configured(self, monkeypatch):
        monkeypatch.setenv("PENTAHO_MIGRATION_API_KEY", "sekret")
        client = TestClient(app)
        res = client.post("/convert", files={"export": ("x.xml", b"<POWERMART/>", "text/xml")})
        assert res.status_code == 401
        res = client.post(
            "/convert",
            files={"export": ("x.xml", b"<POWERMART/>", "text/xml")},
            headers={"X-API-Key": "sekret"},
        )
        assert res.status_code == 200  # authenticated; parses an empty export

    def test_oversized_upload_rejected(self):
        client = TestClient(app)
        blob = b"x" * (MAX_UPLOAD_BYTES + 1)
        res = client.post("/convert", files={"export": ("big.xml", blob, "text/xml")})
        assert res.status_code == 413

    def test_health_reports_rules_version(self):
        from pentaho_migration.mapper import RulesMapper

        client = TestClient(app)
        body = client.get("/health").json()
        assert body["rules_version"] == str(RulesMapper().meta["version"])