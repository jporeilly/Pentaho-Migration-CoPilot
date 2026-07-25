# Pentaho Migration Copilot launcher (Windows PowerShell).
# Creates the venv on first run, installs the package, builds the frontend
# if needed, then serves the app at http://localhost:8321
# ASCII only - keep it parseable by Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Port = if ($env:COPILOT_PORT) { $env:COPILOT_PORT } else { "8321" }
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "[run] creating virtual environment..."
    python -m venv .venv
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -e ".[api,schema]"
}

# make sure the package (and its api/schema extras) is importable
& $Python -c "import pentaho_migration, fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[run] installing dependencies..."
    & $Python -m pip install -e ".[api,schema]"
}

if (-not (Test-Path (Join-Path $Root "frontend\dist\index.html"))) {
    Write-Host "[run] building frontend (first run)..."
    Push-Location (Join-Path $Root "frontend")
    npm install
    npm run build
    Pop-Location
}

Write-Host "[run] Pentaho Migration Copilot -> http://localhost:$Port"
& $Python -m uvicorn pentaho_migration.api.main:app --port $Port
