"""Unit tests for openings_stats module — exact ECO lookup, prefix fallback,
unknown ECO, and the descriptive formatting helper.
"""

from __future__ import annotations


class TestOpeningStats:
    def test_exact_eco_lookup_returns_stats(self) -> None:
        from openings_stats import get_opening_stats

        stats = get_opening_stats("C42")
        assert stats is not None
        assert stats["white_win_pct"] == 33.5
        assert stats["draw_pct"] == 48.5
        assert stats["label"] == "Petrov's Defence"

    def test_popular_opening(self) -> None:
        from openings_stats import get_opening_stats

        stats = get_opening_stats("B20")  # Sicilian Defence
        assert stats is not None
        assert stats["total_games"] == 1500000
        assert stats["white_win_pct"] == 45.5

    def test_prefix_fallback_not_found(self) -> None:
        """ECO code with no matching prefix returns None."""
        from openings_stats import get_opening_stats

        # "B00" is not in _OPENING_STATS, and "B0" prefix is also not
        stats = get_opening_stats("B00")
        assert stats is None

    def test_unknown_eco_prefix_nonexistent(self) -> None:
        """ECO code from an entirely absent letter prefix returns None."""
        from openings_stats import get_opening_stats

        stats = get_opening_stats("X99")
        assert stats is None

    def test_unknown_eco_returns_none(self) -> None:
        from openings_stats import get_opening_stats

        stats = get_opening_stats("ZZ99")
        assert stats is None

    def test_empty_string_returns_none(self) -> None:
        from openings_stats import get_opening_stats

        stats = get_opening_stats("")
        assert stats is None

    def test_opening_stats_api_returns_correct_type(self) -> None:
        from openings_stats import get_opening_stats

        stats = get_opening_stats("A00")
        assert stats is not None
        # Verify TypedDict fields
        assert isinstance(stats["white_win_pct"], float)
        assert isinstance(stats["draw_pct"], float)
        assert isinstance(stats["total_games"], int)
        assert isinstance(stats["label"], str)

    # ── Variation stats tests ──────────────────────────────────────

    def test_variation_exact_match_returns_variation_stats(self) -> None:
        """Exact UCI match should return variation-specific stats."""
        from openings_stats import get_variation_stats

        # Sicilian Dragon: e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6
        uci = ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6", "b1c3", "g7g6")
        stats = get_variation_stats("B20", uci)
        assert stats is not None
        assert stats["label"] == "Sicilian Dragon"
        assert stats["white_win_pct"] == 47.5

    def test_variation_prefix_match_falls_back(self) -> None:
        """Shorter UCI prefix should still match a sub-variation."""
        from openings_stats import get_variation_stats

        # Only Alapin first 3 moves: e4 c5 c3
        uci = ("e2e4", "c7c5", "c2c3")
        stats = get_variation_stats("B20", uci)
        assert stats is not None
        assert stats["label"] == "Sicilian Alapin"

    def test_variation_no_match_falls_back_to_eco(self) -> None:
        """UCI moves that don't match any variation should return ECO stats."""
        from openings_stats import get_variation_stats

        # Rossolimo: e4 c5 Nf3 Nc6 Bb5 — no variation match in current data
        uci = ("e2e4", "c7c5", "g1f3", "b8c6", "f1b5")
        stats = get_variation_stats("B20", uci)
        assert stats is not None
        assert stats["label"] == "Sicilian Defence"  # ECO-level fallback

    def test_variation_empty_uci_returns_eco(self) -> None:
        """Empty UCI moves should return ECO-level stats."""
        from openings_stats import get_variation_stats

        stats = get_variation_stats("C42", ())
        assert stats is not None
        assert stats["label"] == "Petrov's Defence"

    def test_variation_unknown_eco_returns_none(self) -> None:
        """Unknown ECO with variation lookup should return None."""
        from openings_stats import get_variation_stats

        stats = get_variation_stats("ZZ99", ("e2e4",))
        assert stats is None

    def test_variation_french_advance(self) -> None:
        """French Advance should match variation-specific stats over ECO."""
        from openings_stats import get_variation_stats

        uci = ("e2e4", "e7e6", "d2d4", "d7d5", "e4e5")
        stats = get_variation_stats("C00", uci)
        assert stats is not None
        assert stats["label"] == "French Advance"
        assert stats["white_win_pct"] == 46.5
