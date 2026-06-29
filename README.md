# Chess Studio

Chess Studio is a Windows desktop chess application built with Python, Pygame, `python-chess`, and Stockfish 18. It provides a premium chess experience with legal move handling, move history, FEN/PGN support, Stockfish AI opponent, game review, and a rich set of visual and analytical tools.

The project uses an MVC-inspired structure:

- **Model:** `engine.py` manages chess state, legal moves, move history, captures, draw logic, and Stockfish communication.
- **View:** `ui_comp.py` manages the Pygame window, board rendering, panels, promotion menu, dialogs, icons, and layout.
- **Controller:** `main.py` connects input handling, game flow, UI state, game modes, dialogs, and background engine analysis.

This separation keeps rules, rendering, and interaction flow in distinct parts of the codebase.

## Features

### 🎮 Gameplay
- Local 1v1 chess with legal move validation through `python-chess`.
- Vs-AI mode where White is controlled by the player and Black is controlled by Stockfish 18 with configurable ELO (Full, 1320–3190).
- **Premove system** — queue moves during opponent's turn (click or drag). Auto-executes when it's your turn.
- **Promotion dialogs** — AI suggests the best promotion piece when hints are enabled.
- **Draw claim dialogs** — threefold repetition and fifty-move rule claims with "Claim Draw" / "Continue Playing" options.
- Automatic game endings for checkmate, stalemate, insufficient material, fivefold repetition, and seventy-five-move rule.
- **Chess clock** — configurable time controls (10+5, 5+0, 3+2, 15+10, 20+15) with low-time warning tick.
- **Auto-save** — completed games are automatically saved to the `games/` folder as PGN files.
- **Move annotations** — right-click on any move in the move list to cycle through !, ?, !!, ??, !? annotations.

### 👁️ Visual / Board
- **Animated piece movement** — smooth slide with ease-out cubic easing.
- **Takeback animation** — reverse slide animation on undo.
- **File/rank/square hover highlight** — subtle white overlay on hovered file, rank, and exact square.
- **Move number trail** — last 6 move numbers displayed on destination squares with dark badges.
- **Last-move arrow** — subtle green arrow from origin → destination.
- **Center highlight** — subtle yellow dots on d4/d5/e4/e5.
- **King-in-check highlight** — red overlay with border on the checked king.
- **Threat visualization** — red arrows from attackers to king when in check, with red dots on attacked squares.
- **Premove ghost indicator** — semi-transparent ghost piece + yellow arrow for queued premoves.
- **Board themes** — 4 color schemes (Classic, Blue, Green, Dark) switchable with `B` key, persisted in settings.
- **Board glow effect** — subtle blue glow shadow around the board.
- **Coordinates** — file and rank labels on the board edges.
- **User analysis arrows** — right-click drag to draw yellow arrows, right-click on target square to clear.

### 📊 Engine / Analysis
- **Live evaluation bar** with gradient fill (green/red).
- **Multi-PV** — up to 2 best lines with rank, score, and short principal variation.
- **Evaluation history graph** — line chart of last 20 eval snapshots (accent color).
- **Material balance graph** — line chart of net material advantage over last 30 moves (gold).
- **Engine depth/node display** — shows current search depth and node count.
- **Background analysis** — threaded loop keeps evaluation fresh at all times.
- **AI hints** — toggleable suggested move arrows and promotion suggestions (A key).
- **Game review** — post-game analysis with classification (brilliant/best/excellent/good/inaccuracy/mistake/blunder).
- **ECO opening detection** — 400+ common openings detected with ECO codes.
- **Legal move counter** — shows number of legal moves in the Engine Pulse panel.

### 🔊 Audio
- **Sound effects** — move, capture, check, game over, button, undo, flag fall.
- **Low-time tick** — 880Hz tick warning when <10s on clock.
- **Sound toggle** — S key to enable/disable.
- **Volume control** — `-` and `=` keys adjust volume 0–100%, persisted in settings.

### 🧭 Navigation / UX
- **Shortcut overlay** — H key shows all keyboard shortcuts.
- **Click move in list** — click any move to jump to that position for review.
- **Keyboard move-list navigation** — ↑/↓/←/→ arrows to step through move history.
- **Scroll move list** — mouse wheel over the move list panel.
- **Drag scrollbar** — click and drag the scrollbar thumb in the move list.
- **Flash messages** — status updates for all actions.
- **Board image copy** — Ctrl+Shift+B captures the board area to clipboard as an image.
- **Result dialog** — post-game dialog with review summary and game stats.
- **Auto-flip** — board resets to White's perspective when starting a new game in AI mode.

### 🔧 Import / Export
- **PGN import from clipboard** — Ctrl+O.
- **PGN export to clipboard** — Ctrl+P (includes player names in PGN headers).
- **PGN file open** — Ctrl+Shift+O opens a file dialog to load PGN files.
- **PGN file save** — Ctrl+Shift+P saves the current game via file dialog.
- **FEN import from clipboard** — Ctrl+F sets up any position from a FEN string.
- **Copy FEN** — C key.
- **Copy move list** — Ctrl+C.
- **Auto-save** — completed games saved to `games/` with ECO-prefixed filenames.

### ⚙️ Settings Persistence
- Sound on/off
- Volume level
- AI ELO index
- Clock time control preset
- Board theme
- Window size

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
| Right-click drag on board | Draw analysis arrow |
| Right-click on move list | Cycle move annotation (!, ?, !!, ??, !?) |
| Mouse wheel over move list | Scroll move history |
| Click on move in list | Jump to that position |
| `R` | New game |
| `U` | Undo last move |
| `F` | Flip board orientation |
| `A` | Toggle AI hints and promotion suggestions |
| `M` | Toggle local 1v1 / vs-AI mode |
| `C` | Copy current FEN |
| `Ctrl+C` | Copy the full move list |
| `S` | Toggle sound effects |
| `-` / `=` | Volume down / up |
| `B` | Cycle board theme |
| `E` | Cycle AI difficulty (ELO) |
| `P` | Start / pause chess clock |
| `T` | Cycle time control preset |
| `H` | Toggle shortcut overlay |
| `↑/↓/←/→` | Navigate move history (review mode) |
| `Esc` | Cancel promotion, clear selection, close dialog |
| `Enter` | Confirm primary dialog action |
| `Q/N/R/B` | Select promotion piece (when dialog open) |
| `Shift+click` | Auto-queen promotion |
| `Ctrl+O` | Import PGN from clipboard |
| `Ctrl+Shift+O` | Open PGN file |
| `Ctrl+P` | Export PGN to clipboard |
| `Ctrl+Shift+P` | Save PGN file |
| `Ctrl+F` | Import FEN from clipboard |
| `Ctrl+Shift+B` | Copy board image to clipboard |
| `F2` | Save board screenshot to `games/` folder |
| `F3` | Toggle PGN metadata viewer |
| `F4` | Toggle blindfold mode (hide pieces for visualization training) |

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

The codebase is organized around a small MVC-style split with supporting utility modules.

| Layer | File | Responsibility |
| --- | --- | --- |
| Model | `engine.py` | Board state, legal moves, SAN history, captures, draw checks, Stockfish evaluation, AI move selection |
| View | `ui_comp.py` | Pygame rendering, responsive layout, panels, board hit-testing, promotion menu, dialogs, clipboard support |
| Controller | `main.py` | Event loop, user actions, mode switching, promotion flow, draw dialogs, background analysis coordination |
| Utilities | `clock_utils.py` | Clock formatting, presets, animation helpers (pure functions) |
| Utilities | `pgn_utils.py` | PGN file open/save dialog helpers (pure functions) |
| Data | `openings_data.py` | 500+ opening database entries (ECO code, name, UCI moves) |
| Logic | `openings.py` | Opening detection tree, `detect_opening()`, `get_opening_continuations()` |

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
|-- clock_utils.py           # Clock utility functions
|-- engine.py                # Model
|-- main.py                  # Controller
|-- openings.py              # Opening detection logic
|-- openings_data.py         # Opening database (data only)
|-- pgn_utils.py             # PGN utility functions
|-- ui_comp.py               # View
|-- requirements.txt
|-- RELEASE_COMMANDS.md
|-- THIRD_PARTY_NOTICES.md
|-- LICENSE
|-- README.md
`-- tests/
    |-- test_engine.py       # Core engine tests (47)
    |-- test_features.py     # Premium feature tests (16)
    `-- test_integration.py  # Integration + utility tests (20)
```

## Tests

Three test files provide comprehensive coverage:

```powershell
# Core engine tests — board state, moves, draw detection, PGN roundtrips
python -m pytest tests/test_engine.py -v

# Premium feature tests — player names, move annotations, clock animation, legal moves
python -m pytest tests/test_features.py -v

# Integration + utility tests — clock_utils, pgn_utils, opening continuations
python -m pytest tests/test_integration.py -v -k "TestClockUtils or TestPgnUtils or TestOpeningContinuations"

# All tests (83 total)
python -m pytest tests/ -v
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
