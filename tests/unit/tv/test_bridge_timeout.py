"""Tests for TVBridgeClient — tradingview_screener library integration.

Verifies error handling, empty result, and success paths.
All tests mock asyncio.to_thread or tradingview_screener.Query to avoid
real network calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.services.tv.bridge import TVBridgeClient, TVBridgeUnavailableError


def _make_df(row: dict[str, Any] | None = None) -> pd.DataFrame:
    """Build a one-row DataFrame for mocking get_scanner_data."""
    if row is None:
        row = {"name": "RELIANCE", "Recommend.All": 0.6}
    return pd.DataFrame([row])


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Helper: patch asyncio.to_thread to run synchronously with our fake result
# ---------------------------------------------------------------------------


def _patch_to_thread(fake_result: dict[str, Any] | Exception) -> Any:
    """Return a patch context for asyncio.to_thread that ignores fn and returns fake_result."""

    async def _fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(fake_result, Exception):
            raise fake_result
        return fake_result

    return patch("backend.services.tv.bridge.asyncio.to_thread", side_effect=_fake_to_thread)


# ---------------------------------------------------------------------------
# 1. get_ta_summary success returns dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ta_summary_success_returns_dict() -> None:
    """Successful get_ta_summary call returns the dict from the library."""
    expected = {"name": "RELIANCE", "Recommend.All": 0.6, "RSI": 55.0}
    with _patch_to_thread(expected):
        bridge = TVBridgeClient()
        result = await bridge.get_ta_summary("RELIANCE", "NSE", "1D")
    assert result == expected


# ---------------------------------------------------------------------------
# 2. get_screener success returns dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_screener_success_returns_dict() -> None:
    """Successful get_screener call returns the dict from the library."""
    expected = {"name": "INFY", "close": 1500.0, "volume": 100000}
    with _patch_to_thread(expected):
        bridge = TVBridgeClient()
        result = await bridge.get_screener("INFY", "NSE")
    assert result == expected


# ---------------------------------------------------------------------------
# 3. get_fundamentals success returns dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fundamentals_success_returns_dict() -> None:
    """Successful get_fundamentals call returns the dict from the library."""
    expected = {"name": "TCS", "price_earnings_ttm": 28.5}
    with _patch_to_thread(expected):
        bridge = TVBridgeClient()
        result = await bridge.get_fundamentals("TCS", "NSE")
    assert result == expected


# ---------------------------------------------------------------------------
# 4. Empty DataFrame raises TVBridgeUnavailableError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_dataframe_raises_unavailable() -> None:
    """Empty df.empty == True inside _run_query → TVBridgeUnavailableError propagated."""
    # Simulate the inner _run_query raising TVBridgeUnavailableError on empty df
    with _patch_to_thread(TVBridgeUnavailableError("NSE:UNKNOWN not found in TradingView")):
        bridge = TVBridgeClient()
        with pytest.raises(TVBridgeUnavailableError, match="not found"):
            await bridge.get_ta_summary("UNKNOWN", "NSE", "1D")


# ---------------------------------------------------------------------------
# 5. Network error wrapped as TVBridgeUnavailableError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_error_wrapped_as_unavailable() -> None:
    """Generic exception from _run_query → TVBridgeUnavailableError with 'fetch failed'."""
    with _patch_to_thread(ConnectionError("network unreachable")):
        bridge = TVBridgeClient()
        with pytest.raises(TVBridgeUnavailableError, match="TradingView fetch failed"):
            await bridge.get_ta_summary("RELIANCE", "NSE", "1D")


# ---------------------------------------------------------------------------
# 6. TVBridgeUnavailableError is re-raised unchanged (not double-wrapped)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bridge_unavailable_error_reraises() -> None:
    """TVBridgeUnavailableError from inner function is re-raised, not double-wrapped."""
    original = TVBridgeUnavailableError("symbol not found")
    with _patch_to_thread(original):
        bridge = TVBridgeClient()
        with pytest.raises(TVBridgeUnavailableError) as exc_info:
            await bridge.get_ta_summary("RELIANCE", "NSE", "1D")
    assert exc_info.value is original


# ---------------------------------------------------------------------------
# 7. Real Query integration path — verify ticker and market params
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_called_with_correct_ticker() -> None:
    """Verify Query is called with NSE:<symbol> ticker and 'india' market."""
    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.set_tickers.return_value = mock_query
    mock_query.set_markets.return_value = mock_query
    df = _make_df({"name": "RELIANCE", "Recommend.All": 0.7})
    mock_query.get_scanner_data.return_value = (None, df)

    with patch("tradingview_screener.query.Query", return_value=mock_query):
        bridge = TVBridgeClient()
        result = await bridge.get_ta_summary("RELIANCE", "NSE", "1D")

    mock_query.set_tickers.assert_called_once_with("NSE:RELIANCE")
    mock_query.set_markets.assert_called_once_with("india")
    assert result["name"] == "RELIANCE"


# ---------------------------------------------------------------------------
# 8. asyncio.to_thread is called exactly once (non-blocking guarantee)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asyncio_to_thread_used_for_blocking_call() -> None:
    """get_scanner_data must be called via asyncio.to_thread, not awaited directly."""
    captured_fn: list[Any] = []

    async def _capture_fn(fn: Any, *args: Any, **kwargs: Any) -> Any:
        captured_fn.append(fn)
        # Actually call the function to test its behavior with a mock
        mock_query = MagicMock()
        mock_query.select.return_value = mock_query
        mock_query.set_tickers.return_value = mock_query
        mock_query.set_markets.return_value = mock_query
        df = _make_df()
        mock_query.get_scanner_data.return_value = (None, df)
        with patch("tradingview_screener.query.Query", return_value=mock_query):
            return fn()

    with patch("backend.services.tv.bridge.asyncio.to_thread", side_effect=_capture_fn):
        bridge = TVBridgeClient()
        await bridge.get_ta_summary("RELIANCE", "NSE", "1D")

    assert len(captured_fn) == 1, "asyncio.to_thread must be called exactly once"
