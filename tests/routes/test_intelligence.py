"""Tests for backend/routes/intelligence.py.

Unit tests use AsyncClient with mocked service layer.
Integration tests require real DB.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

IST = timezone.utc


def _make_data_as_of() -> datetime:
    return datetime(2026, 4, 13, 10, 0, 0, tzinfo=IST)


def _mock_finding_row(
    finding_id: uuid.UUID | None = None,
    entity: str = "AAPL",
    confidence: Decimal = Decimal("0.8"),
    content: str = "Test content",
) -> MagicMock:
    """Create a mock AtlasIntelligence ORM row."""
    row = MagicMock()
    row.id = finding_id or uuid.uuid4()
    row.agent_id = "test-agent"
    row.agent_type = "technical"
    row.entity = entity
    row.entity_type = "equity"
    row.finding_type = "technical"
    row.title = "Test Finding"
    row.content = content
    row.confidence = confidence
    row.evidence = {}
    row.tags = ["test"]
    row.data_as_of = _make_data_as_of()
    row.expires_at = None
    row.is_validated = False
    row.created_at = _make_data_as_of()
    row.updated_at = _make_data_as_of()
    return row


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    from backend.main import app as _app

    return _app


# ---------------------------------------------------------------------------
# Route tests: POST /api/v1/intelligence/findings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_finding_returns_201(app: Any) -> None:
    """POST /findings with valid payload returns 201."""
    mock_row = _mock_finding_row()

    with (
        patch("backend.routes.intelligence.store_finding", new=AsyncMock(return_value=mock_row)),
        patch("backend.routes.intelligence.get_db"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/intelligence/findings",
                json={
                    "agent_id": "test-agent",
                    "agent_type": "technical",
                    "entity": "AAPL",
                    "entity_type": "equity",
                    "finding_type": "technical",
                    "title": "Test Finding",
                    "content": "Test content",
                    "confidence": "0.8",
                    "data_as_of": "2026-04-13T10:00:00+00:00",
                },
            )

    assert resp.status_code == 201
    body = resp.json()
    assert body["agent_id"] == "test-agent"
    assert body["entity"] == "AAPL"


@pytest.mark.asyncio
async def test_create_finding_response_confidence_is_decimal_serializable(app: Any) -> None:
    """Confidence in response should be a number (Decimal serialized to float/str by JSON)."""
    mock_row = _mock_finding_row(confidence=Decimal("0.75"))

    with (
        patch("backend.routes.intelligence.store_finding", new=AsyncMock(return_value=mock_row)),
        patch("backend.routes.intelligence.get_db"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/intelligence/findings",
                json={
                    "agent_id": "agent",
                    "agent_type": "tech",
                    "entity": "AAPL",
                    "entity_type": "equity",
                    "finding_type": "tech",
                    "title": "T",
                    "content": "C",
                    "confidence": "0.75",
                    "data_as_of": "2026-04-13T10:00:00+00:00",
                },
            )

    assert resp.status_code == 201
    body = resp.json()
    # JSON serializes Decimal as a number — verify it's a number type in JSON
    assert body["confidence"] is not None
    # The value should represent 0.75
    assert abs(float(body["confidence"]) - 0.75) < 0.001


@pytest.mark.asyncio
async def test_create_finding_service_value_error_returns_422(app: Any) -> None:
    """When service raises ValueError, route returns 422."""
    with (
        patch(
            "backend.routes.intelligence.store_finding",
            new=AsyncMock(side_effect=ValueError("data_as_of must be timezone-aware")),
        ),
        patch("backend.routes.intelligence.get_db"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/intelligence/findings",
                json={
                    "agent_id": "agent",
                    "agent_type": "tech",
                    "entity": "AAPL",
                    "entity_type": "equity",
                    "finding_type": "tech",
                    "title": "T",
                    "content": "C",
                    "confidence": "0.8",
                    "data_as_of": "2026-04-13T10:00:00+00:00",
                },
            )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Route tests: GET /api/v1/intelligence/search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_200_with_findings(app: Any) -> None:
    """GET /search with query param returns 200 and findings list."""
    mock_rows = [_mock_finding_row(entity="AAPL"), _mock_finding_row(entity="MSFT")]

    with (
        patch(
            "backend.routes.intelligence.get_relevant_intelligence",
            new=AsyncMock(return_value=mock_rows),
        ),
        patch("backend.routes.intelligence.get_db"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/intelligence/search",
                params={"q": "bullish technical setup"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["findings"]) == 2
    assert body["meta"]["record_count"] == 2


@pytest.mark.asyncio
async def test_search_missing_query_param_returns_422(app: Any) -> None:
    """GET /search without 'q' param returns 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/intelligence/search")

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Route tests: GET /api/v1/intelligence/findings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_findings_returns_200(app: Any) -> None:
    """GET /findings returns 200 with list."""
    mock_rows = [_mock_finding_row()]

    with (
        patch(
            "backend.routes.intelligence.list_findings",
            new=AsyncMock(return_value=mock_rows),
        ),
        patch("backend.routes.intelligence.get_db"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/intelligence/findings")

    assert resp.status_code == 200
    body = resp.json()
    assert "findings" in body
    assert body["meta"]["record_count"] == 1


@pytest.mark.asyncio
async def test_list_findings_with_filters(app: Any) -> None:
    """GET /findings with entity filter passes it to service."""
    mock_rows: list = []
    list_mock = AsyncMock(return_value=mock_rows)

    with (
        patch("backend.routes.intelligence.list_findings", new=list_mock),
        patch("backend.routes.intelligence.get_db"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/intelligence/findings",
                params={"entity": "AAPL", "finding_type": "technical"},
            )

    assert resp.status_code == 200
    # Verify filters were passed to service
    call_kwargs = list_mock.call_args.kwargs
    assert call_kwargs["entity"] == "AAPL"
    assert call_kwargs["finding_type"] == "technical"


# ---------------------------------------------------------------------------
# Route tests: GET /api/v1/intelligence/findings/{finding_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_finding_by_id_returns_200(app: Any) -> None:
    """GET /findings/{id} with existing id returns 200."""
    finding_id = uuid.uuid4()
    mock_row = _mock_finding_row(finding_id=finding_id)

    with (
        patch(
            "backend.routes.intelligence.get_finding_by_id",
            new=AsyncMock(return_value=mock_row),
        ),
        patch("backend.routes.intelligence.get_db"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/intelligence/findings/{finding_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(finding_id)


@pytest.mark.asyncio
async def test_get_finding_by_id_not_found_returns_404(app: Any) -> None:
    """GET /findings/{id} with non-existent id returns 404."""
    finding_id = uuid.uuid4()

    with (
        patch(
            "backend.routes.intelligence.get_finding_by_id",
            new=AsyncMock(return_value=None),
        ),
        patch("backend.routes.intelligence.get_db"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/v1/intelligence/findings/{finding_id}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_finding_invalid_uuid_returns_422(app: Any) -> None:
    """GET /findings/{id} with invalid UUID returns 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/intelligence/findings/not-a-uuid")

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Route: intelligence router is registered
# ---------------------------------------------------------------------------


def test_intelligence_router_registered_in_app() -> None:
    """Intelligence router must be registered in main.py."""
    from backend.main import app

    route_paths = [r.path for r in app.routes]  # type: ignore[attr-defined]
    intelligence_routes = [p for p in route_paths if "/intelligence" in p]
    assert len(intelligence_routes) >= 4, (
        f"Expected 4+ intelligence routes, found: {intelligence_routes}"
    )
