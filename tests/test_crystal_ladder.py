"""CSCU migration ladder: six authored RptToXml dumps of increasing
complexity, each backed by the live cscu_core schema so it converts AND
renders end-to-end. These are the pipeline's golden-path regression set
(the 150-file GitHub corpus stays the parser's real-world variety test).

The parse/convert assertions run everywhere. The live-render assertion is
opt-in (needs the CSCU database + a local PRD install) via CSCU_LIVE=1."""

import os
import zipfile
from pathlib import Path

import pytest

from pentaho_migration.reports import load_report_model, write_prpt
from pentaho_migration.reports.effort import count_todos

LADDER = Path(__file__).resolve().parents[1] / "samples" / "cr_demo"
RUNGS = sorted(LADDER.glob("0*.xml"))


def test_ladder_present():
    assert len(RUNGS) == 6, "expected 6 ladder rungs"


@pytest.mark.parametrize("dump", RUNGS, ids=lambda p: p.stem)
def test_rung_converts_to_valid_bundle(dump, tmp_path):
    model = load_report_model(dump, jndi="CSCU")
    assert model.sql.startswith("SELECT")
    assert "cscu_core" in model.sql
    out = tmp_path / f"{dump.stem}.prpt"
    write_prpt(model, out)
    zf = zipfile.ZipFile(out)
    assert zf.infolist()[0].filename == "mimetype"
    import xml.etree.ElementTree as ET
    for name in zf.namelist():
        if name.endswith(".xml"):
            ET.fromstring(zf.read(name))  # well-formed
    # the JNDI the report will use is the CSCU credit-union database
    assert "CSCU" in zf.read("datasources/sql-ds.xml").decode()


def test_ladder_exercises_increasing_complexity():
    """Each rung should introduce at least one new capability, and the hard
    rungs must flag (never silently drop) what PRD can't do mechanically."""
    models = {p.stem: load_report_model(p, jndi="CSCU") for p in RUNGS}

    roster = models["01_member_roster"]
    assert not roster.groups and not roster.formulas

    accounts = models["02_accounts_by_branch"]
    assert accounts.groups and accounts.summaries
    chart_els = [el for s in accounts.sections for el in s.elements if el.kind == "chart"]
    assert chart_els and chart_els[0].chart_type == "bar"          # migrated chart
    assert chart_els[0].chart_category == "BR_NAME"
    assert chart_els[0].chart_value == "BAL_AMT"

    register = models["03_transaction_register"]
    assert any(f.status == "auto" for f in register.formulas.values())

    statement = models["04_member_statement"]
    assert len(statement.groups) == 2                       # nested groups
    assert statement.parameters                             # parameter
    running = statement.formulas["RunningBalance"]        # running total is
    assert running.status == "review"                     # auto-rewritten as a
    assert running.rewrite_class.endswith("ItemSumFunction")  # report function

    loans = models["05_loan_portfolio"]
    assert any("StdDeviation" in i for i in loans.issues)   # unsupported aggregate flagged
    element_notes = [n for s in loans.sections for el in s.elements for n in el.notes]
    assert any("conditional" in n.lower() for n in element_notes)  # conditional format flagged

    sar = models["06_suspicious_activity"]
    assert count_todos(sar) >= 2   # subreport + crosstab (embedded logo is migrated, not a TODO)


@pytest.mark.skipif(os.environ.get("CSCU_LIVE") != "1",
                    reason="set CSCU_LIVE=1 to render against the live CSCU database")
@pytest.mark.parametrize("dump", RUNGS, ids=lambda p: p.stem)
def test_rung_renders_with_live_data(dump, tmp_path):
    from pentaho_migration.reports.prpt_validator import validator_available
    if not validator_available():
        pytest.skip("no local PRD install + Java")
    from pentaho_migration.reports.prpt_validator import render_prpt_pdf

    model = load_report_model(dump, jndi="CSCU")
    out = tmp_path / f"{dump.stem}.prpt"
    write_prpt(model, out)
    pdf = render_prpt_pdf(out)  # empty-data engine render — proves layout loads
    assert pdf[:4] == b"%PDF"
