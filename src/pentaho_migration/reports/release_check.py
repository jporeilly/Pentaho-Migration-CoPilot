"""Release gate: render the ORIGINAL .rpt and the CONVERTED .prpt, compare
them, and say SHIP or REVIEW - with evidence.

This automates the compare-fix-compare loop that found the pagination,
paint-order and currency defects by hand: the original renders through the
SAP Crystal viewer (saved-data reports need no database), the conversion
renders through the real Pentaho engine with its embedded rows, and the two
PDFs are diffed deterministically:

  * page-count delta;
  * NUMBERS as a multiset (reusing the parity normalizer) - catches missing
    rows, broken totals, x100 scaling, dropped currency values;
  * LINES of the original that never appear in the conversion (normalized) -
    catches dropped labels, wrong letter variants, suppressed content;
  * lines that MOVED pages - catches the "Total slipped to the next page"
    class without failing content that merely reflowed.

Findings can then be handed to the LLM (shared provider dispatch) to propose
a resolution or write consultant guidance - see consultant_report.py. Every
comparison here is deterministic; the LLM only ever ANNOTATES findings, it
never decides the verdict.
"""

import re
import subprocess

from pentaho_migration.reports.proc import run_nice
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pentaho_migration.reports.parity import compare_numbers, numbers_from_text

REPO_ROOT = Path(__file__).resolve().parents[3]
VIEWER = REPO_ROOT / "tools" / "RptViewer" / "RptViewer.exe"

RENDER_TIMEOUT = 300.0
# ignore trivial page drift; a statement report reflows a little by design
PAGE_DELTA_WARN = 0.1          # >10% page-count drift is a finding
MOVED_LINE_CAP = 12            # report the first N moved/missing lines


@dataclass
class Finding:
    severity: str              # error | warning
    code: str                  # pages | numbers | missing-content | moved-content
    message: str
    evidence: list = field(default_factory=list)
    resolution: str = ""       # filled by the LLM annotator (or left empty)


@dataclass
class ReleaseCheck:
    verdict: str = "REVIEW"    # SHIP | REVIEW | UNAVAILABLE
    reason: str = ""           # why UNAVAILABLE, when it is
    original_pages: int = 0
    converted_pages: int = 0
    findings: list = field(default_factory=list)


def _pdf_pages_text(pdf_bytes: bytes) -> list:
    import time

    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        pages = []
        for page in doc:
            pages.append(page.get_textpage().get_text_bounded())
            time.sleep(0)   # yield the GIL so the web app keeps serving
        return pages
    finally:
        doc.close()


def render_original_pdf(rpt_path: Path) -> bytes:
    """The customer's report, rendered by the SAP viewer. Raises RuntimeError
    with one actionable sentence when the viewer is missing or export fails."""
    if not VIEWER.is_file():
        raise RuntimeError(
            "the Crystal viewer is not built - run tools/RptViewer/build.ps1")
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "original.pdf"
        proc = run_nice(
            [str(VIEWER), str(rpt_path), "--export", str(out)],
            capture_output=True, text=True, timeout=RENDER_TIMEOUT)
        if proc.returncode != 0 or not out.exists():
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise RuntimeError(
                "viewer export failed"
                + (f": {tail[-1][:200]}" if tail else ""))
        return out.read_bytes()


def _normalize_line(line: str) -> str:
    """Comparison form of a text line: collapsed whitespace, digits masked so
    a date or an amount matches itself in either format. Short/noise lines
    normalize to '' and drop out."""
    text = re.sub(r"\s+", " ", line).strip()
    text = re.sub(r"[\d,.]+", "#", text)
    return text if len(text) >= 6 else ""


def _line_pages(pages: list) -> dict:
    """normalized line -> first page index it appears on."""
    out: dict = {}
    for i, page in enumerate(pages):
        for raw in page.splitlines():
            line = _normalize_line(raw)
            if line and line not in out:
                out[line] = i
    return out


def compare_renders(original_pdf: bytes, converted_pdf: bytes) -> ReleaseCheck:
    """Deterministic comparison of the two renders."""
    result = ReleaseCheck()
    orig_pages = _pdf_pages_text(original_pdf)
    conv_pages = _pdf_pages_text(converted_pdf)
    result.original_pages = len(orig_pages)
    result.converted_pages = len(conv_pages)

    # 1. page count
    delta = abs(len(orig_pages) - len(conv_pages))
    if delta and delta / max(len(orig_pages), 1) > PAGE_DELTA_WARN:
        result.findings.append(Finding(
            "warning", "pages",
            f"page count differs: original {len(orig_pages)}, converted "
            f"{len(conv_pages)} - grouping, page breaks or section heights "
            "changed the flow"))

    # 2. numbers as a multiset. Dates are stripped first: the two engines
    # format them differently ("2002/04/3" vs "2002-04-03"), which tokenizes
    # into different number soup and drowns real numeric differences. Date
    # CONTENT still gets compared - by the line diff below, digit-masked.
    strip_dates = re.compile(
        r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b|\b[A-Z][a-z]{2,8} \d{1,2}, \d{4}\b")
    orig_numbers = Counter()
    conv_numbers = Counter()
    for page in orig_pages:
        orig_numbers.update(numbers_from_text(strip_dates.sub(" ", page)))
    for page in conv_pages:
        conv_numbers.update(numbers_from_text(strip_dates.sub(" ", page)))
    parity = compare_numbers(orig_numbers, conv_numbers)
    missing = Counter(orig_numbers)
    missing.subtract(conv_numbers)
    missing = +missing                      # only positive counts remain
    if parity.verdict == "FAIL":
        result.findings.append(Finding(
            "error", "numbers",
            f"{sum(missing.values())} numeric value(s) from the original are "
            "absent in the conversion - data, totals or formats are wrong",
            evidence=[f"{v} (x{n})" for v, n in missing.most_common(8)]))
    elif parity.verdict == "NEAR":
        result.findings.append(Finding(
            "warning", "numbers",
            f"{sum(missing.values())} numeric value(s) differ from the "
            "original - check formats and edge rows",
            evidence=[f"{v} (x{n})" for v, n in missing.most_common(8)]))

    # 3 + 4. content lines: missing entirely, or moved to another page
    orig_lines = _line_pages(orig_pages)
    conv_lines = _line_pages(conv_pages)
    missing_lines = [l for l in orig_lines if l not in conv_lines]
    if missing_lines:
        result.findings.append(Finding(
            "error", "missing-content",
            f"{len(missing_lines)} line(s) of the original never appear in "
            "the conversion",
            evidence=missing_lines[:MOVED_LINE_CAP]))
    moved = [(l, orig_lines[l], conv_lines[l])
             for l in orig_lines
             if l in conv_lines and conv_lines[l] != orig_lines[l]]
    # only meaningful when the page counts broadly agree - otherwise
    # everything trivially "moves"
    if moved and delta / max(len(orig_pages), 1) <= PAGE_DELTA_WARN:
        result.findings.append(Finding(
            "warning", "moved-content",
            f"{len(moved)} line(s) print on a different page than the "
            "original (first occurrence compared)",
            evidence=[f"p{o + 1} -> p{c + 1}: {l[:70]}"
                      for l, o, c in moved[:MOVED_LINE_CAP]]))

    # conservative gate: anything worth a sentence is worth a look
    result.verdict = "SHIP" if not result.findings else "REVIEW"
    return result


def run_release_check(model, rpt_path: Path) -> ReleaseCheck:
    """Render both sides and compare. UNAVAILABLE (never a crash) when the
    environment cannot render one of them."""
    from pentaho_migration.reports import write_prpt
    from pentaho_migration.reports.prpt_validator import (
        render_prpt_pdf, render_prpt_pdf_live, validator_available)
    import tempfile

    if not validator_available():
        return ReleaseCheck(verdict="UNAVAILABLE",
                            reason="no local PRD install to render the .prpt")
    try:
        original_pdf = render_original_pdf(rpt_path)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        return ReleaseCheck(verdict="UNAVAILABLE", reason=str(exc))
    try:
        with tempfile.TemporaryDirectory() as td:
            prpt = Path(td) / "converted.prpt"
            write_prpt(model, prpt, saved_rows=model.saved_rows)
            converted_pdf = (render_prpt_pdf_live(prpt)
                             if model.saved_rows is not None
                             else render_prpt_pdf(prpt))
    except RuntimeError as exc:
        return ReleaseCheck(verdict="UNAVAILABLE",
                            reason=f"converted render failed: {exc}")
    return compare_renders(original_pdf, converted_pdf)


def annotate_findings_with_llm(check: ReleaseCheck, model, settings=None,
                               max_findings: int = 8) -> int:
    """Ask the LLM for a resolution-or-guidance note per finding. Advisory
    only: the verdict is already decided deterministically. Returns how many
    findings were annotated; 0 (with no exception) when no provider is
    configured - the report then simply carries un-annotated findings."""
    from pentaho_migration.llm.settings import load_settings
    from pentaho_migration.llm.translate import chat_json

    if not check.findings:
        return 0
    settings = settings or load_settings()
    schema = {"type": "object",
              "properties": {"resolution": {"type": "string"}},
              "required": ["resolution"]}
    context = (f"Report: {model.name}. Groups: "
               f"{[g.column for g in model.groups]}. "
               f"Bands: {[(s.area_kind, round(s.height, 1)) for s in model.sections][:20]}.")
    done = 0
    for finding in check.findings[:max_findings]:
        prompt = (
            "You are reviewing a SAP Crystal Reports to Pentaho Report "
            "Designer conversion. A deterministic comparison of the rendered "
            "original vs the rendered conversion produced this finding:\n\n"
            f"[{finding.severity}/{finding.code}] {finding.message}\n"
            f"Evidence: {finding.evidence[:6]}\n\n"
            f"{context}\n\n"
            "In 2-4 sentences: if this is mechanically fixable in the .prpt, "
            "say exactly what to change (band, property, value). If it needs "
            "judgment, write the guidance a consultant needs to resolve it "
            "quickly. No preamble.")
        try:
            reply = chat_json(settings,
                              [{"role": "user", "content": prompt}], schema)
            finding.resolution = (reply.get("resolution") or "").strip()
            done += 1 if finding.resolution else 0
        except Exception:
            break                      # provider missing/down - stop quietly
    return done
