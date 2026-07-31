# corpus2 Provenance

Second harvested corpus of Pentaho BI-platform (1.x-4.x era) report action sequences
(.xaction with JFreeReportComponent) and their paired JFreeReport definitions.
Harvested 2026-07-31 from public GitHub repositories. Solution-folder structure is
preserved so sibling resources (report definitions, .properties bundles, images)
resolve by relative name, exactly as on a BI server.

The first corpus (samples/xactions/corpus/, from github.com/it4biz/IT4bizBIServer)
is NOT duplicated here: every .xaction basename in corpus2 was checked against
corpus1 and name-collisions were excluded (e.g. MDX_report, JFree_XQuery_report,
BurstSales, the steel-wheels-reports set).

## breadboard/  (58 report xactions)

- Repo: https://github.com/breadboard-bi/breadboard
- Commit: 85ee75e72fa9b175450f6ce5782b7cefb3191c95 (master, fetched via codeload tarball)
- License: Apache-2.0 (repo LICENSE)
- Source path prefix: `presentation layer/pentaho/original/solution/` -> local paths are
  solution-relative (e.g. `breadboard/finance/general_ledger/reporting/...`).
- What: "Breadboard BI" packaged analytic applications (~2008-2011 era) - finance
  (billing, budget forecast, general ledger), supply chain (inventory, purchase
  orders, shipments, work orders), customer 360 (leads, online marketing, returns,
  sales order capture, web analytics incl. bursting/email partner reports and MDX),
  workforce (snapshot reports + WAQR .waqr.xaction adhoc reports).
- Report definitions: legacy-EXT dialect (`<report-definition
  xmlns="http://jfreereport.sourceforge.net/namespaces/reports/legacy/ext">`,
  engine-version 0.8.9-rc6/0.8.9.3). `.report` siblings are Pentaho Report Designer
  1.x source files; `.rptdesign` files (none here) n/a.
- Excluded: `deprecated/` and `old_ reporting/` duplicate subtrees, chart-only and
  dashboard-only folders except `finance/billing/dashboards/reports` (kept as a
  dashboard-feeding report example).
- CREDENTIAL NOTE: nine `.report` (Report Designer source) files embedded a real-looking
  MySQL credential (`userName="mdw" password="jasiu123"` at private IP 10.10.10.3).
  The password value has been REDACTED in the local copies ( password="[REDACTED]" ).
  Affected: web_server_sample.report, web_visit_bar.report, Billing_buckets_wPie.report,
  Billing_wPie.report, Ledgers_wTwoPrompts.report, inventory_trxn_supplier_list.report,
  inventory_trxn_trxn_type_list.report, inventory_trxn_warehouse_list.report,
  workforce_dept_snapshot_2_prompts.report. The runtime `.xml` definitions used by the
  xactions carry JNDI names only and were not modified.

## pentaho-platform-5.0-OLD/  (17 report xactions)

- Repo: https://github.com/pentaho/pentaho-platform
- Branch: 5.0-OLD (pre-5.0 codebase snapshot; commit 993c68d334d70239b3764ce7d92cb7bd30459751,
  fetched by anonymous shallow sparse clone - the pentaho org enforces SAML on API tokens,
  raw/anonymous access used instead)
- License: LGPL-2.1 era platform sources (per source headers, Pentaho Corporation
  2005-2011; the current master is BUSL - this branch predates that).
- Local layout:
  - `test-solution/test/reporting/` <- `extensions/test-src/solution/test/reporting/`
    (jfreereport-reports-test-1/2, -param/-param2/-param3, -file,
    jfreereport-subreport-basic-test, jfreereport-subreport-ipreparedcomponent-test,
    JFreeReportChartTypes/JFreeReport_Chart_ChartTypes + 8 chart element defs,
    DynamicSQLSample, quadrant-budget-* BIRT ridealongs, jasper-reports-test-1/2
    JasperReports ridealongs). Corpus1 name-dups removed: MDX_report.xaction,
    JFree_XQuery_report.xaction, JFree_SQLQuery_ComboChart.xaction,
    custom-parameter-page-example.xaction (their resource files retained).
  - `test-solution/test/email/` <- `extensions/test-src/solution/test/email/`
    (AttachmentTest, AttachmentsTest, UrlContentTest, AdvancedUrlContentTest =
    report-to-email chains; text_only_email* loops are EmailComponent-only ridealongs).
  - `test-solution/boot/` <- `extensions/test-src/solution/boot/` (report.xaction).
  - `pentaho-solutions/admin/` <- `assembly/package-res/biserver/pentaho-solutions/admin/`
    (PentahoNetwork.xaction, PentahoNetworkParameterized.xaction = XQuery-over-RSS
    reports; clean_repository/clear_mondrian_schema_cache/schedule-clean are
    non-report admin ridealongs; binaries skipped).
- Report definitions: simple dialect (`<report>` root) for the JFreeQuad*/subreport/
  ChartTypes definitions.
- Demo credentials only (odaPassword "password" in BIRT .rptdesign) - left as-is.

## lanit/  (51 report xactions)

- Repo: https://github.com/lanitadmin/lanit
- Commit: 4447c8641edeb316834e35d96d76a93c9d5bac02 (master, 2017-06-15; content authored
  ~2008-2012)
- License: none declared in repo (public repository, no LICENSE file). Harvested for
  internal migration-tool gap analysis only; do not redistribute.
- Source path prefix: `pentaho-solutions/` -> local paths solution-relative
  (`lanit/lodint/...`).
- What: real production estate from LANIT (Russian systems integrator) - regional
  government licensing / public-services document printing ("lodint" solution):
  `lodint/lod/orel/` (Orel region: licence forms, inspection acts, registries),
  `lodint/gossrvc/` (public-services receipts/applications), `lodint/archive/`
  (archive cards/receipts), `lodint/action/` (EJB-QL datasource test xactions).
  Russian-language titles and Cp1251-era content; custom platform components
  (org.pentaho.plugin.comsoft.DataSeamEJB / DataSeamEJBQL), SecureFilterComponent
  prompts, JavascriptRule parameter prep, nested conditional action blocks.
- Report definitions: legacy-EXT dialect `.xml` (engine-version 0.8.9.8) paired with
  Report Designer `.report` sources and parallel BIRT `_birt.rptdesign/.rptconfig`
  variants of the same forms.
- CREDENTIAL NOTE: BIRT `.rptdesign` files carry `odaPassword` = base64 `bWFzdGVya2V5`
  ("masterkey" - the canonical BIRT/Derby sample-database password) with jdbc URLs to
  private 192.168.x.x hosts. Treated as demo-grade default, left as-is; flagged here
  for awareness.

## Not harvested (checked and rejected)

- `bys-levi-lu/testgit2`, `gridgentoo/PentahoPlatform`, `datafor123/datafor-free`,
  `obonilla66/pentaho_10.1`, `tahopen/tahopen-platform`: forks/mirrors of
  pentaho-platform - same test solutions as above, no new material.
- `ambientelivre/iguana`: stock biserver-ce bundle; report xactions duplicate
  corpus1/it4biz and the admin/ content taken from pentaho-platform above.
- `LLuke/jfreereport`: JFreeReport engine sources; definitions exist but no paired
  .xaction action sequences.
- OpenI platform: no GitHub presence with .xaction content found.
