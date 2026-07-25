"""Path self-healing in the project store, the talend_demo walkthrough set,
and the ETL consultant portfolio report."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.project import (
    MappingRecord, list_mappings, record_mapping, resolve_source_path)

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "samples" / "talend_demo"

client = TestClient(app)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
    return tmp_path


def _record(**overrides):
    base = dict(mapping="m_X", file="x.xml", source_path="", steps=5, auto=3,
                review=1, manual=1, expressions=0, score=70, grade="B",
                status="converted", updated_at="")
    base.update(overrides)
    return MappingRecord(**base)


class TestPathHealing:
    def test_resolves_pre_rename_absolute_path(self):
        """The store predating the repo rename holds dead PDI-Migration
        paths - they rebase onto the current repo root."""
        stale = r"C:\Projects\PDI-Migration\samples\informatica\hhs_les.xml"
        resolved = resolve_source_path(stale)
        assert resolved is not None
        assert resolved == REPO / "samples" / "informatica" / "hhs_les.xml"

    def test_resolves_by_basename_fallback(self):
        resolved = resolve_source_path(r"D:\elsewhere\members_export_0.1.item")
        assert resolved == DEMO / "members_export_0.1.item"

    def test_unresolvable_returns_none(self):
        assert resolve_source_path(r"C:\nope\missing_forever.xml") is None

    def test_list_mappings_heals_in_place(self, store):
        stale = r"C:\Projects\PDI-Migration\samples\informatica\hhs_les.xml"
        record_mapping(_record(source_path=stale))
        (row,) = list_mappings()
        assert Path(row.source_path).is_file()
        assert "PDI-Migration" not in row.source_path


class TestTalendDemo:
    def test_all_four_jobs_convert(self):
        from pentaho_migration.generator import KtrGenerator
        from pentaho_migration.mapper import RulesMapper
        from pentaho_migration.parser import TalendParser

        for item in sorted(DEMO.glob("*.item")):
            (pipe,) = TalendParser().parse_file(item)
            RulesMapper.for_pipeline(pipe).apply(pipe)
            assert KtrGenerator().generate(pipe)  # emits without error

    def test_orchestrator_produces_kjb(self):
        from pentaho_migration.parser import TalendParser

        (job,) = TalendParser().parse_workflows(DEMO / "cscu_nightly_0.1.item")
        chains = [(h.from_entry, h.to_entry) for h in job.hops]
        assert ("tRunJob_1", "tRunJob_2") in chains
        assert ("tRunJob_2", "tRunJob_3") in chains

    def test_sample_talend_endpoint_serves_demo_job(self):
        res = client.get("/sample-talend")
        assert res.status_code == 200
        assert b"tAggregateRow" in res.content


class TestEtlPortfolio:
    def test_endpoint_renders_html_per_family(self, store):
        record_mapping(_record(
            mapping="j1", file="branch_balances_0.1.item",
            source_path=str(DEMO / "branch_balances_0.1.item")))
        record_mapping(_record(
            mapping="m1", file="hhs_les.xml",
            source_path=str(REPO / "samples" / "informatica" / "hhs_les.xml")))
        talend = client.get("/project/portfolio?family=talend")
        assert talend.status_code == 200
        assert "Talend Migration" in talend.text
        infa = client.get("/project/portfolio?family=informatica")
        assert infa.status_code == 200
        assert "Informatica PowerCenter Migration" in infa.text
        assert "Remaining manual work by component" in infa.text

    def test_unknown_family_is_404_when_empty(self, store):
        assert client.get("/project/portfolio?family=talend").status_code == 404
