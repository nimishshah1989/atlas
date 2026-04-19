"""Tests for BreadthZoneDetector — V2FE-1."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from backend.services.breadth_zone_detector import (
    BreadthZoneDetector,
    _detect_events_for_series,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(rows: list[dict[str, Any]]) -> AsyncMock:
    """Build an async SQLAlchemy session mock that returns given rows."""
    mock_session = AsyncMock()
    mock_mapping_result = MagicMock()
    mock_mapping_result.all.return_value = rows
    mock_result = MagicMock()
    mock_result.mappings.return_value = mock_mapping_result
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


def _breadth_rows(
    dates: list[str],
    ema21: list[int],
    dma50: list[int],
    dma200: list[int],
) -> list[dict[str, Any]]:
    return [
        {"date": d, "above_ema21": e, "above_dma50": f, "above_dma200": g}
        for d, e, f, g in zip(dates, ema21, dma50, dma200)
    ]


# ---------------------------------------------------------------------------
# Unit tests for _detect_events_for_series
# ---------------------------------------------------------------------------


def test_zone_entry_overbought_detected() -> None:
    """Test that crossing into OB zone emits entered_ob event."""
    dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
    values = [300, 350, 420]  # Crosses OB=400 at index 2
    thresholds = {"overbought": 400, "midline": 250, "oversold": 100}

    events = _detect_events_for_series(dates, values, "nifty500", "ema21", thresholds)

    assert len(events) == 1
    assert events[0]["event_type"] == "entered_ob"
    assert events[0]["value"] == 420
    assert events[0]["indicator"] == "ema21"
    assert events[0]["universe"] == "nifty500"


def test_zone_exit_overbought_detected() -> None:
    """Test that exiting OB zone emits exited_ob event."""
    dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
    values = [420, 410, 350]  # Starts OB, exits at index 2
    thresholds = {"overbought": 400, "midline": 250, "oversold": 100}

    events = _detect_events_for_series(dates, values, "nifty500", "ema21", thresholds)

    assert len(events) == 1
    assert events[0]["event_type"] == "exited_ob"
    assert events[0]["prior_zone"] == "ob"


def test_prior_duration_days_calculation() -> None:
    """Test that prior_zone_duration_days is correctly calculated."""
    # Stay in neutral for 5 days, then cross into OB
    dates = [f"2024-01-0{i}" for i in range(1, 8)]
    values = [300, 310, 320, 330, 340, 350, 410]  # 6 neutral days, then OB
    thresholds = {"overbought": 400, "midline": 250, "oversold": 100}

    events = _detect_events_for_series(dates, values, "nifty500", "ema21", thresholds)

    assert len(events) == 1
    assert events[0]["prior_zone_duration_days"] == 6


def test_empty_series_returns_empty_events() -> None:
    """Test that empty input returns empty events list."""
    thresholds = {"overbought": 400, "midline": 250, "oversold": 100}

    events = _detect_events_for_series([], [], "nifty500", "ema21", thresholds)

    assert events == []


async def test_indicator_all_returns_events_for_all_three() -> None:
    """Test that indicator='all' computes events for ema21, dma50, dma200."""
    # OB threshold is 400 for nifty500
    dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
    rows = _breadth_rows(dates, [300, 350, 420], [300, 350, 420], [300, 350, 420])
    mock_session = _make_mock_session(rows)

    detector = BreadthZoneDetector(session=mock_session)
    result = await detector.compute("nifty500", "5y", "all")

    # Should have events for all 3 indicators
    indicators_in_events = {e["indicator"] for e in result["events"]}
    assert "ema21" in indicators_in_events
    assert "dma50" in indicators_in_events
    assert "dma200" in indicators_in_events


def test_cache_key_is_deterministic() -> None:
    """Test that cache key generation is deterministic for same inputs."""
    mock_session = AsyncMock()
    detector = BreadthZoneDetector(session=mock_session)

    key1 = detector._cache_key("nifty500", "5y", "all", "2026-04-17")
    key2 = detector._cache_key("nifty500", "5y", "all", "2026-04-17")

    assert key1 == key2
    assert key1 == "breadth_zone:nifty500:5y:all:2026-04-17"


async def test_empty_db_returns_empty_events() -> None:
    """Test that empty DB series returns events: []."""
    mock_session = _make_mock_session([])
    detector = BreadthZoneDetector(session=mock_session)

    result = await detector.compute("nifty500", "5y", "ema21")

    assert result["events"] == []
    assert result["universe"] == "nifty500"
    assert "thresholds" in result
