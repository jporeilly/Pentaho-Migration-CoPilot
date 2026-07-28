"""Crystal's group tree, recreated as the converted report's PDF outline.

The Crystal viewer's left-hand tree - countries, then customers within each -
is how anyone navigates a long statement run. Without it the converted report
is a flat scroll, which is the first thing a customer notices about a 62-page
document.

PRD's equivalent is the `bookmark` band style on a group header. The engine's
PDF writer attaches every bookmark to the ROOT outline
(PdfLogicalPageDrawable.drawBookmark), so a true hierarchy is not reachable -
inner groups are indented instead, which reads as the tree it represents.
"""

import textwrap
import zipfile

import pytest

from pentaho_migration.reports import load_report_model, write_prpt
from pentaho_migration.reports.prpt_writer import NBSP


def _dump(tmp_path, body):
    p = tmp_path / "r.xml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _report(groups_xml, group_headers=""):
    return f"""\
<Report Name="G" FileName="g.rpt">
  <Database><Tables><Table Name="T" Alias="T"><Fields>
    <Field Name="COUNTRY" ValueType="StringField"/>
    <Field Name="CUSTOMER" ValueType="StringField"/>
    <Field Name="AMT" ValueType="NumberField"/>
  </Fields></Table></Tables></Database>
  <DataDefinition><RecordSelectionFormula/>{groups_xml}</DataDefinition>
  <ReportDefinition><Areas>
    {group_headers}
    <Area Kind="Detail"><Sections>
      <Section Name="D1" Height="240"><ReportObjects>
        <FieldObject Name="F1" Left="0" Top="0" Width="1440" Height="220"
                     DataSource="{{T.AMT}}"/>
      </ReportObjects></Section>
    </Sections></Area>
  </Areas></ReportDefinition>
</Report>"""


TWO_GROUPS = """
    <Groups>
      <Group Name="G1" ConditionField="{T.COUNTRY}"/>
      <Group Name="G2" ConditionField="{T.CUSTOMER}"/>
    </Groups>"""

HEADERS = """
    <Area Kind="GroupHeader"><Sections>
      <Section Name="GH1" Height="240"><ReportObjects>
        <FieldObject Name="C1" Left="0" Top="0" Width="1440" Height="220"
                     DataSource="{T.COUNTRY}"/>
      </ReportObjects></Section>
      <Section Name="GH2" Height="240"><ReportObjects>
        <FieldObject Name="C2" Left="0" Top="0" Width="1440" Height="220"
                     DataSource="{T.CUSTOMER}"/>
      </ReportObjects></Section>
    </Sections></Area>"""


def _layout(tmp_path, dump):
    out = tmp_path / "g.prpt"
    write_prpt(load_report_model(dump, None), out)
    with zipfile.ZipFile(out) as z:
        return z.read("layout.xml").decode("utf-8")


class TestBookmarksAreEmitted:
    def test_each_group_header_bookmarks_its_own_column(self, tmp_path):
        layout = _layout(tmp_path, _dump(tmp_path, _report(TWO_GROUPS, HEADERS)))
        assert 'style-key="bookmark"' in layout
        assert "[COUNTRY]" in layout and "[CUSTOMER]" in layout

    def test_inner_groups_are_indented_to_read_as_a_tree(self, tmp_path):
        """The engine offers no nesting, so depth is carried by indent."""
        layout = _layout(tmp_path, _dump(tmp_path, _report(TWO_GROUPS, HEADERS)))
        assert f'="{NBSP * 4}" &amp; [CUSTOMER]' in layout
        # the outermost group is NOT indented
        assert 'formula="=[COUNTRY]"' in layout

    def test_the_indent_is_a_non_breaking_space(self):
        """An ordinary leading space is free to be collapsed by a PDF
        viewer's outline panel; a non-breaking one is not."""
        assert NBSP == " "

    def test_a_report_with_no_groups_gets_no_bookmarks(self, tmp_path):
        layout = _layout(tmp_path, _dump(tmp_path, _report("")))
        assert 'style-key="bookmark"' not in layout


class TestAgainstTheEngine:
    """The XML being right is not the same as the engine producing an
    outline - the bookmark style key had to be verified by rendering."""

    def test_the_demo_report_renders_a_navigable_outline(self):
        import io
        from pathlib import Path

        from pentaho_migration.reports.prpt_validator import (
            render_prpt_pdf_live, validator_available)
        from pentaho_migration.reports.rpt_saved import load_saved_rows

        if not validator_available():
            pytest.skip("no local PRD install + Java")
        demo = (Path(__file__).resolve().parents[1] / "samples" / "crystal"
                / "demo" / "souvikduttachoudhury_Statement_of_Account.xml")
        if not demo.exists():
            pytest.skip("demo dump not present")
        model = load_report_model(demo, None)
        model.saved_rows = load_saved_rows(demo.with_suffix(".rpt"))
        if model.saved_rows is None:
            pytest.skip("no saved rows recovered")
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "x.prpt"
            write_prpt(model, out, saved_rows=model.saved_rows)
            pdf = render_prpt_pdf_live(out)

        from pypdf import PdfReader

        titles = []

        def walk(items):
            for it in items:
                if isinstance(it, list):
                    walk(it)
                else:
                    titles.append(str(it.title))

        walk(PdfReader(io.BytesIO(pdf)).outline)
        assert len(titles) > 20, "no group tree in the rendered PDF"
        # outer group values are flush, inner ones indented
        assert "Canada" in titles
        assert any(t.startswith(NBSP) for t in titles)
