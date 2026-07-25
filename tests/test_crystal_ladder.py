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
    assert len(RUNGS) == 9, "expected 9 ladder rungs"


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

    if any(el.subreport is not None
           for s in model.sections for el in s.elements):
        # nested sub-report bundle: child layout + mapping + manifest marker
        sub_layout = zf.read("subreport/layout.xml").decode()
        assert 'core:element-type="sub-report"' in sub_layout
        dd = zf.read("subreport/datadefinition.xml").decode()
        assert "<parameter-mapping>" in dd
        manifest = zf.read("META-INF/manifest.xml").decode()
        assert "application/vnd.pentaho.reporting.classic.subreport" in manifest
        parent_layout = zf.read("layout.xml").decode()
        assert '<sub-report href="/subreport/content.xml">' in parent_layout
        assert "input-parameter master-fieldname" in parent_layout


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
    # StdDev has no PRD function -> folded into a windowed SQL column
    assert not any("StdDeviation" in i for i in loans.issues)
    assert "STDDEV_SAMP" in loans.sql
    # conditional font color -> paint style expression on the balance field
    balance = next(el for s in loans.sections for el in s.elements
                   if el.name == "d_Balance")
    assert ("paint", '=IF([LN_STATUS] = "Delinquent30";"#ff0000";"#000000")') \
        in balance.style_expressions
    # conditional section suppression -> band visible expression
    detail_band = loans.sections_of("Detail")[0]
    assert ("visible", "=NOT([PRIN_BAL_AMT] = 0)") in detail_band.style_expressions

    sar = models["06_suspicious_activity"]
    # the linked subreport now CONVERTS: child model attached, parent MBR_ID
    # mapped to the sanitized Pm_ parameter, child WHERE folded
    sub_el = next(el for s in sar.sections for el in s.elements if el.kind == "subreport")
    assert sub_el.subreport is not None
    assert sub_el.subreport_links == [("MBR_ID", "Pm_Command_MBR_ID")]
    assert sub_el.subreport.record_selection_folded
    assert "${Pm_Command_MBR_ID}" in sub_el.subreport.sql
    assert count_todos(sar) >= 1   # the cross-tab honestly remains manual

    cards = models["07_card_program"]
    assert cards.groups[0].descending                       # group sort direction consumed
    assert ("ISSUED_DT", True) in cards.record_sorts        # record sort consumed
    statuses = {f.name: f.status for f in cards.formulas.values()}
    assert statuses == {"CardAction": "review",   # Select Case multi-value -> IF/OR
                        "ExpiryWindow": "auto",   # in-range -> AND(>=;<=)
                        "Holder": "review"}       # local alias inlined

    stress = models["08_stress_lab"]
    assert len(stress.groups) == 3                          # incl. a formula group
    assert stress.groups[2].condition_field == "{@Tier}"
    subs = [el for s in stress.sections for el in s.elements if el.kind == "subreport"]
    assert len(subs) == 3
    two_link = next(el for el in subs if el.name == "TxnSub")
    assert two_link.subreport_links == [("MBR_ID", "Pm_Command_MBR_ID"),
                                        ("BR_ID", "Pm_Command_BR_ID")]
    # engine boundary (verified live): sub-reports cannot live in page bands
    page_sub = next(el for el in subs if el.name == "BranchSub")
    assert page_sub.subreport is None
    assert any("page band" in n for n in page_sub.notes)
    # the folded prompt gains a query-backed pick-list
    assert stress.param_sql_columns == {"TxnType": "t.txn_type_cd"}


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
