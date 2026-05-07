param(
    [string]$Url = "https://github.com/official-stockfish/Stockfish/releases/download/sf_18/stockfish-windows-x86-64.zip",
    [string]$OutputPath = "AI.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$DownloadDir = Join-Path $ProjectRoot ".engine_download"
$ZipPath = Join-Path $DownloadDir "stockfish.zip"
$ExtractDir = Join-Path $DownloadDir "extract"

Remove-Item -LiteralPath $DownloadDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $ExtractDir | Out-Null

Write-Host "Downloading Stockfish from $Url"
Invoke-WebRequest -Uri $Url -OutFile $ZipPath

Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractDir -Force

$engine = Get-ChildItem -LiteralPath $ExtractDir -Recurse -File -Filter "*.exe" |
    Where-Object { $_.Name -like "stockfish*.exe" } |
    Sort-Object Length -Descending |
    Select-Object -First 1

if (-not $engine) {
    throw "No Stockfish executable was found in the downloaded archive."
}

Copy-Item -LiteralPath $engine.FullName -Destination $OutputPath -Force
Write-Host "Stockfish ready at $OutputPath"
