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
# A difference on this share of the compared pages is REPORT-WIDE - it lives
# in a band that repeats, so it is one defect with one fix. Listing it page
# by page reads as N problems and gets costed N times.
GLOBAL_SHARE = 0.7


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
    groups_checked: int = 0    # per-group span comparison: how many identities
    groups_matching: int = 0   # ... and how many span the SAME pages as the original
    pages_compared: int = 0    # pages compared by APPEARANCE, not just text
    pages_pairable: int = 0    # ... out of this many that could be paired
    findings: list = field(default_factory=list)


def _appearance_finding(visual: dict) -> Finding:
    """One finding for a visual difference, said once.

    A fill missing from a band that repeats on every statement is ONE defect
    with one fix, not twelve. Listing it page by page buries that and reads
    as twelve problems, which is how a consultant ends up costing the same
    work over and over. Where every compared page differs the same way, the
    finding says so and quotes a single page as the example."""
    worst = visual["pages"]
    compared = visual["compared"]
    lo = min(f for _o, _c, f, _w in worst)
    hi = max(f for _o, _c, f, _w in worst)
    # Group by WHERE on the page, not by the exact wording: the same missing
    # fill reads as "missing something" on a page where it dominates and
    # "content differs" where text moved too, and those are one defect.
    places: dict = {}
    for o, c, f, where in worst:
        places.setdefault(where.split(" - ")[0], []).append((o, c, f))
    place, hits = max(places.items(), key=lambda kv: len(kv[1]))
    if compared > 1 and len(hits) >= max(2, int(compared * GLOBAL_SHARE)):
        o, c, f = hits[0]
        return Finding(
            "warning", "appearance",
            f"REPORT-WIDE: the {place} differs on {len(hits)} of the "
            f"{compared} page(s) compared. It is one difference in a band "
            "that repeats, not one per page - a single fix covers every "
            "statement",
            evidence=[f"{lo:.0%}-{hi:.0%} of each page affected",
                      f"e.g. original p{o + 1} vs converted p{c + 1} "
                      f"({f:.0%} of the page)"]
            + ([f"{len(worst) - len(hits)} further page(s) differ elsewhere"]
               if len(worst) > len(hits) else []))
    return Finding(
        "warning", "appearance",
        f"{len(worst)} of {compared} page(s) compared LOOK different from "
        "the original beyond text - a fill, rule or box that the text "
        "comparison cannot see",
        evidence=[f"original p{o + 1} vs converted p{c + 1}: "
                  f"{f:.0%} of the page - {where}"
                  for o, c, f, where in worst[:MOVED_LINE_CAP]])


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


# whole month NAMES only - a bare 3-letter prefix rule would fold "Mark" into
# "Mar" and "Maybe" into "May", making unrelated words compare equal and hiding
# real dropped content.
_MONTHS = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\b")


def _normalize_line(line: str) -> str:
    """Comparison form of a text line: collapsed whitespace, digits masked,
    month names shortened, currency spacing collapsed - so a date or an
    amount matches itself in either engine's dialect. Short/noise lines
    normalize to '' and drop out."""
    text = re.sub(r"\s+", " ", line).strip()
    text = _MONTHS.sub(lambda m: m.group(1)[:3], text)
    text = re.sub(r"[\d,.]+", "#", text)
    text = text.replace("$ #", "$#")
    return text if len(text) >= 6 else ""


def _doc_stream(pages: list) -> str:
    """The whole document as one normalized stream - matching against it is
    WRAP-INSENSITIVE, so a paragraph that wraps at a different column (or a
    label and its value extracted as separate lines) still counts as
    present."""
    return " " + " ".join(
        _normalize_line(" ".join(page.split())) or "" for page in pages) + " "


def _line_pages(pages: list) -> dict:
    """normalized line -> first page index it appears on."""
    out: dict = {}
    for i, page in enumerate(pages):
        for raw in page.splitlines():
            line = _normalize_line(raw)
            if line and line not in out:
                out[line] = i
    return out


def _boilerplate(pages: list) -> set:
    """Normalized lines that appear on most pages - page furniture (headers,
    legal footers). Excluded from sparseness so a page holding only furniture
    plus a stray Total counts as widowed."""
    from collections import Counter

    seen = Counter()
    for page in pages:
        for line in {l for l in map(_normalize_line, page.splitlines()) if l}:
            seen[line] += 1
    threshold = max(2, int(len(pages) * 0.6))
    return {line for line, n in seen.items() if n >= threshold}


def _sparse_pages(pages: list) -> list:
    """Page indices carrying almost no content beyond the furniture -
    the widowed Total/Remit pages the eye catches instantly."""
    furniture = _boilerplate(pages)
    sparse = []
    for i, page in enumerate(pages):
        content = {l for l in map(_normalize_line, page.splitlines()) if l}
        if len(content - furniture) <= 3:
            sparse.append(i)
    return sparse


def _group_spans(pages: list, values: list) -> dict:
    """value -> number of pages it appears on."""
    spans: dict = {}
    for value in values:
        spans[value] = sum(1 for p in pages if value in p)
    return spans


def compare_renders(original_pdf: bytes, converted_pdf: bytes,
                    group_values: list | None = None) -> ReleaseCheck:
    """Deterministic comparison of the two renders. `group_values` (e.g. the
    customer names from the embedded saved rows) enables the per-group span
    comparison - the check that answers "does each statement occupy the same
    pages as the original"."""
    result = ReleaseCheck()
    orig_pages = _pdf_pages_text(original_pdf)
    conv_pages = _pdf_pages_text(converted_pdf)
    result.original_pages = len(orig_pages)
    result.converted_pages = len(conv_pages)

    # 1. page count - deferred: whether a delta is a DEFECT depends on the
    # group-span comparison below (a compacter render whose statements all
    # match the original is a difference to mention, not a problem to fix)
    delta = abs(len(orig_pages) - len(conv_pages))

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

    # 3 + 4. content lines: missing entirely, or moved to another page.
    # "Missing" is judged against the WHOLE converted document, wrap- and
    # format-insensitively - line-by-line comparison flagged every paragraph
    # that merely wrapped at a different column. The last fallback drops
    # spaces entirely: the Crystal renderer's glyph gaps get extracted as
    # spaces the source text does not contain ("Objects :", "and/ or"), so a
    # character-faithful conversion looked like dropped content.
    orig_lines = _line_pages(orig_pages)
    conv_lines = _line_pages(conv_pages)
    conv_stream = _doc_stream(conv_pages)
    conv_squeezed = conv_stream.replace(" ", "")
    missing_lines = [l for l in orig_lines
                     if l not in conv_lines and l not in conv_stream
                     and l.replace(" ", "") not in conv_squeezed]
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

    # 5. widowed pages: near-empty pages (a Total/Remit separated from its
    # statement). The original may legitimately have some - the finding is
    # about having MORE of them than it does.
    orig_sparse = _sparse_pages(orig_pages)
    conv_sparse = _sparse_pages(conv_pages)
    if len(conv_sparse) > len(orig_sparse) + 2:
        result.findings.append(Finding(
            "warning", "widowed-pages",
            f"{len(conv_sparse)} near-empty page(s) vs {len(orig_sparse)} in "
            "the original - group footers are separating from their content; "
            "check band heights and keep-together",
            evidence=[f"converted p{p + 1}" for p in conv_sparse[:8]]))

    # 6. per-group page spans: does each customer/statement occupy the same
    # number of pages as the original?
    if group_values:
        orig_spans = _group_spans(orig_pages, group_values)
        conv_spans = _group_spans(conv_pages, group_values)
        drifted = [(v, orig_spans[v], conv_spans[v]) for v in group_values
                   if orig_spans[v] and conv_spans[v]
                   and orig_spans[v] != conv_spans[v]]
        result.groups_checked = len(group_values)
        result.groups_matching = len(group_values) - len(drifted)
        if len(drifted) > max(2, len(group_values) // 10):
            result.findings.append(Finding(
                "warning", "group-spans",
                f"{len(drifted)} of {len(group_values)} group(s) span a "
                "different number of pages than the original",
                evidence=[f"{v[:40]}: original {o} page(s) -> converted {c}"
                          for v, o, c in drifted[:8]]))

    if delta and delta / max(len(orig_pages), 1) > PAGE_DELTA_WARN:
        if (result.groups_checked
                and result.groups_matching == result.groups_checked
                and len(conv_pages) < len(orig_pages)):
            result.findings.append(Finding(
                "info", "pages",
                f"the conversion is more compact: {len(conv_pages)} pages vs "
                f"{len(orig_pages)} - the original leaves near-empty spill "
                f"pages ({len(_sparse_pages(orig_pages))} of them) that the "
                "conversion consolidates; every statement still spans the "
                "same pages as the original"))
        else:
            result.findings.append(Finding(
                "warning", "pages",
                f"page count differs: original {len(orig_pages)}, converted "
                f"{len(conv_pages)} - grouping, page breaks or section "
                "heights changed the flow"))

    # 7. how the pages LOOK. Everything above reads text, which is blind to
    # the differences a reader notices first - a background panel that
    # vanished, a rule the original does not draw, a total box that lost its
    # fill. All of those leave the text identical, so the gate reported SHIP
    # through a series of real visual defects until this existed.
    from pentaho_migration.reports.visual_diff import compare_visually

    orig_line_sets = [set(filter(None, map(_normalize_line, p.splitlines())))
                      for p in orig_pages]
    conv_line_sets = [set(filter(None, map(_normalize_line, p.splitlines())))
                      for p in conv_pages]
    visual = compare_visually(original_pdf, converted_pdf,
                              orig_line_sets, conv_line_sets)
    result.pages_compared = visual["compared"]
    result.pages_pairable = visual["available"]
    if visual["pages"]:
        result.findings.append(_appearance_finding(visual))
    elif not visual["compared"]:
        # say so rather than let a silent skip read as a clean result
        result.findings.append(Finding(
            "info", "appearance",
            "the pages were not compared visually - no pairable pages, or "
            "Pillow is not installed"))

    # conservative gate: warnings and errors need a look; info findings are
    # context, not work
    result.verdict = ("SHIP" if not any(f.severity in ("error", "warning")
                                        for f in result.findings)
                      else "REVIEW")
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
    return compare_renders(original_pdf, converted_pdf,
                           group_values=_innermost_group_values(model))


def _innermost_group_values(model, cap: int = 60) -> list:
    """Distinct values of the innermost group, in row order, from the
    embedded saved rows - the per-statement identities the span check keys
    on. Empty when there is no saved data (the check simply skips)."""
    saved = getattr(model, "saved_rows", None)
    groups = [g.column for g in getattr(model, "groups", [])]
    if saved is None or not groups:
        return []
    columns = [c[0] for c in saved.columns]
    if groups[-1] not in columns:
        return []
    idx = columns.index(groups[-1])
    values = []
    for row in saved.rows:
        value = str(row[idx] or "").strip()
        if value and value not in values:
            values.append(value)
        if len(values) >= cap:
            break
    return values


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
