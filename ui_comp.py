from __future__ import annotations

import array
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import chess
import pygame

from engine import MoveRecord, PVLine

# ── Sound Manager ─────────────────────────────────────────────────


class SoundManager:
    """Generates programmatic sound effects for game events using pygame mixer."""

    SAMPLE_RATE = 22050
    BASE_VOLUME = 0.25

    def __init__(self) -> None:
        self._enabled = False
        self._volume = 1.0  # user volume multiplier (0.0-1.0)
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=self.SAMPLE_RATE, size=-16, channels=1)
            self._enabled = True
        except pygame.error:
            pass

        self.sounds: dict[str, pygame.mixer.Sound] = {}
        if self._enabled:
            self.sounds["move"] = self._tone(440.0, 0.08)
            self.sounds["capture"] = self._tone(330.0, 0.14)
            self.sounds["check"] = self._tone(660.0, 0.16)
            self.sounds["game_over"] = self._tone(220.0, 0.35)
            self.sounds["button"] = self._tone(550.0, 0.05)
            self.sounds["undo"] = self._tone(380.0, 0.10)
            self.sounds["flag_fall"] = self._tone(180.0, 0.50)
            self.sounds["tick"] = self._tone(880.0, 0.04)

    def _tone(self, freq: float, duration: float) -> pygame.mixer.Sound:
        """Generate a pure sine-wave tone at the given frequency and duration."""
        num_samples = int(self.SAMPLE_RATE * duration)
        samples = array.array(
            "h",
            [
                int(32767 * self.BASE_VOLUME * self._volume * math.sin(2.0 * math.pi * freq * t / self.SAMPLE_RATE))
                for t in range(num_samples)
            ],
        )
        return pygame.mixer.Sound(buffer=samples)

    def play(self, name: str) -> None:
        """Play a named sound effect."""
        if self._enabled and name in self.sounds:
            self.sounds[name].play()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_volume(self, volume: float) -> None:
        """Set user volume multiplier (0.0-1.0). Rebuilds sounds to apply."""
        self._volume = max(0.0, min(1.0, volume))
        if self._enabled:
            self.sounds["move"] = self._tone(440.0, 0.08)
            self.sounds["capture"] = self._tone(330.0, 0.14)
            self.sounds["check"] = self._tone(660.0, 0.16)
            self.sounds["game_over"] = self._tone(220.0, 0.35)
            self.sounds["button"] = self._tone(550.0, 0.05)
            self.sounds["undo"] = self._tone(380.0, 0.10)
            self.sounds["flag_fall"] = self._tone(180.0, 0.50)
            self.sounds["tick"] = self._tone(880.0, 0.04)




@dataclass
class ReviewEntry:
    move_type: str
    move_number: str
    san: str
    delta: float
    before: float
    after: float


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
    selected_square: int | None
    legal_targets: set[int]
    last_move: chess.Move | None
    suggested_move: chess.Move | None
    evaluation: float
    status_text: str
    analysis_text: str
    orientation_white_bottom: bool
    dragging_square: int | None
    drag_position: tuple[int, int] | None
    pending_promotion: bool
    promotion_suggestion: int | None
    promotion_suggestion_enabled: bool
    fen: str
    mode_text: str
    button_labels: dict[str, str]
    show_shortcuts: bool
    result_visible: bool
    result_title: str
    result_message: str
    result_hint: str
    result_primary_key: str
    result_primary_label: str
    result_secondary_key: str
    result_secondary_label: str
    sound_enabled: bool
    opening_name: str
    material_balance: str
    king_in_check: bool
    checked_king_square: int | None
    ai_elo_label: str
    clock_text: str
    white_captured_keys: list[str]
    black_captured_keys: list[str]
    multi_pv_lines: list[PVLine]
    arrows: list[tuple[int, int]]
    review_data: list[ReviewEntry]
    premove: tuple[int, int, int | None] | None
    move_number_trail: list[tuple[int, int]]
    eval_history: list[float]
    material_history: list[int]  # net material advantage over time
    check_attackers: list[tuple[int, int]]  # (attacker, king) pairs
    attacked_squares: set[int]  # squares attacked by opponent
    board_theme_light: tuple[int, int, int]
    board_theme_dark: tuple[int, int, int]
    analysis_depth: int
    analysis_nodes: int
    sound_volume: float
    clock_anim_progress: float
    clock_anim_duration: float
    clock_prev_text: str
    move_annotations: dict[int, str]
    num_legal_moves: int
    opening_continuations: list[tuple[str, str, str]]  # (san, eco, name)
    show_pgn_viewer: bool
    pgn_metadata: dict[str, str]
    opening_stats: Any
    blindfold_active: bool


class ChessView:
    BG_TOP = (17, 21, 30)
    BG_BOTTOM = (10, 14, 23)
    PANEL = (25, 30, 40)
    PANEL_ALT = (35, 41, 53)
    PANEL_BORDER = (48, 56, 74)
    TEXT_PRIMARY = (245, 248, 255)
    TEXT_MUTED = (150, 163, 190)
    ACCENT = (94, 178, 255)
    ACCENT_SOFT = (140, 206, 255)
    HIGHLIGHT = (255, 212, 96)
    MOVE_HINT = (60, 130, 220)
    DANGER = (224, 98, 98)
    SUCCESS = (82, 198, 138)

    CENTER_SQUARES: ClassVar[set[int]] = {chess.D4, chess.E4, chess.D5, chess.E5}

    def __init__(
        self,
        assets_dir: str | Path = "assets",
        window_size: tuple[int, int] | None = None,
    ):
        self._enable_high_dpi()
        pygame.init()
        if window_size is None:
            window_size = self._preferred_window_size()
        self.screen = pygame.display.set_mode(window_size, pygame.RESIZABLE)
        pygame.display.set_caption("Chess Studio")
        self._set_window_icon("chess.ico")
        self.clock = pygame.time.Clock()
        self.assets_dir = self._resolve_assets_dir(assets_dir)
        self.fonts: dict[str, pygame.font.Font] = {}
        self.layout: dict[str, pygame.Rect] = {}
        self.buttons: list[UIButton] = []
        self.result_buttons: list[UIButton] = []
        self.promotion_menu: PromotionMenu | None = None
        self.base_images: dict[str, pygame.Surface] = {}
        self.scaled_images: dict[tuple[str, int], pygame.Surface] = {}
        self.mouse_pos: tuple[int, int] = (0, 0)
        self._load_piece_images()
        self._init_clipboard()

        self._cached_background: pygame.Surface | None = None
        self._last_bg_size: tuple[int, int] | None = None
        self._cached_board_glow: pygame.Surface | None = None
        self._last_glow_size: tuple[int, int] | None = None
        self._cached_fen_text: tuple[str, list[str]] = ("", [])
        self._last_state: ViewState | None = None

        self._anim_piece_key: str = ""
        self._anim_from: pygame.Rect | None = None
        self._anim_to: pygame.Rect | None = None
        self._anim_start: float = 0.0
        self._anim_duration: float = 0.15
        self._anim_progress: float = 1.0
        self._anim_to_square: int | None = None

        self._pgn_tab = 0
        self._pgn_tab_rects: list[pygame.Rect] = []
        self._pgn_panel_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)

        self.rebuild_layout(*window_size)

    def _resolve_assets_dir(self, assets_dir: str | Path) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / Path(assets_dir)  # type: ignore
        return Path(assets_dir)

    def _resolve_app_file(self, file_name: str | Path) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys._MEIPASS) / Path(file_name)  # type: ignore[attr-defined]
        return Path(file_name)

    def _set_window_icon(self, icon_path: str | Path) -> None:
        path = self._resolve_app_file(icon_path)
        if not path.exists():
            return

        from contextlib import suppress

        with suppress(pygame.error):
            pygame.display.set_icon(pygame.image.load(str(path)))

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
        from contextlib import suppress

        with suppress(pygame.error):
            pygame.scrap.init()

    def _load_piece_images(self) -> None:
        for color in ("w", "b"):
            for piece_code in ("K", "Q", "R", "B", "N", "P"):
                key = f"{color}{piece_code}"
                path = self.assets_dir / f"{key}.png"
                self.base_images[key] = pygame.image.load(str(path)).convert_alpha()

    def rebuild_layout(self, width: int, height: int) -> None:
        self._cached_background = None
        self._last_bg_size = None
        self._cached_board_glow = None
        self._last_glow_size = None

        outer_pad = 32
        column_gap = 28
        panel_gap = 20
        sidebar_min_width = 420
        morgue_width = 160
        morgue_gap = 20
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

        header_height = 82
        controls_height = 200
        eval_height = 110
        status_height = 142
        fen_height = 120

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

        control_area = self.layout["controls"].inflate(-12, -14)
        button_width = int((control_area.width - 18) / 2)
        button_height = 38
        button_gap = 10
        left_x = control_area.x
        right_x = control_area.x + button_width + button_gap
        gap2 = button_gap
        top_y = control_area.y
        row2_y = top_y + button_height + gap2
        row3_y = row2_y + button_height + gap2
        row4_y = row3_y + button_height + gap2
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
                pygame.Rect(left_x, row2_y, button_width, button_height),
                self.ACCENT,
            ),
            UIButton(
                "copy_fen",
                "Copy FEN",
                pygame.Rect(right_x, row2_y, button_width, button_height),
                self.ACCENT_SOFT,
            ),
            UIButton(
                "mode_toggle",
                "Mode: Local 1v1",
                pygame.Rect(left_x, row3_y, control_area.width, button_height),
                self.SUCCESS,
            ),
            UIButton(
                "clock_toggle",
                "Clock: Paused",
                pygame.Rect(left_x, row4_y, control_area.width, button_height),
                self.ACCENT,
            ),
        ]

        self.fonts = {
            "title": pygame.font.SysFont("Segoe UI Semibold", 42),
            "heading": pygame.font.SysFont("Segoe UI Semibold", 22),
            "body": pygame.font.SysFont("Segoe UI", 20),
            "small": pygame.font.SysFont("Segoe UI", 16),
            "tiny": pygame.font.SysFont("Consolas", 15),
            "button": pygame.font.SysFont("Segoe UI Semibold", 17),
            "coord": pygame.font.SysFont("Segoe UI", 14),
        }
        self.scaled_images.clear()

    def tick(self, fps: int = 60) -> int:
        return self.clock.tick(fps)

    def handle_resize(self, size: tuple[int, int]) -> None:
        width = max(size[0], 1260)
        height = max(size[1], 820)
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.rebuild_layout(width, height)

    def button_at(self, position: tuple[int, int]) -> str | None:
        for button in self.buttons:
            if button.rect.collidepoint(position):
                return button.key
        return None

    def point_in_panel(self, panel_key: str, position: tuple[int, int]) -> bool:
        rect = self.layout.get(panel_key)
        return rect.collidepoint(position) if rect else False

    def get_move_list_visible_rows(self) -> int:
        rect = self.layout["moves"]
        line_height = 26
        return max(1, (rect.height - 64) // line_height)

    def get_move_list_max_scroll(self, move_history: list[MoveRecord]) -> int:
        total_rows = (len(move_history) + 1) // 2
        visible_rows = self.get_move_list_visible_rows()
        return max(0, total_rows - visible_rows)

    def screen_to_square(self, position: tuple[int, int], white_bottom: bool) -> int | None:
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

    def promotion_choice_at(self, position: tuple[int, int]) -> int | None:
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

    def read_from_clipboard(self) -> str | None:
        try:
            data = pygame.scrap.get(pygame.SCRAP_TEXT)
            if data:
                return data.decode("utf-8")
        except pygame.error:
            pass
        return None

    def _fit_single_line(self, text: str, font: pygame.font.Font, max_width: int) -> str:
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
        max_lines: int | None = None,
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

    def result_dialog_action_at(self, position: tuple[int, int]) -> str | None:
        for button in self.result_buttons:
            if button.rect.collidepoint(position):
                return button.key
        return None

    def scrollbar_rect(self, move_history_len: int) -> pygame.Rect | None:
        rect = self.layout.get("moves")
        if not rect or rect.height < 60:
            return None
        total_rows = (move_history_len + 1) // 2
        visible_rows = self.get_move_list_visible_rows()
        max_scroll = max(0, total_rows - visible_rows)
        if max_scroll <= 0:
            return None
        track_rect = pygame.Rect(rect.right - 12, rect.y + 56, 6, rect.height - 74)
        thumb_height = max(28, int(track_rect.height * (visible_rows / max(total_rows, 1))))
        return track_rect.inflate(12, 0)

    def scrollbar_drag_to(self, y: int, move_history_len: int, current_scroll: int) -> int:
        rect = self.layout.get("moves")
        if not rect:
            return current_scroll
        total_rows = (move_history_len + 1) // 2
        visible_rows = self.get_move_list_visible_rows()
        max_scroll = max(0, total_rows - visible_rows)
        if max_scroll <= 0:
            return current_scroll
        track_top = rect.y + 56
        track_bottom = rect.bottom - 18
        track_height = track_bottom - track_top
        if track_height <= 0:
            return current_scroll
        fraction = (y - track_top) / track_height
        return max(0, min(max_scroll, int(fraction * max_scroll)))

    def scrollbar_track(self) -> pygame.Rect | None:
        rect = self.layout.get("moves")
        if not rect:
            return None
        return pygame.Rect(rect.right - 24, rect.y + 56, 20, rect.height - 74)

    def start_animation(self, piece_key: str, from_rect: pygame.Rect, to_rect: pygame.Rect, to_square: int | None = None, duration: float = 0.15) -> None:
        self._anim_piece_key = piece_key
        self._anim_from = from_rect
        self._anim_to = to_rect
        self._anim_to_square = to_square
        self._anim_start = pygame.time.get_ticks() / 1000.0
        self._anim_duration = duration
        self._anim_progress = 0.0

    def _update_animation(self) -> tuple[int, int] | None:
        if self._anim_progress >= 1.0:
            return None
        now = pygame.time.get_ticks() / 1000.0
        elapsed = now - self._anim_start
        self._anim_progress = min(1.0, elapsed / self._anim_duration)
        if self._anim_progress >= 1.0:
            return None

        if self._anim_from is None or self._anim_to is None:
            return None

        t = self._anim_progress
        eased = 1.0 - (1.0 - t) ** 3

        cx = self._anim_from.centerx + (self._anim_to.centerx - self._anim_from.centerx) * eased
        cy = self._anim_from.centery + (self._anim_to.centery - self._anim_from.centery) * eased
        return (int(cx), int(cy))


    def draw(self, state: ViewState) -> None:
        self._last_state = state
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
        self._draw_clock(state)
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
        elif state.show_pgn_viewer:
            self.promotion_menu = None
            self.result_buttons = []
            self._draw_pgn_viewer(state)
        elif state.show_shortcuts:
            self.promotion_menu = None
            self.result_buttons = []
            self._draw_shortcut_overlay()
        else:
            self.promotion_menu = None
            self.result_buttons = []
        pygame.display.flip()

    def _draw_background(self) -> None:
        size = self.screen.get_size()
        if self._cached_background is None or self._last_bg_size != size:
            width, height = size
            bg = pygame.Surface(size)
            for y in range(height):
                blend = y / max(height - 1, 1)
                color = tuple(
                    int(self.BG_TOP[index] * (1 - blend) + self.BG_BOTTOM[index] * blend)
                    for index in range(3)
                )
                pygame.draw.line(bg, color, (0, y), (width, y))
            self._cached_background = bg
            self._last_bg_size = size

        self.screen.blit(self._cached_background, (0, 0))

        board_rect = self.layout["board"]
        glow_size = board_rect.size
        if self._cached_board_glow is None or self._last_glow_size != glow_size:
            glow_radius = max(glow_size[0], glow_size[1]) // 2
            glow = pygame.Surface((glow_radius * 2, glow_radius * 2), pygame.SRCALPHA)
            for r in range(glow_radius, 0, -2):
                alpha = max(0, int(30 * (1 - r / glow_radius)))
                pygame.draw.circle(glow, (60, 120, 200, alpha), (glow_radius, glow_radius), r)
            self._cached_board_glow = glow
            self._last_glow_size = glow_size
        glow_rect = self._cached_board_glow.get_rect(center=board_rect.center)
        self.screen.blit(self._cached_board_glow, glow_rect)

    def _draw_panel(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=22)
        pygame.draw.rect(self.screen, self.PANEL_BORDER, rect, 1, border_radius=22)

    def _draw_header(self) -> None:
        rect = self.layout["header"]
        title = self.fonts["title"].render("Chess Studio", True, self.TEXT_PRIMARY)
        title_y = rect.y + (rect.height - title.get_height()) // 2 - 2
        self.screen.blit(title, (rect.x + 24, title_y))

        state = self._last_state
        if state and state.opening_name and state.opening_name != "Unknown Opening":
            eco_name = state.opening_name
            max_w = (rect.width - 30) // 2
            eco_surface = self.fonts["small"].render(
                self._fit_single_line(eco_name, self.fonts["small"], max_w),
                True,
                self.HIGHLIGHT,
            )
            eco_y = rect.y + (rect.height - eco_surface.get_height()) // 2 + 2
            self.screen.blit(eco_surface, (rect.right - eco_surface.get_width() - 24, eco_y))
        else:
            sub = self.fonts["small"].render("Powered by Stockfish", True, self.TEXT_MUTED)
            self.screen.blit(sub, (rect.x + 24, rect.bottom - sub.get_height() - 18))

    def _draw_clock(self, state: ViewState) -> None:
        if not state.clock_text:
            return
        rect = self.layout["header"]

        # Determine clock color — pulse red when either side is low on time
        # Parse the clock text to extract white/black time values (format: "MM:SS | MM:SS [W/B]")
        clock_str = state.clock_text
        clock_low = False
        try:
            parts = clock_str.split(" | ")
            if len(parts) >= 2:
                w_time_str = parts[0].strip()
                b_time_str = parts[1].split("[")[0].strip()
                # Parse MM:SS
                if ":" in w_time_str and ":" in b_time_str:
                    f_w = w_time_str.split(":")
                    f_b = b_time_str.split(":")
                    w_sec = int(f_w[0]) * 60 + int(f_w[1])
                    b_sec = int(f_b[0]) * 60 + int(f_b[1])
                    if w_sec <= 10 or b_sec <= 10:
                        clock_low = True
        except (ValueError, IndexError):
            pass

        clock_color = self.DANGER if clock_low else self.ACCENT_SOFT

        # Animate clock digits on change (pulse effect)
        if state.clock_anim_duration > 0 and state.clock_anim_progress < 1.0:
            t = state.clock_anim_progress
            # Scale from 1.1 down to 1.0 with ease-out
            scale = 1.0 + 0.1 * (1.0 - t) ** 2
            orig = self.fonts["body"].render(clock_str, True, clock_color)
            w = int(orig.get_width() * scale)
            h = int(orig.get_height() * scale)
            if w > 0 and h > 0:
                scaled = pygame.transform.smoothscale(orig, (w, h))
                clock_rect = scaled.get_rect(topright=(rect.right - 24, rect.y + 12))
                self.screen.blit(scaled, clock_rect)
            else:
                self.screen.blit(orig, (rect.right - orig.get_width() - 24, rect.y + 12))
        else:
            clock_surface = self.fonts["body"].render(clock_str, True, clock_color)
            self.screen.blit(clock_surface, (rect.right - clock_surface.get_width() - 24, rect.y + 12))

    def _draw_morgue(self, state: ViewState) -> None:
        rect = self.layout["morgue"]
        top_rect = pygame.Rect(rect.x + 12, rect.y + 12, rect.width - 24, rect.height // 2 - 18)
        bottom_rect = pygame.Rect(
            rect.x + 12, rect.centery + 6, rect.width - 24, rect.height // 2 - 18
        )
        self._draw_morgue_section(top_rect, "Captured · Black", state.black_captured_keys)
        self._draw_morgue_section(bottom_rect, "Captured · White", state.white_captured_keys)

    def _draw_morgue_section(self, rect: pygame.Rect, title: str, captured_keys: list[str]) -> None:
        pygame.draw.rect(self.screen, self.PANEL_ALT, rect, border_radius=16)
        pygame.draw.rect(self.screen, self.PANEL_BORDER, rect, 1, border_radius=16)
        heading = self.fonts["small"].render(title, True, self.TEXT_MUTED)
        self.screen.blit(heading, (rect.x + 12, rect.y + 8))

        body_rect = pygame.Rect(rect.x + 10, rect.y + 34, rect.width - 20, rect.height - 44)
        if not captured_keys:
            placeholder = self.fonts["tiny"].render("—", True, self.TEXT_MUTED)
            self.screen.blit(placeholder, placeholder.get_rect(center=body_rect.center))
            return

        ordered_keys = self._sort_captured_keys(captured_keys)
        columns = 3
        cell_size = min((body_rect.width - 8 * (columns - 1)) // columns, 36)
        cell_size = max(cell_size, 24)
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
            hovered = button.rect.collidepoint(self.mouse_pos)
            shadow_offset = 3 if not hovered else 1

            shadow = button.rect.move(0, shadow_offset)
            pygame.draw.rect(self.screen, (0, 0, 0, 50), shadow, border_radius=14)

            if hovered:
                fill = tuple(min(80, c + 25) for c in button.accent)
                pygame.draw.rect(self.screen, fill, button.rect, border_radius=14)
            else:
                pygame.draw.rect(self.screen, self.PANEL_ALT, button.rect, border_radius=14)

            border_width = 2
            border_color = button.accent if not hovered else tuple(min(255, c + 60) for c in button.accent)
            pygame.draw.rect(self.screen, border_color, button.rect, border_width, border_radius=14)

            label_text = state.button_labels.get(button.key, button.label)
            label = self.fonts["button"].render(
                self._fit_single_line(label_text, self.fonts["button"], button.rect.width - 26),
                True,
                self.TEXT_PRIMARY,
            )
            self.screen.blit(label, label.get_rect(center=button.rect.center))

    def _draw_eval_panel(self, state: ViewState) -> None:
        rect = self.layout["eval"]
        heading = self.fonts["heading"].render("Engine Pulse", True, self.TEXT_PRIMARY)
        self.screen.blit(heading, (rect.x + 18, rect.y + 14))

        # Eval score in top right
        score_text = f"{state.evaluation:+.2f}"
        score = self.fonts["body"].render(score_text, True, self.TEXT_PRIMARY)
        self.screen.blit(score, (rect.right - score.get_width() - 18, rect.y + 12))

        # Eval bar
        bar_rect = pygame.Rect(rect.x + 18, rect.y + 44, rect.width - 36, 22)
        bar_bg = pygame.Rect(bar_rect.x - 1, bar_rect.y - 1, bar_rect.width + 2, bar_rect.height + 2)
        pygame.draw.rect(self.screen, self.PANEL_BORDER, bar_bg, border_radius=11)

        clamped = max(-8.0, min(8.0, state.evaluation))
        fill_ratio = (clamped + 8.0) / 16.0
        fill_width = max(12, int(bar_rect.width * fill_ratio))
        fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, fill_width, bar_rect.height)

        fill_color = self.SUCCESS if clamped >= 0 else self.DANGER

        for i in range(fill_rect.height):
            alpha_blend = 1.0 - (i / fill_rect.height) * 0.35
            adjusted = tuple(int(c * alpha_blend) for c in fill_color)
            pygame.draw.line(
                self.screen,
                adjusted,
                (fill_rect.x, fill_rect.y + i),
                (fill_rect.x + fill_rect.width, fill_rect.y + i),
            )

        center_x = bar_rect.x + bar_rect.width // 2
        pygame.draw.line(
            self.screen,
            self.TEXT_MUTED,
            (center_x, bar_rect.y),
            (center_x, bar_rect.bottom),
            1,
        )

        # Combined dual-graph: eval history (top 8px) + material history (bottom 8px)
        has_eval = len(state.eval_history) >= 2
        has_mat = len(state.material_history) >= 2
        if not state.multi_pv_lines and (has_eval or has_mat):
            graph_rect = pygame.Rect(rect.x + 18, rect.y + 72, rect.width - 36, 18)
            half_h = 8
            # Eval history graph (top half, accent color)
            if has_eval:
                eval_vals = [ev * 100.0 for ev in state.eval_history]
                min_eval = min(eval_vals)
                max_eval = max(eval_vals)
                range_eval = max(1.0, max_eval - min_eval)
                points: list[tuple[int, int]] = []
                for i, ev in enumerate(eval_vals):
                    x = graph_rect.x + int((i / max(len(eval_vals) - 1, 1)) * graph_rect.width)
                    norm = (ev - min_eval) / range_eval
                    y = graph_rect.y + half_h - int(norm * half_h)
                    points.append((x, y))
                if len(points) >= 2:
                    pygame.draw.lines(self.screen, self.ACCENT_SOFT, False, points, 2)
            # Material history graph (bottom half, gold color)
            if has_mat:
                mat_vals = state.material_history
                min_val = min(mat_vals)
                max_val = max(mat_vals)
                range_val = max(1, max_val - min_val)
                mat_points: list[tuple[int, int]] = []
                for i, mv in enumerate(mat_vals):
                    x = graph_rect.x + int((i / max(len(mat_vals) - 1, 1)) * graph_rect.width)
                    norm = (mv - min_val) / range_val
                    y = graph_rect.y + half_h + int((1.0 - norm) * half_h)
                    mat_points.append((x, y))
                # Zero line in bottom half
                if min_val < 0 < max_val:
                    zero_norm = (0 - min_val) / range_val
                    zero_y = graph_rect.y + half_h + int((1.0 - zero_norm) * half_h)
                    pygame.draw.line(self.screen, self.PANEL_BORDER, (graph_rect.x, zero_y), (graph_rect.x + graph_rect.width, zero_y), 1)
                if len(mat_points) >= 2:
                    pygame.draw.lines(self.screen, self.HIGHLIGHT, False, mat_points, 2)
                    pygame.draw.circle(self.screen, self.HIGHLIGHT, mat_points[-1], 3)

        # Multi-PV (up to 2 lines)
        if state.multi_pv_lines:
            pv_y = rect.y + 74
            for pv_line in state.multi_pv_lines[:2]:
                score_cp = pv_line["score"] / 100.0
                rank = pv_line["rank"]
                score_str = f"#{rank}  {score_cp:+.2f}"
                score_color = self.SUCCESS if score_cp >= 0 else self.DANGER
                score_surface = self.fonts["tiny"].render(score_str, True, score_color)
                self.screen.blit(score_surface, (rect.x + 18, pv_y))

                if pv_line["pv"]:
                    max_pv_w = rect.width - 100
                    pv_text = self._fit_single_line(pv_line["pv"], self.fonts["tiny"], max_pv_w)
                    pv_surface = self.fonts["tiny"].render(pv_text, True, self.TEXT_MUTED)
                    self.screen.blit(pv_surface, (rect.x + 78, pv_y))
                pv_y += 16
        else:
            # Analysis text
            self._draw_wrapped_text(
                state.analysis_text,
                self.fonts["small"],
                self.TEXT_MUTED,
                pygame.Rect(rect.x + 18, rect.y + 74, rect.width - 36, 20),
                line_gap=2,
                max_lines=1,
            )

        # Material balance, ELO label, depth, volume, legal moves at bottom
        bottom_y = rect.y + 94
        parts = []
        if state.material_balance:
            parts.append(state.material_balance)
        if state.num_legal_moves > 0:
            parts.append(f"{state.num_legal_moves} moves")
        if state.analysis_depth > 0:
            depth_str = f"Depth: {state.analysis_depth}"
            if state.analysis_nodes > 0:
                nodes_k = state.analysis_nodes // 1000
                depth_str += f" ({nodes_k}kN)" if nodes_k > 0 else ""
            parts.append(depth_str)
        info_width = 0
        if parts:
            info_str = "  |  ".join(parts)
            info_surface = self.fonts["tiny"].render(info_str, True, self.TEXT_MUTED)
            self.screen.blit(info_surface, (rect.x + 18, bottom_y))
            info_width = info_surface.get_width()
        # Volume indicator
        if state.sound_volume < 1.0:
            vol_str = f"Vol: {int(state.sound_volume * 100)}%"
            vol_surface = self.fonts["tiny"].render(vol_str, True, self.TEXT_MUTED)
            vol_x = rect.x + 18 + info_width + (12 if info_width else 0)
            self.screen.blit(vol_surface, (vol_x, bottom_y))
        if state.ai_elo_label:
            elo_surface = self.fonts["tiny"].render(state.ai_elo_label, True, self.TEXT_MUTED)
            self.screen.blit(elo_surface, (rect.right - elo_surface.get_width() - 18, bottom_y))

    def _draw_status_panel(self, state: ViewState) -> None:
        rect = self.layout["status"]
        heading = self.fonts["heading"].render("Position", True, self.TEXT_PRIMARY)
        self.screen.blit(heading, (rect.x + 18, rect.y + 14))

        status_rect = pygame.Rect(rect.x + 18, rect.y + 46, rect.width - 36, 38)
        self._draw_wrapped_text(
            state.status_text,
            self.fonts["body"],
            self.TEXT_PRIMARY,
            status_rect,
            line_gap=3,
            max_lines=2,
        )

        # Opening continuations (if any) — max 2 to avoid overflow
        cont_y = status_rect.bottom + 6
        if state.opening_continuations:
            cont_header = self.fonts["tiny"].render("Continuations", True, self.TEXT_MUTED)
            self.screen.blit(cont_header, (rect.x + 18, cont_y))
            cont_y += cont_header.get_height() + 2
            for san, eco, name in state.opening_continuations[:2]:
                max_w = rect.width - 50
                label_str = f"{san}  {eco}"
                label_str = self._fit_single_line(label_str, self.fonts["tiny"], max_w)
                cont_surface = self.fonts["tiny"].render(label_str, True, self.HIGHLIGHT)
                self.screen.blit(cont_surface, (rect.x + 18, cont_y))
                cont_y += 15
            cont_y += 3

        # Opening stats mini-badge (play rate and win rate), with bounds guard
        if state.opening_stats and cont_y + 18 < rect.bottom - 4:
            stats = state.opening_stats
            w = stats["white_win_pct"]
            d = stats["draw_pct"]
            total_k = round(stats["total_games"] / 1000)
            stat_str = f"W:{w:.0f}% D:{d:.0f}%  \u2022 {total_k:,}k games"
            stat_surface = self.fonts["tiny"].render(stat_str, True, self.TEXT_MUTED)
            self.screen.blit(stat_surface, (rect.x + 18, cont_y))
            cont_y += stat_surface.get_height() + 3

        shortcut_label = self.fonts["small"].render("Keyboard Shortcuts", True, self.TEXT_MUTED)
        label_y = cont_y + 4
        if label_y + shortcut_label.get_height() + 2 < rect.bottom - 4:
            self.screen.blit(shortcut_label, (rect.x + 18, label_y))

            shortcut_y = label_y + shortcut_label.get_height() + 6
            shortcut_rect = pygame.Rect(rect.x + 18, shortcut_y, rect.width - 36, 26)
            if shortcut_y + shortcut_rect.height <= rect.bottom - 4:
                pygame.draw.rect(self.screen, self.PANEL_ALT, shortcut_rect, border_radius=14)
                pygame.draw.rect(self.screen, self.PANEL_BORDER, shortcut_rect, 1, border_radius=14)

                shortcut_text = "R=New  U=Undo  F=Flip  A=Hint  M=Mode  S=Sound  B=Theme  F2=Board  F3=PGN  F4=Blindfold  H=Shortcuts  +/-Vol"
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
        self.screen.blit(heading, (rect.x + 18, rect.y + 14))

        list_rect = pygame.Rect(rect.x + 12, rect.y + 46, rect.width - 24, rect.height - 58)
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(list_rect)

        line_y = list_rect.y + 4
        line_height = 26
        visible_rows = max(1, (list_rect.height - 8) // line_height)
        number_x = list_rect.x + 8
        white_x = list_rect.x + 56
        black_x = list_rect.x + list_rect.width // 2 + 4
        white_width = max(74, list_rect.width // 2 - 72)
        black_width = max(74, list_rect.right - black_x - 8)
        row_font = self.fonts["small"]

        rows: list[tuple[str, str, str]] = []
        for index in range(0, len(move_history), 2):
            move_number = f"{index // 2 + 1}."
            white_move = move_history[index].san
            black_move = move_history[index + 1].san if index + 1 < len(move_history) else ""
            rows.append((move_number, white_move, black_move))

        max_scroll = max(0, len(rows) - visible_rows)
        start_index = min(max(scroll_offset, 0), max_scroll)
        visible_rows_data = rows[start_index : start_index + visible_rows]
        for row_index, (move_number, white_move, black_move) in enumerate(
            visible_rows_data, start=start_index
        ):
            if row_index % 2 == 0:
                row_bg = pygame.Rect(list_rect.x, line_y - 2, list_rect.width, line_height)
                pygame.draw.rect(self.screen, (30, 36, 48), row_bg, border_radius=6)

            num_surface = row_font.render(move_number, True, self.TEXT_MUTED)
            white_display = white_move
            white_ann = self._last_state.move_annotations.get(row_index * 2) if self._last_state else None
            if white_ann:
                white_display += white_ann
            white_surface = row_font.render(
                self._fit_single_line(white_display, row_font, white_width),
                True,
                self.TEXT_PRIMARY,
            )
            black_display = black_move
            black_ann = self._last_state.move_annotations.get(row_index * 2 + 1) if self._last_state else None
            if black_ann:
                black_display += black_ann
            black_surface = row_font.render(
                self._fit_single_line(black_display, row_font, black_width),
                True,
                self.TEXT_MUTED,
            )
            self.screen.blit(num_surface, (number_x, line_y))
            self.screen.blit(white_surface, (white_x, line_y))
            self.screen.blit(black_surface, (black_x, line_y))
            line_y += line_height

        self.screen.set_clip(previous_clip)

        if max_scroll > 0:
            track_rect = pygame.Rect(rect.right - 12, rect.y + 56, 6, rect.height - 74)
            pygame.draw.rect(self.screen, self.PANEL_ALT, track_rect, border_radius=4)
            thumb_height = max(28, int(track_rect.height * (visible_rows / max(len(rows), 1))))
            thumb_range = max(1, track_rect.height - thumb_height)
            thumb_y = track_rect.y + int((start_index / max_scroll) * thumb_range)
            thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_height)
            pygame.draw.rect(self.screen, self.ACCENT, thumb_rect, border_radius=4)
            _track = self.scrollbar_track()
            if _track and _track.collidepoint(self.mouse_pos):
                hover_thumb = thumb_rect.inflate(4, 4)
                pygame.draw.rect(self.screen, self.ACCENT_SOFT, hover_thumb, border_radius=4)

    def _draw_fen_panel(self, fen: str) -> None:
        rect = self.layout["fen"]
        heading = self.fonts["heading"].render("FEN Snapshot", True, self.TEXT_PRIMARY)
        self.screen.blit(heading, (rect.x + 18, rect.y + 14))

        body_rect = pygame.Rect(rect.x + 18, rect.y + 46, rect.width - 36, rect.height - 60)
        pygame.draw.rect(self.screen, self.PANEL_ALT, body_rect, border_radius=14)

        if self._cached_fen_text[0] != fen:
            wrapped = self._wrap_text(fen, self.fonts["tiny"], body_rect.width - 20)
            self._cached_fen_text = (fen, wrapped)

        lines = self._cached_fen_text[1]
        y = body_rect.y + 10
        for line in lines[:4]:
            surface = self.fonts["tiny"].render(line, True, self.TEXT_MUTED)
            self.screen.blit(surface, (body_rect.x + 10, y))
            y += 18

    def _draw_threat_arrows(self, state: ViewState) -> None:
        """Draw red arrows from attackers to the king when in check."""
        if not state.check_attackers:
            return
        for attacker_sq, king_sq in state.check_attackers:
            start = self.square_to_rect(attacker_sq, state.orientation_white_bottom).center
            end = self.square_to_rect(king_sq, state.orientation_white_bottom).center
            # Glow outline
            pygame.draw.line(self.screen, (180, 40, 40, 160), start, end, 8)
            # Bright fill
            pygame.draw.line(self.screen, (255, 60, 60), start, end, 5)
            # Arrowhead circle on king
            pygame.draw.circle(self.screen, (255, 50, 50), end, 10)

    def _draw_board(self, state: ViewState) -> None:
        board_rect = self.layout["board"]

        # Board shadow
        shadow_rect = board_rect.inflate(16, 16)
        shadow_surf = pygame.Surface(shadow_rect.size, pygame.SRCALPHA)
        for r in range(8, 0, -1):
            alpha = max(0, int(20 * (1 - r / 8)))
            pygame.draw.rect(
                shadow_surf, (0, 0, 0, alpha), shadow_surf.get_rect(), border_radius=20 + r
            )
        self.screen.blit(shadow_surf, shadow_rect)

        # Board frame
        frame_rect = board_rect.inflate(8, 8)
        pygame.draw.rect(self.screen, (14, 17, 24), frame_rect, border_radius=18)
        pygame.draw.rect(self.screen, self.PANEL_BORDER, frame_rect, 2, border_radius=18)

        # F-key reference hint (persistent, shown at board bottom-left)
        _fkey = "[F2] Board  [F3] PGN  [F4] Blindfold"
        _fkey_surf = self.fonts["tiny"].render(_fkey, True, self.TEXT_MUTED)
        _fkey_bg = pygame.Rect(
            frame_rect.x + 2,
            frame_rect.bottom - _fkey_surf.get_height() - 5,
            _fkey_surf.get_width() + 8,
            _fkey_surf.get_height() + 4,
        )
        _fkey_bg_surf = pygame.Surface(_fkey_bg.size, pygame.SRCALPHA)
        _fkey_bg_surf.fill((10, 14, 22, 170))
        self.screen.blit(_fkey_bg_surf, _fkey_bg)
        self.screen.blit(_fkey_surf, (_fkey_bg.x + 4, _fkey_bg.y + 2))

        # Squares using board theme colors
        for square in chess.SQUARES:
            square_rect = self.square_to_rect(square, state.orientation_white_bottom)
            is_light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 0
            color = state.board_theme_light if is_light else state.board_theme_dark
            pygame.draw.rect(self.screen, color, square_rect)

            # Last move highlight
            if state.last_move and square in {
                state.last_move.from_square,
                state.last_move.to_square,
            }:
                overlay = pygame.Surface(square_rect.size, pygame.SRCALPHA)
                overlay.fill((255, 220, 84, 92))
                self.screen.blit(overlay, square_rect.topleft)

            # Selected square
            if state.selected_square == square:
                pygame.draw.rect(self.screen, self.ACCENT, square_rect, 4, border_radius=6)

            # Legal targets
            if square in state.legal_targets:
                overlay = pygame.Surface(square_rect.size, pygame.SRCALPHA)
                if state.board.piece_at(square):
                    pygame.draw.rect(
                        overlay,
                        (255, 116, 116, 130),
                        overlay.get_rect(),
                        5,
                        border_radius=10,
                    )
                else:
                    pygame.draw.circle(
                        overlay,
                        (42, 82, 148, 140),
                        (overlay.get_width() // 2, overlay.get_height() // 2),
                        max(10, overlay.get_width() // 7),
                    )
                self.screen.blit(overlay, square_rect.topleft)

            # Attacked squares indicator (subtle red dots)
            if square in state.attacked_squares and not state.pending_promotion:
                atk_overlay = pygame.Surface(square_rect.size, pygame.SRCALPHA)
                cx, cy = atk_overlay.get_width() // 2, atk_overlay.get_height() // 2
                dot_radius = max(3, atk_overlay.get_width() // 14)
                pygame.draw.circle(atk_overlay, (255, 60, 60, 80), (cx, cy), dot_radius)
                self.screen.blit(atk_overlay, square_rect.topleft)

        # Center highlight (d4/d5/e4/e5)
            if square in self.CENTER_SQUARES and not state.pending_promotion:
                center_overlay = pygame.Surface(square_rect.size, pygame.SRCALPHA)
                cx, cy = center_overlay.get_width() // 2, center_overlay.get_height() // 2
                spot_radius = max(4, center_overlay.get_width() // 10)
                pygame.draw.circle(center_overlay, (255, 255, 200, 24), (cx, cy), spot_radius)
                self.screen.blit(center_overlay, square_rect.topleft)

        # Move number trail
        if state.move_number_trail:
            trail_font = self.fonts["tiny"]
            for trail_move_num, trail_sq in state.move_number_trail:
                trail_rect = self.square_to_rect(trail_sq, state.orientation_white_bottom)
                num_label = trail_font.render(str(trail_move_num), True, (255, 255, 200))
                num_x = trail_rect.right - num_label.get_width() - 3
                num_y = trail_rect.bottom - num_label.get_height() - 2
                badge_rect = pygame.Rect(num_x - 2, num_y - 1, num_label.get_width() + 4, num_label.get_height() + 2)
                pygame.draw.rect(self.screen, (10, 15, 25, 160), badge_rect, border_radius=3)
                self.screen.blit(num_label, (num_x, num_y))

        # Last-move arrow (subtle green)
        if state.last_move and state.king_in_check is False:
            last_from = self.square_to_rect(state.last_move.from_square, state.orientation_white_bottom).center
            last_to = self.square_to_rect(state.last_move.to_square, state.orientation_white_bottom).center
            if last_from != last_to:
                pygame.draw.line(self.screen, (60, 200, 100, 100), last_from, last_to, 4)
                pygame.draw.circle(self.screen, (60, 200, 100, 120), last_to, 7)

        # King-in-check highlight
        if state.king_in_check and state.checked_king_square is not None:
            king_rect = self.square_to_rect(state.checked_king_square, state.orientation_white_bottom)
            overlay = pygame.Surface(king_rect.size, pygame.SRCALPHA)
            overlay.fill((255, 50, 50, 150))
            self.screen.blit(overlay, king_rect.topleft)
            pygame.draw.rect(self.screen, (255, 30, 30), king_rect, 4, border_radius=6)

        # Blindfold overlay — dark vignette over the board when pieces are hidden
        if state.blindfold_active:
            bf_overlay = pygame.Surface(board_rect.size, pygame.SRCALPHA)
            bf_overlay.fill((5, 8, 16, 80))
            self.screen.blit(bf_overlay, board_rect.topleft)
            bf_label = self.fonts["small"].render(
                "Blindfold — pieces hidden", True, self.HIGHLIGHT
            )
            bf_badge = pygame.Rect(0, 0, bf_label.get_width() + 20, bf_label.get_height() + 10)
            bf_badge.center = board_rect.center
            bf_badge.y = board_rect.y + 20
            pygame.draw.rect(self.screen, (10, 14, 24), bf_badge, border_radius=10)
            pygame.draw.rect(self.screen, self.HIGHLIGHT, bf_badge, 1, border_radius=10)
            self.screen.blit(bf_label, (bf_badge.x + 10, bf_badge.y + 5))

        # Premove indicator
        if state.premove is not None:
            pm_from, pm_to, _ = state.premove
            pm_from_rect = self.square_to_rect(pm_from, state.orientation_white_bottom)
            pm_to_rect = self.square_to_rect(pm_to, state.orientation_white_bottom)
            ghost = pygame.Surface(pm_from_rect.size, pygame.SRCALPHA)
            ghost.fill((255, 255, 255, 40))
            self.screen.blit(ghost, pm_from_rect.topleft)
            pygame.draw.rect(self.screen, (255, 255, 100, 120), pm_from_rect, 3, border_radius=6)
            pygame.draw.rect(self.screen, (255, 255, 100, 80), pm_to_rect, 3, border_radius=6)
            pygame.draw.line(self.screen, (255, 255, 100), pm_from_rect.center, pm_to_rect.center, 4)
            pygame.draw.circle(self.screen, (255, 255, 100), pm_to_rect.center, 8)

        # Board hover highlight
        hover_square = self.screen_to_square(self.mouse_pos, state.orientation_white_bottom)
        if hover_square is not None:
            hover_file = chess.square_file(hover_square)
            hover_rank = chess.square_rank(hover_square)
            for sq in chess.SQUARES:
                if chess.square_file(sq) == hover_file or chess.square_rank(sq) == hover_rank:
                    hr_rect = self.square_to_rect(sq, state.orientation_white_bottom)
                    hr_overlay = pygame.Surface(hr_rect.size, pygame.SRCALPHA)
                    hr_overlay.fill((255, 255, 255, 12))
                    self.screen.blit(hr_overlay, hr_rect.topleft)
            hover_rect = self.square_to_rect(hover_square, state.orientation_white_bottom)
            hover_overlay = pygame.Surface(hover_rect.size, pygame.SRCALPHA)
            hover_overlay.fill((255, 255, 255, 30))
            self.screen.blit(hover_overlay, hover_rect.topleft)

        self._draw_coordinates(state.orientation_white_bottom)

        if state.suggested_move and state.suggested_move in state.board.legal_moves:
            self._draw_suggestion_arrow(state.suggested_move, state.orientation_white_bottom)

        # Threat arrows (red, attackers→king)
        self._draw_threat_arrows(state)

        # Analysis arrows
        self._draw_arrows(state)

        # Pieces — skip drawing if blindfold mode is active
        if not state.blindfold_active:
            anim_centre = self._update_animation()
            for square in chess.SQUARES:
                if square == state.dragging_square:
                    continue
                if self._anim_to_square is not None and self._anim_progress < 1.0 and square == self._anim_to_square:
                    continue
                piece = state.board.piece_at(square)
                if piece:
                    self._draw_piece(piece, self.square_to_rect(square, state.orientation_white_bottom))

            # Animated piece on top
            if anim_centre is not None and self._anim_piece_key:
                sample = self.square_to_rect(chess.E2, state.orientation_white_bottom)
                image = self._scaled_piece(self._anim_piece_key, sample.width)
                img_rect = image.get_rect(center=anim_centre)
                self.screen.blit(image, img_rect)

            # Dragged piece on top
            if state.dragging_square is not None and state.drag_position is not None:
                piece = state.board.piece_at(state.dragging_square)
                if piece:
                    rect = self.square_to_rect(state.dragging_square, state.orientation_white_bottom)
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
            self.scaled_images[cache_key] = pygame.transform.smoothscale(image, (target, target))
        return self.scaled_images[cache_key]

    def _draw_coordinates(self, white_bottom: bool) -> None:
        board_rect = self.layout["board"]
        cell = board_rect.width / 8
        files = "abcdefgh" if white_bottom else "hgfedcba"
        ranks = "12345678" if not white_bottom else "87654321"

        coord_color = (55, 65, 82)
        for idx, file_char in enumerate(files):
            label = self.fonts["coord"].render(file_char, True, coord_color)
            x = int(board_rect.x + idx * cell + cell - label.get_width() - 5)
            y = int(board_rect.bottom - label.get_height() - 3)
            self.screen.blit(label, (x, y))

        for idx, rank_char in enumerate(ranks):
            label = self.fonts["coord"].render(rank_char, True, coord_color)
            x = int(board_rect.x + 5)
            y = int(board_rect.y + idx * cell + 3)
            self.screen.blit(label, (x, y))

    def _draw_arrows(self, state: ViewState) -> None:
        if not state.arrows:
            return
        for from_sq, to_sq in state.arrows:
            start = self.square_to_rect(from_sq, state.orientation_white_bottom).center
            end = self.square_to_rect(to_sq, state.orientation_white_bottom).center
            pygame.draw.line(self.screen, (160, 160, 60), start, end, 7)
            pygame.draw.circle(self.screen, (160, 160, 60), end, 10)
            pygame.draw.line(self.screen, (200, 200, 80), start, end, 5)
            pygame.draw.circle(self.screen, (220, 220, 100), end, 8)

    def _draw_suggestion_arrow(self, move: chess.Move, white_bottom: bool) -> None:
        start = self.square_to_rect(move.from_square, white_bottom).center
        end = self.square_to_rect(move.to_square, white_bottom).center
        pygame.draw.line(self.screen, (56, 190, 255), start, end, 6)
        pygame.draw.circle(self.screen, (56, 190, 255), end, 9)

    def _draw_promotion_menu(self, state: ViewState) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((3, 8, 14, 168))
        self.screen.blit(overlay, (0, 0))

        board_rect = self.layout["board"]
        panel_rect = pygame.Rect(0, 0, 400, 200)
        panel_rect.center = board_rect.center
        pygame.draw.rect(self.screen, self.PANEL, panel_rect, border_radius=22)

        accent_line = pygame.Rect(panel_rect.x, panel_rect.y, panel_rect.width, 3)
        pygame.draw.rect(self.screen, self.ACCENT, accent_line, border_radius=2)

        title = self.fonts["heading"].render("Choose Promotion", True, self.TEXT_PRIMARY)
        self.screen.blit(title, (panel_rect.x + 24, panel_rect.y + 20))
        self._draw_wrapped_text(
            self._promotion_hint_text(
                state.promotion_suggestion, state.promotion_suggestion_enabled
            ),
            self.fonts["small"],
            self.TEXT_MUTED,
            pygame.Rect(panel_rect.x + 24, panel_rect.y + 50, panel_rect.width - 48, 48),
            line_gap=2,
            max_lines=2,
        )

        piece_types = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]
        option_rects: list[tuple[int, pygame.Rect]] = []
        for index, piece_type in enumerate(piece_types):
            rect = pygame.Rect(panel_rect.x + 20 + index * 92, panel_rect.y + 114, 68, 54)
            hovered = rect.collidepoint(self.mouse_pos)

            if hovered:
                fill_color = tuple(min(255, c + 30) for c in self.PANEL_ALT)
                pygame.draw.rect(self.screen, fill_color, rect, border_radius=14)
            else:
                pygame.draw.rect(self.screen, self.PANEL_ALT, rect, border_radius=14)

            border_color = self.SUCCESS if piece_type == state.promotion_suggestion else (
                tuple(min(255, c + 40) for c in self.ACCENT) if hovered else self.ACCENT
            )
            pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=14)
            piece = chess.Piece(piece_type, state.board.turn)
            self._draw_piece(piece, rect.inflate(-6, -6))
            if piece_type == state.promotion_suggestion:
                badge_rect = pygame.Rect(rect.x + 10, rect.bottom - 2, rect.width - 20, 18)
                pygame.draw.rect(self.screen, self.SUCCESS, badge_rect, border_radius=9)
                badge = self.fonts["tiny"].render("AI", True, (6, 22, 15))
                self.screen.blit(badge, badge.get_rect(center=badge_rect.center))
            option_rects.append((piece_type, rect))

        self.promotion_menu = PromotionMenu(panel_rect, option_rects)

    def _promotion_hint_text(self, suggestion: int | None, suggestion_enabled: bool) -> str:
        piece_names = {
            chess.QUEEN: "queen",
            chess.ROOK: "rook",
            chess.BISHOP: "bishop",
            chess.KNIGHT: "knight",
        }
        if not suggestion_enabled:
            return "AI promotion suggestion is paused. Press A to enable hints."
        if suggestion in piece_names:
            return f"AI suggests promotion to {piece_names[suggestion]}."
        return "AI is checking the promotion choice."

    def _draw_review_entry(self, entry: ReviewEntry, x: int, y: int, max_width: int) -> int:
        type_colors = {
            "brilliant": (105, 210, 255),
            "best": self.SUCCESS,
            "excellent": (100, 220, 160),
            "good": (140, 180, 210),
            "inaccuracy": self.HIGHLIGHT,
            "mistake": (255, 165, 80),
            "blunder": self.DANGER,
        }
        if entry.move_type in ("brilliant", "best"):
            icon = "★ "
        elif entry.move_type in ("mistake", "blunder"):
            icon = "▲ "
        else:
            icon = "▸ "
        color = type_colors.get(entry.move_type, self.TEXT_MUTED)
        label = f"{icon}{entry.move_number} {entry.san}"
        delta_str = f"{entry.delta:+.1f}"

        badge_w = 76
        badge = pygame.Rect(x, y, badge_w, 20)
        pygame.draw.rect(self.screen, tuple(min(255, c + 15) for c in self.PANEL_ALT), badge, border_radius=10)
        pygame.draw.rect(self.screen, color, badge, 1, border_radius=10)
        badge_label = self.fonts["tiny"].render(entry.move_type, True, color)
        self.screen.blit(badge_label, (badge.x + 6, badge.y + (badge.height - badge_label.get_height()) // 2))

        move_surface = self.fonts["small"].render(label, True, self.TEXT_PRIMARY)
        self.screen.blit(move_surface, (badge.right + 8, y + 1))

        delta_color = self.SUCCESS if entry.delta >= 0 else self.DANGER
        delta_surface = self.fonts["tiny"].render(delta_str, True, delta_color)
        self.screen.blit(delta_surface, (x + max_width - delta_surface.get_width() - 4, y + 3))

        return y + 26

    def _draw_result_dialog(self, state: ViewState) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((3, 8, 14, 184))
        self.screen.blit(overlay, (0, 0))

        has_review = bool(state.review_data)
        dialog_height = 380 if has_review else 320
        panel_rect = pygame.Rect(0, 0, 540, dialog_height)
        panel_rect.center = self.screen.get_rect().center
        pygame.draw.rect(self.screen, self.PANEL, panel_rect, border_radius=24)

        accent_line = pygame.Rect(panel_rect.x, panel_rect.y, panel_rect.width, 3)
        pygame.draw.rect(self.screen, self.ACCENT, accent_line, border_radius=2)

        title = self.fonts["title"].render(state.result_title, True, self.TEXT_PRIMARY)
        self.screen.blit(title, (panel_rect.x + 28, panel_rect.y + 22))

        self._draw_wrapped_text(
            state.result_message,
            self.fonts["body"],
            self.TEXT_PRIMARY,
            pygame.Rect(panel_rect.x + 28, panel_rect.y + 72, panel_rect.width - 56, 40),
            line_gap=3,
            max_lines=2,
        )

        y_offset = panel_rect.y + 112
        if has_review:
            type_counts: dict[str, int] = {}
            for entry in state.review_data:
                type_counts[entry.move_type] = type_counts.get(entry.move_type, 0) + 1
            summary_parts: list[str] = []
            for mt in ("brilliant", "best", "excellent", "good", "inaccuracy", "mistake", "blunder"):
                cnt = type_counts.get(mt, 0)
                if cnt:
                    summary_parts.append(f"{cnt} {mt}")
            summary_str = f"Game Review — {', '.join(summary_parts)}" if summary_parts else "Game Review"
            review_header = self.fonts["small"].render(summary_str, True, self.HIGHLIGHT)
            self.screen.blit(review_header, (panel_rect.x + 28, y_offset))
            y_offset += 24

            max_entries = 6
            entry_width = panel_rect.width - 56
            for entry in state.review_data[:max_entries]:
                if y_offset + 24 > panel_rect.bottom - 62:
                    break
                y_offset = self._draw_review_entry(entry, panel_rect.x + 28, y_offset, entry_width)

            hint_rect = pygame.Rect(panel_rect.x + 28, y_offset + 4, entry_width, 28)
            self._draw_wrapped_text(
                state.result_hint,
                self.fonts["tiny"],
                self.TEXT_MUTED,
                hint_rect,
                line_gap=2,
                max_lines=2,
            )
        else:
            self._draw_wrapped_text(
                state.result_hint,
                self.fonts["small"],
                self.TEXT_MUTED,
                pygame.Rect(panel_rect.x + 28, panel_rect.bottom - 100, panel_rect.width - 56, 48),
                line_gap=3,
                max_lines=3,
            )

        button_y = panel_rect.bottom - 54
        button_w = (panel_rect.width - 72) // 2
        button_h = 38
        gap = 16
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
            hovered = button.rect.collidepoint(self.mouse_pos)
            if hovered:
                fill = tuple(min(80, c + 25) for c in button.accent)
                pygame.draw.rect(self.screen, fill, button.rect, border_radius=14)
            else:
                pygame.draw.rect(self.screen, self.PANEL_ALT, button.rect, border_radius=14)

            border_color = (
                tuple(min(255, c + 60) for c in button.accent) if hovered else button.accent
            )
            pygame.draw.rect(self.screen, border_color, button.rect, 2, border_radius=14)
            label = self.fonts["button"].render(
                self._fit_single_line(button.label, self.fonts["button"], button.rect.width - 26),
                True,
                self.TEXT_PRIMARY,
            )
            self.screen.blit(label, label.get_rect(center=button.rect.center))

    def pgn_viewer_tab_at(self, position: tuple[int, int]) -> int | None:
        """Return the tab index at *position*, or None if not on a tab."""
        if not self._pgn_tab_rects:
            return None
        for idx, rect in enumerate(self._pgn_tab_rects):
            if rect.collidepoint(position):
                return idx
        return None

    def _draw_pgn_viewer(self, state: ViewState) -> None:
        """Draw a floating overlay showing PGN metadata plus raw PGN text."""
        size = self.screen.get_size()
        overlay = pygame.Surface(size, pygame.SRCALPHA)
        overlay.fill((3, 8, 14, 180))
        self.screen.blit(overlay, (0, 0))

        panel_rect = pygame.Rect(0, 0, 540, 460)
        panel_rect.center = (size[0] // 2, size[1] // 2)
        self._pgn_panel_rect = panel_rect
        pygame.draw.rect(self.screen, self.PANEL, panel_rect, border_radius=24)

        accent_line = pygame.Rect(panel_rect.x, panel_rect.y, panel_rect.width, 3)
        pygame.draw.rect(self.screen, self.ACCENT, accent_line, border_radius=2)

        # Title tabs area
        tab_rect = pygame.Rect(panel_rect.x + 28, panel_rect.y + 20, panel_rect.width - 56, 36)
        tabs = ["Metadata", "Raw PGN"]
        current_tab = self._pgn_tab
        tab_w = (tab_rect.width - 12) // 2
        self._pgn_tab_rects = []
        for idx, tab_name in enumerate(tabs):
            t_rect = pygame.Rect(tab_rect.x + idx * (tab_w + 12), tab_rect.y, tab_w, 34)
            self._pgn_tab_rects.append(t_rect)
            is_active = idx == current_tab
            if is_active:
                pygame.draw.rect(self.screen, self.PANEL_ALT, t_rect, border_radius=14)
                pygame.draw.rect(self.screen, self.ACCENT, t_rect, 1, border_radius=14)
            else:
                pygame.draw.rect(self.screen, self.PANEL, t_rect, border_radius=14)
            tab_label = self.fonts["heading"].render(tab_name, True, self.TEXT_PRIMARY if is_active else self.TEXT_MUTED)
            self.screen.blit(tab_label, tab_label.get_rect(center=t_rect.center))

        content_rect = pygame.Rect(panel_rect.x + 28, tab_rect.bottom + 16, panel_rect.width - 56, panel_rect.height - tab_rect.bottom - 68)

        if current_tab == 0:
            # ── Metadata tab ──
            meta = state.pgn_metadata
            tags = [
                ("Event", meta.get("Event", "—")),
                ("Site", meta.get("Site", "—")),
                ("Date", meta.get("Date", "—")),
                ("Round", meta.get("Round", "—")),
                ("White", meta.get("White", "—")),
                ("Black", meta.get("Black", "—")),
                ("Result", meta.get("Result", "*")),
                ("Opening", meta.get("Opening", "—")),
                ("Moves", meta.get("Moves", "0")),
                ("FEN", meta.get("FEN", "—")),
            ]

            body_x = content_rect.x
            body_y = content_rect.y
            label_width = 70
            value_x = body_x + label_width
            value_max_width = content_rect.width - label_width
            line_height = 26

            for label, value in tags:
                label_surface = self.fonts["small"].render(label, True, self.TEXT_MUTED)
                self.screen.blit(label_surface, (body_x, body_y))

                display_value = self._fit_single_line(
                    value, self.fonts["small"], value_max_width
                )
                value_surface = self.fonts["small"].render(
                    display_value, True, self.TEXT_PRIMARY
                )
                self.screen.blit(value_surface, (value_x, body_y))
                body_y += line_height
        else:
            # ── Raw PGN tab ──
            pgn_str = state.pgn_metadata.get("Raw", "[No PGN data]") if state.move_history else "[No moves played yet]"

            lines = self._wrap_text(pgn_str, self.fonts["tiny"], content_rect.width)
            previous_clip = self.screen.get_clip()
            self.screen.set_clip(content_rect)
            line_y = content_rect.y
            line_h = 16
            for line in lines[:60]:
                if line_y + line_h > content_rect.bottom:
                    break
                surface = self.fonts["tiny"].render(line, True, self.TEXT_PRIMARY)
                self.screen.blit(surface, (content_rect.x, line_y))
                line_y += line_h
            if len(lines) > 60:
                more = self.fonts["tiny"].render("... (truncated)", True, self.TEXT_MUTED)
                if line_y + line_h <= content_rect.bottom:
                    self.screen.blit(more, (content_rect.x, line_y))
            self.screen.set_clip(previous_clip)

        hint = self.fonts["small"].render(
            "Press F3 or Esc to close this overlay.", True, self.TEXT_MUTED
        )
        self.screen.blit(
            hint,
            (
                panel_rect.centerx - hint.get_width() // 2,
                panel_rect.bottom - 38,
            ),
        )

    def _draw_shortcut_overlay(self) -> None:
        size = self.screen.get_size()
        overlay = pygame.Surface(size, pygame.SRCALPHA)
        overlay.fill((3, 8, 14, 200))
        self.screen.blit(overlay, (0, 0))

        panel_rect = pygame.Rect(0, 0, 600, 460)
        panel_rect.center = (size[0] // 2, size[1] // 2)
        pygame.draw.rect(self.screen, self.PANEL, panel_rect, border_radius=24)

        accent_line = pygame.Rect(panel_rect.x, panel_rect.y, panel_rect.width, 3)
        pygame.draw.rect(self.screen, self.ACCENT, accent_line, border_radius=2)

        title = self.fonts["title"].render("Keyboard Shortcuts", True, self.TEXT_PRIMARY)
        self.screen.blit(title, (panel_rect.x + 28, panel_rect.y + 26))

        shortcuts = [
            ("R", "New game"),
            ("U", "Undo last move"),
            ("F", "Flip board orientation"),
            ("A", "Toggle AI hints / promotion suggestions"),
            ("M", "Toggle local 1v1 / vs-AI mode"),
            ("E", "Cycle AI difficulty (Elo)"),
            ("B", "Cycle board theme"),
            ("C", "Copy current FEN"),
            ("Ctrl+C", "Copy full move list"),
            ("S", "Toggle sound effects"),
            ("-/+", "Volume down/up"),
            ("P", "Start / pause chess clock"),
            ("T", "Cycle time control preset"),
            ("H", "Toggle this shortcut overlay"),
            ("Esc", "Cancel / close dialog / dismiss promotion"),
            ("Enter", "Confirm primary dialog action"),
            ("Q/N/R/B", "Select promotion piece (when dialog open)"),
            ("Shift+click", "Auto-queen promotion"),
            ("Ctrl+O", "Import PGN from clipboard"),
            ("Ctrl+Shift+O", "Open PGN file"),
            ("Ctrl+P", "Export PGN to clipboard"),
            ("Ctrl+Shift+P", "Save PGN file"),
            ("Ctrl+F", "Import FEN from clipboard"),
            ("Ctrl+Shift+B", "Copy board image to clipboard"),
            ("F2", "Save board screenshot to games/ folder"),
            ("F3", "Toggle PGN metadata viewer"),
            ("F4", "Toggle blindfold mode (hide pieces)"),
            ("Right-click", "Draw analysis arrow (drag)"),
            ("Right-click move", "Cycle move annotation (!, ?, !!)"),
            ("Mouse wheel", "Scroll move history"),
            ("—", "Continuations shown in Position panel"),
        ]

        body_x = panel_rect.x + 28
        body_y = panel_rect.y + 82
        col_width = (panel_rect.width - 56) // 2
        line_height = 30
        mid_col_x = body_x + col_width + 20

        col_size = (len(shortcuts) + 1) // 2
        for idx, (key, description) in enumerate(shortcuts):
            col = idx // col_size
            row = idx % col_size
            x = body_x if col == 0 else mid_col_x
            y = body_y + row * line_height

            key_bg = pygame.Rect(x, y, 85, 28)
            pygame.draw.rect(self.screen, self.PANEL_ALT, key_bg, border_radius=10)
            pygame.draw.rect(self.screen, self.PANEL_BORDER, key_bg, 1, border_radius=10)
            key_surface = self.fonts["small"].render(key, True, self.HIGHLIGHT)
            self.screen.blit(
                key_surface,
                (key_bg.x + 8, key_bg.y + (key_bg.height - key_surface.get_height()) // 2),
            )

            desc_surface = self.fonts["small"].render(description, True, self.TEXT_PRIMARY)
            self.screen.blit(
                desc_surface,
                (key_bg.right + 12, key_bg.y + (key_bg.height - desc_surface.get_height()) // 2),
            )

        hint = self.fonts["small"].render(
            "Press H or Esc to close this overlay.", True, self.TEXT_MUTED
        )
        self.screen.blit(
            hint,
            (
                panel_rect.centerx - hint.get_width() // 2,
                panel_rect.bottom - 48,
            ),
        )

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
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
