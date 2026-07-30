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
        assert by_name["time_start"].default == "2005-01-01"

    def test_the_implicit_report_definition_resource_binds(self):
        # Income Statement's component names no action-resource; the platform
        # convention (a resource called report-definition*) applies
        m = build_report_model(SW / "Income Statement.xaction")
        assert m.sections, "layout should come from Income Statement.xml"

    def test_a_legacy_ext_definition_is_flagged_not_crashed(self):
        m = build_report_model(SW / "Inventory List.xaction")
        assert any("legacy-EXT" in i for i in m.issues)

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

    def test_javascript_suggests_sql_or_a_prd_function(self):
        m = build_report_model(SW / "Variance Report.xaction")
        assert any("JavaScript" in i and "computed column" in i for i in m.issues)

    def test_a_query_picklist_prompt_carries_its_query(self):
        # Sales_by_Customer feeds its prompts from SQL lookups
        m = build_report_model(SW / "Sales_by_Customer.xaction")
        assert any("query-backed list parameter" in i for i in m.issues)

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
