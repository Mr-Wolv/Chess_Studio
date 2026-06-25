from __future__ import annotations

import threading
import time
from collections.abc import Callable

import chess
import pygame

from engine import AnalysisResult, ChessEngine, MoveRecord, format_move_history
from ui_comp import ChessView, SoundManager, ViewState

# ── Named Constants ──────────────────────────────────────────────

FLASH_DURATION = 2.2
"""Default duration in seconds for flash messages."""

ANALYSIS_LOOP_SLEEP = 0.06
"""Sleep between analysis-loop iterations in seconds."""

AI_MOVE_TIME = 0.7
"""Time in seconds for the AI to think about its move."""

SUGGESTION_MOVE_TIME = 0.45
"""Time in seconds for the engine to suggest a move."""

EVAL_TIME = 0.08
"""Time in seconds per quick evaluation call."""

SLEEP_IDLE = 0.1
"""Sleep when no analysis work is needed."""

SLEEP_MATCH_OVER = 0.12
"""Sleep when the match is over."""

SLEEP_ENGINE_UNAVAILABLE = 0.25
"""Sleep when the engine is not available."""


class ChessController:
    AI_SIDE = chess.BLACK
    AI_UNAVAILABLE_TEXT = "AI is not loaded, so engine features are unavailable."

    def __init__(self) -> None:
        self.engine = ChessEngine()
        self.view = ChessView(assets_dir="assets")
        self.running = True
        self.orientation_white_bottom = True
        self.selected_square: int | None = None
        self.legal_targets: set[int] = set()
        self.dragging_square: int | None = None
        self.drag_position: tuple[int, int] | None = None
        self.pending_promotion: tuple[int, int] | None = None
        self.move_list_scroll = 0

        self.state_lock = threading.Lock()
        self.analysis_enabled = False
        self.analysis_eval = 0.0
        self.analysis_text = (
            "Move hints are off. Press A to show AI suggestions."
            if self.engine.is_available()
            else self.AI_UNAVAILABLE_TEXT
        )
        self.suggested_move: chess.Move | None = None
        self.pending_ai_move: tuple[str, chess.Move] | None = None
        self.promotion_suggestion: int | None = None
        self.analysis_dirty = True
        self.ai_thinking = False
        self.play_vs_ai = False
        self.match_result: dict[str, str] | None = None
        self.result_dialog_visible = False
        self.claim_dialog: dict[str, str] | None = None
        self.suppressed_claim_fen: str | None = None
        self.flash_message = "Board ready."
        self.flash_until = time.monotonic() + 1.8

        self.show_shortcuts = False
        self.sound_mgr = SoundManager()
        self.sound_enabled = True
        self.shift_promotion = False

        # AI difficulty
        self.ai_elo_index = 0  # Off (full strength)
        self.ai_elo_label = self._apply_ai_elo()

        # Chess clock — configurable time controls (user starts via P key)
        self.CLOCK_PRESETS: list[tuple[float, float, str]] = [
            (600.0, 5.0, "10+5"),
            (300.0, 0.0, "5+0"),
            (180.0, 2.0, "3+2"),
            (900.0, 10.0, "15+10"),
            (1200.0, 15.0, "20+15"),
        ]
        self._clock_preset_index = 0
        self.CLOCK_INITIAL, self.CLOCK_INCREMENT, _ = self.CLOCK_PRESETS[0]
        self.white_clock = self.CLOCK_INITIAL
        self.black_clock = self.CLOCK_INITIAL
        self.clock_active = False
        self.clock_last_tick = 0.0

        # Key dispatch table (built once to avoid repeated if/elif chains)
        self._key_handlers: dict[int, Callable[[], None]] = {}
        self._build_key_handlers()

        self.analysis_thread = threading.Thread(
            target=self._analysis_loop, name="analysis-worker", daemon=True
        )
        self.analysis_thread.start()

    def _build_key_handlers(self) -> None:
        """Populate the key dispatch table.

        Maps key codes directly to no-arg handler methods.
        Modifier-sensitive keys (C, O, P) are handled separately.
        """
        self._key_handlers = {
            pygame.K_r: self._new_game,
            pygame.K_u: self._undo_move,
            pygame.K_f: self._flip_board,
            pygame.K_m: self._toggle_ai_mode,
            pygame.K_h: self._toggle_shortcuts,
            pygame.K_s: self._toggle_sound,
            pygame.K_a: self._toggle_analysis,
            pygame.K_e: self._cycle_ai_elo,
            pygame.K_p: self._toggle_clock,
            pygame.K_t: self._cycle_time_control,
        }

    def _flip_board(self) -> None:
        self.orientation_white_bottom = not self.orientation_white_bottom
        self._flash("Board orientation flipped.")

    def _cycle_ai_elo(self) -> None:
        if not self.engine.is_available():
            self._flash("AI is not loaded, cannot change skill.")
            return
        self.ai_elo_index = (self.ai_elo_index + 1) % len(ChessEngine.ELO_PRESETS)
        label = self._apply_ai_elo()
        self._flash(f"AI strength: {label}")

    def _cycle_time_control(self) -> None:
        """Cycle through clock preset time controls."""
        self._clock_preset_index = (self._clock_preset_index + 1) % len(self.CLOCK_PRESETS)
        time_val, inc, label = self.CLOCK_PRESETS[self._clock_preset_index]
        self.CLOCK_INITIAL = time_val
        self.CLOCK_INCREMENT = inc
        # Reset clocks with new settings (keep running state)
        self.white_clock = self.CLOCK_INITIAL
        self.black_clock = self.CLOCK_INITIAL
        if self.clock_active:
            self.clock_last_tick = time.monotonic()
        self._flash(f"Time control: {label}")

    def _toggle_shortcuts(self) -> None:
        self.show_shortcuts = not self.show_shortcuts
        self._flash("Keyboard shortcuts (H to close)." if self.show_shortcuts else "Shortcuts closed.")

    def _toggle_sound(self) -> None:
        self.sound_enabled = not self.sound_enabled
        self.sound_mgr.set_enabled(self.sound_enabled)
        self._flash("Sound ON." if self.sound_enabled else "Sound OFF.")

    def _toggle_clock(self) -> None:
        """Start or pause the chess clock."""
        if self._match_is_over():
            self._flash("Cannot start clock — game is over.")
            return
        self.clock_active = not self.clock_active
        if self.clock_active:
            self.clock_last_tick = time.monotonic()
            self._flash("Clock started.")
        else:
            self._flash("Clock paused.")

    def _toggle_analysis(self) -> None:
        self.analysis_enabled = not self.analysis_enabled and self.engine.is_available()
        with self.state_lock:
            if not self.analysis_enabled:
                self.suggested_move = None
                self.promotion_suggestion = None
            if not self.engine.is_available():
                self.analysis_text = self.AI_UNAVAILABLE_TEXT
            else:
                self.analysis_text = (
                    "Move hints paused. Evaluation still updates in the background."
                    if not self.analysis_enabled
                    else "Move hints resumed. AI is reviewing the current position..."
                )
            self.analysis_dirty = True
        self._flash(
            "AI is not loaded."
            if not self.engine.is_available()
            else "Move hints paused."
            if not self.analysis_enabled
            else "Move hints resumed."
        )

    def _handle_escape(self) -> None:
        if self.show_shortcuts:
            self.show_shortcuts = False
            self._flash("Shortcuts closed.")
            return
        if self.pending_promotion:
            self.pending_promotion = None
            with self.state_lock:
                self.promotion_suggestion = None
                self.analysis_dirty = True
        else:
            self._clear_selection()

    def _clear_engine_suggestions_locked(self) -> None:
        self.suggested_move = None
        self.pending_ai_move = None
        self.ai_thinking = False
        self.promotion_suggestion = None

    def run(self, max_frames: int | None = None) -> None:
        frame_count = 0
        try:
            while self.running:
                for event in pygame.event.get():
                    self._handle_event(event)

                self._process_pending_ai_move()
                self._update_clocks()
                self.view.draw(self._build_view_state())
                self.view.tick(60)
                frame_count += 1

                if max_frames is not None and frame_count >= max_frames:
                    self.running = False
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self.running = False
        if self.analysis_thread.is_alive():
            self.analysis_thread.join(timeout=1.2)
        self.engine.quit()
        pygame.mixer.quit()
        pygame.quit()

    def _handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return

        if event.type == pygame.VIDEORESIZE:
            self.view.handle_resize(event.size)
            self._clamp_move_list_scroll()
            return

        if event.type == pygame.KEYDOWN:
            self._handle_keypress(event.key)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.pending_promotion:
            # Check for Shift+click to auto-queen
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self.shift_promotion = True
            self._handle_promotion_click(event.pos)
            self.shift_promotion = False
            return

        if event.type == pygame.MOUSEMOTION and self.dragging_square is not None:
            self.drag_position = event.pos
            return

        if event.type == pygame.MOUSEWHEEL:
            mouse_position = pygame.mouse.get_pos()
            if self.view.point_in_panel("moves", mouse_position):
                self._scroll_move_list(-event.y)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._dialog_is_visible():
                action = self.view.result_dialog_action_at(event.pos)
                if action:
                    self._handle_result_dialog_action(action)
                return

            button = self.view.button_at(event.pos)
            if button:
                self._handle_button(button)
                return

            if self.view.point_in_panel("moves", event.pos):
                return

            self._handle_board_press(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self.pending_promotion:
                self._handle_board_release(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._clear_selection()

    def _handle_keypress(self, key: int) -> None:
        # Dialog shortcuts (highest priority)
        if self._dialog_is_visible():
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                dialog = self._get_active_dialog()
                if dialog:
                    self._handle_result_dialog_action(dialog["primary_key"])
                return
            if key == pygame.K_ESCAPE:
                dialog = self._get_active_dialog()
                if dialog:
                    self._handle_result_dialog_action(dialog["secondary_key"])
                return

        # Escape — always handled (closes shortcuts, promotion, selection)
        if key == pygame.K_ESCAPE:
            self._handle_escape()
            return

        # Dispatch table for simple key -> handler mappings
        handler = self._key_handlers.get(key)
        if handler is not None:
            handler()
            return

        # Modifier-sensitive keys (C vs Ctrl+C, O vs Ctrl+O, P vs Ctrl+P)
        mods = pygame.key.get_mods()
        if key == pygame.K_c:
            if mods & pygame.KMOD_CTRL:
                self._copy_move_history()
            else:
                self._copy_fen()
            return
        if key == pygame.K_o and (mods & pygame.KMOD_CTRL):
            self._import_pgn()
            return
        if key == pygame.K_p and (mods & pygame.KMOD_CTRL):
            self._export_pgn()
            return

    def _handle_button(self, button_key: str) -> None:
        self.sound_mgr.play("button")
        if button_key == "new_game":
            self._new_game()
        elif button_key == "undo":
            self._undo_move()
        elif button_key == "flip_board":
            self.orientation_white_bottom = not self.orientation_white_bottom
            self._flash("Board orientation flipped.")
        elif button_key == "copy_fen":
            self._copy_fen()
        elif button_key == "mode_toggle":
            self._toggle_ai_mode()
        elif button_key == "clock_toggle":
            self._toggle_clock()

    def _handle_result_dialog_action(self, action_key: str) -> None:
        if action_key == "dialog_new_game":
            self._new_game()
        elif action_key == "dialog_review":
            self.result_dialog_visible = False
        elif action_key == "dialog_claim_draw":
            self._claim_draw()
        elif action_key == "dialog_continue":
            self._dismiss_claim_dialog()

    def _handle_board_press(self, position: tuple[int, int]) -> None:
        board = self.engine.get_board_copy()
        if self._match_is_over(board):
            self._clear_selection()
            self._flash("Game is finished. Start a new game or undo to continue.", duration=1.5)
            return

        if self._is_ai_turn(board):
            self._clear_selection()
            self._flash("AI is thinking...", duration=1.1)
            return

        square = self.view.screen_to_square(position, self.orientation_white_bottom)
        if square is None:
            self._clear_selection()
            return

        if self.selected_square is not None and square in self.legal_targets and self._attempt_move(self.selected_square, square):
            return

        piece = board.piece_at(square)
        if piece and piece.color == board.turn:
            self.selected_square = square
            self.dragging_square = square
            self.drag_position = position
            self.legal_targets = {
                move.to_square for move in board.legal_moves if move.from_square == square
            }
            return

        self._clear_selection()

    def _handle_board_release(self, position: tuple[int, int]) -> None:
        if self.dragging_square is None:
            return

        origin = self.dragging_square
        target = self.view.screen_to_square(position, self.orientation_white_bottom)
        self.dragging_square = None
        self.drag_position = None

        if target is None or target == origin:
            return

        if target in self.legal_targets:
            self._attempt_move(origin, target)

    def _handle_promotion_click(self, position: tuple[int, int]) -> None:
        choice = self.view.promotion_choice_at(position)
        if self.pending_promotion is None:
            return

        from_square, to_square = self.pending_promotion

        # Auto-queen on Shift+click even if click is outside the panel
        if self.shift_promotion and choice is None:
            choice = chess.QUEEN

        if choice is None:
            return

        if self.engine.execute_move(from_square, to_square, promotion=choice):
            self.pending_promotion = None
            self.shift_promotion = False
            self._after_successful_move()

    def _attempt_move(self, from_square: int, to_square: int) -> bool:
        board = self.engine.get_board_copy()
        legal_moves = [
            move
            for move in board.legal_moves
            if move.from_square == from_square and move.to_square == to_square
        ]

        if not legal_moves:
            return False

        if any(move.promotion for move in legal_moves):
            self.pending_promotion = (from_square, to_square)
            self.dragging_square = None
            self.drag_position = None
            with self.state_lock:
                self.analysis_dirty = True
                self.promotion_suggestion = None
            self._flash("Choose a promotion piece.", duration=1.5)
            return False

        if self.engine.execute_move(from_square, to_square):
            self._after_successful_move()
            return True
        return False

    def _clamp_move_list_scroll(self) -> None:
        max_scroll = self.view.get_move_list_max_scroll(self.engine.get_move_history())
        self.move_list_scroll = max(0, min(self.move_list_scroll, max_scroll))

    def _scroll_move_list(self, delta: int) -> None:
        self.move_list_scroll += delta
        self._clamp_move_list_scroll()

    def _scroll_move_list_to_latest(self) -> None:
        self.move_list_scroll = self.view.get_move_list_max_scroll(self.engine.get_move_history())

    def _after_successful_move(self) -> None:
        self._clear_selection()
        with self.state_lock:
            self.analysis_dirty = True
            self._clear_engine_suggestions_locked()
        self._scroll_move_list_to_latest()

        board = self.engine.get_board_copy()
        move_history = self.engine.get_move_history()
        if move_history:
            piece_side = "AI" if self.play_vs_ai and board.turn == chess.WHITE else "Played"
            notation = move_history[-1].san
            if piece_side == "Played":
                self._flash(f"Played {notation}")
            else:
                self._flash(f"{piece_side} played {notation}")

        # Sound effects
        if board.is_check():
            self.sound_mgr.play("check")
        elif self._was_a_capture():
            self.sound_mgr.play("capture")
        else:
            self.sound_mgr.play("move")

        # Chess clock — add increment to the side that just moved
        side_just_moved = chess.BLACK if board.turn == chess.WHITE else chess.WHITE
        if side_just_moved == chess.WHITE:
            self.white_clock += self.CLOCK_INCREMENT
        else:
            self.black_clock += self.CLOCK_INCREMENT
        self.clock_last_tick = time.monotonic()

        self._refresh_match_result()
        if self.match_result is not None:
            self.sound_mgr.play("game_over")
            self.claim_dialog = None
        else:
            self._refresh_claim_dialog()

    def _new_game(self) -> None:
        self.engine.reset_engine()
        self.pending_promotion = None
        self._clear_selection()
        self._clear_match_result()
        with self.state_lock:
            self.analysis_eval = 0.0
            self._clear_engine_suggestions_locked()
            self.analysis_text = (
                self.AI_UNAVAILABLE_TEXT
                if not self.engine.is_available()
                else "AI is reviewing the opening position..."
                if self.analysis_enabled
                else "Move hints are off. Press A to show AI suggestions."
            )
            self.analysis_dirty = True
        self.move_list_scroll = 0
        self._refresh_claim_dialog()
        # Reset chess clock (user starts it manually via P key)
        self.white_clock = self.CLOCK_INITIAL
        self.black_clock = self.CLOCK_INITIAL
        self.clock_preset_label = self.CLOCK_PRESETS[self._clock_preset_index][2]
        self.clock_active = False
        self._flash("New game loaded against AI." if self.play_vs_ai else "New local game loaded.")

    def _undo_move(self) -> None:
        move_undone = False
        while self.engine.undo_last_move():
            move_undone = True
            if not self.play_vs_ai:
                break
            if self.engine.get_board_copy().turn == chess.WHITE:
                break

        if not move_undone:
            self._flash("No moves to undo.")
            return

        self.pending_promotion = None
        self._clear_selection()
        self._clear_match_result()
        with self.state_lock:
            self.analysis_dirty = True
            self._clear_engine_suggestions_locked()
        self._scroll_move_list_to_latest()
        self._refresh_match_result()
        if self.match_result is None:
            self._refresh_claim_dialog()
        self._flash("Rolled back the last position.")

    def _copy_fen(self) -> None:
        fen = self.engine.get_fen()
        if self.view.copy_to_clipboard(fen):
            self._flash("FEN copied to clipboard.")
        else:
            self._flash("Clipboard is unavailable in this session.")

    def _copy_move_history(self) -> None:
        move_history = self.engine.get_move_history()
        move_text = self._format_move_history(move_history)
        if not move_text:
            self._flash("No moves to copy.")
            return

        if self.view.copy_to_clipboard(move_text):
            self._flash("Move list copied to clipboard.")
        else:
            self._flash("Clipboard is unavailable in this session.")

    def _apply_ai_elo(self) -> str:
        """Apply the current ai_elo_index to the engine and return a label."""
        label = self.engine.set_skill_level(self.ai_elo_index)
        self.ai_elo_label = label
        return label

    def _export_pgn(self) -> None:
        """Export the current game as PGN to clipboard."""
        pgn = self.engine.export_pgn()
        if self.view.copy_to_clipboard(pgn):
            self._flash("PGN copied to clipboard.")
        else:
            self._flash("Clipboard is unavailable.")

    def _import_pgn(self) -> None:
        """Import a game from clipboard PGN and replace the current board."""
        pgn = self.view.read_from_clipboard()
        if not pgn:
            self._flash("No PGN data found in clipboard. Copy a PGN first, then use Ctrl+O.")
            return
        result = ChessEngine.import_pgn(pgn)
        if result is None:
            self._flash("Invalid PGN data. Make sure the clipboard contains valid PGN.")
            return
        board, move_history, capture_history = result
        self.engine.board = board
        self.engine.move_history = move_history
        self.engine.capture_history = capture_history
        self.pending_promotion = None
        self._clear_selection()
        self._clear_match_result()
        with self.state_lock:
            self.analysis_dirty = True
            self._clear_engine_suggestions_locked()
        self._scroll_move_list_to_latest()
        # Reset clocks since we're on a new position (user starts via P key)
        self.white_clock = self.CLOCK_INITIAL
        self.black_clock = self.CLOCK_INITIAL
        self.clock_preset_label = self.CLOCK_PRESETS[self._clock_preset_index][2]
        self.clock_active = False
        self._flash("PGN imported successfully.")

    def _update_clocks(self) -> None:
        """Tick the active chess clock based on elapsed time."""
        if not self.clock_active:
            return
        board = self.engine.get_board_copy()
        if self._match_is_over(board):
            self.clock_active = False
            return
        now = time.monotonic()
        elapsed = now - self.clock_last_tick
        self.clock_last_tick = now
        if board.turn == chess.WHITE:
            self.white_clock = max(0.0, self.white_clock - elapsed)
        else:
            self.black_clock = max(0.0, self.black_clock - elapsed)
        if self.white_clock <= 0 or self.black_clock <= 0:
            loser = "White" if self.white_clock <= 0 else "Black"
            winner = "Black" if loser == "White" else "White"
            self.sound_mgr.play("flag_fall")
            self._flash(f"{loser} ran out of time! {winner} wins!")
            self.clock_active = False

    def _clock_text(self) -> str:
        """Return formatted clock string like '10:00 | 10:00 [W]'.
        Shows 'Paused' suffix and empty string when clock has never been started."""
        if not self.clock_active and self.clock_last_tick == 0.0:
            return ""  # never started
        def _fmt(seconds: float) -> str:
            m = int(seconds // 60)
            s = int(seconds % 60)
            return f"{m:02d}:{s:02d}"
        board = self.engine.get_board_copy()
        active = "W" if board.turn == chess.WHITE else "B"
        pause = " Paused" if not self.clock_active else ""
        return f"{_fmt(self.white_clock)} | {_fmt(self.black_clock)} [{active}]{pause}"

    def _format_move_history(self, move_history: list[MoveRecord]) -> str:
        return format_move_history(move_history)

    def _was_a_capture(self) -> bool:
        """Check whether the most recent move was a capture."""
        history = self.engine.get_move_history()
        if not history:
            return False
        last_san = history[-1].san
        return "x" in last_san

    def _clear_selection(self) -> None:
        self.selected_square = None
        self.legal_targets.clear()
        self.dragging_square = None
        self.drag_position = None

    def _flash(self, message: str, duration: float = FLASH_DURATION) -> None:
        self.flash_message = message
        self.flash_until = time.monotonic() + duration

    def _dialog_is_visible(self) -> bool:
        return self._get_active_dialog() is not None

    def _get_active_dialog(self) -> dict[str, str] | None:
        if self.result_dialog_visible and self.match_result is not None:
            return self.match_result
        if self.claim_dialog is not None:
            return self.claim_dialog
        return None

    def _clear_match_result(self) -> None:
        self.match_result = None
        self.result_dialog_visible = False
        self.claim_dialog = None
        self.suppressed_claim_fen = None

    def _dismiss_claim_dialog(self) -> None:
        if self.claim_dialog is not None:
            self.suppressed_claim_fen = self.claim_dialog.get("fen")
        self.claim_dialog = None

    def _describe_side(self, color: bool) -> str:
        if not self.play_vs_ai:
            return "White" if color == chess.WHITE else "Black"
        return "AI" if color == self.AI_SIDE else "You"

    def _get_board_outcome(self, board: chess.Board | None = None) -> chess.Outcome | None:
        board = board or self.engine.get_board_copy()
        return board.outcome(claim_draw=False)

    def _match_is_over(self, board: chess.Board | None = None) -> bool:
        board = board or self.engine.get_board_copy()
        automatic_outcome = self._get_board_outcome(board)
        if automatic_outcome is not None:
            return True
        return self.match_result is not None and self.match_result.get("fen") == board.fen()

    def _draw_claim_reason(self, board: chess.Board) -> str | None:
        reasons: list[str] = []
        if board.can_claim_threefold_repetition():
            reasons.append("threefold repetition")
        if board.can_claim_fifty_moves():
            reasons.append("the fifty-move rule")

        if not reasons:
            return None
        if len(reasons) == 1:
            return reasons[0]
        return " and ".join(reasons)

    def _can_offer_draw_claim(self, board: chess.Board) -> bool:
        if self._match_is_over(board):
            return False
        if self.play_vs_ai and board.turn == self.AI_SIDE:
            return False
        return self._draw_claim_reason(board) is not None

    def _build_result_payload(self, board: chess.Board, outcome: chess.Outcome) -> dict[str, str]:
        termination = outcome.termination
        title = "Game Over"
        message = "The game has finished."

        if termination == chess.Termination.CHECKMATE:
            winner = (
                self._describe_side(outcome.winner) if outcome.winner is not None else "Unknown"
            )
            title = "Checkmate"
            message = f"{winner} wins by checkmate."
        elif termination == chess.Termination.STALEMATE:
            title = "Stalemate"
            message = "The game is drawn because the side to move has no legal moves."
        elif termination == chess.Termination.INSUFFICIENT_MATERIAL:
            title = "Draw"
            message = "Draw by insufficient material."
        elif termination == chess.Termination.THREEFOLD_REPETITION:
            title = "Draw"
            message = "Draw by threefold repetition."
        elif termination == chess.Termination.FIVEFOLD_REPETITION:
            title = "Draw"
            message = "Draw by fivefold repetition."
        elif termination == chess.Termination.FIFTY_MOVES:
            title = "Draw"
            message = "Draw by the fifty-move rule."
        elif termination == chess.Termination.SEVENTYFIVE_MOVES:
            title = "Draw"
            message = "Draw by the seventy-five-move rule."
        else:
            title = termination.name.replace("_", " ").title()
            if outcome.winner is None:
                message = f"The game ended by {termination.name.replace('_', ' ').lower()}."
            else:
                winner = self._describe_side(outcome.winner)
                message = f"{winner} wins by {termination.name.replace('_', ' ').lower()}."

        return {
            "fen": board.fen(),
            "title": title,
            "message": message,
            "hint": "Press Enter or click New Game to start again. You can also press U to undo or Esc to close this dialog.",
            "primary_key": "dialog_new_game",
            "primary_label": "New Game",
            "secondary_key": "dialog_review",
            "secondary_label": "Review Board",
            "source": "automatic",
        }

    def _refresh_match_result(self) -> None:
        board = self.engine.get_board_copy()
        outcome = self._get_board_outcome(board)
        if outcome is None:
            if self.match_result is not None and self.match_result.get("source") == "automatic":
                self.match_result = None
                self.result_dialog_visible = False
            return

        payload = self._build_result_payload(board, outcome)
        if not self.match_result or self.match_result.get("fen") != payload["fen"]:
            self.match_result = payload
            self.result_dialog_visible = True
        else:
            self.match_result = payload

    def _build_claim_dialog(self, board: chess.Board) -> dict[str, str] | None:
        reason = self._draw_claim_reason(board)
        if reason is None:
            return None

        claimant = "You" if self.play_vs_ai else ("White" if board.turn == chess.WHITE else "Black")
        return {
            "fen": board.fen(),
            "title": "Draw Available",
            "message": f"{claimant} may claim a draw by {reason}.",
            "hint": "Choose Claim Draw to end the game, or Continue Playing to keep the position live.",
            "primary_key": "dialog_claim_draw",
            "primary_label": "Claim Draw",
            "secondary_key": "dialog_continue",
            "secondary_label": "Continue Playing",
            "source": "claim_prompt",
        }

    def _refresh_claim_dialog(self) -> None:
        board = self.engine.get_board_copy()
        if self.suppressed_claim_fen is not None and self.suppressed_claim_fen != board.fen():
            self.suppressed_claim_fen = None

        if not self._can_offer_draw_claim(board):
            self.claim_dialog = None
            return

        if self.suppressed_claim_fen == board.fen():
            return

        payload = self._build_claim_dialog(board)
        if payload is None:
            self.claim_dialog = None
            return

        self.claim_dialog = payload

    def _claim_draw(self) -> None:
        board = self.engine.get_board_copy()
        reason = self._draw_claim_reason(board)
        if reason is None:
            self.claim_dialog = None
            return

        claimant = "You" if self.play_vs_ai else ("White" if board.turn == chess.WHITE else "Black")
        self.match_result = {
            "fen": board.fen(),
            "title": "Draw Claimed",
            "message": f"{claimant} claimed a draw by {reason}.",
            "hint": "Press Enter or click New Game to start again. You can also press U to undo or Esc to close this dialog.",
            "primary_key": "dialog_new_game",
            "primary_label": "New Game",
            "secondary_key": "dialog_review",
            "secondary_label": "Review Board",
            "source": "claimed",
        }
        self.result_dialog_visible = True
        self.claim_dialog = None
        self.suppressed_claim_fen = None
        with self.state_lock:
            self.analysis_dirty = False
            self._clear_engine_suggestions_locked()
            self.analysis_text = self.match_result["message"]

    def _toggle_ai_mode(self) -> None:
        if not self.play_vs_ai and not self.engine.is_available():
            self._flash("AI is unavailable, so vs AI mode cannot start.")
            return

        self.play_vs_ai = not self.play_vs_ai
        self.pending_promotion = None
        self._clear_selection()
        self._clear_match_result()
        with self.state_lock:
            self.analysis_dirty = True
            self._clear_engine_suggestions_locked()
            self.analysis_text = (
                self.AI_UNAVAILABLE_TEXT
                if not self.engine.is_available()
                else "AI is ready to play Black."
                if self.play_vs_ai
                else "Local 1v1 mode is active."
            )
        self._flash("Vs AI enabled." if self.play_vs_ai else "Switched to local 1v1.")
        self._refresh_match_result()
        if self.match_result is None:
            self._refresh_claim_dialog()

    def _is_ai_turn(self, board: chess.Board | None = None) -> bool:
        if not self.play_vs_ai:
            return False
        board = board or self.engine.get_board_copy()
        return (
            not self._match_is_over(board)
            and board.turn == self.AI_SIDE
            and self.pending_promotion is None
        )

    def _process_pending_ai_move(self) -> None:
        with self.state_lock:
            pending = self.pending_ai_move
            self.pending_ai_move = None

        if not pending:
            return

        fen, move = pending
        current_fen = self.engine.get_fen()
        if current_fen != fen:
            return

        board = chess.Board(fen)
        if not self._is_ai_turn(board):
            return

        move = self._normalize_ai_move(board, move)
        if self.engine.execute_move(move.from_square, move.to_square, move.promotion):
            self._after_successful_move()

    def _normalize_ai_move(self, board: chess.Board, move: chess.Move) -> chess.Move:
        if move.promotion is not None:
            return move

        piece = board.piece_at(move.from_square)
        if piece and piece.piece_type == chess.PAWN and chess.square_rank(move.to_square) in (0, 7):
            promoted_move = chess.Move(move.from_square, move.to_square, promotion=chess.QUEEN)
            if promoted_move in board.legal_moves:
                return promoted_move
        return move

    def _extract_promotion_suggestion(
        self,
        pending_promotion: tuple[int, int] | None,
        move: chess.Move | None,
    ) -> int | None:
        if pending_promotion is None or move is None or move.promotion is None:
            return None

        from_square, to_square = pending_promotion
        if move.from_square == from_square and move.to_square == to_square:
            return move.promotion
        return None

    def _compose_status(self, board: chess.Board) -> str:
        if time.monotonic() < self.flash_until:
            return self.flash_message

        if self.match_result is not None and self.match_result.get("fen") == board.fen():
            return self.match_result["message"]
        if self.claim_dialog is not None and self.claim_dialog.get("fen") == board.fen():
            return self.claim_dialog["message"]

        outcome = self._get_board_outcome(board)
        if outcome is not None:
            if self.match_result:
                return self.match_result["message"]
            return self._build_result_payload(board, outcome)["message"]

        if board.can_claim_threefold_repetition():
            return "Threefold repetition claim is available."
        if board.can_claim_fifty_moves():
            return "Fifty-move rule claim is available."

        if self._is_ai_turn(board):
            return "AI is thinking..."

        side = "White" if board.turn == chess.WHITE else "Black"
        return f"{side} to move{' and in check' if board.is_check() else ''}."

    @staticmethod
    def _calc_material_balance(white_captured: list[str], black_captured: list[str]) -> str:
        """Calculate material advantage from captured piece keys."""
        values = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9}
        white_lost = sum(values.get(k[1], 0) for k in white_captured if k)
        black_lost = sum(values.get(k[1], 0) for k in black_captured if k)
        net = black_lost - white_lost
        if net > 0:
            return f"Material: +{net}"
        if net < 0:
            return f"Material: {net}"
        return ""

    def _build_view_state(self) -> ViewState:
        board = self.engine.get_board_copy()
        self._clamp_move_list_scroll()
        white_captured_keys, black_captured_keys = self.engine.get_captured_piece_keys()
        with self.state_lock:
            evaluation = self.analysis_eval
            analysis_text = self.analysis_text
            suggested_move = self.suggested_move
            promotion_suggestion = self.promotion_suggestion
            if not self.engine.is_available():
                evaluation = 0.0
                analysis_text = self.AI_UNAVAILABLE_TEXT
                suggested_move = None
                promotion_suggestion = None
        active_dialog = self._get_active_dialog()

        if suggested_move and suggested_move not in board.legal_moves:
            suggested_move = None

        # King check detection
        king_in_check = board.is_check()
        checked_king_square: int | None = (
            board.king(board.turn) if king_in_check else None
        )

        material_balance = self._calc_material_balance(
            white_captured_keys, black_captured_keys
        )

        # Clock button label
        _, _, preset_label = self.CLOCK_PRESETS[self._clock_preset_index]
        clock_btn = "Clock: Paused" if not self.clock_active else f"Clock: {preset_label}"

        return ViewState(
            board=board,
            move_history=self.engine.get_move_history(),
            move_scroll_offset=self.move_list_scroll,
            selected_square=self.selected_square,
            legal_targets=set(self.legal_targets),
            last_move=self.engine.get_last_move(),
            suggested_move=suggested_move,
            evaluation=evaluation,
            status_text=self._compose_status(board),
            analysis_text=analysis_text,
            orientation_white_bottom=self.orientation_white_bottom,
            dragging_square=self.dragging_square,
            drag_position=self.drag_position,
            pending_promotion=self.pending_promotion is not None,
            promotion_suggestion=promotion_suggestion,
            promotion_suggestion_enabled=self.analysis_enabled,
            fen=board.fen(),
            mode_text=("Mode: Vs AI (you play White)" if self.play_vs_ai else "Mode: Local 1v1"),
            button_labels={
                "mode_toggle": ("Playing: Vs AI" if self.play_vs_ai else "Playing: Local 1v1"),
                "clock_toggle": clock_btn,
            },
            show_shortcuts=self.show_shortcuts,
            sound_enabled=self.sound_enabled,
            material_balance=material_balance,
            king_in_check=king_in_check,
            checked_king_square=checked_king_square,
            ai_elo_label=self.ai_elo_label,
            clock_text=self._clock_text(),
            result_visible=active_dialog is not None,
            result_title=active_dialog["title"] if active_dialog else "",
            result_message=active_dialog["message"] if active_dialog else "",
            result_hint=active_dialog["hint"] if active_dialog else "",
            result_primary_key=active_dialog["primary_key"] if active_dialog else "",
            result_primary_label=(active_dialog["primary_label"] if active_dialog else ""),
            result_secondary_key=(active_dialog["secondary_key"] if active_dialog else ""),
            result_secondary_label=(active_dialog["secondary_label"] if active_dialog else ""),
            white_captured_keys=white_captured_keys,
            black_captured_keys=black_captured_keys,
        )

    def _analysis_loop(self) -> None:
        """Background thread that periodically evaluates positions and generates AI moves."""
        if not self.engine.is_available():
            self._set_analysis_unavailable()
            return

        last_fen: str | None = None
        while self.running:
            fen = self.engine.get_fen()
            board = chess.Board(fen)
            match_over = self._match_is_over(board)
            ai_turn = self._is_ai_turn(board)
            pp = self.pending_promotion
            with self.state_lock:
                dirty = self.analysis_dirty or ai_turn

            if not self.engine.is_available():
                self._set_analysis_unavailable()
                time.sleep(SLEEP_ENGINE_UNAVAILABLE)
                continue

            if match_over:
                self._handle_analysis_match_over(fen)
                continue

            if not dirty and fen == last_fen:
                time.sleep(SLEEP_IDLE)
                continue

            self._set_analysis_status_text(ai_turn, pp)
            analysis = self._run_analysis(fen, ai_turn, pp)
            suggested_move = analysis["suggestion"]

            next_text = self._compose_analysis_text(
                board, suggested_move, ai_turn, pp
            )

            if self.engine.get_fen() == fen:
                self._store_analysis_results(
                    fen, analysis, suggested_move, next_text, ai_turn, pp
                )
                last_fen = fen

            time.sleep(ANALYSIS_LOOP_SLEEP)

    def _set_analysis_unavailable(self) -> None:
        """Mark analysis state when the engine is not available."""
        with self.state_lock:
            self.analysis_eval = 0.0
            self.analysis_dirty = False
            self._clear_engine_suggestions_locked()
            self.analysis_text = self.AI_UNAVAILABLE_TEXT

    def _handle_analysis_match_over(self, fen: str) -> None:
        """Update analysis state when the match has ended."""
        self._refresh_match_result()
        with self.state_lock:
            self.analysis_dirty = False
            self._clear_engine_suggestions_locked()
            self.analysis_text = (
                self.match_result["message"] if self.match_result else "Game over."
            )
        time.sleep(SLEEP_MATCH_OVER)

    def _set_analysis_status_text(self, ai_turn: bool, pp: tuple[int, int] | None) -> None:
        """Set the analysis status text under lock."""
        with self.state_lock:
            self.ai_thinking = ai_turn
            if ai_turn:
                self.analysis_text = "AI is thinking about its move..."
            elif pp is not None and self.analysis_enabled:
                self.analysis_text = "AI is checking the promotion choice..."
            elif pp is not None:
                self.analysis_text = "Promotion suggestion is paused. Press A to enable hints."
            elif self.analysis_enabled:
                self.analysis_text = "AI is reviewing the current position..."
            else:
                self.analysis_text = "Evaluation updated. Move hints are paused."

    def _run_analysis(
        self,
        fen: str,
        ai_turn: bool,
        pp: tuple[int, int] | None,
    ) -> AnalysisResult:
        """Run the engine analysis and return the result."""
        move_time = 0.0
        if ai_turn:
            move_time = AI_MOVE_TIME
        elif (pp is not None and self.analysis_enabled) or self.analysis_enabled:
            move_time = SUGGESTION_MOVE_TIME

        # Also check promotion suggestion
        analysis = self.engine.analyze_position(
            fen=fen,
            eval_time=EVAL_TIME,
            move_time=0.0 if pp is not None else move_time,
        )
        if pp is not None and self.analysis_enabled:
            from_sq, to_sq = pp
            prom_move = self.engine.suggest_promotion_choice(fen, from_sq, to_sq)
            if prom_move is not None:
                analysis["suggestion"] = prom_move
        return analysis

    def _compose_analysis_text(
        self,
        board: chess.Board,
        suggested_move: chess.Move | None,
        ai_turn: bool,
        pp: tuple[int, int] | None,
    ) -> str:
        """Build a human-readable status line from the analysis result."""
        if board.is_game_over():
            return "Game over. Analysis complete."
        if ai_turn and suggested_move and suggested_move in board.legal_moves:
            return f"AI found {board.san(suggested_move)}"
        if pp is not None and suggested_move and suggested_move in board.legal_moves:
            return f"AI suggests {board.san(suggested_move)}"
        if pp is not None and not self.analysis_enabled:
            return "Promotion suggestion is paused. Press A to enable hints."
        if pp is not None:
            return "Promotion choice pending."
        if self.analysis_enabled and suggested_move and suggested_move in board.legal_moves:
            return f"Best move: {board.san(suggested_move)}"
        if not self.analysis_enabled:
            return "Evaluation live. Press A to show move hints again."
        return "Evaluation live. No clear move suggestion right now."

    def _store_analysis_results(
        self,
        fen: str,
        analysis: AnalysisResult,
        suggested_move: chess.Move | None,
        next_text: str,
        ai_turn: bool,
        pp: tuple[int, int] | None,
    ) -> None:
        """Write analysis results to controller state under the state lock."""
        ps = self._extract_promotion_suggestion(pp, suggested_move)
        if not self.analysis_enabled:
            ps = None
        with self.state_lock:
            self.analysis_eval = analysis["evaluation"]
            self.suggested_move = (
                suggested_move if self.analysis_enabled and not ai_turn else None
            )
            self.promotion_suggestion = ps
            self.analysis_text = next_text
            self.analysis_dirty = False
            self.ai_thinking = False
            self.pending_ai_move = (
                (fen, suggested_move)
                if ai_turn and self.play_vs_ai
                and suggested_move and suggested_move in chess.Board(fen).legal_moves
                else None
            )


def main() -> None:
    ChessController().run()


if __name__ == "__main__":
    main()
