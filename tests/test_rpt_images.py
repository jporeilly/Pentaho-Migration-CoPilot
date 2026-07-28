"""Image carving: .rpt binary -> decode-proven PNGs -> aspect-matched
injection into the dump's PictureObjects (the free SAP SDK cannot read
picture bytes - PictureData is null in the embedded RAS)."""

import base64
import io
import struct
from pathlib import Path

import pytest
from PIL import Image

from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.rpt_images import (
    CarvedImage, carve_rpt_images, enrich_dump, match_images)

RPT_DIR = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "corpus"
REAL = Path(__file__).resolve().parents[1] / "samples" / "crystal" / "corpus"


def _png_bytes(w, h, color=(200, 30, 30)):
    img = Image.new("RGB", (w, h), color)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _dib_bytes(w, h):
    """Uncompressed 24bpp DIB (BITMAPINFOHEADER only, as Crystal stores)."""
    row = ((w * 24 + 31) // 32) * 4
    header = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, row * h, 0, 0, 0, 0)
    return header + b"\x40\x80\xc0" * (row * h // 3 + 1)


class TestCompoundFileStreams:
    """An .rpt is an OLE compound file. Any picture larger than one 512-byte
    sector is chained across sectors that need not be adjacent on disk, so
    scanning raw file bytes splices foreign data into the middle of the image.
    It still decodes - it just renders torn - which is why this is pinned."""

    REPORT = "Statement_of_Account"

    def _rpt(self):
        p = RPT_DIR / f"{self.REPORT}.rpt"
        if not p.exists():
            pytest.skip("corpus .rpt not present")
        return p

    def test_every_embedded_picture_is_recovered_and_distinct(self):
        """Three logos in the report means three different logos out."""
        images = carve_rpt_images(self._rpt())
        assert len(images) == 3
        assert len({img.png for img in images}) == 3

    def test_raw_byte_scanning_would_have_corrupted_one(self):
        from pentaho_migration.reports import rpt_images

        rpt = self._rpt()
        clean = {(i.width, i.height): i.png for i in carve_rpt_images(rpt)}
        raw = {(i.width, i.height): i.png
               for i in rpt_images._carved_from_raw_bytes(rpt)}
        shared = set(clean) & set(raw)
        assert shared, "the raw scan should still find the same pictures"
        assert any(clean[k] != raw[k] for k in shared), (
            "this report is the regression fixture precisely because one of "
            "its pictures spans sectors - if raw and stream carving now agree, "
            "the fixture no longer exercises the bug")

    def test_pictures_are_not_assigned_the_same_image_twice(self, tmp_path):
        import xml.etree.ElementTree as ET

        dump = REAL / f"{self.REPORT}.xml"
        if not dump.exists():
            pytest.skip("corpus dump not present")
        tree = ET.parse(dump)
        for pic in tree.getroot().iter("PictureObject"):
            for data in pic.findall("ImageData"):
                pic.remove(data)
        stripped = tmp_path / "stripped.xml"
        tree.write(stripped, encoding="utf-8", xml_declaration=True)

        assert enrich_dump(stripped, self._rpt()) == 3
        injected = [d.text for d in ET.parse(stripped).getroot().iter("ImageData")]
        assert len(set(injected)) == 3, (
            "a distinct image must not be spent on one box while another image "
            "goes unused - that is how a signature becomes a second logo")


class TestCarving:
    def test_carves_png_and_dib_from_binary_soup(self, tmp_path):
        blob = b"\x00" * 100 + _png_bytes(40, 20) + b"junk" + _dib_bytes(30, 30) + b"\xff" * 50
        p = tmp_path / "fake.rpt"
        p.write_bytes(blob)
        found = carve_rpt_images(p)
        dims = {(i.width, i.height) for i in found}
        assert (40, 20) in dims and (30, 30) in dims
        # every carved image is re-encoded as PNG
        assert all(i.png.startswith(b"\x89PNG") for i in found)

    def test_tiny_noise_ignored(self, tmp_path):
        p = tmp_path / "noise.rpt"
        p.write_bytes(_png_bytes(4, 4))
        assert carve_rpt_images(p) == []

    @pytest.mark.skipif(not (RPT_DIR / "GeneralIrma.rpt").exists(),
                        reason="corpus .rpt not present")
    def test_real_rpt_yields_decoded_logo(self):
        found = carve_rpt_images(RPT_DIR / "GeneralIrma.rpt")
        assert any(i.width == 213 and i.height == 39 for i in found)


class TestMatching:
    def _img(self, w, h):
        return CarvedImage(_png_bytes(w, h), w, h, 24, "dib")

    def test_single_box_single_image_matches_unconditionally(self):
        m = match_images([("a", 999, 10)], [self._img(30, 30)])
        assert "a" in m  # cropping can break the ratio - still assign

    def test_best_aspect_wins(self):
        wide, tall = self._img(200, 40), self._img(50, 100)
        m = match_images([("wide", 1000, 210), ("tall", 500, 900)], [wide, tall])
        assert m["wide"] is wide and m["tall"] is tall

    def test_page_thumbnail_stays_unmatched(self):
        # a saved A4-shaped preview never wins over the real logo
        logo, thumb = self._img(213, 39), self._img(198, 281)
        m = match_images([("logo", 1481, 244)], [logo, thumb])
        assert m["logo"] is logo

    def test_implausible_aspect_is_left_todo(self):
        m = match_images([("a", 1000, 10), ("b", 10, 1000)], [self._img(50, 50)])
        assert m == {}


class TestEnrichment:
    DUMP = """<?xml version="1.0" encoding="utf-8"?>
<Report Name="R" FileName="r.rpt" HasSavedData="False">
<Database><Tables><Table Name="Command" Alias="Command" ClassName="CommandTable">
<Command>SELECT a AS "A" FROM t</Command>
<Fields><Field Name="A" ValueType="StringField"/></Fields></Table></Tables></Database>
<DataDefinition><Groups/><SortFields/><FormulaFieldDefinitions/>
<ParameterFieldDefinitions/><SummaryFields/></DataDefinition>
<ReportDefinition><Areas>
<Area Kind="ReportHeader" Name="RHArea"><Sections>
<Section Name="RH" Height="1000"><SectionFormat EnableSuppress="false"/>
<ReportObjects>
<PictureObject Name="Logo" Left="0" Top="0" Width="2000" Height="400"/>
</ReportObjects></Section></Sections></Area>
</Areas></ReportDefinition></Report>
"""

    def test_enrich_injects_and_parser_flags_for_review(self, tmp_path):
        dump = tmp_path / "r.xml"
        dump.write_text(self.DUMP, encoding="utf-8")
        rpt = tmp_path / "r.rpt"
        rpt.write_bytes(b"\x00" * 64 + _png_bytes(200, 40) + b"\x00" * 64)

        assert enrich_dump(dump, rpt) == 1
        model = load_report_model(dump)
        (el,) = [e for s in model.sections for e in s.elements if e.kind == "image"]
        assert el.image_bytes.startswith(b"\x89PNG")
        assert el.image_mime == "image/png"
        assert any("carved" in n for n in el.notes)

    def test_enrich_is_idempotent(self, tmp_path):
        dump = tmp_path / "r.xml"
        dump.write_text(self.DUMP, encoding="utf-8")
        rpt = tmp_path / "r.rpt"
        rpt.write_bytes(_png_bytes(200, 40))
        assert enrich_dump(dump, rpt) == 1
        assert enrich_dump(dump, rpt) == 0  # already has ImageData

    def test_no_images_in_rpt_leaves_dump_untouched(self, tmp_path):
        dump = tmp_path / "r.xml"
        dump.write_text(self.DUMP, encoding="utf-8")
        rpt = tmp_path / "r.rpt"
        rpt.write_bytes(b"\x00" * 256)
        assert enrich_dump(dump, rpt) == 0
        assert "ImageData" not in dump.read_text(encoding="utf-8")


@pytest.mark.skipif(not (REAL / "GeneralIrma.xml").exists(),
                    reason="corpus dump not present")
def test_corpus_dump_carries_carved_logo():
    """The enriched corpus dump converts with its real logo embedded."""
    model = load_report_model(REAL / "GeneralIrma.xml")
    imgs = [e for s in model.sections for e in s.elements
            if e.kind == "image" and e.image_bytes]
    assert imgs, "expected the carved logo in the enriched corpus dump"
