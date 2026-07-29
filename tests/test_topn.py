"""Crystal's Group Sort Expert / Top-N has no PRD group equivalent. Rather
than flag it as unsupported, we realize it in the report SQL: order the groups
by their ranking measure so the top groups lead (this step), then roll the
tail into an "Others" bucket (the next step).

RptToXml exports only the direction (TopNOrder/BottomNOrder) and the ranking
measure - not the N count or the "Others" options - so those are assumed and
the note says so.
"""

import textwrap

from pentaho_migration.reports import load_report_model
from pentaho_migration.reports.model import Group, ReportModel, TopN
from pentaho_migration.reports.rpt_saved import SavedRows, bucket_saved_rows_topn


def _dump(tmp_path, body):
    p = tmp_path / "r.xml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


# Top 5 countries by sales, the WorldSalesReport shape in miniature.
TOP_N = """\
<Report Name="TopFive" FileName="topfive.rpt">
  <Database><Tables>
    <Table Name="Sales" Alias="Sales"><Fields>
      <Field Name="Country" LongName="Sales.Country"
             Type="crFieldValueTypeStringField"/>
      <Field Name="Sales_Amount" LongName="Sales.Sales_Amount"
             Type="crFieldValueTypeNumberField"/>
    </Fields></Table>
  </Tables></Database>
  <DataDefinition>
    <RecordSelectionFormula/>
    <Groups>
      <Group Name="G0" ConditionField="{Sales.Country}"/>
    </Groups>
    <SortFields>
      <SortField Field="Sum ({Sales.Sales_Amount}, {Sales.Country})"
                 SortDirection="TopNOrder" SortType="GroupSortField"/>
    </SortFields>
  </DataDefinition>
  <ReportDefinition><Areas>
    <Area Kind="Detail"><Sections><Section Name="D" Height="200">
      <ReportObjects>
        <FieldObject Name="a" Kind="FieldObject" Left="0" Top="0"
            Width="500" Height="200" DataSource="{Sales.Country}"/>
      </ReportObjects>
    </Section></Sections></Area>
  </Areas></ReportDefinition>
</Report>"""

# Same, but an ordinary alphabetical group sort - not Top-N.
PLAIN_GROUP = TOP_N.replace(
    '<SortField Field="Sum ({Sales.Sales_Amount}, {Sales.Country})"\n'
    '                 SortDirection="TopNOrder" SortType="GroupSortField"/>',
    '<SortField Field="{Sales.Country}"'
    ' SortDirection="AscendingOrder" SortType="GroupSortField"/>')


class TestTopNIsParsed:
    def test_the_group_carries_a_topn_spec(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N))
        g = next(g for g in model.groups if g.column == "Country")
        assert g.topn is not None
        assert g.topn.op == "Sum"
        assert g.topn.measure == "Sales_Amount"
        assert g.topn.descending is True          # TopN = largest first

    def test_bottom_n_is_ascending(self, tmp_path):
        model = load_report_model(
            _dump(tmp_path, TOP_N.replace("TopNOrder", "BottomNOrder")))
        g = next(g for g in model.groups if g.column == "Country")
        assert g.topn is not None and g.topn.descending is False

    def test_n_is_assumed_because_the_export_omits_it(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N))
        g = next(g for g in model.groups if g.column == "Country")
        assert g.topn.n_assumed is True


class TestTopNBucketsIntoOthers:
    def test_groups_are_ranked_by_the_measure(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N))
        # the per-group total, then a dense rank of those totals, largest first
        assert "SUM(w.Sales_Amount) OVER (PARTITION BY w.Country)" in model.sql
        assert "DENSE_RANK() OVER (ORDER BY x._t DESC)" in model.sql

    def test_the_tail_is_relabelled_others(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N))
        assert ("CASE WHEN r._rk <= 5 THEN r.Country ELSE 'Others' "
                "END AS Country") in model.sql

    def test_others_sorts_last(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N))
        # kept groups keep their rank; Others gets a sentinel that sorts last
        assert "2147483647" in model.sql
        assert "f._ord_0" in model.sql.split("ORDER BY")[-1]

    def test_a_plain_group_sort_is_not_wrapped(self, tmp_path):
        model = load_report_model(_dump(tmp_path, PLAIN_GROUP))
        assert "_rk" not in model.sql and "PARTITION BY" not in model.sql


# Two Top-N groups nested: countries, then regions WITHIN each country.
NESTED = """\
<Report Name="Nested" FileName="n.rpt">
  <Database><Tables>
    <Table Name="Sales" Alias="Sales"><Fields>
      <Field Name="Country" LongName="Sales.Country"
             Type="crFieldValueTypeStringField"/>
      <Field Name="Region" LongName="Sales.Region"
             Type="crFieldValueTypeStringField"/>
      <Field Name="Sales_Amount" LongName="Sales.Sales_Amount"
             Type="crFieldValueTypeNumberField"/>
    </Fields></Table>
  </Tables></Database>
  <DataDefinition>
    <RecordSelectionFormula/>
    <Groups>
      <Group Name="G0" ConditionField="{Sales.Country}"/>
      <Group Name="G1" ConditionField="{Sales.Region}"/>
    </Groups>
    <SortFields>
      <SortField Field="Sum ({Sales.Sales_Amount}, {Sales.Country})"
                 SortDirection="TopNOrder" SortType="GroupSortField"/>
      <SortField Field="Sum ({Sales.Sales_Amount}, {Sales.Region})"
                 SortDirection="TopNOrder" SortType="GroupSortField"/>
    </SortFields>
  </DataDefinition>
  <ReportDefinition><Areas>
    <Area Kind="Detail"><Sections><Section Name="D" Height="20">
      <ReportObjects>
        <FieldObject Name="a" Kind="FieldObject" Left="0" Top="0"
            Width="500" Height="20" DataSource="{Sales.Region}"/>
      </ReportObjects>
    </Section></Sections></Area>
  </Areas></ReportDefinition>
</Report>"""


class TestNestedTopNRanksPerParent:
    def test_the_inner_group_ranks_within_its_parent(self, tmp_path):
        model = load_report_model(_dump(tmp_path, NESTED))
        # Region is ranked partitioned by the (relabelled) parent Country
        assert ("DENSE_RANK() OVER (PARTITION BY x.Country ORDER BY x._t DESC)"
                in model.sql)
        # and its total is the per (Country, Region) total
        assert "SUM(w.Sales_Amount) OVER (PARTITION BY w.Country, w.Region)" in model.sql

    def test_both_groups_are_bucketed(self, tmp_path):
        model = load_report_model(_dump(tmp_path, NESTED))
        assert "ELSE 'Others' END AS Country" in model.sql
        assert "ELSE 'Others' END AS Region" in model.sql

    def test_the_note_scopes_the_nested_group_to_its_parent(self, tmp_path):
        model = load_report_model(_dump(tmp_path, NESTED))
        assert any("on 'Region' within 'Country'" in i for i in model.issues)


# A Top-5 pie: its category is the Top-N group, so it must follow the same
# bucketing as the table.
TOP_N_CHART = """\
<Report Name="TopFiveChart" FileName="tfc.rpt">
  <Database><Tables>
    <Table Name="Sales" Alias="Sales"><Fields>
      <Field Name="Country" LongName="Sales.Country"
             Type="crFieldValueTypeStringField"/>
      <Field Name="Sales_Amount" LongName="Sales.Sales_Amount"
             Type="crFieldValueTypeNumberField"/>
    </Fields></Table>
  </Tables></Database>
  <DataDefinition>
    <RecordSelectionFormula/>
    <Groups><Group Name="G0" ConditionField="{Sales.Country}"/></Groups>
    <SortFields>
      <SortField Field="Sum ({Sales.Sales_Amount}, {Sales.Country})"
                 SortDirection="TopNOrder" SortType="GroupSortField"/>
    </SortFields>
  </DataDefinition>
  <ReportDefinition><Areas>
    <Area Kind="ReportHeader"><Sections><Section Name="RH" Height="300">
      <ReportObjects>
        <ChartObject Name="G1" Kind="ChartObject" Left="0" Top="0"
                     Width="500" Height="300">
          <ChartDefinition StyleType="crChartStyleTypePie"
                           ChartType="crChartTypeGroup" Title="" Subtitle="">
            <ConditionFields>
              <Field FormulaName="{Sales.Country}" Name="Country"/>
            </ConditionFields>
            <DataFields>
              <Field FormulaName="Sum ({Sales.Sales_Amount}, {Sales.Country})"
                     Name="Sales_Amount"/>
            </DataFields>
          </ChartDefinition>
        </ChartObject>
      </ReportObjects>
    </Section></Sections></Area>
    <Area Kind="Detail"><Sections><Section Name="D" Height="20">
      <ReportObjects>
        <FieldObject Name="a" Kind="FieldObject" Left="0" Top="0"
            Width="500" Height="20" DataSource="{Sales.Country}"/>
      </ReportObjects>
    </Section></Sections></Area>
  </Areas></ReportDefinition>
</Report>"""


class TestTopNReachesTheChart:
    def _chart(self, model):
        return next(el for s in model.sections for el in s.elements
                    if el.kind == "chart")

    def test_the_pie_category_is_the_bucketed_column(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N_CHART))
        chart = self._chart(model)
        # the pie's category column is the very column the SQL relabels, so the
        # pie shows the same top-N + Others the table does
        assert chart.chart_category == "Country"
        assert ("CASE WHEN r._rk <= 5 THEN r.Country ELSE 'Others' "
                "END AS Country") in model.sql

    def test_the_chart_is_annotated_for_review(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N_CHART))
        notes = " ".join(self._chart(model).notes or [])
        assert "Top-N chart" in notes and "Others" in notes


class TestBucketEmbeddedSample:
    """The offline .prpt's embedded saved rows get the same Top-N + Others
    rollup the SQL path applies, so it opens showing the top groups + Others
    with no database."""

    def _saved(self, cols, rows):
        return SavedRows(columns=cols, rows=[list(r) for r in rows])

    def test_the_tail_rows_become_one_others_group_last(self):
        model = ReportModel()
        model.groups = [Group(condition_field="{S.Country}", column="Country",
                              topn=TopN(op="Sum", measure="Sales", n=2))]
        saved = self._saved(
            [("Country", "String"), ("Sales", "Number")],
            [["USA", 100.0], ["USA", 50.0], ["France", 80.0],
             ["Germany", 30.0], ["Italy", 20.0]])
        bucket_saved_rows_topn(model, saved)
        countries = [r[0] for r in saved.rows]
        assert set(countries) == {"USA", "France", "Others"}  # top 2 by sum
        assert countries[-1] == "Others"
        assert countries.count("Others") == 2                 # Germany + Italy

    def test_nested_ranks_within_the_parent(self):
        model = ReportModel()
        model.groups = [
            Group(condition_field="{S.Country}", column="Country",
                  topn=TopN(op="Sum", measure="Sales", n=1)),
            Group(condition_field="{S.Region}", column="Region",
                  topn=TopN(op="Sum", measure="Sales", n=1))]
        saved = self._saved(
            [("Country", "String"), ("Region", "String"), ("Sales", "Number")],
            [["USA", "CA", 100.0], ["USA", "TX", 10.0], ["France", "IDF", 5.0]])
        bucket_saved_rows_topn(model, saved)
        pairs = {(r[0], r[1]) for r in saved.rows}
        assert ("USA", "CA") in pairs        # top country, top region kept
        assert ("USA", "Others") in pairs    # TX rolled up within USA
        assert ("Others", "IDF") in pairs    # France -> Others country

    def test_no_topn_leaves_the_rows_untouched(self):
        model = ReportModel()
        model.groups = [Group(condition_field="{S.Country}", column="Country")]
        saved = self._saved([("Country", "String"), ("Sales", "Number")],
                            [["USA", 100.0], ["France", 80.0]])
        bucket_saved_rows_topn(model, saved)
        assert [r[0] for r in saved.rows] == ["USA", "France"]


class TestTopNSuggestsAPrdSolution:
    def test_the_note_states_the_solution_not_an_error(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N))
        topn_notes = [i for i in model.issues if "Top-N" in i or "Group Sort" in i]
        assert topn_notes, "expected a Top-N conversion note"
        note = " ".join(topn_notes)
        # states what was DONE (kept top N, rolled the rest into Others) and the
        # one thing the export can't give - N - to confirm; not a bare error
        assert "Others" in note and "keeps the top" in note
        assert "confirm" in note.lower()
        assert "not carried" not in note
