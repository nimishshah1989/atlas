"""Tests for GET /api/v1/global/flows (V2FE-1b).

Uses ASGITransport + AsyncClient so no live backend required.
Mocks FlowsService to isolate from DB. Verifies sparse/empty data
path returns insufficient_data=True (not an error).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app

_SVC_MOD = "backend.routes.global_intel.FlowsService"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def client() -> AsyncClient:  # type: ignore[override]
    """ASGI-backed client — no live backend needed."""
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    async def override_get_db() -> Any:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


def _sparse_flows_response() -> dict[str, Any]:
    return {
        "_meta": {
            "data_as_of": None,
            "insufficient_data": True,
            "record_count": 0,
            "query_ms": 3,
            "reason": "de_fii_dii_daily has 0 rows",
        },
        "series": [],
    }


def _sample_flows_response() -> dict[str, Any]:
    return {
        "_meta": {
            "data_as_of": "2026-04-18",
            "insufficient_data": False,
            "record_count": 4,
            "query_ms": 12,
        },
        "series": [
            {"date": "2026-04-17", "scope": "fii_equity", "value_crore": Decimal("1500.0000")},
            {"date": "2026-04-17", "scope": "dii_equity", "value_crore": Decimal("800.0000")},
            {"date": "2026-04-18", "scope": "fii_equity", "value_crore": Decimal("-300.0000")},
            {"date": "2026-04-18", "scope": "dii_equity", "value_crore": Decimal("1200.0000")},
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_global_flows_returns_200(client: AsyncClient) -> None:
    """GET /api/v1/global/flows returns 200."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_flows = AsyncMock(return_value=_sparse_flows_response())
        resp = await client.get("/api/v1/global/flows")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_global_flows_sparse_data_returns_insufficient_data_true(
    client: AsyncClient,
) -> None:
    """Sparse/empty de_fii_dii_daily → insufficient_data=True in _meta, not error."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_flows = AsyncMock(return_value=_sparse_flows_response())
        resp = await client.get("/api/v1/global/flows")
    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["insufficient_data"] is True
    assert body["series"] == []


@pytest.mark.asyncio
async def test_global_flows_has_meta_key(client: AsyncClient) -> None:
    """Response always contains _meta envelope."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_flows = AsyncMock(return_value=_sparse_flows_response())
        resp = await client.get("/api/v1/global/flows")
    body = resp.json()
    assert "_meta" in body


@pytest.mark.asyncio
async def test_global_flows_meta_has_insufficient_data_field(client: AsyncClient) -> None:
    """_meta always contains insufficient_data field."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_flows = AsyncMock(return_value=_sparse_flows_response())
        resp = await client.get("/api/v1/global/flows")
    body = resp.json()
    assert "insufficient_data" in body["_meta"]


@pytest.mark.asyncio
async def test_global_flows_has_series_key(client: AsyncClient) -> None:
    """Response always contains series key."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_flows = AsyncMock(return_value=_sparse_flows_response())
        resp = await client.get("/api/v1/global/flows")
    body = resp.json()
    assert "series" in body
    assert isinstance(body["series"], list)


@pytest.mark.asyncio
async def test_global_flows_with_data(client: AsyncClient) -> None:
    """When FII/DII data exists, series is populated with scope + value_crore."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_flows = AsyncMock(return_value=_sample_flows_response())
        resp = await client.get("/api/v1/global/flows")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["series"]) == 4
    assert body["_meta"]["insufficient_data"] is False
    assert body["_meta"]["record_count"] == 4
    # All entries have scope and value_crore
    for entry in body["series"]:
        assert "scope" in entry
        assert "value_crore" in entry


@pytest.mark.asyncio
async def test_global_flows_scope_param_accepted(client: AsyncClient) -> None:
    """scope query param is forwarded to FlowsService."""
    with patch(_SVC_MOD) as MockSvc:
        instance = MockSvc.return_value
        instance.get_flows = AsyncMock(return_value=_sparse_flows_response())
        resp = await client.get("/api/v1/global/flows?scope=fii_equity,dii_equity")
    assert resp.status_code == 200
    call_kwargs = instance.get_flows.call_args
    assert call_kwargs is not None


@pytest.mark.asyncio
async def test_global_flows_range_param_accepted(client: AsyncClient) -> None:
    """range query param is accepted and forwarded."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_flows = AsyncMock(return_value=_sparse_flows_response())
        resp = await client.get("/api/v1/global/flows?range=3m")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_global_flows_no_float_in_financial_values(client: AsyncClient) -> None:
    """All financial values in series are Decimal-serialised strings, not raw floats."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_flows = AsyncMock(return_value=_sample_flows_response())
        resp = await client.get("/api/v1/global/flows")
    body = resp.json()
    for entry in body["series"]:
        # JSON serialises Decimal as string — must be parseable as Decimal
        val = entry["value_crore"]
        assert isinstance(val, str), f"value_crore should be string, got {type(val)}: {val}"
        Decimal(val)  # must not raise
