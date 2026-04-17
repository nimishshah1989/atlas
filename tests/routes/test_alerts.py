"""Unit tests for Alerts API routes (V6-7).

Uses ASGITransport + AsyncClient against the real FastAPI app.
DB session is overridden via dependency_overrides[get_db].
No real DB connections — all data is in-memory mocks.

Placed in tests/routes/ (not tests/api/) to avoid the conftest integration
marker trap that would exclude these from the forge-ship gate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.models import AtlasAlert
from backend.db.session import get_db
from backend.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC)


def _make_alert_mock(
    *,
    alert_id: int = 1,
    source: str = "budget",
    symbol: str | None = "RELIANCE",
    alert_type: str | None = "budget_exceeded",
    message: str | None = "Daily budget exceeded",
    is_read: bool = False,
    is_deleted: bool = False,
    rs_at_alert: Decimal | None = None,
    quadrant_at_alert: str | None = None,
) -> MagicMock:
    """Create a MagicMock mimicking AtlasAlert without triggering ORM __new__."""
    alert = MagicMock(spec=AtlasAlert)
    alert.id = alert_id
    alert.source = source
    alert.symbol = symbol
    alert.instrument_id = None
    alert.alert_type = alert_type
    alert.message = message
    alert.metadata_json = None
    alert.rs_at_alert = rs_at_alert
    alert.quadrant_at_alert = quadrant_at_alert
    alert.is_read = is_read
    alert.is_deleted = is_deleted
    alert.deleted_at = None
    alert.created_at = _NOW
    alert.updated_at = _NOW
    return alert


def _mock_session(
    scalar_result: object = None,
    scalars_result: list[object] | None = None,
) -> AsyncMock:
    """Build a mocked AsyncSession."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_result
    scalars_chain = MagicMock()
    scalars_chain.all.return_value = scalars_result or []
    mock_result.scalars.return_value = scalars_chain

    session.execute = AsyncMock(return_value=mock_result)
    return session


def _client_with_session(session: AsyncMock) -> AsyncClient:
    app.dependency_overrides[get_db] = lambda: session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. GET /api/alerts — returns 200 with data + _meta envelope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alerts_returns_envelope() -> None:
    """GET /api/alerts returns 200 with data list and _meta."""
    alert1 = _make_alert_mock(alert_id=1, source="budget", is_read=False)
    alert2 = _make_alert_mock(alert_id=2, source="tv", is_read=True)
    session = _mock_session(scalars_result=[alert1, alert2])

    try:
        async with _client_with_session(session) as client:
            resp = await client.get("/api/alerts")

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "_meta" in body
        assert len(body["data"]) == 2
        assert body["_meta"]["returned"] == 2
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 2. GET /api/alerts?unread=true — filters to only unread rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alerts_unread_filter() -> None:
    """GET /api/alerts?unread=true returns only unread rows."""
    unread_alert = _make_alert_mock(alert_id=1, is_read=False)
    session = _mock_session(scalars_result=[unread_alert])

    try:
        async with _client_with_session(session) as client:
            resp = await client.get("/api/alerts?unread=true")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["is_read"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 3. GET /api/alerts?source=tv — returns only tv-source rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alerts_source_filter() -> None:
    """GET /api/alerts?source=tv returns only rows with source=tv."""
    tv_alert = _make_alert_mock(alert_id=5, source="tv")
    session = _mock_session(scalars_result=[tv_alert])

    try:
        async with _client_with_session(session) as client:
            resp = await client.get("/api/alerts?source=tv")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["source"] == "tv"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 4. POST /api/alerts/1/read — returns 200 with is_read=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_alert_read_returns_200() -> None:
    """POST /api/alerts/1/read → 200 with is_read=True."""
    alert = _make_alert_mock(alert_id=1, is_read=False)
    session = _mock_session(scalar_result=alert)

    try:
        async with _client_with_session(session) as client:
            resp = await client.post("/api/alerts/1/read")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["is_read"] is True
        assert "message" in body
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 5. POST /api/alerts/999999/read — returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_alert_read_not_found_returns_404() -> None:
    """POST /api/alerts/999999/read → 404."""
    session = _mock_session(scalar_result=None)

    try:
        async with _client_with_session(session) as client:
            resp = await client.post("/api/alerts/999999/read")

        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 6. GET /api/alerts/rules — returns 501
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alert_rules_returns_501() -> None:
    """GET /api/alerts/rules → 501 (not yet implemented stub)."""
    session = _mock_session()

    try:
        async with _client_with_session(session) as client:
            resp = await client.get("/api/alerts/rules")

        assert resp.status_code == 501
    finally:
        app.dependency_overrides.pop(get_db, None)
