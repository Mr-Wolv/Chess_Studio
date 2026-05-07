from __future__ import annotations

from dataclasses import dataclass
import os
import sys
from pathlib import Path
from typing import Optional

import chess
import pygame
from engine import MoveRecord


@dataclass(frozen=True)
class UIButton:
    key: str
    label: str
    rect: pygame.Rect
    accent: tuple[int, int, int]


@dataclass
class PromotionMenu:
    backdrop: pygame.Rect
    options: list[tuple[int, pygame.Rect]]


@dataclass
class ViewState:
    board: chess.Board
    move_history: list[MoveRecord]
    move_scroll_offset: int
    selected_square: Optional[int]
    legal_targets: set[int]
    last_move: Optional[chess.Move]
    suggested_move: Optional[chess.Move]
    evaluation: float
    status_text: str
    analysis_text: str
    orientation_white_bottom: bool
    dragging_square: Optional[int]
    drag_position: Optional[tuple[int, int]]
    pending_promotion: bool
    promotion_suggestion: Optional[int]
    promotion_suggestion_enabled: bool
    fen: str
    mode_text: str
    button_labels: dict[str, str]
    result_visible: bool
    result_title: str
    result_message: str
    result_hint: str
    result_primary_key: str
    result_primary_label: str
    result_secondary_key: str
    result_secondary_label: str
    white_captured_keys: list[str]
    black_captured_keys: list[str]


class ChessView:
    BG_TOP = (20, 28, 41)
    BG_BOTTOM = (10, 14, 23)
    PANEL = (21, 31, 47)
    PANEL_ALT = (27, 38, 58)
    PANEL_BORDER = (61, 83, 120)
    TEXT_PRIMARY = (247, 250, 255)
    TEXT_MUTED = (189, 201, 224)
    BOARD_LIGHT = (233, 221, 200)
    BOARD_DARK = (110, 146, 123)
    ACCENT = (80, 167, 255)
    ACCENT_SOFT = (130, 201, 255)
    HIGHLIGHT = (255, 211, 94)
    MOVE_HINT = (53, 121, 214)
    DANGER = (214, 95, 95)
    SUCCESS = (77, 195, 134)

    def __init__(
        self,
        assets_dir: str | Path = "assets",
        window_size: Optional[tuple[int, int]] = None,
    ):
        self._enable_high_dpi()
        pygame.init()
        if window_size is None:
            window_size = self._preferred_window_size()
        self.screen = pygame.display.set_mode(window_size, pygame.RESIZABLE)
        pygame.display.set_caption("Chess Studio")
        self.clock = pygame.time.Clock()
        self.assets_dir = self._resolve_assets_dir(assets_dir)
        self.fonts: dict[str, pygame.font.Font] = {}
        self.layout: dict[str, pygame.Rect] = {}
        self.buttons: list[UIButton] = []
        self.result_buttons: list[UIButton] = []
        self.promotion_menu: Optional[PromotionMenu] = None
        self.base_images: dict[str, pygame.Surface] = {}
        self.scaled_images: dict[tuple[str, int], pygame.Surface] = {}
        self._load_piece_images()
        self._init_clipboard()
        self.rebuild_layout(*window_size)

    def _resolve_assets_dir(self, assets_dir: str | Path) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / Path(assets_dir) # type: ignore
        return Path(assets_dir)

    def _enable_high_dpi(self) -> None:
        if os.name != "nt":
            return

        try:
            import ctypes

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    def _preferred_window_size(self) -> tuple[int, int]:
        display_info = pygame.display.Info()
        width = min(1600, max(1260, display_info.current_w - 180))
        height = min(940, max(820, display_info.current_h - 180))
        return width, height

    def _init_clipboard(self) -> None:
        try:
            pygame.scrap.init()
        except pygame.error:
            pass

    def _load_piece_images(self) -> None:
        for color in ("w", "b"):
            for piece_code in ("K", "Q", "R", "B", "N", "P"):
                key = f"{color}{piece_code}"
                path = self.assets_dir / f"{key}.png"
                self.base_images[key] = pygame.image.load(str(path)).convert_alpha()

    def rebuild_layout(self, width: int, height: int) -> None:
        outer_pad = 28
        column_gap = 26
        panel_gap = 18
        sidebar_min_width = 430
        morgue_width = 168
        morgue_gap = 18
        board_soft_cap = 920 if height >= 980 else height - 84
        board_size = width - (
            outer_pad * 2 + column_gap + sidebar_min_width + morgue_width + morgue_gap
        )
        board_size = min(board_size, height - outer_pad * 2, board_soft_cap)
        board_size = max(board_size, 520)

        morgue_x = outer_pad
        board_x = morgue_x + morgue_width + morgue_gap
        board_y = outer_pad
        sidebar_x = board_x + board_size + column_gap
        sidebar_width = max(sidebar_min_width, width - sidebar_x - outer_pad)

        header_height = 88
        controls_height = 148
        eval_height = 106
        status_height = 148
        fen_height = 128

        header_rect = pygame.Rect(sidebar_x, outer_pad, sidebar_width, header_height)
        controls_rect = pygame.Rect(
            sidebar_x, header_rect.bottom + panel_gap, sidebar_width, controls_height
        )
        eval_rect = pygame.Rect(
            sidebar_x, controls_rect.bottom + panel_gap, sidebar_width, eval_height
        )
        status_rect = pygame.Rect(
            sidebar_x, eval_rect.bottom + panel_gap, sidebar_width, status_height
        )
        fen_rect = pygame.Rect(
            sidebar_x, height - outer_pad - fen_height, sidebar_width, fen_height
        )
        moves_top = status_rect.bottom + panel_gap
        available_move_space = fen_rect.y - moves_top - panel_gap
        move_list_height = max(0, available_move_space)
        moves_rect = pygame.Rect(sidebar_x, moves_top, sidebar_width, move_list_height)

        self.layout = {
            "morgue": pygame.Rect(morgue_x, board_y, morgue_width, board_size),
            "board": pygame.Rect(board_x, board_y, board_size, board_size),
            "header": header_rect,
            "controls": controls_rect,
            "eval": eval_rect,
            "status": status_rect,
            "moves": moves_rect,
            "fen": fen_rect,
        }

        control_area = self.layout["controls"].inflate(-10, -12)
        button_width = int((control_area.width - 18) / 2)
        button_height = 36
        button_gap = 10
        left_x = control_area.x
        right_x = control_area.x + button_width + button_gap
        top_y = control_area.y
        middle_y = top_y + button_height + 10
        bottom_y = middle_y + button_height + 10
        self.buttons = [
            UIButton(
                "new_game",
                "New Game",
                pygame.Rect(left_x, top_y, button_width, button_height),
                self.SUCCESS,
            ),
            UIButton(
                "undo",
                "Undo",
                pygame.Rect(right_x, top_y, button_width, button_height),
                self.HIGHLIGHT,
            ),
            UIButton(
                "flip_board",
                "Flip Board",
                pygame.Rect(left_x, middle_y, button_width, button_height),
                self.ACCENT,
            ),
            UIButton(
                "copy_fen",
                "Copy FEN",
                pygame.Rect(right_x, middle_y, button_width, button_height),
                self.ACCENT_SOFT,
            ),
            UIButton(
                "mode_toggle",
                "Mode: Local 1v1",
                pygame.Rect(left_x, bottom_y, control_area.width, button_height),
                self.SUCCESS,
            ),
        ]

        self.fonts = {
            "title": pygame.font.SysFont("Segoe UI Semibold", 40),
            "heading": pygame.font.SysFont("Segoe UI Semibold", 24),
            "body": pygame.font.SysFont("Segoe UI", 21),
            "small": pygame.font.SysFont("Segoe UI", 17),
            "tiny": pygame.font.SysFont("Consolas", 16),
            "button": pygame.font.SysFont("Segoe UI Semibold", 18),
            "coord": pygame.font.SysFont("Segoe UI", 15),
        }
        self.scaled_images.clear()

    def tick(self, fps: int = 60) -> int:
        return self.clock.tick(fps)

    def handle_resize(self, size: tuple[int, int]) -> None:
        width = max(size[0], 1260)
        height = max(size[1], 820)
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.rebuild_layout(width, height)

    def button_at(self, position: tuple[int, int]) -> Optional[str]:
        for button in self.buttons:
            if button.rect.collidepoint(position):
                return button.key
        return None

    def point_in_panel(self, panel_key: str, position: tuple[int, int]) -> bool:
        rect = self.layout.get(panel_key)
        return rect.collidepoint(position) if rect else False

    def get_move_list_visible_rows(self) -> int:
        rect = self.layout["moves"]
        line_height = 24
        return max(1, (rect.height - 64) // line_height)

    def get_move_list_max_scroll(self, move_history: list[MoveRecord]) -> int:
        total_rows = (len(move_history) + 1) // 2
        visible_rows = self.get_move_list_visible_rows()
        return max(0, total_rows - visible_rows)

    def screen_to_square(
        self, position: tuple[int, int], white_bottom: bool
    ) -> Optional[int]:
        board_rect = self.layout["board"]
        if not board_rect.collidepoint(position):
            return None

        cell = board_rect.width / 8
        file_index = int((position[0] - board_rect.x) / cell)
        rank_index = int((position[1] - board_rect.y) / cell)

        file = file_index if white_bottom else 7 - file_index
        rank = 7 - rank_index if white_bottom else rank_index

        if not (0 <= file <= 7 and 0 <= rank <= 7):
            return None
        return chess.square(file, rank)

    def square_to_rect(self, square: int, white_bottom: bool) -> pygame.Rect:
        board_rect = self.layout["board"]
        cell = board_rect.width / 8
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        draw_file = file if white_bottom else 7 - file
        draw_rank = 7 - rank if white_bottom else rank
        return pygame.Rect(
            int(board_rect.x + draw_file * cell),
            int(board_rect.y + draw_rank * cell),
            int(cell),
            int(cell),
        )

    def promotion_choice_at(self, position: tuple[int, int]) -> Optional[int]:
        if not self.promotion_menu:
            return None
        for piece_type, rect in self.promotion_menu.options:
            if rect.collidepoint(position):
                return piece_type
        return None

    def copy_to_clipboard(self, text: str) -> bool:
        try:
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
            return True
        except pygame.error:
            return False

    def _fit_single_line(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> str:
        if font.size(text)[0] <= max_width:
            return text

        ellipsis = "..."
        trimmed = text
        while trimmed and font.size(f"{trimmed}{ellipsis}")[0] > max_width:
            trimmed = trimmed[:-1]
        return f"{trimmed}{ellipsis}" if trimmed else ellipsis

    def _draw_wrapped_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        rect: pygame.Rect,
        line_gap: int = 6,
        max_lines: Optional[int] = None,
    ) -> int:
        words = text.split()
        if not words:
            return 0

        lines: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if font.size(candidate)[0] <= rect.width:
                current = candidate
                continue

            if current:
                lines.append(current)
                if max_lines is not None and len(lines) >= max_lines:
                    break
                current = word
            else:
                lines.append(self._fit_single_line(word, font, rect.width))
                if max_lines is not None and len(lines) >= max_lines:
                    break
                current = ""

        if current and (max_lines is None or len(lines) < max_lines):
            lines.append(current)

        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]

        if max_lines is not None and len(lines) == max_lines and words:
            lines[-1] = self._fit_single_line(lines[-1], font, rect.width)

        y = rect.y
        line_height = font.get_linesize()
        for line in lines:
            surface = font.render(line, True, color)
            self.screen.blit(surface, (rect.x, y))
            y += line_height + line_gap
        return y - rect.y

    def result_dialog_action_at(self, position: tuple[int, int]) -> Optional[str]:
        for button in self.result_buttons:
            if button.rect.collidepoint(position):
                return button.key
        return None

    def draw(self, state: ViewState) -> None:
        self._draw_background()
        self._draw_panel(self.layout["morgue"])
        self._draw_panel(self.layout["header"])
        self._draw_panel(self.layout["controls"])
        self._draw_panel(self.layout["eval"])
        self._draw_panel(self.layout["status"])
        self._draw_panel(self.layout["moves"])
        self._draw_panel(self.layout["fen"])
        self._draw_morgue(state)
        self._draw_header()
        self._draw_buttons(state)
        self._draw_eval_panel(state)
        self._draw_status_panel(state)
        self._draw_move_history(
            state.move_history,
            state.move_scroll_offset,
        )
        self._draw_board(state)
        self._draw_fen_panel(state.fen)
        if state.pending_promotion:
            self._draw_promotion_menu(state)
            self.result_buttons = []
        elif state.result_visible:
            self._draw_result_dialog(state)
            self.promotion_menu = None
        else:
            self.promotion_menu = None
            self.result_buttons = []
        pygame.display.flip()

    def _draw_background(self) -> None:
        width, height = self.screen.get_size()
        for y in range(height):
            blend = y / max(height - 1, 1)
            color = tuple(
                int(self.BG_TOP[index] * (1 - blend) + self.BG_BOTTOM[index] * blend)
                for index in range(3)
            )
            pygame.draw.line(self.screen, color, (0, y), (width, y))

        board_rect = self.layout["board"]
        halo = pygame.Surface(
            (board_rect.width + 80, board_rect.height + 80), pygame.SRCALPHA
        )
        pygame.draw.ellipse(halo, (57, 105, 178, 44), halo.get_rect())
        self.screen.blit(halo, (board_rect.x - 40, board_rect.y - 40))

    def _draw_panel(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=24)
        pygame.draw.rect(self.screen, self.PANEL_BORDER, rect, 1, border_radius=24)

    def _draw_header(self) -> None:
        rect = self.layout["header"]
        title = self.fonts["title"].render("Chess Studio", True, self.TEXT_PRIMARY)
        title_y = rect.y + (rect.height - title.get_height()) // 2 - 2
        self.screen.blit(title, (rect.x + 22, title_y))

    def _draw_morgue(self, state: ViewState) -> None:
        rect = self.layout["morgue"]
        top_rect = pygame.Rect(
            rect.x + 12, rect.y + 12, rect.width - 24, rect.height // 2 - 18
        )
        bottom_rect = pygame.Rect(
            rect.x + 12, rect.centery + 6, rect.width - 24, rect.height // 2 - 18
        )
        self._draw_morgue_section(top_rect, "Black Captured", state.black_captured_keys)
        self._draw_morgue_section(
            bottom_rect, "White Captured", state.white_captured_keys
        )

    def _draw_morgue_section(
        self, rect: pygame.Rect, title: str, captured_keys: list[str]
    ) -> None:
        pygame.draw.rect(self.screen, self.PANEL_ALT, rect, border_radius=18)
        pygame.draw.rect(self.screen, self.PANEL_BORDER, rect, 1, border_radius=18)
        heading = self.fonts["small"].render(title, True, self.TEXT_PRIMARY)
        self.screen.blit(heading, (rect.x + 12, rect.y + 10))

        body_rect = pygame.Rect(
            rect.x + 10, rect.y + 40, rect.width - 20, rect.height - 50
        )
        if not captured_keys:
            placeholder = self.fonts["small"].render("None", True, self.TEXT_MUTED)
            self.screen.blit(placeholder, placeholder.get_rect(center=body_rect.center))
            return

        ordered_keys = self._sort_captured_keys(captured_keys)
        columns = 3
        cell_size = min((body_rect.width - 8 * (columns - 1)) // columns, 38)
        cell_size = max(cell_size, 28)
        gap = 8
        for index, piece_key in enumerate(ordered_keys):
            row = index // columns
            col = index % columns
            x = body_rect.x + col * (cell_size + gap)
            y = body_rect.y + row * (cell_size + gap)
            piece_rect = pygame.Rect(x, y, cell_size, cell_size)
            if piece_rect.bottom > body_rect.bottom:
                break
            image = self._scaled_piece(piece_key, piece_rect.width)
            image_rect = image.get_rect(center=piece_rect.center)
            self.screen.blit(image, image_rect)

    def _sort_captured_keys(self, captured_keys: list[str]) -> list[str]:
        piece_order = {"Q": 0, "R": 1, "B": 2, "N": 3, "P": 4, "K": 5}
        return sorted(captured_keys, key=lambda key: (piece_order.get(key[1], 99), key))

    def _draw_buttons(self, state: ViewState) -> None:
        for button in self.buttons:
            shadow = button.rect.move(0, 3)
            pygame.draw.rect(self.screen, (0, 0, 0, 50), shadow, border_radius=16)
            pygame.draw.rect(self.screen, self.PANEL_ALT, button.rect, border_radius=16)
            pygame.draw.rect(
                self.screen, button.accent, button.rect, 2, border_radius=16
            )
            label_text = state.button_labels.get(button.key, button.label)
            label = self.fonts["button"].render(
                self._fit_single_line(
                    label_text, self.fonts["button"], button.rect.width - 26
                ),
                True,
                self.TEXT_PRIMARY,
            )
            self.screen.blit(label, label.get_rect(center=button.rect.center))

    def _draw_eval_panel(self, state: ViewState) -> None:
        rect = self.layout["eval"]
        heading = self.fonts["heading"].render("Engine Pulse", True, self.TEXT_PRIMARY)
        self.screen.blit(heading, (rect.x + 18, rect.y + 12))

        bar_rect = pygame.Rect(rect.x + 18, rect.y + 48, rect.width - 36, 20)
        pygame.draw.rect(self.screen, self.PANEL_ALT, bar_rect, border_radius=9)
        clamped = max(-8.0, min(8.0, state.evaluation))
        fill_ratio = (clamped + 8.0) / 16.0
        fill_rect = pygame.Rect(
            bar_rect.x,
            bar_rect.y,
            max(12, int(bar_rect.width * fill_ratio)),
            bar_rect.height,
        )
        fill_color = self.SUCCESS if clamped >= 0 else self.DANGER
        pygame.draw.rect(self.screen, fill_color, fill_rect, border_radius=9)

        score_text = f"{state.evaluation:+.2f}"
        score = self.fonts["body"].render(score_text, True, self.TEXT_PRIMARY)
        self.screen.blit(score, (bar_rect.right - score.get_width(), rect.y + 10))
        self._draw_wrapped_text(
            state.analysis_text,
            self.fonts["small"],
            self.TEXT_MUTED,
            pygame.Rect(rect.x + 18, rect.y + 76, rect.width - 36, rect.height - 82),
            line_gap=2,
            max_lines=2,
        )

    def _draw_status_panel(self, state: ViewState) -> None:
        rect = self.layout["status"]
        heading = self.fonts["heading"].render("Position", True, self.TEXT_PRIMARY)
        self.screen.blit(heading, (rect.x + 18, rect.y + 12))

        status_rect = pygame.Rect(rect.x + 18, rect.y + 46, rect.width - 36, 36)
        self._draw_wrapped_text(
            state.status_text,
            self.fonts["body"],
            self.TEXT_PRIMARY,
            status_rect,
            line_gap=3,
            max_lines=2,
        )

        shortcut_label = self.fonts["small"].render(
            "Keyboard Shortcuts", True, self.TEXT_PRIMARY
        )
        label_y = status_rect.bottom + 6
        if label_y + shortcut_label.get_height() + 2 < rect.bottom - 4:
            self.screen.blit(shortcut_label, (rect.x + 18, label_y))

            shortcut_y = label_y + shortcut_label.get_height() + 4
            shortcut_rect = pygame.Rect(rect.x + 18, shortcut_y, rect.width - 36, 26)
            if shortcut_y + shortcut_rect.height <= rect.bottom - 4:
                pygame.draw.rect(
                    self.screen, self.PANEL_ALT, shortcut_rect, border_radius=16
                )
                pygame.draw.rect(
                    self.screen, self.PANEL_BORDER, shortcut_rect, 1, border_radius=16
                )

                shortcut_text = "R=New, U=Undo, F=Flip, A=Hint, M=Mode, C=Copy FEN, Ctrl+C=Copy Moves"
                shortcut_surface = self.fonts["small"].render(
                    self._fit_single_line(
                        shortcut_text, self.fonts["small"], shortcut_rect.width - 20
                    ),
                    True,
                    self.TEXT_MUTED,
                )
                self.screen.blit(
                    shortcut_surface,
                    (
                        shortcut_rect.x + 10,
                        shortcut_rect.y
                        + (shortcut_rect.height - shortcut_surface.get_height()) // 2,
                    ),
                )

    def _draw_move_history(
        self,
        move_history: list[MoveRecord],
        scroll_offset: int,
    ) -> None:
        rect = self.layout["moves"]
        if rect.height < 60:
            return

        heading = self.fonts["heading"].render("Move List", True, self.TEXT_PRIMARY)
        self.screen.blit(heading, (rect.x + 18, rect.y + 12))

        list_rect = pygame.Rect(
            rect.x + 10, rect.y + 44, rect.width - 20, rect.height - 56
        )
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(list_rect)

        line_y = list_rect.y + 4
        line_height = 24
        visible_rows = max(1, (list_rect.height - 8) // line_height)
        number_x = list_rect.x + 8
        white_x = list_rect.x + 60
        black_x = list_rect.x + list_rect.width // 2 + 4
        white_width = max(74, list_rect.width // 2 - 76)
        black_width = max(74, list_rect.right - black_x - 8)
        row_font = self.fonts["small"]

        rows: list[tuple[str, str, str]] = []
        for index in range(0, len(move_history), 2):
            move_number = f"{index // 2 + 1}."
            white_move = move_history[index].san
            black_move = (
                move_history[index + 1].san
                if index + 1 < len(move_history)
                else ""
            )
            rows.append((move_number, white_move, black_move))

        max_scroll = max(0, len(rows) - visible_rows)
        start_index = min(max(scroll_offset, 0), max_scroll)
        visible_rows_data = rows[start_index : start_index + visible_rows]
        for row_index, (move_number, white_move, black_move) in enumerate(
            visible_rows_data, start=start_index
        ):
            num_surface = row_font.render(move_number, True, self.TEXT_MUTED)
            white_surface = row_font.render(
                self._fit_single_line(white_move, row_font, white_width),
                True,
                self.TEXT_PRIMARY,
            )
            black_surface = row_font.render(
                self._fit_single_line(black_move, row_font, black_width),
                True,
                self.TEXT_MUTED,
            )
            self.screen.blit(num_surface, (number_x, line_y))
            self.screen.blit(white_surface, (white_x, line_y))
            self.screen.blit(black_surface, (black_x, line_y))
            line_y += line_height

        self.screen.set_clip(previous_clip)

        if max_scroll > 0:
            track_rect = pygame.Rect(rect.right - 12, rect.y + 54, 4, rect.height - 72)
            pygame.draw.rect(self.screen, self.PANEL_ALT, track_rect, border_radius=4)
            thumb_height = max(
                28, int(track_rect.height * (visible_rows / max(len(rows), 1)))
            )
            thumb_range = max(1, track_rect.height - thumb_height)
            thumb_y = track_rect.y + int((start_index / max_scroll) * thumb_range)
            thumb_rect = pygame.Rect(
                track_rect.x, thumb_y, track_rect.width, thumb_height
            )
            pygame.draw.rect(self.screen, self.ACCENT_SOFT, thumb_rect, border_radius=4)

    def _draw_fen_panel(self, fen: str) -> None:
        rect = self.layout["fen"]
        heading = self.fonts["heading"].render("FEN Snapshot", True, self.TEXT_PRIMARY)
        self.screen.blit(heading, (rect.x + 18, rect.y + 12))

        body_rect = pygame.Rect(
            rect.x + 18, rect.y + 48, rect.width - 36, rect.height - 62
        )
        pygame.draw.rect(self.screen, self.PANEL_ALT, body_rect, border_radius=16)

        lines = self._wrap_text(fen, self.fonts["tiny"], body_rect.width - 20)
        y = body_rect.y + 12
        for line in lines[:4]:
            surface = self.fonts["tiny"].render(line, True, self.TEXT_MUTED)
            self.screen.blit(surface, (body_rect.x + 10, y))
            y += 20

    def _draw_board(self, state: ViewState) -> None:
        board_rect = self.layout["board"]
        frame_rect = board_rect.inflate(12, 12)
        pygame.draw.rect(self.screen, (7, 10, 16), frame_rect, border_radius=24)
        pygame.draw.rect(
            self.screen, self.PANEL_BORDER, frame_rect, 2, border_radius=24
        )

        for square in chess.SQUARES:
            square_rect = self.square_to_rect(square, state.orientation_white_bottom)
            is_light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 0
            color = self.BOARD_LIGHT if is_light else self.BOARD_DARK
            pygame.draw.rect(self.screen, color, square_rect)

            if state.last_move and square in {
                state.last_move.from_square,
                state.last_move.to_square,
            }:
                overlay = pygame.Surface(square_rect.size, pygame.SRCALPHA)
                overlay.fill((255, 220, 84, 92))
                self.screen.blit(overlay, square_rect.topleft)

            if state.selected_square == square:
                pygame.draw.rect(
                    self.screen, self.ACCENT, square_rect, 4, border_radius=8
                )

            if square in state.legal_targets:
                overlay = pygame.Surface(square_rect.size, pygame.SRCALPHA)
                if state.board.piece_at(square):
                    pygame.draw.rect(
                        overlay,
                        (255, 116, 116, 120),
                        overlay.get_rect(),
                        6,
                        border_radius=12,
                    )
                else:
                    pygame.draw.circle(
                        overlay,
                        (32, 74, 138, 130),
                        (overlay.get_width() // 2, overlay.get_height() // 2),
                        max(10, overlay.get_width() // 7),
                    )
                self.screen.blit(overlay, square_rect.topleft)

        self._draw_coordinates(state.orientation_white_bottom)

        if state.suggested_move and state.suggested_move in state.board.legal_moves:
            self._draw_suggestion_arrow(
                state.suggested_move, state.orientation_white_bottom
            )

        for square in chess.SQUARES:
            if square == state.dragging_square:
                continue
            piece = state.board.piece_at(square)
            if piece:
                self._draw_piece(
                    piece, self.square_to_rect(square, state.orientation_white_bottom)
                )

        if state.dragging_square is not None and state.drag_position is not None:
            piece = state.board.piece_at(state.dragging_square)
            if piece:
                rect = self.square_to_rect(
                    state.dragging_square, state.orientation_white_bottom
                )
                rect.center = state.drag_position
                self._draw_piece(piece, rect)

    def _draw_piece(self, piece: chess.Piece, rect: pygame.Rect) -> None:
        key = f"{'w' if piece.color == chess.WHITE else 'b'}{piece.symbol().upper()}"
        image = self._scaled_piece(key, rect.width)
        image_rect = image.get_rect(center=rect.center)
        self.screen.blit(image, image_rect)

    def _scaled_piece(self, key: str, square_size: int) -> pygame.Surface:
        cache_key = (key, square_size)
        if cache_key not in self.scaled_images:
            image = self.base_images[key]
            target = int(square_size * 0.82)
            self.scaled_images[cache_key] = pygame.transform.smoothscale(
                image, (target, target)
            )
        return self.scaled_images[cache_key]

    def _draw_coordinates(self, white_bottom: bool) -> None:
        board_rect = self.layout["board"]
        cell = board_rect.width / 8
        files = "abcdefgh" if white_bottom else "hgfedcba"
        ranks = "12345678" if not white_bottom else "87654321"

        for idx, file_char in enumerate(files):
            label = self.fonts["coord"].render(file_char, True, (46, 58, 76))
            x = int(board_rect.x + idx * cell + cell - label.get_width() - 6)
            y = int(board_rect.bottom - label.get_height() - 4)
            self.screen.blit(label, (x, y))

        for idx, rank_char in enumerate(ranks):
            label = self.fonts["coord"].render(rank_char, True, (46, 58, 76))
            x = int(board_rect.x + 6)
            y = int(board_rect.y + idx * cell + 4)
            self.screen.blit(label, (x, y))

    def _draw_suggestion_arrow(self, move: chess.Move, white_bottom: bool) -> None:
        start = self.square_to_rect(move.from_square, white_bottom).center
        end = self.square_to_rect(move.to_square, white_bottom).center
        pygame.draw.line(self.screen, (56, 190, 255), start, end, 7)
        pygame.draw.circle(self.screen, (56, 190, 255), end, 10)

    def _draw_promotion_menu(self, state: ViewState) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((3, 8, 14, 168))
        self.screen.blit(overlay, (0, 0))

        board_rect = self.layout["board"]
        panel_rect = pygame.Rect(0, 0, 412, 206)
        panel_rect.center = board_rect.center
        pygame.draw.rect(self.screen, self.PANEL, panel_rect, border_radius=24)
        pygame.draw.rect(self.screen, self.ACCENT_SOFT, panel_rect, 2, border_radius=24)

        title = self.fonts["heading"].render(
            "Choose Promotion", True, self.TEXT_PRIMARY
        )
        self.screen.blit(title, (panel_rect.x + 26, panel_rect.y + 16))
        self._draw_wrapped_text(
            self._promotion_hint_text(
                state.promotion_suggestion, state.promotion_suggestion_enabled
            ),
            self.fonts["small"],
            self.TEXT_MUTED,
            pygame.Rect(
                panel_rect.x + 26, panel_rect.y + 48, panel_rect.width - 52, 58
            ),
            line_gap=2,
            max_lines=2,
        )

        piece_types = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]
        option_rects: list[tuple[int, pygame.Rect]] = []
        for index, piece_type in enumerate(piece_types):
            rect = pygame.Rect(
                panel_rect.x + 22 + index * 92, panel_rect.y + 124, 70, 56
            )
            pygame.draw.rect(self.screen, self.PANEL_ALT, rect, border_radius=16)
            border_color = (
                self.SUCCESS
                if piece_type == state.promotion_suggestion
                else self.ACCENT
            )
            pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=16)
            piece = chess.Piece(piece_type, state.board.turn)
            self._draw_piece(piece, rect.inflate(-6, -6))
            if piece_type == state.promotion_suggestion:
                badge_rect = pygame.Rect(rect.x + 10, rect.bottom - 2, rect.width - 20, 18)
                pygame.draw.rect(self.screen, self.SUCCESS, badge_rect, border_radius=9)
                badge = self.fonts["tiny"].render("AI", True, (6, 22, 15))
                self.screen.blit(badge, badge.get_rect(center=badge_rect.center))
            option_rects.append((piece_type, rect))

        self.promotion_menu = PromotionMenu(panel_rect, option_rects)

    def _promotion_hint_text(
        self, suggestion: Optional[int], suggestion_enabled: bool
    ) -> str:
        piece_names = {
            chess.QUEEN: "queen",
            chess.ROOK: "rook",
            chess.BISHOP: "bishop",
            chess.KNIGHT: "knight",
        }
        if not suggestion_enabled:
            return "Stockfish promotion suggestion is paused. Press A to enable hints."
        if suggestion in piece_names:
            return f"Stockfish suggests promotion to {piece_names[suggestion]}."
        return "Stockfish is checking the promotion choice."

    def _draw_result_dialog(self, state: ViewState) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((3, 8, 14, 184))
        self.screen.blit(overlay, (0, 0))

        panel_rect = pygame.Rect(0, 0, 560, 336)
        panel_rect.center = self.screen.get_rect().center
        pygame.draw.rect(self.screen, self.PANEL, panel_rect, border_radius=28)
        pygame.draw.rect(self.screen, self.ACCENT_SOFT, panel_rect, 2, border_radius=28)

        title = self.fonts["title"].render(state.result_title, True, self.TEXT_PRIMARY)
        self.screen.blit(title, (panel_rect.x + 28, panel_rect.y + 24))

        self._draw_wrapped_text(
            state.result_message,
            self.fonts["body"],
            self.TEXT_PRIMARY,
            pygame.Rect(
                panel_rect.x + 28, panel_rect.y + 94, panel_rect.width - 56, 76
            ),
            line_gap=4,
            max_lines=3,
        )
        self._draw_wrapped_text(
            state.result_hint,
            self.fonts["small"],
            self.TEXT_MUTED,
            pygame.Rect(
                panel_rect.x + 28, panel_rect.bottom - 122, panel_rect.width - 56, 56
            ),
            line_gap=3,
            max_lines=3,
        )

        button_y = panel_rect.bottom - 58
        button_w = (panel_rect.width - 74) // 2
        button_h = 38
        gap = 18
        left_rect = pygame.Rect(panel_rect.x + 28, button_y, button_w, button_h)
        right_rect = pygame.Rect(left_rect.right + gap, button_y, button_w, button_h)
        self.result_buttons = [
            UIButton(
                state.result_primary_key,
                state.result_primary_label,
                left_rect,
                self.SUCCESS,
            ),
            UIButton(
                state.result_secondary_key,
                state.result_secondary_label,
                right_rect,
                self.ACCENT,
            ),
        ]

        for button in self.result_buttons:
            pygame.draw.rect(self.screen, self.PANEL_ALT, button.rect, border_radius=16)
            pygame.draw.rect(
                self.screen, button.accent, button.rect, 2, border_radius=16
            )
            label = self.fonts["button"].render(
                self._fit_single_line(
                    button.label, self.fonts["button"], button.rect.width - 26
                ),
                True,
                self.TEXT_PRIMARY,
            )
            self.screen.blit(label, label.get_rect(center=button.rect.center))

    def _wrap_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> list[str]:
        words = text.split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines
