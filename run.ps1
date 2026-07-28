# Pentaho Migration Copilot launcher (Windows PowerShell).
# Creates the venv on first run, installs the package, builds the frontend
# if needed, shows the consultant what this machine can do, then serves the
# app at http://localhost:8321
# ASCII only - keep it parseable by Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Port = if ($env:COPILOT_PORT) { $env:COPILOT_PORT } else { "8321" }
$Python = Join-Path $Root ".venv\Scripts\python.exe"

function Step($msg)  { Write-Host ("  > " + $msg) -ForegroundColor Cyan }
function Ok($msg)    { Write-Host ("  [OK]   " + $msg) -ForegroundColor Green }
function Warn($msg)  { Write-Host ("  [--]   " + $msg) -ForegroundColor DarkYellow }

# ----- banner ---------------------------------------------------------------
$Version = "?"
$initPy = Join-Path $Root "src\pentaho_migration\__init__.py"
if (Test-Path $initPy) {
    $m = Select-String -Path $initPy -Pattern '__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($m) { $Version = $m.Matches[0].Groups[1].Value }
}
Write-Host ""
Write-Host ("=" * 66) -ForegroundColor DarkCyan
Write-Host ("  Pentaho Migration Copilot  v" + $Version) -ForegroundColor White
Write-Host  "  Informatica + Talend -> PDI   |   SAP Crystal Reports -> PRD"
Write-Host ("=" * 66) -ForegroundColor DarkCyan
Write-Host ""

# ----- environment ----------------------------------------------------------
if (-not (Test-Path $Python)) {
    Step "First run: creating the Python environment (one-time, ~2 min)"
    python -m venv .venv
    & $Python -m pip install --upgrade pip --quiet
    & $Python -m pip install -e ".[api,schema]" --quiet
}

& $Python -c "import pentaho_migration, fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Step "Installing dependencies"
    & $Python -m pip install -e ".[api,schema]" --quiet
}

if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) {
    Step "Building the web UI (first run)"
    Push-Location (Join-Path $Root "frontend")
    npm install --silent
    npm run build | Out-Null
    Pop-Location
}

# ----- capability check: what can THIS machine demo? ------------------------
Write-Host "  Crystal environment on this machine:" -ForegroundColor White
$envJson = & $Python -c "import json; from pentaho_migration.reports.environment import environment_report; print(json.dumps(environment_report()))" 2>$null
if ($LASTEXITCODE -eq 0 -and $envJson) {
    $envInfo = $envJson | ConvertFrom-Json
    if ($envInfo.prd_home)   { Ok  ("Report Designer: " + $envInfo.prd_home + "  (validate + PDF preview + Open-in-PRD)") }
    else                     { Warn "Report Designer not found - preview/validate/release-check disabled (PRD_HOME)" }
    if ($envInfo.crystal_runtime) { Ok ("SAP Crystal runtime " + $envInfo.crystal_runtime + "  (view originals, extract .rpt drops)") }
    else                     { Warn "SAP Crystal runtime missing - .rpt drag-and-drop and the viewer need it" }
    if ($envInfo.rpttoxml)   { Ok  "RptToXml extractor  (drop the customer's .rpt straight on the app)" }
    else                     { Warn "RptToXml not found - only pre-extracted .xml dumps will convert" }
} else {
    Warn "capability check skipped (package not importable yet?)"
}
$viewer = Join-Path $Root "tools\RptViewer\RptViewer.exe"
if (Test-Path $viewer) { Ok "Crystal viewer  (View original .rpt, side-by-side demos)" }
else { Warn "Crystal viewer not built - run tools\RptViewer\build.ps1 for side-by-side" }
Write-Host ""

# ----- go -------------------------------------------------------------------
Write-Host  "  Open the app:      " -NoNewline
Write-Host ("http://localhost:" + $Port) -ForegroundColor Green
Write-Host  "  Demo walkthrough:  docs\DEMO-WALKTHROUGH.md  (scripted 10-minute demo)"
Write-Host  "  Quick start:       click 'Try Crystal Reports' - original opens in the"
Write-Host  "                     viewer, converts, release-check gates the download"
Write-Host  "  Stop:              Ctrl+C"
Write-Host ""
& $Python -m uvicorn pentaho_migration.api.main:app --port $Port
