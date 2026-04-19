"""Tests for GET /api/v1/global/events (V2FE-1b).

Uses ASGITransport + AsyncClient so no live backend required.
Mocks EventMarkerService to isolate from DB.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app

_SVC_MOD = "backend.routes.global_intel.EventMarkerService"


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


def _empty_events_response() -> dict[str, Any]:
    return {
        "data_as_of": "2026-04-19",
        "source": "ATLAS key events",
        "events": [],
        "_meta": {"data_as_of": "2026-04-19", "record_count": 0, "query_ms": 2},
    }


def _sample_events_response() -> dict[str, Any]:
    return {
        "data_as_of": "2026-04-19",
        "source": "ATLAS key events",
        "events": [
            {
                "date": "2024-01-01",
                "category": "rbi_policy",
                "severity": "high",
                "affects": ["india"],
                "label": "RBI Rate Cut",
                "source": None,
                "description": None,
                "display_color": None,
                "source_url": None,
            }
        ],
        "_meta": {"data_as_of": "2026-04-19", "record_count": 1, "query_ms": 5},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_global_events_returns_200(client: AsyncClient) -> None:
    """GET /api/v1/global/events returns 200."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_events = AsyncMock(return_value=_empty_events_response())
        resp = await client.get("/api/v1/global/events")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_global_events_empty_atlas_returns_empty_array(client: AsyncClient) -> None:
    """Empty atlas_key_events → events: [] not an error."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_events = AsyncMock(return_value=_empty_events_response())
        resp = await client.get("/api/v1/global/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] == []


@pytest.mark.asyncio
async def test_global_events_has_meta_key(client: AsyncClient) -> None:
    """Response always contains _meta envelope."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_events = AsyncMock(return_value=_empty_events_response())
        resp = await client.get("/api/v1/global/events")
    body = resp.json()
    assert "_meta" in body


@pytest.mark.asyncio
async def test_global_events_meta_has_data_as_of(client: AsyncClient) -> None:
    """_meta contains data_as_of field."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_events = AsyncMock(return_value=_empty_events_response())
        resp = await client.get("/api/v1/global/events")
    body = resp.json()
    assert "data_as_of" in body["_meta"]


@pytest.mark.asyncio
async def test_global_events_with_data(client: AsyncClient) -> None:
    """When events exist, they are returned in the events array."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_events = AsyncMock(return_value=_sample_events_response())
        resp = await client.get("/api/v1/global/events")
    body = resp.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["label"] == "RBI Rate Cut"
    assert body["_meta"]["record_count"] == 1


@pytest.mark.asyncio
async def test_global_events_scope_param_accepted(client: AsyncClient) -> None:
    """scope query param is forwarded to EventMarkerService."""
    with patch(_SVC_MOD) as MockSvc:
        instance = MockSvc.return_value
        instance.get_events = AsyncMock(return_value=_empty_events_response())
        resp = await client.get("/api/v1/global/events?scope=india")
    assert resp.status_code == 200
    call_kwargs = instance.get_events.call_args
    assert call_kwargs is not None
    assert "india" in str(call_kwargs)


@pytest.mark.asyncio
async def test_global_events_categories_param_accepted(client: AsyncClient) -> None:
    """categories query param is accepted and forwarded."""
    with patch(_SVC_MOD) as MockSvc:
        instance = MockSvc.return_value
        instance.get_events = AsyncMock(return_value=_empty_events_response())
        resp = await client.get("/api/v1/global/events?categories=rbi_policy,budget")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_global_events_source_field_present(client: AsyncClient) -> None:
    """Response contains source field (provenance)."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_events = AsyncMock(return_value=_empty_events_response())
        resp = await client.get("/api/v1/global/events")
    body = resp.json()
    assert "source" in body


@pytest.mark.asyncio
async def test_global_events_data_as_of_in_response(client: AsyncClient) -> None:
    """Top-level data_as_of field is present in response."""
    with patch(_SVC_MOD) as MockSvc:
        MockSvc.return_value.get_events = AsyncMock(return_value=_empty_events_response())
        resp = await client.get("/api/v1/global/events")
    body = resp.json()
    assert "data_as_of" in body
