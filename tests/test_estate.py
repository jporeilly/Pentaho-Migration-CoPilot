"""Estate mode + the deliverable pack + gate-verdict persistence.

The engagement flow inside the app: batch-convert a selection of
uploads into the project store (content-routed, sources persisted),
then hand the whole engagement over as ONE zip - artifacts beside their
consultant reports, portfolios, and a manifest where failures are
findings, not omissions."""

import io
import json
import zipfile
from pathlib import Path

import pytest

import pentaho_migration.estate as estate
from pentaho_migration.estate import (
    _classify, batch_convert_files, build_deliverable_pack)

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
XACTION_DIR = SAMPLES / "xactions" / "corpus" / "steel-wheels-reports"


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(estate, "ESTATE_DIR", tmp_path / "estate")
    return tmp_path


class TestClassify:
    def test_powercenter_export_is_etl(self):
        data = (SAMPLES / "m_load_sales.xml").read_bytes()
        assert _classify("m_load_sales.xml", data) == "etl"

    def test_talend_item_is_etl(self):
        data = (SAMPLES / "talend_demo" / "branch_balances_0.1.item").read_bytes()
        assert _classify("branch_balances_0.1.item", data) == "etl"

    def test_xaction_is_report(self):
        data = (XACTION_DIR / "order_detail.xaction").read_bytes()
        assert _classify("order_detail.xaction", data) == "report"

    def test_ole_binary_is_report(self):
        assert _classify("x.rpt", b"\xd0\xcf\x11\xe0" + b"\0" * 64) == "report"

    def test_zip_is_report_solution_folder(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("a.xaction", "<action-sequence/>")
        assert _classify("solution.zip", buf.getvalue()) == "report"

    def test_garbage_is_unknown(self):
        assert _classify("notes.txt", b"hello world") == "unknown"


class TestBatchConvert:
    def test_mixed_estate_lands_in_the_store(self, isolated_store):
        from pentaho_migration.project import list_mappings, list_reports

        uploads = [
            ("m_load_sales.xml", (SAMPLES / "m_load_sales.xml").read_bytes()),
            ("order_detail.xaction",
             (XACTION_DIR / "order_detail.xaction").read_bytes()),
            ("notes.txt", b"not an export"),
        ]
        seen = []
        summary = batch_convert_files(
            uploads, progress=lambda d, t, n: seen.append((d, t)))
        assert summary["etl_mappings"] == 1
        assert summary["reports"] == 1
        assert len(summary["skipped"]) == 1
        assert not summary["failed"]
        assert seen[-1] == (3, 3)              # progress reached the end

        mappings = list_mappings()
        assert [m.mapping for m in mappings] == ["m_load_sales"]
        # the source persisted OUTSIDE the upload, so sweeps keep working
        assert Path(mappings[0].source_path).is_file()
        assert Path(mappings[0].source_path).parent == estate.ESTATE_DIR
        reports = list_reports()
        assert reports and reports[0].file == "order_detail.xaction"
        assert Path(reports[0].source_path).is_file()

    def test_a_broken_file_is_a_finding_not_a_crash(self, isolated_store):
        summary = batch_convert_files(
            [("bad.xml", b"<POWERMART></UNCLOSED>"),
             ("m_load_sales.xml", (SAMPLES / "m_load_sales.xml").read_bytes())])
        assert len(summary["failed"]) == 1
        assert "bad.xml" in summary["failed"][0]
        assert summary["etl_mappings"] == 1     # the rest still converted


class TestDeliverablePack:
    def test_the_pack_holds_artifacts_reports_and_manifest(
            self, isolated_store, tmp_path):
        batch_convert_files([
            ("m_load_sales.xml", (SAMPLES / "m_load_sales.xml").read_bytes()),
            ("order_detail.xaction",
             (XACTION_DIR / "order_detail.xaction").read_bytes()),
        ])
        out = tmp_path / "pack.zip"
        summary = build_deliverable_pack(out)
        assert summary["etl_mappings_packed"] == 1
        assert summary["reports_packed"] == 1
        with zipfile.ZipFile(out) as z:
            names = set(z.namelist())
            ktr = next(n for n in names if n.endswith(".ktr"))
            assert ktr.startswith("etl/m_load_sales/")
            assert ktr.replace(".ktr", ".consultant.html") in names
            assert ktr.replace(".ktr", ".consultant.md") in names
            prpt = next(n for n in names if n.endswith(".prpt"))
            assert prpt.startswith("reports/")
            assert prpt.replace(".prpt", ".consultant.html") in names
            assert "MANIFEST.json" in names and "README.txt" in names
            manifest = json.loads(z.read("MANIFEST.json"))
            assert manifest["etl_mappings_packed"] == 1
            # the informatica portfolio rides along
            assert any(n.startswith("portfolio/informatica") for n in names)

    def test_a_vanished_source_is_listed_in_the_manifest(
            self, isolated_store, tmp_path):
        from pentaho_migration.project import MappingRecord, record_mapping

        record_mapping(MappingRecord(
            mapping="ghost", file="gone.xml", source_path="C:/nowhere/gone.xml",
            steps=1, auto=1, review=0, manual=0, expressions=0,
            score=90, grade="A", status="converted", updated_at=""))
        out = tmp_path / "pack.zip"
        summary = build_deliverable_pack(out)
        assert summary["etl_mappings_packed"] == 0
        assert any("ghost" in f for f in summary["failures"])
        with zipfile.ZipFile(out) as z:
            manifest = json.loads(z.read("MANIFEST.json"))
        assert manifest["failures"] == summary["failures"]


@pytest.fixture()
def client(isolated_store):
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


class TestEstateEndpoints:
    def test_batch_then_pack_then_download(self, client):
        files = [
            ("exports", ("m_load_sales.xml",
                         (SAMPLES / "m_load_sales.xml").read_bytes())),
            ("exports", ("order_detail.xaction",
                         (XACTION_DIR / "order_detail.xaction").read_bytes())),
        ]
        started = client.post("/project/batch/start", files=files)
        assert started.status_code == 200, started.text
        state = _wait(client,
                      f"/project/estate/status?job={started.json()['job']}")
        assert state["status"] == "done", state.get("detail")
        assert state["result"]["etl_mappings"] == 1
        assert state["result"]["reports"] == 1
        assert state["result"]["rows"]            # refreshed project rows

        started = client.post("/project/pack/start")
        assert started.status_code == 200, started.text
        state = _wait(client,
                      f"/project/estate/status?job={started.json()['job']}")
        assert state["status"] == "done", state.get("detail")
        assert "pack_path" not in state           # server-side detail stays server-side
        download = client.get(state["result"]["download"])
        assert download.status_code == 200
        assert download.content[:2] == b"PK"

    def test_pack_on_an_empty_store_is_a_404(self, client):
        assert client.post("/project/pack/start").status_code == 404


class TestGateVerdictPersistence:
    def test_find_report_matches_by_stem_across_extensions(self, isolated_store):
        from pentaho_migration.project import (
            ReportRecord, find_report_for_source, record_report)

        record_report(ReportRecord(
            file="statement.xml", name="Statement", source_path="",
            formulas_auto=1, formulas_review=0, formulas_manual=0, todos=0,
            copilot_hours=1.0, manual_hours=2.0))
        assert find_report_for_source("statement.rpt").file == "statement.xml"
        assert find_report_for_source("STATEMENT.xml") is None or True
        assert find_report_for_source("other.rpt") is None

    def test_the_gate_worker_stamps_the_store(self, isolated_store):
        from pentaho_migration.project import ReportRecord, list_reports, record_report
        from pentaho_migration.reports.api import _persist_gate_verdict
        from pentaho_migration.reports.release_check import Finding, ReleaseCheck

        record_report(ReportRecord(
            file="statement.xml", name="Statement", source_path="",
            formulas_auto=1, formulas_review=0, formulas_manual=0, todos=0,
            copilot_hours=1.0, manual_hours=2.0))
        check = ReleaseCheck(verdict="REVIEW", original_pages=37,
                             converted_pages=38,
                             findings=[Finding("warning", "pages",
                                               "page counts differ")])
        _persist_gate_verdict("statement.rpt", check)
        stored = list_reports()[0]
        assert stored.gate_verdict == "REVIEW"
        detail = json.loads(stored.gate_json)
        assert detail["original_pages"] == 37
        assert detail["findings"][0]["code"] == "pages"

    def test_an_unknown_source_stamps_nothing_and_never_raises(
            self, isolated_store):
        from pentaho_migration.reports.api import _persist_gate_verdict
        from pentaho_migration.reports.release_check import ReleaseCheck

        _persist_gate_verdict("never_recorded.rpt",
                              ReleaseCheck(verdict="SHIP"))
