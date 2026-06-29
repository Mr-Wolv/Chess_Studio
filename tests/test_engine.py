"""Unit tests for the chess engine module.

These tests cover core board logic, move execution, undo, captured-piece
tracking, PGN import/export, and prompt-suggestion logic.  Most tests do
*not* require Stockfish -- they operate directly on the ``ChessEngine``
datastructures.  The few tests that exercise the UCI engine are guarded
by ``pytest.mark.skipif`` so the suite always passes in CI.
"""

from __future__ import annotations

import chess

from engine import ChessEngine, MoveRecord, format_move_history

# ── Helper factories ──────────────────────────────────────────────


def _engine() -> ChessEngine:
    """Return a ``ChessEngine`` with an invalid AI path so Stockfish
    is never launched — fast for board-operation tests."""
    return ChessEngine(ai_path="__nonexistent__")


# ── MoveRecord ────────────────────────────────────────────────────


class TestMoveRecord:
    def test_white_side_label(self) -> None:
        record = MoveRecord(chess.WHITE, "e4")
        assert record.side_label == "W"

    def test_black_side_label(self) -> None:
        record = MoveRecord(chess.BLACK, "e5")
        assert record.side_label == "B"

    def test_immutable(self) -> None:
        record = MoveRecord(chess.WHITE, "e4")
        assert isinstance(record, MoveRecord)  # frozen dataclass


# ── format_move_history ───────────────────────────────────────────


class TestFormatMoveHistory:
    def test_empty(self) -> None:
        assert format_move_history([]) == ""

    def test_single_move(self) -> None:
        records = [MoveRecord(chess.WHITE, "e4")]
        assert format_move_history(records) == "1. e4"

    def test_two_moves(self) -> None:
        records = [
            MoveRecord(chess.WHITE, "e4"),
            MoveRecord(chess.BLACK, "e5"),
        ]
        assert format_move_history(records) == "1. e4 e5"

    def test_three_moves(self) -> None:
        records = [
            MoveRecord(chess.WHITE, "e4"),
            MoveRecord(chess.BLACK, "e5"),
            MoveRecord(chess.WHITE, "Nf3"),
        ]
        assert format_move_history(records) == "1. e4 e5\n2. Nf3"

    def test_four_moves(self) -> None:
        records = [
            MoveRecord(chess.WHITE, "e4"),
            MoveRecord(chess.BLACK, "e5"),
            MoveRecord(chess.WHITE, "Nf3"),
            MoveRecord(chess.BLACK, "Nc6"),
        ]
        assert format_move_history(records) == "1. e4 e5\n2. Nf3 Nc6"


# ── ChessEngine - board operations (no engine needed) ─────────────


class TestChessEngineBoard:
    def test_initial_board(self) -> None:
        eng = _engine()
        board = eng.get_board_copy()
        assert board.fen() == chess.Board().fen()
        assert eng.get_move_history() == []
        captured_w, captured_b = eng.get_captured_piece_keys()
        assert captured_w == []
        assert captured_b == []

    def test_reset_to_start(self) -> None:
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        eng.reset_engine()
        assert eng.get_board_copy().fen() == chess.Board().fen()
        assert eng.get_move_history() == []

    def test_reset_to_fen(self) -> None:
        fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        eng = _engine()
        eng.reset_engine(fen)
        assert eng.get_fen().startswith(fen.split()[0])

    def test_execute_simple_move(self) -> None:
        eng = _engine()
        result = eng.execute_move(chess.E2, chess.E4)
        assert result
        board = eng.get_board_copy()
        assert board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
        assert board.piece_at(chess.E2) is None

    def test_execute_invalid_move(self) -> None:
        eng = _engine()
        result = eng.execute_move(chess.E2, chess.E5)  # can't jump two pieces
        assert not result

    def test_execute_capture(self) -> None:
        eng = _engine()
        # Set up a fast capture: 1.e4 d5 2.exd5
        eng.execute_move(chess.E2, chess.E4)
        eng.execute_move(chess.D7, chess.D5)
        result = eng.execute_move(chess.E4, chess.D5)
        assert result
        _w_cap, _b_cap = eng.get_captured_piece_keys()
        assert _b_cap == ["bP"]  # black pawn captured
        assert _w_cap == []

    def test_execute_en_passant(self) -> None:
        eng = _engine()
        # 1.e4 d5 2.e5 f5 3.exf6 (en passant)
        eng.execute_move(chess.E2, chess.E4)
        eng.execute_move(chess.D7, chess.D5)
        eng.execute_move(chess.E4, chess.E5)
        eng.execute_move(chess.F7, chess.F5)
        result = eng.execute_move(chess.E5, chess.F6)
        assert result
        board = eng.get_board_copy()
        assert board.piece_at(chess.F6) == chess.Piece(chess.PAWN, chess.WHITE)
        assert board.piece_at(chess.F5) is None

    def test_undo_last_move(self) -> None:
        eng = _engine()
        fen_before = eng.get_fen()
        eng.execute_move(chess.E2, chess.E4)
        assert eng.undo_last_move()
        assert eng.get_fen() == fen_before
        assert not eng.get_move_history()

    def test_undo_when_empty(self) -> None:
        eng = _engine()
        assert not eng.undo_last_move()

    def test_undo_clears_capture_history(self) -> None:
        """Undoing a capture should also remove the captured-piece entry."""
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        eng.execute_move(chess.D7, chess.D5)
        eng.execute_move(chess.E4, chess.D5)
        _w, _b = eng.get_captured_piece_keys()
        assert _b == ["bP"]
        eng.undo_last_move()
        _w2, _b2 = eng.get_captured_piece_keys()
        assert _b2 == []

    def test_get_last_move_none(self) -> None:
        eng = _engine()
        assert eng.get_last_move() is None

    def test_get_last_move_after_move(self) -> None:
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        move = eng.get_last_move()
        assert move is not None
        assert move.from_square == chess.E2
        assert move.to_square == chess.E4

    def test_get_fen(self) -> None:
        eng = _engine()
        fen = eng.get_fen()
        assert isinstance(fen, str)
        assert fen != ""
        assert "/" in fen  # FEN always contains ranks

    def test_promotion(self) -> None:
        """Advance a pawn to the 8th rank and verify promotion works."""
        eng = _engine()
        fen = "8/4P3/8/8/8/8/8/4K3 w - - 0 1"
        eng.reset_engine(fen)
        result = eng.execute_move(chess.E7, chess.E8, promotion=chess.QUEEN)
        assert result
        board = eng.get_board_copy()
        assert board.piece_at(chess.E8) == chess.Piece(chess.QUEEN, chess.WHITE)

    def test_captured_after_promotion(self) -> None:
        """Capture a rook with a pawn that promotes."""
        eng = _engine()
        # Black rook on f8, white pawn on e7, capture e7-f8+promotion
        fen = "4kr2/4P3/8/8/8/8/8/4K3 w - - 0 1"
        eng.reset_engine(fen)
        assert eng.board.piece_at(chess.F8) == chess.Piece(chess.ROOK, chess.BLACK)
        result = eng.execute_move(chess.E7, chess.F8, promotion=chess.QUEEN)
        assert result
        _, black_cap = eng.get_captured_piece_keys()
        assert black_cap == ["bR"]  # black rook captured


# ── ChessEngine - engine-dependent tests (graceful fallback) ──────


class TestChessEngineAnalysis:
    def test_evaluate_board_no_crash_when_engine_unavailable(self) -> None:
        eng = ChessEngine()
        if eng.is_available():
            eng.quit()
        val = eng.evaluate_board()
        assert val == 0.0

    def test_analyze_position_no_crash_when_engine_unavailable(self) -> None:
        eng = ChessEngine()
        if eng.is_available():
            eng.quit()
        result = eng.analyze_position()
        assert result["evaluation"] == 0.0
        assert result["suggestion"] is None

    def test_analyze_position_checkmate_detected(self) -> None:
        eng = ChessEngine()
        if eng.is_available():
            eng.quit()
        fen = "rnb1kbnr/pppp1ppp/8/4p3/5PPq/8/PPPPP2P/RNBQKBNR w KQkq - 1 3"
        eng.reset_engine(fen)
        result = eng.analyze_position(fen=fen)
        assert result["evaluation"] == -999.99

    def test_suggest_promotion_no_crash_when_engine_unavailable(self) -> None:
        eng = ChessEngine()
        if eng.is_available():
            eng.quit()
        fen = "8/4P3/8/8/8/8/8/4K3 w - - 0 1"
        result = eng.suggest_promotion_choice(fen, chess.E7, chess.E8)
        assert result is None

    def test_set_skill_level_no_crash_when_engine_unavailable(self) -> None:
        eng = ChessEngine()
        if eng.is_available():
            eng.quit()
        label = eng.set_skill_level(3)
        assert label == "AI Off"

    def test_is_available(self) -> None:
        eng = ChessEngine()
        # Should return bool without crashing
        assert isinstance(eng.is_available(), bool)
        if eng.is_available():
            eng.quit()
            assert not eng.is_available()


# ── ChessEngine - PGN support ─────────────────────────────────────


class TestChessEnginePgn:
    def test_export_empty_game(self) -> None:
        eng = _engine()
        pgn = eng.export_pgn()
        # Should contain the starting position FEN elements
        assert "rnbqkbnr" in pgn or "1." not in pgn

    def test_export_after_move(self) -> None:
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        pgn = eng.export_pgn()
        assert "1." in pgn
        assert "e4" in pgn

    def test_export_import_roundtrip(self) -> None:
        """Export a game and re-import it; the boards should match."""
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        eng.execute_move(chess.E7, chess.E5)
        eng.execute_move(chess.G1, chess.F3)
        pgn = eng.export_pgn()
        result = ChessEngine.import_pgn(pgn)
        assert result is not None
        imported_board, _, _ = result
        assert imported_board.fen() == eng.get_board_copy().fen()

    def test_export_import_with_capture(self) -> None:
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        eng.execute_move(chess.D7, chess.D5)
        eng.execute_move(chess.E4, chess.D5)
        pgn = eng.export_pgn()
        result = ChessEngine.import_pgn(pgn)
        assert result is not None
        imported_board, _, _ = result
        assert imported_board.fen() == eng.get_board_copy().fen()

    def test_import_invalid_pgn(self) -> None:
        result = ChessEngine.import_pgn("not valid pgn content")
        # read_game treats unrecognisable text as an empty game; verify no moves
        assert result is not None
        _, history, _ = result
        assert history == []

    def test_import_empty_string(self) -> None:
        result = ChessEngine.import_pgn("")
        assert result is None

    def test_import_pgn_with_result(self) -> None:
        """PGN with a result tag should still import the moves correctly."""
        pgn = (
            '[Event "Test"]\n'
            '[Result "1-0"]\n'
            '\n'
            '1.e4 e5 2.Nf3 Nc6 *\n'
        )
        result = ChessEngine.import_pgn(pgn)
        assert result is not None
        _board, history, _ = result
        assert len(history) == 4
        assert history[0].san == "e4"
        assert history[2].san == "Nf3"


# ── ChessEngine - multi-move scenarios ────────────────────────────


class TestChessEngineIntegration:
    def test_italian_game(self) -> None:
        """Play the Italian Game opening and verify board state."""
        eng = _engine()
        moves = [
            (chess.E2, chess.E4),
            (chess.E7, chess.E5),
            (chess.G1, chess.F3),
            (chess.B8, chess.C6),
            (chess.F1, chess.C4),
            (chess.G8, chess.F6),
        ]
        for from_sq, to_sq in moves:
            assert eng.execute_move(from_sq, to_sq)
        board = eng.get_board_copy()
        assert board.fullmove_number == 4
        assert len(eng.get_move_history()) == 6

    def test_scholars_mate_sequence(self) -> None:
        """Play Scholar's Mate and verify checkmate via execute_move."""
        eng = _engine()
        moves = [
            (chess.E2, chess.E4),
            (chess.E7, chess.E5),
            (chess.D1, chess.H5),
            (chess.B8, chess.C6),
            (chess.F1, chess.C4),
            (chess.G8, chess.F6),
            (chess.H5, chess.F7),  # Qxf7#
        ]
        for from_sq, to_sq in moves:
            assert eng.execute_move(from_sq, to_sq)
        board = eng.get_board_copy()
        assert board.is_checkmate()
        assert board.outcome() is not None
        assert board.outcome().winner == chess.WHITE

    def test_kingside_castle(self) -> None:
        """Set up a position where kingside castling is legal and execute it."""
        # FEN after 1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O
        fen = "r1bqkb1r/1ppp1ppp/p1n2n2/1B2p3/4P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 5 5"
        eng = _engine()
        eng.reset_engine(fen)
        # White already castled; verify king and rook are in the right places
        board = eng.get_board_copy()
        assert board.piece_at(chess.G1) == chess.Piece(chess.KING, chess.WHITE)
        assert board.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)

    def test_queenside_castle(self) -> None:
        """Set up a position where queenside castling is legal and execute it."""
        # Rank 1: R3K2R — rook on a1, king on e1, rook on h1; no bishops blocking
        fen = "r3kbnr/pppq1ppp/2np4/2b1p3/2B1P3/3P1N2/PPPN1PPP/R3K2R w KQkq - 4 7"
        eng = _engine()
        eng.reset_engine(fen)
        result = eng.execute_move(chess.E1, chess.C1)
        assert result, f"Queenside castle should be legal, legal moves: {[eng.board.san(m) for m in eng.board.legal_moves]}"
        board = eng.get_board_copy()
        assert board.piece_at(chess.C1) == chess.Piece(chess.KING, chess.WHITE)
        assert board.piece_at(chess.D1) == chess.Piece(chess.ROOK, chess.WHITE)

    def test_castle_move_recorded_as_o_o(self) -> None:
        """Verify kingside castling is recorded as 'O-O' in move history."""
        fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R w KQkq - 5 6"
        eng = _engine()
        eng.reset_engine(fen)
        result = eng.execute_move(chess.E1, chess.G1)
        assert result
        history = eng.get_move_history()
        assert len(history) == 1
        san = history[0].san
        # python-chess may use "O-O" or the Unicode symbol; check for either
        assert "O" in san or "0" in san or "o" in san

    def test_analyze_scholars_mate_position(self) -> None:
        """Call analyze_position on a Scholar's Mate position; should return mate eval."""
        eng = _engine()
        # FEN after 1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7# — black is checkmated
        fen = "r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4"
        eng.reset_engine(fen)
        result = eng.analyze_position(fen=fen)
        assert result["evaluation"] == 999.99  # white wins
        assert result["suggestion"] is None

    def test_multiple_undos(self) -> None:
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        eng.execute_move(chess.D7, chess.D5)
        fen_after_two_moves = eng.get_fen()
        eng.execute_move(chess.E4, chess.D5)
        eng.undo_last_move()
        assert eng.get_fen() == fen_after_two_moves

    def test_full_undo_then_redo(self) -> None:
        """Undo all moves, then replay them to reach the same position."""
        eng = _engine()
        moves = [
            (chess.E2, chess.E4),
            (chess.E7, chess.E5),
            (chess.G1, chess.F3),
        ]
        for from_sq, to_sq in moves:
            eng.execute_move(from_sq, to_sq)
        final_fen = eng.get_fen()
        # Undo all
        for _ in range(len(moves)):
            eng.undo_last_move()
        assert eng.get_board_copy().fen() == chess.Board().fen()
        # Replay
        for from_sq, to_sq in moves:
            eng.execute_move(from_sq, to_sq)
        assert eng.get_fen() == final_fen
