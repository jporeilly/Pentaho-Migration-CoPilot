"""The release gate: rendered original vs rendered conversion.

The comparison is deterministic and testable without any renderer - the
PDF-text extraction is patched and the comparators fed synthetic pages.
The gate's first real catches are pinned here as fixtures: the signature
block lost to design-space underlay offsets, and $0.00 totals from
braceless recovered summary refs.
"""

import pytest

from pentaho_migration.reports import release_check as rc


def _patch_pages(monkeypatch, original_pages, converted_pages):
    calls = []

    def fake(pdf_bytes):
        calls.append(pdf_bytes)
        return original_pages if pdf_bytes == b"ORIG" else converted_pages

    monkeypatch.setattr(rc, "_pdf_pages_text", fake)


class TestComparison:
    def test_identical_renders_ship(self, monkeypatch):
        pages = ["Statement for Crazy Wheels\nTotal: $43.50\nPage 1"]
        _patch_pages(monkeypatch, pages, list(pages))
        check = rc.compare_renders(b"ORIG", b"CONV")
        assert check.verdict == "SHIP"
        # the synthetic bytes are not renderable, so the appearance check
        # reports that it could not run - an INFO note, never a defect
        assert not [f for f in check.findings
                    if f.severity in ("error", "warning")]
        assert [f.code for f in check.findings] == ["appearance"]

    def test_missing_number_is_an_error(self, monkeypatch):
        _patch_pages(monkeypatch,
                     ["Amount due 1139.55 and 43.50 for the order"],
                     ["Amount due 1139.55 and nothing for the order"])
        check = rc.compare_renders(b"ORIG", b"CONV")
        codes = {f.code: f.severity for f in check.findings}
        assert codes.get("numbers") == "error"
        assert check.verdict == "REVIEW"

    def test_date_format_differences_are_not_numeric_findings(self, monkeypatch):
        """'2002/04/3' vs '2002-04-03' is the same date in two dialects - it
        must not drown the numeric comparison in token soup."""
        _patch_pages(monkeypatch,
                     ["Invoice 2002/04/3 amount 43.50"],
                     ["Invoice 2002-04-03 amount 43.50"])
        check = rc.compare_renders(b"ORIG", b"CONV")
        assert not any(f.code == "numbers" for f in check.findings)

    def test_content_that_moved_pages_is_reported(self, monkeypatch):
        _patch_pages(monkeypatch,
                     ["The letter body here\nRemit Payment instructions",
                      "second page content", "third page content"],
                     ["The letter body here",
                      "Remit Payment instructions\nsecond page content",
                      "third page content"])
        check = rc.compare_renders(b"ORIG", b"CONV")
        moved = next((f for f in check.findings if f.code == "moved-content"), None)
        assert moved is not None
        assert any("Remit" in e for e in moved.evidence)

    def test_dropped_line_is_an_error(self, monkeypatch):
        _patch_pages(monkeypatch,
                     ["Mark Elroy signature block\nBody text of the letter"],
                     ["Body text of the letter"])
        check = rc.compare_renders(b"ORIG", b"CONV")
        missing = next(f for f in check.findings if f.code == "missing-content")
        assert missing.severity == "error"
        assert any("Mark Elroy" in e for e in missing.evidence)

    def test_page_count_drift_beyond_threshold(self, monkeypatch):
        _patch_pages(monkeypatch, ["page content here"] * 10,
                     ["page content here"] * 8)
        check = rc.compare_renders(b"ORIG", b"CONV")
        assert any(f.code == "pages" for f in check.findings)


class TestLlmAnnotation:
    def test_annotations_are_advisory_and_optional(self, monkeypatch):
        check = rc.ReleaseCheck(verdict="REVIEW", findings=[
            rc.Finding("warning", "pages", "page count differs")])

        class Model:
            name = "X"
            groups = []
            sections = []

        import pentaho_migration.llm.translate as tr
        monkeypatch.setattr(tr, "chat_json",
                            lambda *a, **k: {"resolution": "Adjust band Y."})
        import pentaho_migration.llm.settings as st
        monkeypatch.setattr(st, "load_settings", lambda: object())
        n = rc.annotate_findings_with_llm(check, Model())
        assert n == 1
        assert check.findings[0].resolution == "Adjust band Y."
        assert check.verdict == "REVIEW"   # the LLM never changes the verdict

    def test_no_provider_means_no_annotations_no_crash(self, monkeypatch):
        check = rc.ReleaseCheck(verdict="REVIEW", findings=[
            rc.Finding("warning", "pages", "page count differs")])

        class Model:
            name = "X"
            groups = []
            sections = []

        import pentaho_migration.llm.translate as tr
        def boom(*a, **k):
            raise RuntimeError("no provider")
        monkeypatch.setattr(tr, "chat_json", boom)
        assert rc.annotate_findings_with_llm(check, Model()) == 0


class TestRegressionFixtures:
    """The gate's first real catches, pinned so they stay caught."""

    def test_renderer_glyph_gaps_are_not_dropped_content(self, monkeypatch):
        """The Crystal renderer's inter-glyph gaps extract as spaces the
        source text has no character for ('Objects :', 'and/ or'). A
        character-faithful conversion was being reported as dropping the
        legal footer."""
        _patch_pages(
            monkeypatch,
            ["licensed by Business Objects : 5,295,243; 5,339,390\n"
             "countries of Business Objects and/ or affiliated companies"],
            ["licensed by Business Objects: 5,295,243; 5,339,390\n"
             "countries of Business Objects and/or affiliated companies"])
        check = rc.compare_renders(b"ORIG", b"CONV")
        assert not any(f.code == "missing-content" for f in check.findings)

    def test_squeezed_match_still_catches_real_drops(self, monkeypatch):
        """Space-insensitivity must not swallow genuinely absent text."""
        _patch_pages(monkeypatch,
                     ["Authorised signatory Mark Elroy\nBody of the letter"],
                     ["Body of the letter"])
        check = rc.compare_renders(b"ORIG", b"CONV")
        missing = next(f for f in check.findings if f.code == "missing-content")
        assert any("Mark Elroy" in e for e in missing.evidence)

    def test_month_names_normalize_without_eating_ordinary_words(self):
        """The two engines print 'July' and 'Jul' for the same date, so month
        names fold to three letters - but only WHOLE month names. A prefix
        rule folded 'Mark' into 'Mar' and 'Maybe' into 'May', which made
        unrelated lines compare equal and hid dropped content."""
        assert rc._normalize_line("as of July 27, 2026") == "as of Jul # #"
        assert rc._normalize_line("as of Jul 28, 2026") == "as of Jul # #"
        for intact in ("Mark Elroy signature", "Marketing summary line",
                       "Maybe later on the invoice", "Augmented totals here"):
            assert rc._normalize_line(intact) == intact

    def test_recovered_summary_refs_keep_their_braces(self, tmp_path):
        """Braceless 'ORDERS.ORDER_AMOUNT' classified as unknown and the
        emitted function summed a field the query does not have - $0.00
        totals at the customer."""
        from pentaho_migration.reports.rpt_parser import (
            _recover_summary_refs, parse_field_ref)
        fref, gref = _recover_summary_refs(
            "Sum ({ORDERS.ORDER_AMOUNT}, {CUSTOMER.CUSTOMER_NAME})",
            "CrystalDecisions.CrystalReports.Engine.DatabaseFieldDefinition",
            "CrystalDecisions.CrystalReports.Engine.Group")
        assert parse_field_ref(fref) == ("db", "ORDER_AMOUNT")
        assert parse_field_ref(gref) == ("db", "CUSTOMER_NAME")

    def test_underlay_targets_conditional_variants_as_one_slot(self):
        """Three mutually-exclusive letter variants stack sequentially in
        DESIGN space but occupy one slot at RUNTIME - the underlay copy must
        land in every variant, or whichever renders loses the signature."""
        import zipfile
        from pathlib import Path

        demo = (Path(__file__).resolve().parents[1] / "samples" / "crystal"
                / "demo" / "Statement_of_Account.xml")
        if not demo.exists():
            pytest.skip("demo dump not present")
        import tempfile

        from pentaho_migration.reports import load_report_model, write_prpt
        model = load_report_model(demo, "Xtreme")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.prpt"
            write_prpt(model, out)
            layout = zipfile.ZipFile(out).read("layout.xml").decode()
        assert layout.count("Mark Elroy") >= 3, (
            "the signature block must ride every letter variant")
