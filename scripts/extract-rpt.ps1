# Extract Crystal Reports .rpt binaries to RptToXml dumps.
#
# Prerequisites (check with: pentaho-migrate report-env):
#   1. SAP Crystal Reports .NET runtime (free, 64-bit runtime MSI, latest SP):
#      https://pages.community.sap.com/topics/crystal-reports/visual-studio
#   2. RptToXml.exe (github.com/ajryan/RptToXml/releases) in tools\RptToXml\
#      or pointed to by the RPTTOXML_PATH environment variable.
#
# Usage:
#   .\scripts\extract-rpt.ps1                          # samples\crystal-rpt -> samples\crystal\real
#   .\scripts\extract-rpt.ps1 -InDir C:\customer\rpts -OutDir C:\customer\xml

param(
    [string]$InDir = "",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
if ($InDir -eq "") { $InDir = Join-Path $repoRoot "samples\crystal-rpt" }
if ($OutDir -eq "") { $OutDir = Join-Path $repoRoot "samples\crystal\real" }

# locate the extractor: prefer the fork (per-field formats + redaction),
# fall back to stock RptToXml.exe
$rptToXml = $env:RPTTOXML_PATH
if (-not $rptToXml -or -not (Test-Path $rptToXml)) {
    $rptToXml = Join-Path $repoRoot "tools\RptToXml\RptToXmlFork.exe"
}
if (-not (Test-Path $rptToXml)) {
    $rptToXml = Join-Path $repoRoot "tools\RptToXml\RptToXml.exe"
}
$env:RPTTOXML_REDACT = "1"
if (-not (Test-Path $rptToXml)) {
    Write-Host "ERROR: RptToXml.exe not found. Place it in tools\RptToXml\ or set RPTTOXML_PATH."
    Write-Host "Binaries: https://github.com/ajryan/RptToXml/releases"
    exit 2
}

$files = Get-ChildItem -Path $InDir -Filter *.rpt -File
if ($files.Count -eq 0) {
    Write-Host "No .rpt files found in $InDir"
    exit 1
}
New-Item -ItemType Directory -Force $OutDir | Out-Null

Write-Host "Extracting $($files.Count) .rpt file(s) with $rptToXml"
$ok = 0
$failed = 0
$failures = @()
foreach ($file in $files) {
    $outFile = Join-Path $OutDir ($file.BaseName + ".xml")
    & $rptToXml $file.FullName $outFile | Out-Null
    if ($LASTEXITCODE -eq 0 -and (Test-Path $outFile) -and (Get-Item $outFile).Length -gt 0) {
        $ok = $ok + 1
    } else {
        $failed = $failed + 1
        $failures += $file.Name
        if (Test-Path $outFile) { Remove-Item $outFile -Force }
    }
}

Write-Host ""
Write-Host "Extracted: $ok    Failed: $failed    Output: $OutDir"
if ($failures.Count -gt 0) {
    Write-Host "Failures (often password-protected or pre-9.0 format):"
    foreach ($name in $failures) { Write-Host "  $name" }
}
Write-Host ""
Write-Host "Next: pentaho-migrate report-scrub $OutDir   (removes credentials RptToXml copies from the .rpt files)"
Write-Host "Then: pentaho-migrate report-gaps $OutDir"
