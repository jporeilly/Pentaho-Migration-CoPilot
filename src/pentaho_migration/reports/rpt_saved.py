"""Recover a report's SAVED DATA rows from the .rpt binary, typed and scaled.

A Crystal report saved with its data carries the cached rowset inside the
binary. That is what lets the original render in the Crystal viewer with no
database — and, recovered here, what lets the CONVERTED .prpt open in Report
Designer showing real rows with no database either: the missing half of the
end-to-end demo.

rpt-rs (`rpt saved --limit all --json`) decodes the stored batches into raw
cells. The stored encodings, calibrated against reports whose true values are
known (the SAP viewer render, the AdventureWorks/Xtreme datasets, a MilkoScan
instrument report whose fat percentages are physical reality):

* Number / Currency — an 8-byte double holding the value **x100** (a milk-fat
  reading of 3.5478% is stored as 354.78..., $1,139.55 as 113955);
* Date — an integer Julian Day Number, midnight-based (2452368 = 2002-04-03);
* DateTime — a 64-bit scalar: low u32 = the date's JDN, high u32 = seconds
  since midnight;
* Time — seconds since midnight;
* Int8/16/32, String, Boolean — stored as themselves.

Only decode-proven data is used: a report without saved data, a missing
rpt-rs, or a decode failure all yield None and the conversion proceeds
exactly as before (JNDI datasource, no rows).
"""

import json
import subprocess

from pentaho_migration.reports.proc import run_nice
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

from pentaho_migration.reports.rpt_crosstabs import find_rpt_rs

# Midnight-based JDN of 1970-01-01 (matches rpt-rs's own civil-calendar tests:
# serial 2460312 = 2024-01-03).
_JDN_EPOCH = 2440587
_SAVED_TIMEOUT = 120.0

# Keep bundles sane: a demo dataset, not a data warehouse. Reports beyond this
# embed the first N rows with a note - PRD opens instantly either way.
MAX_EMBED_ROWS = 5000


@dataclass
class SavedRows:
    """A recovered rowset, converted to real values, keyed by SHORT column
    names (the names the converted layout binds to)."""

    columns: list = field(default_factory=list)   # [(short_name, value_type)]
    rows: list = field(default_factory=list)      # [[python value | None]]
    total_records: int = 0
    notes: list = field(default_factory=list)


def _jdn_to_date(serial: int) -> date:
    return date(1970, 1, 1) + timedelta(days=serial - _JDN_EPOCH)


# How much of a string must carry the swapped-Latin signature before the
# repair runs. Genuine CJK scores near zero here, a swapped Latin string
# near one, so anything in the middle would be a coincidence either way.
_SWAP_SHARE = 0.6


def _repair_byteswapped_utf16(text: str) -> str:
    """Undo a UTF-16 byte-order mix-up in a recovered string.

    Crystal stores some saved strings as UTF-16LE, and those come back
    decoded as big-endian: "Mendoza" arrives as a run of CJK-looking
    characters whose low byte is always zero (M = 0x4D reads as U+4D00).
    That signature is what makes the repair safe to apply automatically -
    genuine CJK text has non-zero low bytes almost immediately, so it is
    never mistaken for a swapped Latin string.

    The signature is a MAJORITY test, not a unanimous one, and the repair
    swaps bytes rather than shifting them. Requiring every character to
    carry a zero low byte meant one non-Latin character defeated the whole
    string: "Provence-Alpes-Cote d'Azur" with a typographic apostrophe
    (U+2019 swaps to U+1920, low byte 0x20) stayed mojibake, and shifting
    right by 8 would have dropped that apostrophe even if it had run. Any
    string carrying a curly quote, an em-dash or a euro sign hit this."""
    if not text:
        return text
    looks_swapped = sum(1 for c in text if ord(c) > 0xFF and not ord(c) & 0xFF)
    if looks_swapped < len(text) * _SWAP_SHARE:
        return text
    try:
        repaired = text.encode("utf-16-be", "surrogatepass").decode("utf-16-le")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text
    # A swap that did not produce ordinary text was not the right reading -
    # genuine CJK put through this comes out as noise, and returning noise
    # would be worse than returning what was stored.
    if sum(1 for c in repaired if ord(c) < 0x0500) < len(repaired) * _SWAP_SHARE:
        return text
    return repaired


def _convert_cell(raw: str | None, value_type: str):
    """One stored cell -> a real Python value. Unparseable cells return the
    raw text rather than None - visible beats vanished."""
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = _repair_byteswapped_utf16(raw)
    try:
        if value_type in ("Number", "Currency"):
            # the /100 un-scaling introduces float dust (20565.620600000002);
            # 10 decimals is far beyond report precision and kills the noise
            return round(float(raw) / 100.0, 10)
        if value_type in ("Int8s", "Int16s", "Int32s", "Int32u"):
            return int(raw)
        if value_type == "Date":
            return _jdn_to_date(int(raw))
        if value_type == "DateTime":
            packed = int(raw)
            day = _jdn_to_date(packed & 0xFFFFFFFF)
            seconds = (packed >> 32) & 0xFFFFFFFF
            if seconds >= 86400:          # implausible time-of-day: date only
                return datetime.combine(day, time(0, 0, 0))
            return datetime.combine(day, time(seconds // 3600,
                                              seconds % 3600 // 60,
                                              seconds % 60))
        if value_type == "Time":
            seconds = int(raw) % 86400
            return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)
        if value_type == "Boolean":
            return raw.strip().lower() in ("true", "1")
    except (ValueError, OverflowError):
        return raw
    return raw


def load_saved_rows(rpt_path: Path) -> SavedRows | None:
    """Decode and convert a report's saved rowset. None whenever anything is
    missing - the caller converts without embedded data, as before."""
    exe = find_rpt_rs()
    if exe is None or not Path(rpt_path).is_file():
        return None
    try:
        proc = run_nice(
            [str(exe), "saved", str(rpt_path), "--limit", "all", "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_SAVED_TIMEOUT)
        payload = json.loads(proc.stdout) if proc.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return None
    if not payload or not payload.get("rows"):
        return None

    result = SavedRows(total_records=int(payload.get("recordCount", 0)))

    # Layout elements bind SHORT column names ({ORDERS.ORDER_AMOUNT} ->
    # ORDER_AMOUNT). A short-name collision across tables keeps the first
    # column and drops the later one, with a note - a wrong-but-plausible
    # column is worse than an absent one.
    keep: list[int] = []
    seen: set[str] = set()
    for i, col in enumerate(payload.get("columns", [])):
        name = str(col.get("name", ""))
        short = name.rsplit(".", 1)[-1]
        if short in seen:
            result.notes.append(
                f"saved column {name!r} shares the short name {short!r} with "
                "another table - dropped from the embedded dataset")
            continue
        seen.add(short)
        keep.append(i)
        result.columns.append((short, str(col.get("valueType", "String"))))

    rows = payload["rows"]
    if len(rows) > MAX_EMBED_ROWS:
        result.notes.append(
            f"report carries {len(rows):,} saved rows - the first "
            f"{MAX_EMBED_ROWS:,} are embedded (a demo dataset, not a "
            "warehouse); switch to the source-sql query for the full set")
        rows = rows[:MAX_EMBED_ROWS]

    for raw_row in rows:
        result.rows.append([
            _convert_cell(raw_row[i] if i < len(raw_row) else None,
                          result.columns[k][1])
            for k, i in enumerate(keep)])
    return result


# PRD inline-table column/cell java types per Crystal value type. The column
# declaration and the per-cell attribute differ (a Number column declares
# java.lang.Number, its cells are BigDecimal) - shapes copied from PRD's own
# sample bundles.
_JAVA_TYPES = {
    "Number": ("java.lang.Number", "java.math.BigDecimal"),
    "Currency": ("java.lang.Number", "java.math.BigDecimal"),
    "Int8s": ("java.lang.Integer", "java.lang.Integer"),
    "Int16s": ("java.lang.Integer", "java.lang.Integer"),
    "Int32s": ("java.lang.Integer", "java.lang.Integer"),
    "Int32u": ("java.lang.Integer", "java.lang.Integer"),
    "Boolean": ("java.lang.Boolean", "java.lang.Boolean"),
    "Date": ("java.sql.Date", "java.sql.Date"),
    "DateTime": ("java.sql.Timestamp", "java.sql.Timestamp"),
}


def _cell_text(value) -> str:
    # Every date-family bean converter in the engine (SQLDate/SQLTime/Date/
    # Timestamp) parses exactly yyyy-MM-dd'T'HH:mm:ss.SSSZ - a bare ISO date
    # is "Not a parsable SQL-date" and the whole bundle fails to load.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.10g}"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%dT00:00:00.000+0000")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return str(value)


def _effective_types(saved: SavedRows):
    """(column declaration, cell type) per column, trusting the RECOVERED
    VALUES over the declared Crystal type.

    Some .rpt files report every saved column as Int32s while the batches
    plainly hold text. Declaring java.lang.Integer for a column of country
    names makes the engine fail on the first cell and the whole bundle
    refuses to load - the report is lost to a metadata lie. The values are
    the ground truth here, so a column holding any string is a String
    column."""
    out = []
    for i, (_short, vt) in enumerate(saved.columns):
        decl, cell = _JAVA_TYPES.get(vt, ("java.lang.String", None))
        values = [row[i] for row in saved.rows
                  if i < len(row) and row[i] is not None]
        if values and any(isinstance(v, str) for v in values):
            decl, cell = "java.lang.String", None
        out.append((decl, cell))
    return out


def build_inline_ds_xml(saved: SavedRows, query_name: str = "default") -> str:
    """The recovered rowset as a PRD inline-table datasource document
    (datasources/inline-ds.xml) whose table answers `query_name`."""
    from xml.sax.saxutils import escape, quoteattr

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<data:inline-datasource xmlns:data='
        '"http://reporting.pentaho.org/namespaces/datasources/inline/1.0">',
        f"<data:inline-table name={quoteattr(query_name)}><data:definition>",
    ]
    types = _effective_types(saved)
    for (short, _vt), (decl, _cell) in zip(saved.columns, types):
        parts.append(f"<data:column name={quoteattr(short)} type={quoteattr(decl)}/>")
    parts.append("</data:definition>")
    for row in saved.rows:
        parts.append("<data:row>")
        for (_short, _vt), (_decl, cell_type), value in zip(
                saved.columns, types, row):
            if value is None:
                parts.append('<data:data null="true"/>')
                continue
            attr = f" type={quoteattr(cell_type)}" if cell_type else ""
            parts.append(f"<data:data{attr}>{escape(_cell_text(value))}</data:data>")
        parts.append("</data:row>")
    parts.append("</data:inline-table></data:inline-datasource>")
    return "".join(parts)
