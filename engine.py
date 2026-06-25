from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import chess
import chess.engine
import chess.pgn  # ensure pgn submodule is loaded at runtime

# ── Named Constants ──────────────────────────────────────────────

DEFAULT_HASH_SIZE_MB = 512
"""Default hash table size in megabytes for the UCI engine."""

EVALUATION_TIME_LIMIT = 0.1
"""Default time in seconds for a single board evaluation call."""


@dataclass(frozen=True)
class MoveRecord:
    """A single move stored with the side that made it and its SAN representation."""

    side: bool
    san: str

    @property
    def side_label(self) -> str:
        return "W" if self.side == chess.WHITE else "B"

    def legacy_text(self) -> str:
        return f"[{self.side_label}] {self.san}"


def format_move_history(move_history: list[MoveRecord]) -> str:
    """Format a move list into standard algebraic notation, one row per pair."""
    lines: list[str] = []
    for row in range((len(move_history) + 1) // 2):
        index = row * 2
        white_move = move_history[index].san
        black_move = move_history[index + 1].san if index + 1 < len(move_history) else ""
        if black_move:
            lines.append(f"{row + 1}. {white_move} {black_move}")
        else:
            lines.append(f"{row + 1}. {white_move}")
    return "\n".join(lines)


class AnalysisResult(TypedDict):
    """Result of a position analysis: evaluation in pawns and an optional best move."""
    evaluation: float
    suggestion: chess.Move | None


class ChessEngine:
    """Manages the chess board state, move history, captured pieces, and
    communication with the Stockfish UCI engine."""

    def __init__(self, ai_path: str = "AI.exe") -> None:
        self.board = chess.Board()
        self.move_history: list[MoveRecord] = []
        self.capture_history: list[str | None] = []
        self._board_lock = threading.RLock()
        self._engine_lock = threading.RLock()
        self.engine: chess.engine.SimpleEngine | None = None

        self.path = str(self._resolve_engine_path(ai_path))

        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(
                self.path,
                **self._engine_startup_options(),
            )

            cpu_count = os.cpu_count() or 1
            self.engine.configure(
                {
                    "Threads": max(1, cpu_count // 2),
                    "Hash": DEFAULT_HASH_SIZE_MB,
                    "UCI_LimitStrength": False,
                }
            )
            print("Engine initialized successfully.")
        except Exception as e:
            print(f"ERROR: Could not launch AI at {self.path}. \nDetail: {e}")
            self.engine = None

    def is_available(self) -> bool:
        """Check whether the UCI engine process is loaded and ready."""
        with self._engine_lock:
            return self.engine is not None

    def _mark_engine_unavailable(self) -> None:
        self.engine = None

    def _resolve_engine_path(self, engine_path: str) -> Path:
        path = Path(engine_path)
        if path.is_absolute():
            return path
        if getattr(sys, "frozen", False):
            external_path = Path(sys.executable).resolve().parent / path
            if external_path.exists():
                return external_path
            return Path(sys._MEIPASS) / path  # type: ignore[attr-defined]
        return Path(os.path.abspath(path))

    def _engine_startup_options(self) -> Any:
        if os.name != "nt":
            return {}

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return {
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "startupinfo": startupinfo,
        }

    def reset_engine(self, fen: str | None = None) -> None:
        """Reset the board to the starting position (or *fen*) and clear history."""
        with self._board_lock:
            self.board = chess.Board(fen) if fen else chess.Board()
            self.move_history.clear()
            self.capture_history.clear()

    def get_board_copy(self) -> chess.Board:
        """Return a deep copy of the current board."""
        with self._board_lock:
            return self.board.copy(stack=True)

    def get_fen(self) -> str:
        """Return the current board FEN string."""
        with self._board_lock:
            return self.board.fen()

    def get_move_history(self) -> list[MoveRecord]:
        """Return a copy of the move history."""
        with self._board_lock:
            return list(self.move_history)

    def get_legacy_move_history(self) -> list[str]:
        """Return move history as a list of legacy-formatted strings."""
        with self._board_lock:
            return [record.legacy_text() for record in self.move_history]

    def get_captured_piece_keys(self) -> tuple[list[str], list[str]]:
        """Return (white_captured, black_captured) piece key lists."""
        with self._board_lock:
            white_captured: list[str] = []
            black_captured: list[str] = []
            for captured_key in self.capture_history:
                if not captured_key:
                    continue
                if captured_key.startswith("w"):
                    white_captured.append(captured_key)
                else:
                    black_captured.append(captured_key)
            return white_captured, black_captured

    def get_last_move(self) -> chess.Move | None:
        """Return the most recently played move, or *None*."""
        with self._board_lock:
            return self.board.move_stack[-1] if self.board.move_stack else None

    def undo_last_move(self) -> bool:
        """Pop the last move from the board and history. Returns *False* if empty."""
        with self._board_lock:
            if not self.board.move_stack:
                return False
            self.board.pop()
            if self.move_history:
                self.move_history.pop()
            if self.capture_history:
                self.capture_history.pop()
            return True

    def _extract_white_score(self, score_obj: chess.engine.PovScore | None) -> float:
        """Convert a UCI Score to a centipawn value from White's perspective."""
        if not score_obj:
            return 0.0

        white_score = score_obj.white()

        if white_score.is_mate():
            mate_score = white_score.mate()
            return 99999.0 if (mate_score is not None and mate_score >= 0) else -99999.0

        cp_score = white_score.score()
        return float(cp_score) if cp_score is not None else 0.0

    def _evaluate_board_instance(
        self,
        board: chess.Board,
        time_limit: float = EVALUATION_TIME_LIMIT,
    ) -> float:
        """Run a quick evaluation of *board* and return a centipawn score."""
        if not self.is_available():
            return 0.0

        try:
            with self._engine_lock:
                assert self.engine is not None
                info = self.engine.analyse(board, chess.engine.Limit(time=time_limit))
        except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError):
            self._mark_engine_unavailable()
            return 0.0

        return self._extract_white_score(info.get("score"))

    def evaluate_board(self) -> float:
        """Convenience method: evaluate the current board position."""
        board = self.get_board_copy()
        return self._evaluate_board_instance(board, time_limit=EVALUATION_TIME_LIMIT)

    def analyze_position(
        self,
        fen: str | None = None,
        eval_time: float = 0.08,
        move_time: float = 0.4,
    ) -> AnalysisResult:
        """Analyse a position and return evaluation + best-move suggestion."""
        board = chess.Board(fen) if fen else self.get_board_copy()

        # Check terminal board states before checking engine availability.
        # These conditions are purely board-level and never need Stockfish.
        if board.is_checkmate():
            return {
                "evaluation": -999.99 if board.turn == chess.WHITE else 999.99,
                "suggestion": None,
            }
        if board.is_stalemate() or board.is_insufficient_material():
            return {"evaluation": 0.0, "suggestion": None}

        if not self.is_available():
            return {"evaluation": 0.0, "suggestion": None}

        evaluation = self._evaluate_board_instance(board, time_limit=eval_time) / 100.0

        if board.is_game_over() or move_time is None or move_time <= 0:
            return {"evaluation": evaluation, "suggestion": None}

        try:
            with self._engine_lock:
                assert self.engine is not None
                result = self.engine.play(board, chess.engine.Limit(time=move_time))
        except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError):
            self._mark_engine_unavailable()
            return {"evaluation": evaluation, "suggestion": None}

        return {
            "evaluation": evaluation,
            "suggestion": result.move if result and result.move else None,
        }

    def suggest_promotion_choice(
        self,
        fen: str,
        from_sq: int,
        to_sq: int,
        move_time: float = 0.18,
    ) -> chess.Move | None:
        """Ask the engine which promotion piece to use for a given pawn move."""
        board = chess.Board(fen)
        if not self.is_available():
            return None

        promotion_moves = [
            move
            for move in board.legal_moves
            if (
                move.from_square == from_sq
                and move.to_square == to_sq
                and move.promotion is not None
            )
        ]
        if not promotion_moves:
            return None

        try:
            with self._engine_lock:
                assert self.engine is not None
                result = self.engine.play(
                    board,
                    chess.engine.Limit(time=move_time),
                    root_moves=promotion_moves,
                )
        except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError):
            self._mark_engine_unavailable()
            return None
        return result.move if result and result.move else None

    def execute_move(
        self,
        from_sq: int,
        to_sq: int,
        promotion: int | None = None,
    ) -> bool:
        """Attempt to execute a move. Returns *True* on success."""
        with self._board_lock:
            move = chess.Move(from_sq, to_sq, promotion=promotion)
            if move not in self.board.legal_moves:
                return False

            captured_piece = self.board.piece_at(to_sq)
            if captured_piece is None and self.board.is_en_passant(move):
                capture_rank = chess.square_rank(to_sq) - (
                    1 if self.board.turn == chess.WHITE else -1
                )
                capture_square = chess.square(chess.square_file(to_sq), capture_rank)
                captured_piece = self.board.piece_at(capture_square)

            self.move_history.append(MoveRecord(self.board.turn, self.board.san(move)))

            if captured_piece is None:
                self.capture_history.append(None)
            else:
                color_key = "w" if captured_piece.color == chess.WHITE else "b"
                self.capture_history.append(f"{color_key}{captured_piece.symbol().upper()}")

            self.board.push(move)
            return True

    def get_numeric_eval(self) -> float:
        """Return the current evaluation in pawn units."""
        return self.evaluate_board() / 100.0

    # ── AI Skill Level ──────────────────────────────────────────

    ELO_PRESETS: tuple[str, ...] = ("Off", "1320", "1600", "1800", "2000", "2200", "2500", "2700", "3190")
    """Stockfish UCI_Elo presets. 'Off' disables strength limiting."""

    def set_skill_level(self, preset_index: int) -> str:
        """Configure Stockfish strength via UCI_Elo. Returns a display label."""
        if not self.is_available():
            return "AI Off"

        preset_index = max(0, min(preset_index, len(self.ELO_PRESETS) - 1))
        label = self.ELO_PRESETS[preset_index]
        with self._engine_lock:
            if label == "Off":
                self.engine.configure({"UCI_LimitStrength": False})  # type: ignore[union-attr]
                return "AI Full"
            elo = int(label)
            self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})  # type: ignore[union-attr]
        return f"AI {label}"

    # ── PGN Support ──────────────────────────────────────────────

    def export_pgn(self) -> str:
        """Export the current game as a PGN string by replaying moves from the start."""
        with self._board_lock:
            game = chess.pgn.Game()
            node: Any = game
            replay_board = chess.Board()
            for record in self.move_history:
                move = replay_board.parse_san(record.san)
                node = node.add_variation(move)
                replay_board.push(move)
            return str(game)

    @staticmethod
    def import_pgn(pgn: str) -> tuple[chess.Board, list[MoveRecord], list[str | None]] | None:
        """Parse a PGN string and return (board, move_history, capture_history) or None."""
        try:
            game = chess.pgn.read_game(io.StringIO(pgn))
            if game is None:
                return None
            board = game.board()
            move_history: list[MoveRecord] = []
            capture_history: list[str | None] = []
            for move in game.mainline_moves():
                captured_piece = board.piece_at(move.to_square)
                if captured_piece is None and board.is_en_passant(move):
                    capture_rank = chess.square_rank(move.to_square) - (
                        1 if board.turn == chess.WHITE else -1
                    )
                    capture_square = chess.square(chess.square_file(move.to_square), capture_rank)
                    captured_piece = board.piece_at(capture_square)
                move_history.append(MoveRecord(board.turn, board.san(move)))
                if captured_piece is None:
                    capture_history.append(None)
                else:
                    color_key = "w" if captured_piece.color == chess.WHITE else "b"
                    capture_history.append(f"{color_key}{captured_piece.symbol().upper()}")
                board.push(move)
            return board, move_history, capture_history
        except Exception:
            return None

    # ── Cleanup ──────────────────────────────────────────────────

    def quit(self) -> None:
        """Shut down the UCI engine process."""
        if self.engine:
            with self._engine_lock:
                try:
                    self.engine.quit()
                except chess.engine.EngineTerminatedError:
                    pass
                finally:
                    self.engine = None
