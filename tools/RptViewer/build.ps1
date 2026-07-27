# Build RptViewer - a .rpt viewer built on the free SAP Crystal .NET runtime
# (no designer, no Visual Studio integration required). See tools/RptViewer/README.md.
#
# Requirements: VS 2019+ Build Tools (Roslyn csc) and the SAP Crystal .NET
# runtime (installed by setup-crystal-env.ps1 / the runtime MSI).
#
# Usage:  .\tools\RptViewer\build.ps1

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$crd = Join-Path (Split-Path $here) "RptToXml"
$fw = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319"

$csc = Get-ChildItem "C:\Program Files (x86)\Microsoft Visual Studio\*\*\MSBuild\Current\Bin\Roslyn\csc.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $csc) {
    $csc = Get-ChildItem "C:\Program Files\Microsoft Visual Studio\*\*\MSBuild\Current\Bin\Roslyn\csc.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $csc) { Write-Host "ERROR: Roslyn csc.exe not found - install VS Build Tools."; exit 2 }

# The viewer control ships only in the GAC (the runtime MSI does not drop it
# next to the engine assemblies), so reference it from there.
$gac = "C:\Windows\Microsoft.NET\assembly\GAC_MSIL"
$viewer = Get-ChildItem "$gac\CrystalDecisions.Windows.Forms\*\CrystalDecisions.Windows.Forms.dll" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $viewer) {
    Write-Host "ERROR: CrystalDecisions.Windows.Forms not found in the GAC."
    Write-Host "Install the SAP Crystal Reports .NET runtime (64-bit MSI) first."
    exit 2
}

# Engine assemblies: prefer the local copies, fall back to the GAC.
function Resolve-CrAssembly([string]$name) {
    $local = Join-Path $crd "$name.dll"
    if (Test-Path $local) { return $local }
    $found = Get-ChildItem "$gac\$name\*\$name.dll" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.FullName }
    Write-Host "ERROR: $name.dll not found (tools\RptToXml or GAC)."
    exit 2
}

$refs = @(
    "$fw\mscorlib.dll", "$fw\System.dll", "$fw\System.Core.dll",
    "$fw\System.Drawing.dll", "$fw\System.Windows.Forms.dll",
    (Resolve-CrAssembly "CrystalDecisions.CrystalReports.Engine"),
    (Resolve-CrAssembly "CrystalDecisions.Shared"),
    (Resolve-CrAssembly "CrystalDecisions.ReportSource"),
    $viewer.FullName
) | ForEach-Object { "-r:`"$_`"" }

$out = Join-Path $here "RptViewer.exe"
& $csc.FullName -nologo -target:winexe "-out:$out" -platform:x64 @refs (Join-Path $here "RptViewer.cs")

if ($LASTEXITCODE -eq 0 -and (Test-Path $out)) {
    Write-Host "Built $out"
    Write-Host "Try:  .\tools\RptViewer\RptViewer.exe samples\crystal-rpt\ajryan_B1Budget_M.rpt"
} else {
    Write-Host "Build failed."; exit 1
}
