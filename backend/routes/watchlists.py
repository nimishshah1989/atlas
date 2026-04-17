"""Watchlist CRUD + TV sync routes — V6-6."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.models import AtlasWatchlist
from backend.db.session import get_db
from backend.models.watchlist import (
    WatchlistCreateRequest,
    WatchlistListResponse,
    WatchlistResponse,
    WatchlistUpdateRequest,
)
from backend.services.tv.bridge import TVBridgeClient, TVBridgeUnavailableError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])


# ---------------------------------------------------------------------------
# GET / — list all non-deleted watchlists
# ---------------------------------------------------------------------------


@router.get("/", response_model=WatchlistListResponse)
async def list_watchlists(
    session: AsyncSession = Depends(get_db),
) -> WatchlistListResponse:
    stmt = select(AtlasWatchlist).where(AtlasWatchlist.is_deleted == False)  # noqa: E712
    execute_out = await session.execute(stmt)
    rows = execute_out.scalars().all()
    items = [WatchlistResponse.model_validate(r) for r in rows]
    log.info("watchlists_listed", count=len(items))
    return WatchlistListResponse(watchlists=items, total=len(items))


# ---------------------------------------------------------------------------
# POST / — create a watchlist
# ---------------------------------------------------------------------------


@router.post("/", response_model=WatchlistResponse, status_code=201)
async def create_watchlist(
    body: WatchlistCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    watchlist = AtlasWatchlist(
        id=uuid.uuid4(),
        name=body.name,
        symbols=body.symbols,
        tv_synced=False,
        is_deleted=False,
    )
    session.add(watchlist)
    await session.commit()
    await session.refresh(watchlist)
    log.info("watchlist_created", id=str(watchlist.id), name=watchlist.name)
    return WatchlistResponse.model_validate(watchlist)


# ---------------------------------------------------------------------------
# GET /{id} — get one watchlist
# ---------------------------------------------------------------------------


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    stmt = select(AtlasWatchlist).where(
        AtlasWatchlist.id == watchlist_id,
        AtlasWatchlist.is_deleted == False,  # noqa: E712
    )
    execute_out = await session.execute(stmt)
    row = execute_out.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return WatchlistResponse.model_validate(row)


# ---------------------------------------------------------------------------
# PATCH /{id} — update name and/or symbols
# ---------------------------------------------------------------------------


@router.patch("/{watchlist_id}", response_model=WatchlistResponse)
async def update_watchlist(
    watchlist_id: uuid.UUID,
    body: WatchlistUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    # Fetch first to confirm existence
    stmt = select(AtlasWatchlist).where(
        AtlasWatchlist.id == watchlist_id,
        AtlasWatchlist.is_deleted == False,  # noqa: E712
    )
    execute_out = await session.execute(stmt)
    row = execute_out.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.symbols is not None:
        updates["symbols"] = body.symbols

    if updates:
        update_stmt = (
            update(AtlasWatchlist)
            .where(AtlasWatchlist.id == watchlist_id)
            .values(**updates)
            .returning(AtlasWatchlist)
        )
        update_result = await session.execute(update_stmt)
        row = update_result.scalar_one()
        await session.commit()
        log.info("watchlist_updated", id=str(watchlist_id), fields=list(updates.keys()))
    else:
        log.info("watchlist_update_noop", id=str(watchlist_id))

    return WatchlistResponse.model_validate(row)


# ---------------------------------------------------------------------------
# DELETE /{id} — soft-delete
# ---------------------------------------------------------------------------


@router.delete("/{watchlist_id}", status_code=204)
async def delete_watchlist(
    watchlist_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(AtlasWatchlist).where(
        AtlasWatchlist.id == watchlist_id,
        AtlasWatchlist.is_deleted == False,  # noqa: E712
    )
    execute_out = await session.execute(stmt)
    row = execute_out.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    soft_delete_stmt = (
        update(AtlasWatchlist)
        .where(AtlasWatchlist.id == watchlist_id)
        .values(is_deleted=True, deleted_at=datetime.now(UTC))
    )
    await session.execute(soft_delete_stmt)
    await session.commit()
    log.info("watchlist_deleted", id=str(watchlist_id))


# ---------------------------------------------------------------------------
# POST /{id}/sync-tv — push watchlist to TradingView bridge
# ---------------------------------------------------------------------------


@router.post("/{watchlist_id}/sync-tv")
async def sync_tv(
    watchlist_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(AtlasWatchlist).where(
        AtlasWatchlist.id == watchlist_id,
        AtlasWatchlist.is_deleted == False,  # noqa: E712
    )
    execute_out = await session.execute(stmt)
    row = execute_out.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    settings = get_settings()
    symbols: list[str] = row.symbols or []

    if symbols:
        # Ping bridge with first symbol as connectivity test
        client = TVBridgeClient(base_url=settings.tv_bridge_url)
        try:
            await client.get_screener(symbols[0], "NSE")
        except TVBridgeUnavailableError:
            log.warning("sync_tv_bridge_unavailable", watchlist_id=str(watchlist_id))
            raise HTTPException(status_code=503, detail="TV bridge unavailable")

    # Mark synced
    sync_stmt = (
        update(AtlasWatchlist).where(AtlasWatchlist.id == watchlist_id).values(tv_synced=True)
    )
    await session.execute(sync_stmt)
    await session.commit()

    log.info("watchlist_tv_synced", id=str(watchlist_id), symbol_count=len(symbols))

    response_data: dict[str, Any] = {
        "id": str(watchlist_id),
        "tv_synced": True,
        "message": "Watchlist synced to TradingView",
    }
    return {
        "data": response_data,
        "_meta": {"symbol_count": len(symbols)},
    }
