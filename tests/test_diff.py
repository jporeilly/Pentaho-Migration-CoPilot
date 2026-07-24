"""Diff harness: CSV parity comparison."""

import pytest
from fastapi.testclient import TestClient

from pentaho_migration.api.main import app
from pentaho_migration.validator.diff import DiffError, compare_csv

EXPECTED = "REGION,TOTAL\nnorth,100.50\nsouth,200.00\neast,50.25\n"


class TestCompare:
    def test_identical_outputs_pass(self):
        report = compare_csv(EXPECTED, EXPECTED)
        assert report.parity == 1.0
        assert report.verdict.startswith("PASS")
        assert not report.columns

    def test_numeric_tolerance_and_formatting(self):
        actual = "REGION,TOTAL\nnorth,100.5\nsouth,200\neast,50.250\n"
        report = compare_csv(EXPECTED, actual)
        assert report.parity == 1.0

    def test_value_mismatch_reported_with_samples(self):
        actual = "REGION,TOTAL\nnorth,100.50\nsouth,999.99\neast,50.25\n"
        report = compare_csv(EXPECTED, actual)
        assert report.mismatched_rows == 1
        assert report.columns[0].column == "TOTAL"
        assert report.samples[0].expected == "200.00"
        assert report.samples[0].actual == "999.99"

    def test_key_mode_reports_missing_and_extra(self):
        actual = "REGION,TOTAL\nnorth,100.50\nwest,75.00\n"
        report = compare_csv(EXPECTED, actual, key="REGION")
        assert report.missing_rows == 2   # south, east absent from actual
        assert report.extra_rows == 1     # west only in actual
        assert report.matching_rows == 1

    def test_no_shared_columns_is_an_error(self):
        with pytest.raises(DiffError):
            compare_csv("A,B\n1,2\n", "X,Y\n1,2\n")

    def test_bad_key_is_an_error(self):
        with pytest.raises(DiffError):
            compare_csv(EXPECTED, EXPECTED, key="NOPE")


def test_diff_endpoint():
    client = TestClient(app)
    actual = EXPECTED.replace("200.00", "201.00")
    res = client.post(
        "/diff?key=REGION",
        files={
            "expected": ("old.csv", EXPECTED, "text/csv"),
            "actual": ("new.csv", actual, "text/csv"),
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["mismatched_rows"] == 1
    assert 0 < body["parity"] < 1