# Chess Studio

Chess Studio is a polished Windows desktop chess application built with Python, Pygame, `python-chess`, and Stockfish 18 analysis. It provides a responsive local chess board, move history, FEN copying, draw-claim handling, promotion assistance, and a vs-AI mode designed to be bundled cleanly with PyInstaller.

## Features

- Local 1v1 chess with legal move validation.
- Vs-AI mode where the player controls White and Stockfish 18 controls Black.
- Engine hints toggled with `A`; hints are off by default.
- Stockfish promotion guidance restricted to the legal promotion choices.
- Scrollable move-list panel.
- `Ctrl+C` copies the full move list.
- `C` copies the current FEN.
- Captured-piece display for both sides.
- Claim dialogs for threefold repetition and the fifty-move rule.
- Automatic game-over handling for checkmate, stalemate, insufficient material, fivefold repetition, and the seventy-five-move rule.
- High-DPI aware Windows rendering.
- PyInstaller-friendly runtime path handling for bundled assets and engine binaries.

## Project Structure

```text
Chess_Game/
|-- .github/
|   |-- workflows/
|       |-- ci.yml
|       `-- release.yml
|-- assets/              # Piece images
|-- scripts/
|   |-- build.ps1        # Local/CI PyInstaller build script
|   `-- fetch-stockfish.ps1
|-- AI.exe               # Stockfish 18 executable copied/renamed locally, ignored by Git
|-- engine.py            # Board state, move history, UCI engine integration
|-- main.py              # Application controller and event loop
|-- ui_comp.py           # Pygame layout, rendering, and hit-testing
|-- requirements.txt     # Runtime dependencies
|-- LICENSE
|-- THIRD_PARTY_NOTICES.md
`-- README.md
```

## Requirements

- Windows
- Python 3.12
- `pygame==2.6.1`
- `chess==1.11.2`
- Stockfish 18 copied/renamed to `AI.exe` for source runs

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run From Source

```powershell
python main.py
```

For source runs, `AI.exe` should be present in the project root. If it is missing, Chess Studio still opens as a local chess board, but engine hints and vs-AI mode are unavailable. Production builds fetch and bundle Stockfish 18 automatically.

To download the official Stockfish 18 Windows x86-64 release and place it at `AI.exe`:

```powershell
.\scripts\fetch-stockfish.ps1
```

## Controls

| Input | Action |
| --- | --- |
| Left click / drag | Select and move pieces |
| Mouse wheel over move list | Scroll move history |
| `R` | Start a new game |
| `U` | Undo the last move |
| `F` | Flip board orientation |
| `A` | Toggle AI hints and promotion suggestions |
| `M` | Toggle local 1v1 / vs-AI mode |
| `C` | Copy current FEN |
| `Ctrl+C` | Copy the full move list |
| `Esc` | Cancel promotion, clear selection, or close a dialog |
| `Enter` | Confirm the primary dialog action |

## Engine Behavior

Chess Studio expects Stockfish 18 at `AI.exe`. The expected upstream archive is:

```text
https://github.com/official-stockfish/Stockfish/releases/download/sf_18/stockfish-windows-x86-64.zip
```

The helper script `scripts/fetch-stockfish.ps1` downloads that archive, extracts the Stockfish executable, and copies it to `AI.exe`.

Engine lookup order:

1. If running from source, `AI.exe` is resolved from the project root.
2. If running as a PyInstaller executable, Chess Studio first checks beside the executable.
3. If bundled with `--add-binary`, Chess Studio checks PyInstaller's bundle extraction directory.

Production CI and release builds fetch and bundle Stockfish 18 automatically. The external-engine lookup is kept as a development safety net for source runs or custom builds.

Engine hints are intentionally disabled on startup. Press `A` to enable best-move arrows and promotion suggestions. When a pawn promotion is pending, Chess Studio asks Stockfish to choose among only the legal promotion pieces for that pawn move.

## Draws And Game Endings

Chess Studio distinguishes claimable draw rights from automatic endings:

- Threefold repetition and the fifty-move rule open a claim dialog when available.
- Continuing from a claim dialog suppresses that exact-position prompt, while future claimable positions can still prompt again.
- Fivefold repetition and the seventy-five-move rule end the game automatically.
- Checkmate, stalemate, and insufficient material are detected automatically.

## Build Locally

Install build tooling and create a one-file Windows executable:

```powershell
.\scripts\build.ps1 -Clean
```

The executable is written to:

```text
dist/ChessStudio.exe
```

By default, the build script bundles `AI.exe` when it is present in the project root.

To fetch Stockfish automatically before building:

```powershell
.\scripts\build.ps1 -Clean -FetchEngine
```

To intentionally create an engine-less development build:

```powershell
.\scripts\build.ps1 -Clean -NoBundleEngine
```

## CI/CD

The repository includes GitHub Actions workflows:

- `.github/workflows/ci.yml`
  - Installs Python 3.12 dependencies.
  - Verifies all required piece assets are present.
  - Compiles Python sources.
  - Downloads the official Stockfish 18 Windows x86-64 release.
  - Builds a Windows `ChessStudio.exe` artifact with Stockfish bundled as `AI.exe`.

- `.github/workflows/release.yml`
  - Manual `workflow_dispatch` release pipeline.
  - Downloads the official Stockfish 18 Windows x86-64 release.
  - Builds `ChessStudio.exe` with Stockfish bundled as `AI.exe`.
  - Packages the executable with `README.md`, `LICENSE`, and `THIRD_PARTY_NOTICES.md`.
  - Publishes a GitHub release ZIP for the supplied version tag.

Because `AI.exe` is ignored by Git, CI/CD fetches Stockfish 18 from the official upstream release URL before production packaging. If that download is unavailable, the production build should fail rather than publish an engine-less release.

## Packaging Notes

- `assets/` must be included in PyInstaller builds.
- `AI.exe` is required for production builds and for engine hints/vs-AI play.
- `AI.exe` is ignored by Git because the Stockfish binary is large and distributed separately upstream.
- If distributing a build with Stockfish bundled, include Stockfish's license and required attribution with the release.
- `THIRD_PARTY_NOTICES.md` is included for release packaging and should be kept current.
- The repository license is GPLv3. Confirm that bundled assets and binaries are compatible with your intended distribution.

## Dependencies

```text
chess==1.11.2
pygame==2.6.1
```
