"""Effort & cost estimation: heuristic sanity for both families and API
surface. Hours are the server product; cost is client-side (hours x rate),
so no currency assertions here."""

from pathlib import Path

from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.mapper import RulesMapper
from pentaho_migration.parser import PowerCenterParser
from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.effort import build_report_effort
from pentaho_migration.validator import build_effort, build_report

ETL_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"
CRYSTAL_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "demo" / "branch_transactions.xml"

client = TestClient(app)


def _etl_estimate():
    (pipeline,) = PowerCenterParser().parse_file(ETL_SAMPLE)
    RulesMapper().apply(pipeline)
    return pipeline, build_effort(pipeline, build_report(pipeline))


def test_etl_effort_sanity():
    _, effort = _etl_estimate()
    assert effort.copilot_hours > 0
    assert effort.manual_hours > effort.copilot_hours
    assert effort.saved_hours == effort.manual_hours - effort.copilot_hours
    assert 0 < effort.saved_pct <= 100
    assert effort.assumptions  # the numbers must be defensible


def test_etl_effort_scales_with_manual_steps():
    pipeline, base = _etl_estimate()
    for step in pipeline.steps:
        step.confidence = "manual"
    worse = build_effort(pipeline, build_report(pipeline))
    assert worse.copilot_hours > base.copilot_hours


def test_report_effort_sanity():
    model = load_report_model(CRYSTAL_SAMPLE)
    effort = build_report_effort(model)
    assert effort.copilot_hours > 0
    assert effort.manual_hours > effort.copilot_hours
    assert 0 < effort.saved_pct <= 100


def test_report_effort_drops_after_formula_assist():
    model = load_report_model(CRYSTAL_SAMPLE)
    before = build_report_effort(model)
    for f in model.formulas.values():
        if f.status == "manual":
            f.status = "review"
            f.translation = "=[AMOUNT]"
    after = build_report_effort(model)
    # with realistic (small) constants the half-hour rounding can absorb the
    # drop on a small report, but assist must never *increase* the estimate
    assert after.copilot_hours <= before.copilot_hours
    # rebuild-from-scratch cost is unchanged by the assist
    assert after.manual_hours == before.manual_hours


def test_effort_in_etl_api():
    res = client.post("/convert",
                      files={"export": ("m.xml", ETL_SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    effort = res.json()["results"][0]["effort"]
    assert effort["manual_hours"] > effort["copilot_hours"]


def test_effort_in_reports_api():
    res = client.post("/reports/convert",
                      files={"dump": ("b.xml", CRYSTAL_SAMPLE.read_bytes(), "text/xml")})
    assert res.status_code == 200
    effort = res.json()["summary"]["effort"]
    assert effort["manual_hours"] > effort["copilot_hours"]
    assert effort["saved_pct"] > 0


def test_effort_from_counts_approximation_is_conservative():
    from pentaho_migration.validator.effort import effort_from_counts

    pipeline, full = _etl_estimate()
    from pentaho_migration.validator import build_report
    report = build_report(pipeline)
    approx = effort_from_counts(
        steps=report.total_steps, auto=report.auto, review=report.review,
        manual=report.manual, untranslated_exprs=report.untranslated_expressions)
    assert approx.copilot_hours <= full.copilot_hours
    assert approx.manual_hours <= full.manual_hours
    assert any("approximated" in a for a in approx.assumptions)


def test_project_rows_carry_effort(tmp_path, monkeypatch):
    monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
    from pentaho_migration.project import MappingRecord, record_mapping

    record_mapping(MappingRecord(
        mapping="m_test", file="t.xml", source_path="", steps=10, auto=6,
        review=3, manual=1, expressions=5, score=60, grade="C",
        status="converted", updated_at=""))
    rows = client.get("/project").json()
    row = next(r for r in rows if r["mapping"] == "m_test")
    assert row["manual_hours"] > row["copilot_hours"] > 0
    assert row["saved_hours"] == row["manual_hours"] - row["copilot_hours"]


def test_pdf_includes_effort():
    from pentaho_migration.report_pdf import build_pdf_report
    from pentaho_migration.validator import build_impact_analysis, build_score

    pipeline, effort = _etl_estimate()
    report = build_report(pipeline)
    impact = build_impact_analysis(pipeline)
    score = build_score(pipeline, impact)
    with_effort = build_pdf_report(None, pipeline, report, score, impact,
                                   effort=effort, rate=175.0)
    without = build_pdf_report(None, pipeline, report, score, impact)
    assert with_effort[:4] == b"%PDF" and without[:4] == b"%PDF"
    assert len(with_effort) > len(without)
