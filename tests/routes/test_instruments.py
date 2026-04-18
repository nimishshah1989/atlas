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
