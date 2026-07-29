"""Crystal's drawing objects: what gets drawn, and where.

Two defects the demo statement made visible, both general to any .rpt:

* a zero-thickness line is a designer's guide, NOT a hairline - Crystal does
  not draw it. Emitted anyway it showed through the gaps between the detail
  fields as a stray dot and a trailing underline on every row;
* an underlay copied into a following section can compute a NEGATIVE y when
  a spacer section sits between the two. A PRD band has no space above its
  origin, and the engine responded by pushing the watermark BELOW the letter
  instead of behind it.
"""

import textwrap
import zipfile

from pentaho_migration.reports import load_report_model, write_prpt


def _model(tmp_path, body):
    p = tmp_path / "r.xml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return load_report_model(p, None)


def _report(sections):
    return f"""\
<Report Name="D" FileName="d.rpt">
  <Database><Tables><Table Name="T" Alias="T"><Fields>
    <Field Name="AMT" ValueType="NumberField"/>
  </Fields></Table></Tables></Database>
  <DataDefinition><RecordSelectionFormula/></DataDefinition>
  <ReportDefinition><Areas>
    <Area Kind="Detail"><Sections>{sections}</Sections></Area>
  </Areas></ReportDefinition>
</Report>"""


class TestZeroThicknessIsNotDrawn:
    def test_a_zero_thickness_line_never_reaches_the_model(self, tmp_path):
        model = _model(tmp_path, _report("""
            <Section Name="D1" Height="240"><ReportObjects>
              <LineObject Name="L" Top="100" Left="0" Width="9360"
                          Height="0" LineThickness="0"/>
              <FieldObject Name="F" Left="0" Top="0" Width="1440"
                           Height="220" DataSource="{T.AMT}"/>
            </ReportObjects></Section>"""))
        kinds = [e.kind for s in model.sections for e in s.elements]
        assert "line" not in kinds
        assert "field" in kinds        # the rest of the band is untouched

    def test_a_real_line_is_still_drawn(self, tmp_path):
        """Only zero is special - the page-header rule and the Total box in
        the demo carry thickness 20 and must survive."""
        model = _model(tmp_path, _report("""
            <Section Name="D1" Height="240"><ReportObjects>
              <LineObject Name="L" Top="100" Left="0" Width="9360"
                          Height="0" LineThickness="20"/>
            </ReportObjects></Section>"""))
        assert [e.kind for s in model.sections for e in s.elements] == ["line"]

    def test_a_zero_thickness_box_is_dropped_too(self, tmp_path):
        model = _model(tmp_path, _report("""
            <Section Name="D1" Height="240"><ReportObjects>
              <BoxObject Name="B" Top="0" Left="0" Width="3479"
                         Height="390" LineThickness="0"/>
            </ReportObjects></Section>"""))
        assert not [e for s in model.sections for e in s.elements]

    def test_marking_it_invisible_is_not_enough(self, tmp_path):
        """The engine drew the line anyway when it was only styled
        invisible, so it must not be in the bundle at all."""
        model = _model(tmp_path, _report("""
            <Section Name="D1" Height="240"><ReportObjects>
              <LineObject Name="L" Top="100" Left="0" Width="9360"
                          Height="0" LineThickness="0"/>
            </ReportObjects></Section>"""))
        out = tmp_path / "d.prpt"
        write_prpt(model, out)
        with zipfile.ZipFile(out) as z:
            layout = z.read("layout.xml").decode("utf-8")
        assert "horizontal-line" not in layout


UNDERLAY_WITH_SPACER = """
    <Section Name="U" Height="4080">
      <SectionFormat EnableUnderlaySection="True"/>
      <ReportObjects>
        <PictureObject Name="P" Top="0" Left="720" Width="9504" Height="4080"><ImageData>iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFUlEQVR4nGP8/+4qAzbAhFV00EoAAClcAtLbS0aeAAAAAElFTkSuQmCC</ImageData></PictureObject>
      </ReportObjects>
    </Section>
    <Section Name="Spacer" Height="600"><ReportObjects/></Section>
    <Section Name="Letter" Height="4080"><ReportObjects>
      <TextObject Name="T" Top="180" Left="1200" Width="8385" Height="1590">
        <Text>Dear customer</Text></TextObject>
    </ReportObjects></Section>"""


# An underlay watermark over two mutually-exclusive letter variants: each
# variant carries a suppress CONDITION, so at runtime exactly one of them
# renders. They share one slot, and the watermark has to ride BOTH - the
# customer whose statement shows variant B must still get it.
UNDERLAY_OVER_VARIANTS = """
    <Section Name="U" Height="2040">
      <SectionFormat EnableUnderlaySection="True"/>
      <ReportObjects>
        <PictureObject Name="P" Top="0" Left="720" Width="9504" Height="2040"><ImageData>iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFUlEQVR4nGP8/+4qAzbAhFV00EoAAClcAtLbS0aeAAAAAElFTkSuQmCC</ImageData></PictureObject>
      </ReportObjects>
    </Section>
    <Section Name="VariantA" Height="2040">
      <SectionFormat EnableSuppress="False">
        <SectionAreaFormatConditionFormulas EnableSuppress="{T.AMT} &gt; 100"/>
      </SectionFormat>
      <ReportObjects>
        <TextObject Name="TA" Top="180" Left="1200" Width="8385" Height="220"><Text>Premium customer letter</Text></TextObject>
      </ReportObjects>
    </Section>
    <Section Name="VariantB" Height="2040">
      <SectionFormat EnableSuppress="False">
        <SectionAreaFormatConditionFormulas EnableSuppress="{T.AMT} &lt;= 100"/>
      </SectionFormat>
      <ReportObjects>
        <TextObject Name="TB" Top="180" Left="1200" Width="8385" Height="220"><Text>Standard customer letter</Text></TextObject>
      </ReportObjects>
    </Section>"""


class TestUnderlayRidesEveryLetterVariant:
    """The bug the release gate caught: computing offsets from the DESIGN
    stack put the watermark into variant A only, so the customer whose
    statement rendered variant B lost the signature block. Mutually-exclusive
    conditional sections share ONE runtime slot, and the underlay element has
    to be copied into each of them."""

    def _layout(self, tmp_path):
        model = _model(tmp_path, _report(UNDERLAY_OVER_VARIANTS))
        out = tmp_path / "v.prpt"
        write_prpt(model, out)
        with zipfile.ZipFile(out) as z:
            return z.read("layout.xml").decode("utf-8")

    def test_the_watermark_is_copied_into_both_variants(self, tmp_path):
        # the underlay band is dropped, so every <content> image in the
        # layout is a copy - one per variant that shares the slot
        assert self._layout(tmp_path).count("<content") == 2

    def test_both_variant_letters_still_render(self, tmp_path):
        layout = self._layout(tmp_path)
        assert "Premium customer letter" in layout
        assert "Standard customer letter" in layout

    def test_neither_copy_is_pushed_above_its_band(self, tmp_path):
        # both variants start at the same slot, so both copies sit at y=0,
        # never negative - the watermark stays behind the text
        assert 'y="-' not in self._layout(tmp_path)


class TestUnderlayStaysInsideItsBand:
    def test_the_copy_never_gets_a_negative_offset(self, tmp_path):
        """A spacer between the underlay and what it underlays made the
        offset negative; the watermark then rendered below the letter."""
        model = _model(tmp_path, _report(UNDERLAY_WITH_SPACER))
        out = tmp_path / "u.prpt"
        write_prpt(model, out)
        with zipfile.ZipFile(out) as z:
            layout = z.read("layout.xml").decode("utf-8")
        assert 'y="-' not in layout, "an element is positioned above its band"

    def test_the_watermark_is_painted_behind_the_text(self, tmp_path):
        """PRD has no z-index - paint order IS document order, so the
        underlay copy has to come first in the band."""
        import re

        model = _model(tmp_path, _report(UNDERLAY_WITH_SPACER))
        out = tmp_path / "u.prpt"
        write_prpt(model, out)
        with zipfile.ZipFile(out) as z:
            layout = z.read("layout.xml").decode("utf-8")
        order = re.findall(r"<(content|label|message|text-field)\b", layout)
        assert order, "nothing rendered"
        assert order[0] == "content", f"watermark is not first: {order}"


class TestWhiteIsNoFill:
    """RptToXml exports <BackgroundColor Name="White"/> on virtually every
    object whether or not Crystal applies a fill. Painting it made each label
    an opaque tile, which hid the grey Total box sitting behind the "Total:"
    label and the amount."""

    def _layout(self, tmp_path, bg):
        model = _model(tmp_path, _report(f"""
            <Section Name="D1" Height="240"><ReportObjects>
              <BoxObject Name="B" Top="0" Left="0" Width="3479" Height="390"
                         LineThickness="20">
                <BackgroundColor Name="grey" A="255" R="219" G="219" B="219"/>
                <BorderColor Name="Black" A="255" R="0" G="0" B="0"/>
              </BoxObject>
              <TextObject Name="T" Top="0" Left="200" Width="1440"
                          Height="220"><Text>Total:</Text>
                <BackgroundColor Name="{bg[0]}" A="255" R="{bg[1]}"
                                 G="{bg[2]}" B="{bg[3]}"/>
              </TextObject>
            </ReportObjects></Section>"""))
        out = tmp_path / "w.prpt"
        write_prpt(model, out)
        with zipfile.ZipFile(out) as z:
            return z.read("layout.xml").decode("utf-8")

    def test_a_white_label_background_is_not_painted(self, tmp_path):
        layout = self._layout(tmp_path, ("White", 255, 255, 255))
        assert 'background-color="#ffffff"' not in layout

    def test_a_real_colour_still_is(self, tmp_path):
        """Only white is treated as no-fill; a deliberate colour survives."""
        layout = self._layout(tmp_path, ("teal", 64, 128, 128))
        assert 'background-color="#408080"' in layout

    def test_the_box_keeps_its_own_fill(self, tmp_path):
        layout = self._layout(tmp_path, ("White", 255, 255, 255))
        assert 'fill-color="#dbdbdb"' in layout
        assert 'fill-shape="true"' in layout


class TestPicturesFillTheirBox:
    def test_a_picture_scales_to_fill_rather_than_letterbox(self, tmp_path):
        """Crystal scales a picture to fill its box. Preserving the aspect
        letterboxed the statement's watermark to 315pt inside a 475pt box,
        so it read as clipped."""
        model = _model(tmp_path, _report(UNDERLAY_WITH_SPACER))
        out = tmp_path / "p.prpt"
        write_prpt(model, out)
        with zipfile.ZipFile(out) as z:
            layout = z.read("layout.xml").decode("utf-8")
        assert 'scale="true"' in layout
        assert 'keep-aspect-ratio="false"' in layout
