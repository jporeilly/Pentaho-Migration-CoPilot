"""End-to-end tests over the sample PowerCenter export: parse -> map -> generate."""

from pathlib import Path
from xml.etree import ElementTree

import pytest

from pentaho_migration.generator import KtrGenerator
from pentaho_migration.ir import Confidence
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import PowerCenterParser
from pentaho_migration.parser.powercenter import PowerCenterParseError
from pentaho_migration.validator import build_report

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"


@pytest.fixture
def pipeline():
    pipelines = PowerCenterParser().parse_file(SAMPLE)
    assert len(pipelines) == 1
    return pipelines[0]


class TestParser:
    def test_extracts_mapping_and_steps(self, pipeline):
        assert pipeline.name == "m_load_sales"
        names = {s.name for s in pipeline.steps}
        assert names == {"SQ_SALES", "EXP_CALC", "AGG_SALES", "SALES", "T_SALES_SUMMARY"}

    def test_extracts_hops_deduplicated(self, pipeline):
        edges = {(h.from_step, h.to_step) for h in pipeline.hops}
        # 8 CONNECTORs collapse to 4 unique instance-level hops
        assert len(pipeline.hops) == len(edges) == 4
        assert ("EXP_CALC", "AGG_SALES") in edges

    def test_extracts_expressions_skipping_passthrough(self, pipeline):
        exp_calc = pipeline.step("EXP_CALC")
        assert [e.field for e in exp_calc.expressions] == ["AMOUNT_TAXED"]
        assert "IIF(ISNULL(AMOUNT)" in exp_calc.expressions[0].raw

    def test_rejects_non_powercenter_xml(self, tmp_path):
        bad = tmp_path / "bad.xml"
        bad.write_text("<html></html>")
        with pytest.raises(PowerCenterParseError):
            PowerCenterParser().parse_file(bad)


class TestRulesMapper:
    def test_maps_known_types(self, pipeline):
        RulesMapper().apply(pipeline)
        assert pipeline.step("AGG_SALES").pdi_type == "GroupBy"
        assert pipeline.step("SQ_SALES").pdi_type == "TableInput"

    def test_expressions_downgrade_auto_to_review(self, pipeline):
        RulesMapper().apply(pipeline)
        # Aggregator rule is AUTO, but AGG_SALES carries an untranslated SUM()
        assert pipeline.step("AGG_SALES").confidence == Confidence.REVIEW

    def test_unknown_type_marked_manual(self, pipeline):
        pipeline.steps[0].source_type = "Custom Transformation"
        RulesMapper().apply(pipeline)
        assert pipeline.steps[0].confidence == Confidence.MANUAL
        assert pipeline.steps[0].pdi_type is None


class TestGenerator:
    def test_emits_wellformed_ktr_with_steps_and_hops(self, pipeline):
        RulesMapper().apply(pipeline)
        root = ElementTree.fromstring(KtrGenerator().generate(pipeline))
        assert root.tag == "transformation"
        types = {s.findtext("name"): s.findtext("type") for s in root.iter("step")}
        assert types["AGG_SALES"] == "GroupBy"
        assert len(root.findall("order/hop")) == 4

    def test_todo_expressions_land_in_description(self, pipeline):
        RulesMapper().apply(pipeline)
        root = ElementTree.fromstring(KtrGenerator().generate(pipeline))
        exp = next(s for s in root.iter("step") if s.findtext("name") == "EXP_CALC")
        assert "TODO expression [AMOUNT_TAXED]" in exp.findtext("description")

    def test_table_input_gets_generated_sql(self, pipeline):
        RulesMapper().apply(pipeline)
        root = ElementTree.fromstring(KtrGenerator().generate(pipeline))
        sq = next(s for s in root.iter("step") if s.findtext("name") == "SQ_SALES")
        assert "SELECT REGION, AMOUNT" in sq.findtext("sql")

    def test_group_by_emits_keys_and_aggregates(self, pipeline):
        RulesMapper().apply(pipeline)
        root = ElementTree.fromstring(KtrGenerator().generate(pipeline))
        agg = next(s for s in root.iter("step") if s.findtext("name") == "AGG_SALES")
        group_keys = [f.findtext("name") for f in agg.findall("group/field")]
        assert group_keys == ["REGION"]
        aggregate = agg.find("fields/field")
        assert aggregate.findtext("aggregate") == "TOTAL_AMOUNT"
        assert aggregate.findtext("subject") == "AMOUNT_TAXED"
        assert aggregate.findtext("type") == "SUM"

    def test_script_step_carries_todo_script_and_output_fields(self, pipeline):
        RulesMapper().apply(pipeline)
        root = ElementTree.fromstring(KtrGenerator().generate(pipeline))
        exp = next(s for s in root.iter("step") if s.findtext("name") == "EXP_CALC")
        script = exp.findtext("jsScripts/jsScript/jsScript_script")
        assert "TODO translate: AMOUNT_TAXED" in script
        field = exp.find("fields/field")
        assert field.findtext("name") == "AMOUNT_TAXED"
        assert field.findtext("type") == "Number"


class TestReport:
    def test_counts_by_confidence(self, pipeline):
        RulesMapper().apply(pipeline)
        report = build_report(pipeline)
        assert report.total_steps == 5
        assert report.auto + report.review + report.manual == 5
        assert report.untranslated_expressions == 2
