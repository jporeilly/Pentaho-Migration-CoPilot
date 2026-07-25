# Pentaho Migration Copilot - one-shot bootstrap installer (Windows PowerShell).
#
#   Downloads the app from GitHub, installs it to C:\Pentaho-Migration,
#   detects your hardware (NVIDIA GPU VRAM, or CPU + RAM) and configures
#   the matching local LLM model, then tells you how to start.
#
#   Usage:   powershell -ExecutionPolicy Bypass -File bootstrap.ps1
#   Options: -InstallDir <path>   (default C:\Pentaho-Migration)
#            -Branch <name>       (default main)
#            -PullModel           (also run `ollama pull` for the chosen model)
#
# Works when piped (irm ... | iex) - it never relies on its own file location.
# ASCII only - keep it parseable by Windows PowerShell 5.1.
param(
    [string]$InstallDir = "C:\Pentaho-Migration",
    [string]$Branch = "main",
    [switch]$PullModel
)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/jporeilly/Pentaho-Migration-CoPilot"

Write-Host ""
Write-Host "=============================================================" -ForegroundColor DarkCyan
Write-Host "  Pentaho Migration Copilot - bootstrap installer" -ForegroundColor Cyan
Write-Host "=============================================================" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  Source : $RepoUrl ($Branch)"
Write-Host "  Target : $InstallDir"
Write-Host ""

# -- 1. get the code ------------------------------------------------------
Write-Host "[1/4] Downloading..." -ForegroundColor Yellow
$git = Get-Command git -ErrorAction SilentlyContinue
if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Host "  existing checkout found - pulling latest $Branch"
    Push-Location $InstallDir
    git fetch origin; git checkout $Branch; git pull origin $Branch
    Pop-Location
} elseif (Test-Path $InstallDir) {
    Write-Host "  $InstallDir exists but is not a git checkout - refusing to overwrite it." -ForegroundColor Red
    Write-Host "  Move it aside or pick another folder: bootstrap.ps1 -InstallDir <path>"
    exit 1
} elseif ($git) {
    git clone --branch $Branch "$RepoUrl.git" $InstallDir
} else {
    Write-Host "  git not found - downloading a zip snapshot instead"
    $zip = Join-Path $env:TEMP "pentaho-migration-$Branch.zip"
    Invoke-WebRequest "$RepoUrl/archive/refs/heads/$Branch.zip" -OutFile $zip
    $staging = Join-Path $env:TEMP "pentaho-migration-unzip"
    if (Test-Path $staging) { Remove-Item -Recurse -Force $staging -Confirm:$false }
    Expand-Archive $zip -DestinationPath $staging
    $inner = Get-ChildItem $staging -Directory | Select-Object -First 1
    Move-Item $inner.FullName $InstallDir
    Remove-Item $zip -Force; Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
}
Write-Host "  + code in $InstallDir"

# -- 2. install (venv, dependencies, web UI, environment preflight) -------
Write-Host ""
Write-Host "[2/4] Installing (this runs the guided installer)..." -ForegroundColor Yellow
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallDir "install.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Host "install.ps1 failed - fix the issue above and re-run bootstrap.ps1" -ForegroundColor Red
    exit 1
}

# -- 3. hardware detection -> LLM model -----------------------------------
# Mirrors the app's own recommendation ladder (src/pentaho_migration/llm/detect.py):
# translation is a short-context structured-code task, so qwen2.5-coder sized
# to memory: 24GB+ VRAM -> 32b, 12GB+ -> 14b, 6GB+ -> 7b, any GPU -> 3b;
# CPU-only: 32GB+ RAM -> 7b, 16GB+ -> 3b, else 1.5b.
Write-Host ""
Write-Host "[3/4] Detecting hardware for the local LLM..." -ForegroundColor Yellow

$vramGb = $null; $gpuCount = 0; $gpuNames = @()
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) {
    try {
        $lines = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null
        $totalMib = 0
        foreach ($line in @($lines)) {
            $parts = "$line" -split ","
            if ($parts.Count -ge 2) {
                $gpuNames += $parts[0].Trim()
                $totalMib += [double]$parts[1].Trim()
                $gpuCount += 1
            }
        }
        if ($gpuCount -gt 0) { $vramGb = [math]::Round($totalMib / 1024, 1) }
    } catch {}
}
$ramGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)

if ($vramGb) {
    Write-Host "  GPU  : $($gpuNames -join ' + ') ($vramGb GB VRAM across $gpuCount GPU(s))"
} else {
    Write-Host "  GPU  : none detected (nvidia-smi not found) - CPU mode"
}
Write-Host "  RAM  : $ramGb GB"

$ollamaEnv = [ordered]@{ OLLAMA_KEEP_ALIVE = "30m"; OLLAMA_NUM_PARALLEL = "2" }
if ($gpuCount -gt 1) { $ollamaEnv["OLLAMA_SCHED_SPREAD"] = "1" }
if ($vramGb) {
    $ollamaEnv["OLLAMA_FLASH_ATTENTION"] = "1"
    if ($vramGb -ge 24)     { $model = "qwen2.5-coder:32b"; $why = "$vramGb GB VRAM fits the 32B coder model" }
    elseif ($vramGb -ge 12) { $model = "qwen2.5-coder:14b"; $why = "$vramGb GB VRAM fits the 14B coder model" }
    elseif ($vramGb -ge 6)  { $model = "qwen2.5-coder:7b";  $why = "$vramGb GB VRAM fits the 7B coder model" }
    else                    { $model = "qwen2.5-coder:3b";  $why = "$vramGb GB VRAM is tight; 3B stays fully on GPU" }
} else {
    if ($ramGb -ge 32)     { $model = "qwen2.5-coder:7b";   $why = "no NVIDIA GPU; $ramGb GB RAM runs the 7B model on CPU" }
    elseif ($ramGb -ge 16) { $model = "qwen2.5-coder:3b";   $why = "no NVIDIA GPU; $ramGb GB RAM suits the 3B model on CPU" }
    else                   { $model = "qwen2.5-coder:1.5b"; $why = "limited memory; 1.5B is the safe floor" }
}
Write-Host "  Model: $model ($why)"

$settingsPath = Join-Path $InstallDir "config\settings.json"
if (Test-Path $settingsPath) {
    Write-Host "  config\settings.json already exists - keeping your configuration" -ForegroundColor Yellow
} else {
    New-Item -ItemType Directory -Force (Split-Path $settingsPath) | Out-Null
    $settings = [ordered]@{
        provider = "ollama"
        base_url = "http://127.0.0.1:11434"
        model    = $model
        env      = $ollamaEnv
    }
    # write WITHOUT a BOM: PS 5.1's Out-File -Encoding utf8 adds one, and the
    # app's strict JSON parser rejects it
    $json = $settings | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText($settingsPath, $json,
        (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  + LLM settings written to config\settings.json"
}

# -- 4. Ollama -------------------------------------------------------------
Write-Host ""
Write-Host "[4/4] Local LLM runtime..." -ForegroundColor Yellow
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host "  + Ollama found"
    if ($PullModel) {
        Write-Host "  pulling $model (this can be a large download)..."
        & ollama pull $model
    } else {
        Write-Host "  pull the model when ready:  ollama pull $model"
    }
} else {
    Write-Host "  Ollama not installed - the app works without it (deterministic"
    Write-Host "  conversion is unaffected); install it for AI formula assist and"
    Write-Host "  the schema chat: https://ollama.com/download"
    Write-Host "  then:  ollama pull $model"
}

Write-Host ""
Write-Host "=============================================================" -ForegroundColor DarkCyan
Write-Host "  Done. Start the app:" -ForegroundColor Green
Write-Host ""
Write-Host "    cd $InstallDir"
Write-Host "    .\run.ps1                 ->  http://localhost:8321"
Write-Host ""
Write-Host "  Docs: README.md - docs\INSTALL.md - docs\CRYSTAL-COVERAGE.md"
Write-Host "=============================================================" -ForegroundColor DarkCyan
