# Xaction corpus — old Pentaho BI-Platform action-sequence reports

Starter corpus for the `.xaction` → `.prpt` migration (task #67), pulled from
the steel-wheels-era BI-server 4.5 sample solutions
(github.com/it4biz/IT4bizBIServer, `biserver-ce/pentaho-solutions/` —
`bi-developers/reporting/` + `steel-wheels-reports/` + the steel-wheels
dashboard/google folders for the non-report classes).

**69 files: 34 .xaction + 35 report/chart definition .xml.** Each classic
report xaction ships with its paired OLD JFreeReport XML definition beside it
(`Income Statement.xaction` + `Income Statement.xml`) — the "old .report"
format, the direct ancestor of PRD's.

## Census (deterministic scan)

Component frequencies across the 34 xactions:

| n | component | maps to |
|---|-----------|---------|
| 52 | SQLLookupRule | .prpt SQL datasource |
| 24 | JFreeReportComponent | the report render — its definition becomes layout.xml |
| 17 | SecureFilterComponent | .prpt parameters (prompts; preceding SQLLookupRule = query-backed pick-list) |
| 10 | JavascriptRule | business logic — suggested-solutions territory |
| 8 | TemplateComponent | HTML wrapper around the render |
| 6 | UtilityComponent | variable munging, mostly folds away |
| 5 | MDXLookupRule | Mondrian/OLAP datasource |
| 4 | ChartComponent | chart image generation |
| 3 | EmailComponent | bursting/distribution — PDI job (.kjb) territory |
| 2 | XQueryLookupRule | XML datasource |

Xaction kinds: **23 report** (JFreeReportComponent), 3 chart/dashboard, 8 other.
Report-definition roots: 17 old JFreeReport simple `<report>`, 4 legacy-ext
`report-definition`, 1 `sub-report`, 6 `chart`, plus result-set/widget/schema.

## Complexity ladder in the corpus (the T&M model, measurable)

- **Low** — `SQLLookupRule -> JFreeReportComponent` and done:
  order_detail, customer_details, Income Statement, JFree_Quad.
- **Medium** — prompts + several lookups + JS glue:
  the Sales_by_* family, Inventory List, Top Ten (MDX + SQL).
- **High** — orchestration around the render:
  BurstSales (template + JS + utilities + report + EMAIL = bursting),
  invent_subscribe (TWO renders + two emails + templates), Variance
  (JS + template output).
