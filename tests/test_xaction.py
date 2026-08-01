"""Xaction (.xaction) -> .prpt: the old BI-platform report path (task #67).

Corpus-driven, like everything else: every assertion is against the real
steel-wheels-era sample solutions in samples/xactions/corpus. The three
pillars: the report pipeline converts (query, parameters, layout), everything
that cannot convert carries a SUGGESTED solution, and each xaction gets a
deterministic complexity grade - the T&M Level-of-Effort signal.
"""

import zipfile
from pathlib import Path

import pytest

from pentaho_migration.reports import write_prpt
from pentaho_migration.reports.jfreereport_parser import parse_jfreereport
from pentaho_migration.reports.xaction_parser import (
    build_report_model, classify_complexity, parse_xaction)

CORPUS = Path("samples/xactions/corpus")
SW = CORPUS / "steel-wheels-reports"


class TestParseXaction:
    def test_order_detail_anatomy(self):
        x = parse_xaction(SW / "order_detail.xaction")
        assert x.is_report
        assert [i.name for i in x.inputs] == [
            "output-type", "customernumber", "time_start", "time_stop"]
        assert x.resources["report-definition1"] == "order_detail.xml"
        assert [a.component for a in x.actions] == [
            "SQLLookupRule", "JFreeReportComponent"]

    def test_a_dashboard_chart_xaction_is_not_a_report(self):
        x = parse_xaction(CORPUS / "dashboards" / "productline_sales.xaction")
        assert not x.is_report

    def test_a_non_xaction_is_rejected(self, tmp_path):
        bad = tmp_path / "x.xaction"
        bad.write_text("<report/>", encoding="utf-8")
        with pytest.raises(ValueError):
            parse_xaction(bad)


class TestParseJFreeReport:
    def test_order_detail_layout(self):
        m = parse_jfreereport(SW / "order_detail.xml")
        assert m.page.paper == "LETTER" and m.page.margin_left == 36.0
        assert [g.column for g in m.groups] == ["CUSTOMERNAME", "ORDERNUMBER"]
        kinds = {s.area_kind for s in m.sections}
        assert {"ReportHeader", "PageHeader", "Detail",
                "PageFooter", "GroupHeader"} <= kinds

    def test_percent_widths_resolve_against_the_printable_page(self):
        m = parse_jfreereport(SW / "order_detail.xml")
        detail = next(s for s in m.sections if s.area_kind == "Detail")
        productname = next(e for e in detail.elements
                           if e.column == "PRODUCTNAME")
        # width="40%" of LETTER printable width (612 - 36 - 36 = 540)
        assert productname.width == pytest.approx(216.0)

    def test_message_templates_carry_over_verbatim(self):
        # PRD inherited JFreeReport's $() message syntax unchanged
        m = parse_jfreereport(SW / "order_detail.xml")
        footer = next(s for s in m.sections if s.area_kind == "PageFooter")
        assert any("$(PageofPages)" in e.text_template for e in footer.elements)

    def test_number_formats_are_kept(self):
        m = parse_jfreereport(SW / "order_detail.xml")
        detail = next(s for s in m.sections if s.area_kind == "Detail")
        price = next(e for e in detail.elements if e.column == "PRICEEACH")
        assert price.format_string == "'$'###,###.00"

    def test_a_known_function_becomes_a_summary(self):
        m = parse_jfreereport(SW / "order_detail.xml")
        assert any(s.operation == "Count" for s in m.summaries)


class TestBuildReportModel:
    def test_the_query_and_jndi_convert(self):
        m = build_report_model(SW / "order_detail.xaction")
        assert m.jndi == "SampleData"
        assert "${customernumber}" in m.sql          # {PREPARE:x} -> ${x}
        assert "{PREPARE:" not in m.sql

    def test_inputs_with_defaults_become_optional_parameters(self):
        # an xaction <default-value/> (even empty) means blank is acceptable -
        # a mandatory PRD parameter would fail validation the platform passed
        m = build_report_model(SW / "order_detail.xaction")
        by_name = {p.name: p for p in m.parameters}
        assert set(by_name) == {"customernumber", "time_start", "time_stop"}
        assert all(p.optional for p in by_name.values())
        # date-only defaults are padded to midnight: HSQLDB 2.x only
        # implicitly converts the FULL timestamp format
        assert by_name["time_start"].default == "2005-01-01 00:00:00"

    def test_the_implicit_report_definition_resource_binds(self):
        # Income Statement's component names no action-resource; the platform
        # convention (a resource called report-definition*) applies
        m = build_report_model(SW / "Income Statement.xaction")
        assert m.sections, "layout should come from Income Statement.xml"

    def test_a_legacy_ext_definition_translates(self):
        # the EXT dialect used to be flagged honestly; it now parses for real
        m = build_report_model(SW / "Inventory List.xaction")
        assert not any("legacy-EXT" in i for i in m.issues)
        assert sum(len(s.elements) for s in m.sections) > 20

    def test_the_bundle_writes_with_the_parameterised_query(self, tmp_path):
        m = build_report_model(SW / "order_detail.xaction")
        out = tmp_path / "order_detail.prpt"
        write_prpt(m, out)
        z = zipfile.ZipFile(out)
        assert b"${customernumber}" in z.read("datasources/sql-ds.xml")
        assert len(z.read("layout.xml")) > 5000

    def test_a_non_report_xaction_says_what_it_is(self):
        m = build_report_model(CORPUS / "dashboards" / "productline_sales.xaction")
        assert any("no JFreeReportComponent" in i for i in m.issues)


class TestSuggestedSolutions:
    def test_bursting_suggests_a_pdi_job(self):
        m = build_report_model(CORPUS / "bi-developers-reporting" / "BurstSales.xaction")
        notes = " ".join(m.issues)
        assert "PDI job" in notes and "EMAIL" in notes.upper()

    def test_conditional_defaulting_javascript_fully_evaluates(self):
        # Sales_by_Customer's JS is the classic if(x=="default") shape -
        # the interpreter runs the same branch the platform ran
        m = build_report_model(SW / "Sales_by_Customer.xaction")
        note = next(i for i in m.issues
                    if "evaluated at conversion time" in i)
        assert "'All Customers'" in note or "All " in note
        assert not any("computed column" in i and "Script head" in i
                       for i in m.issues)

    def test_lookup_read_javascript_gets_the_pointed_suggestion(self):
        # lanit's scripts read a prior lookup's result set - outside the
        # deterministic subset, so the note names the PRD-native fix
        xa = Path("samples/xactions/corpus2/lanit/lodint/lod"
                  "/orel/application.xaction")
        if not xa.is_file():
            import pytest
            pytest.skip("corpus2 not present")
        m = build_report_model(xa)
        note = next((i for i in m.issues
                     if "prior lookup's result set" in i), "")
        assert "query-backed parameter default" in note
        assert "stopped at" in note

    def test_pure_arithmetic_javascript_is_evaluated_instead(self):
        # Variance's JS is one arithmetic line (PrevYear = YEAR - 1) - the
        # conversion computes it rather than telling the consultant to
        m = build_report_model(SW / "Variance Report.xaction")
        assert any("evaluated at conversion time" in i
                   and "PrevYear = '2003'" in i for i in m.issues)

    def test_a_query_picklist_prompt_becomes_a_real_lov_query(self):
        # Sales_by_Customer feeds its prompts from SQL lookups; the lookup
        # SQL now ships IN the bundle as the parameter's own query
        from pentaho_migration.reports.todo_kinds import classify_todo
        m = build_report_model(SW / "Sales_by_Customer.xaction")
        assert m.param_lov_sql, "pick-list lookups should carry their SQL"
        note = next(i for i in m.issues if "pick-list converted" in i)
        assert classify_todo(note) == "applied"

    def test_a_static_picklist_becomes_a_prd_list_parameter(self):
        # Sales_by_Supplier hardcodes its pick-lists as property-map-lists
        m = build_report_model(SW / "Sales_by_Supplier.xaction")
        start = next(p for p in m.parameters if p.name == "time_start")
        assert "2003-01-01" in start.default_values
        assert len(start.default_values) >= 3

    def test_mdx_suggests_the_mondrian_datasource(self):
        m = build_report_model(CORPUS / "bi-developers-reporting" / "MDX_report.xaction")
        assert any("Mondrian datasource" in i for i in m.issues)


class TestComplexityGrade:
    def _grade(self, path):
        return classify_complexity(parse_xaction(path))[0]

    def test_single_query_report_is_low(self):
        assert self._grade(SW / "order_detail.xaction") == "Low"

    def test_prompted_report_is_medium(self):
        assert self._grade(SW / "Sales_by_Supplier.xaction") == "Medium"

    def test_bursting_is_high(self):
        assert self._grade(CORPUS / "bi-developers-reporting" / "BurstSales.xaction") == "High"

    def test_the_grade_lands_in_the_review_output(self):
        m = build_report_model(SW / "order_detail.xaction")
        assert m.complexity == "Low"
        assert any(i.startswith("complexity: Low") for i in m.issues)


class TestUploadRouting:
    """The web chokepoint routes by CONTENT: an <action-sequence> root or a
    zipped solution folder reaches the xaction path through the same
    /reports/convert endpoint every other report family uses."""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from pentaho_migration.api.main import app
        return TestClient(app, client=("127.0.0.1", 12345))

    def test_a_raw_xaction_converts_via_the_reports_endpoint(self, client):
        data = (SW / "order_detail.xaction").read_bytes()
        r = client.post("/reports/convert",
                        files={"dump": ("order_detail.xaction", data, "text/xml")})
        assert r.status_code == 200
        d = r.json()
        assert d["filename"] == "order_detail.prpt"
        assert "complexity: Low" in d["report_markdown"]

    def test_a_zipped_solution_folder_carries_its_definition(self, client, tmp_path):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.write(SW / "order_detail.xaction", "order_detail.xaction")
            zf.write(SW / "order_detail.xml", "order_detail.xml")
        r = client.post("/reports/convert",
                        files={"dump": ("solution.zip", buf.getvalue(),
                                        "application/zip")})
        assert r.status_code == 200
        assert r.json()["filename"] == "order_detail.prpt"

    def test_a_zip_without_an_xaction_is_a_clear_422(self, client):
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "nothing here")
        r = client.post("/reports/convert",
                        files={"dump": ("x.zip", buf.getvalue(), "application/zip")})
        assert r.status_code == 422
        assert ".xaction" in r.json()["detail"]

    def test_the_picker_lists_the_demo_ladder(self, client):
        names = [m["name"] for m in client.get("/reports/xaction-samples").json()]
        assert names[0] == "order_detail" and "BurstSales" in names


class TestLiveDataFidelityRound2:
    """Second round of fixes from live SampleData rendering: dynamic SQL
    fragments, date-default padding, and templated field bindings."""

    def test_dynamic_sql_fragments_take_the_platforms_own_values(self):
        # the JS computes territory_qry_string = " " for the default
        # prompt choice; the fragment substitutes that exact value -
        # reproducing the platform's own text substitution, not a strip
        m = build_report_model(SW / "Sales_by_Customer.xaction")
        assert "{territory_qry_string}" not in m.sql
        assert any("dynamic SQL fragment" in i
                   and "substituted with the sequence's own value" in i
                   for i in m.issues)

    def test_date_defaults_are_padded_for_strict_hsqldb(self):
        m = build_report_model(SW / "Sales_by_Supplier.xaction")
        start = next(p for p in m.parameters if p.name == "time_start")
        assert start.default == "2005-01-01 00:00:00"

    def test_a_non_iso_original_default_is_flagged(self):
        m = build_report_model(SW / "order_detail.xaction")
        assert any("not ISO" in i for i in m.issues)

    def test_templated_bindings_resolve_by_type_uniqueness(self):
        # ${Group_by}/${Amount} in the shared Sales_by_* definition: exactly
        # one plain column and one aggregate alias in the query settle them
        m = build_report_model(SW / "Sales_by_Supplier.xaction")
        detail = next(s for s in m.sections if s.area_kind == "Detail")
        cols = {e.column for e in detail.elements if e.kind == "field"}
        assert "PRODUCTVENDOR" in cols and "SOLD_PRICE" in cols
        assert not any(c.startswith("${") for c in cols)
        assert any("templated field binding" in i for i in m.issues)

    def test_templated_summary_fields_resolve_too(self):
        m = build_report_model(SW / "Sales_by_Supplier.xaction")
        total = next(s2 for s2 in m.summaries
                     if s2.expression_name == "totalsales")
        assert "${" not in total.field_ref
        assert "SOLD_PRICE" in total.field_ref


class TestLiveDataFidelity:
    """The Income Statement fixes, found by rendering against the REAL
    SampleData database: layered visibility, expression-tag functions, and
    running-vs-total sum semantics."""

    def _model(self):
        return build_report_model(SW / "Income Statement.xaction")

    def test_hide_element_by_name_becomes_visibility_expressions(self):
        m = self._model()
        detail = next(s for s in m.sections if s.area_kind == "Detail")
        vis = [f for e in detail.elements
               for k, f in e.style_expressions if k == "visible"]
        assert vis, "layered bands should carry visibility expressions"
        assert any('[Category] = "Revenue"' in f for f in vis)
        assert any("layered-visibility layout translated" in i for i in m.issues)

    def test_expression_tag_functions_are_scanned(self):
        # <expression> declares the same classes as <function>; missing them
        # rendered $ <null> in every computed cell
        names = {s.expression_name for s in self._model().summaries}
        assert "Summary_AmountExpression" in names
        assert "CategoryAmountExpression" in names

    def test_item_sum_is_running_not_total(self):
        # JFree ItemSumFunction is a RUNNING sum; mapping it to a total put
        # the report's ending net income on the Gross Margin line
        summ = next(s for s in self._model().summaries
                    if s.expression_name == "Summary_AmountExpression")
        assert summ.running is True

    def test_group_functions_stay_totals(self):
        m = parse_jfreereport(SW / "order_detail.xml")
        count = next(s for s in m.summaries if s.operation == "Count")
        assert count.running is False


class TestLocalAssetEmbedding:
    """Server-hosted images (${serverBaseURL}/sw-style/...) embed when a local
    copy exists - the env override or the conventional install path - and the
    watermark band becomes an underlay carrying it."""

    def _definition(self, tmp_path, monkeypatch):
        webapps = tmp_path / "webapps"
        (webapps / "sw-style").mkdir(parents=True)
        (webapps / "sw-style" / "logo.jpg").write_bytes(b"\xff\xd8fakejpg")
        monkeypatch.setenv("PENTAHO_SERVER_WEBAPPS", str(webapps))
        xml = tmp_path / "r.xml"
        xml.write_text(
            '<report name="R" pageformat="LETTER">'
            '<watermark><imageref src="${serverBaseURL}/sw-style/logo.jpg"'
            ' x="0" y="0" width="100%" height="40"/></watermark>'
            '<items><string-field fieldname="A" x="0" y="0" width="100"'
            ' height="12"/></items></report>', encoding="utf-8")
        return xml

    def test_the_image_embeds_and_the_note_is_applied(self, tmp_path, monkeypatch):
        from pentaho_migration.reports.todo_kinds import classify_todo
        m = parse_jfreereport(self._definition(tmp_path, monkeypatch))
        wm = m.sections[0]
        assert wm.underlay is True
        img = next(e for e in wm.elements if e.kind == "image")
        assert img.image_bytes.startswith(b"\xff\xd8")
        assert img.image_mime == "image/jpeg"
        note = next(i for i in m.issues if "underlay" in i)
        assert classify_todo(note) == "applied"

    def test_an_unresolvable_image_gets_a_stamped_placeholder(self, tmp_path,
                                                              monkeypatch):
        # dead URL, nothing in the solution folder: a same-size placeholder
        # embeds so layout review proceeds, and the note names the ONE
        # estate-wide fix (drop the real file in; tier-2 picks it up)
        monkeypatch.setenv("PENTAHO_SERVER_WEBAPPS", str(tmp_path / "nope"))
        xml = tmp_path / "r.xml"
        xml.write_text(
            '<report name="R" pageformat="LETTER">'
            '<items><imageref src="${serverBaseURL}/missing/x.png" x="0" y="0"'
            ' width="50" height="20"/></items></report>', encoding="utf-8")
        m = parse_jfreereport(xml)
        img = next(e for s in m.sections for e in s.elements
                   if e.kind == "image")
        assert img.image_bytes[1:4] == b"PNG"
        note = next(n for n in img.notes if "placeholder is stamped" in n)
        assert "solution folder" in note
        from pentaho_migration.reports.todo_kinds import classify_todo
        assert classify_todo(note) == "info"

    def test_a_solution_folder_sibling_resolves_by_basename(self, tmp_path,
                                                            monkeypatch):
        monkeypatch.setenv("PENTAHO_SERVER_WEBAPPS", str(tmp_path / "nope"))
        xml = tmp_path / "r.xml"
        xml.write_text(
            '<report name="R" pageformat="LETTER">'
            '<items><imageref src="http://dead.example.com/img/logo.gif"'
            ' x="0" y="0" width="50" height="20"/></items></report>',
            encoding="utf-8")
        m = parse_jfreereport(
            xml, resource_loader=lambda n: b"GIF89a-bytes"
            if n == "logo.gif" else None)
        img = next(e for s in m.sections for e in s.elements
                   if e.kind == "image")
        assert img.image_bytes == b"GIF89a-bytes"
        assert img.image_mime == "image/gif"
        note = next(n for n in img.notes
                    if "embedded from the solution folder" in n)
        from pentaho_migration.reports.todo_kinds import classify_todo
        assert classify_todo(note) == "applied"

    def test_a_hostile_src_cannot_escape_the_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PENTAHO_SERVER_WEBAPPS", str(tmp_path))
        from pentaho_migration.reports.jfreereport_parser import (
            _resolve_image_asset)
        assert _resolve_image_asset("${serverBaseURL}/../../secret.txt") is None


class TestXactionNoteClassification:
    """The pipeline's own work must not read as manual backlog: the layered
    translation, padding, fragments and embeds classify applied/info, so the
    'Other manual work' panel holds only real hand-work."""

    def test_income_statement_has_no_manual_notes(self):
        from pentaho_migration.reports.todo_kinds import classify_todo
        m = build_report_model(SW / "Income Statement.xaction")
        manual = [n for n in m.issues if classify_todo(n) == "manual"]
        assert manual == []


class TestLegacyExtParser:
    """The OTHER old dialect (report-definition root) translates for real:
    styled object graphs, resource bundles, ported functions, conditional
    images, chart expressions. Steel Wheels ships four of them."""

    def test_inventory_layout_translates_with_live_styling(self):
        m = build_report_model(SW / "Inventory List.xaction")
        assert [g.column for g in m.groups] == ["PRODUCTLINE"]
        kinds = {e.kind for s in m.sections for e in s.elements}
        assert {"label", "field", "line", "image"} <= kinds
        stock = next(e for s in m.sections for e in s.elements
                     if e.column == "QUANTITYINSTOCK")
        # the traffic-light stock formatting rides as a style expression
        assert any(k == "background-color" and "QUANTITYINSTOCK" in f
                   for k, f in stock.style_expressions)
        logo = next(e for s in m.sections for e in s.elements
                    if e.kind == "image" and e.image_bytes)
        assert logo.image_mime == "image/jpeg"

    def test_missing_resource_bundle_is_an_honest_manual_note(self):
        from pentaho_migration.reports.todo_kinds import classify_todo
        m = build_report_model(SW / "Inventory List.xaction")
        note = next(i for i in m.issues if "shown literally" in i)
        assert "InventoryList.properties" in note
        assert classify_todo(note) == "manual"

    def test_resource_bundle_resolves_when_present(self):
        xml = (
            '<report-definition xmlns="http://x/legacy/ext" name="R">'
            "<report-config><simple-page-definition>"
            '<page orientation="portrait" pageformat="LETTER" topmargin="10"'
            ' leftmargin="10" bottommargin="10" rightmargin="10"/>'
            "</simple-page-definition></report-config>"
            "<report-description><report-header>"
            '<element name="t" type="text/plain">'
            '<style><basic-key name="x">0.0</basic-key>'
            '<basic-key name="y">0.0</basic-key>'
            '<basic-key name="min-width">100.0</basic-key>'
            '<basic-key name="min-height">14.0</basic-key></style>'
            '<template references="resource-label">'
            '<basic-object name="content">reportTitle</basic-object>'
            '<basic-object name="resourceIdentifier">Inv</basic-object>'
            "</template></element>"
            "</report-header></report-description></report-definition>")

        def loader(name):
            if name == "Inv.properties":
                return b"reportTitle=Detail Inventory Report\n"
            raise FileNotFoundError(name)

        from pentaho_migration.reports.todo_kinds import classify_todo
        m = parse_jfreereport(xml.encode(), resource_loader=loader)
        label = next(e for s in m.sections for e in s.elements)
        assert label.text == "Detail Inventory Report"
        note = next(i for i in m.issues if "resource-bundle text resolved" in i)
        assert classify_todo(note) == "applied"

    def test_invoice_groups_pagination_and_parent_relative_percents(self):
        m = build_report_model(SW / "invoice.xaction")
        assert [g.column for g in m.groups] == ["CUSTOMERNAME", "ORDERNUMBER"]
        # the watermark converts as the underlay, image embedded
        first = m.sections[0]
        assert first.underlay and any(e.image_bytes for e in first.elements)
        # each order's footer starts a new page, per the original's style key
        footers = [s for s in m.sections if s.area_kind == "GroupFooter"]
        assert any(s.new_page_after for s in footers)
        # -100.0 widths resolve against the CONTAINING band, not the page:
        # nothing may overflow the printable width (504pt LETTER + margins)
        assert all(e.x + e.width <= 505 for s in m.sections
                   for e in s.elements)
        total = next(s for s in m.summaries if s.expression_name == "invoicetotal")
        assert (total.operation, total.group_field, total.running) == \
            ("Sum", "ORDERNUMBER", True)

    def test_variance_resolves_everything(self):
        m = build_report_model(SW / "Variance Report.xaction")
        # JS arithmetic evaluated + fragments substituted -> runnable SQL
        assert "WHEN 2003" in m.sql and "WHEN 2004" in m.sql
        assert "{" not in m.sql.replace("${TERRITORY}", "")
        # comma-list default feeding IN (...) -> PRD multi-select
        terr = next(p for p in m.parameters if p.name == "TERRITORY")
        assert terr.multi_value
        assert terr.default_values == ["EMEA", "APAC", "NA", "Japan"]
        # the trend arrows: two stacked images, opposite visibility, embedded
        arrows = [e for s in m.sections for e in s.elements
                  if e.kind == "image" and e.style_expressions]
        assert len(arrows) == 2
        conds = sorted(f for e in arrows for _k, f in e.style_expressions)
        assert conds == ["=NOT([2004]>[2003])", "=[2004]>[2003]"]
        assert all(e.image_bytes for e in arrows)
        # the row-banding function ports unchanged and its band keeps a name
        assert any(cls.endswith("ElementVisibilitySwitchFunction")
                   for _n, cls, _p in m.port_functions)
        assert any(e.emit_name and e.name == "ITEMRECT"
                   for s in m.sections for e in s.elements)
        # one chart, three series
        chart = next(e for s in m.sections for e in s.elements
                     if e.kind == "chart")
        assert [c for c, _n in chart.chart_values] == ["2003", "2004",
                                                       "Variance"]

    def test_topten_mdx_gets_a_stub_query_and_charts(self):
        from pentaho_migration.reports.todo_kinds import classify_todo
        m = build_report_model(
            SW / "Top Ten Customer Product Line Analysis.xaction")
        assert m.sql_generated and "WHERE 1 = 0" in m.sql
        assert any("MDX (Mondrian)" in i for i in m.issues)
        stub_note = next(i for i in m.issues if "stub query stands in" in i)
        assert classify_todo(stub_note) == "applied"
        def charts_of(model):
            for sec in model.sections:
                for e in sec.elements:
                    if e.kind == "chart":
                        yield e
                    if e.kind == "subreport" and e.subreport is not None:
                        yield from charts_of(e.subreport)
        # the pie lives in the nested EXT sub-report (Product Line Mix)
        assert {c.chart_type for c in charts_of(m)} >= {"bar", "pie"}

    def test_pipeline_work_classifies_applied_not_manual(self):
        from pentaho_migration.reports.todo_kinds import split_todos
        m = build_report_model(SW / "Variance Report.xaction")
        kinds = split_todos(m.issues)
        for marker in ("substituted with the sequence's own value",
                       "evaluated at conversion time",
                       "ported unchanged"):
            assert any(marker in n for n in kinds["applied"]), marker
        # the one genuine manual item left: the header arrow whose
        # condition references a name nothing declares ('Total Selected')
        assert kinds["manual"], "the Total Selected arrow stays honest"
        assert all("Total Selected" in n for n in kinds["manual"])
