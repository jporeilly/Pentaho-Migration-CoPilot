"""Estate triage: point at a folder of .xactions, get the measured T&M model.
Corpus-driven against samples/xactions - the same files the parsers were
built on, so the distribution asserted here is the one the demos show.
"""

from pathlib import Path

from pentaho_migration.reports.xaction_triage import (
    LOE_HOURS, build_xaction_estate_report_html, triage_estate)

# corpus1 only: corpus2 (the 126-report second harvest) has its own
# gap-report sweep and would drift these distribution assertions
ESTATE = Path("samples/xactions/corpus")


def _records():
    return triage_estate(ESTATE)


class TestTriageEstate:
    def test_nothing_is_skipped_silently(self):
        records = _records()
        assert len(records) == 36
        kinds = {r.kind for r in records}
        assert "report" in kinds and "chart" in kinds

    def test_the_corpus_distribution(self):
        reports = [r for r in _records() if r.kind == "report"]
        grades = {g: sum(1 for r in reports if r.grade == g)
                  for g in ("Low", "Medium", "High")}
        assert len(reports) == 25
        assert grades == {"Low": 5, "Medium": 16, "High": 4}

    def test_hours_follow_the_grade_bands(self):
        for r in _records():
            if r.kind != "report":
                assert r.copilot_hours == 0.0
                continue
            copilot, manual, _a, _m = LOE_HOURS[r.grade]
            assert (r.copilot_hours, r.manual_hours) == (copilot, manual)
            assert r.manual_hours > r.copilot_hours

    def test_definition_status_is_classified(self):
        reports = [r for r in _records() if r.kind == "report"]
        statuses = {r.definition for r in reports}
        assert "simple" in statuses and "legacy-ext" in statuses

    def test_an_unparsable_file_is_a_record_not_a_crash(self, tmp_path):
        (tmp_path / "broken.xaction").write_text("<action-sequence>",
                                                 encoding="utf-8")
        records = triage_estate(tmp_path)
        assert [r.kind for r in records] == ["unparsable"]


class TestEstateReportHtml:
    def test_the_house_sections_render(self):
        html = build_xaction_estate_report_html(_records(), rate=150.0,
                                                estate_label="corpus")
        for section in ("Executive summary", "Complexity distribution",
                        "Priority actions across the estate",
                        "Level-of-Effort bands"):
            assert section in html
        assert "Low: 5" in html and "High: 4" in html
        # the 4 legacy-EXT definitions now TRANSLATE - the action is a
        # review sign-off, not a rebuild
        assert "Review the legacy-EXT conversions" in html
        assert "Rebuild legacy-EXT" not in html
        assert "1-2h" in html and "16-40h" in html   # the published bands

    def test_an_estate_with_no_reports_is_honest(self, tmp_path):
        (tmp_path / "chart.xaction").write_text(
            "<action-sequence><name>c</name><actions><action-definition>"
            "<component-name>ChartComponent</component-name>"
            "</action-definition></actions></action-sequence>",
            encoding="utf-8")
        html = build_xaction_estate_report_html(triage_estate(tmp_path))
        assert "nothing beyond the per-report conversion work" in html
