"""Tests for GET /api/instruments/{symbol}/price.

All JIP/DB calls mocked -- no real DB required.
Tests placed in tests/routes/ (NOT tests/api/) per conftest-integration-marker-trap pattern.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import backend.clients.jip_equity_service as _jip_module
from backend.db.session import get_db
from backend.main import app

# Module-level patch path aliases
_ROUTE = "backend.routes.instruments"
_HEALTH_CHECK = f"{_ROUTE}._check_corporate_actions_health"
_SESSION_FACTORY = f"{_ROUTE}.async_session_factory"

# Convenience ref to the service class for patch.object calls
_JIP_SVC = _jip_module.JIPEquityService


# ---------------------------------------------------------------------------
# DB dependency override -- avoids real DB connection
# ---------------------------------------------------------------------------


async def _fake_db() -> Any:  # type: ignore[return]
    """Return a no-op async session mock."""
    yield MagicMock()


app.dependency_overrides[get_db] = _fake_db

# ---------------------------------------------------------------------------
# Sample price data
# ---------------------------------------------------------------------------

_SAMPLE_PRICES: list[dict[str, Any]] = [
    {
        "date": date(2025, 1, 2),
        "open": Decimal("1000.0000"),
        "high": Decimal("1050.0000"),
        "low": Decimal("990.0000"),
        "close": Decimal("1020.0000"),
        "volume": 1000000,
    },
    {
        "date": date(2025, 6, 1),
        "open": Decimal("1100.0000"),
        "high": Decimal("1150.0000"),
        "low": Decimal("1080.0000"),
        "close": Decimal("1120.0000"),
        "volume": 1200000,
    },
]


# ---------------------------------------------------------------------------
# Session factory mock helper
# ---------------------------------------------------------------------------


def _make_session_ctx(symbol_exists: bool = True) -> Any:
    """Build an async context manager mock that simulates session + service."""
    mock_session = AsyncMock()

    # Simulate symbol existence check
    mock_row = MagicMock()
    mock_row.fetchone.return_value = (1,) if symbol_exists else None
    mock_session.execute = AsyncMock(return_value=mock_row)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_price_returns_adjusted_by_default(client: AsyncClient) -> None:
    """No ?adjusted param -> adjusted=True in meta by default."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch(_HEALTH_CHECK, return_value=[]),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price")

    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["adjusted"] is True
    assert body["_meta"]["symbol"] == "RELIANCE"


@pytest.mark.asyncio
async def test_get_price_raw_when_adjusted_false(client: AsyncClient) -> None:
    """?adjusted=false -> adjusted=False in meta, no corporate actions fetched."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch(_HEALTH_CHECK, return_value=[]),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price?adjusted=false")

    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["adjusted"] is False
    assert body["_meta"]["warnings"] == []


@pytest.mark.asyncio
async def test_get_price_symbol_not_found_returns_404(client: AsyncClient) -> None:
    """Unknown symbol -> HTTP 404 with INSTRUMENT_NOT_FOUND error."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=False)

    with patch(_SESSION_FACTORY, return_value=mock_ctx):
        resp = await client.get("/api/instruments/NOSUCHSYMBOL/price")

    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"]["code"] == "INSTRUMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_price_invalid_date_range_returns_400(client: AsyncClient) -> None:
    """from_date > to_date -> HTTP 400 with INVALID_DATE_RANGE error."""
    resp = await client.get(
        "/api/instruments/RELIANCE/price?from_date=2025-12-01&to_date=2025-01-01"
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "INVALID_DATE_RANGE"


@pytest.mark.asyncio
async def test_get_price_health_warning_when_domain_failing(
    client: AsyncClient,
) -> None:
    """Health warnings from _check_corporate_actions_health -> meta.warnings set,
    adjusted=False (soft degradation, never 503)."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)
    degraded_warnings = ["adjustment_factor_health_degraded: de_corporate_actions"]

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch(_HEALTH_CHECK, return_value=degraded_warnings),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price")

    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["adjusted"] is False
    assert len(body["_meta"]["warnings"]) > 0
    assert "adjustment_factor_health_degraded" in body["_meta"]["warnings"][0]


@pytest.mark.asyncio
async def test_get_price_meta_envelope(client: AsyncClient) -> None:
    """Response has 'data' key and '_meta' key (§20.4 envelope)."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch(_HEALTH_CHECK, return_value=[]),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "_meta" in body
    assert isinstance(body["data"], list)
    assert isinstance(body["_meta"], dict)
    assert body["_meta"]["point_count"] == len(_SAMPLE_PRICES)


@pytest.mark.asyncio
async def test_get_price_no_float_in_response(client: AsyncClient) -> None:
    """Serialized response prices must not contain float values (Decimal -> str in JSON)."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch(_HEALTH_CHECK, return_value=[]),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price")

    assert resp.status_code == 200
    body = resp.json()

    for row in body["data"]:
        for col in ("open", "high", "low", "close"):
            val = row.get(col)
            if val is not None:
                assert not isinstance(val, float), (
                    f"{col} must not be float in JSON output, got {type(val)}: {val}"
                )


@pytest.mark.asyncio
async def test_get_price_empty_corporate_actions(client: AsyncClient) -> None:
    """No corporate actions -> returns prices unchanged (factor=1 for all rows)."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch(_HEALTH_CHECK, return_value=[]),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["_meta"]["point_count"] == 2


# ---------------------------------------------------------------------------
# V11-3 — Denomination lens tests
# ---------------------------------------------------------------------------

_GOLD_SERIES: list[tuple[date, Decimal]] = [
    (date(2025, 1, 2), Decimal("100.0000")),
    (date(2025, 6, 1), Decimal("120.0000")),
]

_USDINR_SERIES: list[tuple[date, Decimal]] = [
    (date(2025, 1, 2), Decimal("84.5000")),
    (date(2025, 6, 1), Decimal("85.0000")),
]

_GET_DENOM = f"{_ROUTE}._get_denom_series"
_DENOM_CACHE_PATH = f"{_ROUTE}._DENOM_CACHE"


@pytest.mark.asyncio
async def test_denomination_gold_divides_by_goldbees(client: AsyncClient) -> None:
    """denomination=gold returns close = inr_close / goldbees_close, 4dp."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch(_HEALTH_CHECK, return_value=[]),
        patch(_GET_DENOM, new=AsyncMock(return_value=_GOLD_SERIES)),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price?denomination=gold")

    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["denomination"] == "gold"
    # close = 1020.0 / 100.0 = 10.2000
    first_row = body["data"][0]
    assert first_row["close"] == "10.2000"


@pytest.mark.asyncio
async def test_denomination_usd_divides_by_usdinr(client: AsyncClient) -> None:
    """denomination=usd returns close = inr_close / usdinr_rate, 4dp."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch(_HEALTH_CHECK, return_value=[]),
        patch(_GET_DENOM, new=AsyncMock(return_value=_USDINR_SERIES)),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price?denomination=usd")

    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["denomination"] == "usd"
    # close = 1020.0 / 84.5 = ...
    first_row = body["data"][0]
    expected = (Decimal("1020.0000") / Decimal("84.5000")).quantize(Decimal("0.0001"))
    assert first_row["close"] == str(expected)


@pytest.mark.asyncio
async def test_denomination_inr_is_default(client: AsyncClient) -> None:
    """No denomination param -> denomination='inr' in meta, INR prices returned."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch(_HEALTH_CHECK, return_value=[]),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price")

    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["denomination"] == "inr"
    # INR close preserved (no division)
    assert body["data"][0]["close"] == "1020.0000"


@pytest.mark.asyncio
async def test_denomination_invalid_returns_400(client: AsyncClient) -> None:
    """Unknown denomination -> HTTP 400 INVALID_DENOMINATION."""
    resp = await client.get("/api/instruments/RELIANCE/price?denomination=bitcoin")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "INVALID_DENOMINATION"


@pytest.mark.asyncio
async def test_denomination_data_as_of_worst_of_staleness(client: AsyncClient) -> None:
    """data_as_of = min(instrument_max_date, denom_max_date) — worst-of staleness."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)
    # Denom series ends earlier than instrument series
    early_denom = [(date(2025, 1, 2), Decimal("100.0000"))]  # only one date (2025-01-02)

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch(_HEALTH_CHECK, return_value=[]),
        patch(_GET_DENOM, new=AsyncMock(return_value=early_denom)),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price?denomination=gold")

    assert resp.status_code == 200
    body = resp.json()
    # denom only has 2025-01-02, instrument has up to 2025-06-01
    # data_as_of should be 2025-01-02 (denom is more stale)
    assert body["_meta"]["data_as_of"] == "2025-01-02"


@pytest.mark.asyncio
async def test_denomination_common_intersection_only(client: AsyncClient) -> None:
    """Only dates in BOTH series appear in output."""
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)
    # Denom only has the second date (2025-06-01)
    partial_denom = [(date(2025, 6, 1), Decimal("120.0000"))]

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch(_HEALTH_CHECK, return_value=[]),
        patch(_GET_DENOM, new=AsyncMock(return_value=partial_denom)),
    ):
        resp = await client.get("/api/instruments/RELIANCE/price?denomination=gold")

    assert resp.status_code == 200
    body = resp.json()
    # Only 2025-06-01 is common; 2025-01-02 excluded
    assert len(body["data"]) == 1
    assert body["data"][0]["trade_date"] == "2025-06-01"


@pytest.mark.asyncio
async def test_denomination_cache_hit_skips_db(client: AsyncClient) -> None:
    """Second call within TTL uses cache (denom fetch called only once)."""
    import backend.routes.instruments as _instruments_module

    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    # Clear the cache before this test
    _instruments_module._DENOM_CACHE.clear()

    fetch_count = 0

    async def _fake_get_global(self: Any, ticker: str, from_date: Any, to_date: Any) -> Any:
        nonlocal fetch_count
        fetch_count += 1
        return _GOLD_SERIES

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch.object(_JIP_SVC, "get_global_price_series", new=_fake_get_global),
        patch(_HEALTH_CHECK, return_value=[]),
    ):
        resp1 = await client.get(
            "/api/instruments/RELIANCE/price?denomination=gold&from_date=2025-01-01&to_date=2025-12-31"
        )
        resp2 = await client.get(
            "/api/instruments/RELIANCE/price?denomination=gold&from_date=2025-01-01&to_date=2025-12-31"
        )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # DB fetch should only happen once; second call served from cache
    assert fetch_count == 1, f"Expected 1 DB fetch, got {fetch_count}"


@pytest.mark.asyncio
async def test_denomination_cache_hit_timing(client: AsyncClient) -> None:
    """Second call within TTL completes in < 200ms (cache bypass, no network call)."""
    import time as _time

    import backend.routes.instruments as _instruments_module

    _instruments_module._DENOM_CACHE.clear()
    mock_ctx, _ = _make_session_ctx(symbol_exists=True)

    async def _fake_get_global(self: Any, ticker: str, from_date: Any, to_date: Any) -> Any:
        return _GOLD_SERIES

    with (
        patch(_SESSION_FACTORY, return_value=mock_ctx),
        patch.object(_JIP_SVC, "get_chart_data", new=AsyncMock(return_value=_SAMPLE_PRICES)),
        patch.object(_JIP_SVC, "get_corporate_actions", new=AsyncMock(return_value=[])),
        patch.object(_JIP_SVC, "get_global_price_series", new=_fake_get_global),
        patch(_HEALTH_CHECK, return_value=[]),
    ):
        # First call (populates cache)
        await client.get(
            "/api/instruments/RELIANCE/price?denomination=gold&from_date=2025-01-01&to_date=2025-12-31"
        )
        # Second call (should hit cache)
        t0 = _time.monotonic()
        resp = await client.get(
            "/api/instruments/RELIANCE/price?denomination=gold&from_date=2025-01-01&to_date=2025-12-31"
        )
        elapsed_ms = (_time.monotonic() - t0) * 1000

    assert resp.status_code == 200
    assert elapsed_ms < 200, f"Cache hit took {elapsed_ms:.1f}ms, expected < 200ms"
