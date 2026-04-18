"""Tests for derivatives routes: PCR and OI buildup.

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
_ROUTE = "backend.routes.derivatives"
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
    fo_healthy: bool = True,
    fo_reason: str = "",
    pcr_rows: list[dict[str, Any]] | None = None,
    pcr_source: str = "fo_summary",
    oi_rows: list[dict[str, Any]] | None = None,
) -> AsyncMock:
    """Build a mock JIPDerivativesService instance."""
    svc = AsyncMock()
    svc.check_fo_health = AsyncMock(return_value=(fo_healthy, fo_reason))
    svc.get_pcr_series = AsyncMock(return_value=(pcr_rows or [], pcr_source))
    svc.get_oi_buildup = AsyncMock(return_value=oi_rows or [])
    return svc


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_PCR_ROWS: list[dict[str, Any]] = [
    {
        "trade_date": date(2026, 4, 14),
        "pcr_oi": Decimal("1.2500"),
        "pcr_volume": Decimal("0.9800"),
        "total_oi": 5000000,
    },
    {
        "trade_date": date(2026, 4, 13),
        "pcr_oi": Decimal("1.1000"),
        "pcr_volume": None,
        "total_oi": 4800000,
    },
]

_SAMPLE_OI_ROWS: list[dict[str, Any]] = [
    {
        "trade_date": date(2026, 4, 14),
        "option_type": "CE",
        "total_oi": 2000000,
        "change_in_oi": 50000,
    },
    {
        "trade_date": date(2026, 4, 14),
        "option_type": "PE",
        "total_oi": 2500000,
        "change_in_oi": -30000,
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ===========================================================================
# TestPCRRoute
# ===========================================================================


class TestPCRRoute:
    @pytest.mark.asyncio
    async def test_pcr_unhealthy_empty_table_returns_503(self, client: AsyncClient) -> None:
        """503 when check_fo_health returns unhealthy (empty table)."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            fo_healthy=False,
            fo_reason="derivatives_eod:freshness=0 (de_fo_bhavcopy has no data)",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/pcr/NIFTY")

        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_pcr_detail_has_reason_field(self, client: AsyncClient) -> None:
        """503 detail must contain 'reason' key."""
        mock_ctx, _ = _make_session_ctx()
        reason = "derivatives_eod:freshness=0 (de_fo_bhavcopy has no data)"
        mock_svc = _make_svc_mock(fo_healthy=False, fo_reason=reason)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/pcr/NIFTY")

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "reason" in detail
        assert "freshness" in detail["reason"]

    @pytest.mark.asyncio
    async def test_pcr_healthy_returns_200(self, client: AsyncClient) -> None:
        """200 when health check passes and data is available."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            fo_healthy=True,
            pcr_rows=_SAMPLE_PCR_ROWS,
            pcr_source="fo_summary",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/pcr/NIFTY")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_pcr_healthy_response_shape(self, client: AsyncClient) -> None:
        """Response has 'data' list and '_meta' dict (§20.4 envelope)."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            fo_healthy=True,
            pcr_rows=_SAMPLE_PCR_ROWS,
            pcr_source="fo_summary",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/pcr/NIFTY")

        body = resp.json()
        assert "data" in body
        assert "_meta" in body
        assert isinstance(body["data"], list)
        assert isinstance(body["_meta"], dict)
        assert body["_meta"]["symbol"] == "NIFTY"
        assert body["_meta"]["point_count"] == len(_SAMPLE_PCR_ROWS)
        assert body["_meta"]["data_source"] == "fo_summary"

    @pytest.mark.asyncio
    async def test_pcr_invalid_date_range_400(self, client: AsyncClient) -> None:
        """from_date > to_date returns HTTP 400 with INVALID_DATE_RANGE."""
        resp = await client.get(
            "/api/derivatives/pcr/NIFTY?from_date=2026-04-14&to_date=2026-04-01"
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["error"]["code"] == "INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_pcr_empty_data_still_200(self, client: AsyncClient) -> None:
        """Healthy table but no data in range → 200 with empty data list."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(fo_healthy=True, pcr_rows=[], pcr_source="fo_summary")

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/pcr/NIFTY")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["point_count"] == 0
        assert body["_meta"]["data_as_of"] is None

    @pytest.mark.asyncio
    async def test_pcr_null_pcr_volume_allowed(self, client: AsyncClient) -> None:
        """pcr_volume=None is valid — should not raise or coerce to 0."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            fo_healthy=True,
            pcr_rows=[
                {
                    "trade_date": date(2026, 4, 14),
                    "pcr_oi": Decimal("1.25"),
                    "pcr_volume": None,
                    "total_oi": 5000000,
                }
            ],
            pcr_source="fo_bhavcopy_computed",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/pcr/NIFTY")

        assert resp.status_code == 200
        row = resp.json()["data"][0]
        assert row["pcr_volume"] is None

    @pytest.mark.asyncio
    async def test_pcr_stale_table_returns_503(self, client: AsyncClient) -> None:
        """503 when staleness reason given (stale, not zero)."""
        mock_ctx, _ = _make_session_ctx()
        reason = "derivatives_eod:freshness=stale (last trade_date=2026-04-01, lag=17d)"
        mock_svc = _make_svc_mock(fo_healthy=False, fo_reason=reason)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/pcr/NIFTY")

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "stale" in detail["reason"]

    @pytest.mark.asyncio
    async def test_pcr_symbol_uppercased_in_meta(self, client: AsyncClient) -> None:
        """Symbol in _meta is always upper-cased."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            fo_healthy=True, pcr_rows=_SAMPLE_PCR_ROWS, pcr_source="fo_summary"
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/pcr/nifty")

        assert resp.status_code == 200
        assert resp.json()["_meta"]["symbol"] == "NIFTY"


# ===========================================================================
# TestOIRoute
# ===========================================================================


class TestOIRoute:
    @pytest.mark.asyncio
    async def test_oi_unhealthy_returns_503(self, client: AsyncClient) -> None:
        """503 when F&O table empty/stale."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            fo_healthy=False,
            fo_reason="derivatives_eod:freshness=0 (de_fo_bhavcopy has no data)",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/NIFTY/oi")

        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_oi_detail_has_reason_field(self, client: AsyncClient) -> None:
        """503 detail must contain 'reason' key."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            fo_healthy=False,
            fo_reason="derivatives_eod:freshness=0 (de_fo_bhavcopy has no data)",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/NIFTY/oi")

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "reason" in detail

    @pytest.mark.asyncio
    async def test_oi_healthy_returns_200(self, client: AsyncClient) -> None:
        """200 when health check passes with OI data."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(fo_healthy=True, oi_rows=_SAMPLE_OI_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/NIFTY/oi")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_oi_response_shape(self, client: AsyncClient) -> None:
        """Response has 'data' list and '_meta' dict (§20.4 envelope)."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(fo_healthy=True, oi_rows=_SAMPLE_OI_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/NIFTY/oi")

        body = resp.json()
        assert "data" in body
        assert "_meta" in body
        assert isinstance(body["data"], list)
        assert body["_meta"]["symbol"] == "NIFTY"
        assert body["_meta"]["point_count"] == len(_SAMPLE_OI_ROWS)

    @pytest.mark.asyncio
    async def test_oi_invalid_date_range_400(self, client: AsyncClient) -> None:
        """from_date > to_date returns HTTP 400."""
        resp = await client.get("/api/derivatives/NIFTY/oi?from_date=2026-04-14&to_date=2026-04-01")
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["error"]["code"] == "INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_oi_empty_data_still_200(self, client: AsyncClient) -> None:
        """Healthy table but no data in range → 200 with empty list."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(fo_healthy=True, oi_rows=[])

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/derivatives/NIFTY/oi")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["point_count"] == 0
        assert body["_meta"]["data_as_of"] is None
