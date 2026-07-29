"""Which of a Crystal table's two names is the one to use.

A `<Table>` carries a Name and an Alias. The ALIAS is the report's own
name for it and the only one anything else uses: every Field LongName,
every FormulaForm and both ends of every TableLink are written against it.
Across the corpus 83 tables have an alias that differs from the name, and
not one of them qualifies its fields by the name.

Keying by Name broke exactly that. An XML datasource names its table
`dataroot/Customer_Query` while its links say `{Customer.Customer_ID}`, so
no link ever matched a table: the join was silently dropped, the generated
SELECT became a cartesian product, and the table it selected from was an
XPath that no database could resolve. One wrong identifier, three symptoms.
"""

import textwrap

from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.rpt_parser import generate_sql


def _model(tmp_path, body):
    p = tmp_path / "r.xml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return load_report_model(p)


def _report(cust_name, cust_alias, ord_name, ord_alias):
    """Two linked tables, fields qualified by ALIAS as Crystal writes them."""
    return f"""\
    <Report Name="R" FileName="r.rpt">
      <Database>
        <TableLinks><TableLink JoinType="Equal">
          <SourceFields><Field FormulaName="{{{cust_alias}.Customer_ID}}"
                               Name="Customer_ID"/></SourceFields>
          <DestinationFields><Field FormulaName="{{{ord_alias}.Customer_ID}}"
                               Name="Customer_ID"/></DestinationFields>
        </TableLink></TableLinks>
        <Tables>
          <Table Name="{cust_name}" Alias="{cust_alias}"><Fields>
            <Field Name="Customer_ID" LongName="{cust_alias}.Customer_ID"
                   Type="crFieldValueTypeInt32sField"/>
            <Field Name="Customer_Name" LongName="{cust_alias}.Customer_Name"
                   Type="crFieldValueTypeStringField"/>
          </Fields></Table>
          <Table Name="{ord_name}" Alias="{ord_alias}"><Fields>
            <Field Name="Customer_ID" LongName="{ord_alias}.Customer_ID"
                   Type="crFieldValueTypeInt32sField"/>
            <Field Name="Order_Amount" LongName="{ord_alias}.Order_Amount"
                   Type="crFieldValueTypeNumberField"/>
          </Fields></Table>
        </Tables>
      </Database>
      <DataDefinition><RecordSelectionFormula/></DataDefinition>
      <ReportDefinition><Areas>
        <Area Kind="Detail"><Sections><Section Name="D" Height="200">
          <ReportObjects>
            <FieldObject Name="n" Kind="FieldObject" Left="0" Top="0"
                Width="1000" Height="200" DataSource="{{{cust_alias}.Customer_Name}}"/>
            <FieldObject Name="a" Kind="FieldObject" Left="1100" Top="0"
                Width="1000" Height="200" DataSource="{{{ord_alias}.Order_Amount}}"/>
          </ReportObjects>
        </Section></Sections></Area>
      </Areas></ReportDefinition>
    </Report>"""


class TestAnXmlDatasourceIsNamedByItsAlias:
    """`dataroot/Customer_Query` is where the data physically sits - an
    XPath into an XML file. It is not a table any database can select
    from, and it is not what the report calls the table."""

    def _sql(self, tmp_path):
        return generate_sql(_model(tmp_path, _report(
            "dataroot/Customer_Query", "Customer",
            "dataroot/Orders_Query", "Orders")))

    def test_the_select_names_the_alias(self, tmp_path):
        sql = self._sql(tmp_path)
        assert "Customer.Customer_Name" in sql
        assert "dataroot" not in sql

    def test_the_declared_link_becomes_a_join(self, tmp_path):
        """The join was there all along; it could never match, because the
        link says Customer and the table was keyed dataroot/Customer_Query."""
        assert "JOIN Orders ON Customer.Customer_ID = Orders.Customer_ID" \
            in self._sql(tmp_path)

    def test_no_cartesian_product(self, tmp_path):
        sql = self._sql(tmp_path)
        assert "FROM Customer\nJOIN" in sql
        assert "FROM Customer, Orders" not in sql

    def test_no_quoting_is_needed_once_the_path_is_gone(self, tmp_path):
        """The `/` forced ANSI double quotes, which MySQL rejects without
        ANSI_QUOTES. A plain alias needs no quoting at all."""
        assert '"' not in self._sql(tmp_path)


class TestARealTableKeepsItsName:
    """A self-join style alias over a genuine table is the other case: the
    name IS selectable, so the query must still read against it."""

    def test_the_source_table_is_declared_with_its_alias(self, tmp_path):
        sql = generate_sql(_model(tmp_path, _report(
            "PV_Customer", "PV_Customer1", "PV_Orders", "PV_Orders1")))
        assert "FROM PV_Customer PV_Customer1" in sql
        assert "JOIN PV_Orders PV_Orders1 ON " in sql
        assert "PV_Customer1.Customer_Name" in sql

    def test_matching_name_and_alias_are_not_repeated(self, tmp_path):
        sql = generate_sql(_model(tmp_path, _report(
            "CUSTOMER", "CUSTOMER", "ORDERS", "ORDERS")))
        assert "FROM CUSTOMER\n" in sql
        assert "CUSTOMER CUSTOMER" not in sql


class TestEscapedIdentifiers:
    """`_x005F_` is the XML name-escape for an underscore. Left encoded, one
    report's `variance_x005F_xtab` and another's `variance_xtab` are two
    different tables, and a link between them cannot resolve."""

    def test_an_escaped_alias_is_decoded(self, tmp_path):
        model = _model(tmp_path, _report(
            "dataroot/variance_xtab", "variance_x005F_xtab",
            "dataroot/Orders_Query", "Orders"))
        assert "variance_xtab" in model.tables
        assert "variance_x005F_xtab" not in model.tables

    def test_a_link_to_an_escaped_name_still_joins(self, tmp_path):
        sql = generate_sql(_model(tmp_path, _report(
            "dataroot/variance_xtab", "variance_x005F_xtab",
            "dataroot/Orders_Query", "Orders")))
        assert "JOIN Orders ON variance_xtab.Customer_ID" in sql
