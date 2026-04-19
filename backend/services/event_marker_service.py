"""EventMarkerService — V2FE-1: Read key market events from atlas_key_events.

Filters by scope (india/global/etc), date range, and category.
Redis TTL 7d, best-effort.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from redis.asyncio import Redis

log = structlog.get_logger()

_CACHE_TTL = 7 * 24 * 3600  # 7 days in seconds

_RANGE_DAYS: dict[str, Optional[int]] = {
    "1y": 365,
    "2y": 730,
    "5y": 1825,
    "10y": 3650,
    "all": None,
}


class EventMarkerService:
    """Reads market key events from atlas_key_events with scope/date/category filters."""

    def __init__(
        self,
        session: AsyncSession,
        redis_client: Optional["Redis"] = None,
    ) -> None:
        self._session = session
        self._redis = redis_client

    def _scope_hash(self, scope: str) -> str:
        return hashlib.md5(scope.encode()).hexdigest()[:8]

    def _cat_hash(self, categories: Optional[str]) -> str:
        if not categories:
            return "all"
        return hashlib.md5(categories.encode()).hexdigest()[:8]

    def _cache_key(self, scope: str, range_: str, categories: Optional[str]) -> str:
        return f"events:{self._scope_hash(scope)}:{range_}:{self._cat_hash(categories)}"

    async def _get_cached(self, key: str) -> Optional[dict[str, Any]]:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is not None:
                cached_data: dict[str, Any] = json.loads(raw)
                return cached_data
        except Exception as exc:
            log.warning("event_marker_cache_get_error", error=str(exc))
        return None

    async def _set_cached(self, key: str, data: dict[str, Any]) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(key, _CACHE_TTL, json.dumps(data, default=str))
        except Exception as exc:
            log.warning("event_marker_cache_set_error", error=str(exc))

    async def get_events(
        self,
        scope: str,
        range_: str = "5y",
        categories: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return key market events filtered by scope, range, and categories.

        Args:
            scope: Comma-separated scope values e.g. "india,global"
            range_: Date range string "1y", "5y", "all", etc.
            categories: Optional comma-separated category filter

        Returns:
            Dict with events list and data_as_of timestamp.
        """
        import datetime

        t0 = time.monotonic()

        # Check cache first
        cache_key = self._cache_key(scope, range_, categories)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            log.debug("event_marker_cache_hit", cache_key=cache_key)
            return cached

        from backend.db.models import AtlasKeyEvent

        events: list[dict[str, Any]] = []
        today_str = datetime.date.today().isoformat()

        try:
            # Parse scope into list
            scope_list = [s.strip() for s in scope.split(",") if s.strip()] if scope else []

            # Parse categories into list
            cat_list: Optional[list[str]] = None
            if categories:
                cat_list = [c.strip() for c in categories.split(",") if c.strip()]

            # Determine date cutoff
            days = _RANGE_DAYS.get(range_)

            # Build query
            stmt = select(AtlasKeyEvent)

            if days is not None:
                from sqlalchemy import text as sa_text

                cutoff_expr = sa_text(f"CURRENT_DATE - INTERVAL '{days} days'")
                stmt = stmt.where(AtlasKeyEvent.date >= cutoff_expr)

            if cat_list:
                stmt = stmt.where(AtlasKeyEvent.category.in_(cat_list))

            stmt = stmt.order_by(AtlasKeyEvent.date.desc())

            query_result = await self._session.execute(stmt)
            rows = query_result.scalars().all()

            for row in rows:
                # Filter by scope: check if any of the requested scopes appear in affects
                affects = row.affects if row.affects is not None else []
                if scope_list:
                    # Check if any scope matches affects
                    if not any(s in affects for s in scope_list):
                        continue

                events.append(
                    {
                        "date": row.date.isoformat() if row.date else None,
                        "category": row.category,
                        "severity": row.severity,
                        "affects": affects,
                        "label": row.label,
                        "source": row.source,
                        "description": row.description,
                        "display_color": row.display_color,
                        "source_url": row.source_url,
                    }
                )

        except Exception as exc:
            log.warning("event_marker_service_query_failed", error=str(exc)[:300])

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        output: dict[str, Any] = {
            "data_as_of": today_str,
            "source": "ATLAS key events",
            "events": events,
            "_meta": {
                "data_as_of": today_str,
                "record_count": len(events),
                "query_ms": elapsed_ms,
            },
        }

        log.info(
            "event_marker_service_fetched",
            scope=scope,
            range_=range_,
            event_count=len(events),
            query_ms=elapsed_ms,
        )

        # Best-effort cache write
        await self._set_cached(cache_key, output)
        return output
