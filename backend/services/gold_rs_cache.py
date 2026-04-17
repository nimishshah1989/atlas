"""GoldRSCache — V7-0: Redis read-through cache for Gold RS data.

Architecture:
  1. get_cached()  — check Redis first (15-min TTL)
  2. set_cached()  — write to Redis after compute
  3. upsert_db()   — persist to atlas_gold_rs_cache via INSERT ... ON CONFLICT DO UPDATE

Redis errors are swallowed (best-effort) — DB is the source of truth.
All Decimal values are serialized via str() → JSON → parsed back via Decimal(str()).

Cache key format:
  gold_rs:{entity_type}:{entity_id}:{date.isoformat()}
  e.g. gold_rs:equity:RELIANCE:2026-04-17
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from redis.asyncio import Redis

log = structlog.get_logger()

CACHE_TTL = 900  # 15 minutes in seconds


class GoldRSCache:
    """Redis read-through cache for Gold RS computation results.

    Args:
        redis_client: An async Redis client (redis.asyncio.Redis).
                      Must support: get(), setex() coroutines.
                      Tests may pass a mock.

    All Redis errors are caught and swallowed — the system degrades
    gracefully to DB-only mode on Redis failure.
    """

    def __init__(self, redis_client: "Redis") -> None:
        self._redis = redis_client

    def _cache_key(self, entity_type: str, entity_id: str, dt: date) -> str:
        """Build the Redis cache key for a (entity_type, entity_id, date) triple."""
        return f"gold_rs:{entity_type}:{entity_id}:{dt.isoformat()}"

    async def get_cached(
        self, entity_type: str, entity_id: str, dt: date
    ) -> Optional[dict[str, object]]:
        """Check Redis for a cached Gold RS entry.

        Returns:
            Parsed dict on cache hit, or None on miss / error.
            The returned dict mirrors GoldRSCacheEntry fields.
        """
        key = self._cache_key(entity_type, entity_id, dt)
        try:
            raw = await self._redis.get(key)
            if raw is not None:
                log.debug("gold_rs_cache_hit", key=key)
                parsed: dict[str, object] = json.loads(raw)
                return parsed
            log.debug("gold_rs_cache_miss", key=key)
        except Exception as exc:
            log.warning(
                "gold_rs_cache_redis_error",
                entity_type=entity_type,
                entity_id=entity_id,
                error=str(exc),
            )
        return None

    async def set_cached(
        self, entity_type: str, entity_id: str, dt: date, data: dict[str, object]
    ) -> None:
        """Write a Gold RS result to Redis with TTL.

        Args:
            data: Dict to serialize. Decimal values are handled by str() default.

        Redis errors are swallowed — DB is the authoritative source.
        """
        key = self._cache_key(entity_type, entity_id, dt)
        try:
            payload = json.dumps(data, default=str)
            await self._redis.setex(key, CACHE_TTL, payload)
            log.debug("gold_rs_cache_set", key=key, ttl=CACHE_TTL)
        except Exception as exc:
            log.warning(
                "gold_rs_cache_set_error",
                entity_type=entity_type,
                entity_id=entity_id,
                error=str(exc),
            )

    async def upsert_db(
        self,
        session: AsyncSession,
        entity_type: str,
        entity_id: str,
        dt: date,
        rs_1m: Optional[Decimal],
        rs_3m: Optional[Decimal],
        rs_6m: Optional[Decimal],
        rs_12m: Optional[Decimal],
        signal: str,
        gold_series: str,
    ) -> None:
        """Persist Gold RS result to atlas_gold_rs_cache via upsert.

        Uses INSERT ... ON CONFLICT ON CONSTRAINT uq_gold_rs_cache DO UPDATE.
        Converts Decimal → str for parameter binding (asyncpg-safe).
        Commits the session after execution.

        Args:
            session:    Async SQLAlchemy session.
            entity_type: e.g. "equity", "sector", "etf"
            entity_id:   e.g. "RELIANCE", "NIFTY_IT"
            dt:          Date of computation.
            rs_1m..rs_12m: RS values in pct pts, or None if insufficient data.
            signal:      One of AMPLIFIES_BULL | AMPLIFIES_BEAR | NEUTRAL_BENCH_ONLY
                         | FRAGILE | STALE
            gold_series: "GLD" or "GOLDBEES"
        """
        await session.execute(
            text(
                """
                INSERT INTO atlas_gold_rs_cache
                  (entity_type, entity_id, date,
                   rs_vs_gold_1m, rs_vs_gold_3m, rs_vs_gold_6m, rs_vs_gold_12m,
                   gold_rs_signal, gold_series, computed_at, updated_at)
                VALUES
                  (:entity_type, :entity_id, :date,
                   :rs_1m, :rs_3m, :rs_6m, :rs_12m,
                   :signal, :gold_series, NOW(), NOW())
                ON CONFLICT ON CONSTRAINT uq_gold_rs_cache
                DO UPDATE SET
                  rs_vs_gold_1m  = EXCLUDED.rs_vs_gold_1m,
                  rs_vs_gold_3m  = EXCLUDED.rs_vs_gold_3m,
                  rs_vs_gold_6m  = EXCLUDED.rs_vs_gold_6m,
                  rs_vs_gold_12m = EXCLUDED.rs_vs_gold_12m,
                  gold_rs_signal = EXCLUDED.gold_rs_signal,
                  gold_series    = EXCLUDED.gold_series,
                  computed_at    = NOW(),
                  updated_at     = NOW()
                """
            ),
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "date": dt,
                "rs_1m": str(rs_1m) if rs_1m is not None else None,
                "rs_3m": str(rs_3m) if rs_3m is not None else None,
                "rs_6m": str(rs_6m) if rs_6m is not None else None,
                "rs_12m": str(rs_12m) if rs_12m is not None else None,
                "signal": signal,
                "gold_series": gold_series,
            },
        )
        await session.commit()
        log.info(
            "gold_rs_db_upserted",
            entity_type=entity_type,
            entity_id=entity_id,
            date=str(dt),
            signal=signal,
        )

    async def invalidate(self, entity_type: str, entity_id: str, dt: date) -> None:
        """Remove a cached Gold RS entry from Redis (e.g. on forced recompute).

        Redis errors are swallowed.
        """
        key = self._cache_key(entity_type, entity_id, dt)
        try:
            await self._redis.delete(key)
            log.debug("gold_rs_cache_invalidated", key=key)
        except Exception as exc:
            log.warning("gold_rs_cache_invalidate_error", key=key, error=str(exc))
