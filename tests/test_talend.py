"""Talend source support: parser, detection, rules, end-to-end conversion."""

from pathlib import Path
from xml.etree import ElementTree

from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.generator import KtrGenerator
from pentaho_migration.ir import SourceTool
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import PowerCenterParser, TalendParser, detect_parser

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "demo_orders_0.1.item"
PC_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"


def _pipeline():
    (pipeline,) = TalendParser().parse_file(FIXTURE)
    return pipeline


class TestDetection:
    def test_item_file_routes_to_talend(self):
        assert isinstance(detect_parser(FIXTURE), TalendParser)

    def test_powermart_routes_to_powercenter(self):
        assert isinstance(detect_parser(PC_SAMPLE), PowerCenterParser)


class TestTalendParser:
    def test_job_name_strips_version_suffix(self):
        assert _pipeline().name == "demo_orders"

    def test_steps_and_source_tool(self):
        pipeline = _pipeline()
        assert pipeline.source_tool == SourceTool.TALEND
        names = {s.name for s in pipeline.steps}
        assert names == {
            "tFileInputDelimited_1", "tMysqlInput_1", "tMap_1",
            "tAggregateRow_1", "tMysqlOutput_1", "tLogRow_1",
        }

    def test_schema_columns_typed(self):
        step = _pipeline().step("tFileInputDelimited_1")
        by_name = {f.name: f for f in step.fields}
        assert by_name["AMOUNT"].datatype == "decimal"
        assert by_name["AMOUNT"].precision == 12
        assert by_name["AMOUNT"].scale == 2
        assert by_name["ORDER_ID"].datatype == "integer"
        assert by_name["ORDER_ID"].nullable is False

    def test_hops_include_flow_and_lookup(self):
        edges = {(h.from_step, h.to_step) for h in _pipeline().hops}
        assert ("tFileInputDelimited_1", "tMap_1") in edges
        assert ("tMysqlInput_1", "tMap_1") in edges          # LOOKUP connector
        assert ("tAggregateRow_1", "tLogRow_1") in edges
        assert len(edges) == 5

    def test_tmap_expressions_java_passthrough_skipped(self):
        tmap = _pipeline().step("tMap_1")
        fields = {e.field for e in tmap.expressions}
        # row1.ORDER_ID is a bare passthrough — not a derivation
        assert fields == {"REGION_NAME", "AMOUNT_TAXED"}
        assert all(e.language == "java" for e in tmap.expressions)
        region = next(e for e in tmap.expressions if e.field == "REGION_NAME")
        assert "StringHandling.UPCASE" in region.raw

    def test_analyze_export(self):
        info = TalendParser().analyze_export(FIXTURE)
        assert info.tool == "Talend"
        assert info.product_version == "8.0.1"
        assert info.mappings == 1


class TestTalendRules:
    def test_component_mappings(self):
        pipeline = _pipeline()
        RulesMapper.for_pipeline(pipeline).apply(pipeline)
        mapped = {s.name: s.pdi_type for s in pipeline.steps}
        assert mapped["tFileInputDelimited_1"] == "CsvInput"
        assert mapped["tMysqlInput_1"] == "TableInput"
        assert mapped["tMap_1"] == "ScriptValueMod"
        assert mapped["tAggregateRow_1"] == "GroupBy"
        assert mapped["tMysqlOutput_1"] == "TableOutput"
        assert mapped["tLogRow_1"] == "WriteToLog"

    def test_talend_query_lands_in_table_input_sql(self):
        pipeline = _pipeline()
        RulesMapper.for_pipeline(pipeline).apply(pipeline)
        root = ElementTree.fromstring(KtrGenerator().generate(pipeline))
        mysql = next(s for s in root.iter("step") if s.findtext("name") == "tMysqlInput_1")
        assert mysql.findtext("sql") == "SELECT REGION_CODE, REGION_NAME FROM REGIONS"


class TestTalendEndToEnd:
    def test_convert_via_api(self):
        client = TestClient(app)
        with open(FIXTURE, "rb") as f:
            res = client.post("/convert", files={"export": ("demo_orders_0.1.item", f, "text/xml")})
        assert res.status_code == 200
        body = res.json()
        assert body["source"]["tool"] == "Talend"
        (result,) = body["results"]
        assert result["pipeline"]["source_tool"] == "talend"
        # job name must come from the uploaded filename, not a server temp file
        assert result["pipeline"]["name"] == "demo_orders"
        assert result["score"]["grade"] in "ABCDE"
        tmap_impact = next(e for e in result["impact"]["entries"] if e["step"] == "tMap_1")
        assert tmap_impact["impact"] == "high"