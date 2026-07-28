"""Trailing empty space in a band that ends the page.

The demo statement split 21 of its 36 statements for this one reason: the
group footer declared 138.75pt while its content ended at 80.25pt, and the
page had about 125pt left. A band that would have FIT jumped to the next
page and took the statement's total with it - while the original, which
Crystal lays out with more room to spare, split none of them.

The 58.5pt was unreachable. The band sets Crystal's "New Page After", so a
page break follows immediately and nothing can ever render in that space.
Reserving it bought nothing and cost the statement.

The numbers below are the demo's own, so a regression reproduces the
defect rather than an abstraction of it.
"""

from pentaho_migration.reports.model import Element, Section
from pentaho_migration.reports.prpt_writer import _section_band


def _height(band: str) -> float:
    """The band's own min-height in points."""
    tag = band.split("spatial-styles ")[1]
    return float(tag.split('min-height="')[1].split('"')[0])


def _footer(**kw) -> Section:
    """The demo's group footer: 138.75pt declared, ink ending at 80.25pt."""
    kw.setdefault("new_page_after", True)
    section = Section(area_kind="GroupFooter", name="GF1", height=138.75, **kw)
    section.elements.append(
        Element(kind="field", name="total", x=5.0, y=22.5,
                width=50.0, height=57.75, column="AMT"))
    return section


class TestSpaceNothingCanReach:
    def test_slack_before_a_page_break_is_not_reserved(self):
        assert _height(_section_band(_footer())) == 80.25

    def test_slack_is_kept_when_no_page_break_follows(self):
        """Without a break the space is real: the next band stacks below it,
        so removing it would move content up the page."""
        assert _height(_section_band(_footer(new_page_after=False))) == 138.75

    def test_a_background_fill_makes_the_slack_visible(self):
        """A coloured band paints its whole height. Trimming it would
        shorten a panel the reader can see."""
        assert _height(_section_band(_footer(bg_color="#ffffcc"))) == 138.75

    def test_an_empty_band_keeps_its_declared_height(self):
        """Crystal's declared height is the whole meaning of an empty band -
        it is how a zero-height detail band prints one page, not one per
        row. There is no ink to fall back to, so it must survive."""
        empty = Section(area_kind="GroupFooter", name="GF2", height=138.75,
                        new_page_after=True)
        assert _height(_section_band(empty)) == 138.75

    def test_an_object_reaching_past_the_declared_height_still_wins(self):
        """The band must never end up shorter than what it holds - the trim
        only ever removes space BELOW the last object."""
        section = _footer()
        section.height = 40.0        # declared shorter than its own content
        assert _height(_section_band(section)) == 80.25
