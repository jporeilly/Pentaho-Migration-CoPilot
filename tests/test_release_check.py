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


class TestWhereStatementsBreak:
    """A span COUNT says a statement takes two pages in both renders. It does
    not say the original breaks after the letter and the conversion breaks
    halfway down the invoice table, which is the difference a reader sees."""

    def test_same_page_count_but_a_different_break_is_caught(self, monkeypatch):
        _patch_pages(
            monkeypatch,
            ["Wheels Inc.\n8 Harbour Road\nSan Diego CA\nlegal footer here",
             "Wheels Inc.\n2002/04/03 2886 43.50\nTotal 43.50\nlegal footer here"],
            ["Wheels Inc.\n8 Harbour Road\nSan Diego CA\n2002/04/03 2886 43.50\n"
             "legal footer here",
             "Wheels Inc.\nTotal 43.50\nlegal footer here"])
        check = rc.compare_renders(b"ORIG", b"CONV", group_values=["Wheels Inc."])
        breaks = next(f for f in check.findings if f.code == "group-breaks")
        assert breaks.severity == "warning"
        assert check.groups_with_breaks == 1
        assert check.groups_breaking_alike == 0
        # the span count alone saw nothing wrong
        assert check.groups_matching == check.groups_checked

    def test_an_identical_break_is_not_flagged(self, monkeypatch):
        pages = ["Wheels Inc.\n8 Harbour Road\nSan Diego CA\nlegal footer here",
                 "Wheels Inc.\nTotal 43.50\nlegal footer here"]
        _patch_pages(monkeypatch, pages, list(pages))
        check = rc.compare_renders(b"ORIG", b"CONV", group_values=["Wheels Inc."])
        assert not [f for f in check.findings if f.code == "group-breaks"]
        assert check.groups_breaking_alike == check.groups_with_breaks == 1

    def test_a_single_page_group_has_no_break_to_compare(self, monkeypatch):
        _patch_pages(monkeypatch, ["Acme Ltd\nTotal 10.00\nlegal footer here"],
                     ["Acme Ltd\nTotal 10.00\nlegal footer here"])
        check = rc.compare_renders(b"ORIG", b"CONV", group_values=["Acme Ltd"])
        assert check.groups_with_breaks == 0
        assert not [f for f in check.findings if f.code == "group-breaks"]


class TestFurnitureIsFoundOnPopulatedPages:
    """The demo's original leaves 37 near-empty spill pages out of 74, so its
    legal footer prints on exactly half. A 60%-of-ALL-pages rule found no
    furniture at all, which left the break comparison quoting the copyright
    block as if it were statement content."""

    def test_footer_on_half_the_pages_is_still_furniture(self):
        content = "Acme\nreal content line\nlegal footer here\nBusiness Objects"
        pages = [content] * 5 + ["", "", "", "", ""]     # 5 populated, 5 spill
        furniture = rc._boilerplate(pages)
        assert any("legal footer" in f for f in furniture)

    def test_a_line_on_one_page_is_not_furniture(self):
        pages = ["Acme\nunique to this page\nlegal footer here\nshared two",
                 "Beta\nsomething else\nlegal footer here\nshared two"]
        furniture = rc._boilerplate(pages)
        assert not any("unique to this page" in f for f in furniture)


def _statement(customer, *body):
    return "\n".join([customer, *body, "legal footer here", "Business Objects"])


def _total_page():
    return "\n".join(["Remit Payment to:", "Total 43.50",
                      "legal footer here", "Business Objects"])


class TestAnOrphanedTotalIsAttributedToItsCustomer:
    """A total pushed past the page break sits alone, and no other check in
    the gate sees it: the page count can be right, every number present,
    and each statement still spanning the pages it should.

    The near-empty-page count cannot catch it either, because the original
    leaves 43 spill pages of its own - "more near-empty pages than the
    original" stays false while a total is stranded."""

    def _check(self, monkeypatch, orig, conv, values):
        _patch_pages(monkeypatch, orig, conv)
        return rc.compare_renders(b"ORIG", b"CONV", group_values=values)

    def test_a_total_alone_on_the_next_page_names_its_customer(self, monkeypatch):
        orig = [_statement("Wheels Inc.", "8 Harbour Road", "Total 43.50")]
        conv = [_statement("Wheels Inc.", "8 Harbour Road"), _total_page()]
        check = self._check(monkeypatch, orig, conv, ["Wheels Inc."])
        f = next(f for f in check.findings if f.code == "orphaned-total")
        assert f.severity == "error"
        assert any("Wheels Inc." in e for e in f.evidence)
        assert any("p2" in e for e in f.evidence)
        assert check.verdict == "REVIEW"

    def test_a_total_on_the_statement_page_is_not_orphaned(self, monkeypatch):
        pages = [_statement("Wheels Inc.", "8 Harbour Road", "Total 43.50")]
        check = self._check(monkeypatch, pages, list(pages), ["Wheels Inc."])
        assert not [f for f in check.findings if f.code == "orphaned-total"]

    def test_a_total_two_pages_from_the_statement_is_not_attributed(self, monkeypatch):
        """The customer's name is on the page BEFORE the total, which is the
        only reason attribution works at all. Two pages away it could be
        anyone's, and guessing would invent a defect."""
        orig = [_statement("Wheels Inc.", "8 Harbour Road", "Total 43.50")]
        conv = [_statement("Wheels Inc.", "8 Harbour Road"),
                _statement("Filler Co.", "unrelated content", "more content",
                           "and more", "and more still", "yet more",
                           "still more", "and more again", "final line"),
                _total_page()]
        check = self._check(monkeypatch, orig, conv, ["Wheels Inc."])
        assert not [f for f in check.findings if f.code == "orphaned-total"]

    def test_a_split_the_original_also_makes_is_faithful(self, monkeypatch):
        """Crystal orphaning the total too means the conversion is right.
        The gate compares - it does not have an opinion about layout."""
        pages = [_statement("Wheels Inc.", "8 Harbour Road"), _total_page()]
        check = self._check(monkeypatch, pages, list(pages), ["Wheels Inc."])
        assert not [f for f in check.findings if f.code == "orphaned-total"]

    def test_the_letters_stated_total_proves_whose_total_it_is(self, monkeypatch):
        """The statement says its own total in prose. A stranded total
        carrying that amount is that customer's - proven, not guessed."""
        orig = [_statement("Wheels Inc.", "8 Harbour Road",
                           "invoices totalling $43.50.", "Total: $43.50")]
        conv = [_statement("Wheels Inc.", "8 Harbour Road",
                           "invoices totalling $43.50."),
                _total_page()]
        check = self._check(monkeypatch, orig, conv, ["Wheels Inc."])
        f = next(f for f in check.findings if f.code == "orphaned-total")
        assert any("Wheels Inc." in e for e in f.evidence)

    def test_a_total_for_a_different_amount_is_not_this_customers(self, monkeypatch):
        """The letter said $43.50 and the stranded total says $912.00, so it
        belongs to the next statement - naming this customer would be a lie."""
        orig = [_statement("Wheels Inc.", "8 Harbour Road",
                           "invoices totalling $43.50.", "Total: $43.50")]
        conv = [_statement("Wheels Inc.", "8 Harbour Road",
                           "invoices totalling $43.50."),
                "\n".join(["Remit Payment to:", "Total 912.00",
                           "legal footer here", "Business Objects"])]
        check = self._check(monkeypatch, orig, conv, ["Wheels Inc."])
        assert not [f for f in check.findings if f.code == "orphaned-total"]

    def test_a_declared_total_must_print_on_the_page_that_declares_it(self, monkeypatch):
        """The demo's real defect, and the one nothing else caught: the
        total is not stranded on an EMPTY page, it is carried over with
        the invoice table onto a busy one. 21 of 36 statements did this
        while the original split none of them."""
        letter = _statement("Wheels Inc.", "8 Harbour Road",
                            "invoices totalling $758.13.")
        orig = [letter + "\nTotal: $758.13"]
        conv = [letter,
                _statement("", *[f"invoice line {n}" for n in range(9)],
                           "Total: $758.13")]
        check = self._check(monkeypatch, orig, conv, ["Wheels Inc."])
        f = next(f for f in check.findings if f.code == "orphaned-total")
        assert any("Wheels Inc." in e for e in f.evidence)
        assert any("p2" in e for e in f.evidence)

    def test_a_declared_total_on_its_own_page_is_fine(self, monkeypatch):
        pages = [_statement("Wheels Inc.", "invoices totalling $758.13.",
                            "Total: $758.13")]
        check = self._check(monkeypatch, pages, list(pages), ["Wheels Inc."])
        assert not [f for f in check.findings if f.code == "orphaned-total"]

    def test_a_street_number_is_not_an_amount(self):
        """Matching bare integers as money made "8 Harbour Road" the
        statement's total, which then disagreed with the real one and
        suppressed the finding. Money has a currency symbol or cents."""
        found = rc._amounts(rc._ANY_MONEY, "8 Harbour Road\nInvoice 2886")
        assert found == set()
        assert rc._amounts(rc._ANY_MONEY, "$43.50 and 912.00") == {"43.50",
                                                                   "912.00"}

    def test_either_spelling_of_totalling_is_read(self, monkeypatch):
        """Crystal's own sample text uses "totalling"; other reports use the
        US "totaling". Reading only one would silently drop the evidence."""
        for word in ("totalling", "totaling"):
            page = f"Wheels Inc.\ninvoices {word} $43.50. Please pay"
            assert rc._amounts(rc._STATED_TOTAL, page) == {"43.50"}

    def test_a_full_page_of_content_is_not_a_total_page(self, monkeypatch):
        """A page that happens to carry a running total mid-table is a real
        page, not a stranded footer."""
        orig = [_statement("Wheels Inc.", "8 Harbour Road", "Total 43.50")]
        conv = [_statement("Wheels Inc.", "8 Harbour Road"),
                _statement("", *[f"invoice line {n}" for n in range(9)],
                           "Total 43.50")]
        check = self._check(monkeypatch, orig, conv, ["Wheels Inc."])
        assert not [f for f in check.findings if f.code == "orphaned-total"]


class TestGroupPageMatching:
    """Two traps that both invented findings on the demo."""

    def test_a_name_inside_a_longer_name_is_not_claimed(self, monkeypatch):
        """"Wheels Inc." matches inside "Sporting Wheels Inc.", so one
        statement looked like two spread fourteen pages apart - and the
        break comparison then reported a difference that did not exist."""
        pages = ["To: Sporting Wheels Inc.\nTotal 10.00",
                 "unrelated filler page",
                 "To: Wheels Inc.\nTotal 20.00"]
        values = ["Sporting Wheels Inc.", "Wheels Inc."]
        assert rc._pages_of(pages, "Wheels Inc.", values) == [2]
        assert rc._pages_of(pages, "Sporting Wheels Inc.", values) == [0]

    def test_only_consecutive_pages_count_as_one_span(self):
        """A statement occupies consecutive pages. A gap means the string
        turned up somewhere else, not that the statement was split."""
        pages = ["Acme here", "someone else", "Acme here again"]
        assert rc._pages_of(pages, "Acme", ["Acme"]) == [0]

    def test_a_real_two_page_statement_is_kept_whole(self):
        pages = ["Acme page one", "Acme page two", "Beta page one"]
        assert rc._pages_of(pages, "Acme", ["Acme", "Beta"]) == [0, 1]

    def test_the_span_count_uses_the_same_rule(self, monkeypatch):
        pages = ["To: Sporting Wheels Inc.", "filler", "To: Wheels Inc."]
        spans = rc._group_spans(pages, ["Sporting Wheels Inc.", "Wheels Inc."])
        assert spans == {"Sporting Wheels Inc.": 1, "Wheels Inc.": 1}
