# Pentaho Migration Copilot - installer (Windows PowerShell).
# Sets up everything the app needs and tells you what it found.
# ASCII only - keep it parseable by Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# -- version + about -----------------------------------------------------
$InitFile = Join-Path $Root "src\pentaho_migration\__init__.py"
$Version = "unknown"
$m = Select-String -Path $InitFile -Pattern '__version__ = "([0-9.]+)"'
if ($m) { $Version = $m.Matches[0].Groups[1].Value }

Write-Host ""
Write-Host "=============================================================" -ForegroundColor DarkCyan
Write-Host "  Pentaho Migration Copilot  v$Version" -ForegroundColor Cyan
Write-Host "=============================================================" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  AI-assisted migration of legacy data platforms into Pentaho:"
Write-Host ""
Write-Host "    * Informatica PowerCenter and Talend  ->  native PDI (.ktr/.kjb)"
Write-Host "    * SAP Crystal Reports                 ->  Report Designer (.prpt)"
Write-Host ""
Write-Host "  Deterministic where accuracy is non-negotiable, AI only where"
Write-Host "  semantic judgment is required. Anything the tool cannot prove"
Write-Host "  is flagged for human review - never guessed, never hidden."
Write-Host ""

# -- prerequisites --------------------------------------------------------
Write-Host "[1/4] Checking prerequisites..." -ForegroundColor Yellow
$ok = $true

$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
    $pyver = (& python --version) 2>&1
    Write-Host "  + Python found: $pyver"
} else {
    Write-Host "  x Python 3.11+ not found - install from https://www.python.org/downloads/" -ForegroundColor Red
    $ok = $false
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($npm) {
    $nodever = (& node --version) 2>&1
    Write-Host "  + Node.js found: $nodever (needed once, to build the web UI)"
} else {
    Write-Host "  x Node.js 18+ not found - install from https://nodejs.org/" -ForegroundColor Red
    $ok = $false
}

if (-not $ok) {
    Write-Host ""
    Write-Host "Install the missing prerequisites above, then re-run install.ps1" -ForegroundColor Red
    exit 1
}

# -- python environment ---------------------------------------------------
Write-Host ""
Write-Host "[2/4] Python environment..." -ForegroundColor Yellow
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "  creating .venv..."
    python -m venv .venv
    & $Python -m pip install --upgrade pip --quiet
}
Write-Host "  installing the package + API + schema-agent extras..."
& $Python -m pip install -e ".[api,schema]" --quiet
Write-Host "  + Python environment ready"

# -- web UI -----------------------------------------------------------------
Write-Host ""
Write-Host "[3/4] Web UI..." -ForegroundColor Yellow
if (-not (Test-Path (Join-Path $Root "frontend\node_modules"))) {
    Write-Host "  npm install (first run)..."
    Push-Location (Join-Path $Root "frontend"); npm install --silent; Pop-Location
}
if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) {
    Write-Host "  building the React UI..."
    Push-Location (Join-Path $Root "frontend"); npm run build --silent; Pop-Location
} else {
    Write-Host "  + UI already built (frontend\dist)"
}

# -- optional environment ---------------------------------------------------
Write-Host ""
Write-Host "[4/4] Crystal Reports environment (optional - only needed to" -ForegroundColor Yellow
Write-Host "      extract .rpt files and engine-validate .prpt output):" -ForegroundColor Yellow
& $Python -m pentaho_migration.cli report-env
Write-Host "      Anything missing above? See docs\INSTALL.md - the app works"
Write-Host "      without it for RptToXml dumps and all ETL sources."

# -- done -------------------------------------------------------------------
Write-Host ""
Write-Host "=============================================================" -ForegroundColor DarkCyan
Write-Host "  Installed. Next steps:" -ForegroundColor Green
Write-Host ""
Write-Host "    .\run.ps1                 start the app -> http://localhost:8321"
Write-Host "                              then click 'Try the Crystal sample'"
Write-Host ""
Write-Host "    CLI highlights (.venv\Scripts\pentaho-migrate --help):"
Write-Host "      convert <export>        Informatica/Talend -> PDI .ktr"
Write-Host "      report <dump> --jndi X  Crystal dump -> PRD .prpt + report"
Write-Host "      report-triage <dir>     verdict per report over a corpus"
Write-Host "      report-qa <dump>        layout lint before opening PRD"
Write-Host ""
Write-Host "    Docs: README.md - docs\INSTALL.md - docs\BEST_PRACTICES.md"
Write-Host "    Uninstall: .\uninstall.ps1"
Write-Host "=============================================================" -ForegroundColor DarkCyan
