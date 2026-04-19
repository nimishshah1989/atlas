"""Tests for POST /api/v1/query/template (V2FE-1c).

Tests the three new templates (stock_peers, sector_breadth_template) and the
updated mf_rank_composite. Tests: valid params -> 200, missing required param -> 400,
unknown template -> 404.

Uses ASGITransport + patch on engine.execute_template so no live DB is needed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app
from backend.models.uql import UQLResponse
from backend.models.schemas import ResponseMeta

_ENGINE_MOD = "backend.routes.query.engine"

_CANNED_RESPONSE = UQLResponse(
    records=[{"symbol": "RELIANCE", "rs_composite": "75.0"}],
    total=1,
    meta=ResponseMeta(
        data_as_of="2026-04-19",
        record_count=1,
        query_ms=5,
    ),
)


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


# ---------------------------------------------------------------------------
# stock_peers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_peers_valid_params_returns_200(client: AsyncClient) -> None:
    """stock_peers with required symbol param returns 200."""
    with patch(f"{_ENGINE_MOD}.execute_template", new=AsyncMock(return_value=_CANNED_RESPONSE)):
        resp = await client.post(
            "/api/v1/query/template",
            json={"template": "stock_peers", "params": {"symbol": "RELIANCE"}},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stock_peers_returns_data_array(client: AsyncClient) -> None:
    """stock_peers response contains records array."""
    with patch(f"{_ENGINE_MOD}.execute_template", new=AsyncMock(return_value=_CANNED_RESPONSE)):
        resp = await client.post(
            "/api/v1/query/template",
            json={"template": "stock_peers", "params": {"symbol": "TCS", "limit": 5}},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "records" in body


@pytest.mark.asyncio
async def test_stock_peers_missing_symbol_returns_400(client: AsyncClient) -> None:
    """stock_peers with missing required symbol returns 400."""
    resp = await client.post(
        "/api/v1/query/template",
        json={"template": "stock_peers", "params": {}},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stock_peers_missing_symbol_error_code(client: AsyncClient) -> None:
    """stock_peers missing symbol error body has TEMPLATE_PARAM_MISSING code."""
    resp = await client.post(
        "/api/v1/query/template",
        json={"template": "stock_peers", "params": {}},
    )
    body = resp.json()
    assert body.get("error", {}).get("code") == "TEMPLATE_PARAM_MISSING"


# ---------------------------------------------------------------------------
# mf_rank_composite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mf_rank_composite_valid_params_returns_200(client: AsyncClient) -> None:
    """mf_rank_composite with category param returns 200."""
    with patch(f"{_ENGINE_MOD}.execute_template", new=AsyncMock(return_value=_CANNED_RESPONSE)):
        resp = await client.post(
            "/api/v1/query/template",
            json={
                "template": "mf_rank_composite",
                "params": {"category": "Large Cap", "period": "1y"},
            },
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_mf_rank_composite_no_params_returns_200(client: AsyncClient) -> None:
    """mf_rank_composite with no params uses defaults (all optional)."""
    with patch(f"{_ENGINE_MOD}.execute_template", new=AsyncMock(return_value=_CANNED_RESPONSE)):
        resp = await client.post(
            "/api/v1/query/template",
            json={"template": "mf_rank_composite", "params": {}},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_mf_rank_composite_has_records(client: AsyncClient) -> None:
    """mf_rank_composite response contains records."""
    with patch(f"{_ENGINE_MOD}.execute_template", new=AsyncMock(return_value=_CANNED_RESPONSE)):
        resp = await client.post(
            "/api/v1/query/template",
            json={"template": "mf_rank_composite", "params": {"limit": 10}},
        )
    body = resp.json()
    assert "records" in body


# ---------------------------------------------------------------------------
# sector_breadth_template
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sector_breadth_template_valid_params_returns_200(client: AsyncClient) -> None:
    """sector_breadth_template with default params returns 200."""
    with patch(f"{_ENGINE_MOD}.execute_template", new=AsyncMock(return_value=_CANNED_RESPONSE)):
        resp = await client.post(
            "/api/v1/query/template",
            json={"template": "sector_breadth_template", "params": {}},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_sector_breadth_template_with_universe_param(client: AsyncClient) -> None:
    """sector_breadth_template accepts universe param."""
    with patch(f"{_ENGINE_MOD}.execute_template", new=AsyncMock(return_value=_CANNED_RESPONSE)):
        resp = await client.post(
            "/api/v1/query/template",
            json={"template": "sector_breadth_template", "params": {"universe": "nifty500"}},
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Unknown template -> 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_template_returns_404(client: AsyncClient) -> None:
    """Unknown template name returns 404."""
    resp = await client.post(
        "/api/v1/query/template",
        json={"template": "does_not_exist", "params": {}},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unknown_template_error_code(client: AsyncClient) -> None:
    """Unknown template error body has TEMPLATE_NOT_FOUND code."""
    resp = await client.post(
        "/api/v1/query/template",
        json={"template": "not_a_real_template", "params": {}},
    )
    body = resp.json()
    assert body.get("error", {}).get("code") == "TEMPLATE_NOT_FOUND"
