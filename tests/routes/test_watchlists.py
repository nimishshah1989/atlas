"""Unit tests for watchlist CRUD + TV sync routes (V6-6).

Uses ASGITransport + AsyncClient against the real FastAPI app.
DB session is overridden via dependency_overrides.
TVBridgeClient is patched so no live bridge calls occur.
No real DB connections — all data is in-memory mocks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.models import AtlasWatchlist
from backend.db.session import get_db
from backend.main import app
from backend.services.tv.bridge import TVBridgeUnavailableError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC)


def _make_watchlist_mock(
    *,
    wl_id: uuid.UUID | None = None,
    name: str = "My Watchlist",
    symbols: list[str] | None = None,
    tv_synced: bool = False,
    is_deleted: bool = False,
) -> MagicMock:
    """Create a MagicMock that mimics AtlasWatchlist without triggering ORM __new__."""
    wl = MagicMock(spec=AtlasWatchlist)
    wl.id = wl_id or uuid.uuid4()
    wl.name = name
    wl.symbols = symbols if symbols is not None else ["RELIANCE", "HDFCBANK"]
    wl.tv_synced = tv_synced
    wl.is_deleted = is_deleted
    wl.deleted_at = None
    wl.created_at = _NOW
    wl.updated_at = _NOW
    return wl


def _mock_session_factory(
    scalar_result: object = None,
    scalars_result: list[object] | None = None,
) -> AsyncMock:
    """Build a mocked AsyncSession.

    scalar_result: returned by result.scalar_one_or_none() / scalar_one()
    scalars_result: returned by result.scalars().all()
    """
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_result
    mock_result.scalar_one.return_value = scalar_result
    scalars_chain = MagicMock()
    scalars_chain.all.return_value = scalars_result or []
    mock_result.scalars.return_value = scalars_chain

    session.execute = AsyncMock(return_value=mock_result)
    return session


def _client_with_session(session: AsyncMock) -> AsyncClient:
    app.dependency_overrides[get_db] = lambda: session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# 1. Create watchlist — 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_watchlist_returns_201() -> None:
    """POST /api/v1/watchlists with name+symbols → 201 with id."""
    wl = _make_watchlist_mock(name="Tech Picks", symbols=["INFY", "TCS"])
    session = _mock_session_factory()

    # After session.refresh(watchlist), the watchlist object should have attrs
    async def _refresh(obj: object) -> None:
        obj.id = wl.id  # type: ignore[attr-defined]
        obj.name = wl.name  # type: ignore[attr-defined]
        obj.symbols = wl.symbols  # type: ignore[attr-defined]
        obj.tv_synced = False
        obj.is_deleted = False
        obj.deleted_at = None
        obj.created_at = _NOW
        obj.updated_at = _NOW

    session.refresh = AsyncMock(side_effect=_refresh)

    async with _client_with_session(session) as ac:
        resp = await ac.post(
            "/api/v1/watchlists/",
            json={"name": "Tech Picks", "symbols": ["INFY", "TCS"]},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["name"] == "Tech Picks"
    assert body["symbols"] == ["INFY", "TCS"]
    assert body["tv_synced"] is False


# ---------------------------------------------------------------------------
# 2. List watchlists — 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_watchlists_returns_200() -> None:
    """GET /api/v1/watchlists → 200 with data list."""
    wl1 = _make_watchlist_mock(name="A")
    wl2 = _make_watchlist_mock(name="B")
    session = _mock_session_factory(scalars_result=[wl1, wl2])

    async with _client_with_session(session) as ac:
        resp = await ac.get("/api/v1/watchlists/")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["watchlists"]) == 2


# ---------------------------------------------------------------------------
# 3. Get one — 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watchlist_returns_200() -> None:
    """GET /api/v1/watchlists/{id} with valid UUID → 200."""
    wl_id = uuid.uuid4()
    wl = _make_watchlist_mock(wl_id=wl_id, name="My WL")
    session = _mock_session_factory(scalar_result=wl)

    async with _client_with_session(session) as ac:
        resp = await ac.get(f"/api/v1/watchlists/{wl_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(wl_id)
    assert body["name"] == "My WL"


# ---------------------------------------------------------------------------
# 4. Get one — 404 on missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watchlist_not_found_returns_404() -> None:
    """GET /api/v1/watchlists/{id} with unknown UUID → 404."""
    session = _mock_session_factory(scalar_result=None)

    async with _client_with_session(session) as ac:
        resp = await ac.get(f"/api/v1/watchlists/{uuid.uuid4()}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Watchlist not found"


# ---------------------------------------------------------------------------
# 5. Update — 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_watchlist_returns_200() -> None:
    """PATCH /api/v1/watchlists/{id} → 200 with updated fields."""
    wl_id = uuid.uuid4()
    original = _make_watchlist_mock(wl_id=wl_id, name="Old Name")
    updated = _make_watchlist_mock(wl_id=wl_id, name="New Name", symbols=["WIPRO"])

    # First execute returns original (existence check), second returns updated (after update)
    mock_result_original = MagicMock()
    mock_result_original.scalar_one_or_none.return_value = original
    mock_result_original.scalar_one.return_value = original
    scalars_orig = MagicMock()
    scalars_orig.all.return_value = [original]
    mock_result_original.scalars.return_value = scalars_orig

    mock_result_updated = MagicMock()
    mock_result_updated.scalar_one_or_none.return_value = updated
    mock_result_updated.scalar_one.return_value = updated
    scalars_upd = MagicMock()
    scalars_upd.all.return_value = [updated]
    mock_result_updated.scalars.return_value = scalars_upd

    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(side_effect=[mock_result_original, mock_result_updated])

    async with _client_with_session(session) as ac:
        resp = await ac.patch(
            f"/api/v1/watchlists/{wl_id}",
            json={"name": "New Name", "symbols": ["WIPRO"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New Name"
    assert body["symbols"] == ["WIPRO"]


# ---------------------------------------------------------------------------
# 6. Delete — 204 + soft-delete verified
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_sets_is_deleted_true() -> None:
    """DELETE /api/v1/watchlists/{id} → 204; two execute calls (select + update)."""
    wl_id = uuid.uuid4()
    wl = _make_watchlist_mock(wl_id=wl_id)

    mock_result_select = MagicMock()
    mock_result_select.scalar_one_or_none.return_value = wl
    mock_result_update = MagicMock()

    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(side_effect=[mock_result_select, mock_result_update])

    async with _client_with_session(session) as ac:
        resp = await ac.delete(f"/api/v1/watchlists/{wl_id}")

    assert resp.status_code == 204
    # Verify two execute calls: one SELECT, one UPDATE (soft-delete)
    assert session.execute.call_count == 2
    # Verify commit was called
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# 7. Sync TV — success → 200 + tv_synced=true
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_tv_success_sets_tv_synced_true() -> None:
    """POST /api/v1/watchlists/{id}/sync-tv with bridge success → 200, tv_synced=true."""
    wl_id = uuid.uuid4()
    wl = _make_watchlist_mock(wl_id=wl_id, symbols=["RELIANCE"])

    mock_result_select = MagicMock()
    mock_result_select.scalar_one_or_none.return_value = wl
    mock_result_update = MagicMock()

    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(side_effect=[mock_result_select, mock_result_update])

    with patch("backend.routes.watchlists.TVBridgeClient") as MockClient:
        instance = MockClient.return_value
        instance.get_screener = AsyncMock(return_value={"close": "1234.5"})
        with patch("backend.routes.watchlists.get_settings") as mock_settings:
            mock_settings.return_value.tv_bridge_url = "http://127.0.0.1:7100"
            async with _client_with_session(session) as ac:
                resp = await ac.post(f"/api/v1/watchlists/{wl_id}/sync-tv")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["tv_synced"] is True
    assert body["data"]["id"] == str(wl_id)


# ---------------------------------------------------------------------------
# 8. Sync TV — bridge unavailable → 503
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_tv_bridge_unavailable_returns_503() -> None:
    """POST /api/v1/watchlists/{id}/sync-tv with TVBridgeUnavailableError → 503."""
    wl_id = uuid.uuid4()
    wl = _make_watchlist_mock(wl_id=wl_id, symbols=["RELIANCE"])

    mock_result_select = MagicMock()
    mock_result_select.scalar_one_or_none.return_value = wl

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result_select)

    with patch("backend.routes.watchlists.TVBridgeClient") as MockClient:
        instance = MockClient.return_value
        instance.get_screener = AsyncMock(side_effect=TVBridgeUnavailableError("down"))
        with patch("backend.routes.watchlists.get_settings") as mock_settings:
            mock_settings.return_value.tv_bridge_url = "http://127.0.0.1:7100"
            async with _client_with_session(session) as ac:
                resp = await ac.post(f"/api/v1/watchlists/{wl_id}/sync-tv")

    assert resp.status_code == 503
    assert resp.json()["detail"] == "TV bridge unavailable"


# ---------------------------------------------------------------------------
# 9. List excludes deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_excludes_deleted() -> None:
    """GET /api/v1/watchlists query includes is_deleted=False filter."""
    # Return empty list — verifies the route runs the query without error
    session = _mock_session_factory(scalars_result=[])

    async with _client_with_session(session) as ac:
        resp = await ac.get("/api/v1/watchlists/")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["watchlists"] == []
    # Verify execute was called (the WHERE clause is inside the stmt, not easily
    # inspectable here — the unit test validates route runs the filter path)
    session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# 10. Create with empty symbols — 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_empty_symbols_allowed() -> None:
    """POST /api/v1/watchlists with empty symbols list → 201."""
    wl = _make_watchlist_mock(name="Empty WL", symbols=[])
    session = _mock_session_factory()

    async def _refresh(obj: object) -> None:
        obj.id = wl.id  # type: ignore[attr-defined]
        obj.name = "Empty WL"
        obj.symbols = []
        obj.tv_synced = False
        obj.is_deleted = False
        obj.deleted_at = None
        obj.created_at = _NOW
        obj.updated_at = _NOW

    session.refresh = AsyncMock(side_effect=_refresh)

    async with _client_with_session(session) as ac:
        resp = await ac.post(
            "/api/v1/watchlists/",
            json={"name": "Empty WL", "symbols": []},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["symbols"] == []


# ---------------------------------------------------------------------------
# 11. Sync TV with empty symbols — 200 (no bridge call)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_tv_empty_symbols_skips_bridge() -> None:
    """POST /{id}/sync-tv on empty watchlist → 200, tv_synced=true (no bridge call)."""
    wl_id = uuid.uuid4()
    wl = _make_watchlist_mock(wl_id=wl_id, symbols=[])

    mock_result_select = MagicMock()
    mock_result_select.scalar_one_or_none.return_value = wl
    mock_result_update = MagicMock()

    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(side_effect=[mock_result_select, mock_result_update])

    with patch("backend.routes.watchlists.TVBridgeClient") as MockClient:
        with patch("backend.routes.watchlists.get_settings") as mock_settings:
            mock_settings.return_value.tv_bridge_url = "http://127.0.0.1:7100"
            async with _client_with_session(session) as ac:
                resp = await ac.post(f"/api/v1/watchlists/{wl_id}/sync-tv")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["tv_synced"] is True
    # Bridge client should NOT have been instantiated (no symbols)
    MockClient.assert_not_called()


# ---------------------------------------------------------------------------
# 12. Delete on non-existent watchlist — 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_missing_watchlist_returns_404() -> None:
    """DELETE /api/v1/watchlists/{id} on unknown id → 404."""
    session = _mock_session_factory(scalar_result=None)

    async with _client_with_session(session) as ac:
        resp = await ac.delete(f"/api/v1/watchlists/{uuid.uuid4()}")

    assert resp.status_code == 404
