"""Tests for insider + bulk/block deal routes.

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
_ROUTE = "backend.routes.insider"
_SESSION_FACTORY = f"{_ROUTE}.async_session_factory"
_SERVICE_CLASS = f"{_ROUTE}.JIPInsiderService"


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
    insider_healthy: bool = True,
    insider_reason: str = "",
    insider_rows: list[dict[str, Any]] | None = None,
    bulk_healthy: bool = True,
    bulk_reason: str = "",
    bulk_rows: list[dict[str, Any]] | None = None,
    block_healthy: bool = True,
    block_reason: str = "",
    block_rows: list[dict[str, Any]] | None = None,
) -> AsyncMock:
    """Build a mock JIPInsiderService instance."""
    svc = AsyncMock()
    svc.check_insider_health = AsyncMock(return_value=(insider_healthy, insider_reason))
    svc.get_insider_trades = AsyncMock(return_value=insider_rows or [])
    svc.check_bulk_health = AsyncMock(return_value=(bulk_healthy, bulk_reason))
    svc.get_bulk_deals = AsyncMock(return_value=bulk_rows or [])
    svc.check_block_health = AsyncMock(return_value=(block_healthy, block_reason))
    svc.get_block_deals = AsyncMock(return_value=block_rows or [])
    return svc


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_INSIDER_ROWS: list[dict[str, Any]] = [
    {
        "txn_date": date(2026, 4, 10),
        "filing_date": date(2026, 4, 12),
        "person_name": "John Doe",
        "person_category": "Promoter",
        "txn_type": "Buy",
        "qty": 50000,
        "value_inr": Decimal("2500000.0000"),
        "post_holding_pct": Decimal("25.4200"),
    },
    {
        "txn_date": date(2026, 4, 8),
        "filing_date": date(2026, 4, 9),
        "person_name": "Jane Smith",
        "person_category": "Director",
        "txn_type": "Sell",
        "qty": 10000,
        "value_inr": Decimal("500000.0000"),
        "post_holding_pct": Decimal("3.1500"),
    },
]

_SAMPLE_BULK_ROWS: list[dict[str, Any]] = [
    {
        "trade_date": date(2026, 4, 14),
        "client_name": "ABC Mutual Fund",
        "txn_type": "Buy",
        "qty": 200000,
        "avg_price": Decimal("512.5000"),
    },
    {
        "trade_date": date(2026, 4, 13),
        "client_name": "XYZ Insurance",
        "txn_type": "Sell",
        "qty": 150000,
        "avg_price": Decimal("508.2500"),
    },
]

_SAMPLE_BLOCK_ROWS: list[dict[str, Any]] = [
    {
        "trade_date": date(2026, 4, 14),
        "client_name": "DEF Fund",
        "txn_type": "Buy",
        "qty": 500000,
        "trade_price": Decimal("510.0000"),
    },
    {
        "trade_date": date(2026, 4, 12),
        "client_name": "GHI Corp",
        "txn_type": "Sell",
        "qty": 300000,
        "trade_price": Decimal("505.7500"),
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
# TestInsiderRoute
# ===========================================================================


class TestInsiderRoute:
    @pytest.mark.asyncio
    async def test_insider_unhealthy_returns_503(self, client: AsyncClient) -> None:
        """503 when check_insider_health returns unhealthy (empty table)."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            insider_healthy=False,
            insider_reason="insider_trades:freshness=0 (de_insider_trades has no data)",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/insider")

        assert resp.status_code == 503
        assert "reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_insider_empty_list_when_no_rows_in_range(self, client: AsyncClient) -> None:
        """Healthy table but no rows in date range → 200 with empty data list."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(insider_healthy=True, insider_rows=[])

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/insider")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["point_count"] == 0
        assert body["_meta"]["data_as_of"] is None

    @pytest.mark.asyncio
    async def test_insider_returns_rows_correctly(self, client: AsyncClient) -> None:
        """All insider trade fields are present and correctly typed."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(insider_healthy=True, insider_rows=_SAMPLE_INSIDER_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/insider")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        row = body["data"][0]
        assert row["txn_date"] == "2026-04-10"
        assert row["filing_date"] == "2026-04-12"
        assert row["person_name"] == "John Doe"
        assert row["person_category"] == "Promoter"
        assert row["txn_type"] == "Buy"
        assert row["qty"] == 50000
        assert body["_meta"]["point_count"] == 2

    @pytest.mark.asyncio
    async def test_insider_default_date_range(self, client: AsyncClient) -> None:
        """No date params → default 90-day window applied."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(insider_healthy=True, insider_rows=[])

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/insider")

        assert resp.status_code == 200
        meta = resp.json()["_meta"]
        assert meta["from_date"] is not None
        assert meta["to_date"] is not None

    @pytest.mark.asyncio
    async def test_insider_custom_date_range(self, client: AsyncClient) -> None:
        """Custom from_date and to_date are echoed in _meta."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(insider_healthy=True, insider_rows=_SAMPLE_INSIDER_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get(
                "/api/stocks/RELIANCE/insider?from_date=2026-01-01&to_date=2026-04-18"
            )

        assert resp.status_code == 200
        meta = resp.json()["_meta"]
        assert meta["from_date"] == "2026-01-01"
        assert meta["to_date"] == "2026-04-18"

    @pytest.mark.asyncio
    async def test_insider_limit_param(self, client: AsyncClient) -> None:
        """limit param is reflected in _meta."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(insider_healthy=True, insider_rows=_SAMPLE_INSIDER_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/insider?limit=50")

        assert resp.status_code == 200
        assert resp.json()["_meta"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_insider_invalid_date_range_400(self, client: AsyncClient) -> None:
        """from_date > to_date → HTTP 400 INVALID_DATE_RANGE."""
        resp = await client.get(
            "/api/stocks/RELIANCE/insider?from_date=2026-04-14&to_date=2026-04-01"
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_insider_symbol_uppercased_in_meta(self, client: AsyncClient) -> None:
        """Symbol is always upper-cased in _meta."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(insider_healthy=True, insider_rows=_SAMPLE_INSIDER_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/reliance/insider")

        assert resp.status_code == 200
        assert resp.json()["_meta"]["symbol"] == "RELIANCE"

    @pytest.mark.asyncio
    async def test_insider_response_has_data_and_meta_keys(self, client: AsyncClient) -> None:
        """Response has 'data' + '_meta' keys per §20.4 envelope."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(insider_healthy=True, insider_rows=_SAMPLE_INSIDER_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/insider")

        body = resp.json()
        assert "data" in body
        assert "_meta" in body
        assert isinstance(body["data"], list)
        assert isinstance(body["_meta"], dict)


# ===========================================================================
# TestBulkDealsRoute
# ===========================================================================


class TestBulkDealsRoute:
    @pytest.mark.asyncio
    async def test_bulk_unhealthy_returns_503(self, client: AsyncClient) -> None:
        """503 when check_bulk_health returns unhealthy."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            bulk_healthy=False,
            bulk_reason="bulk_deals:freshness=0 (de_bulk_deals has no data)",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/bulk-deals")

        assert resp.status_code == 503
        assert "reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_bulk_empty_list_when_no_rows(self, client: AsyncClient) -> None:
        """Healthy table but no rows → 200 with empty data list."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(bulk_healthy=True, bulk_rows=[])

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/bulk-deals")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["point_count"] == 0
        assert body["_meta"]["data_as_of"] is None

    @pytest.mark.asyncio
    async def test_bulk_returns_rows_correctly(self, client: AsyncClient) -> None:
        """All bulk deal fields are present and correct."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(bulk_healthy=True, bulk_rows=_SAMPLE_BULK_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/bulk-deals")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        row = body["data"][0]
        assert row["trade_date"] == "2026-04-14"
        assert row["client_name"] == "ABC Mutual Fund"
        assert row["txn_type"] == "Buy"
        assert row["qty"] == 200000
        assert body["_meta"]["point_count"] == 2

    @pytest.mark.asyncio
    async def test_bulk_default_date_range(self, client: AsyncClient) -> None:
        """No date params → default 30-day window applied."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(bulk_healthy=True, bulk_rows=[])

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/bulk-deals")

        assert resp.status_code == 200
        meta = resp.json()["_meta"]
        assert meta["from_date"] is not None
        assert meta["to_date"] is not None

    @pytest.mark.asyncio
    async def test_bulk_custom_date_range(self, client: AsyncClient) -> None:
        """Custom from_date and to_date are echoed in _meta."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(bulk_healthy=True, bulk_rows=_SAMPLE_BULK_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get(
                "/api/stocks/RELIANCE/bulk-deals?from_date=2026-03-01&to_date=2026-04-18"
            )

        assert resp.status_code == 200
        meta = resp.json()["_meta"]
        assert meta["from_date"] == "2026-03-01"
        assert meta["to_date"] == "2026-04-18"

    @pytest.mark.asyncio
    async def test_bulk_invalid_date_range_400(self, client: AsyncClient) -> None:
        """from_date > to_date → HTTP 400."""
        resp = await client.get(
            "/api/stocks/RELIANCE/bulk-deals?from_date=2026-04-14&to_date=2026-04-01"
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_bulk_decimal_fields_preserved(self, client: AsyncClient) -> None:
        """avg_price Decimal preserved in JSON response (not lost to float rounding)."""
        mock_ctx, _ = _make_session_ctx()
        rows = [
            {
                "trade_date": date(2026, 4, 14),
                "client_name": "Precision Fund",
                "txn_type": "Buy",
                "qty": 100,
                "avg_price": Decimal("512.1234"),
            }
        ]
        mock_svc = _make_svc_mock(bulk_healthy=True, bulk_rows=rows)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/bulk-deals")

        assert resp.status_code == 200
        row = resp.json()["data"][0]
        # Decimal serialized to string in JSON via model_dump(mode="json")
        assert row["avg_price"] is not None

    @pytest.mark.asyncio
    async def test_bulk_response_has_data_and_meta_keys(self, client: AsyncClient) -> None:
        """Bulk response has 'data' + '_meta' keys per §20.4 envelope."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(bulk_healthy=True, bulk_rows=_SAMPLE_BULK_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/bulk-deals")

        body = resp.json()
        assert "data" in body
        assert "_meta" in body


# ===========================================================================
# TestBlockDealsRoute
# ===========================================================================


class TestBlockDealsRoute:
    @pytest.mark.asyncio
    async def test_block_unhealthy_returns_503(self, client: AsyncClient) -> None:
        """503 when check_block_health returns unhealthy."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(
            block_healthy=False,
            block_reason="block_deals:freshness=0 (de_block_deals has no data)",
        )

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/block-deals")

        assert resp.status_code == 503
        assert "reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_block_empty_list_when_no_rows(self, client: AsyncClient) -> None:
        """Healthy table but no rows → 200 with empty data list."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(block_healthy=True, block_rows=[])

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/block-deals")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["_meta"]["point_count"] == 0
        assert body["_meta"]["data_as_of"] is None

    @pytest.mark.asyncio
    async def test_block_returns_rows_correctly(self, client: AsyncClient) -> None:
        """All block deal fields are present and correct."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(block_healthy=True, block_rows=_SAMPLE_BLOCK_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/block-deals")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        row = body["data"][0]
        assert row["trade_date"] == "2026-04-14"
        assert row["client_name"] == "DEF Fund"
        assert row["txn_type"] == "Buy"
        assert row["qty"] == 500000
        assert body["_meta"]["point_count"] == 2

    @pytest.mark.asyncio
    async def test_block_default_date_range(self, client: AsyncClient) -> None:
        """No date params → default 30-day window applied."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(block_healthy=True, block_rows=[])

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/block-deals")

        assert resp.status_code == 200
        meta = resp.json()["_meta"]
        assert meta["from_date"] is not None
        assert meta["to_date"] is not None

    @pytest.mark.asyncio
    async def test_block_custom_date_range(self, client: AsyncClient) -> None:
        """Custom from_date and to_date are echoed in _meta."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(block_healthy=True, block_rows=_SAMPLE_BLOCK_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get(
                "/api/stocks/RELIANCE/block-deals?from_date=2026-03-01&to_date=2026-04-18"
            )

        assert resp.status_code == 200
        meta = resp.json()["_meta"]
        assert meta["from_date"] == "2026-03-01"
        assert meta["to_date"] == "2026-04-18"

    @pytest.mark.asyncio
    async def test_block_invalid_date_range_400(self, client: AsyncClient) -> None:
        """from_date > to_date → HTTP 400."""
        resp = await client.get(
            "/api/stocks/RELIANCE/block-deals?from_date=2026-04-14&to_date=2026-04-01"
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "INVALID_DATE_RANGE"

    @pytest.mark.asyncio
    async def test_block_trade_price_decimal_in_response(self, client: AsyncClient) -> None:
        """trade_price Decimal is serialized correctly (not lost to float)."""
        mock_ctx, _ = _make_session_ctx()
        rows = [
            {
                "trade_date": date(2026, 4, 14),
                "client_name": "Precision Corp",
                "txn_type": "Buy",
                "qty": 100,
                "trade_price": Decimal("510.1234"),
            }
        ]
        mock_svc = _make_svc_mock(block_healthy=True, block_rows=rows)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/block-deals")

        assert resp.status_code == 200
        row = resp.json()["data"][0]
        assert row["trade_price"] is not None

    @pytest.mark.asyncio
    async def test_block_response_has_data_and_meta_keys(self, client: AsyncClient) -> None:
        """Block response has 'data' + '_meta' keys; bulk too (§20.4)."""
        mock_ctx, _ = _make_session_ctx()
        mock_svc = _make_svc_mock(block_healthy=True, block_rows=_SAMPLE_BLOCK_ROWS)

        with (
            patch(_SESSION_FACTORY, return_value=mock_ctx),
            patch(_SERVICE_CLASS, return_value=mock_svc),
        ):
            resp = await client.get("/api/stocks/RELIANCE/block-deals")

        body = resp.json()
        assert "data" in body
        assert "_meta" in body
        assert isinstance(body["data"], list)
        assert isinstance(body["_meta"], dict)


# ===========================================================================
# TestJIPInsiderServiceColumnNames
# Regression tests: verify correct SQL column names after JIP schema discovery.
# de_insider_trades uses transaction_date/disclosure_date/transaction_type/quantity
# (not txn_date/filing_date/txn_type/qty).
# ===========================================================================


class TestJIPInsiderServiceColumnNames:
    """Unit tests for JIPInsiderService SQL correctness (no route layer)."""

    @pytest.mark.asyncio
    async def test_check_insider_health_queries_transaction_date(self) -> None:
        """check_insider_health must use transaction_date column (not txn_date)."""
        from backend.clients.jip_insider_service import JIPInsiderService

        mock_session = AsyncMock()
        # Simulate a healthy table: count=100, max_date=today
        from datetime import UTC, datetime

        today = datetime.now(UTC).date()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (100, today)
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = JIPInsiderService(mock_session)
        healthy, reason = await svc.check_insider_health()

        assert healthy is True
        assert reason == ""
        # Verify the SQL used transaction_date, not txn_date
        executed_sql: str = str(mock_session.execute.call_args[0][0])
        assert "transaction_date" in executed_sql
        assert "txn_date" not in executed_sql

    @pytest.mark.asyncio
    async def test_check_insider_health_handles_exception_gracefully(self) -> None:
        """check_insider_health returns (False, reason) on DB exception, does not raise."""
        from backend.clients.jip_insider_service import JIPInsiderService

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception('column "txn_date" does not exist'))

        svc = JIPInsiderService(mock_session)
        healthy, reason = await svc.check_insider_health()

        assert healthy is False
        assert "insider_trades:health_probe_failed" in reason

    @pytest.mark.asyncio
    async def test_get_insider_trades_uses_column_aliases(self) -> None:
        """get_insider_trades SQL must alias transaction_date→txn_date, disclosure_date→filing_date,
        transaction_type→txn_type, quantity→qty."""
        from datetime import date

        from backend.clients.jip_insider_service import JIPInsiderService

        mock_session = AsyncMock()
        mock_mappings = MagicMock()
        mock_mappings.all.return_value = []
        mock_result = MagicMock()
        mock_result.mappings.return_value = mock_mappings
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = JIPInsiderService(mock_session)
        rows = await svc.get_insider_trades(
            symbol="RELIANCE",
            from_date=date(2026, 1, 1),
            to_date=date(2026, 4, 18),
        )

        assert rows == []
        executed_sql: str = str(mock_session.execute.call_args[0][0])
        # Verify actual column names (not legacy aliases) appear in the SELECT
        assert "transaction_date" in executed_sql
        assert "disclosure_date" in executed_sql
        assert "transaction_type" in executed_sql
        assert "quantity" in executed_sql
        # Verify aliases to legacy contract names
        assert "AS txn_date" in executed_sql or "txn_date" in executed_sql
        assert "AS filing_date" in executed_sql or "filing_date" in executed_sql
        assert "AS txn_type" in executed_sql or "txn_type" in executed_sql
        assert "AS qty" in executed_sql or "qty" in executed_sql

    @pytest.mark.asyncio
    async def test_check_bulk_health_handles_missing_table_gracefully(self) -> None:
        """check_bulk_health returns (False, reason) when de_bulk_deals does not exist."""
        from backend.clients.jip_insider_service import JIPInsiderService

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=Exception('relation "de_bulk_deals" does not exist')
        )

        svc = JIPInsiderService(mock_session)
        healthy, reason = await svc.check_bulk_health()

        assert healthy is False
        assert "bulk_deals:table_unavailable" in reason

    @pytest.mark.asyncio
    async def test_check_block_health_handles_missing_table_gracefully(self) -> None:
        """check_block_health returns (False, reason) when de_block_deals does not exist."""
        from backend.clients.jip_insider_service import JIPInsiderService

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=Exception('relation "de_block_deals" does not exist')
        )

        svc = JIPInsiderService(mock_session)
        healthy, reason = await svc.check_block_health()

        assert healthy is False
        assert "block_deals:table_unavailable" in reason

    @pytest.mark.asyncio
    async def test_check_insider_health_stale_data_returns_unhealthy(self) -> None:
        """check_insider_health returns unhealthy when max transaction_date is stale."""
        from datetime import UTC, datetime, timedelta

        from backend.clients.jip_insider_service import JIPInsiderService

        mock_session = AsyncMock()
        stale_date = datetime.now(UTC).date() - timedelta(days=10)
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (500, stale_date)
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = JIPInsiderService(mock_session)
        healthy, reason = await svc.check_insider_health()

        assert healthy is False
        assert "stale" in reason
        assert "transaction_date" in reason
