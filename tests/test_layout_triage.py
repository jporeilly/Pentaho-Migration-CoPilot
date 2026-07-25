"""Layout QA agent (geometry lint) and batch triage agent (verdicts +
markdown report). Deterministic throughout; the LLM brief is mocked."""

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


def test_autofit_scales_overflowing_band_to_printable_width():
    """User ask: 'can't the agent adjust printable widths?' - page-overflow
    is repaired deterministically by proportional band scaling."""
    from pentaho_migration.reports.layout_qa import autofit_layout

    wide = Element(kind="field", name="Wide", x=500, y=0, width=400, height=14)
    ok = Element(kind="label", name="Ok", text="x", x=0, y=0, width=100, height=14)
    m = _model(wide, ok)                      # A4 landscape: printable 806pt
    assert autofit_layout(m) == 1
    factor = 806.0 / 900.0
    assert abs((wide.x + wide.width) - 806.0) < 0.5
    assert abs(ok.width - 100 * factor) < 0.5  # whole band scales together
    assert any("auto-fit" in i for i in m.issues)
    assert not [f for f in lint_layout(m).findings if f.code == "page-overflow"]


def test_autofit_nudges_overlapping_text_apart():
    """User ask: overlapping text should be spaced out and aligned - the
    later element (reading order) moves right or down, minimally."""
    from pentaho_migration.reports.layout_qa import autofit_layout

    a = Element(kind="field", name="A", x=0, y=0, width=100, height=14)
    b = Element(kind="field", name="B", x=10, y=0, width=100, height=14)   # same row
    c = Element(kind="label", name="C", text="x", x=0, y=4, width=100, height=14)  # stacked
    m = _model(a, b, c)
    assert autofit_layout(m) >= 1
    qa = lint_layout(m)
    assert not [f for f in qa.findings if f.code == "overlap"]
    assert b.x >= a.x + a.width          # pushed right, order kept
    assert c.y >= a.y + a.height         # pushed down
    assert any("nudged apart" in i for i in m.issues)


def test_autofit_never_moves_conditionally_visible_alternates():
    """Crystal stacks mutually-exclusive fields (one visible at runtime via a
    suppression condition) - those must stay exactly where they are."""
    from pentaho_migration.reports.layout_qa import autofit_layout

    a = Element(kind="field", name="A", x=0, y=0, width=100, height=14)
    b = Element(kind="field", name="B", x=0, y=0, width=100, height=14)
    b.style_expressions.append(("visible", "=[MODE] = \"B\""))
    m = _model(a, b)
    autofit_layout(m)
    assert (b.x, b.y) == (0, 0)          # untouched - it's a stacked alternate


def test_autofit_leaves_fitting_and_suppressed_bands_alone():
    from pentaho_migration.reports.layout_qa import autofit_layout

    fits = Element(kind="field", name="F", x=0, y=0, width=300, height=14)
    m = _model(fits)
    assert autofit_layout(m) == 0
    assert fits.width == 300
    wide = Element(kind="field", name="W", x=0, y=0, width=900, height=14)
    m2 = _model(wide)
    m2.sections[0].suppressed = True
    assert autofit_layout(m2) == 0             # suppressed bands never print


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
    assert len(results) == 9
    md = build_triage_report(results, jndi="")
    assert md.startswith("# Migration Triage Report")
    assert "READY 6 | REVIEW 3 | BLOCKED 0" in md
    assert "Member Statement" in md
    assert "## Needs review" in md


def test_llm_brief_mocked(monkeypatch):
    """The brief goes through the shared provider dispatch (chat_json)."""
    captured = {}

    def fake_chat_json(settings, messages, schema, timeout=120.0):
        captured["messages"] = messages
        return {"brief": "Check the running-total rewrite first."}

    monkeypatch.setattr("pentaho_migration.llm.translate.chat_json", fake_chat_json)
    r = triage_one(LADDER / "04_member_statement.xml", check_sql=False)
    brief = llm_brief(r, LLMSettings(provider="ollama", model="test"))
    assert brief == "Check the running-total rewrite first."
    sent = captured["messages"][1]["content"]
    assert "idiom_rewrites" in sent and "Member Statement" in sent
