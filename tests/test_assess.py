"""Source analysis + pre-migration warnings, exercised on a real HHS export."""

from pathlib import Path

from pentaho_migration.ir import WarningLevel
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import PowerCenterParser
from pentaho_migration.validator import assess_source

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
HHS_COMPTIME = SAMPLES / "informatica" / "hhs_comptime.xml"


def _assessed(path):
    parser = PowerCenterParser()
    mapper = RulesMapper()
    pipelines = [mapper.apply(p) for p in parser.parse_file(path)]
    return assess_source(parser.analyze_export(path), pipelines)


def test_analyze_reads_version_and_counts():
    source = _assessed(HHS_COMPTIME)
    assert source.repository_version == "187.96"
    assert source.product_version == "10.4.0"
    assert source.mappings == 3
    assert source.workflows >= 1


def test_workflow_warning_raised():
    source = _assessed(HHS_COMPTIME)
    texts = [w.text for w in source.warnings if w.level == WarningLevel.WARNING]
    assert any("workflow" in t for t in texts)


def test_demo_sample_has_no_serious_warnings():
    source = _assessed(SAMPLES / "m_load_sales.xml")
    assert not [w for w in source.warnings if w.level == WarningLevel.SERIOUS]
    # but the untranslated expressions are surfaced as info
    assert any("expression" in w.text for w in source.warnings)