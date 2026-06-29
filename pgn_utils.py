"""PGN utility helpers for Chess Studio — file dialog wrappers.

Extracted from the ChessController in ``main.py`` to keep the controller
focused on orchestration and allow the dialog logic to be used / tested
independently.
"""

from __future__ import annotations

import os
from datetime import datetime

# ── File Dialogs ──────────────────────────────────────────────────


def open_pgn_dialog() -> str | None:
    """Open a system file-picker dialog for ``.pgn`` files.

    Returns the file content as a string, or *None* if the user cancels.
    """
    try:
        import tkinter as _tk
        import tkinter.filedialog as _fd

        root = _tk.Tk()
        root.withdraw()
        filepath = _fd.askopenfilename(
            title="Open PGN File",
            filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")],
        )
        root.destroy()
        if not filepath:
            return None
        with open(filepath, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def save_pgn_dialog(pgn_content: str) -> str | None:
    """Open a system file-save dialog for ``.pgn`` files.

    Writes *pgn_content* to the chosen path and returns the basename of the
    saved file, or *None* if the user cancels or an error occurs.
    """
    try:
        import tkinter as _tk
        import tkinter.filedialog as _fd

        root = _tk.Tk()
        root.withdraw()
        filepath = _fd.asksaveasfilename(
            title="Save PGN File",
            defaultextension=".pgn",
            filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")],
        )
        root.destroy()
        if not filepath:
            return None
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(pgn_content)
        return os.path.basename(filepath)
    except Exception:
        return None


# ── Auto-save ──────────────────────────────────────────────────────


def auto_save_pgn(
    pgn: str,
    opening_name: str = "",
    target_dir: str = "games",
) -> str | None:
    """Auto-save a PGN string to a timestamped file under *target_dir*.

    Returns the filename that was written, or *None* on failure.
    """
    if not pgn.strip():
        return None
    games_dir = os.path.join(os.getcwd(), target_dir)
    try:
        os.makedirs(games_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        eco_prefix = (
            opening_name[:8].replace(" ", "_").replace("\u2014", "-")
            if opening_name
            else ""
        )
        filename = f"chess_{ts}{'_'+eco_prefix if eco_prefix else ''}.pgn"
        filepath = os.path.join(games_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(pgn)
        return filename
    except OSError:
        return None
