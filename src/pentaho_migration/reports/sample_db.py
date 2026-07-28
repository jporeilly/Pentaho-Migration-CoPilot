"""Rebuild a database from the data saved inside the reports.

The problem this solves is not the demo's. During a PoC the customer hands
over a folder of `.rpt` files and no database - the DBA is on holiday, the
schema is confidential, the server is behind a VPN nobody has arranged
yet. The conversion still runs, because the pipeline recovers the rows
Crystal saved inside each report, but those rows are embedded in one
bundle each and prove nothing about the SQL. The consultant cannot show
that the generated query actually returns anything.

Two halves of the answer are already in the files:

SCHEMA comes from the dumps. Every `.rpt` declares its tables, columns,
Crystal value types and lengths - including columns no report reads.
That is a real schema, not an inference, so the tables can be created in
full and the generated SELECT will bind against them.

DATA comes from the saved rows. Those are RESULT SETS, though: joined,
filtered, and only the columns the report used. So a column outside every
report's SELECT list has no values to recover, and a row filtered out by
every report's record selection was never saved. Both are stated in the
manifest rather than papered over - the point of this is to be able to
run the real query, and a consultant who thinks the table is complete
will be wrong in front of the customer.

Splitting the result sets back into base tables works because Crystal
keeps the qualified name: a saved column called `CUSTOMER_NAME` is
declared as `CUSTOMER.CUSTOMER_NAME` in the dump. A short name owned by
more than one table is a join key, and is written to each - which is what
makes the joins in the generated SQL resolve.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from xml.etree import ElementTree as ET

# Crystal value type -> column type per dialect. Numbers are DECIMAL rather
# than DOUBLE because these are money columns and a report that footed to
# $20,820.61 in Crystal must foot to the same value here.
_TYPES = {
    "mysql": {
        "StringField": "VARCHAR({n})", "MemoField": "TEXT",
        "NumberField": "DECIMAL(18,4)", "CurrencyField": "DECIMAL(18,4)",
        "Int8sField": "INT", "Int16sField": "INT", "Int32sField": "INT",
        "Int64sField": "BIGINT", "IntegerField": "INT",
        "DateField": "DATE", "DateTimeField": "DATETIME", "TimeField": "TIME",
        "BooleanField": "TINYINT(1)", "BlobField": "LONGBLOB",
    },
}
_DEFAULT_TYPE = {"mysql": "VARCHAR(255)"}
# Crystal reports a string field's length in bytes of UTF-16 plus a header,
# so it runs to about twice the characters. Halving it back keeps VARCHAR
# widths believable without ever narrowing a column below its data.
_STRING_DIVISOR = 2
_MAX_VARCHAR = 1000


@dataclass
class Column:
    name: str
    value_type: str = "StringField"
    length: int = 0
    populated: bool = False   # did any saved result set carry this column?


@dataclass
class Table:
    name: str
    columns: dict = field(default_factory=dict)     # name -> Column
    rows: list = field(default_factory=list)        # [dict]
    sources: set = field(default_factory=set)       # reports it came from


def _text(el, attr: str) -> str:
    return (el.get(attr) or "").strip()


def collect_schema(dumps: list) -> dict:
    """table name -> Table, from every dump's declared field metadata.

    Keyed on the qualified name's prefix, not on `Table/@Name`, because an
    aliased table reports its alias there while the fields keep the real
    one - and the generated SQL is written against the real one."""
    tables: dict = {}
    for dump in dumps:
        try:
            tree = ET.parse(dump)
        except ET.ParseError:
            continue
        for tbl in tree.iter("Table"):
            for f in tbl.iter("Field"):
                long_name = _text(f, "LongName")
                short = _text(f, "Name")
                if "." not in long_name or not short:
                    continue
                owner = long_name.rsplit(".", 1)[0]
                # a schema-qualified name keeps only its last part: the
                # database being rebuilt has one schema
                owner = owner.rsplit(".", 1)[-1]
                table = tables.setdefault(owner, Table(owner))
                table.sources.add(dump.stem)
                col = table.columns.get(short)
                if col is None:
                    col = table.columns[short] = Column(short)
                raw = _text(f, "Type") or _text(f, "ValueType")
                for prefix in ("crFieldValueType", "crFieldValue", "crValueType"):
                    if raw.startswith(prefix):
                        raw = raw[len(prefix):]
                        break
                if raw:
                    col.value_type = raw
                try:
                    col.length = max(col.length, int(_text(f, "Length") or 0))
                except ValueError:
                    pass
    return tables


def _owners(tables: dict) -> dict:
    """short column name -> the tables that declare it. A name owned by
    several tables is a join key and belongs in all of them."""
    owners: dict = defaultdict(list)
    for name, table in tables.items():
        for col in table.columns:
            owners[col].append(name)
    return owners


def collect_rows(dumps: list, tables: dict, load_saved_rows) -> list:
    """Fill `tables` from each report's saved rows. Returns per-report notes.

    Rows are deduped per table on their full tuple: thirty invoices for one
    customer are thirty ORDERS rows and one CUSTOMER row, which is exactly
    the decomposition a result set needs to survive."""
    owners = _owners(tables)
    seen: dict = defaultdict(set)
    notes = []
    for dump in dumps:
        rpt = dump.with_suffix(".rpt")
        if not rpt.is_file():
            continue
        try:
            saved = load_saved_rows(rpt)
        except Exception as exc:                      # a corrupt .rpt is data
            notes.append(f"{dump.stem}: saved data unreadable ({exc})")
            continue
        if not saved or not saved.rows:
            continue
        names = [c for c, _t in saved.columns]
        placed = 0
        for row in saved.rows:
            record = dict(zip(names, row))
            for table_name in {t for n in names for t in owners.get(n, ())}:
                table = tables[table_name]
                cells = {n: v for n, v in record.items() if n in table.columns}
                if not cells or all(v is None for v in cells.values()):
                    continue
                key = tuple(sorted((k, _hashable(v)) for k, v in cells.items()))
                if key in seen[table_name]:
                    continue
                seen[table_name].add(key)
                table.rows.append(cells)
                placed += 1
        for n in names:
            for table_name in owners.get(n, ()):
                tables[table_name].columns[n].populated = True
        unknown = [n for n in names if n not in owners]
        if unknown:
            notes.append(f"{dump.stem}: {len(unknown)} saved column(s) match "
                         f"no declared table and were skipped "
                         f"({', '.join(sorted(unknown)[:5])})")
        notes.append(f"{dump.stem}: {len(saved.rows)} saved row(s) -> "
                     f"{placed} table row(s)")
    return notes


def _hashable(value):
    return value.isoformat() if isinstance(value, (date, datetime, time)) else value


def _quote_ident(name: str, dialect: str) -> str:
    if dialect == "mysql":
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.replace('"', '""') + '"'


def _column_type(col: Column, dialect: str) -> str:
    spec = _TYPES[dialect].get(col.value_type)
    if spec is None:
        return _DEFAULT_TYPE[dialect]
    if "{n}" not in spec:
        return spec
    width = max(1, min(col.length // _STRING_DIVISOR or 255, _MAX_VARCHAR))
    return spec.format(n=width)


def _literal(value, dialect: str) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(value, date):
        return "'" + value.strftime("%Y-%m-%d") + "'"
    if isinstance(value, time):
        return "'" + value.strftime("%H:%M:%S") + "'"
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return "'" + text + "'"


def emit_sql(tables: dict, database: str, dialect: str = "mysql",
             batch: int = 200) -> str:
    """CREATE DATABASE + CREATE TABLE + INSERTs, ready to pipe into a client."""
    q = _quote_ident
    out = [f"-- Rebuilt from the data saved inside the Crystal reports.",
           f"-- Schema is complete (declared in the .rpt files); data covers",
           f"-- only what the reports' own result sets contained.",
           f"CREATE DATABASE IF NOT EXISTS {q(database, dialect)} "
           "CHARACTER SET utf8mb4;" if dialect == "mysql" else "",
           f"USE {q(database, dialect)};" if dialect == "mysql" else ""]
    for name in sorted(tables):
        table = tables[name]
        if not table.columns:
            continue
        cols = [f"  {q(c.name, dialect)} {_column_type(c, dialect)}"
                for c in table.columns.values()]
        out.append("")
        out.append(f"DROP TABLE IF EXISTS {q(name, dialect)};")
        out.append(f"CREATE TABLE {q(name, dialect)} (\n"
                   + ",\n".join(cols) + "\n);")
        if not table.rows:
            out.append(f"-- no rows recovered for {name}")
            continue
        # every INSERT names the same full column list, so a row missing a
        # column writes NULL there rather than shifting the others along
        names = list(table.columns)
        collist = ", ".join(q(n, dialect) for n in names)
        for start in range(0, len(table.rows), batch):
            chunk = table.rows[start:start + batch]
            values = ",\n".join(
                "  (" + ", ".join(_literal(r.get(n), dialect) for n in names) + ")"
                for r in chunk)
            out.append(f"INSERT INTO {q(name, dialect)} ({collist}) VALUES\n"
                       + values + ";")
    return "\n".join(line for line in out if line != "") + "\n"


def manifest(tables: dict, notes: list) -> str:
    """What was rebuilt and - the part that matters - what was not.

    A consultant who believes these tables are complete will be wrong in
    front of the customer, so the gaps are the headline, not a footnote."""
    lines = ["# Sample database rebuilt from saved report data", "",
             "Schema is complete: every table and column below is declared in",
             "the `.rpt` files themselves. The DATA is not complete, and cannot",
             "be - Crystal saves a report's result set, so a column no report",
             "selected has no values and a row every report filtered out was",
             "never saved. Columns without data are created and left NULL.", "",
             "| Table | Columns | With data | Rows | From |",
             "| --- | ---: | ---: | ---: | --- |"]
    for name in sorted(tables):
        t = tables[name]
        filled = sum(1 for c in t.columns.values() if c.populated)
        lines.append(f"| `{name}` | {len(t.columns)} | {filled} | "
                     f"{len(t.rows)} | {', '.join(sorted(t.sources)[:3])} |")
    # The same logical table often appears twice because the corpus was
    # harvested from several Crystal front ends: the Derby build of Xtreme
    # calls it CUSTOMER.CUSTOMER_NAME, the Access build Customer."Customer
    # Name". Both are kept - each report binds to the one it names - but a
    # consultant has to know, and on a case-insensitive server they collide.
    clashes = defaultdict(list)
    for name in tables:
        clashes[name.lower()].append(name)
    clashes = {k: v for k, v in clashes.items() if len(v) > 1}
    if clashes:
        lines += ["", "## Tables that differ only by case", "",
                  "The corpus was harvested from more than one Crystal front",
                  "end, so the same logical table arrives under two spellings",
                  "with different column naming. Both are created, and each",
                  "report binds to the one it names. On a case-insensitive",
                  "server (MySQL on Windows, `lower_case_table_names=1`) they",
                  "collide and one will be lost - run this on Linux or in the",
                  "container, where table names are case-sensitive.", ""]
        lines += [f"- {' / '.join(sorted(v))}" for v in clashes.values()]
    empty = [n for n in sorted(tables) if not tables[n].rows]
    if empty:
        lines += ["", "## Tables created with no rows", "",
                  "No report's saved data covered these. They exist so the",
                  "generated SQL binds; they will return nothing until the",
                  "customer's real datasource is connected.", ""]
        lines += [f"- `{n}`" for n in empty]
    if notes:
        lines += ["", "## Per report", ""] + [f"- {n}" for n in notes]
    return "\n".join(lines) + "\n"


def build(dump_dir: Path, database: str = "xtreme", dialect: str = "mysql",
          only: str = "") -> tuple:
    """(sql, manifest_markdown, tables). `only` filters dumps to those whose
    connection metadata mentions it - "xtreme" for Crystal's own sample DB."""
    from pentaho_migration.reports.rpt_saved import load_saved_rows

    dumps = _unique_dumps(dump_dir, only)
    tables = collect_schema(dumps)
    notes = collect_rows(dumps, tables, load_saved_rows)
    return emit_sql(tables, database, dialect), manifest(tables, notes), tables


def _unique_dumps(dump_dir: Path, only: str) -> list:
    """One dump per report name - the by-feature folders are copies of the
    corpus, and loading a report twice would double every recovered row
    before the dedupe ever saw it."""
    seen: dict = {}
    for dump in sorted(dump_dir.rglob("*.xml")):
        if dump.stem in seen:
            continue
        if only and not _mentions(dump, only):
            continue
        seen[dump.stem] = dump
    return list(seen.values())


def _mentions(dump: Path, needle: str) -> bool:
    try:
        tree = ET.parse(dump)
    except ET.ParseError:
        return False
    needle = needle.lower()
    for ci in tree.iter("ConnectionInfo"):
        blob = (_text(ci, "QE_DatabaseName") + " "
                + _text(ci, "QE_ServerDescription")).lower()
        if needle in blob:
            return True
    return False
