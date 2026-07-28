# Crystal corpus, classified by migration feature

150 reports scanned from `samples/crystal/corpus`. A report demonstrating several features appears in several folders - pick demo reports by the feature you want to show.

Each folder also holds the matching **`.rpt` binary** (150 of 150 reports), so a folder is a self-contained end-to-end demo:

```powershell
tools\RptViewer\RptViewer.exe <report>.rpt      # the ORIGINAL
pentaho-migrate report <report>.xml --validate   # the CONVERTED .prpt
```

**111 of those carry saved data** and render in the viewer with no database (marked * below). The rest show layout only until you pass --server/--db/--user/--password.

| Folder | Feature | Reports | Viewer-ready |
| --- | --- | --- | --- |
| `sub-reports/` | nested subreport definitions (converted to PRD sub-reports) | 22 | 17 |
| `charts/` | chart objects (converted to PRD legacy charts) | 14 | 13 |
| `cross-tabs/` | cross-tab objects (live PRD crosstab when the definition block is present, honest TODO otherwise) | 12 | 9 |
| `parameters/` | prompted parameters | 50 | 29 |
| `multi-value-params/` | multi-select prompts (IN-list folding) | 4 | 2 |
| `record-selection/` | record selection formulas (SQL WHERE folding) | 28 | 23 |
| `groups/` | grouped reports | 35 | 26 |
| `nested-groups/` | two or more nested groups | 21 | 16 |
| `summaries/` | summary fields (report functions) | 23 | 16 |
| `running-totals/` | running-total idiom rewritten as report functions | 6 | 4 |
| `select-case/` | Select Case formulas (nested IF conversion) | 1 | 0 |
| `conditional-formatting/` | conditional format/suppress formulas (style expressions) | 35 | 26 |
| `sort-directions/` | explicit record/group sort fields | 19 | 13 |
| `images/` | picture objects | 44 | 30 |
| `manual-formulas/` | formulas needing the LLM or a human | 30 | 24 |
| `linked-tables/` | no SQL command - the query is generated from the layout | 118 | 94 |
| `sql-commands/` | verbatim SQL command objects | 32 | 17 |

## Per-report features

- `28_Inventory_Raw.xml` * — groups, linked-tables, nested-groups, record-selection
- `28_JobSteps_Active_Jobs.xml` * — linked-tables, record-selection, sort-directions
- `28_Job_Steps_for_material_swap.xml` * — linked-tables, record-selection
- `28_Jobs_Ok_to_Close.xml` * — groups, linked-tables, record-selection
- `28_Loblaws_Item_Label.xml` * — linked-tables, record-selection
- `28_Mismatching_Print_Cyl_to_Print_Repeat.xml` * — linked-tables, record-selection, sort-directions
- `28_Packing_on_Jobs_sorted_by_cost.xml` * — linked-tables, record-selection, sort-directions
- `28__jobstep_2-6_to_2--4.xml` * — linked-tables, record-selection
- `97-Lista_Por_Carro_Alfabetica_Con_Grupos__Print_.xml` * — conditional-formatting, groups, images, manual-formulas, nested-groups, sort-directions, sql-commands
- `97-Lista_Por_Carro_Alfabetica__Print_.xml` * — conditional-formatting, groups, images, manual-formulas, sort-directions, sql-commands
- `98-Lista_Por_Carro__Print_.xml` * — conditional-formatting, groups, images, manual-formulas, nested-groups, sort-directions, sql-commands
- `AccountBalance.xml` — conditional-formatting, images, parameters, running-totals, sort-directions, sql-commands, summaries
- `AccountBalance_HANA.xml` — conditional-formatting, images, parameters, running-totals, sort-directions, sql-commands, summaries
- `Activity.xml` * — conditional-formatting, manual-formulas, parameters, sql-commands
- `Activity_HANA.xml` * — conditional-formatting, manual-formulas, parameters, sql-commands
- `AdventureWorks-MainMenu.xml` * — images, linked-tables, subreports
- `AdventureWorks-TotalSalesByDay.xml` * — charts, images, linked-tables, manual-formulas
- `AdventureWorks-TotalSalesByMonth.xml` * — charts, images, linked-tables
- `AdventureWorks-TotalSalesByYear.xml` * — charts, images, linked-tables
- `AlphaISOsByCountry.xml` * — conditional-formatting, linked-tables, manual-formulas
- `B1Budget_M.xml` * — conditional-formatting, crosstabs, parameters, record-selection, sql-commands
- `B1Budget_Q.xml` * — conditional-formatting, crosstabs, parameters, record-selection, sql-commands
- `BOM.xml` * — conditional-formatting, manual-formulas, parameters, sql-commands
- `BOM_HANA.xml` * — conditional-formatting, manual-formulas, parameters, sql-commands
- `CR__Dev_.xml` — images, parameters, sql-commands
- `CR__Orig_.xml` — images, parameters, sort-directions, sql-commands, summaries
- `CalibrationControlexp.xml` * — groups, images, manual-formulas, parameters, sql-commands, subreports
- `CarteraEdadesFix.xml` — conditional-formatting, groups, images, nested-groups, parameters, sort-directions, sql-commands, summaries
- `Cartera_Vendedores__Movil_.xml` — conditional-formatting, groups, images, nested-groups, parameters, sort-directions, sql-commands, summaries
- `CashFlowDetailReport.xml` * — linked-tables, manual-formulas, parameters, subreports
- `CashFlowReport.xml` * — linked-tables, manual-formulas, parameters, subreports
- `ColourPaletteSampler.xml` * — conditional-formatting, linked-tables
- `ComparativeIncomeStatement.xml` * — crosstabs, images, linked-tables, parameters, record-selection
- `Comportamiento_Entregas.xml` — charts, sql-commands
- `ConsolidatedIncomeStatement.xml` * — crosstabs, images, linked-tables, parameters, record-selection
- `Consolidated_Balance_Sheet.xml` * — crosstabs, images, linked-tables
- `CountriesAndCapitolCitiesOfTheWorld.xml` * — linked-tables, manual-formulas
- `CrossTab.xml` * — crosstabs, linked-tables
- `CrystalGraph.xml` * — charts, linked-tables
- `CrystalReport-code128.xml` — conditional-formatting, linked-tables, manual-formulas
- `CrystalReport.xml` * — linked-tables
- `CrystalReport1-10.xml` * — linked-tables
- `CrystalReport1-11.xml` * — linked-tables
- `CrystalReport1-12.xml` * — linked-tables
- `CrystalReport1-13.xml` * — images, linked-tables
- `CrystalReport1-14.xml` * — linked-tables, subreports
- `CrystalReport1-2.xml` * — groups, linked-tables, nested-groups, summaries
- `CrystalReport1-3.xml` * — charts, groups, linked-tables, nested-groups, summaries
- `CrystalReport1-4.xml` * — images, linked-tables
- `CrystalReport1-5.xml` * — linked-tables
- `CrystalReport1-6.xml` * — linked-tables
- `CrystalReport1-7.xml` * — linked-tables
- `CrystalReport1-8.xml` — linked-tables
- `CrystalReport1-9.xml` * — linked-tables
- `CrystalReport1.xml` * — linked-tables, subreports
- `CrystalReport1_2.xml` * — linked-tables
- `CrystalReport1_2_3.xml` * — linked-tables
- `CrystalReport1_2_3_4.xml` * — linked-tables
- `CrystalReport1_2_3_4_5.xml` * — groups, linked-tables, nested-groups
- `CrystalReport1_2_3_4_5_6.xml` * — linked-tables
- `CrystalReport2-2.xml` * — linked-tables
- `CrystalReport2-3.xml` * — linked-tables
- `CrystalReport2-4.xml` * — parameters, sql-commands
- `CrystalReport2-5.xml` — linked-tables
- `CrystalReport2-6.xml` * — conditional-formatting, images, linked-tables
- `CrystalReport2-7.xml` * — images, linked-tables
- `CrystalReport2.xml` * — linked-tables
- `CrystalReport3-2.xml` * — crosstabs, linked-tables
- `CrystalReport3-3.xml` — conditional-formatting, groups, images, linked-tables, nested-groups
- `CrystalReport3-4.xml` — groups, linked-tables
- `CrystalReport3-5.xml` * — images, linked-tables
- `CrystalReport3.xml` * — linked-tables, manual-formulas
- `CrystalReportGrouping.xml` * — groups, linked-tables, summaries
- `CrystalReportProduct.xml` * — linked-tables, summaries
- `CrystalReport_Invoice.xml` * — linked-tables, manual-formulas
- `CrystalReport_Product.xml` * — linked-tables
- `CrystalReportsHospital.xml` * — parameters, sql-commands
- `Crystall.xml` — linked-tables
- `Custom_Functions.xml` * — conditional-formatting, groups, images, linked-tables, manual-formulas, nested-groups, record-selection, sort-directions
- `Customer.xml` * — linked-tables
- `CustomerByMenu.xml` * — groups, linked-tables
- `CustomerList.xml` * — linked-tables
- `Customer_Profile_Report.xml` * — conditional-formatting, groups, images, linked-tables, manual-formulas, nested-groups, parameters, record-selection, subreports, summaries
- `Customers.xml` — groups, linked-tables
- `DataSetReport.xml` * — linked-tables, parameters
- `EmployeeList.xml` * — linked-tables
- `EmployeeList_2.xml` * — linked-tables, subreports
- `ExpenseReport.xml` * — linked-tables, parameters, summaries
- `Factura_Deudores_92_V29QR.xml` — conditional-formatting, groups, images, linked-tables, manual-formulas, parameters, record-selection, select-case, subreports
- `GeneralIrma.xml` — images, manual-formulas, sql-commands
- `GroupRpt.xml` — groups, linked-tables, nested-groups, summaries
- `GroupSubReports.xml` * — groups, linked-tables, subreports
- `IncomeStatement.xml` * — crosstabs, images, linked-tables, parameters, record-selection
- `InstrumentCheckSample.xml` * — charts, conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, sql-commands
- `InstrumentCheckSample1Week.xml` * — charts, conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, running-totals, sort-directions, sql-commands, subreports, summaries
- `InstrumentCheckSample2Weeks.xml` * — charts, conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, running-totals, sort-directions, sql-commands, subreports, summaries
- `InstrumentCheckSample3Weeks.xml` * — charts, conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, running-totals, sort-directions, sql-commands, subreports, summaries
- `ListOfAllInstruments.xml` — groups, parameters, sort-directions, sql-commands
- `LoV.xml` — linked-tables, multi-value-params, parameters
- `LoteF063.xml` — parameters, record-selection, sql-commands
- `MajorCitiesInCanadaUSAandMexico.xml` * — linked-tables
- `MonthlyVarianceCrossTab.xml` — crosstabs, images, linked-tables, parameters, record-selection
- `MostRecentStructuringOfCanadianCities.xml` * — charts, conditional-formatting, groups, linked-tables, manual-formulas, sort-directions, summaries
- `Oracle.12.xml` — conditional-formatting, sql-commands
- `OrderProcessingEfficiencyDashboard.xml` * — charts, conditional-formatting, groups, images, linked-tables, manual-formulas, multi-value-params, nested-groups, parameters, record-selection, sort-directions, summaries
- `PinkPaletteSampler.xml` * — conditional-formatting, linked-tables, record-selection
- `PrecioPromedio_00.xml` * — crosstabs, linked-tables, parameters, record-selection
- `PredictionModelControl.xml` — conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, sql-commands, subreports, summaries
- `Report1DbConsultas.xml` — sql-commands
- `ReportCustomer.xml` * — linked-tables
- `ReportFromDB.xml` * — linked-tables
- `RollingQuarterIncomeStatement.xml` — crosstabs, images, linked-tables, manual-formulas, parameters, record-selection
- `RptCanchasMasReservadas.xml` — images, linked-tables
- `RptCanchasMasReservadas_2.xml` * — images, linked-tables
- `RptHorariosOcupadosPorFecha.xml` * — images, linked-tables, parameters
- `RptReservasClientes.xml` * — images, linked-tables, parameters
- `SI51_rptProductos.xml` * — linked-tables, parameters, summaries
- `SQLCommand.12.xml` — sql-commands
- `SQLCommand.Parameters.12.xml` — parameters, sql-commands
- `SQLquerry.xml` * — sql-commands, subreports
- `SampleReport-2.xml` — linked-tables, parameters
- `SampleReport-3.xml` * — linked-tables
- `SampleReport.xml` * — linked-tables, parameters
- `SampleReportDataset.xml` — linked-tables, parameters
- `SampleReportDatasetParameters.xml` — linked-tables, manual-formulas, multi-value-params, parameters
- `SampleReportTwoDataSources.xml` — linked-tables, parameters
- `SampleReport_WithSubreportParameters.xml` — linked-tables, parameters, subreports
- `SimpleCrystal.xml` * — linked-tables
- `SortedVarianceAnalysisReport.xml` — crosstabs, images, linked-tables, parameters, record-selection
- `SportsTeams.xml` * — conditional-formatting, linked-tables
- `SportsTeams_TorontoOnly.xml` * — conditional-formatting, linked-tables, record-selection
- `Statement_of_Account.xml` * — conditional-formatting, groups, images, linked-tables, nested-groups, record-selection, running-totals, summaries
- `TestReport.xml` * — groups, linked-tables
- `Testing.xml` * — linked-tables
- `WebRangeParameter.xml` * — groups, linked-tables, multi-value-params, parameters, record-selection, summaries
- `WorldSalesReport.xml` * — charts, conditional-formatting, groups, images, linked-tables, nested-groups, record-selection, sort-directions, summaries
- `World_Sales_Report.xml` * — charts, conditional-formatting, groups, images, linked-tables, manual-formulas, nested-groups, record-selection, summaries
- `analyzer_report.xml` — linked-tables, parameters, subreports
- `crptDetails.xml` * — linked-tables, subreports
- `crptSubReport.xml` * — linked-tables, subreports
- `reporte.xml` * — linked-tables
- `rptCustomerList.xml` — linked-tables
- `sample1.xml` * — linked-tables
- `sample1_2.xml` * — linked-tables
- `simple.xml` * — linked-tables
- `subReport1.xml` * — groups, linked-tables, subreports
- `the_dotnet_dataset_report.xml` — linked-tables
- `the_java_dataset_report.xml` — linked-tables
- `thereport_with_subreport_with_dotnet_dataset.xml` — linked-tables, subreports
- `thereport_with_subreport_with_parameters.xml` * — linked-tables, parameters, subreports

`*` = carries saved data; renders in the Crystal viewer without its source database.
