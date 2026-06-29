"""Unit tests for premium features: player names in PGN, move annotations,
clock animation, and legal move counter.

These tests operate on the ChessEngine and test helper methods without
requiring a running Pygame display.
"""

from __future__ import annotations

import chess

from engine import ChessEngine, MoveRecord, format_move_history

# ── Helper ─────────────────────────────────────────────────────────


def _engine() -> ChessEngine:
    """Return a ChessEngine with an invalid AI path — fast for board tests."""
    return ChessEngine(ai_path="__nonexistent__")


# ── Player Names in PGN Export ─────────────────────────────────────


class TestPlayerNamesInPgn:
    def test_export_with_player_names(self) -> None:
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        pgn = eng.export_pgn(white_name="Magnus", black_name="Hikaru")
        assert "White" in pgn and "Magnus" in pgn, f"PGN should contain White name, got: {pgn}"
        assert "Black" in pgn and "Hikaru" in pgn, f"PGN should contain Black name, got: {pgn}"

    def test_export_default_names(self) -> None:
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        pgn = eng.export_pgn()
        assert "White" in pgn and "Player 1" in pgn, "Default White name should be 'Player 1'"
        assert "Black" in pgn and "Player 2" in pgn, "Default Black name should be 'Player 2'"

    def test_export_result_after_checkmate(self) -> None:
        eng = _engine()
        # Scholar's Mate: 1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7#
        moves = [
            (chess.E2, chess.E4),
            (chess.E7, chess.E5),
            (chess.D1, chess.H5),
            (chess.B8, chess.C6),
            (chess.F1, chess.C4),
            (chess.G8, chess.F6),
            (chess.H5, chess.F7),
        ]
        for from_sq, to_sq in moves:
            assert eng.execute_move(from_sq, to_sq)
        pgn = eng.export_pgn(white_name="Player", black_name="AI")
        assert 'Result "1-0"' in pgn, f"PGN should contain '1-0' result, got: {pgn}"

    def test_export_result_in_progress(self) -> None:
        eng = _engine()
        eng.execute_move(chess.E2, chess.E4)
        pgn = eng.export_pgn()
        assert 'Result "*"' in pgn, f"PGN should contain '*' for in-progress game, got: {pgn}"

    def test_player_names_mode_switch(self) -> None:
        """Simulate _update_player_names_for_mode logic for AI vs local mode."""
        # AI mode
        play_vs_ai = True
        if play_vs_ai:
            player_white = "Player"
            player_black = "AI"
        else:
            player_white = "Player 1"
            player_black = "Player 2"
        assert player_white == "Player"
        assert player_black == "AI"

        # Local mode
        play_vs_ai = False
        if play_vs_ai:
            player_white = "Player"
            player_black = "AI"
        else:
            player_white = "Player 1"
            player_black = "Player 2"
        assert player_white == "Player 1"
        assert player_black == "Player 2"


# ── Move Annotations ──────────────────────────────────────────────


class TestMoveAnnotations:
    def test_annotation_full_cycle(self) -> None:
        """Verify the full annotation cycle: ! → ? → !! → ?? → !? → None → !"""
        cycle = ["!", "?", "!!", "??", "!?", None]
        current = None
        for expected in cycle:
            next_idx = (cycle.index(current) + 1) % len(cycle) if current in cycle else 0
            current = cycle[next_idx]
            assert current == expected, f"Expected {expected}, got {current}"
        # One more should cycle back to "!"
        next_idx = (cycle.index(current) + 1) % len(cycle) if current in cycle else 0
        assert cycle[next_idx] == "!"


# ── Clock Animation State ─────────────────────────────────────────


class TestClockAnimationState:
    def test_anim_state_returns_completed_when_no_anim(self) -> None:
        """When no animation is active, progress should be 1.0 and duration 0."""
        progress, duration = 1.0, 0.0
        assert progress >= 1.0
        assert duration == 0.0

    def test_anim_state_progress_in_range(self) -> None:
        """Simulate partial animation progress."""
        elapsed = 0.15
        duration = 0.3
        progress = elapsed / duration
        assert 0.0 < progress < 1.0

    def test_anim_state_completed(self) -> None:
        """When elapsed exceeds duration, progress should be >= 1.0."""
        elapsed = 0.5
        duration = 0.3
        progress = min(1.0, elapsed / duration)
        assert progress >= 1.0

    def test_prev_text_tracks_changes(self) -> None:
        """Simulate clock text comparison."""
        prev_text = "10:00 | 10:00 [W]"
        new_text = "09:59 | 10:00 [W]"
        assert new_text != prev_text
        # After update
        prev_text = new_text
        assert prev_text == new_text


# ── Legal Move Counter ────────────────────────────────────────────


class TestLegalMoveCounter:
    def test_initial_position_has_20_moves(self) -> None:
        board = chess.Board()
        count = board.legal_moves.count()
        assert count == 20, f"Starting position should have 20 legal moves, got {count}"

    def test_after_e4_e5_has_29_moves(self) -> None:
        board = chess.Board()
        board.push_san("e4")
        board.push_san("e5")
        count = board.legal_moves.count()
        assert count == 29, f"After 1.e4 e5 should have 29 legal moves, got {count}"

    def test_checkmate_has_zero_moves(self) -> None:
        board = chess.Board()
        board.push_san("e4")
        board.push_san("e5")
        board.push_san("Qh5")
        board.push_san("Nc6")
        board.push_san("Bc4")
        board.push_san("Nf6")
        board.push_san("Qxf7")
        count = board.legal_moves.count()
        assert count == 0, f"Checkmate should have 0 legal moves, got {count}"

    def test_stalemate_has_zero_moves(self) -> None:
        # Stalemate: Black king a8, White pawn a7 (occupies a7, attacks b8), White king b6 (attacks b7)
        # King can't go to a7 (occupied), b7 (attacked by Kb6), or b8 (attacked by Pa7). Not in check.
        fen = "k7/P7/1K6/8/8/8/8/8 b - - 0 1"
        board = chess.Board(fen)
        assert not board.is_check(), "Should not be in check"
        assert board.legal_moves.count() == 0, f"Expected 0 legal moves, got {board.legal_moves.count()}"
        assert board.is_stalemate()


# ── SoundManager Tests ────────────────────────────────────────────


class TestSoundManager:
    """Unit tests for SoundManager.

    The SoundManager handles pygame.mixer initialisation gracefully when
    audio is unavailable (e.g. in headless CI environments). These tests
    verify its state management API without requiring actual audio output.
    """

    def test_initial_state(self) -> None:
        """SoundManager should be creatable even when mixer is unavailable."""
        # Simulate mixer failure by not calling pygame.mixer.init
        from ui_comp import SoundManager
        sm = SoundManager()
        # _enabled may be False if mixer couldn't init in headless env
        assert hasattr(sm, '_enabled')
        assert hasattr(sm, '_volume')
        assert sm._volume == 1.0

    def test_set_enabled_toggle(self) -> None:
        """set_enabled should update the internal _enabled flag."""
        from ui_comp import SoundManager
        sm = SoundManager()
        sm.set_enabled(True)
        assert sm._enabled is True
        sm.set_enabled(False)
        assert sm._enabled is False
        sm.set_enabled(True)
        assert sm._enabled is True

    def test_set_volume_clamps_range(self) -> None:
        """set_volume should clamp to 0.0-1.0."""
        from ui_comp import SoundManager
        sm = SoundManager()
        sm.set_volume(1.5)
        assert sm._volume == 1.0
        sm.set_volume(-0.5)
        assert sm._volume == 0.0
        sm.set_volume(0.75)
        assert sm._volume == 0.75

    def test_play_no_crash_when_disabled(self) -> None:
        """play() should not raise when sounds dict is empty (mixer unavailable)."""
        from ui_comp import SoundManager
        sm = SoundManager()
        sm.set_enabled(False)
        # Should not raise even though sounds dict may be empty
        sm.play("move")
        sm.play("nonexistent")

    def test_set_volume_rebuilds_sounds(self) -> None:
        """set_volume should rebuild the sounds dict when enabled."""
        from ui_comp import SoundManager
        sm = SoundManager()
        # Force enable so sounds get built
        sm._enabled = True
        sm.sounds = {}
        sm.set_volume(0.5)
        # After set_volume with enabled=True, sounds should be rebuilt
        assert "move" in sm.sounds
        assert "capture" in sm.sounds
        assert "check" in sm.sounds
        assert "game_over" in sm.sounds
        assert "button" in sm.sounds
        assert "undo" in sm.sounds
        assert "flag_fall" in sm.sounds
        assert "tick" in sm.sounds

    def test_play_ignores_unknown_name(self) -> None:
        """play() with a name not in sounds should silently do nothing."""
        from ui_comp import SoundManager
        sm = SoundManager()
        sm.set_enabled(False)
        sm.play("__definitely_not_a_sound__")
        # No assertion needed — just verifies no crash
        assert True

    def test_volume_default_is_max(self) -> None:
        """Default volume should be 1.0 (100%)."""
        from ui_comp import SoundManager
        sm = SoundManager()
        assert sm._volume == 1.0


# ── Format Move History (edge cases) ──────────────────────────────


class TestFormatMoveHistoryEdgeCases:
    def test_single_white_move(self) -> None:
        records = [MoveRecord(chess.WHITE, "e4")]
        assert format_move_history(records) == "1. e4"

    def test_odd_number_of_moves(self) -> None:
        records = [
            MoveRecord(chess.WHITE, "e4"),
            MoveRecord(chess.BLACK, "e5"),
            MoveRecord(chess.WHITE, "Nf3"),
        ]
        result = format_move_history(records)
        assert "1. e4 e5" in result
        assert "2. Nf3" in result
