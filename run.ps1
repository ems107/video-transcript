# Arranca la aplicación: compila el frontend si hace falta y sirve todo en http://127.0.0.1:8770
param(
    [int]$Port = 8770,
    [switch]$Rebuild,
    [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$dist = Join-Path $root "frontend\dist\index.html"
if ($Rebuild -or -not (Test-Path $dist)) {
    Write-Host "Compilando el frontend..."
    Push-Location (Join-Path $root "frontend")
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
    Pop-Location
}

Push-Location (Join-Path $root "backend")
if (-not $NoBrowser) {
    Start-Job -ScriptBlock { param($p) Start-Sleep 4; Start-Process "http://127.0.0.1:$p" } -ArgumentList $Port | Out-Null
}
Write-Host "Vídeo Transcript en http://127.0.0.1:$Port  (Ctrl+C para salir)"
uv run uvicorn app.main:app --host 127.0.0.1 --port $Port
Pop-Location
