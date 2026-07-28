"""Rebuilding a queryable database from the data saved inside the reports.

The value of this is entirely in what it refuses to claim. The SCHEMA is
recoverable in full - the reports declare every table, column and type -
but the DATA is a result set: joined, filtered, and only the columns each
report selected. A consultant who reads these tables as a dump of the
customer's database will be wrong in front of the customer, so the gaps
have to survive into the manifest rather than be smoothed over.
"""

import textwrap
from pathlib import Path

from pentaho_migration.reports import sample_db


def _dump(tmp_path, name, body):
    p = tmp_path / f"{name}.xml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


CUSTOMER_AND_ORDERS = """\
    <Report Name="R" FileName="r.rpt">
      <Database><Tables>
        <Table Name="CUSTOMER" Alias="C"><Fields>
          <Field Name="CUSTOMER_ID" LongName="CUSTOMER.CUSTOMER_ID"
                 Type="crFieldValueTypeInt32sField" Length="4"/>
          <Field Name="CUSTOMER_NAME" LongName="CUSTOMER.CUSTOMER_NAME"
                 Type="crFieldValueTypeStringField" Length="82"/>
          <Field Name="LAST_YEARS_SALES" LongName="CUSTOMER.LAST_YEARS_SALES"
                 Type="crFieldValueTypeNumberField" Length="8"/>
        </Fields></Table>
        <Table Name="ORDERS" Alias="O"><Fields>
          <Field Name="CUSTOMER_ID" LongName="ORDERS.CUSTOMER_ID"
                 Type="crFieldValueTypeInt32sField" Length="4"/>
          <Field Name="ORDER_AMOUNT" LongName="ORDERS.ORDER_AMOUNT"
                 Type="crFieldValueTypeNumberField" Length="8"/>
          <Field Name="ORDER_DATE" LongName="ORDERS.ORDER_DATE"
                 Type="crFieldValueTypeDateField" Length="4"/>
        </Fields></Table>
      </Tables></Database>
      <DataDefinition><RecordSelectionFormula/></DataDefinition>
      <ReportDefinition><Areas/></ReportDefinition>
    </Report>"""


class _Saved:
    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = rows


def _loader(mapping):
    """Stand-in for load_saved_rows keyed on the .rpt's stem."""
    def load(rpt_path):
        return mapping.get(Path(rpt_path).stem)
    return load


class TestSchemaComesFromTheReports:
    def test_every_declared_table_and_column_is_created(self, tmp_path):
        tables = sample_db.collect_schema(
            [_dump(tmp_path, "r", CUSTOMER_AND_ORDERS)])
        assert set(tables) == {"CUSTOMER", "ORDERS"}
        assert set(tables["CUSTOMER"].columns) == {
            "CUSTOMER_ID", "CUSTOMER_NAME", "LAST_YEARS_SALES"}

    def test_the_qualified_name_wins_over_the_alias(self, tmp_path):
        """The table is aliased C and O in the report while its fields keep
        CUSTOMER and ORDERS - and the generated SQL is written against the
        real names, so the database has to use those."""
        tables = sample_db.collect_schema(
            [_dump(tmp_path, "r", CUSTOMER_AND_ORDERS)])
        assert "C" not in tables and "O" not in tables

    def test_crystal_types_become_column_types(self, tmp_path):
        tables = sample_db.collect_schema(
            [_dump(tmp_path, "r", CUSTOMER_AND_ORDERS)])
        sql = sample_db.emit_sql(tables, "x")
        assert "`CUSTOMER_ID` INT" in sql
        assert "`ORDER_DATE` DATE" in sql
        # money is DECIMAL, never a float: a report that footed to $20,820.61
        # in Crystal has to foot to the same value here
        assert "`ORDER_AMOUNT` DECIMAL(18,4)" in sql


class TestDataComesFromTheSavedRows:
    def _built(self, tmp_path, columns, rows):
        dump = _dump(tmp_path, "r", CUSTOMER_AND_ORDERS)
        (tmp_path / "r.rpt").write_bytes(b"stub")
        tables = sample_db.collect_schema([dump])
        notes = sample_db.collect_rows(
            [dump], tables, _loader({"r": _Saved(columns, rows)}))
        return tables, notes

    def test_a_result_set_is_split_back_into_its_base_tables(self, tmp_path):
        """One row of a joined result set is one CUSTOMER row and one ORDERS
        row - which is the whole reason the rebuild is possible."""
        tables, _ = self._built(
            tmp_path,
            [("CUSTOMER_NAME", "StringField"), ("ORDER_AMOUNT", "NumberField")],
            [["Crazy Wheels", 43.50]])
        assert tables["CUSTOMER"].rows == [{"CUSTOMER_NAME": "Crazy Wheels"}]
        assert tables["ORDERS"].rows == [{"ORDER_AMOUNT": 43.50}]

    def test_one_customer_with_many_orders_is_not_duplicated(self, tmp_path):
        """Thirty invoices for one customer are thirty ORDERS rows and ONE
        CUSTOMER row. Without the dedupe the rebuilt CUSTOMER table would
        carry a row per invoice and every join would fan out."""
        tables, _ = self._built(
            tmp_path,
            [("CUSTOMER_NAME", "StringField"), ("ORDER_AMOUNT", "NumberField")],
            [["Crazy Wheels", 10.0], ["Crazy Wheels", 20.0],
             ["Crazy Wheels", 30.0]])
        assert len(tables["CUSTOMER"].rows) == 1
        assert len(tables["ORDERS"].rows) == 3

    def test_a_join_key_is_written_to_every_table_that_declares_it(self, tmp_path):
        """CUSTOMER_ID belongs to both tables. Putting it in only one would
        leave the generated SQL's join unresolvable."""
        tables, _ = self._built(
            tmp_path, [("CUSTOMER_ID", "Int32sField")], [[7]])
        assert tables["CUSTOMER"].rows == [{"CUSTOMER_ID": 7}]
        assert tables["ORDERS"].rows == [{"CUSTOMER_ID": 7}]


class TestTheGapsSurvive:
    def _built(self, tmp_path):
        dump = _dump(tmp_path, "r", CUSTOMER_AND_ORDERS)
        (tmp_path / "r.rpt").write_bytes(b"stub")
        tables = sample_db.collect_schema([dump])
        notes = sample_db.collect_rows(
            [dump], tables,
            _loader({"r": _Saved([("CUSTOMER_NAME", "StringField")],
                                 [["Crazy Wheels"]])}))
        return tables, notes

    def test_a_column_no_report_selected_is_created_and_left_null(self, tmp_path):
        tables, _ = self._built(tmp_path)
        sql = sample_db.emit_sql(tables, "x")
        assert "`LAST_YEARS_SALES`" in sql          # created...
        assert not tables["CUSTOMER"].columns["LAST_YEARS_SALES"].populated
        # ...and the INSERT names every column, so the missing one is NULL
        # rather than shifting the values that follow it along
        assert "INSERT INTO `CUSTOMER` (`CUSTOMER_ID`, `CUSTOMER_NAME`, " \
               "`LAST_YEARS_SALES`) VALUES" in sql
        assert "(NULL, 'Crazy Wheels', NULL)" in sql

    def test_a_table_no_report_covered_is_reported_as_empty(self, tmp_path):
        tables, notes = self._built(tmp_path)
        md = sample_db.manifest(tables, notes)
        assert "Tables created with no rows" in md
        assert "`ORDERS`" in md

    def test_the_manifest_counts_columns_that_carry_data(self, tmp_path):
        tables, notes = self._built(tmp_path)
        md = sample_db.manifest(tables, notes)
        # CUSTOMER: 3 columns declared, 1 with data
        assert "| `CUSTOMER` | 3 | 1 | 1 |" in md

    def test_tables_differing_only_by_case_are_called_out(self, tmp_path):
        """The corpus carries CUSTOMER (Derby build of Xtreme) and Customer
        (Access build) - genuinely different tables that a case-insensitive
        server would silently merge."""
        tables = sample_db.collect_schema([
            _dump(tmp_path, "r", CUSTOMER_AND_ORDERS),
            _dump(tmp_path, "s", CUSTOMER_AND_ORDERS.replace(
                'LongName="CUSTOMER.', 'LongName="Customer.'))])
        md = sample_db.manifest(tables, [])
        assert "differ only by case" in md
        assert "CUSTOMER / Customer" in md


class TestLiteralsSurviveTheRoundTrip:
    def test_a_quote_in_a_customer_name_does_not_break_the_insert(self):
        assert sample_db._literal("O'Brien Cycles", "mysql") \
            == "'O''Brien Cycles'"

    def test_a_backslash_is_escaped_for_mysql(self):
        """MySQL treats a backslash as an escape inside string literals, so
        a Windows path in an address field would eat the character after
        it - or end the statement."""
        assert sample_db._literal("A\\B", "mysql") == "'A\\\\B'"

    def test_dates_are_written_in_a_form_mysql_accepts(self):
        from datetime import date, datetime
        assert sample_db._literal(date(2002, 4, 3), "mysql") == "'2002-04-03'"
        assert sample_db._literal(datetime(2002, 4, 3, 9, 30), "mysql") \
            == "'2002-04-03 09:30:00'"

    def test_a_missing_value_is_null_not_an_empty_string(self):
        """An empty string and NULL foot differently in a SUM and read
        differently in a report - Crystal saved one of them."""
        assert sample_db._literal(None, "mysql") == "NULL"
