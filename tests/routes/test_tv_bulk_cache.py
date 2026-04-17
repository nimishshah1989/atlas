"""Route unit tests for GET /api/tv/ta/bulk (cache-only, no bridge calls).

Pattern follows tests/routes/test_tv_routes.py — ASGITransport + AsyncClient,
DB session overridden, AtlasTvCache rows mocked at SQLAlchemy level.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_tv_cache_row(symbol: str, recommend_all: float = 0.6) -> MagicMock:
    """Return a MagicMock that mimics an AtlasTvCache ORM row."""
    row = MagicMock()
    row.symbol = symbol
    row.data_type = "ta_summary"
    row.interval = "1D"
    row.tv_data = {"Recommend.All": recommend_all, "RECOMMENDATION": "STRONG_BUY"}
    row.fetched_at = datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC)
    return row


def _mock_db_with_rows(rows: list[MagicMock]) -> AsyncMock:
    """Return a DB session mock that returns the given rows from scalars().all()."""
    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)
    return session


def _client_with_db(session: AsyncMock) -> AsyncClient:
    app.dependency_overrides[get_db] = lambda: session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_both_cached_returns_populated_items() -> None:
    """GET /api/tv/ta/bulk?symbols=RELIANCE,TCS with both cached → 2 items, cached_count=2."""
    rows = [_fake_tv_cache_row("RELIANCE", 0.7), _fake_tv_cache_row("TCS", 0.4)]
    session = _mock_db_with_rows(rows)
    async with _client_with_db(session) as ac:
        resp = await ac.get("/api/tv/ta/bulk?symbols=RELIANCE,TCS")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    items = body["data"]["items"]
    assert len(items) == 2
    assert all(it["tv_ta"] is not None for it in items)
    assert body["_meta"]["cached_count"] == 2
    assert body["_meta"]["requested_count"] == 2


@pytest.mark.asyncio
async def test_bulk_partial_cached_uncached_returns_null_tv_ta() -> None:
    """GET /api/tv/ta/bulk?symbols=RELIANCE,TCS with only RELIANCE cached → TCS tv_ta=null."""
    rows = [_fake_tv_cache_row("RELIANCE", 0.7)]
    session = _mock_db_with_rows(rows)
    async with _client_with_db(session) as ac:
        resp = await ac.get("/api/tv/ta/bulk?symbols=RELIANCE,TCS")

    assert resp.status_code == 200
    body = resp.json()
    items = body["data"]["items"]
    assert len(items) == 2
    reliance_item = next(it for it in items if it["symbol"] == "RELIANCE")
    tcs_item = next(it for it in items if it["symbol"] == "TCS")
    assert reliance_item["tv_ta"] is not None
    assert tcs_item["tv_ta"] is None
    assert tcs_item["fetched_at"] is None
    assert body["_meta"]["cached_count"] == 1


@pytest.mark.asyncio
async def test_bulk_empty_symbols_returns_400() -> None:
    """GET /api/tv/ta/bulk?symbols= (empty) → 400."""
    session = _mock_db_with_rows([])
    async with _client_with_db(session) as ac:
        resp = await ac.get("/api/tv/ta/bulk?symbols=")

    assert resp.status_code == 400
    assert "symbols required" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_bulk_too_many_symbols_returns_400() -> None:
    """GET /api/tv/ta/bulk?symbols=... (501 symbols) → 400."""
    too_many = ",".join(f"SYM{i:04d}" for i in range(501))
    session = _mock_db_with_rows([])
    async with _client_with_db(session) as ac:
        resp = await ac.get(f"/api/tv/ta/bulk?symbols={too_many}")

    assert resp.status_code == 400
    assert "500" in resp.json().get("detail", "")


@pytest.mark.asyncio
async def test_bulk_data_as_of_equals_latest_fetched_at() -> None:
    """_meta.data_as_of equals the latest fetched_at ISO string."""
    row = _fake_tv_cache_row("WIPRO", 0.3)
    expected_iso = row.fetched_at.isoformat()
    session = _mock_db_with_rows([row])
    async with _client_with_db(session) as ac:
        resp = await ac.get("/api/tv/ta/bulk?symbols=WIPRO")

    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["data_as_of"] == expected_iso


@pytest.mark.asyncio
async def test_bulk_case_insensitive_symbols_upper_cased() -> None:
    """Symbols passed in lowercase are upper-cased in the response items."""
    row = _fake_tv_cache_row("INFY", 0.5)
    session = _mock_db_with_rows([row])
    async with _client_with_db(session) as ac:
        resp = await ac.get("/api/tv/ta/bulk?symbols=infy,tcs")

    assert resp.status_code == 200
    body = resp.json()
    items = body["data"]["items"]
    symbols_in_response = [it["symbol"] for it in items]
    assert "INFY" in symbols_in_response
    assert "TCS" in symbols_in_response
