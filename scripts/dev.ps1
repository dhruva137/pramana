# Pramana local DX - install, seed, run API
# Usage: .\scripts\dev.ps1
# Optional: .\scripts\dev.ps1 -History -SkipInstall

param(
    [switch]$History,
    [switch]$SkipInstall,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== Pramana dev ($Root) ==" -ForegroundColor Cyan

if (-not $SkipInstall) {
    Write-Host "Installing Python deps..."
    python -m pip install -r requirements.txt
}

if (-not (Test-Path .env)) {
    if (Test-Path .env.example) {
        Copy-Item .env.example .env
        Write-Host "Created .env from .env.example"
    }
}

$seedArgs = @("-m", "core.db.seed", "--demo")
if ($History) { $seedArgs += "--history" }
Write-Host "Seeding demo data..."
python @seedArgs

Write-Host "Starting uvicorn on http://127.0.0.1:$Port"
Write-Host "Open / for console (if console/dist built) or /docs for OpenAPI"
python -m uvicorn core.app:app --host 127.0.0.1 --port $Port --reload
