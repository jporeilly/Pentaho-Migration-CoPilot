"""Layout QA agent (geometry lint) and batch triage agent (verdicts +
markdown report). Deterministic throughout; the LLM brief is mocked."""

import json
from pathlib import Path

from pentaho_migration.llm.settings import LLMSettings
from pentaho_migration.reports import triage as triage_mod
from pentaho_migration.reports.layout_qa import lint_layout, usable_page_width
from pentaho_migration.reports.model import Element, PageSetup, ReportModel, Section
from pentaho_migration.reports.triage import (
    build_triage_report, llm_brief, triage_corpus, triage_one)

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
LADDER = SAMPLES / "cr_demo"


def _model(*elements, height=30.0):
    m = ReportModel(name="t")
    m.page = PageSetup(paper="A4", orientation="landscape")
    m.sections.append(Section(area_kind="Detail", height=height,
                              elements=list(elements)))
    return m


def test_usable_width_a4_landscape():
    assert usable_page_width(PageSetup(paper="A4", orientation="landscape")) == 806.0


def test_lint_flags_page_overflow_and_band_overflow():
    qa = lint_layout(_model(
        Element(kind="field", name="Wide", x=500, y=0, width=400, height=14),
        Element(kind="field", name="Tall", x=0, y=20, width=100, height=20)))
    codes = {f.code for f in qa.findings}
    assert "page-overflow" in codes and "band-overflow" in codes
    assert len(qa.errors) == 1     # overflow is the error; band clip is a warning


def test_lint_flags_overlap_font_clip_and_chart_columns():
    a = Element(kind="field", name="A", x=0, y=0, width=100, height=14)
    b = Element(kind="field", name="B", x=10, y=0, width=100, height=14)
    tiny = Element(kind="label", name="Big", text="X", x=200, y=0, width=50, height=10)
    tiny.font.size = 14
    chart = Element(kind="chart", name="C", x=300, y=0, width=100, height=20)
    qa = lint_layout(_model(a, b, tiny, chart))
    codes = {f.code for f in qa.findings}
    assert {"overlap", "font-clip", "chart-columns"} <= codes


def test_lint_skips_suppressed_bands_and_decor():
    m = _model(Element(kind="box", name="Fill", x=0, y=0, width=900, height=30))
    m.sections[0].suppressed = True
    assert lint_layout(m).findings == []


def test_demo_ladder_is_layout_clean():
    """The QA agent found real overflows in the authored demos (TotRule at
    900pt on an 806pt page); they are fixed - only intentional TODO
    placeholders may remain, never geometry errors."""
    from pentaho_migration.reports import load_report_model

    for dump in sorted(LADDER.glob("0*.xml")):
        qa = lint_layout(load_report_model(dump))
        assert qa.errors == [], f"{dump.name}: {[f.message for f in qa.errors]}"
        assert qa.warnings == [], f"{dump.name}: {[f.message for f in qa.warnings]}"


# ------------------------------------------------------------------ triage

def test_triage_roster_is_ready_without_db():
    r = triage_one(LADDER / "01_member_roster.xml", check_sql=False)
    assert r.verdict == "READY"
    assert r.todos == 0            # embedded logo is migrated, not a TODO
    assert r.sql_status == "unchecked"


def test_triage_statement_needs_review_for_the_rewrite():
    r = triage_one(LADDER / "04_member_statement.xml", check_sql=False)
    assert r.verdict == "REVIEW"
    assert r.rewrites == 1
    assert any("idiom rewrite" in reason for reason in r.reasons)


def test_triage_parse_failure_is_blocked(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("this is not a report", encoding="utf-8")
    r = triage_one(bad)
    assert r.verdict == "BLOCKED"
    assert r.parse_error


def test_triage_invalid_sql_is_blocked(monkeypatch):
    monkeypatch.setattr(
        triage_mod, "validate_sql",
        lambda jndi, sql, params: {"ok": False, "error": "no such column",
                                   "checked_sql": "EXPLAINABLE"})
    r = triage_one(LADDER / "01_member_roster.xml", jndi="CSCU")
    assert r.verdict == "BLOCKED"
    assert r.sql_status == "invalid"


def test_triage_db_unreachable_is_not_blocking(monkeypatch):
    monkeypatch.setattr(
        triage_mod, "validate_sql",
        lambda jndi, sql, params: {"ok": False, "error": "cannot connect",
                                   "checked_sql": ""})
    r = triage_one(LADDER / "01_member_roster.xml", jndi="CSCU")
    assert r.sql_status == "unchecked"
    assert r.verdict == "READY"    # the report is not at fault


def test_triage_report_markdown():
    results = triage_corpus(LADDER, check_sql=False)
    assert len(results) == 6
    md = build_triage_report(results, jndi="")
    assert md.startswith("# Migration Triage Report")
    assert "READY 3 | REVIEW 3 | BLOCKED 0" in md
    assert "Member Statement" in md
    assert "## Needs review" in md


def test_llm_brief_mocked(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": json.dumps(
                {"brief": "Check the running-total rewrite first."})}}

    def fake_post(url, json=None, timeout=None):
        captured["payload"] = json
        return _Resp()

    monkeypatch.setattr(triage_mod.httpx, "post", fake_post)
    r = triage_one(LADDER / "04_member_statement.xml", check_sql=False)
    brief = llm_brief(r, LLMSettings(provider="ollama", model="test"))
    assert brief == "Check the running-total rewrite first."
    sent = captured["payload"]["messages"][1]["content"]
    assert "idiom_rewrites" in sent and "Member Statement" in sent
