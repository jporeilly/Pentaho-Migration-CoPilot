<#
.SYNOPSIS
    Developer helper for Migration Copilot on Windows 11.

.DESCRIPTION
    Mirrors the Makefile targets for machines without make.
    Run from anywhere; the script locates the repo root itself.

.EXAMPLE
    .\scripts\dev.ps1 setup          # create venv + install everything (run once)
    .\scripts\dev.ps1 test           # run the test suite
    .\scripts\dev.ps1 run            # start the review UI on http://127.0.0.1:8321
    .\scripts\dev.ps1 run-dev        # UI with auto-reload
    .\scripts\dev.ps1 convert        # convert the sample export into output\
    .\scripts\dev.ps1 convert my.xml # convert a specific PowerCenter export
    .\scripts\dev.ps1 gaps           # coverage/gap analysis over samples\informatica
    .\scripts\dev.ps1 ui-install     # npm install for the React frontend
    .\scripts\dev.ps1 ui-build       # build the React UI (served by `run`)
    .\scripts\dev.ps1 ui-dev         # frontend dev server with hot reload
    .\scripts\dev.ps1 status         # environment health check
    .\scripts\dev.ps1 clean          # remove caches and generated output
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "setup", "install", "test", "test-verbose", "run", "run-dev",
                 "convert", "parse", "gaps", "ui-install", "ui-build", "ui-dev",
                 "status", "clean", "distclean")]
    [string]$Command = "help",

    [Parameter(Position = 1)]
    [string]$Target,

    [int]$Port = 8321
)

$ErrorActionPreference = "Stop"
$Root   = Split-Path -Parent $PSScriptRoot
$Venv   = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Sample = Join-Path $Root "samples\m_load_sales.xml"

function Write-Step($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Assert-Venv {
    if (-not (Test-Path $Python)) {
        Write-Warn2 "Virtual environment not found at $Venv"
        Write-Warn2 "Run: .\scripts\dev.ps1 setup"
        exit 1
    }
}

function Invoke-Setup {
    Write-Step "Locating Python 3.13"
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $launcher) {
        Write-Warn2 "Python launcher 'py' not found. Install Python 3.13 from python.org first."
        exit 1
    }
    Write-Step "Creating virtual environment at $Venv"
    py -3.13 -m venv $Venv
    Invoke-Install
    Write-Ok "Setup complete. Try: .\scripts\dev.ps1 test"
}

function Invoke-Install {
    Assert-Venv
    Write-Step "Installing pentaho-migration (editable) with dev+api extras"
    & $Python -m pip install --upgrade pip --quiet
    & $Python -m pip install -e (Join-Path $Root ".[dev,api]")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Ok "Dependencies installed"
}

switch ($Command) {
    "help" {
        Get-Help $PSCommandPath -Examples
    }
    "setup"   { Invoke-Setup }
    "install" { Invoke-Install }
    "test" {
        Assert-Venv
        Write-Step "Running test suite"
        & $Python -m pytest -q --rootdir $Root $Root\tests
        exit $LASTEXITCODE
    }
    "test-verbose" {
        Assert-Venv
        & $Python -m pytest -v --rootdir $Root $Root\tests
        exit $LASTEXITCODE
    }
    "run" {
        Assert-Venv
        Write-Step "Review UI:  http://127.0.0.1:$Port    (Ctrl+C to stop)"
        Write-Step "API docs:   http://127.0.0.1:$Port/docs"
        & $Python -m uvicorn pentaho_migration.api.main:app --port $Port
    }
    "run-dev" {
        Assert-Venv
        Write-Step "Review UI (auto-reload):  http://127.0.0.1:$Port"
        & $Python -m uvicorn pentaho_migration.api.main:app --port $Port --reload
    }
    "convert" {
        Assert-Venv
        $file = if ($Target) { $Target } else { $Sample }
        $out  = Join-Path $Root "output\informatica"
        Write-Step "Converting $file -> $out"
        & $Python -m pentaho_migration.cli convert $file -o $out
        exit $LASTEXITCODE
    }
    "parse" {
        Assert-Venv
        $file = if ($Target) { $Target } else { $Sample }
        & $Python -m pentaho_migration.cli parse $file
        exit $LASTEXITCODE
    }
    "gaps" {
        Assert-Venv
        $dir = if ($Target) { $Target } else { Join-Path $Root "samples\informatica" }
        Write-Step "Coverage/gap analysis over $dir"
        & $Python -m pentaho_migration.cli gaps $dir
        exit $LASTEXITCODE
    }
    "ui-install" {
        Write-Step "Installing frontend dependencies (Node 18+ required)"
        Push-Location (Join-Path $Root "frontend"); npm install --no-fund --no-audit; Pop-Location
    }
    "ui-build" {
        Write-Step "Building React UI into frontend\dist"
        Push-Location (Join-Path $Root "frontend"); npm run build; Pop-Location
        Write-Ok "Built. 'dev.ps1 run' now serves the UI at http://127.0.0.1:$Port"
    }
    "ui-dev" {
        Write-Step "Frontend dev server with hot reload (start the backend first: dev.ps1 run)"
        Push-Location (Join-Path $Root "frontend"); npm run dev; Pop-Location
    }
    "status" {
        Write-Step "Environment status"
        if (Test-Path $Python) {
            Write-Ok ("Python:  " + (& $Python --version))
            $pkg = & $Python -m pip show pentaho-migration 2>$null | Select-String "^Version"
            if ($pkg) { Write-Ok "Package: pentaho-migration $($pkg -replace 'Version: ','')" }
            else      { Write-Warn2 "Package not installed - run: .\scripts\dev.ps1 install" }
        } else {
            Write-Warn2 "No venv - run: .\scripts\dev.ps1 setup"
        }
        $commit = git -C $Root log --oneline -1 2>$null
        if ($commit) { Write-Ok "Git:     $commit" }
    }
    "clean" {
        Write-Step "Removing caches and generated output"
        foreach ($dir in @("output", ".pytest_cache", "build", "dist")) {
            $p = Join-Path $Root $dir
            if (Test-Path $p) { Remove-Item -Recurse -Force $p; Write-Ok "removed $dir" }
        }
        Get-ChildItem $Root -Recurse -Directory -Filter "__pycache__" |
            Where-Object { $_.FullName -notlike "*\.venv\*" } |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
        Get-ChildItem (Join-Path $Root "src") -Directory -Filter "*.egg-info" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
        Write-Ok "clean"
    }
    "distclean" {
        & $PSCommandPath clean
        if (Test-Path $Venv) {
            Write-Step "Removing virtual environment"
            Remove-Item -Recurse -Force $Venv
            Write-Ok "removed .venv"
        }
    }
}
