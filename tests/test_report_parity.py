"""Report output-parity harness: number normalization, PDF/CSV extraction,
multiset comparison and verdicts. Live end-to-end (render vs itself = PASS)
is opt-in via CSCU_LIVE=1."""

import os
from collections import Counter
from pathlib import Path

import pytest

from pentaho_migration.reports.parity import (
    compare_numbers, normalize_number, numbers_from_csv, numbers_from_text)


def test_normalize_number_shapes():
    assert normalize_number("$ 1,234.50") == "1234.5"
    assert normalize_number("(42.00)") == "-42"
    assert normalize_number("-16,924.20") == "-16924.2"
    assert normalize_number("007") == "7"
    assert normalize_number("CSCU-100501") is None
    assert normalize_number("Phoenix") is None


def test_numbers_from_text_is_a_multiset():
    counts = numbers_from_text("Total: $ 100.00 and again 100.00 but (50.00)")
    assert counts["100"] == 2
    assert counts["-50"] == 1


def test_numbers_from_csv():
    counts = numbers_from_csv(b'name,amount\nAlice,"1,200.50"\nBob,(30.00)\n')
    assert counts["1200.5"] == 1
    assert counts["-30"] == 1


def test_parity_pass_near_fail():
    ref = Counter({"100": 1, "200": 1, "300": 1})
    assert compare_numbers(ref, Counter(ref)).verdict == "PASS"

    rendered = Counter({"100": 1, "200": 1, "300": 1, "999": 1})
    result = compare_numbers(ref, rendered)
    assert result.verdict == "PASS"          # extra numbers alone never fail
    assert result.extra == ["999"]

    ten = Counter({str(i): 1 for i in range(10)})
    nine = Counter({str(i): 1 for i in range(9)})
    result = compare_numbers(ten, nine)
    assert result.verdict == "NEAR"
    assert result.missing == ["9"]

    assert compare_numbers(ten, Counter({"0": 1})).verdict == "FAIL"
    assert compare_numbers(Counter(), Counter({"1": 1})).verdict == "FAIL"


@pytest.mark.skipif(os.environ.get("CSCU_LIVE") != "1",
                    reason="set CSCU_LIVE=1 for the live self-parity check")
def test_live_self_parity_is_pass(tmp_path):
    """Render the Member Statement live, then compare it against its own PDF:
    a converted report always has parity with itself."""
    from pentaho_migration.reports import load_report_model, write_prpt
    from pentaho_migration.reports.parity import run_report_parity
    from pentaho_migration.reports.prpt_validator import (
        render_prpt_pdf_live, validator_available)

    if not validator_available():
        pytest.skip("no local PRD install + Java")
    dump = Path(__file__).resolve().parents[1] / "samples" / "cr_demo" / "04_member_statement.xml"
    model = load_report_model(dump, jndi="CSCU")
    prpt = tmp_path / "statement.prpt"
    write_prpt(model, prpt)
    reference = tmp_path / "reference.pdf"
    reference.write_bytes(render_prpt_pdf_live(prpt))
    result = run_report_parity(prpt, reference)
    assert result.verdict == "PASS"
    assert result.reference_total > 10
