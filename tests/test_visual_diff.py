"""The gate's appearance check.

Everything else in the gate reads extracted TEXT, which is blind to what a
reader notices first: a background panel that vanished, a rule the original
does not draw, a box that lost its fill. All of those leave the text
identical, so the gate reported SHIP through a series of real visual defects
until this existed.

Two properties make it worth having rather than noise: pages are PAIRED BY
CONTENT before comparison (74 original pages against 58 converted ones would
otherwise flag everything), and the comparison is deliberately coarse, so it
is loud about a missing panel and silent about two engines hinting a glyph
differently.
"""

import io

import pytest

from pentaho_migration.reports import visual_diff as vd

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402


def _pdf(pages):
    """A small PDF from a list of draw(canvas) callables."""
    imgs = []
    for draw_fn in pages:
        img = Image.new("RGB", (612, 792), "white")
        draw_fn(ImageDraw.Draw(img))
        imgs.append(img)
    buf = io.BytesIO()
    imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:])
    return buf.getvalue()


def _text(*lines):
    return [set(lines)]


class TestPagePairing:
    def test_pages_are_paired_by_content_not_by_index(self):
        """The conversion is shorter, so page N is not page N."""
        orig = [{"alpha"}, {"filler"}, {"beta"}, {"filler2"}, {"gamma"}]
        conv = [{"alpha"}, {"beta"}, {"gamma"}]
        pairs = vd.pair_pages(orig, conv)
        assert pairs == [(0, 0), (2, 1), (4, 2)]

    def test_matching_only_moves_forward(self):
        """Repeated page furniture must not pair a late page with an early
        one and make the whole document look reordered."""
        orig = [{"a", "footer"}, {"b", "footer"}, {"c", "footer"}]
        conv = [{"c", "footer"}, {"b", "footer"}]
        pairs = vd.pair_pages(orig, conv)
        assert pairs == sorted(pairs)

    def test_unrelated_pages_are_not_paired(self):
        assert vd.pair_pages([{"alpha"}], [{"totally", "different"}]) == []


class TestItSeesWhatTextCannot:
    def test_a_missing_panel_is_caught(self):
        """The defect that started this: a filled background the conversion
        never drew. Identical text, obviously different page."""
        with_panel = _pdf([lambda d: d.rectangle([60, 200, 550, 500],
                                                 fill=(255, 238, 213))])
        without = _pdf([lambda d: None])
        out = vd.compare_visually(with_panel, without,
                                  _text("statement"), _text("statement"))
        assert out["pages"], "a missing panel went unnoticed"
        _o, _c, fraction, where = out["pages"][0]
        assert fraction > vd.PAGE_TOLERANCE
        assert "missing something the original prints" in where

    def test_something_drawn_that_should_not_be_is_caught(self):
        """The other direction: a rule Crystal does not draw."""
        clean = _pdf([lambda d: None])
        extra = _pdf([lambda d: d.rectangle([60, 200, 550, 500], fill="black")])
        out = vd.compare_visually(clean, extra,
                                  _text("statement"), _text("statement"))
        assert out["pages"]
        assert "prints something the original does not" in out["pages"][0][3]

    def test_identical_pages_are_not_flagged(self):
        same = _pdf([lambda d: d.rectangle([60, 200, 550, 500], fill="grey")])
        out = vd.compare_visually(same, same,
                                  _text("statement"), _text("statement"))
        assert out["pages"] == []
        assert out["compared"] == 1

    def test_a_tiny_difference_is_tolerated(self):
        """Two engines never rasterize identically - a few points of drift
        must not cry wolf on every page."""
        a = _pdf([lambda d: d.rectangle([60, 200, 550, 500], fill="grey")])
        b = _pdf([lambda d: d.rectangle([62, 202, 552, 502], fill="grey")])
        out = vd.compare_visually(a, b, _text("statement"), _text("statement"))
        assert out["pages"] == []


class TestItReportsWhatItDid:
    def test_the_number_compared_is_always_reported(self):
        """No silent caps: a sampled comparison must say how many pages it
        looked at, or a partial check reads as a whole one."""
        page = lambda d: None  # noqa: E731
        pdf = _pdf([page] * 3)
        out = vd.compare_visually(pdf, pdf, [{"a"}, {"b"}, {"c"}],
                                 [{"a"}, {"b"}, {"c"}])
        assert out["compared"] == 3 and out["available"] == 3

    def test_no_pairable_pages_is_not_a_clean_result(self):
        pdf = _pdf([lambda d: None])
        out = vd.compare_visually(pdf, pdf, [{"alpha"}], [{"unrelated"}])
        assert out["compared"] == 0
        assert out["pages"] == []


class TestGlobalDifferencesAreSaidOnce:
    """A fill missing from a band that REPEATS is one defect with one fix,
    not one per page. Listing it page by page reads as N problems and gets
    costed N times."""

    def _finding(self, pages, compared):
        from pentaho_migration.reports.release_check import _appearance_finding
        return _appearance_finding({"compared": compared,
                                    "available": compared, "pages": pages})

    def test_a_difference_on_every_page_is_reported_as_report_wide(self):
        pages = [(i, i, 0.2, "middle of the page - content differs")
                 for i in range(12)]
        f = self._finding(pages, 12)
        assert "REPORT-WIDE" in f.message
        assert "one difference in a band that repeats" in f.message
        # two evidence lines, not twelve
        assert len(f.evidence) <= 3

    def test_wording_may_vary_while_the_place_does_not(self):
        """The same missing fill reads as "missing something" where it
        dominates and "content differs" where text moved too."""
        pages = [(0, 0, 0.3, "middle of the page - the conversion is missing "
                             "something the original prints")]
        pages += [(i, i, 0.2, "middle of the page - content differs")
                  for i in range(1, 12)]
        assert "REPORT-WIDE" in self._finding(pages, 12).message

    def test_a_one_page_difference_is_still_listed_per_page(self):
        """Not everything is global - a single odd page must stay visible."""
        f = self._finding([(3, 3, 0.2, "top of the page - content differs")], 12)
        assert "REPORT-WIDE" not in f.message
        assert "1 of 12" in f.message

    def test_pages_differing_elsewhere_are_still_counted(self):
        pages = [(i, i, 0.2, "middle of the page - content differs")
                 for i in range(10)]
        pages += [(11, 11, 0.3, "bottom of the page - content differs")]
        f = self._finding(pages, 11)
        assert "REPORT-WIDE" in f.message
        assert any("further page(s) differ elsewhere" in e for e in f.evidence)
