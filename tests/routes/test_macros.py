"""Tests for macro routes: India VIX, yield curve, FX rates, RBI policy rates.

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
_MACRO_SERVICE_CLASS = f"{_ROUTE}.JIPMacroService"


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


# ---------------------------------------------------------------------------
# Helpers for macro service mocks (yield curve, FX, policy rates)
# ---------------------------------------------------------------------------


def _make_macro_svc_mock(
    yield_healthy: bool = True,
    yield_reason: str = "",
    yield_rows: list[dict[str, Any]] | None = None,
    fx_healthy: bool = True,
    fx_reason: str = "",
    fx_rows: list[dict[str, Any]] | None = None,
    policy_healthy: bool = True,
    policy_reason: str = "",
    policy_rows: list[dict[str, Any]] | None = None,
) -> AsyncMock:
    """Build a mock JIPMacroService."""
    svc = AsyncMock()
    svc.check_yield_health = AsyncMock(return_value=(yield_healthy, yield_reason))
    svc.get_yield_curve = AsyncMock(return_value=yield_rows or [])
    svc.check_fx_health = AsyncMock(return_value=(fx_healthy, fx_reason))
    svc.get_fx_rates = AsyncMock(return_value=fx_rows or [])
    svc.check_policy_health = AsyncMock(return_value=(policy_healthy, policy_reason))
    svc.get_policy_rates = AsyncMock(return_value=policy_rows or [])
    return svc


# Sample data
_SAMPLE_YIELD_ROWS: list[dict[str, Any]] = [
    {
        "yield_date": date(2026, 4, 14),
        "tenor": "1Y",
        "yield_pct": Decimal("6.2500"),
        "security_name": "91-Day T-Bill",
        "source": "CCIL",
    },
    {
        "yield_date": date(2026, 4, 14),
        "tenor": "10Y",
        "yield_pct": Decimal("6.8500"),
        "security_name": "10Y Benchmark",
        "source": "CCIL",
    },
]

_SAMPLE_FX_ROWS: list[dict[str, Any]] = [
    {
        "rate_date": date(2026, 4, 14),
        "currency_pair": "USD/INR",
        "reference_rate": Decimal("92.5750"),
        "source": "YFINANCE",
    },
    {
        "rate_date": date(2026, 4, 14),
        "currency_pair": "EUR/INR",
        "reference_rate": Decimal("108.9300"),
        "source": "YFINANCE",
    },
    {
        "rate_date": date(2026, 4, 15),
        "currency_pair": "USD/INR",
        "reference_rate": Decimal("92.8100"),
        "source": "YFINANCE",
    },
]

_SAMPLE_POLICY_ROWS: list[dict[str, Any]] = [
    {
        "effective_date": date(2026, 4, 14),
        "rate_type": "REPO",
        "rate_pct": Decimal("6.0000"),
        "source": "RBI",
    },
    {
        "effective_date": date(2026, 4, 14),
        "rate_type": "CRR",
        "rate_pct": Decimal("4.0000"),
        "source": "RBI",
    },
    {
        "effective_date": date(2026, 4, 15),
        "rate_type": "REPO",
        "rate_pct": Decimal("6.0000"),
        "source": "RBI",
    },
]


# ===========================================================================
# TestYieldCurveRoute
# ===========================================================================


class TestYieldCurveRoute:
    @pytest.mark.asyncio
    async def test_yield_unhealthy_empty_returns_503(self, client: AsyncClient) -> None:
        """503 when check_yield_health returns unhealthy (empty table)."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(
            yield_healthy=False,
            yield_reason="yield_curve:freshness=0 (de_gsec_yield has no data)",
        )
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/yield-curve")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_yield_503_detail_has_reason(self, client: AsyncClient) -> None:
        """503 detail must contain 'reason' key with 'yield_curve' substring."""
        mock_ctx, _ = _make_session_ctx()
        reason = "yield_curve:freshness=0 (de_gsec_yield has no data)"
        mock_svc = _make_macro_svc_mock(yield_healthy=False, yield_reason=reason)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/yield-curve")
        detail = resp.json()["detail"]
        assert "reason" in detail
        assert "yield_curve" in detail["reason"]

    @pytest.mark.asyncio
    async def test_yield_healthy_returns_200(self, client: AsyncClient) -> None:
        """200 when healthy with data."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(yield_rows=_SAMPLE_YIELD_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/yield-curve")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_yield_response_shape(self, client: AsyncClient) -> None:
        """Response has 'data' list and '_meta' dict with expected keys."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(yield_rows=_SAMPLE_YIELD_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/yield-curve")
        body = resp.json()
        assert "data" in body
        assert "_meta" in body
        assert isinstance(body["data"], list)
        assert isinstance(body["_meta"], dict)
        assert "date_count" in body["_meta"]
        assert "point_count" in body["_meta"]
        assert "data_as_of" in body["_meta"]

    @pytest.mark.asyncio
    async def test_yield_groups_by_date(self, client: AsyncClient) -> None:
        """Two tenor points on same date collapse into one entry."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(yield_rows=_SAMPLE_YIELD_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/yield-curve")
        body = resp.json()
        # Both rows share the same yield_date → 1 entry with 2 points
        assert body["_meta"]["date_count"] == 1
        assert body["_meta"]["point_count"] == 2
        entry = body["data"][0]
        assert entry["yield_date"] == "2026-04-14"
        assert len(entry["points"]) == 2

    @pytest.mark.asyncio
    async def test_yield_invalid_date_range_400(self, client: AsyncClient) -> None:
        """from_date > to_date returns HTTP 400 INVALID_DATE_RANGE."""
        resp = await client.get("/api/macros/yield-curve?from_date=2026-04-14&to_date=2026-04-01")
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_yield_empty_range_200_null_as_of(self, client: AsyncClient) -> None:
        """Healthy but no rows in range → 200, data_as_of=null."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(yield_rows=[])
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/yield-curve")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["data_as_of"] is None

    @pytest.mark.asyncio
    async def test_yield_pct_not_float(self, client: AsyncClient) -> None:
        """yield_pct must not be a float in JSON output."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(yield_rows=_SAMPLE_YIELD_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/yield-curve")
        body = resp.json()
        for entry in body["data"]:
            for pt in entry["points"]:
                assert not isinstance(pt["yield_pct"], float), (
                    f"yield_pct must not be float, got {type(pt['yield_pct'])}"
                )


# ===========================================================================
# TestFXRatesRoute
# ===========================================================================


class TestFXRatesRoute:
    @pytest.mark.asyncio
    async def test_fx_unhealthy_returns_503(self, client: AsyncClient) -> None:
        """503 when check_fx_health returns unhealthy."""
        mock_ctx, _ = _make_session_ctx()
        reason = "fx_rates:freshness=0 (de_rbi_fx_rate has no data)"
        mock_svc = _make_macro_svc_mock(fx_healthy=False, fx_reason=reason)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/fx")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_fx_503_detail_has_reason(self, client: AsyncClient) -> None:
        """503 detail must have 'reason' containing 'fx_rates'."""
        mock_ctx, _ = _make_session_ctx()
        reason = "fx_rates:freshness=stale (last rate_date=2026-03-01, lag=48d)"
        mock_svc = _make_macro_svc_mock(fx_healthy=False, fx_reason=reason)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/fx")
        detail = resp.json()["detail"]
        assert "reason" in detail
        assert "fx_rates" in detail["reason"]

    @pytest.mark.asyncio
    async def test_fx_healthy_returns_200(self, client: AsyncClient) -> None:
        """200 when healthy with data."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(fx_rows=_SAMPLE_FX_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/fx")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_fx_response_shape(self, client: AsyncClient) -> None:
        """Response has 'data' list, '_meta' dict with currency_pairs and point_count."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(fx_rows=_SAMPLE_FX_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/fx")
        body = resp.json()
        assert "data" in body
        assert "_meta" in body
        assert "currency_pairs" in body["_meta"]
        assert "point_count" in body["_meta"]
        assert "data_as_of" in body["_meta"]

    @pytest.mark.asyncio
    async def test_fx_currency_pairs_collected(self, client: AsyncClient) -> None:
        """Distinct currency pairs present in data are listed in _meta.currency_pairs."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(fx_rows=_SAMPLE_FX_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/fx")
        body = resp.json()
        pairs = body["_meta"]["currency_pairs"]
        assert "EUR/INR" in pairs
        assert "USD/INR" in pairs
        assert body["_meta"]["point_count"] == 3

    @pytest.mark.asyncio
    async def test_fx_invalid_date_range_400(self, client: AsyncClient) -> None:
        """from_date > to_date returns HTTP 400."""
        resp = await client.get("/api/macros/fx?from_date=2026-04-14&to_date=2026-04-01")
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_fx_reference_rate_not_float(self, client: AsyncClient) -> None:
        """reference_rate must not be a float in JSON output."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(fx_rows=_SAMPLE_FX_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/fx")
        body = resp.json()
        for row in body["data"]:
            assert not isinstance(row["reference_rate"], float), (
                f"reference_rate must not be float, got {type(row['reference_rate'])}"
            )

    @pytest.mark.asyncio
    async def test_fx_data_as_of_max_date(self, client: AsyncClient) -> None:
        """data_as_of equals the most recent rate_date in the response."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(fx_rows=_SAMPLE_FX_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/fx")
        body = resp.json()
        assert body["_meta"]["data_as_of"] == "2026-04-15"

    @pytest.mark.asyncio
    async def test_fx_empty_returns_200_null_as_of(self, client: AsyncClient) -> None:
        """Healthy but no rows in range → 200, data_as_of=null."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(fx_rows=[])
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/fx")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["data_as_of"] is None


# ===========================================================================
# TestPolicyRatesRoute
# ===========================================================================


class TestPolicyRatesRoute:
    @pytest.mark.asyncio
    async def test_policy_unhealthy_returns_503(self, client: AsyncClient) -> None:
        """503 when check_policy_health returns unhealthy."""
        mock_ctx, _ = _make_session_ctx()
        reason = "policy_rates:freshness=0 (de_rbi_policy_rate has no data)"
        mock_svc = _make_macro_svc_mock(policy_healthy=False, policy_reason=reason)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/policy-rates")
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_policy_503_detail_has_reason(self, client: AsyncClient) -> None:
        """503 detail must have 'reason' containing 'policy_rates'."""
        mock_ctx, _ = _make_session_ctx()
        reason = "policy_rates:freshness=stale (last effective_date=2026-03-01, lag=48d)"
        mock_svc = _make_macro_svc_mock(policy_healthy=False, policy_reason=reason)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/policy-rates")
        detail = resp.json()["detail"]
        assert "reason" in detail
        assert "policy_rates" in detail["reason"]

    @pytest.mark.asyncio
    async def test_policy_healthy_returns_200(self, client: AsyncClient) -> None:
        """200 when healthy with data."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(policy_rows=_SAMPLE_POLICY_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/policy-rates")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_policy_response_shape(self, client: AsyncClient) -> None:
        """Response has 'data' list and '_meta' dict with rate_types and point_count."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(policy_rows=_SAMPLE_POLICY_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/policy-rates")
        body = resp.json()
        assert "data" in body
        assert "_meta" in body
        assert "rate_types" in body["_meta"]
        assert "point_count" in body["_meta"]
        assert "data_as_of" in body["_meta"]

    @pytest.mark.asyncio
    async def test_policy_rate_types_collected(self, client: AsyncClient) -> None:
        """Distinct rate_types present are listed in _meta.rate_types."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(policy_rows=_SAMPLE_POLICY_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/policy-rates")
        body = resp.json()
        types = body["_meta"]["rate_types"]
        assert "REPO" in types
        assert "CRR" in types
        assert body["_meta"]["point_count"] == 3

    @pytest.mark.asyncio
    async def test_policy_invalid_date_range_400(self, client: AsyncClient) -> None:
        """from_date > to_date returns HTTP 400."""
        resp = await client.get("/api/macros/policy-rates?from_date=2026-04-14&to_date=2026-04-01")
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_policy_rate_pct_not_float(self, client: AsyncClient) -> None:
        """rate_pct must not be a float in JSON output."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(policy_rows=_SAMPLE_POLICY_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/policy-rates")
        body = resp.json()
        for row in body["data"]:
            assert not isinstance(row["rate_pct"], float), (
                f"rate_pct must not be float, got {type(row['rate_pct'])}"
            )

    @pytest.mark.asyncio
    async def test_policy_data_as_of_max_date(self, client: AsyncClient) -> None:
        """data_as_of equals the most recent effective_date in data."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(policy_rows=_SAMPLE_POLICY_ROWS)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/policy-rates")
        body = resp.json()
        assert body["_meta"]["data_as_of"] == "2026-04-15"

    @pytest.mark.asyncio
    async def test_policy_empty_returns_200_null_as_of(self, client: AsyncClient) -> None:
        """Healthy but no rows in range → 200, data_as_of=null."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_macro_svc_mock(policy_rows=[])
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/policy-rates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["data_as_of"] is None

    @pytest.mark.asyncio
    async def test_policy_stale_returns_503(self, client: AsyncClient) -> None:
        """503 when policy health returns stale reason."""
        mock_ctx, _ = _make_session_ctx()
        reason = "policy_rates:freshness=stale (last effective_date=2026-03-01, lag=48d)"
        mock_svc = _make_macro_svc_mock(policy_healthy=False, policy_reason=reason)
        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_MACRO_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/macros/policy-rates")
        assert resp.status_code == 503
        assert "stale" in resp.json()["detail"]["reason"]
