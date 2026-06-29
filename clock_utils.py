"""Clock utilities for Chess Studio — presets, formatting, and animation helpers.

Extracted from the ChessController in ``main.py`` to reduce module size and
allow unit testing of clock logic without a running Pygame display.
"""

from __future__ import annotations

# ── Clock Presets ──────────────────────────────────────────────────

CLOCK_PRESETS: list[tuple[float, float, str]] = [
    (600.0, 5.0, "10+5"),
    (300.0, 0.0, "5+0"),
    (180.0, 2.0, "3+2"),
    (900.0, 10.0, "15+10"),
    (1200.0, 15.0, "20+15"),
]
"""Available time-control presets as (initial_seconds, increment_seconds, label)."""


# ── Formatting ─────────────────────────────────────────────────────


def format_clock_text(
    white_clock: float,
    black_clock: float,
    active_side: str,  # "W" or "B"
    *,  # keyword-only
    clock_active: bool = False,
    clock_initial: float | None = None,
) -> str:
    """Format both clocks into a compact status string.

    Returns an empty string when the clock has never been started
    (``clock_active is False`` and the initial time equals the current time).

    Note: float equality ``white_clock == clock_initial`` is safe here because
    we only compare when the clock has *never* been ticked (both are the exact
    same float value from the preset).
    """
    # Don't show anything if the clock hasn't been started yet
    if not clock_active and clock_initial is not None and white_clock == clock_initial:
        return ""

    def _fmt(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    pause = " Paused" if not clock_active else ""
    return f"{_fmt(white_clock)} | {_fmt(black_clock)} [{active_side}]{pause}"


def format_time(seconds: float) -> str:
    """Format a single time value as mm:ss."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


# ── Animation State ────────────────────────────────────────────────


def compute_clock_anim_progress(
    anim_start: float,
    anim_duration: float,
    now: float,
) -> float:
    """Return normalised animation progress (0.0 → 1.0).

    Returns 1.0 when no animation is active or the animation has completed.
    """
    if anim_duration <= 0 or now < anim_start:
        return 1.0
    elapsed = now - anim_start
    if elapsed >= anim_duration:
        return 1.0
    return elapsed / anim_duration


def is_clock_low(clock_seconds: float, threshold: float = 10.0) -> bool:
    """Return *True* if the given clock is at or below *threshold* seconds."""
    return clock_seconds <= threshold
