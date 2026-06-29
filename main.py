from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from typing import Any

import chess
import pygame

from clock_utils import CLOCK_PRESETS, compute_clock_anim_progress, format_clock_text
from engine import (
    AnalysisResult,
    ChessEngine,
    EvalSnapshot,
    MoveRecord,
    PVLine,
    format_move_history,
)
from openings import detect_opening, get_opening_continuations
from openings_stats import get_variation_stats
from pgn_utils import auto_save_pgn, open_pgn_dialog, save_pgn_dialog
from ui_comp import ChessView, ReviewEntry, SoundManager, ViewState

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

    # ── Board theme definitions ────────────────────────────────────
    BOARD_THEMES: tuple[dict[str, str | tuple[int, int, int]], ...] = (
        {"name": "Classic", "light": (235, 223, 200), "dark": (105, 140, 118)},
        {"name": "Blue",    "light": (200, 215, 235), "dark": (80, 120, 170)},
        {"name": "Green",   "light": (220, 225, 200), "dark": (75, 140, 110)},
        {"name": "Dark",    "light": (70, 75, 90),    "dark": (40, 45, 60)},
    )

    def __init__(self) -> None:
        self.engine = ChessEngine()

        # Load window size from settings before creating the view
        saved_window_size = self._load_window_size_from_settings()
        self.view = ChessView(assets_dir="assets", window_size=saved_window_size)

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
        self.analysis_depth: int = 0
        self.analysis_nodes: int = 0
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
        self._pgn_viewer_active = False
        self._blindfold_active = False
        self.sound_mgr = SoundManager()
        self.sound_enabled = True
        self.sound_volume = 1.0  # 0.0-1.0
        self.shift_promotion = False
        self.board_theme_index = 0
        self._saved_window_size: tuple[int, int] | None = saved_window_size

        # ── Premium features state ──────────────────────────────────
        self._eval_snapshots: list[EvalSnapshot] = []
        self._multi_pv_lines: list[PVLine] = []
        self._opening_name: str = ""
        self._arrows: list[tuple[int, int]] = []
        self._drag_start_square: int | None = None
        self._premove: tuple[int, int, int | None] | None = None
        self._last_multi_pv_fen: str | None = None
        self._last_low_time_warn: float = 0.0
        self._move_number_trail: list[tuple[int, int]] = []
        self._review_board_index: int | None = None
        self._review_fen: str | None = None
        self._dragging_scrollbar: bool = False
        self._scrollbar_drag_offset: int = 0
        self._material_history: list[int] = []  # net material advantage over time

        # Player names for PGN export
        self._player_white = "Player"
        self._player_black = "AI"

        # Move annotations: move_index -> annotation symbol (!, ?, !!, ??, !?)
        self._move_annotations: dict[int, str] = {}

        # Clock animation state
        self._clock_anim_start: float = 0.0
        self._clock_anim_duration: float = 0.0
        self._clock_prev_text: str = ""

        # AI difficulty
        self.ai_elo_index = 0
        self.ai_elo_label = self._apply_ai_elo()

        # Chess clock (imported presets)
        self.CLOCK_PRESETS: list[tuple[float, float, str]] = CLOCK_PRESETS
        self._clock_preset_index = 0
        self.CLOCK_INITIAL, self.CLOCK_INCREMENT, _ = self.CLOCK_PRESETS[0]
        self.white_clock = self.CLOCK_INITIAL
        self.black_clock = self.CLOCK_INITIAL
        self.clock_active = False
        self.clock_last_tick = 0.0

        # Key dispatch table
        self._key_handlers: dict[int, Callable[[], None]] = {}
        self._build_key_handlers()

        self._load_settings()

        self.analysis_thread = threading.Thread(
            target=self._analysis_loop, name="analysis-worker", daemon=True
        )
        self.analysis_thread.start()

    def _load_window_size_from_settings(self) -> tuple[int, int] | None:
        """Read saved window dimensions from settings.json (before view creation)."""
        path = os.path.join(os.getcwd(), "settings.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            w = data.get("window_width")
            h = data.get("window_height")
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                return max(1260, int(w)), max(820, int(h))
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def _build_key_handlers(self) -> None:
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
            pygame.K_b: self._cycle_board_theme,
            pygame.K_F3: self._toggle_pgn_viewer,
            pygame.K_F2: self._save_board_screenshot,
            pygame.K_F4: self._toggle_blindfold,
        }

    def _toggle_blindfold(self) -> None:
        """Toggle blindfold mode (F4) — hides piece images for visualization training."""
        self._blindfold_active = not self._blindfold_active
        self._flash(
            "Blindfold mode ON \u2014 pieces hidden." if self._blindfold_active else "Blindfold mode OFF."
        )

    def _save_board_screenshot(self) -> None:
        """Save the current board area as a timestamped PNG to the games/ folder (F2)."""
        import os as _os
        from datetime import datetime as _dt

        board_rect = self.view.layout.get("board")
        if not board_rect:
            self._flash("Cannot screenshot — board layout not ready.")
            return
        games_dir = _os.path.join(_os.getcwd(), "games")
        try:
            _os.makedirs(games_dir, exist_ok=True)
            ts = _dt.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"board_{ts}.png"
            filepath = _os.path.join(games_dir, filename)
            board_surf = self.view.screen.subsurface(board_rect)
            pygame.image.save(board_surf, filepath)
            self._flash(f"Board saved: {filename}", duration=3.0)
        except Exception as e:
            self._flash(f"Could not save board image: {e}")

    def _toggle_pgn_viewer(self) -> None:
        self._pgn_viewer_active = not self._pgn_viewer_active
        self._flash(
            "PGN viewer opened." if self._pgn_viewer_active else "PGN viewer closed."
        )

    def _flip_board(self) -> None:
        self.orientation_white_bottom = not self.orientation_white_bottom
        self._flash("Board orientation flipped.")

    def _cycle_ai_elo(self) -> None:
        if not self.engine.is_available():
            self._flash("AI is not loaded, cannot change skill.")
            return
        self.ai_elo_index = (self.ai_elo_index + 1) % len(ChessEngine.ELO_PRESETS)
        label = self._apply_ai_elo()
        self._save_settings()
        self._flash(f"AI strength: {label}")

    def _cycle_board_theme(self) -> None:
        self.board_theme_index = (self.board_theme_index + 1) % len(self.BOARD_THEMES)
        theme_name = self.BOARD_THEMES[self.board_theme_index]["name"]
        self._save_settings()
        self._flash(f"Board theme: {theme_name}")

    def _cycle_time_control(self) -> None:
        self._clock_preset_index = (self._clock_preset_index + 1) % len(self.CLOCK_PRESETS)
        time_val, inc, label = self.CLOCK_PRESETS[self._clock_preset_index]
        self.CLOCK_INITIAL = time_val
        self.CLOCK_INCREMENT = inc
        self.white_clock = self.CLOCK_INITIAL
        self.black_clock = self.CLOCK_INITIAL
        if self.clock_active:
            self.clock_last_tick = time.monotonic()
        self._save_settings()
        self._flash(f"Time control: {label}")

    def _import_fen(self) -> None:
        """Read FEN from clipboard and set up the position (Ctrl+F)."""
        fen = self.view.read_from_clipboard()
        if not fen:
            self._flash("No text in clipboard. Copy a FEN first, then press Ctrl+F.")
            return
        # Validate FEN by attempting to create a board
        try:
            chess.Board(fen)
        except ValueError:
            self._flash("Invalid FEN. Make sure the clipboard contains a valid FEN string.")
            return
        self.engine.reset_engine(fen)
        self.pending_promotion = None
        self._clear_selection()
        self._clear_match_result()
        with self.state_lock:
            self.analysis_dirty = True
            self._clear_engine_suggestions_locked()
            self.analysis_text = "Position loaded from FEN. AI is reviewing..."
        self._scroll_move_list_to_latest()
        self.white_clock = self.CLOCK_INITIAL
        self.black_clock = self.CLOCK_INITIAL
        self.clock_active = False
        eco, name = detect_opening(self.engine.get_move_history())
        self._opening_name = f"{eco} — {name}" if eco != "?" else name
        self._eval_snapshots.clear()
        self._material_history.clear()
        self._save_settings()
        self._flash("Position loaded from FEN.")

    def _toggle_shortcuts(self) -> None:
        self.show_shortcuts = not self.show_shortcuts
        self._flash("Keyboard shortcuts (H to close)." if self.show_shortcuts else "Shortcuts closed.")

    def _toggle_sound(self) -> None:
        self.sound_enabled = not self.sound_enabled
        self.sound_mgr.set_enabled(self.sound_enabled)
        self._save_settings()
        self._flash("Sound ON." if self.sound_enabled else "Sound OFF.")

    def _adjust_volume(self, delta: float) -> None:
        self.sound_volume = max(0.0, min(1.0, self.sound_volume + delta))
        self.sound_mgr.set_volume(self.sound_volume)
        self._save_settings()
        pct = int(self.sound_volume * 100)
        self._flash(f"Volume: {pct}%")

    def _toggle_clock(self) -> None:
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
        if self._pgn_viewer_active:
            self._pgn_viewer_active = False
            self._flash("PGN viewer closed.")
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

                self.view.mouse_pos = pygame.mouse.get_pos()
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
        # Save settings (including window size) on shutdown
        if hasattr(self, 'view'):
            self._save_settings()
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
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self.shift_promotion = True
            self._handle_promotion_click(event.pos)
            self.shift_promotion = False
            return

        if event.type == pygame.MOUSEMOTION and self.dragging_square is not None:
            self.drag_position = event.pos
            return

        if event.type == pygame.MOUSEMOTION and self._dragging_scrollbar:
            move_history_len = len(self.engine.get_move_history())
            self.move_list_scroll = self.view.scrollbar_drag_to(
                event.pos[1], move_history_len, self.move_list_scroll
            )
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
                # Check if click is on the scrollbar track
                _track = self.view.scrollbar_track()
                if _track and _track.collidepoint(event.pos):
                    move_history_len = len(self.engine.get_move_history())
                    self.move_list_scroll = self.view.scrollbar_drag_to(
                        event.pos[1], move_history_len, self.move_list_scroll
                    )
                    self._dragging_scrollbar = True
                else:
                    # Click on a move row — navigate to that position
                    self._handle_move_list_click(event.pos)
                return

            # PGN viewer tab click
            if self._pgn_viewer_active:
                tab_idx = self.view.pgn_viewer_tab_at(event.pos)
                if tab_idx is not None:
                    self.view._pgn_tab = tab_idx
                    self._flash(f"PGN viewer: {['Metadata', 'Raw PGN'][tab_idx]}")
                    return

            if self.view.point_in_panel("fen", event.pos):
                self._copy_fen()
                return

            self._handle_board_press(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging_scrollbar = False
            if not self.pending_promotion:
                self._handle_board_release(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            square = self.view.screen_to_square(event.pos, self.orientation_white_bottom)
            if square is not None:
                self._drag_start_square = square
            else:
                self._clear_selection()
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            if self._drag_start_square is not None:
                end_square = self.view.screen_to_square(event.pos, self.orientation_white_bottom)
                if end_square is not None and end_square != self._drag_start_square:
                    arrow = (self._drag_start_square, end_square)
                    if arrow in self._arrows:
                        self._arrows.remove(arrow)
                        self._flash(f"Removed arrow: {chess.square_name(self._drag_start_square)}-{chess.square_name(end_square)}")
                    else:
                        self._arrows.append(arrow)
                        self._flash(f"Analysis arrow: {chess.square_name(self._drag_start_square)}-{chess.square_name(end_square)}")
                elif end_square is not None and end_square == self._drag_start_square:
                    removed = [a for a in self._arrows if a[1] == end_square]
                    for a in removed:
                        self._arrows.remove(a)
                    if removed:
                        self._flash(f"Cleared arrow{'(s)' if len(removed)>1 else ''} at {chess.square_name(end_square)}")
                self._drag_start_square = None
            else:
                # Right-click on move list row to annotate a move
                rect = self.view.layout.get("moves")
                if rect and rect.collidepoint(event.pos):
                    list_rect = pygame.Rect(rect.x + 12, rect.y + 46, rect.width - 24, rect.height - 58)
                    if list_rect.collidepoint(event.pos):
                        line_height = 26
                        clicked_row = (event.pos[1] - list_rect.y - 4) // line_height
                        total_pairs = (len(self.engine.get_move_history()) + 1) // 2
                        rows_visible = max(1, (list_rect.height - 8) // line_height)
                        max_scroll = max(0, total_pairs - rows_visible)
                        start_index = min(max(self.move_list_scroll, 0), max_scroll)
                        absolute_row = start_index + clicked_row
                        move_index = absolute_row * 2
                        # Check black-move column
                        half_width = (list_rect.width - 24) // 2
                        white_x_end = list_rect.x + 56 + half_width
                        if event.pos[0] > white_x_end and absolute_row * 2 + 1 < len(self.engine.get_move_history()):
                            move_index = absolute_row * 2 + 1
                        if move_index < len(self.engine.get_move_history()):
                            self._cycle_move_annotation(move_index)
            return

    def _handle_move_list_click(self, position: tuple[int, int]) -> None:
        """Click on a move in the move list to jump to that position."""
        rect = self.view.layout.get("moves")
        if not rect or rect.height < 60:
            return
        list_rect = pygame.Rect(rect.x + 12, rect.y + 46, rect.width - 24, rect.height - 58)
        if not list_rect.collidepoint(position):
            return
        line_height = 26
        clicked_row = (position[1] - list_rect.y - 4) // line_height
        if clicked_row < 0:
            return
        visible_rows = max(1, (list_rect.height - 8) // line_height)
        total_pairs = (len(self.engine.get_move_history()) + 1) // 2
        max_scroll = max(0, total_pairs - visible_rows)
        start_index = min(max(self.move_list_scroll, 0), max_scroll)
        absolute_row = start_index + clicked_row
        if absolute_row >= total_pairs:
            return
        # Convert pair index to move index
        move_index = absolute_row * 2  # white move
        if clicked_row > 0:
            # Check if clicking on the black move area (right half)
            half_width = (list_rect.width - 24) // 2
            white_x_end = list_rect.x + 56 + half_width
            if position[0] > white_x_end and absolute_row * 2 + 1 < len(self.engine.get_move_history()):
                move_index = absolute_row * 2 + 1  # black move
        if move_index >= len(self.engine.get_move_history()):
            return
        self._review_board_index = move_index
        self._update_review_board()

    def _handle_keypress(self, key: int) -> None:
        # Dialog shortcuts
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

        if key == pygame.K_ESCAPE:
            self._handle_escape()
            return

        # Volume adjustment with =/- keys
        if key == pygame.K_EQUALS:
            self._adjust_volume(0.1)
            return
        if key == pygame.K_MINUS:
            self._adjust_volume(-0.1)
            return

        handler = self._key_handlers.get(key)
        if handler is not None:
            handler()
            return

        mods = pygame.key.get_mods()
        if key == pygame.K_c:
            if mods & pygame.KMOD_CTRL:
                self._copy_move_history()
            else:
                self._copy_fen()
            return
        if key == pygame.K_f and (mods & pygame.KMOD_CTRL):
            self._import_fen()
            return
        if key == pygame.K_o and (mods & pygame.KMOD_CTRL):
            if mods & pygame.KMOD_SHIFT:
                self._open_pgn_file()
            else:
                self._import_pgn()
            return
        if key == pygame.K_p and (mods & pygame.KMOD_CTRL):
            if mods & pygame.KMOD_SHIFT:
                self._save_pgn_file()
            else:
                self._export_pgn()
            return
        if key == pygame.K_b and (mods & pygame.KMOD_CTRL) and (mods & pygame.KMOD_SHIFT):
            self._copy_board_image()
            return

        # Keyboard navigation of move list
        if key == pygame.K_UP:
            if self._review_board_index is None:
                self._review_board_index = max(0, len(self.engine.get_move_history()) - 1)
            elif self._review_board_index > 0:
                self._review_board_index -= 1
            self._update_review_board()
            return
        if key == pygame.K_DOWN:
            if self._review_board_index is not None:
                max_idx = len(self.engine.get_move_history())
                if self._review_board_index < max_idx - 1:
                    self._review_board_index += 1
                    self._update_review_board()
                else:
                    self._review_board_index = None
                    self._update_review_board()
            return
        if key == pygame.K_LEFT:
            if self._review_board_index is None:
                self._review_board_index = max(0, len(self.engine.get_move_history()) - 1)
            elif self._review_board_index > 0:
                self._review_board_index -= 1
            self._update_review_board()
            return
        if key == pygame.K_RIGHT:
            if self._review_board_index is not None:
                max_idx = len(self.engine.get_move_history())
                if self._review_board_index < max_idx - 1:
                    self._review_board_index += 1
                    self._update_review_board()
                else:
                    self._review_board_index = None
                    self._update_review_board()
            return

        if self.pending_promotion is not None:
            prom_map = {
                pygame.K_q: chess.QUEEN,
                pygame.K_r: chess.ROOK,
                pygame.K_b: chess.BISHOP,
                pygame.K_n: chess.KNIGHT,
            }
            if key in prom_map:
                from_square, to_square = self.pending_promotion
                choice = prom_map[key]
                if self.engine.execute_move(from_square, to_square, promotion=choice):
                    self.pending_promotion = None
                    self._after_successful_move()
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
        elif action_key == "dialog_new_game_confirm":
            self.result_dialog_visible = False
            self.match_result = None
            self._do_new_game()
        elif action_key == "dialog_cancel":
            self.result_dialog_visible = False
            self.match_result = None
        elif action_key == "dialog_review":
            self.result_dialog_visible = False
        elif action_key == "dialog_claim_draw":
            self._claim_draw()
        elif action_key == "dialog_continue":
            self._dismiss_claim_dialog()

    def _handle_board_press(self, position: tuple[int, int]) -> None:
        if self._review_fen is not None:
            self._review_board_index = None
            self._review_fen = None
            self._flash("Exited review mode.")
            return

        board = self.engine.get_board_copy()
        if self._match_is_over(board):
            self._clear_selection()
            self._flash("Game is finished. Start a new game or undo to continue.", duration=1.5)
            return

        is_my_turn = not self._is_ai_turn(board)
        square = self.view.screen_to_square(position, self.orientation_white_bottom)
        if square is None:
            self._clear_selection()
            return

        piece = board.piece_at(square)

        if self.selected_square is not None:
            if is_my_turn and square in self.legal_targets:
                if self._attempt_move(self.selected_square, square):
                    return
            elif not is_my_turn and square != self.selected_square:
                from_sq = self.selected_square
                to_sq = square
                self._premove = (from_sq, to_sq, None)
                self._flash(f"Premove: {chess.SQUARE_NAMES[from_sq]}-{chess.SQUARE_NAMES[to_sq]}")
                self._clear_selection()
                return

        if piece and piece.color == board.turn:
            self._premove = None
            self.selected_square = square
            self.dragging_square = square
            self.drag_position = position
            self.legal_targets = {
                move.to_square for move in board.legal_moves if move.from_square == square
            }
            return

        if not is_my_turn and piece:
            ok = (self.play_vs_ai and piece.color == chess.WHITE) or not self.play_vs_ai
            if ok:
                self._premove = None
                self.selected_square = square
                self.dragging_square = square
                self.drag_position = position
                self.legal_targets = set()
                self._flash(f"Premoving {piece.symbol()} from {chess.SQUARE_NAMES[square]}")
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
            return

        board_check = self.engine.get_board_copy()
        piece_at_origin = board_check.piece_at(origin)
        if piece_at_origin and piece_at_origin.color != board_check.turn:
            self._premove = (origin, target, None)
            self._flash(f"Premove: {chess.SQUARE_NAMES[origin]}-{chess.SQUARE_NAMES[target]}")
            self._clear_selection()
            return

    def _handle_promotion_click(self, position: tuple[int, int]) -> None:
        choice = self.view.promotion_choice_at(position)
        if self.pending_promotion is None:
            return

        from_square, to_square = self.pending_promotion

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

    def _update_material_history(self) -> None:
        """Compute net material advantage and append to history."""
        values = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9}
        white_caps, black_caps = self.engine.get_captured_piece_keys()
        white_lost = sum(values.get(k[1], 0) for k in white_caps if k)
        black_lost = sum(values.get(k[1], 0) for k in black_caps if k)
        net = black_lost - white_lost
        self._material_history.append(net)

    def _after_successful_move(self) -> None:
        board_before = self.engine.get_board_copy()
        move_history = self.engine.get_move_history()
        last_move = self.engine.get_last_move()

        self._clear_selection()
        with self.state_lock:
            self.analysis_dirty = True
            self._clear_engine_suggestions_locked()
        self._scroll_move_list_to_latest()

        if self._premove is not None:
            board_check = self.engine.get_board_copy()
            is_my_turn_now = not self._is_ai_turn(board_check)
            if is_my_turn_now:
                pm_from, pm_to, pm_prom = self._premove
                self._premove = None
                if self._attempt_move(pm_from, pm_to):
                    return
                if pm_prom is not None and self.engine.execute_move(pm_from, pm_to, promotion=pm_prom):
                    self._after_successful_move()
                    return

        if last_move is not None:
            piece = board_before.piece_at(last_move.to_square) or board_before.piece_at(last_move.from_square)
            if piece:
                piece_key = f"{'w' if piece.color == chess.WHITE else 'b'}{piece.symbol().upper()}"
                from_rect = self.view.square_to_rect(last_move.from_square, self.orientation_white_bottom)
                to_rect = self.view.square_to_rect(last_move.to_square, self.orientation_white_bottom)
                self.view.start_animation(piece_key, from_rect, to_rect, to_square=last_move.to_square, duration=0.15)

        eco, name = detect_opening(self.engine.get_move_history())
        self._opening_name = f"{eco} — {name}" if eco != "?" else name

        if last_move is not None:
            move_num = (len(move_history) + 1) // 2
            self._move_number_trail.append((move_num, last_move.to_square))
            if len(self._move_number_trail) > 6:
                self._move_number_trail.pop(0)

        # Track material history
        self._update_material_history()

        with self.state_lock:
            eval_after = self.analysis_eval

        if move_history:
            last_record = move_history[-1]
            move_num = (len(move_history) + 1) // 2
            prev_eval = self._eval_snapshots[-1].eval_after if self._eval_snapshots else 0.0
            delta = (eval_after - prev_eval) * (1 if last_record.side == chess.WHITE else -1)
            snapshot = EvalSnapshot(
                move_number=move_num,
                side=last_record.side,
                san=last_record.san,
                eval_before=prev_eval,
                eval_after=eval_after,
                delta=delta,
            )
            self._eval_snapshots.append(snapshot)

        board = self.engine.get_board_copy()
        if move_history:
            piece_side = "AI" if self.play_vs_ai and board.turn == chess.WHITE else "Played"
            notation = move_history[-1].san
            if piece_side == "Played":
                self._flash(f"Played {notation}")
            else:
                self._flash(f"{piece_side} played {notation}")

        if board.is_check():
            self.sound_mgr.play("check")
        elif self._was_a_capture():
            self.sound_mgr.play("capture")
        else:
            self.sound_mgr.play("move")

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
            self._auto_save_pgn()
        else:
            self._refresh_claim_dialog()

    def _auto_save_pgn(self) -> None:
        self._update_player_names_for_mode()
        pgn = self.engine.export_pgn(
            white_name=self._player_white, black_name=self._player_black,
            annotations=self._move_annotations,
        )
        if not pgn.strip():
            return
        filename = auto_save_pgn(pgn, opening_name=self._opening_name)
        if filename:
            self._flash(f"Game saved: {filename}", duration=3.0)

    def _parse_pgn_metadata(self) -> dict[str, str]:
        """Parse PGN header tags from the current game for the PGN viewer."""
        self._update_player_names_for_mode()
        pgn = self.engine.export_pgn(
            white_name=self._player_white, black_name=self._player_black,
            annotations=self._move_annotations,
        )
        metadata: dict[str, str] = {}
        for line in pgn.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith('"'):
                if '"' in line:
                    tag = line[1:line.index('"')].strip()
                    value = line[line.index('"') + 1 : line.rindex('"')]
                    metadata[tag] = value
            if not line.startswith("["):
                # Move text starts — stop parsing headers
                break
        # Add computed fields
        metadata["Opening"] = self._opening_name if self._opening_name else "—"
        metadata["Moves"] = str(len(self.engine.get_move_history()))
        metadata["FEN"] = self.engine.get_fen()
        metadata["Raw"] = pgn
        return metadata

    def _settings_path(self) -> str:
        import os as _os
        return _os.path.join(_os.getcwd(), "settings.json")

    def _save_settings(self) -> None:

        # Guard against headless/dummy display where get_size() may raise
        try:
            win_w = self.view.screen.get_width()
            win_h = self.view.screen.get_height()
        except pygame.error:
            win_w, win_h = 0, 0

        data = {
            "sound_enabled": self.sound_enabled,
            "sound_volume": self.sound_volume,
            "ai_elo_index": self.ai_elo_index,
            "clock_preset_index": self._clock_preset_index,
            "board_theme_index": self.board_theme_index,
            "window_width": win_w,
            "window_height": win_h,
        }
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass

    def _load_settings(self) -> None:
        path = self._settings_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get("sound_enabled"), bool):
                self.sound_enabled = data["sound_enabled"]
                self.sound_mgr.set_enabled(self.sound_enabled)
            if isinstance(data.get("sound_volume"), (int, float)):
                self.sound_volume = max(0.0, min(1.0, float(data["sound_volume"])))
                self.sound_mgr.set_volume(self.sound_volume)
            if isinstance(data.get("ai_elo_index"), int):
                self.ai_elo_index = data["ai_elo_index"] % len(ChessEngine.ELO_PRESETS)
                self._apply_ai_elo()
            if isinstance(data.get("board_theme_index"), int):
                self.board_theme_index = data["board_theme_index"] % len(self.BOARD_THEMES)
            if isinstance(data.get("clock_preset_index"), int):
                self._clock_preset_index = data["clock_preset_index"] % len(self.CLOCK_PRESETS)
                time_val, inc, _ = self.CLOCK_PRESETS[self._clock_preset_index]
                self.CLOCK_INITIAL = time_val
                self.CLOCK_INCREMENT = inc
                self.white_clock = self.CLOCK_INITIAL
                self.black_clock = self.CLOCK_INITIAL
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    def _new_game(self) -> None:
        if self.engine.get_move_history() and self.match_result is None:
            board = self.engine.get_board_copy()
            if not board.is_game_over() and not self._match_is_over(board):
                self.match_result = {
                    "fen": board.fen(),
                    "title": "Start New Game?",
                    "message": "A game is in progress. Starting a new game will discard the current position.",
                    "hint": "Press Enter to confirm or Esc to cancel.",
                    "primary_key": "dialog_new_game_confirm",
                    "primary_label": "Discard & Start New",
                    "secondary_key": "dialog_cancel",
                    "secondary_label": "Cancel",
                    "source": "new_game_confirm",
                }
                self.result_dialog_visible = True
                self._flash("Confirm new game — current game will be discarded.")
                return

        self._do_new_game()

    def _do_new_game(self) -> None:
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
        self.white_clock = self.CLOCK_INITIAL
        self.black_clock = self.CLOCK_INITIAL
        self.clock_active = False

        # Reset premium features
        self._eval_snapshots.clear()
        self._arrows.clear()
        self._multi_pv_lines.clear()
        self._opening_name = ""
        self._last_multi_pv_fen = None
        self._premove = None
        self._move_number_trail.clear()
        self._material_history.clear()
        self._review_board_index = None
        self._review_fen = None

        # Auto-flip so user plays as White in AI mode
        if self.play_vs_ai:
            self.orientation_white_bottom = True
        self._blindfold_active = False

        self._save_settings()
        self._flash("New game loaded against AI." if self.play_vs_ai else "New local game loaded.")

    def _undo_move(self) -> None:
        moves_undone = 0
        board_before = self.engine.get_board_copy()
        anim_piece_key: str | None = None
        anim_from_sq: int | None = None
        anim_to_sq: int | None = None
        if board_before.move_stack:
            last_mv = board_before.move_stack[-1]
            piece = board_before.piece_at(last_mv.to_square) or board_before.piece_at(last_mv.from_square)
            if piece:
                anim_piece_key = f"{'w' if piece.color == chess.WHITE else 'b'}{piece.symbol().upper()}"
                anim_to_sq = last_mv.from_square
                anim_from_sq = last_mv.to_square

        while self.engine.undo_last_move():
            moves_undone += 1
            if not self.play_vs_ai:
                break
            if self.engine.get_board_copy().turn == chess.WHITE:
                break

        if moves_undone == 0:
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

        eco, name = detect_opening(self.engine.get_move_history())
        self._opening_name = f"{eco} — {name}" if eco != "?" else name

        for _ in range(moves_undone):
            if self._eval_snapshots:
                self._eval_snapshots.pop()
            if self._move_number_trail:
                self._move_number_trail.pop()
            if self._material_history:
                self._material_history.pop()

        if anim_piece_key is not None and anim_from_sq is not None and anim_to_sq is not None:
            from_rect = self.view.square_to_rect(anim_from_sq, self.orientation_white_bottom)
            to_rect = self.view.square_to_rect(anim_to_sq, self.orientation_white_bottom)
            self.view.start_animation(anim_piece_key, from_rect, to_rect, duration=0.18)

        self.sound_mgr.play("undo")
        self._flash("Rolled back the last position.")

    def _update_review_board(self) -> None:
        if self._review_board_index is None:
            self._review_fen = None
            self._flash("Exited review mode.")
            return
        tmp_board = chess.Board()
        history = self.engine.get_move_history()
        replay_up_to = min(self._review_board_index, len(history) - 1)
        if replay_up_to < 0:
            self._review_fen = tmp_board.fen()
            self._flash("At starting position.")
            return
        for i, record in enumerate(history):
            if i > replay_up_to:
                break
            try:
                move = tmp_board.parse_san(record.san)
                tmp_board.push(move)
            except Exception:
                break
        self._review_fen = tmp_board.fen()
        move_str = history[replay_up_to].san if replay_up_to < len(history) else ""
        self._flash(f"Review: move {replay_up_to + 1} — {move_str}")

    def _get_effective_board(self) -> chess.Board:
        if self._review_fen is not None:
            return chess.Board(self._review_fen)
        return self.engine.get_board_copy()

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
        label = self.engine.set_skill_level(self.ai_elo_index)
        self.ai_elo_label = label
        return label

    def _open_pgn_file(self) -> None:
        """Open a PGN file using a system dialog (Ctrl+Shift+O)."""
        pgn = open_pgn_dialog()
        if pgn is None:
            return
        self._load_pgn(pgn)
        self._flash("PGN imported from file.")

    def _save_pgn_file(self) -> None:
        """Save the current game as a PGN file using a system dialog (Ctrl+Shift+P)."""
        self._update_player_names_for_mode()
        pgn = self.engine.export_pgn(
            white_name=self._player_white, black_name=self._player_black,
            annotations=self._move_annotations,
        )
        if not pgn.strip():
            self._flash("No moves to save.")
            return
        basename = save_pgn_dialog(pgn)
        if basename:
            self._flash(f"Game saved to: {basename}")

    def _load_pgn(self, pgn: str) -> None:
        """Load a PGN string into the controller (shared by clipboard and file import)."""
        if not pgn:
            self._flash("No PGN data found.")
            return
        result = ChessEngine.import_pgn(pgn)
        if result is None:
            self._flash("Invalid PGN data.")
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
        self.white_clock = self.CLOCK_INITIAL
        self.black_clock = self.CLOCK_INITIAL
        self.clock_active = False
        eco, name = detect_opening(self.engine.get_move_history())
        self._opening_name = f"{eco} — {name}" if eco != "?" else name
        self._eval_snapshots.clear()
        self._material_history.clear()
        self._refresh_match_result()
        if self.match_result is None:
            self._refresh_claim_dialog()

    def _export_pgn(self) -> None:
        self._update_player_names_for_mode()
        pgn = self.engine.export_pgn(
            white_name=self._player_white, black_name=self._player_black,
            annotations=self._move_annotations,
        )
        if self.view.copy_to_clipboard(pgn):
            self._flash("PGN copied to clipboard.")
        else:
            self._flash("Clipboard is unavailable.")

    def _import_pgn(self) -> None:
        pgn = self.view.read_from_clipboard()
        if not pgn:
            self._flash("No PGN data found in clipboard. Copy a PGN first, then use Ctrl+O.")
            return
        self._load_pgn(pgn)
        self._flash("PGN imported from clipboard.")

    def _update_clocks(self) -> None:
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
        active_clock = self.white_clock if board.turn == chess.WHITE else self.black_clock
        if self.clock_active and active_clock <= 10.0 and time.monotonic() - self._last_low_time_warn >= 1.0:
            self._last_low_time_warn = time.monotonic()
            self.sound_mgr.play("tick")

        if self.white_clock <= 0 or self.black_clock <= 0:
            loser = "White" if self.white_clock <= 0 else "Black"
            self.sound_mgr.play("flag_fall")
            clock_fen = self.engine.get_fen()
            winner_side = chess.BLACK if loser == "White" else chess.WHITE
            winner_label = self._describe_side(winner_side)
            self.match_result = {
                "fen": clock_fen,
                "title": "Time Forfeit",
                "message": f"{winner_label} wins! {loser} ran out of time.",
                "hint": "Press Enter or click New Game to start again. You can also press U to undo or Esc to close this dialog.",
                "primary_key": "dialog_new_game",
                "primary_label": "New Game",
                "secondary_key": "dialog_review",
                "secondary_label": "Review Board",
                "source": "timeout",
            }
            self.result_dialog_visible = True
            self.clock_active = False
            self.sound_mgr.play("game_over")
            self._auto_save_pgn()

    def _copy_board_image(self) -> None:
        """Capture the board area and copy it to clipboard as an image.

        Uses platform-specific clipboard methods:
        - Windows: PowerShell + System.Windows.Forms
        - macOS: osascript
        - Linux: xclip
        """
        board_rect = self.view.layout["board"]
        try:
            import os as _os
            import platform as _platform
            import subprocess as _sp
            import tempfile as _tf

            board_surf = self.view.screen.subsurface(board_rect)
            tmp_path = _tf.mktemp(suffix=".png")
            pygame.image.save(board_surf, tmp_path)

            system = _platform.system()
            if system == "Windows":
                ps_cmd = (
                    f"Add-Type -AssemblyName System.Windows.Forms; "
                    f"$img = [System.Drawing.Image]::FromFile('{tmp_path}'); "
                    f"[System.Windows.Forms.Clipboard]::SetImage($img); "
                    f"$img.Dispose()"
                )
                _sp.run(["powershell", "-Command", ps_cmd], capture_output=True, timeout=5)
            elif system == "Darwin":
                _sp.run([
                    "osascript", "-e",
                    f'set the clipboard to (read (POSIX file "{tmp_path}") as TIFF picture)',
                ], capture_output=True, timeout=5)
            elif system == "Linux":
                _sp.run([
                    "xclip", "-selection", "clipboard", "-t", "image/png", "-i", tmp_path,
                ], capture_output=True, timeout=5)
            else:
                self._flash(f"Board image copy not supported on {system}.")
                _os.unlink(tmp_path)
                return

            _os.unlink(tmp_path)
            self._flash("Board image copied to clipboard.")
        except Exception as e:
            self._flash(f"Could not copy board image: {e}")

    def _cycle_move_annotation(self, move_index: int) -> None:
        """Cycle through annotation symbols (!, ?, !!, ??, !?, none) for a move."""
        cycle = ["!", "?", "!!", "??", "!?", None]
        current = self._move_annotations.get(move_index)
        try:
            next_idx = (cycle.index(current) + 1) % len(cycle) if current in cycle else 0
        except ValueError:
            next_idx = 0
        next_ann = cycle[next_idx]
        if next_ann is None:
            self._move_annotations.pop(move_index, None)
            self._flash(f"Removed annotation from move {move_index + 1}")
        else:
            self._move_annotations[move_index] = next_ann
            self._flash(f"Move {move_index + 1}: {next_ann}")

    def _clock_text(self) -> str:
        if not self.clock_active and self.clock_last_tick == 0.0:
            return ""
        board = self.engine.get_board_copy()
        active = "W" if board.turn == chess.WHITE else "B"
        return format_clock_text(
            self.white_clock,
            self.black_clock,
            active,
            clock_active=self.clock_active,
            clock_initial=self.CLOCK_INITIAL,
        )

    def _format_move_history(self, move_history: list[MoveRecord]) -> str:
        return format_move_history(move_history)

    def _was_a_capture(self) -> bool:
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
        self._drag_start_square = None

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

    def _update_player_names_for_mode(self) -> None:
        """Set sensible player names based on current game mode."""
        if self.play_vs_ai:
            self._player_white = "Player"
            self._player_black = "AI"
        else:
            self._player_white = "Player 1"
            self._player_black = "Player 2"

    def _toggle_ai_mode(self) -> None:
        if not self.play_vs_ai and not self.engine.is_available():
            self._flash("AI is unavailable, so vs AI mode cannot start.")
            return

        self.play_vs_ai = not self.play_vs_ai
        self._update_player_names_for_mode()
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
            msg = self.flash_message
            if self._review_board_index is not None:
                return f"[Review] {msg}"
            return msg

        if self._review_board_index is not None:
            move_num = self._review_board_index + 1
            history = self.engine.get_move_history()
            san = history[self._review_board_index].san if self._review_board_index < len(history) else ""
            side = "White" if board.turn == chess.WHITE else "Black"
            return f"Reviewing move {move_num} — {san} · {side} to move [↑/↓ to navigate]"

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
        move_count = board.fullmove_number
        return f"Move {move_count} · {side} to move{' and in check' if board.is_check() else ''}."

    def _build_clock_anim_state(self) -> tuple[float, float, str]:
        """Return (anim_progress, anim_duration, prev_text) for clock animation."""
        now = time.monotonic()
        progress = compute_clock_anim_progress(self._clock_anim_start, self._clock_anim_duration, now)
        return (progress, self._clock_anim_duration, self._clock_prev_text)

    @staticmethod
    def _calc_material_balance(white_captured: list[str], black_captured: list[str]) -> str:
        values = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9}
        white_lost = sum(values.get(k[1], 0) for k in white_captured if k)
        black_lost = sum(values.get(k[1], 0) for k in black_captured if k)
        net = black_lost - white_lost
        if net > 0:
            return f"Material: +{net}"
        if net < 0:
            return f"Material: {net}"
        return ""

    def _compute_review_data(self) -> list[ReviewEntry]:
        if len(self._eval_snapshots) < 2:
            return []

        entries: list[ReviewEntry] = []
        for snap in self._eval_snapshots:
            delta = snap.delta * 100.0
            move_num_str = f"{snap.move_number}."
            if snap.side == chess.BLACK:
                move_num_str = f"{snap.move_number}..."

            if delta >= 2.5:
                mtype = "brilliant"
            elif delta >= 0.7:
                mtype = "best"
            elif delta >= 0.4:
                mtype = "excellent"
            elif delta >= 0.2:
                mtype = "good"
            elif delta >= -0.2:
                continue
            elif delta >= -0.6:
                mtype = "inaccuracy"
            elif delta >= -1.8:
                mtype = "mistake"
            else:
                mtype = "blunder"

            entries.append(ReviewEntry(
                move_type=mtype,
                move_number=move_num_str,
                san=snap.san,
                delta=delta,
                before=snap.eval_before,
                after=snap.eval_after,
            ))

        entries.sort(key=lambda e: e.delta)
        return entries

    def _find_check_attackers(self, board: chess.Board) -> list[tuple[int, int]]:
        """Return list of (attacker_square, king_square) pairs if king is in check."""
        if not board.is_check():
            return []
        king_sq = board.king(board.turn)
        if king_sq is None:
            return []
        attackers: list[tuple[int, int]] = []
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color != board.turn:
                for move in board.legal_moves:
                    if move.to_square == king_sq and move.from_square == sq:
                        attackers.append((sq, king_sq))
                        break
        return attackers

    def _get_attacked_squares(self, board: chess.Board) -> set[int]:
        """Return squares attacked by the opponent (pseudo-legal)."""
        attacked: set[int] = set()
        turn = board.turn
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color != turn:
                for move in board.generate_pseudo_legal_moves():
                    if move.from_square == sq:
                        attacked.add(move.to_square)
        return attacked

    def _build_view_state(self) -> ViewState:
        board = self._get_effective_board()
        self._clamp_move_list_scroll()
        white_captured_keys, black_captured_keys = self.engine.get_captured_piece_keys()
        with self.state_lock:
            evaluation = self.analysis_eval
            analysis_text = self.analysis_text
            suggested_move = self.suggested_move
            promotion_suggestion = self.promotion_suggestion
            multi_pv_lines = list(self._multi_pv_lines)
            analysis_depth = self.analysis_depth
            analysis_nodes = self.analysis_nodes
            if not self.engine.is_available():
                evaluation = 0.0
                analysis_text = self.AI_UNAVAILABLE_TEXT
                suggested_move = None
                promotion_suggestion = None
                analysis_depth = 0
                analysis_nodes = 0
        active_dialog = self._get_active_dialog()

        if suggested_move and suggested_move not in board.legal_moves:
            suggested_move = None

        king_in_check = board.is_check()
        checked_king_square: int | None = (
            board.king(board.turn) if king_in_check else None
        )

        material_balance = self._calc_material_balance(
            white_captured_keys, black_captured_keys
        )

        _, _, preset_label = self.CLOCK_PRESETS[self._clock_preset_index]
        clock_btn = "Clock: Paused" if not self.clock_active else f"Clock: {preset_label}"

        review_data = []
        if self.match_result is not None:
            review_data = self._compute_review_data()

        # Legal moves count and threat visualization
        num_legal_moves = board.legal_moves.count() if not self._match_is_over(board) else 0
        check_attackers = self._find_check_attackers(board)
        attacked_squares = self._get_attacked_squares(board)

        # Clock animation state
        clock_text = self._clock_text()
        clock_anim_progress, clock_anim_duration, clock_prev_text = self._build_clock_anim_state()
        if clock_text and clock_text != self._clock_prev_text:
            self._clock_prev_text = clock_text  # use cached value, don't call again
            self._clock_anim_start = time.monotonic()
            self._clock_anim_duration = 0.3

        # Opening continuations — common named lines from current position
        _opening_continuations = get_opening_continuations(self.engine.get_move_history())
        if not self._match_is_over(board):
            opening_continuations = _opening_continuations
        else:
            opening_continuations = []

        # Opening statistics — try variation-specific first, fall back to ECO-level
        eco_code = self._opening_name.split(" ")[0] if self._opening_name and "\u2014" in self._opening_name else ""
        if eco_code:
            # Compute UCI moves for variation lookup
            _uci_tmp = chess.Board()
            _uci_moves: list[str] = []
            for _rec in self.engine.get_move_history():
                try:
                    _m = _uci_tmp.parse_san(_rec.san)
                    _uci_moves.append(_m.uci())
                    _uci_tmp.push(_m)
                except (ValueError, chess.InvalidMoveError):
                    break
            opening_stats = get_variation_stats(eco_code, tuple(_uci_moves))
        else:
            opening_stats = None

        # PGN metadata for viewer
        pgn_metadata = self._parse_pgn_metadata()

        # Board theme colors
        theme = self.BOARD_THEMES[self.board_theme_index]

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
            clock_text=clock_text,
            clock_anim_progress=clock_anim_progress,
            clock_anim_duration=clock_anim_duration,
            clock_prev_text=clock_prev_text,
            move_annotations=dict(self._move_annotations),
            num_legal_moves=num_legal_moves,
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
            opening_name=self._opening_name,
            multi_pv_lines=multi_pv_lines,
            arrows=self._arrows,
            review_data=review_data,
            premove=self._premove,
            move_number_trail=self._move_number_trail,
            eval_history=[s.eval_after for s in self._eval_snapshots[-20:]],
            material_history=list(self._material_history[-30:]),
            check_attackers=check_attackers,
            attacked_squares=attacked_squares,
            board_theme_light=theme["light"],  # type: ignore[arg-type]
            board_theme_dark=theme["dark"],  # type: ignore[arg-type]
            analysis_depth=analysis_depth,
            analysis_nodes=analysis_nodes,
            sound_volume=self.sound_volume,
            opening_continuations=opening_continuations,
            show_pgn_viewer=self._pgn_viewer_active,
            pgn_metadata=pgn_metadata,
            opening_stats=opening_stats,
            blindfold_active=self._blindfold_active,
        )

    def _analysis_loop(self) -> None:
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
        with self.state_lock:
            self.analysis_eval = 0.0
            self.analysis_dirty = False
            self._clear_engine_suggestions_locked()
            self.analysis_text = self.AI_UNAVAILABLE_TEXT

    def _handle_analysis_match_over(self, fen: str) -> None:
        self._refresh_match_result()
        with self.state_lock:
            self.analysis_dirty = False
            self._clear_engine_suggestions_locked()
            self.analysis_text = (
                self.match_result["message"] if self.match_result else "Game over."
            )
        time.sleep(SLEEP_MATCH_OVER)

    def _set_analysis_status_text(self, ai_turn: bool, pp: tuple[int, int] | None) -> None:
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
        move_time = 0.0
        if ai_turn:
            move_time = AI_MOVE_TIME
        elif (pp is not None and self.analysis_enabled) or self.analysis_enabled:
            move_time = SUGGESTION_MOVE_TIME

        analysis = self.engine.analyze_position(
            fen=fen,
            eval_time=EVAL_TIME,
            move_time=0.0 if pp is not None else move_time,
        )

        # Extract depth/nodes from engine info
        with self.state_lock:
            self.analysis_depth = analysis.get("depth", 0)
            self.analysis_nodes = analysis.get("nodes", 0)

        board_check = chess.Board(fen)
        if not ai_turn and pp is None and not board_check.is_game_over():
            if self._last_multi_pv_fen != fen:
                self._last_multi_pv_fen = fen
                def _update_multi_pv(f: str) -> None:
                    lines = self.engine.analyze_multi_pv(f, num_lines=3, time_limit=0.25)
                    with self.state_lock:
                        if self.engine.get_fen() == f:
                            self._multi_pv_lines = lines
                import threading as _th
                _th.Thread(target=_update_multi_pv, args=(fen,), daemon=True).start()
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
        ps = self._extract_promotion_suggestion(pp, suggested_move)
        if not self.analysis_enabled:
            ps = None
        with self.state_lock:
            self.analysis_eval = analysis["evaluation"]
            self.analysis_depth = analysis.get("depth", 0)
            self.analysis_nodes = analysis.get("nodes", 0)
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
