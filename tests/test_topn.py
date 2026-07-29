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
        assert "SUM(b.Sales_Amount) OVER (PARTITION BY b.Country)" in model.sql
        assert "DENSE_RANK() OVER (ORDER BY t._grp_total DESC)" in model.sql

    def test_the_tail_is_relabelled_others(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N))
        assert ("CASE WHEN r._grp_rank <= 5 THEN r.Country ELSE 'Others' "
                "END AS Country") in model.sql

    def test_others_sorts_last(self, tmp_path):
        model = load_report_model(_dump(tmp_path, TOP_N))
        order = model.sql.split("ORDER BY")[-1]
        assert "(r._grp_rank > 5)" in order   # kept groups first, Others last

    def test_a_plain_group_sort_is_not_wrapped(self, tmp_path):
        model = load_report_model(_dump(tmp_path, PLAIN_GROUP))
        assert "_grp_rank" not in model.sql and "PARTITION BY" not in model.sql


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
