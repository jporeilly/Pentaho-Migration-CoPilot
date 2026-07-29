"""Saved-data recovery: the .rpt's cached rowset becomes the converted
report's inline dataset, so the .prpt opens in PRD showing real rows with no
database.

The stored encodings were calibrated against reports whose true values are
known independently (the SAP viewer's render of the demo statement, the
AdventureWorks/Xtreme datasets, a MilkoScan report whose milk-fat percentages
are physical reality). These tests pin that calibration - if one fails after
an rpt-rs upgrade, re-verify against the viewer before "fixing" the constant.
"""

import zipfile
from datetime import date, datetime, time
from pathlib import Path

import pytest

from pentaho_migration.reports import load_report_model, write_prpt
from pentaho_migration.reports.rpt_crosstabs import find_rpt_rs
from pentaho_migration.reports.rpt_saved import (
    SavedRows, _convert_cell, _repair_byteswapped_utf16, build_inline_ds_xml,
    load_saved_rows)

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "samples" / "crystal" / "demo"


class TestStoredEncodings:
    def test_numbers_and_currency_are_stored_x100(self):
        """$1,139.55 is stored as the double 113955; 3.5478% milk fat as
        354.78... - the x100 applies to Number and Currency alike."""
        assert _convert_cell("113955", "Number") == 1139.55
        assert _convert_cell("2056562.06", "Currency") == 20565.6206

    def test_dates_are_midnight_based_julian_day_numbers(self):
        # the demo statement's invoice date, per the SAP viewer: 2002-04-03
        assert _convert_cell("2452367", "Date") == date(2002, 4, 3)
        # rpt-rs's own civil-calendar fixture
        assert _convert_cell("2460312", "Date") == date(2024, 1, 3)

    def test_datetime_packs_jdn_low_seconds_high(self):
        packed = (43200 << 32) | 2455719   # noon on AdventureWorks' first ship date
        assert _convert_cell(str(packed), "DateTime") == datetime(2011, 6, 7, 12, 0, 0)
        assert _convert_cell("2455719", "DateTime") == datetime(2011, 6, 7, 0, 0, 0)

    def test_ints_strings_and_booleans_are_raw(self):
        assert _convert_cell("597", "Int32s") == 597
        assert _convert_cell("True", "Boolean") is True
        assert _convert_cell("Crazy Wheels", "String") == "Crazy Wheels"
        assert _convert_cell(None, "Number") is None

    def test_time_is_seconds_since_midnight(self):
        assert _convert_cell("44730", "Time") == time(12, 25, 30)

    def test_garbage_stays_visible_not_vanished(self):
        assert _convert_cell("not-a-number", "Number") == "not-a-number"


class TestInlineDatasource:
    def _saved(self):
        return SavedRows(
            columns=[("NAME", "String"), ("AMOUNT", "Currency"),
                     ("WHEN", "Date")],
            rows=[["Crazy Wheels", 43.5, date(2002, 4, 3)],
                  [None, None, None]],
            total_records=2)

    def test_dates_use_the_engine_bean_format(self):
        """Every date-family converter in the engine parses exactly
        yyyy-MM-dd'T'HH:mm:ss.SSSZ - a bare ISO date fails bundle load with
        'Not a parsable SQL-date' (learned the hard way, live)."""
        xml = build_inline_ds_xml(self._saved())
        assert "2002-04-03T00:00:00.000+0000" in xml
        assert 'type="java.sql.Date"' in xml

    def test_null_cells_and_types(self):
        xml = build_inline_ds_xml(self._saved())
        assert xml.count('<data:data null="true"/>') == 3
        assert 'type="java.lang.Number"' in xml       # column declaration
        assert 'type="java.math.BigDecimal"' in xml   # cell value


@pytest.mark.skipif(find_rpt_rs() is None, reason="rpt-rs not available")
class TestEndToEnd:
    def test_demo_statement_rows_recover_with_real_values(self):
        rpt = DEMO / "Statement_of_Account.rpt"
        if not rpt.exists():
            pytest.skip("demo .rpt not present")
        saved = load_saved_rows(rpt)
        assert saved is not None and len(saved.rows) == 53
        cols = [c[0] for c in saved.columns]
        row0 = dict(zip(cols, saved.rows[0]))
        # ground truth = the SAP viewer's render of page 1
        assert row0["CUSTOMER_NAME"] == "Crazy Wheels"
        assert row0["ORDER_AMOUNT"] == 43.5
        assert row0["ORDER_DATE"] == date(2002, 4, 3)

    def test_bundle_embeds_the_rows_and_keeps_the_sql(self, tmp_path):
        dump = DEMO / "Statement_of_Account.xml"
        rpt = dump.with_suffix(".rpt")
        if not rpt.exists():
            pytest.skip("demo pair not present")
        model = load_report_model(dump, "Xtreme")
        model.saved_rows = load_saved_rows(rpt)
        out = tmp_path / "embedded.prpt"
        write_prpt(model, out, saved_rows=model.saved_rows)
        z = zipfile.ZipFile(out)
        inline = z.read("datasources/inline-ds.xml").decode()
        assert 'name="default"' in inline            # answers the report query
        assert "Crazy Wheels" in inline
        sql = z.read("datasources/sql-ds.xml").decode()
        assert 'name="source-sql"' in sql            # live path one click away
        compound = z.read("datasources/compound-ds.xml").decode()
        assert "inline-ds.xml" in compound


class TestRecoveredValuesBeatDeclaredMetadata:
    """Some .rpt files describe their saved columns wrongly. Believing the
    metadata over the bytes cost a whole report: the World Sales corpus
    report declares every column Int32s while the batches hold country
    names, so the engine failed on the first cell and the bundle would not
    load at all."""

    def test_utf16_byte_order_mixup_is_repaired(self):
        # "Mendoza" stored little-endian, decoded big-endian: every character
        # ends up with a zero low byte
        assert _repair_byteswapped_utf16("䴀攀渀搀漀"
                                         "稀愀") == "Mendoza"

    def test_genuine_cjk_text_is_left_alone(self):
        """The repair must key on the zero-low-byte signature, not on the
        characters merely looking East Asian."""
        for text in ("中文", "Mendoza", "", "中䴀"):
            assert _repair_byteswapped_utf16(text) == text

    def test_one_non_latin_character_does_not_defeat_the_repair(self):
        """Found loading the rebuilt Xtreme database into MySQL, which
        rejected the row: "Provence-Alpes-Cote d'Azur" carries a
        typographic apostrophe, and U+2019 swaps to U+1920 whose low byte
        is 0x20. Requiring EVERY character to carry the zero-low-byte
        signature left the whole string mojibake - as it would for any
        value with a curly quote, an em-dash or a euro sign."""
        original = "Provence-Alpes-Côte d’Azur"
        stored = original.encode("utf-16-le").decode("utf-16-be")
        assert _repair_byteswapped_utf16(stored) == original

    def test_the_repair_swaps_bytes_rather_than_shifting_them(self):
        """Shifting right by 8 recovers a Latin-1 character and discards
        the low byte, so it cannot represent the apostrophe at all."""
        original = "café €5"
        stored = original.encode("utf-16-le").decode("utf-16-be")
        assert _repair_byteswapped_utf16(stored) == original

    def test_a_swap_that_produces_noise_is_not_applied(self):
        """The signature can occur by chance in real CJK. If swapping does
        not yield ordinary text, what was stored is returned - returning
        noise would be worse than returning the original."""
        text = "䴀倀怀瀀"       # all zero low bytes...
        out = _repair_byteswapped_utf16(text)
        # ...and the swap gives control characters, so it must be refused
        # or produce something printable - never silent garbage
        assert out == text or out.isprintable()

    def test_a_string_column_declared_integer_is_emitted_as_string(self):
        saved = SavedRows(columns=[("Country", "Int32s"), ("Sales", "Int32s")],
                          rows=[["Argentina", 5], ["Aruba", 7]])
        xml = build_inline_ds_xml(saved)
        assert '<data:column name="Country" type="java.lang.String"/>' in xml
        assert '<data:column name="Sales" type="java.lang.Integer"/>' in xml
        # ... and the cells must not claim Integer either, or the engine
        # fails converting "Argentina"
        assert "java.lang.Integer\">Argentina" not in xml

    def test_a_genuine_integer_column_keeps_its_type(self):
        saved = SavedRows(columns=[("Qty", "Int32s")], rows=[[1], [2]])
        xml = build_inline_ds_xml(saved)
        assert '<data:column name="Qty" type="java.lang.Integer"/>' in xml
