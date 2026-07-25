# Pentaho Migration Copilot - uninstaller (Windows PowerShell).
# Removes everything the installer created; your source checkout, samples,
# and converted output stay unless you pass -All.
# ASCII only - keep it parseable by Windows PowerShell 5.1.
param(
    [switch]$Force,    # skip the confirmation prompt
    [switch]$All,      # also remove converted output/ and the project database
    [switch]$DryRun    # show what would be removed, remove nothing
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$InitFile = Join-Path $Root "src\pentaho_migration\__init__.py"
$Version = "unknown"
if (Test-Path $InitFile) {
    $m = Select-String -Path $InitFile -Pattern '__version__ = "([0-9.]+)"'
    if ($m) { $Version = $m.Matches[0].Groups[1].Value }
}

Write-Host ""
Write-Host "Pentaho Migration Copilot v$Version - uninstall" -ForegroundColor Cyan
Write-Host ""

$targets = @(
    @{ Path = ".venv";                Why = "Python virtual environment" },
    @{ Path = "frontend\node_modules"; Why = "npm packages (UI build deps)" },
    @{ Path = "frontend\dist";         Why = "built web UI" },
    @{ Path = ".pytest_cache";         Why = "test cache" }
)
if ($All) {
    $targets += @{ Path = "output";            Why = "converted .ktr/.kjb/.prpt output (-All)" }
    $targets += @{ Path = "config\project.db"; Why = "project store: batch-converted portfolio (-All)" }
}

Write-Host "This removes what install.ps1 created:"
$found = @()
foreach ($t in $targets) {
    $full = Join-Path $Root $t.Path
    if (Test-Path $full) {
        Write-Host ("  - {0,-24} {1}" -f $t.Path, $t.Why)
        $found += $full
    }
}
if (-not $found) {
    Write-Host "  (nothing found - already clean)"
    exit 0
}
Write-Host ""
Write-Host "Kept: source code, samples, docs, git history" -NoNewline
if (-not $All) { Write-Host ", converted output/, project database (pass -All to remove those too)" } else { Write-Host "" }
Write-Host ""

if ($DryRun) {
    Write-Host "Dry run - nothing removed." -ForegroundColor Yellow
    exit 0
}

if (-not $Force) {
    $answer = Read-Host "Proceed? [y/N]"
    if ($answer -notmatch "^[Yy]") {
        Write-Host "Cancelled - nothing removed."
        exit 0
    }
}

foreach ($full in $found) {
    Write-Host "  removing $full"
    Remove-Item -Recurse -Force $full -Confirm:$false
}
Get-ChildItem -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -Confirm:$false

Write-Host ""
Write-Host "Uninstalled. To reinstall later: .\install.ps1" -ForegroundColor Green
Write-Host "To remove the app entirely, delete this folder."
