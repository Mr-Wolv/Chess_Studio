param(
    [switch]$Clean,
    [switch]$BundleEngine,
    [switch]$FetchEngine,
    [switch]$NoBundleEngine
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if ($Clean) {
    Remove-Item -LiteralPath "build" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "dist" -Recurse -Force -ErrorAction SilentlyContinue
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install "pyinstaller>=6.0"

if ($FetchEngine -and -not (Test-Path -LiteralPath "AI.exe")) {
    & (Join-Path $PSScriptRoot "fetch-stockfish.ps1")
}

$ShouldBundleEngine = -not $NoBundleEngine -and (Test-Path -LiteralPath "AI.exe")

$argsList = @(
    "--onefile",
    "--windowed",
    "--name", "ChessStudio",
    "--icon", "chess.ico",
    "--add-data", "assets;assets",
    "--add-data", "chess.ico;.",
    "main.py"
)

if ($ShouldBundleEngine) {
    $argsList = @(
        "--onefile",
        "--windowed",
        "--name", "ChessStudio",
        "--icon", "chess.ico",
        "--add-data", "assets;assets",
        "--add-data", "chess.ico;.",
        "--add-binary", "AI.exe;.",
        "main.py"
    )
}

if (($BundleEngine -or $FetchEngine) -and -not (Test-Path -LiteralPath "AI.exe")) {
    throw "A bundled-engine build was requested, but AI.exe was not found. Run with -FetchEngine or place Stockfish 18 at AI.exe."
}

pyinstaller @argsList

Write-Host "Build complete: dist\ChessStudio.exe"
if ($ShouldBundleEngine) {
    Write-Host "Stockfish bundled from AI.exe."
} else {
    Write-Host "Engine not bundled. Place AI.exe beside ChessStudio.exe to enable Stockfish at runtime."
}
