from __future__ import annotations

import threading
import time
from typing import Optional

import chess
import pygame

from engine import ChessEngine, MoveRecord, format_move_history
from ui_comp import ChessView, ViewState


class ChessController:
    AI_SIDE = chess.BLACK

    def __init__(self) -> None:
        self.engine = ChessEngine()
        self.view = ChessView(assets_dir="assets")
        self.running = True
        self.orientation_white_bottom = True
        self.selected_square: Optional[int] = None
        self.legal_targets: set[int] = set()
        self.dragging_square: Optional[int] = None
        self.drag_position: Optional[tuple[int, int]] = None
        self.pending_promotion: Optional[tuple[int, int]] = None
        self.move_list_scroll = 0

        self.state_lock = threading.Lock()
        self.analysis_enabled = False
        self.analysis_eval = 0.0
        self.analysis_text = (
            "Move hints are off. Press A to show AI suggestions."
            if self.engine.engine is not None
            else "AI unavailable for live analysis."
        )
        self.suggested_move: Optional[chess.Move] = None
        self.pending_ai_move: Optional[tuple[str, chess.Move]] = None
        self.promotion_suggestion: Optional[int] = None
        self.analysis_dirty = True
        self.ai_thinking = False
        self.play_vs_ai = False
        self.match_result: Optional[dict[str, str]] = None
        self.result_dialog_visible = False
        self.claim_dialog: Optional[dict[str, str]] = None
        self.suppressed_claim_fen: Optional[str] = None
        self.flash_message = "Board ready."
        self.flash_until = time.monotonic() + 1.8

        self.analysis_thread = threading.Thread(
            target=self._analysis_loop, name="analysis-worker", daemon=True
        )
        self.analysis_thread.start()

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

        if event.type == pygame.MOUSEMOTION:
            if self.dragging_square is not None:
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

            if self.pending_promotion:
                self._handle_promotion_click(event.pos)
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
            if self.pending_promotion:
                self.pending_promotion = None
                with self.state_lock:
                    self.promotion_suggestion = None
                    self.analysis_dirty = True
            else:
                self._clear_selection()
            return

        if key == pygame.K_r:
            self._new_game()
            return

        if key == pygame.K_u:
            self._undo_move()
            return

        if key == pygame.K_f:
            self.orientation_white_bottom = not self.orientation_white_bottom
            self._flash("Board orientation flipped.")
            return

        if key == pygame.K_c:
            if pygame.key.get_mods() & pygame.KMOD_CTRL:
                self._copy_move_history()
            else:
                self._copy_fen()
            return

        if key == pygame.K_a:
            self.analysis_enabled = (
                not self.analysis_enabled and self.engine.engine is not None
            )
            with self.state_lock:
                if not self.analysis_enabled:
                    self.suggested_move = None
                    self.promotion_suggestion = None
                self.analysis_text = (
                    "Move hints paused. Evaluation still updates in the background."
                    if not self.analysis_enabled
                    else "Move hints resumed. AI is reviewing the current position..."
                )
                self.analysis_dirty = True
            self._flash(
                "Move hints paused."
                if not self.analysis_enabled
                else "Move hints resumed."
            )
            return

        if key == pygame.K_m:
            self._toggle_ai_mode()

    def _handle_button(self, button_key: str) -> None:
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
            self._flash(
                "Game is finished. Start a new game or undo to continue.", duration=1.5
            )
            return

        if self._is_ai_turn(board):
            self._clear_selection()
            self._flash("AI is thinking...", duration=1.1)
            return

        square = self.view.screen_to_square(position, self.orientation_white_bottom)
        if square is None:
            self._clear_selection()
            return

        if self.selected_square is not None and square in self.legal_targets:
            if self._attempt_move(self.selected_square, square):
                return

        piece = board.piece_at(square)
        if piece and piece.color == board.turn:
            self.selected_square = square
            self.dragging_square = square
            self.drag_position = position
            self.legal_targets = {
                move.to_square
                for move in board.legal_moves
                if move.from_square == square
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
        if choice is None or self.pending_promotion is None:
            return

        from_square, to_square = self.pending_promotion
        if self.engine.execute_move(from_square, to_square, promotion=choice):
            self.pending_promotion = None
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
        self.move_list_scroll = self.view.get_move_list_max_scroll(
            self.engine.get_move_history()
        )

    def _after_successful_move(self) -> None:
        self._clear_selection()
        with self.state_lock:
            self.analysis_dirty = True
            self._clear_engine_suggestions_locked()
        self._scroll_move_list_to_latest()

        move_history = self.engine.get_move_history()
        if move_history:
            piece_side = (
                "AI"
                if self.play_vs_ai and self.engine.get_board_copy().turn == chess.WHITE
                else "Played"
            )
            notation = move_history[-1].san
            if piece_side == "Played":
                self._flash(f"Played {notation}")
            else:
                self._flash(f"{piece_side} played {notation}")

        self._refresh_match_result()
        if self.match_result is None:
            self._refresh_claim_dialog()
        else:
            self.claim_dialog = None

    def _new_game(self) -> None:
        self.engine.reset_engine()
        self.pending_promotion = None
        self._clear_selection()
        self._clear_match_result()
        with self.state_lock:
            self.analysis_eval = 0.0
            self._clear_engine_suggestions_locked()
            self.analysis_text = (
                "AI is reviewing the opening position..."
                if self.analysis_enabled
                else "Move hints are off. Press A to show AI suggestions."
            )
            self.analysis_dirty = True
        self.move_list_scroll = 0
        self._refresh_claim_dialog()
        self._flash(
            "New game loaded against AI."
            if self.play_vs_ai
            else "New local game loaded."
        )

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

    def _format_move_history(self, move_history: list[MoveRecord]) -> str:
        return format_move_history(move_history)

    def _clear_selection(self) -> None:
        self.selected_square = None
        self.legal_targets.clear()
        self.dragging_square = None
        self.drag_position = None

    def _flash(self, message: str, duration: float = 2.2) -> None:
        self.flash_message = message
        self.flash_until = time.monotonic() + duration

    def _dialog_is_visible(self) -> bool:
        return self._get_active_dialog() is not None

    def _get_active_dialog(self) -> Optional[dict[str, str]]:
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

    def _get_board_outcome(
        self, board: Optional[chess.Board] = None
    ) -> Optional[chess.Outcome]:
        board = board or self.engine.get_board_copy()
        return board.outcome(claim_draw=False)

    def _match_is_over(self, board: Optional[chess.Board] = None) -> bool:
        board = board or self.engine.get_board_copy()
        automatic_outcome = self._get_board_outcome(board)
        if automatic_outcome is not None:
            return True
        return (
            self.match_result is not None
            and self.match_result.get("fen") == board.fen()
        )

    def _draw_claim_reason(self, board: chess.Board) -> Optional[str]:
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

    def _build_result_payload(
        self, board: chess.Board, outcome: chess.Outcome
    ) -> dict[str, str]:
        termination = outcome.termination
        title = "Game Over"
        message = "The game has finished."

        if termination == chess.Termination.CHECKMATE:
            winner = (
                self._describe_side(outcome.winner)
                if outcome.winner is not None
                else "Unknown"
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
                message = (
                    f"The game ended by {termination.name.replace('_', ' ').lower()}."
                )
            else:
                winner = self._describe_side(outcome.winner)
                message = (
                    f"{winner} wins by {termination.name.replace('_', ' ').lower()}."
                )

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
            if (
                self.match_result is not None
                and self.match_result.get("source") == "automatic"
            ):
                self.match_result = None
                self.result_dialog_visible = False
            return

        payload = self._build_result_payload(board, outcome)
        if not self.match_result or self.match_result.get("fen") != payload["fen"]:
            self.match_result = payload
            self.result_dialog_visible = True
        else:
            self.match_result = payload

    def _build_claim_dialog(self, board: chess.Board) -> Optional[dict[str, str]]:
        reason = self._draw_claim_reason(board)
        if reason is None:
            return None

        claimant = (
            "You"
            if self.play_vs_ai
            else ("White" if board.turn == chess.WHITE else "Black")
        )
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
        if (
            self.suppressed_claim_fen is not None
            and self.suppressed_claim_fen != board.fen()
        ):
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

        claimant = (
            "You"
            if self.play_vs_ai
            else ("White" if board.turn == chess.WHITE else "Black")
        )
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
        if not self.play_vs_ai and self.engine.engine is None:
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
                "AI is ready to play Black."
                if self.play_vs_ai
                else "Local 1v1 mode is active."
            )
        self._flash("Vs AI enabled." if self.play_vs_ai else "Switched to local 1v1.")
        self._refresh_match_result()
        if self.match_result is None:
            self._refresh_claim_dialog()

    def _is_ai_turn(self, board: Optional[chess.Board] = None) -> bool:
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
        if (
            piece
            and piece.piece_type == chess.PAWN
            and chess.square_rank(move.to_square) in (0, 7)
        ):
            promoted_move = chess.Move(
                move.from_square, move.to_square, promotion=chess.QUEEN
            )
            if promoted_move in board.legal_moves:
                return promoted_move
        return move

    def _extract_promotion_suggestion(
        self,
        pending_promotion: Optional[tuple[int, int]],
        move: Optional[chess.Move],
    ) -> Optional[int]:
        if pending_promotion is None or move is None or move.promotion is None:
            return None

        from_square, to_square = pending_promotion
        if move.from_square == from_square and move.to_square == to_square:
            return move.promotion
        return None

    def _compose_status(self, board: chess.Board) -> str:
        if time.monotonic() < self.flash_until:
            return self.flash_message

        if (
            self.match_result is not None
            and self.match_result.get("fen") == board.fen()
        ):
            return self.match_result["message"]
        if (
            self.claim_dialog is not None
            and self.claim_dialog.get("fen") == board.fen()
        ):
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

    def _build_view_state(self) -> ViewState:
        board = self.engine.get_board_copy()
        self._clamp_move_list_scroll()
        white_captured_keys, black_captured_keys = self.engine.get_captured_piece_keys()
        with self.state_lock:
            evaluation = self.analysis_eval
            analysis_text = self.analysis_text
            suggested_move = self.suggested_move
            promotion_suggestion = self.promotion_suggestion
        active_dialog = self._get_active_dialog()

        if suggested_move and suggested_move not in board.legal_moves:
            suggested_move = None

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
            mode_text=(
                "Mode: Vs AI (you play White)" if self.play_vs_ai else "Mode: Local 1v1"
            ),
            button_labels={
                "mode_toggle": (
                    "Playing: Vs AI" if self.play_vs_ai else "Playing: Local 1v1"
                )
            },
            result_visible=active_dialog is not None,
            result_title=active_dialog["title"] if active_dialog else "",
            result_message=active_dialog["message"] if active_dialog else "",
            result_hint=active_dialog["hint"] if active_dialog else "",
            result_primary_key=active_dialog["primary_key"] if active_dialog else "",
            result_primary_label=(
                active_dialog["primary_label"] if active_dialog else ""
            ),
            result_secondary_key=(
                active_dialog["secondary_key"] if active_dialog else ""
            ),
            result_secondary_label=(
                active_dialog["secondary_label"] if active_dialog else ""
            ),
            white_captured_keys=white_captured_keys,
            black_captured_keys=black_captured_keys,
        )

    def _analysis_loop(self) -> None:
        if self.engine.engine is None:
            return

        last_fen: Optional[str] = None
        while self.running:
            fen = self.engine.get_fen()
            board = chess.Board(fen)
            match_over = self._match_is_over(board)
            ai_turn = self._is_ai_turn(board)
            pending_promotion = self.pending_promotion
            with self.state_lock:
                dirty = self.analysis_dirty or ai_turn

            if match_over:
                self._refresh_match_result()
                with self.state_lock:
                    self.analysis_dirty = False
                    self._clear_engine_suggestions_locked()
                    self.analysis_text = (
                        self.match_result["message"]
                        if self.match_result
                        else "Game over."
                    )
                last_fen = fen
                time.sleep(0.12)
                continue

            if not dirty and fen == last_fen:
                time.sleep(0.1)
                continue

            with self.state_lock:
                self.ai_thinking = ai_turn
                self.analysis_text = (
                    "AI is thinking about its move..."
                    if ai_turn
                    else (
                        "AI is checking the promotion choice..."
                        if pending_promotion is not None and self.analysis_enabled
                        else "Promotion suggestion is paused. Press A to enable hints."
                        if pending_promotion is not None
                        else "AI is reviewing the current position..."
                        if self.analysis_enabled
                        else "Evaluation updated. Move hints are paused."
                    )
                )

            suggestion_time = 0.0
            if ai_turn:
                suggestion_time = 0.7
            elif pending_promotion is not None and self.analysis_enabled:
                suggestion_time = 0.45
            elif self.analysis_enabled:
                suggestion_time = 0.45

            analysis = self.engine.analyze_position(
                fen=fen,
                eval_time=0.08,
                move_time=0.0 if pending_promotion is not None else suggestion_time,
            )
            if pending_promotion is not None and self.analysis_enabled:
                from_square, to_square = pending_promotion
                promotion_move = self.engine.suggest_promotion_choice(
                    fen, from_square, to_square
                )
                if promotion_move is not None:
                    analysis["suggestion"] = promotion_move
            suggested_move = analysis["suggestion"]

            if board.is_game_over():
                next_text = "Game over. Analysis complete."
            elif ai_turn and suggested_move and suggested_move in board.legal_moves:
                next_text = f"AI found {board.san(suggested_move)}"
            elif (
                pending_promotion is not None
                and suggested_move
                and suggested_move in board.legal_moves
            ):
                next_text = f"AI suggests {board.san(suggested_move)}"
            elif pending_promotion is not None and not self.analysis_enabled:
                next_text = "Promotion suggestion is paused. Press A to enable hints."
            elif pending_promotion is not None:
                next_text = "Promotion choice pending."
            elif (
                self.analysis_enabled
                and suggested_move
                and suggested_move in board.legal_moves
            ):
                next_text = f"Best move: {board.san(suggested_move)}"
            elif not self.analysis_enabled:
                next_text = "Evaluation live. Press A to show move hints again."
            else:
                next_text = "Evaluation live. No clear move suggestion right now."

            if self.engine.get_fen() == fen:
                promotion_suggestion = self._extract_promotion_suggestion(
                    pending_promotion, suggested_move
                )
                if not self.analysis_enabled:
                    promotion_suggestion = None
                with self.state_lock:
                    self.analysis_eval = analysis["evaluation"]
                    self.suggested_move = (
                        suggested_move
                        if self.analysis_enabled and not ai_turn
                        else None
                    )
                    self.promotion_suggestion = promotion_suggestion
                    self.analysis_text = next_text
                    self.analysis_dirty = False
                    self.ai_thinking = False
                    self.pending_ai_move = (
                        (fen, suggested_move)
                        if ai_turn
                        and self.play_vs_ai
                        and suggested_move
                        and suggested_move in board.legal_moves
                        else None
                    )
                last_fen = fen

            time.sleep(0.06)


def main() -> None:
    ChessController().run()


if __name__ == "__main__":
    main()
