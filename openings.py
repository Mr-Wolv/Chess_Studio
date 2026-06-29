"""
Chess opening detection — walks a game's move history and identifies
the opening name + ECO code by matching against a curated tree of
the most played lines (covering ~95 % of human games).

Each entry is (eco, name, uci_moves) where uci_moves is a list of
UCIs in the format "e2e4".  The detector walks the tree of all known
openings, returning the *deepest* match (most moves played).

Usage:
    from openings import detect_opening
    eco, name = detect_opening(move_history)
"""

from __future__ import annotations

from typing import Any

import chess

from engine import MoveRecord
from openings_data import OPENINGS


def _build_opening_tree() -> dict[str, Any]:
    """Build a nested dict tree from OPENINGS for efficient look-up.

    Returns a tree of: {uci_move: {uci_move: ... {ECO: ..., name: ...}}}
    """
    tree: dict[str, Any] = {}
    for eco, name, uci_moves in OPENINGS:
        node = tree
        for uci in uci_moves:
            if uci not in node:
                node[uci] = {}
            node = node[uci]
        # Store opening info at this node (deeper entries overwrite shallower)
        node["__eco__"] = eco
        node["__name__"] = name
    return tree


_OPENING_TREE = _build_opening_tree()


def get_opening_continuations(
    move_history: list[MoveRecord],
    max_results: int = 4,
) -> list[tuple[str, str, str]]:
    """Return likely continuations from the current position in the opening tree.

    Each element is *(san, eco, name)* — the SAN representation of the
    continuation move, its ECO code, and its opening name.

    The results are ordered by the order in which they appear in the
    opening database (roughly ECO order).

    Returns an empty list when the current position is not in the tree
    or there are no named continuations available.
    """
    node = _OPENING_TREE
    board = chess.Board()

    # Walk the tree to the current position
    for record in move_history:
        try:
            move = board.parse_san(record.san)
            uci = move.uci()
            if uci in node:
                node = node[uci]
            else:
                return []  # Position not found in opening tree
            board.push(move)
        except (ValueError, chess.InvalidMoveError):
            return []

    # Collect children that have opening names
    continuations: list[tuple[str, str, str]] = []
    for uci, child in node.items():
        if uci.startswith("__"):
            continue
        if "__eco__" in child and "__name__" in child:
            try:
                move = chess.Move.from_uci(uci)
                san = board.san(move)
                continuations.append((san, child["__eco__"], child["__name__"]))
            except (ValueError, chess.InvalidMoveError):
                continue

    # Deduplicate by ECO (same ECO may appear multiple times with diff names)
    seen: set[str] = set()
    unique: list[tuple[str, str, str]] = []
    for san, eco, name in continuations:
        key = f"{eco}:{name}"
        if key not in seen:
            seen.add(key)
            unique.append((san, eco, name))

    return unique[:max_results]


def detect_opening(move_history: list[MoveRecord]) -> tuple[str, str]:
    """Detect the opening from a list of MoveRecords.

    Returns (ECO_code, opening_name).  If no opening is detected,
    returns ("?", "Unknown Opening").
    """
    node = _OPENING_TREE
    last_eco: str = "?"
    last_name: str = "Unknown Opening"

    # Rebuild board from move history to convert SAN -> UCI for matching
    board = chess.Board()
    for record in move_history:
        try:
            move = board.parse_san(record.san)
            uci = move.uci()
            if uci in node:
                node = node[uci]
                if "__eco__" in node:
                    last_eco = node["__eco__"]
                    last_name = node["__name__"]
            else:
                # Partial match is OK — we still report what we found
                break
            board.push(move)
        except (ValueError, chess.InvalidMoveError):
            break

    return last_eco, last_name


# ── Quick test ──────────────────────────────────────────────────

if __name__ == "__main__":
    # Test with Italian Game
    records = [
        MoveRecord(chess.WHITE, "e4"),
        MoveRecord(chess.BLACK, "e5"),
        MoveRecord(chess.WHITE, "Nf3"),
        MoveRecord(chess.BLACK, "Nc6"),
        MoveRecord(chess.WHITE, "Bc4"),
    ]
    eco, name = detect_opening(records)
    print(f"Opening: {eco} — {name}")
