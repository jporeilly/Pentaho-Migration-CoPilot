"""Impact analysis knowledge application + migration confidence score."""

from pathlib import Path

from fastapi.testclient import TestClient

from pdi_migration.api.main import app
from pdi_migration.ir import Confidence
from pdi_migration.mapper import RulesMapper
from pdi_migration.parser import PowerCenterParser
from pdi_migration.validator import build_impact_analysis, build_score

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"


def _mapped():
    (pipeline,) = PowerCenterParser().parse_file(SAMPLE)
    return RulesMapper().apply(pipeline)


class TestImpact:
    def test_every_step_gets_an_entry(self):
        pipeline = _mapped()
        impact = build_impact_analysis(pipeline)
        assert len(impact.entries) == len(pipeline.steps)

    def test_aggregator_flagged_high_with_sort_requirement(self):
        impact = build_impact_analysis(_mapped())
        agg = next(e for e in impact.entries if e.step == "AGG_SALES")
        assert agg.impact == "high"
        assert any("sorted" in d.lower() for d in agg.differences)
        assert any("Sort rows" in a for a in agg.actions)

    def test_entries_sorted_highest_impact_first(self):
        impact = build_impact_analysis(_mapped())
        order = {"high": 3, "medium": 2, "low": 1, "none": 0}
        values = [order[e.impact] for e in impact.entries]
        assert values == sorted(values, reverse=True)

    def test_top_risks_mention_sorting_and_nulls(self):
        impact = build_impact_analysis(_mapped())
        risks = " ".join(impact.summary.top_risks).lower()
        assert "sort" in risks
        assert "null" in risks

    def test_unmapped_step_gets_high_impact(self):
        pipeline = _mapped()
        pipeline.steps[0].source_type = "Custom Widget"
        pipeline.steps[0].pdi_type = None
        impact = build_impact_analysis(pipeline)
        entry = next(e for e in impact.entries if e.source_type == "Custom Widget")
        assert entry.impact == "high"


class TestScore:
    def test_score_shape_and_bounds(self):
        pipeline = _mapped()
        score = build_score(pipeline, build_impact_analysis(pipeline))
        assert 0 <= score.score <= 100
        assert score.grade in "ABCDE"
        assert score.is_static
        assert len(score.factors) == 4
        assert abs(sum(f.weight for f in score.factors) - 1.0) < 1e-9

    def test_translation_improves_score(self):
        pipeline = _mapped()
        before = build_score(pipeline, build_impact_analysis(pipeline)).score
        for step in pipeline.steps:
            for expr in step.expressions:
                expr.translated = "1"
                expr.confidence = Confidence.REVIEW
        after = build_score(pipeline, build_impact_analysis(pipeline)).score
        assert after > before


def test_convert_response_includes_impact_and_score():
    client = TestClient(app)
    with open(SAMPLE, "rb") as f:
        res = client.post("/convert", files={"export": ("m_load_sales.xml", f, "text/xml")})
    assert res.status_code == 200
    (result,) = res.json()["results"]
    assert result["score"]["grade"] in "ABCDE"
    assert result["impact"]["entries"]


def test_best_practices_endpoint():
    client = TestClient(app)
    res = client.get("/best-practices")
    assert res.status_code == 200
    assert "Best Practices" in res.text