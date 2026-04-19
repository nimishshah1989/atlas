"""BreadthZoneDetector — V2FE-1: Detect zone-crossing events in breadth series.

Reads de_breadth_daily time-series and emits one event per zone crossing.
Zone thresholds for nifty500: OB=400, midline=250, OS=100.
Proportionally scaled for nifty50: OB=40, midline=25, OS=10.

Redis TTL 24h, best-effort (swallows errors).
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from redis.asyncio import Redis

log = structlog.get_logger()

_CACHE_TTL = 86400  # 24h in seconds

# Universe-specific thresholds
_THRESHOLDS: dict[str, dict[str, int]] = {
    "nifty500": {"overbought": 400, "midline": 250, "oversold": 100},
    "nifty50": {"overbought": 40, "midline": 25, "oversold": 10},
}
_DEFAULT_THRESHOLDS = _THRESHOLDS["nifty500"]

# Map indicator param to column name
_INDICATOR_COLUMN: dict[str, str] = {
    "ema21": "above_ema21",
    "dma50": "above_dma50",
    "dma200": "above_dma200",
}

_RANGE_DAYS: dict[str, Optional[int]] = {
    "1y": 365,
    "5y": 1825,
    "all": None,
}


def _detect_zone(value: int, ob: int, os: int) -> str:
    if value >= ob:
        return "ob"
    if value <= os:
        return "os"
    return "neutral"


def _detect_events_for_series(
    dates: list[str],
    values: list[int],
    universe: str,
    indicator: str,
    thresholds: dict[str, int],
) -> list[dict[str, Any]]:
    """Edge-triggered zone crossing detector.

    Emits one event per zone boundary crossing.
    """
    ob = thresholds["overbought"]
    os_ = thresholds["oversold"]
    events: list[dict[str, Any]] = []

    if not dates or not values:
        return events

    prev_zone = _detect_zone(values[0], ob, os_)
    zone_start_idx = 0

    for i in range(1, len(dates)):
        count = values[i]
        curr_zone = _detect_zone(count, ob, os_)

        if curr_zone != prev_zone:
            prior_duration = i - zone_start_idx
            # Determine event_type
            event_type: Optional[str] = None
            if curr_zone == "ob":
                event_type = "entered_ob"
            elif curr_zone == "os":
                event_type = "entered_os"
            elif curr_zone == "neutral":
                if prev_zone == "ob":
                    event_type = "exited_ob"
                elif prev_zone == "os":
                    event_type = "exited_os"
                else:
                    event_type = "crossed_midline_up"

            if event_type is None:
                # Fallback for mid crossings (e.g. from ob directly to os or vice versa)
                if prev_zone == "ob" and curr_zone == "os":
                    event_type = "entered_os"
                elif prev_zone == "os" and curr_zone == "ob":
                    event_type = "entered_ob"
                else:
                    event_type = "crossed_midline_up"

            # For midline crossings when coming from neutral (shouldn't happen, but safe)
            if prev_zone == "neutral" and curr_zone == "neutral":
                # Determine up or down via value change
                if values[i] > values[i - 1]:
                    event_type = "crossed_midline_up"
                else:
                    event_type = "crossed_midline_down"

            events.append(
                {
                    "date": dates[i],
                    "universe": universe,
                    "indicator": indicator,
                    "event_type": event_type,
                    "value": count,
                    "prior_zone_duration_days": prior_duration,
                    "prior_zone": prev_zone,
                }
            )

            zone_start_idx = i
            prev_zone = curr_zone

    return events


class BreadthZoneDetector:
    """Detect breadth zone-crossing events from de_breadth_daily."""

    def __init__(
        self,
        session: AsyncSession,
        redis_client: Optional["Redis"] = None,
    ) -> None:
        self._session = session
        self._redis = redis_client

    def _cache_key(self, universe: str, range_: str, indicator: str, eod_date: str) -> str:
        return f"breadth_zone:{universe}:{range_}:{indicator}:{eod_date}"

    async def _get_cached(self, key: str) -> Optional[dict[str, Any]]:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
            if raw is not None:
                cached: dict[str, Any] = json.loads(raw)
                return cached
        except Exception as exc:
            log.warning("breadth_zone_cache_get_error", error=str(exc))
        return None

    async def _set_cached(self, key: str, data: dict[str, Any]) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(key, _CACHE_TTL, json.dumps(data, default=str))
        except Exception as exc:
            log.warning("breadth_zone_cache_set_error", error=str(exc))

    async def compute(
        self,
        universe: str,
        range_: str,
        indicator: str,
    ) -> dict[str, Any]:
        """Compute zone-crossing events for the given universe/range/indicator.

        Args:
            universe: "nifty500" or "nifty50"
            range_: "1y", "5y", or "all"
            indicator: "ema21", "dma50", "dma200", or "all"

        Returns:
            Dict matching zone_events.schema.json shape.
        """
        t0 = time.monotonic()
        thresholds = _THRESHOLDS.get(universe, _DEFAULT_THRESHOLDS)

        # Determine date range
        days = _RANGE_DAYS.get(range_)

        # Build date filter SQL
        if days is not None:
            date_filter = f"WHERE date >= CURRENT_DATE - INTERVAL '{days} days'"
        else:
            date_filter = ""

        # Fetch breadth time-series
        query = text(
            f"""
            SELECT date::text, above_ema21, above_dma50, above_dma200
            FROM de_breadth_daily
            {date_filter}
            ORDER BY date ASC
            """
        )

        all_events: list[dict[str, Any]] = []
        data_as_of: Optional[str] = None

        try:
            query_result = await self._session.execute(query)
            rows = query_result.mappings().all()

            if rows:
                data_as_of = rows[-1]["date"]

                # Determine which indicators to process
                if indicator == "all":
                    indicators_to_run = list(_INDICATOR_COLUMN.keys())
                elif indicator in _INDICATOR_COLUMN:
                    indicators_to_run = [indicator]
                else:
                    indicators_to_run = list(_INDICATOR_COLUMN.keys())

                for ind in indicators_to_run:
                    col = _INDICATOR_COLUMN[ind]
                    dates: list[str] = []
                    values: list[int] = []
                    for row in rows:
                        v = row[col]
                        if v is not None:
                            dates.append(row["date"])
                            values.append(int(v))

                    events = _detect_events_for_series(dates, values, universe, ind, thresholds)
                    all_events.extend(events)

                # Sort merged events by date
                all_events.sort(key=lambda e: e["date"])

        except Exception as exc:
            log.warning(
                "breadth_zone_detector_query_failed",
                error=str(exc)[:300],
                universe=universe,
                range_=range_,
                indicator=indicator,
            )
            data_as_of = None

        import datetime as _dt

        if data_as_of is None:
            data_as_of = _dt.date.today().isoformat()

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        output: dict[str, Any] = {
            "universe": universe,
            "data_as_of": data_as_of,
            "source": "ATLAS zone detection engine — breadth_daily_5y derived",
            "thresholds": {
                "overbought": thresholds["overbought"],
                "midline": thresholds["midline"],
                "oversold": thresholds["oversold"],
            },
            "events": all_events,
            "_meta": {
                "data_as_of": data_as_of,
                "record_count": len(all_events),
                "query_ms": elapsed_ms,
            },
        }

        log.info(
            "breadth_zone_detector_computed",
            universe=universe,
            range_=range_,
            indicator=indicator,
            event_count=len(all_events),
            query_ms=elapsed_ms,
        )

        # Best-effort cache write
        cache_key = self._cache_key(universe, range_, indicator, data_as_of)
        await self._set_cached(cache_key, output)

        return output
