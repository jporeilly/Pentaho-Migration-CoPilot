# Pentaho Migration Copilot - installer (Windows PowerShell).
# Sets up everything the app needs and tells you what it found.
# ASCII only - keep it parseable by Windows PowerShell 5.1.
#
# Two installation types (same pattern as our other tools):
#   1) Complete - full installation: Python env with every extra (API,
#      schema agent, LLM providers), the web UI, JDBC drivers into a
#      detected Report Designer, and the Crystal environment preflight.
#   2) Custom   - pick the components: an ETL-only box can skip the
#      Crystal environment, an API/CLI server can skip the web UI.
# Unattended: .\install.ps1 -Mode Complete   (no prompts)

[CmdletBinding()]
param(
    [ValidateSet("", "Complete", "Custom")]
    [string]$Mode = ""
)

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
Write-Host "    * SAP Crystal Reports and Xactions    ->  Report Designer (.prpt)"
Write-Host ""
Write-Host "  Deterministic where accuracy is non-negotiable, AI only where"
Write-Host "  semantic judgment is required. Anything the tool cannot prove"
Write-Host "  is flagged for human review - never guessed, never hidden."
Write-Host ""

# -- installation type ---------------------------------------------------
if ($Mode -eq "") {
    Write-Host "Installation type:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  [1] Complete - full installation (recommended)"
    Write-Host "      Python env + all extras (API, schema agent, LLM providers),"
    Write-Host "      web UI, JDBC drivers into a detected Report Designer,"
    Write-Host "      Crystal environment preflight."
    Write-Host ""
    Write-Host "  [2] Custom - choose the components"
    Write-Host "      e.g. an ETL-only box without the Crystal environment, or"
    Write-Host "      an API/CLI server without the web UI."
    Write-Host ""
    $choice = Read-Host "Choose [1/2] (Enter = 1)"
    if ($choice -eq "2") { $Mode = "Custom" } else { $Mode = "Complete" }
}

function Ask-Component([string]$Prompt, [string]$Default) {
    # Custom mode asks; Complete takes every default.
    if ($Mode -eq "Complete") { return ($Default -eq "Y") }
    $suffix = "[Y/n]"
    if ($Default -ne "Y") { $suffix = "[y/N]" }
    $answer = Read-Host "  $Prompt $suffix"
    if ($answer -eq "") { return ($Default -eq "Y") }
    return ($answer -match "^[Yy]")
}

Write-Host ""
Write-Host "Components ($Mode):" -ForegroundColor Yellow
Write-Host "  + Python environment + core package (always installed)"
$WantLLM     = Ask-Component "LLM provider clients (Anthropic/OpenAI - local Ollama needs neither)?" "Y"
$WantUI      = Ask-Component "Web UI (needs Node.js 18+; skip for an API/CLI-only box)?" "Y"
$WantCrystal = Ask-Component "Crystal environment preflight (.rpt extraction + engine validation)?" "Y"
$PrdHome = "C:\Pentaho\design-tools\report-designer"
$WantDrivers = $false
if (Test-Path $PrdHome) {
    $WantDrivers = Ask-Component "JDBC drivers into Report Designer ($PrdHome)?" "Y"
} else {
    Write-Host "  - JDBC drivers: skipped (no Report Designer at $PrdHome)"
}

# -- prerequisites --------------------------------------------------------
Write-Host ""
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

if ($WantUI) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) {
        $nodever = (& node --version) 2>&1
        Write-Host "  + Node.js found: $nodever (needed once, to build the web UI)"
    } else {
        Write-Host "  x Node.js 18+ not found - install from https://nodejs.org/" -ForegroundColor Red
        Write-Host "    (or re-run and deselect the web UI for an API/CLI-only box)" -ForegroundColor Red
        $ok = $false
    }
} else {
    Write-Host "  - Node.js: not needed (web UI deselected)"
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
$Extras = "api,schema"
if ($WantLLM) { $Extras = "api,schema,llm" }
Write-Host "  installing the package + extras [$Extras]..."
& $Python -m pip install -e ".[$Extras]" --quiet
Write-Host "  + Python environment ready"

# -- web UI -----------------------------------------------------------------
Write-Host ""
if ($WantUI) {
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
} else {
    Write-Host "[3/4] Web UI: skipped (API + CLI only)" -ForegroundColor Yellow
}

# -- optional environment ---------------------------------------------------
Write-Host ""
if ($WantDrivers) {
    Write-Host "      Installing JDBC drivers into Report Designer (gap-fill," -ForegroundColor Yellow
    Write-Host "      each SHA-1 verified against Maven)..." -ForegroundColor Yellow
    try {
        & $Python -m pentaho_migration.cli report-install-drivers
    } catch {
        Write-Host "      driver install failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "      (re-run later: pentaho-migrate report-install-drivers)"
    }
    Write-Host ""
}
if ($WantCrystal) {
    Write-Host "[4/4] Crystal Reports environment (only needed to extract" -ForegroundColor Yellow
    Write-Host "      .rpt files and engine-validate .prpt output):" -ForegroundColor Yellow
    & $Python -m pentaho_migration.cli report-env
    Write-Host "      Anything missing above? See docs\INSTALL.md - the app works"
    Write-Host "      without it for RptToXml dumps and all ETL sources."
} else {
    Write-Host "[4/4] Crystal environment preflight: skipped" -ForegroundColor Yellow
}

# -- done -------------------------------------------------------------------
Write-Host ""
Write-Host "=============================================================" -ForegroundColor DarkCyan
Write-Host "  Installed ($Mode). Next steps:" -ForegroundColor Green
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
