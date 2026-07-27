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
| `manual-formulas/` | formulas needing the LLM or a human | 36 | 27 |
| `linked-tables/` | no SQL command - the query is generated from the layout | 118 | 94 |
| `sql-commands/` | verbatim SQL command objects | 32 | 17 |

## Per-report features

- `AlejandroNieto-DAM_CrystalReport1.xml` * — groups, linked-tables, nested-groups, summaries
- `AlejandroNieto-DAM_CrystalReport2.xml` * — linked-tables
- `AndyVarnoRLG_28_Inventory_Raw.xml` * — groups, linked-tables, nested-groups, record-selection
- `AndyVarnoRLG_28_JobSteps_Active_Jobs.xml` * — linked-tables, record-selection, sort-directions
- `AndyVarnoRLG_28_Job_Steps_for_material_swap.xml` * — linked-tables, record-selection
- `AndyVarnoRLG_28_Jobs_Ok_to_Close.xml` * — groups, linked-tables, record-selection
- `AndyVarnoRLG_28_Loblaws_Item_Label.xml` * — linked-tables, record-selection
- `AndyVarnoRLG_28_Mismatching_Print_Cyl_to_Print_Repeat.xml` * — linked-tables, record-selection, sort-directions
- `AndyVarnoRLG_28_Packing_on_Jobs_sorted_by_cost.xml` * — linked-tables, record-selection, sort-directions
- `AndyVarnoRLG_28__jobstep_2-6_to_2--4.xml` * — linked-tables, record-selection
- `FacundoRiveraCono_Factura_Deudores_92_V29QR.xml` — conditional-formatting, groups, images, linked-tables, manual-formulas, parameters, record-selection, select-case, subreports
- `FacundoRiveraCono_LoteF063.xml` — parameters, record-selection, sql-commands
- `Jakub-Syrek_CrystalReport1.xml` * — charts, groups, linked-tables, nested-groups, summaries
- `Jakub-Syrek_CrystalReport2.xml` * — linked-tables
- `Jakub-Syrek_CrystalReport3.xml` * — crosstabs, linked-tables
- `Jakub-Syrek_Customers.xml` — groups, linked-tables
- `Jakub-Syrek_EmployeeList.xml` * — linked-tables
- `Jakub-Syrek_EmployeeList_2.xml` * — linked-tables, subreports
- `Jakub-Syrek_SQLquerry.xml` * — sql-commands, subreports
- `Jakub-Syrek_subReport1.xml` * — groups, linked-tables, subreports
- `KrittinEddyDeveloper_ExpenseReport.xml` * — linked-tables, parameters, summaries
- `LarsBusk_CalibrationControlexp.xml` * — groups, images, manual-formulas, parameters, sql-commands, subreports
- `LarsBusk_GeneralIrma.xml` — images, manual-formulas, sql-commands
- `LarsBusk_InstrumentCheckSample.xml` * — charts, conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, sql-commands
- `LarsBusk_InstrumentCheckSample1Week.xml` * — charts, conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, running-totals, sort-directions, sql-commands, subreports, summaries
- `LarsBusk_InstrumentCheckSample2Weeks.xml` * — charts, conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, running-totals, sort-directions, sql-commands, subreports, summaries
- `LarsBusk_InstrumentCheckSample3Weeks.xml` * — charts, conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, running-totals, sort-directions, sql-commands, subreports, summaries
- `LarsBusk_ListOfAllInstruments.xml` — groups, parameters, sort-directions, sql-commands
- `LarsBusk_PredictionModelControl.xml` — conditional-formatting, groups, images, manual-formulas, nested-groups, parameters, sql-commands, subreports, summaries
- `M4sT3rJ3sUs_CrystalReport1.xml` * — images, linked-tables
- `M4sT3rJ3sUs_CrystalReport3.xml` — conditional-formatting, groups, images, linked-tables, manual-formulas, nested-groups
- `Red0699_CrystalReport1.xml` * — linked-tables
- `Red0699_CrystalReport2.xml` * — parameters, sql-commands
- `SI51_rptProductos.xml` * — linked-tables, parameters, summaries
- `TreesukonBuakleeDev_CrystalReport1.xml` * — linked-tables
- `TreesukonBuakleeDev_CrystalReport_Invoice.xml` * — linked-tables, manual-formulas
- `TreesukonBuakleeDev_CrystalReport_Product.xml` * — linked-tables
- `adatapost_SampleReport.xml` * — linked-tables, parameters
- `adatapost_TestReport.xml` * — groups, linked-tables
- `ajryan_AccountBalance.xml` — conditional-formatting, images, manual-formulas, parameters, running-totals, sort-directions, sql-commands, summaries
- `ajryan_AccountBalance_HANA.xml` — conditional-formatting, images, manual-formulas, parameters, running-totals, sort-directions, sql-commands, summaries
- `ajryan_Activity.xml` * — conditional-formatting, manual-formulas, parameters, sql-commands
- `ajryan_Activity_HANA.xml` * — conditional-formatting, manual-formulas, parameters, sql-commands
- `ajryan_B1Budget_M.xml` * — conditional-formatting, crosstabs, manual-formulas, parameters, record-selection, sql-commands
- `ajryan_B1Budget_Q.xml` * — conditional-formatting, crosstabs, manual-formulas, parameters, record-selection, sql-commands
- `ajryan_BOM.xml` * — conditional-formatting, manual-formulas, parameters, sql-commands
- `ajryan_BOM_HANA.xml` * — conditional-formatting, manual-formulas, parameters, sql-commands
- `andrecini_CrystalReport1.xml` * — linked-tables, subreports
- `andrecini_CrystalReport2.xml` * — linked-tables
- `andrecini_CrystalReport3.xml` * — linked-tables, manual-formulas
- `blackmount53_CrystalReportGrouping.xml` * — groups, linked-tables, summaries
- `blackmount53_CrystalReportProduct.xml` * — linked-tables, summaries
- `brunodevlock_CrystalReport1.xml` * — linked-tables
- `codebykey_RptCanchasMasReservadas.xml` — images, linked-tables
- `codebykey_RptCanchasMasReservadas_2.xml` * — images, linked-tables
- `codebykey_RptHorariosOcupadosPorFecha.xml` * — images, linked-tables, parameters
- `codebykey_RptReservasClientes.xml` * — images, linked-tables, parameters
- `coderblog-winson_Testing.xml` * — linked-tables
- `craibuc_LoV.xml` — linked-tables, multi-value-params, parameters
- `craibuc_Oracle.12.xml` — conditional-formatting, sql-commands
- `craibuc_SQLCommand.12.xml` — sql-commands
- `craibuc_SQLCommand.Parameters.12.xml` — parameters, sql-commands
- `devgis_CrystalReport1.xml` — linked-tables
- `devgis_CrystalReport2.xml` — linked-tables
- `devgis_CrystalReport3.xml` — groups, linked-tables
- `devistic-dotnet-projects_ReportCustomer.xml` * — linked-tables
- `diego6bravo_97-Lista_Por_Carro_Alfabetica_Con_Grupos__Print_.xml` * — conditional-formatting, groups, images, manual-formulas, nested-groups, sort-directions, sql-commands
- `diego6bravo_97-Lista_Por_Carro_Alfabetica__Print_.xml` * — conditional-formatting, groups, images, manual-formulas, sort-directions, sql-commands
- `diego6bravo_98-Lista_Por_Carro__Print_.xml` * — conditional-formatting, groups, images, manual-formulas, nested-groups, sort-directions, sql-commands
- `diego6bravo_CR__Dev_.xml` — images, parameters, sql-commands
- `diego6bravo_CR__Orig_.xml` — images, parameters, sort-directions, sql-commands, summaries
- `diego6bravo_CarteraEdadesFix.xml` — conditional-formatting, groups, images, nested-groups, parameters, sort-directions, sql-commands, summaries
- `diego6bravo_Cartera_Vendedores__Movil_.xml` — conditional-formatting, groups, images, nested-groups, parameters, sort-directions, sql-commands, summaries
- `diego6bravo_Comportamiento_Entregas.xml` — charts, sql-commands
- `dineshkummarc_CrossTab.xml` * — crosstabs, linked-tables
- `dineshkummarc_CrystalGraph.xml` * — charts, linked-tables
- `dineshkummarc_GroupRpt.xml` — groups, linked-tables, nested-groups, summaries
- `dineshkummarc_GroupSubReports.xml` * — groups, linked-tables, subreports
- `dineshkummarc_SimpleCrystal.xml` * — linked-tables
- `facherotqda_CrystalReportsHospital.xml` * — parameters, sql-commands
- `facherotqda_Report1DbConsultas.xml` — sql-commands
- `fernandoschilipack_CrystalReport1.xml` * — linked-tables
- `fernandoschilipack_CrystalReport2.xml` * — conditional-formatting, images, linked-tables
- `gerardo-lijs_DataSetReport.xml` * — linked-tables, parameters
- `gerardo-lijs_SampleReport.xml` — linked-tables, parameters
- `gerardo-lijs_SampleReportDataset.xml` — linked-tables, parameters
- `gerardo-lijs_SampleReportDatasetParameters.xml` — linked-tables, manual-formulas, multi-value-params, parameters
- `gerardo-lijs_SampleReportTwoDataSources.xml` — linked-tables, parameters
- `gerardo-lijs_SampleReport_WithSubreportParameters.xml` — linked-tables, parameters, subreports
- `guilherme-stefano_Customer.xml` * — linked-tables
- `guilherme-stefano_CustomerByMenu.xml` * — groups, linked-tables
- `guilherme-stefano_ReportFromDB.xml` * — linked-tables
- `ljokhan_AdventureWorks-MainMenu.xml` * — images, linked-tables, subreports
- `ljokhan_AdventureWorks-TotalSalesByDay.xml` * — charts, images, linked-tables, manual-formulas
- `ljokhan_AdventureWorks-TotalSalesByMonth.xml` * — charts, images, linked-tables
- `ljokhan_AdventureWorks-TotalSalesByYear.xml` * — charts, images, linked-tables
- `majorsilence_analyzer_report.xml` — linked-tables, parameters, subreports
- `majorsilence_the_dotnet_dataset_report.xml` — linked-tables
- `majorsilence_the_java_dataset_report.xml` — linked-tables
- `majorsilence_thereport_with_subreport_with_dotnet_dataset.xml` — linked-tables, subreports
- `majorsilence_thereport_with_subreport_with_parameters.xml` * — linked-tables, parameters, subreports
- `malachite10_reporte.xml` * — linked-tables
- `mkaleemahmad_CashFlowDetailReport.xml` * — linked-tables, manual-formulas, parameters, subreports
- `mkaleemahmad_CashFlowReport.xml` * — linked-tables, manual-formulas, parameters, subreports
- `morellanand_PrecioPromedio_00.xml` * — crosstabs, linked-tables, parameters, record-selection
- `nazrulbspi5_CrystalReport1.xml` * — linked-tables
- `orellabac_SampleReport.xml` * — linked-tables
- `ranahamid_CrystalReport1.xml` * — linked-tables
- `raselahmmedgit_Crystall.xml` — linked-tables
- `raselahmmedgit_crptDetails.xml` * — linked-tables, subreports
- `raselahmmedgit_crptSubReport.xml` * — linked-tables, subreports
- `raselahmmedgit_simple.xml` * — linked-tables
- `rdgasantos_CrystalReport.xml` * — linked-tables
- `rjoseph757-vs_CrystalReport1.xml` * — linked-tables
- `rjoseph757-vs_CrystalReport1_2.xml` * — linked-tables
- `rjoseph757-vs_CrystalReport1_2_3.xml` * — linked-tables
- `rjoseph757-vs_CrystalReport1_2_3_4.xml` * — linked-tables
- `rjoseph757-vs_CrystalReport1_2_3_4_5.xml` * — groups, linked-tables, nested-groups
- `rjoseph757-vs_CrystalReport1_2_3_4_5_6.xml` * — linked-tables
- `rjoseph757-vs_WebRangeParameter.xml` * — groups, linked-tables, multi-value-params, parameters, record-selection, summaries
- `rjoseph757-vs_World_Sales_Report.xml` * — charts, conditional-formatting, groups, images, linked-tables, manual-formulas, nested-groups, record-selection, summaries
- `sajjadahmad300_CrystalReport1.xml` * — images, linked-tables
- `sajjadahmad300_CrystalReport2.xml` * — images, linked-tables
- `sajjadahmad300_CrystalReport3.xml` * — images, linked-tables
- `saper-2_CrystalReport-code128.xml` — conditional-formatting, linked-tables, manual-formulas
- `souvikduttachoudhury_Consolidated_Balance_Sheet.xml` * — crosstabs, images, linked-tables
- `souvikduttachoudhury_Custom_Functions.xml` * — conditional-formatting, groups, images, linked-tables, manual-formulas, nested-groups, record-selection, sort-directions
- `souvikduttachoudhury_Customer_Profile_Report.xml` * — conditional-formatting, groups, images, linked-tables, manual-formulas, nested-groups, parameters, record-selection, subreports, summaries
- `souvikduttachoudhury_Statement_of_Account.xml` * — conditional-formatting, groups, images, linked-tables, nested-groups, record-selection, running-totals, summaries
- `souvikduttachoudhury_sample1.xml` * — linked-tables
- `souvikduttachoudhury_sample1_2.xml` * — linked-tables
- `suhaybnasir_CrystalReport1.xml` * — linked-tables, subreports
- `tekTutorialsHub_rptCustomerList.xml` — linked-tables
- `vssaini_CustomerList.xml` * — linked-tables
- `workcontrolgit_ComparativeIncomeStatement.xml` * — crosstabs, images, linked-tables, parameters, record-selection
- `workcontrolgit_ConsolidatedIncomeStatement.xml` * — crosstabs, images, linked-tables, parameters, record-selection
- `workcontrolgit_IncomeStatement.xml` * — crosstabs, images, linked-tables, parameters, record-selection
- `workcontrolgit_MonthlyVarianceCrossTab.xml` — crosstabs, images, linked-tables, parameters, record-selection
- `workcontrolgit_OrderProcessingEfficiencyDashboard.xml` * — charts, conditional-formatting, groups, images, linked-tables, manual-formulas, multi-value-params, nested-groups, parameters, record-selection, sort-directions, summaries
- `workcontrolgit_RollingQuarterIncomeStatement.xml` — crosstabs, images, linked-tables, manual-formulas, parameters, record-selection
- `workcontrolgit_SortedVarianceAnalysisReport.xml` — crosstabs, images, linked-tables, parameters, record-selection
- `workcontrolgit_WorldSalesReport.xml` * — charts, conditional-formatting, groups, images, linked-tables, manual-formulas, nested-groups, record-selection, sort-directions, summaries
- `worrallbrian_AlphaISOsByCountry.xml` * — conditional-formatting, linked-tables, manual-formulas
- `worrallbrian_ColourPaletteSampler.xml` * — conditional-formatting, linked-tables
- `worrallbrian_CountriesAndCapitolCitiesOfTheWorld.xml` * — linked-tables, manual-formulas
- `worrallbrian_MajorCitiesInCanadaUSAandMexico.xml` * — linked-tables
- `worrallbrian_MostRecentStructuringOfCanadianCities.xml` * — charts, conditional-formatting, groups, linked-tables, manual-formulas, sort-directions, summaries
- `worrallbrian_PinkPaletteSampler.xml` * — conditional-formatting, linked-tables, record-selection
- `worrallbrian_SportsTeams.xml` * — conditional-formatting, linked-tables
- `worrallbrian_SportsTeams_TorontoOnly.xml` * — conditional-formatting, linked-tables, record-selection

`*` = carries saved data; renders in the Crystal viewer without its source database.
