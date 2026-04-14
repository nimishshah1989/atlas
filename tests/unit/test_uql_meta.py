"""Unit tests for the UQL ``_meta`` builder (V2-UQL-AGG-6).

Covers:
- `resolve_data_as_of` per entity_type, missing partition, dict-empty
- `build_meta` pagination math: first page, middle page, last page, empty
- `build_meta` staleness branches: fresh / stale / unknown
- IST normalization of a bare `date` to market-close anchor
- `data_as_of` accepts both date and timezone-aware datetime
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from backend.models.schemas import UQLAggregation, UQLRequest
from backend.services.uql.meta import (
    IST,
    STALENESS_WINDOW_HOURS,
    build_meta,
    resolve_data_as_of,
)


class _FakeJip:
    def __init__(self, freshness: dict[str, Any]) -> None:
        self._freshness = freshness

    async def get_data_freshness(self) -> dict[str, Any]:
        return self._freshness


def _req(limit: int = 50, offset: int = 0) -> UQLRequest:
    return UQLRequest(entity_type="equity", fields=["symbol"], limit=limit, offset=offset)


# --- resolve_data_as_of -----------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_data_as_of_equity_returns_technicals_date() -> None:
    jip = _FakeJip({"technicals_as_of": date(2026, 4, 13), "mf_holdings_as_of": date(2026, 4, 1)})
    assert await resolve_data_as_of(jip, "equity") == date(2026, 4, 13)


@pytest.mark.asyncio
async def test_resolve_data_as_of_sector_inherits_equity() -> None:
    jip = _FakeJip({"technicals_as_of": date(2026, 4, 13)})
    assert await resolve_data_as_of(jip, "sector") == date(2026, 4, 13)


@pytest.mark.asyncio
async def test_resolve_data_as_of_mf_returns_holdings_date() -> None:
    jip = _FakeJip({"technicals_as_of": date(2026, 4, 13), "mf_holdings_as_of": date(2026, 4, 10)})
    assert await resolve_data_as_of(jip, "mf") == date(2026, 4, 10)


@pytest.mark.asyncio
async def test_resolve_data_as_of_index_returns_technicals_date() -> None:
    jip = _FakeJip({"technicals_as_of": date(2026, 4, 13)})
    assert await resolve_data_as_of(jip, "index") == date(2026, 4, 13)


@pytest.mark.asyncio
async def test_resolve_data_as_of_unknown_entity_returns_none() -> None:
    jip = _FakeJip({"technicals_as_of": date(2026, 4, 13)})
    assert await resolve_data_as_of(jip, "bond") is None


@pytest.mark.asyncio
async def test_resolve_data_as_of_missing_partition_returns_none() -> None:
    jip = _FakeJip({"technicals_as_of": None})
    assert await resolve_data_as_of(jip, "equity") is None


@pytest.mark.asyncio
async def test_resolve_data_as_of_empty_freshness_returns_none() -> None:
    jip = _FakeJip({})
    assert await resolve_data_as_of(jip, "equity") is None


@pytest.mark.asyncio
async def test_resolve_data_as_of_accepts_datetime_value() -> None:
    jip = _FakeJip({"technicals_as_of": datetime(2026, 4, 13, 15, 30, tzinfo=IST)})
    assert await resolve_data_as_of(jip, "equity") == date(2026, 4, 13)


# --- build_meta — pagination math ------------------------------------------


def test_build_meta_first_page_has_more_true() -> None:
    req = _req(limit=50, offset=0)
    rows = [object()] * 50
    meta = build_meta(req, rows, total_count=137, query_ms=12, data_as_of=date(2026, 4, 13))
    assert meta.returned == 50
    assert meta.record_count == 50
    assert meta.total_count == 137
    assert meta.offset == 0
    assert meta.limit == 50
    assert meta.has_more is True
    assert meta.next_offset == 50


def test_build_meta_middle_page_has_more_true() -> None:
    req = _req(limit=50, offset=50)
    rows = [object()] * 50
    meta = build_meta(req, rows, total_count=137, query_ms=8, data_as_of=date(2026, 4, 13))
    assert meta.has_more is True
    assert meta.next_offset == 100


def test_build_meta_last_page_partial_has_more_false() -> None:
    req = _req(limit=50, offset=100)
    rows = [object()] * 37
    meta = build_meta(req, rows, total_count=137, query_ms=4, data_as_of=date(2026, 4, 13))
    assert meta.has_more is False
    assert meta.next_offset is None
    assert meta.returned == 37


def test_build_meta_exact_boundary_has_more_false() -> None:
    """total_count == offset + returned → no more pages."""
    req = _req(limit=50, offset=50)
    rows = [object()] * 50
    meta = build_meta(req, rows, total_count=100, query_ms=4, data_as_of=date(2026, 4, 13))
    assert meta.has_more is False
    assert meta.next_offset is None


def test_build_meta_empty_result_has_more_false() -> None:
    req = _req(limit=50, offset=0)
    meta = build_meta(req, [], total_count=0, query_ms=2, data_as_of=date(2026, 4, 13))
    assert meta.returned == 0
    assert meta.total_count == 0
    assert meta.has_more is False
    assert meta.next_offset is None


# --- build_meta — staleness branches ---------------------------------------


def _now_at(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=IST)


def test_build_meta_staleness_fresh_within_18h_window() -> None:
    # Partition stamped 2026-04-13 → market close 15:30 IST.
    # "now" is 2026-04-14 09:00 IST → 17h30m later → fresh.
    req = _req()
    meta = build_meta(
        req,
        rows=[object()],
        total_count=1,
        query_ms=1,
        data_as_of=date(2026, 4, 13),
        now=_now_at(2026, 4, 14, 9, 0),
    )
    assert meta.staleness == "fresh"
    assert meta.stale is False


def test_build_meta_staleness_stale_just_past_window() -> None:
    # 18h01m past the 15:30 anchor → stale.
    req = _req()
    meta = build_meta(
        req,
        rows=[object()],
        total_count=1,
        query_ms=1,
        data_as_of=date(2026, 4, 13),
        now=_now_at(2026, 4, 14, 9, 31),
    )
    assert meta.staleness == "stale"
    assert meta.stale is True


def test_build_meta_staleness_stale_weekend() -> None:
    # Monday morning, last partition Friday → > 18h → stale.
    req = _req()
    meta = build_meta(
        req,
        rows=[object()],
        total_count=1,
        query_ms=1,
        data_as_of=date(2026, 4, 10),  # Friday
        now=_now_at(2026, 4, 13, 9, 0),  # Monday
    )
    assert meta.staleness == "stale"


def test_build_meta_staleness_unknown_when_data_as_of_missing() -> None:
    req = _req()
    meta = build_meta(
        req,
        rows=[],
        total_count=0,
        query_ms=1,
        data_as_of=None,
        now=_now_at(2026, 4, 14, 9, 0),
    )
    assert meta.staleness == "unknown"
    assert meta.stale is False


def test_build_meta_staleness_exact_window_edge_is_fresh() -> None:
    # Exactly 18h after close → still fresh (inclusive boundary).
    req = _req()
    anchor = datetime(2026, 4, 13, 15, 30, tzinfo=IST)
    meta = build_meta(
        req,
        rows=[object()],
        total_count=1,
        query_ms=1,
        data_as_of=date(2026, 4, 13),
        now=anchor + timedelta(hours=STALENESS_WINDOW_HOURS),
    )
    assert meta.staleness == "fresh"


def test_build_meta_staleness_accepts_datetime_data_as_of() -> None:
    req = _req()
    meta = build_meta(
        req,
        rows=[object()],
        total_count=1,
        query_ms=1,
        data_as_of=datetime(2026, 4, 14, 8, 0, tzinfo=IST),
        now=_now_at(2026, 4, 14, 10, 0),
    )
    assert meta.staleness == "fresh"
    assert meta.data_as_of == date(2026, 4, 14)


# --- build_meta — passthrough fields ---------------------------------------


def test_build_meta_includes_loaded_passthrough() -> None:
    req = _req()
    meta = build_meta(
        req,
        rows=[],
        total_count=0,
        query_ms=1,
        data_as_of=date(2026, 4, 13),
        includes_loaded=["identity", "rs"],
    )
    assert meta.includes_loaded == ["identity", "rs"]


def test_build_meta_includes_loaded_default_none() -> None:
    req = _req()
    meta = build_meta(req, rows=[], total_count=0, query_ms=1, data_as_of=date(2026, 4, 13))
    assert meta.includes_loaded is None


def test_build_meta_cache_hit_default_false() -> None:
    req = _req()
    meta = build_meta(req, rows=[], total_count=0, query_ms=1, data_as_of=date(2026, 4, 13))
    assert meta.cache_hit is False


def test_build_meta_cache_hit_passthrough_true() -> None:
    req = _req()
    meta = build_meta(
        req, rows=[], total_count=0, query_ms=1, data_as_of=date(2026, 4, 13), cache_hit=True
    )
    assert meta.cache_hit is True


def test_build_meta_aggregation_request_pagination_works() -> None:
    """Pagination math is mode-agnostic — aggregation responses page too."""
    req = UQLRequest(
        entity_type="sector",
        group_by=["sector"],
        aggregations=[UQLAggregation(field="rs_composite", function="avg", alias="rs_avg")],
        limit=10,
        offset=0,
    )
    rows = [{"sector": f"S{i}", "rs_avg": 0.1} for i in range(10)]
    meta = build_meta(req, rows, total_count=23, query_ms=5, data_as_of=date(2026, 4, 13))
    assert meta.has_more is True
    assert meta.next_offset == 10
    assert meta.returned == 10
