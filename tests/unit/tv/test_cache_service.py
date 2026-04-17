"""Unit tests for TVCacheService.

Tests hit no real database — all DB calls are mocked via AsyncMock.
All asyncio.create_task calls are patched to verify background refresh is spawned.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.tv import TvCacheEntry
from backend.services.tv.bridge import TVBridgeClient
from backend.services.tv.cache_service import TVCacheService, _is_stale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_orm_row(
    symbol: str = "RELIANCE",
    exchange: str = "NSE",
    data_type: str = "ta_summary",
    interval: str = "1D",
    tv_data: dict[str, Any] | None = None,
    fetched_at: datetime | None = None,
) -> MagicMock:
    """Build a minimal ORM-like mock for AtlasTvCache."""
    row = MagicMock()
    row.symbol = symbol
    row.exchange = exchange
    row.data_type = data_type
    row.interval = interval
    row.tv_data = tv_data or {"recommendation": "BUY"}
    row.fetched_at = fetched_at or datetime.now(tz=UTC)
    return row


def _make_session(scalar_result: Any = None) -> AsyncMock:
    """Build a mock AsyncSession that returns scalar_result on execute()."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_result
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    return session


def _make_bridge(return_value: dict[str, Any] | None = None) -> AsyncMock:
    bridge = AsyncMock(spec=TVBridgeClient)
    bridge.get_ta_summary = AsyncMock(return_value=return_value or {"recommendation": "BUY"})
    bridge.get_screener = AsyncMock(return_value=return_value or {"signal": "strong_buy"})
    bridge.get_fundamentals = AsyncMock(return_value=return_value or {"pe": 25})
    return bridge


# ---------------------------------------------------------------------------
# _is_stale helper
# ---------------------------------------------------------------------------


def test_is_stale_fresh_entry_returns_false() -> None:
    """A fetched_at timestamp 1 second ago must not be stale (TTL = 900s)."""
    fresh_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    assert _is_stale(fresh_at) is False


def test_is_stale_old_entry_returns_true() -> None:
    """A fetched_at timestamp 20 minutes ago must be stale (TTL = 900s)."""
    old_at = datetime.now(tz=UTC) - timedelta(seconds=1200)
    assert _is_stale(old_at) is True


def test_is_stale_one_second_before_ttl_is_not_stale() -> None:
    """A fetched_at one second before TTL expiry is not stale."""
    # 899 seconds ago — comfortably under the 900s TTL
    nearly_ttl_at = datetime.now(tz=UTC) - timedelta(seconds=899)
    assert _is_stale(nearly_ttl_at) is False


# ---------------------------------------------------------------------------
# Cache HIT (fresh)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_fetch_cache_hit_fresh_returns_is_stale_false() -> None:
    """A fresh cache hit returns is_stale=False and does NOT call the bridge."""
    fresh_row = _make_orm_row(fetched_at=datetime.now(tz=UTC) - timedelta(seconds=60))
    session = _make_session(scalar_result=fresh_row)
    bridge = _make_bridge()

    svc = TVCacheService()
    entry = await svc.get_or_fetch(session, "RELIANCE", "NSE", "ta_summary", "1D", bridge)

    assert entry.is_stale is False
    bridge.get_ta_summary.assert_not_called()
    bridge.get_screener.assert_not_called()
    bridge.get_fundamentals.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_fetch_cache_hit_returns_correct_data() -> None:
    """A cache hit returns the data stored in the ORM row."""
    expected_data = {"recommendation": "SELL", "buy": 5, "sell": 10}
    fresh_row = _make_orm_row(
        tv_data=expected_data,
        fetched_at=datetime.now(tz=UTC) - timedelta(seconds=30),
    )
    session = _make_session(scalar_result=fresh_row)
    bridge = _make_bridge()

    svc = TVCacheService()
    entry = await svc.get_or_fetch(session, "RELIANCE", "NSE", "ta_summary", "1D", bridge)

    assert entry.tv_data == expected_data
    assert entry.symbol == "RELIANCE"


# ---------------------------------------------------------------------------
# Cache HIT (stale)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_fetch_stale_entry_returns_is_stale_true() -> None:
    """A stale cache hit returns is_stale=True."""
    stale_row = _make_orm_row(fetched_at=datetime.now(tz=UTC) - timedelta(seconds=1200))
    session = _make_session(scalar_result=stale_row)
    bridge = _make_bridge()

    svc = TVCacheService()
    with patch("backend.services.tv.cache_service.asyncio.create_task") as mock_task:
        mock_task.return_value = MagicMock()
        entry = await svc.get_or_fetch(session, "RELIANCE", "NSE", "ta_summary", "1D", bridge)

    assert entry.is_stale is True


@pytest.mark.asyncio
async def test_get_or_fetch_stale_spawns_background_refresh() -> None:
    """A stale cache hit must spawn asyncio.create_task for background refresh."""
    stale_row = _make_orm_row(fetched_at=datetime.now(tz=UTC) - timedelta(seconds=1800))
    session = _make_session(scalar_result=stale_row)
    bridge = _make_bridge()

    svc = TVCacheService()
    with patch("backend.services.tv.cache_service.asyncio.create_task") as mock_task:
        mock_task.return_value = MagicMock()
        await svc.get_or_fetch(session, "RELIANCE", "NSE", "ta_summary", "1D", bridge)
        mock_task.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_fetch_stale_does_not_call_bridge_directly() -> None:
    """Stale cache hit must NOT call the bridge in the request path — only background."""
    stale_row = _make_orm_row(fetched_at=datetime.now(tz=UTC) - timedelta(seconds=1800))
    session = _make_session(scalar_result=stale_row)
    bridge = _make_bridge()

    svc = TVCacheService()
    with patch("backend.services.tv.cache_service.asyncio.create_task") as mock_task:
        mock_task.return_value = MagicMock()
        await svc.get_or_fetch(session, "RELIANCE", "NSE", "ta_summary", "1D", bridge)

    bridge.get_ta_summary.assert_not_called()


# ---------------------------------------------------------------------------
# Cache MISS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_fetch_cache_miss_calls_bridge() -> None:
    """A cache miss must call the appropriate bridge method."""
    session = _make_session(scalar_result=None)
    bridge = _make_bridge(return_value={"recommendation": "BUY"})

    svc = TVCacheService()
    with patch.object(svc, "upsert", new_callable=AsyncMock) as mock_upsert:
        mock_upsert.return_value = TvCacheEntry(
            symbol="RELIANCE",
            exchange="NSE",
            data_type="ta_summary",
            interval="1D",
            tv_data={"recommendation": "BUY"},
            fetched_at=datetime.now(tz=UTC),
            is_stale=False,
        )
        await svc.get_or_fetch(session, "RELIANCE", "NSE", "ta_summary", "1D", bridge)

    bridge.get_ta_summary.assert_called_once_with("RELIANCE", "NSE", "1D")
    mock_upsert.assert_called_once()


@pytest.mark.asyncio
async def test_get_or_fetch_cache_miss_returns_is_stale_false() -> None:
    """A cache miss that succeeds must return is_stale=False."""
    session = _make_session(scalar_result=None)
    bridge = _make_bridge()

    svc = TVCacheService()
    with patch.object(svc, "upsert", new_callable=AsyncMock) as mock_upsert:
        mock_upsert.return_value = TvCacheEntry(
            symbol="RELIANCE",
            exchange="NSE",
            data_type="ta_summary",
            interval="1D",
            tv_data={"recommendation": "BUY"},
            fetched_at=datetime.now(tz=UTC),
            is_stale=False,
        )
        entry = await svc.get_or_fetch(session, "RELIANCE", "NSE", "ta_summary", "1D", bridge)

    assert entry.is_stale is False


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_returns_entry_with_correct_fields() -> None:
    """upsert() must return a TvCacheEntry matching the upserted values."""
    session = _make_session()
    tv_data = {"recommendation": "NEUTRAL"}

    svc = TVCacheService()
    entry = await svc.upsert(session, "TCS", "NSE", "screener", "none", tv_data)

    assert entry.symbol == "TCS"
    assert entry.exchange == "NSE"
    assert entry.data_type == "screener"
    assert entry.interval == "none"
    assert entry.tv_data == tv_data
    assert entry.is_stale is False


@pytest.mark.asyncio
async def test_upsert_calls_session_commit() -> None:
    """upsert() must commit the session after the insert/update."""
    session = _make_session()

    svc = TVCacheService()
    await svc.upsert(session, "INFY", "NSE", "fundamentals", "none", {"pe": 30})

    session.commit.assert_called_once()
