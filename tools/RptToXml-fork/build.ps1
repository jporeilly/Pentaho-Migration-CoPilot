# Build the RptToXml fork (adds per-field format strings + credential
# redaction to stock RptToXml - see docs/RPTTOXML-EXTRACTOR.md).
#
# Requirements: VS 2019+ Build Tools (Roslyn csc) and the SAP Crystal .NET
# runtime assemblies in ..\RptToXml (installed by setup-crystal-env.ps1).
#
# Usage:  .\tools\RptToXml-fork\build.ps1

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$crd = Join-Path (Split-Path $here) "RptToXml"
$fw = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319"

$csc = Get-ChildItem "C:\Program Files (x86)\Microsoft Visual Studio\*\*\MSBuild\Current\Bin\Roslyn\csc.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $csc) {
    $csc = Get-ChildItem "C:\Program Files\Microsoft Visual Studio\*\*\MSBuild\Current\Bin\Roslyn\csc.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $csc) { Write-Host "ERROR: Roslyn csc.exe not found - install VS Build Tools."; exit 2 }

$refs = @(
    "$fw\mscorlib.dll", "$fw\System.dll", "$fw\System.Core.dll", "$fw\System.Xml.dll",
    "$fw\System.Data.dll", "$fw\System.Windows.Forms.dll", "$fw\System.Drawing.dll",
    "$fw\netstandard.dll",
    "$crd\System.CommandLine.dll", "$crd\OpenMcdf.dll",
    "$crd\CrystalDecisions.CrystalReports.Engine.dll", "$crd\CrystalDecisions.Shared.dll",
    "$crd\CrystalDecisions.ReportAppServer.ClientDoc.dll", "$crd\CrystalDecisions.ReportAppServer.Controllers.dll",
    "$crd\CrystalDecisions.ReportAppServer.DataDefModel.dll", "$crd\CrystalDecisions.ReportAppServer.ReportDefModel.dll",
    "$crd\CrystalDecisions.ReportAppServer.CommonObjectModel.dll", "$crd\CrystalDecisions.ReportAppServer.ObjectFactory.dll",
    "$crd\CrystalDecisions.ReportAppServer.CommLayer.dll"
) | ForEach-Object { "-r:`"$_`"" }

$sources = @("Program.cs", "RptDefinitionWriter.cs", "ConditionFormulas.cs", "Enums.cs", "Properties\AssemblyInfo.cs") |
    ForEach-Object { Join-Path $here $_ }

$out = Join-Path $crd "RptToXmlFork.exe"
& $csc.FullName -nologo -target:exe "-out:$out" -platform:x64 @refs @sources
if ($LASTEXITCODE -eq 0 -and (Test-Path $out)) {
    Write-Host "Built $out"
    Write-Host "extract-rpt.ps1 will prefer the fork automatically."
} else {
    Write-Host "Build failed."; exit 1
}
