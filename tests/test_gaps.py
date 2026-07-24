"""Gap-report aggregation over mapped pipelines."""

from pathlib import Path

from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import PowerCenterParser
from pentaho_migration.validator import build_gap_report

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"


def test_gap_report_counts_and_orders_unmapped_first():
    mapper = RulesMapper()
    pipelines = [mapper.apply(p) for p in PowerCenterParser().parse_file(SAMPLE)]
    pipelines[0].steps[0].source_type = "Custom Widget"
    pipelines[0].steps[0].pdi_type = None
    mapper.apply(pipelines[0])

    report = build_gap_report(pipelines)
    assert report.mappings == 1
    assert report.steps == 5
    assert report.auto + report.review + report.manual == 5
    # unmapped types sort to the top of the coverage list
    assert report.types[0].source_type == "Custom Widget"
    assert report.types[0].pdi_type is None
