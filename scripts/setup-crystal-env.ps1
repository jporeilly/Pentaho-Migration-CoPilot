# One-command Crystal extraction environment setup (internal).
#
# Fetches the SAP Crystal .NET runtime MSIs and RptToXml.exe from this
# repository's "crystal-deps-v1" GitHub release (private repo - requires the
# gh CLI, logged in), so internal machines skip the SAP registration flow.
# Public/customer machines should follow docs/INSTALL.md instead (official
# SAP + RptToXml sources).
#
# Usage:  .\scripts\setup-crystal-env.ps1

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$release = "crystal-deps-v1"
$work = Join-Path $env:TEMP "crystal-deps"

function Test-CrystalRuntime {
    $keys = @(
        "HKLM:\SOFTWARE\SAP BusinessObjects\Crystal Reports for .NET Framework 4.0\Crystal Reports",
        "HKLM:\SOFTWARE\WOW6432Node\SAP BusinessObjects\Crystal Reports for .NET Framework 4.0\Crystal Reports"
    )
    foreach ($key in $keys) {
        if (Test-Path $key) { return $true }
    }
    return $false
}

$ghOk = $false
try { gh auth status *> $null; if ($LASTEXITCODE -eq 0) { $ghOk = $true } } catch {}
if (-not $ghOk) {
    Write-Host "ERROR: the gh CLI must be installed and logged in (gh auth login)."
    exit 2
}

New-Item -ItemType Directory -Force $work | Out-Null

# 1. SAP Crystal .NET runtime
if (Test-CrystalRuntime) {
    Write-Host "[OK] SAP Crystal .NET runtime already installed"
} else {
    Write-Host "Downloading SAP Crystal runtime MSIs from release $release ..."
    gh release download $release -p "CR13*MSI*.MSI" -D $work --clobber
    $msis = Get-ChildItem -Path $work -Filter "CR13*MSI*.MSI"
    foreach ($msi in $msis) {
        Write-Host "Installing $($msi.Name) (Windows will prompt for admin consent)..."
        Start-Process msiexec.exe -ArgumentList "/i", "`"$($msi.FullName)`"", "/passive" -Wait
    }
}

# 2. RptToXml.exe
$rptDir = Join-Path $repoRoot "tools\RptToXml"
if (Test-Path (Join-Path $rptDir "RptToXml.exe")) {
    Write-Host "[OK] RptToXml.exe already present"
} else {
    Write-Host "Downloading RptToXml from release $release ..."
    gh release download $release -p "RptToXml*.zip" -D $work --clobber
    $zip = Get-ChildItem -Path $work -Filter "RptToXml*.zip" | Select-Object -First 1
    New-Item -ItemType Directory -Force $rptDir | Out-Null
    Expand-Archive -Path $zip.FullName -DestinationPath $rptDir -Force
    $releaseDir = Join-Path $rptDir "Release"
    if (Test-Path $releaseDir) {
        Move-Item -Path (Join-Path $releaseDir "*") -Destination $rptDir -Force
        Remove-Item $releaseDir -Recurse -Force
    }
}

Write-Host ""
Write-Host "Verifying:"
& "$repoRoot\.venv\Scripts\python.exe" -m pdi_migration.cli report-env
