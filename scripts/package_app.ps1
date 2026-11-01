$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$tgz = Join-Path $out "dlq-judge-app.tgz"
if (Test-Path $tgz) { Remove-Item $tgz -Force }
# Create tar of app sources (no venv, no runs, no HF)
Push-Location $root
tar -czf $tgz `
  --exclude=.venv --exclude=runs --exclude=.git --exclude=dist `
  --exclude=__pycache__ --exclude=.pytest_cache --exclude=*.pyc `
  dlq_judge ui patterns bench docs infra scripts pyproject.toml README.md LICENSE .env.example
Pop-Location
Write-Host "packed $tgz size=$((Get-Item $tgz).Length)"
