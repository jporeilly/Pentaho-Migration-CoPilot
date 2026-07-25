"""Output parity for reports: measured proof that the converted .prpt shows
the same numbers as the original Crystal report.

The customer exports the Crystal report (PDF, or the underlying data as CSV);
we render the converted .prpt against the live JNDI database and compare the
NUMBERS on both sides - normalized (currency symbols and thousands separators
stripped, accounting negatives folded), as multisets, so layout differences
never matter but a wrong total always does.

Verdicts mirror the ETL diff harness: PASS (every reference number appears),
NEAR (>= 90% matched), FAIL. Sample mismatches are listed so the consultant
can chase the first wrong figure instead of eyeballing two PDFs.
"""

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# 1,234.56 | (1,234.56) | $ 1,234.56 | -12.5 | 42
_NUMBER_RE = re.compile(r"\(?-?[$€£]?\s?\d[\d,]*(?:\.\d+)?\)?")


@dataclass
class ParityResult:
    verdict: str               # PASS | NEAR | FAIL
    matched: int = 0
    reference_total: int = 0
    rendered_total: int = 0
    missing: list = field(default_factory=list)   # in reference, not rendered
    extra: list = field(default_factory=list)     # rendered, not in reference
    note: str = ""


def normalize_number(token: str) -> str | None:
    """One raw token -> canonical numeric string, or None if not a number.
    '$ 1,234.50' -> '1234.5'; '(42.00)' -> '-42'; '007' -> '7'."""
    s = token.strip()
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace("$", "").replace("€", "") \
         .replace("£", "").replace(" ", "")
    if s.startswith("-"):
        negative, s = True, s[1:]
    if not s or not re.fullmatch(r"\d+(?:\.\d+)?", s):
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    if negative:
        value = -value
    # canonical form: no trailing zeros, no float noise
    out = f"{value:.6f}".rstrip("0").rstrip(".")
    return out or "0"


def numbers_from_text(text: str) -> Counter:
    """Every number in a blob of text, as a normalized multiset. Bare years
    and page artifacts are numbers too - both sides contain them, so they
    cancel out in the comparison."""
    counts: Counter = Counter()
    for token in _NUMBER_RE.findall(text):
        norm = normalize_number(token)
        if norm is not None:
            counts[norm] += 1
    return counts


def numbers_from_pdf(data: bytes) -> Counter:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("parity needs pypdf - `pip install pypdf`")
    text = "".join(page.extract_text() or ""
                   for page in PdfReader(io.BytesIO(data)).pages)
    return numbers_from_text(text)


def numbers_from_csv(data: bytes) -> Counter:
    counts: Counter = Counter()
    text = data.decode("utf-8-sig", errors="replace")
    for row in csv.reader(io.StringIO(text)):
        for cell in row:
            norm = normalize_number(cell)
            if norm is not None:
                counts[norm] += 1
    return counts


def numbers_from_reference(path: Path) -> Counter:
    data = Path(path).read_bytes()
    if Path(path).suffix.lower() == ".csv":
        return numbers_from_csv(data)
    if data[:4] == b"%PDF":
        return numbers_from_pdf(data)
    raise RuntimeError(
        f"unsupported reference format {Path(path).suffix!r} - "
        "export the Crystal report as PDF or the data as CSV")


def compare_numbers(reference: Counter, rendered: Counter,
                    near_threshold: float = 0.9) -> ParityResult:
    matched = sum((reference & rendered).values())
    missing = list((reference - rendered).elements())
    extra = list((rendered - reference).elements())
    ref_total = sum(reference.values())

    if ref_total == 0:
        return ParityResult(verdict="FAIL", note="no numbers found in the reference")
    if not missing:
        verdict = "PASS"
        note = (f"every one of the reference's {ref_total} numbers appears "
                "in the rendered report")
    elif matched / ref_total >= near_threshold:
        verdict = "NEAR"
        note = (f"{matched}/{ref_total} reference numbers matched - "
                "chase the missing values below")
    else:
        verdict = "FAIL"
        note = f"only {matched}/{ref_total} reference numbers matched"
    return ParityResult(
        verdict=verdict, matched=matched, reference_total=ref_total,
        rendered_total=sum(rendered.values()),
        missing=sorted(missing, key=lambda v: (len(v), v))[-10:],
        extra=sorted(extra, key=lambda v: (len(v), v))[-10:],
        note=note)


def run_report_parity(prpt_path: Path, reference_path: Path) -> ParityResult:
    """Render the .prpt against its live JNDI database and diff its numbers
    against the customer's Crystal export. Raises RuntimeError when the
    environment cannot render (no PRD / Java / database)."""
    from pentaho_migration.reports.prpt_validator import render_prpt_pdf_live

    reference = numbers_from_reference(reference_path)
    rendered = numbers_from_pdf(render_prpt_pdf_live(prpt_path))
    return compare_numbers(reference, rendered)
