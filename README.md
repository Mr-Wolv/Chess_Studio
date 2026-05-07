# Chess Studio

Chess Studio is a Windows desktop chess application built with Python, Pygame, `python-chess`, and Stockfish 18. It provides a local chess board, legal move handling, move history, FEN export, draw handling, promotion support, and an optional Stockfish-controlled opponent.

The project uses an MVC-inspired structure:

- **Model:** `engine.py` manages chess state, legal moves, move history, captures, draw logic, and Stockfish communication.
- **View:** `ui_comp.py` manages the Pygame window, board rendering, panels, promotion menu, dialogs, icons, and layout.
- **Controller:** `main.py` connects input handling, game flow, UI state, game modes, dialogs, and background engine analysis.

This separation keeps rules, rendering, and interaction flow in distinct parts of the codebase.

## Features

- Local 1v1 chess with legal move validation through `python-chess`.
- Vs-AI mode where White is controlled by the player and Black is controlled by Stockfish 18.
- AI hints are disabled by default and can be toggled with `A`.
- Promotion dialogs can show Stockfish's suggested promotion when hints are enabled.
- Engine availability is reflected in the Engine Pulse panel.
- Move history can be scrolled in the side panel.
- `Ctrl+C` copies the full move list.
- `C` copies the current FEN.
- Captured pieces are displayed for both sides.
- Claim dialogs are shown for threefold repetition and the fifty-move rule.
- Automatic game endings are handled for checkmate, stalemate, insufficient material, fivefold repetition, and the seventy-five-move rule.
- Windows executable builds are supported through PyInstaller.
- CI and release workflows are included for reproducible Windows packaging.

## Quick Start

For packaged releases, the release ZIP contains:

```text
ChessStudio.exe
README.md
LICENSE
THIRD_PARTY_NOTICES.md
```

`ChessStudio.exe` starts the application. Production releases are expected to include Stockfish 18 as `AI.exe`, so engine features are available without additional setup.

## Controls

| Input | Action |
| --- | --- |
| Left click / drag | Select and move pieces |
| Mouse wheel over move list | Scroll move history |
| `R` | New game |
| `U` | Undo |
| `F` | Flip board |
| `A` | Toggle AI hints and promotion suggestions |
| `M` | Toggle local 1v1 / vs-AI mode |
| `C` | Copy current FEN |
| `Ctrl+C` | Copy the full move list |
| `Esc` | Cancel promotion, clear selection, or close a dialog |
| `Enter` | Confirm the primary dialog action |

## Run From Source

Requirements:

- Windows
- Python 3.12
- PowerShell
- `pygame==2.6.1`
- `chess==1.11.2`

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Fetch the official Stockfish 18 Windows x86-64 release and copy it locally as `AI.exe`:

```powershell
.\scripts\fetch-stockfish.ps1
```

Run the application:

```powershell
python main.py
```

If `AI.exe` is not present, local 1v1 play remains available. Engine hints and vs-AI mode are disabled until Stockfish can be loaded.

## Stockfish 18

Chess Studio uses the official Stockfish 18 Windows x86-64 release:

```text
https://github.com/official-stockfish/Stockfish/releases/download/sf_18/stockfish-windows-x86-64.zip
```

The engine binary is not committed to the repository. The local and packaged executable name is:

```text
AI.exe
```

Runtime engine lookup supports:

1. `AI.exe` in the project root when running from source.
2. `AI.exe` beside `ChessStudio.exe` for local packaged builds.
3. `AI.exe` inside PyInstaller's bundled extraction directory.

If the engine is missing or becomes unavailable, the Engine Pulse panel reports that AI is not loaded.

## Architecture

The codebase is organized around a small MVC-style split.

| Layer | File | Responsibility |
| --- | --- | --- |
| Model | `engine.py` | Board state, legal moves, SAN history, captures, draw checks, Stockfish evaluation, AI move selection |
| View | `ui_comp.py` | Pygame rendering, responsive layout, panels, board hit-testing, promotion menu, dialogs, clipboard support |
| Controller | `main.py` | Event loop, user actions, mode switching, promotion flow, draw dialogs, background analysis coordination |

The model can be read as the source of chess state, the view as the rendering and hit-testing layer, and the controller as the coordinator between application events and state changes.

## Project Layout

```text
Chess_Game/
|-- .github/workflows/
|   |-- ci.yml
|   `-- release.yml
|-- assets/                  # Chess piece images
|-- scripts/
|   |-- build.ps1            # Local and CI PyInstaller build
|   |-- fetch-stockfish.ps1  # Downloads Stockfish 18 as AI.exe
|   `-- trigger-cicd.ps1     # Convenience workflow trigger
|-- chess.ico                # Window and executable icon
|-- engine.py                # Model
|-- main.py                  # Controller
|-- ui_comp.py               # View
|-- requirements.txt
|-- RELEASE_COMMANDS.md
|-- THIRD_PARTY_NOTICES.md
|-- LICENSE
`-- README.md
```

## Build

Create a clean Windows executable:

```powershell
.\scripts\build.ps1 -Clean
```

Fetch Stockfish before building:

```powershell
.\scripts\build.ps1 -Clean -FetchEngine
```

The generated executable is written to:

```text
dist/ChessStudio.exe
```

The build includes UI assets, `chess.ico`, and `AI.exe` when the engine is present or fetched. For a development build without Stockfish:

```powershell
.\scripts\build.ps1 -Clean -NoBundleEngine
```

## CI And Release

The repository includes two GitHub Actions workflows:

- **CI:** validates source, verifies required assets, compiles Python files, fetches Stockfish 18, and builds a Windows executable artifact.
- **Release:** builds the executable, packages it with the README, license, and third-party notices, then publishes a versioned GitHub release ZIP.

The convenience script can trigger the normal CI workflow:

```powershell
.\scripts\trigger-cicd.ps1
```

The same script can trigger the release workflow with a version:

```powershell
.\scripts\trigger-cicd.ps1 -Workflow release -Version v1.0.0
```

Additional release command examples are documented in `RELEASE_COMMANDS.md`.

## Distribution

Releases are structured as self-contained Windows packages. The release workflow downloads Stockfish from the official upstream archive, bundles it as `AI.exe`, builds `ChessStudio.exe`, and packages the executable with the required project and license documentation.

Release package expectations:

- `ChessStudio.exe` opens directly into the Pygame window without an extra console.
- `chess.ico` is used for the executable and window icon.
- Stockfish 18 is bundled as `AI.exe`.
- Engine features are available when Stockfish loads successfully.
- The UI reports AI unavailability when Stockfish cannot be loaded.
- `README.md`, `LICENSE`, and `THIRD_PARTY_NOTICES.md` are included in the release ZIP.

`AI.exe` is ignored by Git. CI/CD handles the production engine download so the repository does not store the upstream binary.

## License

This repository is licensed under GPLv3. See `LICENSE` for the full license text.

Stockfish and other third-party components remain under their own licenses. See `THIRD_PARTY_NOTICES.md` for attribution and distribution notes.
