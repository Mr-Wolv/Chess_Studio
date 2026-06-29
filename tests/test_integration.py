"""Integration tests for Chess Studio — headless pygame smoke tests.

These tests verify that the controller initialises, runs a few frames,
and shuts down cleanly without crashing.  They use a dummy video driver
so no display is required.
"""

from __future__ import annotations

import os
import sys

import pytest

# ── Skip entire module on non-Windows ─────────────────────────────
# The dummy SDL video driver works best on Windows. On Linux/macOS we
# skip since pygame may still try to open a display.

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and "CI" not in os.environ,
    reason="Headless pygame tests are validated on Windows CI",
)


@pytest.fixture(autouse=True)
def _patch_display():
    """Set SDL to a dummy driver so pygame can initialise without a monitor."""
    old_env = os.environ.get("SDL_VIDEODRIVER")
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    # Also suppress audio to avoid mixer warnings
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    yield
    if old_env is None:
        os.environ.pop("SDL_VIDEODRIVER", None)
    else:
        os.environ["SDL_VIDEODRIVER"] = old_env
    os.environ.pop("SDL_AUDIODRIVER", None)


# ── Smoke test: controller lifecycle ──────────────────────────────


def test_controller_initialises_and_shuts_down() -> None:
    """Controller runs for a limited number of frames and exits cleanly."""
    # Import here so the dummy env var is set first
    from main import ChessController

    # Run 3 frames then exit
    ctrl = ChessController()
    ctrl.run(max_frames=3)
    # If we got here without exception, the test passes
    assert True


def test_controller_plays_move_and_undo() -> None:
    """Simulate a move and undo via the controller."""
    import chess

    from main import ChessController

    ctrl = ChessController()
    # Execute a move programmatically
    assert ctrl.engine.execute_move(chess.E2, chess.E4)
    ctrl.run(max_frames=3)
    assert len(ctrl.engine.get_move_history()) == 1

    # Undo
    ctrl.engine.undo_last_move()
    assert len(ctrl.engine.get_move_history()) == 0

    ctrl.shutdown()


def test_controller_ai_mode_toggle() -> None:
    """Toggling AI mode should not crash."""
    from main import ChessController

    ctrl = ChessController()
    ctrl._toggle_ai_mode()
    ctrl.run(max_frames=2)
    assert ctrl.play_vs_ai is True

    ctrl._toggle_ai_mode()
    ctrl.run(max_frames=2)
    assert ctrl.play_vs_ai is False

    ctrl.shutdown()


def test_controller_flip_board() -> None:
    """Flipping board orientation should not crash."""
    from main import ChessController

    ctrl = ChessController()
    assert ctrl.orientation_white_bottom is True

    ctrl._flip_board()
    ctrl.run(max_frames=2)
    assert ctrl.orientation_white_bottom is False

    ctrl.shutdown()


def test_controller_cycle_board_theme() -> None:
    """Cycling board themes should not crash."""
    from main import ChessController

    ctrl = ChessController()
    index_before = ctrl.board_theme_index
    ctrl._cycle_board_theme()
    ctrl.run(max_frames=2)
    assert ctrl.board_theme_index == (index_before + 1) % len(ctrl.BOARD_THEMES)

    ctrl.shutdown()


def test_controller_clock_toggle() -> None:
    """Toggling the chess clock should not crash."""
    from main import ChessController

    ctrl = ChessController()
    assert ctrl.clock_active is False

    ctrl._toggle_clock()
    ctrl.run(max_frames=2)
    assert ctrl.clock_active is True  # clock should become active

    ctrl.shutdown()


# ── Integration: ViewState is built without error ─────────────────


def test_build_view_state_smoke() -> None:
    """_build_view_state should return a complete ViewState without error."""
    from main import ChessController
    from ui_comp import ViewState

    ctrl = ChessController()
    vs = ctrl._build_view_state()
    assert isinstance(vs, ViewState)
    assert vs.fen != ""
    assert vs.opening_continuations is not None
    assert isinstance(vs.num_legal_moves, int) and vs.num_legal_moves > 0
    ctrl.shutdown()


# ── Integration: key handlers ─────────────────────────────────────


def test_key_handlers_dispatch() -> None:
    """All key handlers should dispatch without raising."""
    import pygame

    from main import ChessController

    ctrl = ChessController()
    # Skip keys that require Stockfish (E, M) or mixer (S)
    skip_keys = {pygame.K_m, pygame.K_s, pygame.K_e}
    for key, handler in ctrl._key_handlers.items():
        if key in skip_keys:
            continue
        handler()
    ctrl.shutdown()


# ── Unit tests for refactored utilities ──────────────────────────


class TestClockUtils:
    def test_format_clock_text_empty_when_inactive(self) -> None:
        from clock_utils import format_clock_text

        result = format_clock_text(
            600.0, 600.0, "W",
            clock_active=False,
            clock_initial=600.0,
        )
        assert result == "", f"Expected empty string, got {result!r}"

    def test_format_clock_text_active(self) -> None:
        from clock_utils import format_clock_text

        result = format_clock_text(
            599.0, 600.0, "W",
            clock_active=True,
        )
        assert "09:59" in result
        assert "10:00" in result
        assert "[W]" in result

    def test_format_clock_text_paused(self) -> None:
        from clock_utils import format_clock_text

        result = format_clock_text(
            600.0, 600.0, "W",
            clock_active=False,
            clock_initial=600.0,
        )
        assert result == ""

    def test_format_time(self) -> None:
        from clock_utils import format_time

        assert format_time(65.0) == "01:05"
        assert format_time(3600.0) == "60:00"
        assert format_time(0.0) == "00:00"

    def test_format_time_negative(self) -> None:
        """Edge case: negative seconds shows negative minutes."""
        from clock_utils import format_time

        result = format_time(-5.0)
        # Python floor div: -5 // 60 = -1, remainder 55 → "-1:55" (02d doesn't pad after minus)
        assert result == "-1:55", f"Expected '-1:55', got {result!r}"

    def test_compute_clock_anim_progress(self) -> None:
        from clock_utils import compute_clock_anim_progress

        # No animation
        assert compute_clock_anim_progress(0.0, 0.0, 1.0) == 1.0
        # Partial
        p = compute_clock_anim_progress(0.0, 1.0, 0.5)
        assert 0.49 < p < 0.51
        # Complete
        assert compute_clock_anim_progress(0.0, 1.0, 2.0) == 1.0

    def test_compute_anim_zero_duration(self) -> None:
        """Edge case: zero duration should return 1.0 immediately."""
        from clock_utils import compute_clock_anim_progress

        assert compute_clock_anim_progress(0.0, 0.0, 5.0) == 1.0
        assert compute_clock_anim_progress(10.0, 0.0, 20.0) == 1.0

    def test_compute_anim_negative_duration(self) -> None:
        """Edge case: negative duration should return 1.0."""
        from clock_utils import compute_clock_anim_progress

        assert compute_clock_anim_progress(0.0, -1.0, 5.0) == 1.0

    def test_compute_anim_now_before_start(self) -> None:
        """Edge case: 'now' before start time should return 1.0."""
        from clock_utils import compute_clock_anim_progress

        assert compute_clock_anim_progress(10.0, 1.0, 5.0) == 1.0

    def test_is_clock_low(self) -> None:
        from clock_utils import is_clock_low

        assert is_clock_low(5.0) is True
        assert is_clock_low(15.0) is False
        assert is_clock_low(10.0, threshold=10.0) is True
        assert is_clock_low(10.01, threshold=10.0) is False

    def test_is_clock_low_negative(self) -> None:
        """Edge case: negative clock seconds (flag fallen) is always low."""
        from clock_utils import is_clock_low

        assert is_clock_low(-1.0) is True
        assert is_clock_low(-100.0) is True

    def test_is_clock_low_zero_threshold(self) -> None:
        """Edge case: threshold of 0 means only exactly 0 is low."""
        from clock_utils import is_clock_low

        assert is_clock_low(0.0, threshold=0.0) is True
        assert is_clock_low(0.001, threshold=0.0) is False

    def test_format_clock_text_none_initial(self) -> None:
        """Edge case: clock_initial=None should never return empty."""
        from clock_utils import format_clock_text

        result = format_clock_text(
            600.0, 600.0, "W",
            clock_active=False,
            clock_initial=None,
        )
        # With None initial and inactive, it should still show paused state
        assert "10:00" in result

    def test_format_clock_text_negative_times(self) -> None:
        """Edge case: both clocks negative (time ran out)."""
        from clock_utils import format_clock_text

        result = format_clock_text(
            -5.0, -3.0, "B",
            clock_active=True,
        )
        assert "[B]" in result
        assert isinstance(result, str)


class TestPgnUtils:
    def test_auto_save_creates_file_in_games_dir(self, tmp_path) -> None:
        import os

        from pgn_utils import auto_save_pgn

        old_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            pgn = '1. e4 e5 *\n'
            name = auto_save_pgn(pgn)
            assert name is not None
            assert name.endswith(".pgn")
            games_dir = tmp_path / "games"
            assert (games_dir / name).exists()
        finally:
            os.chdir(old_cwd)

    def test_auto_save_returns_none_for_empty_pgn(self) -> None:
        from pgn_utils import auto_save_pgn

        assert auto_save_pgn("") is None
        assert auto_save_pgn("   ") is None


class TestOpeningContinuations:
    def test_initial_position(self) -> None:
        from openings import get_opening_continuations

        conts = get_opening_continuations([])
        assert len(conts) > 0, "Should have continuations from start position"
        # First continuation should be 1.e4 (King's Pawn) or similar
        first_san = conts[0][0]
        assert first_san in ("e4", "d4", "c4", "Nf3", "g3", "f4", "b3", "Nc3", "e3", "d3"), f"Unexpected first continuation: {first_san}"

    def test_after_e4(self) -> None:
        import chess

        from engine import MoveRecord
        from openings import get_opening_continuations

        conts = get_opening_continuations([
            MoveRecord(chess.WHITE, "e4"),
        ])
        assert len(conts) >= 3, f"Should have continuations after 1.e4, got {conts}"
        sans = [c[0] for c in conts]
        # Tree is ordered by ECO code (A00→B00→C00→D00→E00), so 1...e5 (C20)
        # may not appear before B00 defences like d5 (B01) or Nf6 (B02).
        # Check that we get known first moves: d5 (Scandinavian), Nf6 (Alekhine),
        # c5 (Sicilian), c6 (Caro-Kann), e6 (French), g6 (Modern), d6 (Pirc), e5 (King's Pawn)
        expected = {"d5", "Nf6", "c5", "c6", "e6", "g6", "d6", "e5"}
        assert len(set(sans) & expected) >= 3, f"Expected at least 3 known continuations from {expected}, got {sans}"

    def test_after_e4_e5(self) -> None:
        import chess

        from engine import MoveRecord
        from openings import get_opening_continuations

        conts = get_opening_continuations([
            MoveRecord(chess.WHITE, "e4"),
            MoveRecord(chess.BLACK, "e5"),
        ])
        assert len(conts) >= 3, f"Should have continuations after 1.e4 e5, got {conts}"
        sans = [c[0] for c in conts]
        # After 1.e4 e5, known continuations (sorted by ECO): d4 (C21), Bc4 (C23),
        # Nc3 (C25), f4 (C30), Nf3 (C40), etc.
        expected = {"d4", "Bc4", "Nc3", "f4", "Nf3", "Qh5", "c3"}
        assert len(set(sans) & expected) >= 3, f"Expected known continuations from {expected}, got {sans}"

    def test_empty_after_nonsense(self) -> None:
        import chess

        from engine import MoveRecord
        from openings import get_opening_continuations

        conts = get_opening_continuations([
            MoveRecord(chess.WHITE, "a4"),  # Not in opening tree
        ])
        assert conts == [], f"Nonsense move should give empty continuations, got {conts}"

    def test_detect_opening_initial(self) -> None:
        from openings import detect_opening

        eco, name = detect_opening([])
        assert eco == "A00" or eco == "?"
        assert isinstance(name, str)
