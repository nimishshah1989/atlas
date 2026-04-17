"""TV cache service — read-through cache for TradingView MCP bridge data.

Cache key: (symbol, data_type, interval)
TTL: configured via settings.tv_cache_ttl_seconds (default 900s / 15 min)

Staleness policy:
- Fresh (age <= TTL): return immediately, no bridge call
- Stale (age > TTL): return cached entry with is_stale=True, spawn background refresh
- Missing: call bridge, upsert, return with is_stale=False
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.tv_models import AtlasTvCache
from backend.models.tv import TvCacheEntry
from backend.services.tv.bridge import TVBridgeClient, TVBridgeUnavailableError

log = structlog.get_logger(__name__)


def _orm_to_entry(row: AtlasTvCache, is_stale: bool = False) -> TvCacheEntry:
    """Convert an ORM row to a TvCacheEntry Pydantic model."""
    return TvCacheEntry(
        symbol=row.symbol,
        exchange=row.exchange,
        data_type=row.data_type,
        interval=row.interval,
        tv_data=row.tv_data,
        fetched_at=row.fetched_at,
        is_stale=is_stale,
    )


def _is_stale(fetched_at: datetime) -> bool:
    """Return True if the cache entry is older than the configured TTL."""
    settings = get_settings()
    ttl = timedelta(seconds=settings.tv_cache_ttl_seconds)
    age = datetime.now(tz=UTC) - fetched_at
    return age > ttl


async def _call_bridge(
    bridge: TVBridgeClient,
    symbol: str,
    exchange: str,
    data_type: str,
    interval: str,
) -> dict[str, Any]:
    """Dispatch to the correct bridge method based on data_type.

    Args:
        bridge: TVBridgeClient instance.
        symbol: Ticker symbol.
        exchange: Exchange code.
        data_type: One of 'ta_summary', 'screener', 'fundamentals'.
        interval: Chart interval (used only for ta_summary).

    Returns:
        Dict of TV data from the bridge.

    Raises:
        TVBridgeUnavailableError: If the bridge sidecar is unreachable.
        ValueError: If data_type is unrecognised.
    """
    if data_type == "ta_summary":
        return await bridge.get_ta_summary(symbol, exchange, interval)
    if data_type == "screener":
        return await bridge.get_screener(symbol, exchange)
    if data_type == "fundamentals":
        return await bridge.get_fundamentals(symbol, exchange)
    raise ValueError(f"Unknown data_type: {data_type!r}")


class TVCacheService:
    """Read-through cache service for TradingView bridge data.

    All methods are pure async and accept an explicit AsyncSession — the
    caller owns transaction boundaries.
    """

    async def get_or_fetch(
        self,
        session: AsyncSession,
        symbol: str,
        exchange: str,
        data_type: str,
        interval: str,
        bridge: TVBridgeClient,
    ) -> TvCacheEntry:
        """Return a cached TV entry, fetching from the bridge if needed.

        - Cache hit, fresh  → return entry, is_stale=False (no bridge call)
        - Cache hit, stale  → spawn background refresh, return entry with is_stale=True
        - Cache miss        → call bridge, upsert, return is_stale=False

        Args:
            session: Async SQLAlchemy session (caller-owned).
            symbol: Ticker symbol.
            exchange: Exchange code.
            data_type: One of 'ta_summary', 'screener', 'fundamentals'.
            interval: Chart interval.
            bridge: TVBridgeClient to use on cache miss.

        Returns:
            TvCacheEntry with is_stale flag set appropriately.
        """
        stmt = select(AtlasTvCache).where(
            AtlasTvCache.symbol == symbol,
            AtlasTvCache.data_type == data_type,
            AtlasTvCache.interval == interval,
        )
        query_result = await session.execute(stmt)
        row = query_result.scalar_one_or_none()

        if row is not None:
            stale = _is_stale(row.fetched_at)
            if stale:
                log.info(
                    "tv_cache_stale",
                    symbol=symbol,
                    data_type=data_type,
                    interval=interval,
                    fetched_at=row.fetched_at.isoformat(),
                )
                settings = get_settings()
                asyncio.create_task(
                    _background_refresh(
                        db_url=settings.database_url,
                        symbol=symbol,
                        exchange=exchange,
                        data_type=data_type,
                        interval=interval,
                        bridge_base_url=settings.tv_bridge_url,
                    )
                )
                return _orm_to_entry(row, is_stale=True)

            log.debug(
                "tv_cache_hit",
                symbol=symbol,
                data_type=data_type,
                interval=interval,
            )
            return _orm_to_entry(row, is_stale=False)

        # Cache miss — call bridge and upsert
        log.info(
            "tv_cache_miss",
            symbol=symbol,
            data_type=data_type,
            interval=interval,
        )
        tv_data = await _call_bridge(bridge, symbol, exchange, data_type, interval)
        return await self.upsert(session, symbol, exchange, data_type, interval, tv_data)

    async def upsert(
        self,
        session: AsyncSession,
        symbol: str,
        exchange: str,
        data_type: str,
        interval: str,
        tv_data: dict[str, Any],
    ) -> TvCacheEntry:
        """Insert or update a cache entry.

        Uses PostgreSQL INSERT ... ON CONFLICT (symbol, data_type, interval)
        DO UPDATE SET tv_data=..., fetched_at=now().

        Args:
            session: Async SQLAlchemy session (caller-owned).
            symbol: Ticker symbol.
            exchange: Exchange code.
            data_type: Data type key.
            interval: Chart interval.
            tv_data: The TradingView data blob to store.

        Returns:
            TvCacheEntry reflecting the stored state.
        """
        now = datetime.now(tz=UTC)
        stmt = (
            pg_insert(AtlasTvCache)
            .values(
                symbol=symbol,
                exchange=exchange,
                data_type=data_type,
                interval=interval,
                tv_data=tv_data,
                fetched_at=now,
            )
            .on_conflict_do_update(
                index_elements=["symbol", "data_type", "interval"],
                set_={
                    "tv_data": tv_data,
                    "exchange": exchange,
                    "fetched_at": now,
                },
            )
        )
        await session.execute(stmt)
        await session.commit()

        log.info(
            "tv_cache_upserted",
            symbol=symbol,
            data_type=data_type,
            interval=interval,
        )
        return TvCacheEntry(
            symbol=symbol,
            exchange=exchange,
            data_type=data_type,
            interval=interval,
            tv_data=tv_data,
            fetched_at=now,
            is_stale=False,
        )


async def _background_refresh(
    db_url: str,
    symbol: str,
    exchange: str,
    data_type: str,
    interval: str,
    bridge_base_url: str,
) -> None:
    """Background task: refresh a stale cache entry with a fresh bridge call.

    Opens its own async session (cannot reuse the caller's session — asyncpg
    cannot multiplex). Swallows TVBridgeUnavailableError so a bridge outage
    never poisons the response path.

    Args:
        db_url: Async database URL for opening a new session.
        symbol: Ticker symbol.
        exchange: Exchange code.
        data_type: Data type key.
        interval: Chart interval.
        bridge_base_url: Base URL for TVBridgeClient.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    log.info(
        "tv_cache_background_refresh_start",
        symbol=symbol,
        data_type=data_type,
        interval=interval,
    )
    try:
        bridge = TVBridgeClient(base_url=bridge_base_url)
        tv_data = await _call_bridge(bridge, symbol, exchange, data_type, interval)

        engine = create_async_engine(db_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            svc = TVCacheService()
            await svc.upsert(session, symbol, exchange, data_type, interval, tv_data)
        await engine.dispose()

        log.info(
            "tv_cache_background_refresh_done",
            symbol=symbol,
            data_type=data_type,
            interval=interval,
        )
    except TVBridgeUnavailableError as exc:
        log.warning(
            "tv_cache_background_refresh_bridge_unavailable",
            symbol=symbol,
            data_type=data_type,
            interval=interval,
            error=str(exc),
        )
    except Exception as exc:
        log.warning(
            "tv_cache_background_refresh_failed",
            symbol=symbol,
            data_type=data_type,
            interval=interval,
            error=str(exc),
        )
