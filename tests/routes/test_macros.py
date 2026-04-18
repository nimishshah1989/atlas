"""Tests for macro routes: India VIX.

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

from backend.db.session import get_db
from backend.main import app

# Module-level patch path aliases
_ROUTE = "backend.routes.macros"
_SESSION_FACTORY = f"{_ROUTE}.async_session_factory"
_SERVICE_CLASS = f"{_ROUTE}.JIPDerivativesService"


# ---------------------------------------------------------------------------
# DB dependency override -- avoids real DB connection
# ---------------------------------------------------------------------------


async def _fake_db() -> Any:  # type: ignore[return]
    """Return a no-op async session mock."""
    yield MagicMock()


app.dependency_overrides[get_db] = _fake_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_ctx() -> Any:
    """Build an async context manager mock simulating session factory."""
    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_session


def _make_svc_mock(
    vix_healthy: bool = True,
    vix_reason: str = "",
    vix_rows: list[dict[str, Any]] | None = None,
) -> AsyncMock:
    """Build a mock JIPDerivativesService instance for macro routes."""
    svc = AsyncMock()
    svc.check_vix_health = AsyncMock(return_value=(vix_healthy, vix_reason))
    svc.get_india_vix = AsyncMock(return_value=vix_rows or [])
    return svc


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_VIX_ROWS: list[dict[str, Any]] = [
    {"trade_date": date(2026, 4, 13), "close": Decimal("13.45")},
    {"trade_date": date(2026, 4, 14), "close": Decimal("14.20")},
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ===========================================================================
# TestVIXRoute
# ===========================================================================


class TestVIXRoute:
    @pytest.mark.asyncio
    async def test_vix_unhealthy_empty_returns_503(self, client: AsyncClient) -> None:
        """503 when check_vix_health returns unhealthy (empty table)."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            vix_healthy=False,
            vix_reason="india_vix:freshness=0 (no INDIAVIX rows in de_macro_values)",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/vix")

        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_vix_detail_has_reason_field(self, client: AsyncClient) -> None:
        """503 detail must contain 'reason' key."""
        mock_ctx, _ = _make_session_ctx()
        reason = "india_vix:freshness=0 (no INDIAVIX rows in de_macro_values)"
        mock_svc = _make_svc_mock(vix_healthy=False, vix_reason=reason)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/vix")

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "reason" in detail
        assert "india_vix" in detail["reason"]

    @pytest.mark.asyncio
    async def test_vix_healthy_returns_200(self, client: AsyncClient) -> None:
        """200 when health check passes and VIX data available."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(vix_healthy=True, vix_rows=_SAMPLE_VIX_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/vix")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_vix_response_shape(self, client: AsyncClient) -> None:
        """Response has 'data' list and '_meta' dict; ticker='INDIAVIX'."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(vix_healthy=True, vix_rows=_SAMPLE_VIX_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/vix")

        body = resp.json()
        assert "data" in body
        assert "_meta" in body
        assert isinstance(body["data"], list)
        assert isinstance(body["_meta"], dict)
        assert body["_meta"]["ticker"] == "INDIAVIX"
        assert body["_meta"]["point_count"] == len(_SAMPLE_VIX_ROWS)

    @pytest.mark.asyncio
    async def test_vix_stale_returns_503(self, client: AsyncClient) -> None:
        """503 when VIX staleness reason given."""
        mock_ctx, _ = _make_session_ctx()
        reason = "india_vix:freshness=stale (last date=2026-03-01, lag=48d)"
        mock_svc = _make_svc_mock(vix_healthy=False, vix_reason=reason)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/vix")

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "stale" in detail["reason"]

    @pytest.mark.asyncio
    async def test_vix_invalid_date_range_400(self, client: AsyncClient) -> None:
        """from_date > to_date returns HTTP 400 with INVALID_DATE_RANGE."""
        resp = await client.get("/api/macros/vix?from_date=2026-04-14&to_date=2026-04-01")
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["error"]["code"] == "INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_vix_data_as_of_max_date(self, client: AsyncClient) -> None:
        """data_as_of equals the most recent trade_date in data."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(vix_healthy=True, vix_rows=_SAMPLE_VIX_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/vix")

        body = resp.json()
        assert body["_meta"]["data_as_of"] == "2026-04-14"

    @pytest.mark.asyncio
    async def test_vix_empty_data_200_null_as_of(self, client: AsyncClient) -> None:
        """Healthy but no rows in range → 200, data_as_of=null."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(vix_healthy=True, vix_rows=[])

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/vix")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["point_count"] == 0
        assert body["_meta"]["data_as_of"] is None

    @pytest.mark.asyncio
    async def test_vix_close_is_decimal_string(self, client: AsyncClient) -> None:
        """VIX close values serialize as Decimal strings, not floats."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(vix_healthy=True, vix_rows=_SAMPLE_VIX_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/vix")

        body = resp.json()
        for row in body["data"]:
            val = row["close"]
            assert not isinstance(val, float), (
                f"close must not be float in JSON output, got {type(val)}: {val}"
            )
