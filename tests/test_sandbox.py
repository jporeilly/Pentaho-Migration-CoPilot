"""Sandbox kit: DDL inference, synthetic data determinism, API endpoint."""

from pathlib import Path

from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.ir import FieldDef
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import PowerCenterParser
from pentaho_migration.sandbox import build_sandbox_kit, generate_csv, sql_type

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"


def _mapped():
    (pipeline,) = PowerCenterParser().parse_file(SAMPLE)
    return RulesMapper().apply(pipeline)


class TestSqlTypes:
    def test_common_types(self):
        assert sql_type(FieldDef(name="A", datatype="string", precision=20)) == "VARCHAR(20)"
        assert sql_type(FieldDef(name="B", datatype="decimal", precision=10, scale=2)) == "NUMERIC(10,2)"
        assert sql_type(FieldDef(name="C", datatype="date/time")) == "TIMESTAMP"
        assert sql_type(FieldDef(name="D", datatype="weirdtype")) == "VARCHAR(255)"


class TestKit:
    def test_ddl_covers_reads_and_writes(self):
        kit = build_sandbox_kit(_mapped())
        assert "CREATE TABLE SQ_SALES" in kit.ddl
        assert "AMOUNT NUMERIC(10,2)" in kit.ddl
        # target has no fields of its own; columns derived from upstream AGG_SALES
        assert "CREATE TABLE T_SALES_SUMMARY" in kit.ddl
        assert "SANDBOX" in kit.ddl.upper()

    def test_csv_generated_for_reads_only(self):
        kit = build_sandbox_kit(_mapped())
        assert "data_SQ_SALES.csv" in kit.data
        assert "data_T_SALES_SUMMARY.csv" not in kit.data

    def test_guide_names_the_connection_steps(self):
        kit = build_sandbox_kit(_mapped())
        assert "SQ_SALES" in kit.guide
        assert "never point the converted transformation at production" in kit.guide.lower()


class TestSyntheticData:
    FIELDS = [
        FieldDef(name="REGION", datatype="string", precision=8),
        FieldDef(name="AMOUNT", datatype="decimal", precision=10, scale=2),
    ]

    def test_deterministic_and_shaped(self):
        a = generate_csv(self.FIELDS, rows=5, seed=7)
        b = generate_csv(self.FIELDS, rows=5, seed=7)
        assert a == b
        lines = a.strip().split("\n")
        assert lines[0] == "REGION,AMOUNT"
        assert len(lines) == 6
        region, amount = lines[1].split(",")
        assert len(region) <= 8
        assert len(amount.split(".")[-1]) == 2  # scale respected


def test_sandbox_endpoint():
    client = TestClient(app)
    pipeline = _mapped()
    res = client.post("/sandbox", json=pipeline.model_dump())
    assert res.status_code == 200
    kit = res.json()
    assert kit["mapping"] == "m_load_sales"
    assert "CREATE TABLE" in kit["ddl"]
    assert any(name.startswith("data_") for name in kit["data"])