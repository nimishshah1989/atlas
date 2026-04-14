"""UQL ``_meta`` builder — data_as_of, pagination, staleness.

`resolve_data_as_of(jip, entity_type)` queries the latest partition per
entity via `JIPDataService.get_data_freshness`. `build_meta(...)` returns
a fully-populated `ResponseMeta` with `staleness` derived as
`fresh` / `stale` / `unknown` from the 18-hour IST business window.

Spec refs: specs/004-uql-aggregations/data-model.md §4 ResponseMeta v2,
spec.md FR-011/FR-019/FR-021.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal, Optional, Protocol

from backend.models.schemas import ResponseMeta, UQLRequest

__all__ = [
    "IST",
    "STALENESS_WINDOW_HOURS",
    "Staleness",
    "resolve_data_as_of",
    "build_meta",
]

IST = timezone(timedelta(hours=5, minutes=30))
STALENESS_WINDOW_HOURS = 18

Staleness = Literal["fresh", "stale", "unknown"]

# entity_type → which key in get_data_freshness() carries its as-of date.
# `sector` derives from `equity` (FR-019). `mf` uses the closest available
# freshness key in V2; AGG-7 will refine once nav freshness is exposed.
_FRESHNESS_KEY: dict[str, str] = {
    "equity": "technicals_as_of",
    "sector": "technicals_as_of",
    "index": "technicals_as_of",
    "mf": "mf_holdings_as_of",
}


class _FreshnessProvider(Protocol):
    async def get_data_freshness(self) -> dict[str, Any]: ...


async def resolve_data_as_of(jip: _FreshnessProvider, entity_type: str) -> Optional[date]:
    """Return latest loaded partition date for ``entity_type``, or None.

    None signals the caller (engine dispatcher) should raise
    ENTITY_PARTITION_MISSING per FR-019.
    """
    key = _FRESHNESS_KEY.get(entity_type)
    if key is None:
        return None
    freshness = await jip.get_data_freshness()
    value = freshness.get(key) if freshness else None
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _to_ist_datetime(value: date | datetime) -> datetime:
    """Normalize a date or datetime to an IST-aware datetime.

    A bare ``date`` is anchored at IST market close (15:30) — partitions
    are stamped with the trading day, and the partition becomes "as of"
    when the close prints.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=IST)
        return value.astimezone(IST)
    return datetime.combine(value, time(15, 30), tzinfo=IST)


def _staleness(data_as_of: date | datetime | None, now: datetime) -> Staleness:
    if data_as_of is None:
        return "unknown"
    as_of_dt = _to_ist_datetime(data_as_of)
    delta = now - as_of_dt
    if timedelta(0) <= delta <= timedelta(hours=STALENESS_WINDOW_HOURS):
        return "fresh"
    return "stale"


def build_meta(
    request: UQLRequest,
    rows: list[Any],
    total_count: int,
    query_ms: int,
    data_as_of: date | datetime | None,
    includes_loaded: Optional[list[str]] = None,
    cache_hit: bool = False,
    now: Optional[datetime] = None,
) -> ResponseMeta:
    """Build a fully-populated `ResponseMeta` for a UQL response.

    Pagination math follows §20.4: ``has_more`` is ``total_count > offset
    + returned``; ``next_offset`` is ``offset + limit`` when ``has_more``
    else ``None``.
    """
    returned = len(rows)
    offset = request.offset
    limit = request.limit
    has_more = total_count > offset + returned
    next_offset: Optional[int] = offset + limit if has_more else None
    now_ist = now if now is not None else datetime.now(IST)
    staleness = _staleness(data_as_of, now_ist)

    as_of_date: Optional[date]
    if isinstance(data_as_of, datetime):
        as_of_date = data_as_of.astimezone(IST).date()
    else:
        as_of_date = data_as_of

    return ResponseMeta(
        data_as_of=as_of_date,
        record_count=returned,
        query_ms=query_ms,
        stale=(staleness == "stale"),
        returned=returned,
        total_count=total_count,
        offset=offset,
        limit=limit,
        has_more=has_more,
        next_offset=next_offset,
        cache_hit=cache_hit,
        includes_loaded=includes_loaded,
        staleness=staleness,
    )
