"""The ETL review agent + per-mapping consultant report (task #42).

The Crystal release gate's counterpart for transformations: every check
deterministic, the verdict decided by error findings alone, the LLM only
ever annotating. The lint targets the CONVERTED graph - the tests build
small pipelines that carry one defect each, plus the real walkthrough
sample end-to-end through the API."""

import pytest

from pentaho_migration.ir import Confidence, Expression, Hop, Pipeline, SourceTool, Step
from pentaho_migration.validator.review import EtlReviewCheck, review_pipeline


def _step(name, source_type="Expression", pdi_type="ScriptValueMod",
          confidence=Confidence.AUTO, expressions=()):
    return Step(name=name, source_type=source_type, pdi_type=pdi_type,
                confidence=confidence, expressions=list(expressions))


def _pipe(steps, hops=()):
    return Pipeline(name="p", source_tool=SourceTool.POWERCENTER,
                    steps=steps, hops=[Hop(from_step=a, to_step=b)
                                       for a, b in hops])


class TestDeterministicChecks:
    def test_a_clean_wired_pipeline_ships(self):
        check = review_pipeline(_pipe(
            [_step("src", "Source", "TableInput"),
             _step("tgt", "Target", "TableOutput")],
            [("src", "tgt")]))
        assert check.verdict == "SHIP"
        assert not [f for f in check.findings if f.severity == "error"]

    def test_unmapped_steps_block_release_grouped_by_type(self):
        check = review_pipeline(_pipe(
            [_step("a", "Custom Widget", None, Confidence.MANUAL),
             _step("b", "Custom Widget", None, Confidence.MANUAL),
             _step("c", "Source", "TableInput")],
            [("c", "a"), ("a", "b")]))
        assert check.verdict == "REVIEW"
        finding = next(f for f in check.findings if f.code == "unmapped-steps")
        # one finding per TYPE, not per step - one kind of work, one row
        assert "2 step(s)" in finding.message
        assert finding.evidence == ["a", "b"]
        assert "Suggested approach" in finding.message

    def test_untranslated_expressions_are_an_error(self):
        expr = Expression(field="OUT", raw="IIF(X>1, 1, 0)")
        check = review_pipeline(_pipe(
            [_step("e", expressions=[expr]),
             _step("s", "Source", "TableInput")], [("s", "e")]))
        finding = next(f for f in check.findings if f.code == "expressions")
        assert finding.severity == "error"
        assert "e.OUT" in finding.evidence

    def test_translated_expressions_downgrade_to_verification(self):
        expr = Expression(field="OUT", raw="IIF(X>1,1,0)", translated="X>1?1:0")
        check = review_pipeline(_pipe(
            [_step("e", expressions=[expr]),
             _step("s", "Source", "TableInput")], [("s", "e")]))
        assert check.verdict == "SHIP"      # verification is not a blocker
        finding = next(f for f in check.findings
                       if f.code == "expressions-review")
        assert finding.severity == "warning"

    def test_dangling_hop_is_an_error(self):
        check = review_pipeline(_pipe(
            [_step("a"), _step("b")], [("a", "ghost")]))
        finding = next(f for f in check.findings if f.code == "hops"
                       and f.severity == "error")
        assert "a -> ghost" in finding.evidence

    def test_isolated_step_is_flagged(self):
        check = review_pipeline(_pipe(
            [_step("a"), _step("b"), _step("island")], [("a", "b")]))
        finding = next(f for f in check.findings if f.code == "hops")
        assert "island" in finding.evidence

    def test_group_by_without_sort_is_the_silent_wrong_results_error(self):
        check = review_pipeline(_pipe(
            [_step("src", "Source", "TableInput"),
             _step("agg", "Aggregator", "GroupBy")],
            [("src", "agg")]))
        finding = next(f for f in check.findings if f.code == "sorted-input")
        assert finding.severity == "error"
        assert "silently wrong" in finding.message
        assert check.verdict == "REVIEW"

    def test_a_sorter_upstream_clears_the_hazard(self):
        check = review_pipeline(_pipe(
            [_step("src", "Source", "TableInput"),
             _step("sort", "Sorter", "SortRows"),
             _step("agg", "Aggregator", "GroupBy")],
            [("src", "sort"), ("sort", "agg")]))
        assert not [f for f in check.findings if f.code == "sorted-input"]

    def test_another_aggregation_between_does_not_carry_the_guarantee(self):
        # sort -> GROUP BY -> group by: the second one re-groups an
        # already-aggregated stream whose order the first does not promise
        check = review_pipeline(_pipe(
            [_step("sort", "Sorter", "SortRows"),
             _step("agg1", "Aggregator", "GroupBy"),
             _step("agg2", "Aggregator", "GroupBy")],
            [("sort", "agg1"), ("agg1", "agg2")]))
        hazards = next(f for f in check.findings if f.code == "sorted-input")
        assert any("agg2" in e for e in hazards.evidence)

    def test_placeholder_connections_are_info_not_defect(self):
        check = review_pipeline(_pipe(
            [_step("src", "Source", "TableInput"),
             _step("tgt", "Target", "TableOutput")], [("src", "tgt")]),
            ktr="<transformation><connection/></transformation>")
        finding = next(f for f in check.findings if f.code == "connections")
        assert finding.severity == "info"
        assert check.verdict == "SHIP"

    def test_findings_sort_errors_first(self):
        expr = Expression(field="OUT", raw="x")
        check = review_pipeline(_pipe(
            [_step("agg", "Aggregator", "GroupBy", expressions=[expr]),
             _step("island")], []),
            ktr="<t><connection/></t>")
        severities = [f.severity for f in check.findings]
        assert severities == sorted(
            severities, key=lambda s: {"error": 0, "warning": 1, "info": 2}[s])


class TestParityFoldIn:
    def _diff(self, parity, row_match=True):
        from pentaho_migration.validator.diff import DiffReport

        return DiffReport(
            expected_rows=10, actual_rows=10 if row_match else 8,
            row_count_match=row_match, compared_rows=10,
            matching_rows=int(parity * 10), mismatched_rows=0,
            parity=parity, verdict="x")

    def test_measured_pass_is_info(self):
        check = review_pipeline(_pipe([_step("a")], []), diff=self._diff(1.0))
        finding = next(f for f in check.findings if f.code == "parity")
        assert finding.severity == "info"

    def test_measured_failure_blocks(self):
        check = review_pipeline(_pipe([_step("a")], []), diff=self._diff(0.4))
        finding = next(f for f in check.findings if f.code == "parity")
        assert finding.severity == "error"
        assert check.verdict == "REVIEW"


class TestConsultantReport:
    def _fixture(self):
        from pentaho_migration.generator import KtrGenerator
        from pentaho_migration.mapper import RulesMapper
        from pentaho_migration.parser import detect_parser
        from pentaho_migration.validator import (
            build_effort, build_impact_analysis, build_report, build_score)
        from pathlib import Path

        sample = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"
        pipeline = detect_parser(sample).parse_file(sample)[0]
        RulesMapper.for_pipeline(pipeline).apply(pipeline)
        report = build_report(pipeline)
        impact = build_impact_analysis(pipeline)
        return (pipeline, report, build_score(pipeline, impact),
                build_effort(pipeline, report), impact,
                KtrGenerator().generate(pipeline))

    def test_html_leads_with_the_costed_plan(self):
        from pentaho_migration.etl_consultant import (
            build_etl_consultant_report_html)

        pipeline, report, score, effort, impact, ktr = self._fixture()
        check = review_pipeline(pipeline, ktr=ktr)
        html = build_etl_consultant_report_html(
            pipeline, report, score, effort, check, rate=150.0, impact=impact)
        assert "Action plan" in html
        assert "Informatica PowerCenter" in html
        assert "REVIEW" in html
        # shares the Crystal consultant stylesheet - one house style
        assert "--navy: #133346" in html
        assert "to finish this mapping" in html

    def test_markdown_and_html_carry_the_same_plan(self):
        from pentaho_migration.etl_consultant import (
            build_etl_action_plan, build_etl_consultant_report_markdown)

        pipeline, report, score, effort, impact, ktr = self._fixture()
        check = review_pipeline(pipeline, ktr=ktr)
        md = build_etl_consultant_report_markdown(
            pipeline, report, score, effort, check)
        for action in build_etl_action_plan(pipeline, check):
            assert action.title in md

    def test_sorted_input_finding_becomes_a_p1_action(self):
        from pentaho_migration.etl_consultant import build_etl_action_plan

        pipeline = _pipe(
            [_step("src", "Source", "TableInput"),
             _step("agg", "Aggregator", "GroupBy")], [("src", "agg")])
        check = review_pipeline(pipeline)
        plan = build_etl_action_plan(pipeline, check)
        action = next(a for a in plan if "Sort rows" in a.title)
        assert action.priority == 1
        assert action.hours > 0

    def test_a_clean_mapping_reports_nothing_outstanding(self):
        from pentaho_migration.etl_consultant import (
            build_etl_consultant_report_html)
        from pentaho_migration.validator import (
            build_effort, build_impact_analysis, build_report, build_score)

        pipeline = _pipe(
            [_step("src", "Source", "TableInput"),
             _step("tgt", "Target", "TableOutput")], [("src", "tgt")])
        check = review_pipeline(pipeline)
        report = build_report(pipeline)
        impact = build_impact_analysis(pipeline)
        html = build_etl_consultant_report_html(
            pipeline, report, build_score(pipeline, impact),
            build_effort(pipeline, report), check)
        assert "SHIP" in html
        assert "Nothing outstanding" in html


class TestJobStore:
    def test_staged_job_lifecycle(self):
        import time

        from pentaho_migration.jobs import JobStore

        store = JobStore()
        job_id, job = store.start(stages=["one", "two", "done"])
        assert store.get(job_id)["stage"] == "one"

        def work():
            job["stage"] = "two"
            job["result"] = 42

        store.run(job, work)
        for _ in range(50):
            if store.get(job_id)["status"] != "running":
                break
            time.sleep(0.05)
        state = store.get(job_id)
        assert state["status"] == "done"
        assert state["stage"] == "done"
        assert state["result"] == 42
        assert "created" not in state       # bookkeeping stays internal

    def test_a_raising_worker_becomes_an_error_status(self):
        import time

        from pentaho_migration.jobs import JobStore

        store = JobStore()
        job_id, job = store.start()

        def work():
            raise RuntimeError("boom")

        store.run(job, work)
        for _ in range(50):
            if store.get(job_id)["status"] != "running":
                break
            time.sleep(0.05)
        state = store.get(job_id)
        assert state["status"] == "error"
        assert "boom" in state["detail"]

    def test_a_worker_that_set_its_own_error_is_left_alone(self):
        import time

        from pentaho_migration.jobs import JobStore

        store = JobStore()
        job_id, job = store.start()

        def work():
            job["status"] = "error"
            job["detail"] = "handled internally"

        store.run(job, work)
        time.sleep(0.2)
        assert store.get(job_id)["status"] == "error"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PENTAHO_MIGRATION_CONFIG_DIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from pentaho_migration.api.main import app

    return TestClient(app, client=("127.0.0.1", 12345))


def _wait(client, url, tries=200):
    import time

    for _ in range(tries):
        state = client.get(url).json()
        if state["status"] != "running":
            return state
        time.sleep(0.05)
    raise AssertionError("job never finished")


class TestReviewEndpoint:
    def test_the_full_flow_on_the_walkthrough_sample(self, client):
        from pathlib import Path

        sample = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"
        result = client.post(
            "/convert",
            files={"export": ("m_load_sales.xml", sample.read_bytes())},
        ).json()["results"][0]

        started = client.post("/review/start", json={
            "pipeline": result["pipeline"], "ktr": result["ktr"],
            "llm": False})
        assert started.status_code == 200
        state = _wait(client, f"/review/status?job={started.json()['job']}")
        assert state["status"] == "done", state.get("detail")
        res = state["result"]
        assert res["verdict"] in ("SHIP", "REVIEW")
        assert res["checks_run"]
        assert "consultant_report_html" in res
        assert "Action plan" in res["consultant_report_html"]

    def test_staged_convert_returns_the_same_shape(self, client):
        from pathlib import Path

        sample = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"
        started = client.post(
            "/convert/start",
            files={"export": ("m_load_sales.xml", sample.read_bytes())})
        state = _wait(client, f"/convert/status?job={started.json()['job']}")
        assert state["status"] == "done", state.get("detail")
        assert state["result"]["results"][0]["ktr"].startswith("<?xml")
        assert state["total"] == 1 and state["done"] == 1

    def test_unknown_job_is_404(self, client):
        assert client.get("/review/status?job=nope").status_code == 404


class TestEtlReviewSweep:
    def test_sweep_persists_verdicts_in_an_isolated_store(self, client):
        from pathlib import Path

        from pentaho_migration.project import MappingRecord, list_mappings, record_mapping

        sample = Path(__file__).resolve().parents[1] / "samples" / "m_load_sales.xml"
        record_mapping(MappingRecord(
            mapping="m_load_sales", file="m_load_sales.xml",
            source_path=str(sample), steps=6, auto=4, review=1, manual=1,
            expressions=2, score=70, grade="B", status="converted",
            updated_at=""))

        started = client.post("/project/etl-review/start")
        assert started.status_code == 200
        state = _wait(client, f"/project/sweep/status?job={started.json()['job']}")
        assert state["status"] == "done", state.get("detail")

        stored = list_mappings()[0]
        assert stored.review_verdict in ("SHIP", "REVIEW")
        assert "checks_run" in stored.review_json
        # the job result carries the refreshed rows for the UI
        assert state["result"][0]["review_verdict"] == stored.review_verdict

    def test_a_missing_source_still_gets_an_honest_verdict(self, client):
        from pentaho_migration.project import MappingRecord, list_mappings, record_mapping

        record_mapping(MappingRecord(
            mapping="ghost", file="gone.xml",
            source_path="C:/nowhere/gone.xml", steps=1, auto=1, review=0,
            manual=0, expressions=0, score=90, grade="A",
            status="converted", updated_at=""))
        started = client.post("/project/etl-review/start")
        state = _wait(client, f"/project/sweep/status?job={started.json()['job']}")
        assert state["status"] == "done"
        stored = next(r for r in list_mappings() if r.mapping == "ghost")
        assert stored.review_verdict == "REVIEW"
        assert "not found" in stored.review_json
