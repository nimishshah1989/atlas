"""Tests for BreadthDivergenceDetector — V2FE-1."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from backend.services.breadth_divergence_detector import BreadthDivergenceDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_two_queries(
    index_rows: list[dict[str, Any]],
    breadth_rows: list[dict[str, Any]],
) -> AsyncMock:
    """Session that returns index_rows for first query, breadth_rows for second."""
    mock_session = AsyncMock()
    call_idx = [0]

    async def fake_execute(query: Any, params: Any = None) -> MagicMock:
        if call_idx[0] == 0:
            data = index_rows
        else:
            data = breadth_rows
        call_idx[0] += 1

        mock_mapping = MagicMock()
        mock_mapping.all.return_value = list(data)
        mock_result = MagicMock()
        mock_result.mappings.return_value = mock_mapping
        return mock_result

    mock_session.execute = fake_execute
    return mock_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_divergence_detection_bearish() -> None:
    """Test that bearish divergence is detected (price up, breadth down)."""
    n = 25
    # index: steadily rising
    index_rows = [{"date": f"2024-01-{i + 1:02d}", "close": 100.0 + i * 2} for i in range(n)]
    # breadth: steadily falling (bearish divergence)
    breadth_rows = [{"date": index_rows[i]["date"], "above_dma50": 300 - i * 5} for i in range(n)]

    mock_session = _make_session_two_queries(index_rows, breadth_rows)
    detector = BreadthDivergenceDetector(session=mock_session)

    result = await detector.compute("nifty500", window=20, lookback=3)

    assert result["_meta"]["insufficient_data"] is False
    # Should find bearish divergences (price up, breadth down over the window)
    bearish = [d for d in result["divergences"] if d["type"] == "bearish"]
    assert len(bearish) > 0


async def test_no_divergences_when_in_sync() -> None:
    """Test that no divergences are returned when price and breadth move together."""
    n = 25
    # Both price and breadth rising together — no divergence
    index_rows = [{"date": f"2024-01-{i + 1:02d}", "close": 100.0 + i * 2} for i in range(n)]
    breadth_rows = [{"date": index_rows[i]["date"], "above_dma50": 200 + i * 5} for i in range(n)]

    mock_session = _make_session_two_queries(index_rows, breadth_rows)
    detector = BreadthDivergenceDetector(session=mock_session)

    result = await detector.compute("nifty500", window=20, lookback=3)

    assert result["_meta"]["insufficient_data"] is False
    assert result["divergences"] == []


async def test_insufficient_data_when_index_empty() -> None:
    """Test that insufficient_data=True when index query returns no rows."""
    mock_session = _make_session_two_queries([], [])
    detector = BreadthDivergenceDetector(session=mock_session)

    result = await detector.compute("nifty500", window=20, lookback=3)

    assert result["_meta"]["insufficient_data"] is True
    assert result["divergences"] == []


async def test_insufficient_data_when_index_query_fails() -> None:
    """Test that insufficient_data=True when de_index_daily raises exception."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=Exception("table does not exist"))
    detector = BreadthDivergenceDetector(session=mock_session)

    result = await detector.compute("nifty500", window=20, lookback=3)

    assert result["_meta"]["insufficient_data"] is True
    assert result["divergences"] == []
    assert "_meta" in result
