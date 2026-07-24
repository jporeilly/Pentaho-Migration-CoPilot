"""Runtime diff harness core (Stage 4: VALIDATE, dynamic half).

Compares the ORIGINAL pipeline's output with the CONVERTED pipeline's output
as CSV and produces a measured parity report — the empirical counterpart to
the static confidence score.

Workflow: run the original mapping in Informatica and the generated .ktr in
PDI (both against the sandbox kit's data), export both outputs to CSV, and
diff them here. Numeric values compare with tolerance; text compares
whitespace-trimmed. With a key column, rows are matched by key; otherwise
positionally.
"""

import csv
import io

from pydantic import BaseModel, Field

NUMERIC_TOLERANCE = 1e-9
MAX_SAMPLES = 20


class ColumnDiff(BaseModel):
    column: str
    mismatches: int


class MismatchSample(BaseModel):
    row: str                 # key value or positional index
    column: str
    expected: str
    actual: str


class DiffReport(BaseModel):
    expected_rows: int
    actual_rows: int
    row_count_match: bool
    compared_rows: int
    matching_rows: int
    mismatched_rows: int
    missing_rows: int = 0    # in expected but not in actual (key mode)
    extra_rows: int = 0      # in actual but not in expected (key mode)
    parity: float            # 0.0 - 1.0
    columns: list[ColumnDiff] = Field(default_factory=list)
    samples: list[MismatchSample] = Field(default_factory=list)
    verdict: str


class DiffError(Exception):
    pass


def _values_equal(expected: str, actual: str) -> bool:
    e, a = expected.strip(), actual.strip()
    if e == a:
        return True
    try:
        return abs(float(e) - float(a)) <= NUMERIC_TOLERANCE
    except ValueError:
        return False


def _read(text: str, label: str) -> tuple[list[str], list[dict]]:
    rows = list(csv.DictReader(io.StringIO(text)))
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        raise DiffError(f"{label} CSV is empty")
    return header, rows


def compare_csv(expected_text: str, actual_text: str, key: str | None = None) -> DiffReport:
    expected_header, expected = _read(expected_text, "expected")
    actual_header, actual = _read(actual_text, "actual")

    shared = [c for c in expected_header if c in set(actual_header)]
    if not shared:
        raise DiffError("the two CSVs share no column names — cannot compare")
    if key and key not in shared:
        raise DiffError(f"key column '{key}' is not present in both files")

    column_mismatches = {c: 0 for c in shared}
    samples: list[MismatchSample] = []
    matching = mismatched = missing = extra = 0

    if key:
        actual_by_key = {row[key]: row for row in actual}
        expected_keys = set()
        for row in expected:
            key_value = row[key]
            expected_keys.add(key_value)
            other = actual_by_key.get(key_value)
            if other is None:
                missing += 1
                continue
            if _compare_row(row, other, shared, column_mismatches, samples, key_value):
                matching += 1
            else:
                mismatched += 1
        extra = sum(1 for k in actual_by_key if k not in expected_keys)
        compared = matching + mismatched
    else:
        compared = min(len(expected), len(actual))
        for i in range(compared):
            if _compare_row(expected[i], actual[i], shared, column_mismatches, samples, str(i + 1)):
                matching += 1
            else:
                mismatched += 1

    denominator = max(len(expected), len(actual), 1)
    parity = matching / denominator
    if parity >= 0.999 and len(expected) == len(actual):
        verdict = "PASS — outputs are equivalent on this data"
    elif parity >= 0.95:
        verdict = "NEAR — small differences; inspect the mismatch samples"
    else:
        verdict = "FAIL — outputs differ materially; review translated expressions and step config"

    return DiffReport(
        expected_rows=len(expected),
        actual_rows=len(actual),
        row_count_match=len(expected) == len(actual),
        compared_rows=compared,
        matching_rows=matching,
        mismatched_rows=mismatched,
        missing_rows=missing,
        extra_rows=extra,
        parity=round(parity, 4),
        columns=[ColumnDiff(column=c, mismatches=n) for c, n in column_mismatches.items() if n],
        samples=samples,
        verdict=verdict,
    )


def _compare_row(expected, actual, columns, column_mismatches, samples, row_id) -> bool:
    row_ok = True
    for column in columns:
        if not _values_equal(expected.get(column, ""), actual.get(column, "")):
            row_ok = False
            column_mismatches[column] += 1
            if len(samples) < MAX_SAMPLES:
                samples.append(MismatchSample(
                    row=row_id, column=column,
                    expected=expected.get(column, ""), actual=actual.get(column, ""),
                ))
    return row_ok
