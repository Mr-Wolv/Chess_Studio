from dataclasses import dataclass
import chess
import chess.engine
import os
from pathlib import Path
import sys
import threading


@dataclass(frozen=True)
class MoveRecord:
    side: bool
    san: str

    @property
    def side_label(self):
        return "W" if self.side == chess.WHITE else "B"

    def legacy_text(self):
        return f"[{self.side_label}] {self.san}"


def format_move_history(move_history: list[MoveRecord]) -> str:
    lines: list[str] = []
    for row in range((len(move_history) + 1) // 2):
        index = row * 2
        white_move = move_history[index].san
        black_move = (
            move_history[index + 1].san if index + 1 < len(move_history) else ""
        )
        if black_move:
            lines.append(f"{row + 1}. {white_move} {black_move}")
        else:
            lines.append(f"{row + 1}. {white_move}")
    return "\n".join(lines)


class ChessEngine:
    def __init__(self, Ai_path="AI.exe"):
        self.board = chess.Board()
        self.move_history: list[MoveRecord] = []
        self.capture_history = []
        self.active_suggestion = None
        self._board_lock = threading.RLock()
        self._engine_lock = threading.RLock()

        self.path = str(self._resolve_engine_path(Ai_path))

        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(self.path)

            cpu_count = os.cpu_count() or 1
            self.engine.configure(
                {
                    "Threads": max(1, cpu_count // 2),
                    "Hash": 512,
                    "UCI_LimitStrength": False,
                }
            )
            print("Engine initialized successfully.")

        except Exception as e:
            print(f"ERROR: Could not launch AI at {self.path}. \nDetail: {e}")
            self.engine = None

    def _resolve_engine_path(self, engine_path):
        path = Path(engine_path)
        if path.is_absolute():
            return path
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / path  # type: ignore[attr-defined]
        return Path(os.path.abspath(path))

    def reset_engine(self, fen=None):
        with self._board_lock:
            self.board = chess.Board(fen) if fen else chess.Board()
            self.move_history = []
            self.capture_history = []
            self.active_suggestion = None

    def get_board_copy(self):
        with self._board_lock:
            return self.board.copy(stack=True)

    def get_fen(self):
        with self._board_lock:
            return self.board.fen()

    def get_move_history(self):
        with self._board_lock:
            return list(self.move_history)

    def get_legacy_move_history(self):
        with self._board_lock:
            return [record.legacy_text() for record in self.move_history]

    def get_captured_piece_keys(self):
        with self._board_lock:
            white_captured = []
            black_captured = []
            for captured_key in self.capture_history:
                if not captured_key:
                    continue
                if captured_key.startswith("w"):
                    white_captured.append(captured_key)
                else:
                    black_captured.append(captured_key)
            return white_captured, black_captured

    def get_last_move(self):
        with self._board_lock:
            return self.board.move_stack[-1] if self.board.move_stack else None

    def undo_last_move(self):
        with self._board_lock:
            if not self.board.move_stack:
                return False
            self.board.pop()
            if self.move_history:
                self.move_history.pop()
            if self.capture_history:
                self.capture_history.pop()
            self.active_suggestion = None
            return True

    def _extract_white_score(self, score_obj):
        if not score_obj:
            return 0

        white_score = score_obj.white()

        if white_score.is_mate():
            mate_score = white_score.mate()
            return 99999 if (mate_score is not None and mate_score >= 0) else -99999

        cp_score = white_score.score()
        return cp_score if cp_score is not None else 0

    def _evaluate_board_instance(self, board, time_limit=0.1):
        if not self.engine:
            return 0

        with self._engine_lock:
            info = self.engine.analyse(board, chess.engine.Limit(time=time_limit))

        return self._extract_white_score(info.get("score"))

    def evaluate_board(self):
        board = self.get_board_copy()
        return self._evaluate_board_instance(board, time_limit=0.1)

    def generate_analysis(self, time_limit=1.0):
        board = self.get_board_copy()
        if not self.engine or board.is_game_over():
            return None

        with self._engine_lock:
            result = self.engine.play(board, chess.engine.Limit(time=time_limit))

        if result and result.move:
            self.active_suggestion = result.move
            return result.move
        return None

    def analyze_position(self, fen=None, eval_time=0.08, move_time=0.4):
        board = chess.Board(fen) if fen else self.get_board_copy()

        if not self.engine:
            return {"evaluation": 0.0, "suggestion": None}

        if board.is_checkmate():
            return {
                "evaluation": -999.99 if board.turn == chess.WHITE else 999.99,
                "suggestion": None,
            }
        if board.is_stalemate() or board.is_insufficient_material():
            return {"evaluation": 0.0, "suggestion": None}

        evaluation = self._evaluate_board_instance(board, time_limit=eval_time) / 100.0

        if board.is_game_over() or move_time is None or move_time <= 0:
            return {"evaluation": evaluation, "suggestion": None}

        with self._engine_lock:
            result = self.engine.play(board, chess.engine.Limit(time=move_time))

        return {
            "evaluation": evaluation,
            "suggestion": result.move if result and result.move else None,
        }

    def suggest_promotion_choice(
        self, fen: str, from_sq: int, to_sq: int, move_time: float = 0.18
    ):
        board = chess.Board(fen)
        if not self.engine:
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

        with self._engine_lock:
            result = self.engine.play(
                board,
                chess.engine.Limit(time=move_time),
                root_moves=promotion_moves,
            )
        return result.move if result and result.move else None

    def execute_move(self, from_sq, to_sq, promotion=None):
        with self._board_lock:
            move = chess.Move(from_sq, to_sq, promotion=promotion)
            if move in self.board.legal_moves:
                captured_piece = self.board.piece_at(to_sq)
                if captured_piece is None and self.board.is_en_passant(move):
                    capture_rank = chess.square_rank(to_sq) - (1 if self.board.turn == chess.WHITE else -1)
                    capture_square = chess.square(chess.square_file(to_sq), capture_rank)
                    captured_piece = self.board.piece_at(capture_square)

                self.move_history.append(MoveRecord(self.board.turn, self.board.san(move)))
                if captured_piece is None:
                    self.capture_history.append(None)
                else:
                    color_key = "w" if captured_piece.color == chess.WHITE else "b"
                    self.capture_history.append(f"{color_key}{captured_piece.symbol().upper()}")
                self.board.push(move)
                self.active_suggestion = None
                return True
            return False

    def get_numeric_eval(self):
        return self.evaluate_board() / 100.0

    def quit(self):
        if self.engine:
            with self._engine_lock:
                try:
                    self.engine.quit()
                except chess.engine.EngineTerminatedError:
                    pass
                finally:
                    self.engine = None
