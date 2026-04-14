"""Unit tests for the UQL engine dispatcher (V2-UQL-AGG-13).

Two non-negotiable invariants from the chunk punch list:

1. Every dispatch path — snapshot, aggregation, timeseries, template,
   validation rejection, downstream error — flows through one shared
   ``_dispatch`` and produces exactly one ``uql.execute`` log event with
   the FR-015 fields (``entity_type``, ``mode``, ``filter_count``,
   ``agg_count``, ``query_ms``, ``record_count``, ``dispatch``,
   ``status``).
2. The engine never builds SQL itself — it routes to the appropriate
   sibling translator based on ``mode`` / ``group_by`` and feeds the
   plan to the JIP port.

Tests use a hand-rolled fake JIP that records every ``execute_sql_plan``
call and returns canned rows. No real database, no FastAPI app, no
``backend.main`` import — the engine module is the only production code
under test.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
import structlog

from backend.models.schemas import (
    SortDirection,
    UQLAggregation,
    UQLFilter,
    UQLOperator,
    UQLRequest,
    UQLSort,
    UQLTimeRange,
)
from backend.services.uql import engine
from backend.services.uql.errors import (
    ENTITY_PARTITION_MISSING,
    INVALID_ENTITY_TYPE,
    LIMIT_EXCEEDED,
    TEMPLATE_NOT_FOUND,
    UQLError,
)
from backend.services.uql.optimizer import SQLPlan


# ---------------------------------------------------------------------------
# Fake JIP — records every call, returns canned rows
# ---------------------------------------------------------------------------


class FakeJip:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        total: int | None = None,
        freshness: dict[str, Any] | None = None,
    ) -> None:
        self.rows = rows if rows is not None else []
        self.total = total if total is not None else len(self.rows)
        self.freshness = (
            freshness
            if freshness is not None
            else {
                "technicals_as_of": date(2026, 4, 13),
                "mf_holdings_as_of": date(2026, 4, 13),
            }
        )
        self.plans: list[SQLPlan] = []

    async def execute_sql_plan(self, plan: SQLPlan) -> tuple[list[dict[str, Any]], int]:
        self.plans.append(plan)
        return list(self.rows), self.total

    async def get_data_freshness(self) -> dict[str, Any]:
        return self.freshness


# ---------------------------------------------------------------------------
# Helper: capture structlog events emitted during the call
# ---------------------------------------------------------------------------


def _events_named(captured: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [e for e in captured if e.get("event") == name]


# ---------------------------------------------------------------------------
# Snapshot dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_snapshot_returns_response_and_logs_once() -> None:
    request = UQLRequest(
        entity_type="equity",
        fields=["symbol", "company_name", "rs_composite"],
        filters=[UQLFilter(field="sector", op=UQLOperator.EQ, value="Banking")],
        limit=10,
    )
    jip = FakeJip(
        rows=[
            {"symbol": "HDFCBANK", "company_name": "HDFC Bank", "rs_composite": 82.1},
            {"symbol": "ICICIBANK", "company_name": "ICICI Bank", "rs_composite": 79.4},
        ]
    )

    with structlog.testing.capture_logs() as captured:
        response = await engine.execute(request, jip=jip)

    events = _events_named(captured, "uql.execute")
    assert len(events) == 1, f"expected one uql.execute event, got {events}"
    fields = events[0]
    assert fields["entity_type"] == "equity"
    assert fields["mode"] == "snapshot"
    assert fields["filter_count"] == 1
    assert fields["agg_count"] == 0
    assert fields["record_count"] == 2
    assert fields["dispatch"] == "raw"
    assert fields["status"] == "ok"
    assert "query_ms" in fields

    assert response.total == 2
    assert len(response.records) == 2
    assert response.meta.data_as_of == date(2026, 4, 13)
    assert response.meta.returned == 2
    # Plan was actually built and handed to the fake JIP.
    assert len(jip.plans) == 1
    assert "SELECT" in jip.plans[0].sql
    assert "i.current_symbol AS symbol" in jip.plans[0].sql


# ---------------------------------------------------------------------------
# Aggregation dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_aggregation_routes_through_translate_aggregation() -> None:
    request = UQLRequest(
        entity_type="sector",
        group_by=["sector"],
        aggregations=[
            UQLAggregation(field="rs_composite", function="avg", alias="avg_rs"),
            UQLAggregation(field=None, function="count_all", alias="constituents"),
        ],
        sort=[UQLSort(field="avg_rs", direction=SortDirection.DESC)],
        limit=20,
    )
    jip = FakeJip(
        rows=[
            {"sector": "Banking", "avg_rs": 78.2, "constituents": 12},
            {"sector": "IT", "avg_rs": 71.5, "constituents": 9},
        ],
        total=2,
    )

    with structlog.testing.capture_logs() as captured:
        response = await engine.execute(request, jip=jip)

    events = _events_named(captured, "uql.execute")
    assert len(events) == 1
    fields = events[0]
    assert fields["mode"] == "aggregation"
    assert fields["agg_count"] == 2
    assert fields["dispatch"] == "raw"
    assert fields["status"] == "ok"
    assert fields["record_count"] == 2

    assert "GROUP BY" in jip.plans[0].sql
    assert "avg_rs" in jip.plans[0].sql
    assert response.records[0]["sector"] == "Banking"


# ---------------------------------------------------------------------------
# Timeseries dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_timeseries_routes_through_translate_timeseries() -> None:
    request = UQLRequest(
        entity_type="mf",
        mode="timeseries",
        time_range=UQLTimeRange.model_validate({"from": "2026-01-01", "to": "2026-03-31"}),
        granularity="daily",
        filters=[UQLFilter(field="mstar_id", op=UQLOperator.EQ, value="F00000ABC")],
        fields=["nav_date", "nav"],
        limit=100,
    )
    jip = FakeJip(
        rows=[
            {"nav_date": date(2026, 1, 5), "nav": 102.5},
            {"nav_date": date(2026, 1, 6), "nav": 103.1},
        ]
    )

    with structlog.testing.capture_logs() as captured:
        response = await engine.execute(request, jip=jip)

    events = _events_named(captured, "uql.execute")
    assert len(events) == 1
    fields = events[0]
    assert fields["mode"] == "timeseries"
    assert fields["entity_type"] == "mf"
    assert fields["dispatch"] == "raw"
    assert fields["status"] == "ok"

    assert "ORDER BY" in jip.plans[0].sql
    assert "nav_date" in jip.plans[0].sql
    assert response.total == 2


# ---------------------------------------------------------------------------
# Template dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_template_uses_template_name_as_dispatch_label() -> None:
    jip = FakeJip(
        rows=[
            {"sector": "Banking", "avg_rs": 78.2, "pct_above_50dma": 0.62, "constituents": 12},
        ]
    )

    with structlog.testing.capture_logs() as captured:
        response = await engine.execute_template("sector_rotation", {"limit": 5}, jip=jip)

    events = _events_named(captured, "uql.execute")
    assert len(events) == 1
    fields = events[0]
    assert fields["dispatch"] == "sector_rotation"
    assert fields["mode"] == "aggregation"
    assert fields["status"] == "ok"
    assert response.total == 1


@pytest.mark.asyncio
async def test_execute_template_unknown_name_raises_404_and_logs_nothing() -> None:
    jip = FakeJip()
    with structlog.testing.capture_logs() as captured:
        with pytest.raises(UQLError) as exc_info:
            await engine.execute_template("does_not_exist", {}, jip=jip)
    # Template lookup happens BEFORE _dispatch, so no uql.execute log here.
    assert _events_named(captured, "uql.execute") == []
    assert exc_info.value.code == TEMPLATE_NOT_FOUND
    assert exc_info.value.http_status == 404


# ---------------------------------------------------------------------------
# Error paths still emit one log event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_unknown_entity_type_raises_and_logs_once() -> None:
    request = UQLRequest.model_construct(  # bypass Literal validation
        entity_type="portfolio",  # type: ignore[arg-type]
        filters=[],
        sort=[],
        group_by=None,
        aggregations=[],
        mode="snapshot",
        time_range=None,
        granularity="daily",
        fields=["symbol"],
        include=None,
        limit=10,
        offset=0,
    )
    jip = FakeJip()

    with structlog.testing.capture_logs() as captured:
        with pytest.raises(UQLError) as exc_info:
            await engine.execute(request, jip=jip)

    assert exc_info.value.code == INVALID_ENTITY_TYPE
    events = _events_named(captured, "uql.execute")
    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["error_code"] == INVALID_ENTITY_TYPE
    assert events[0]["dispatch"] == "raw"


@pytest.mark.asyncio
async def test_execute_safety_rejection_logs_once() -> None:
    # 11 filters → safety.validate_limits raises INVALID_FILTER, but
    # UQLRequest itself caps filters at 10 — bypass with model_construct.
    request = UQLRequest.model_construct(
        entity_type="equity",
        filters=[UQLFilter(field="sector", op=UQLOperator.EQ, value=str(i)) for i in range(11)],
        sort=[],
        group_by=None,
        aggregations=[],
        mode="snapshot",
        time_range=None,
        granularity="daily",
        fields=["symbol"],
        include=None,
        limit=10,
        offset=0,
    )
    jip = FakeJip()
    with structlog.testing.capture_logs() as captured:
        with pytest.raises(UQLError):
            await engine.execute(request, jip=jip)
    events = _events_named(captured, "uql.execute")
    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["filter_count"] == 11


@pytest.mark.asyncio
async def test_execute_limit_overflow_logs_once() -> None:
    request = UQLRequest.model_construct(
        entity_type="equity",
        filters=[],
        sort=[],
        group_by=None,
        aggregations=[],
        mode="snapshot",
        time_range=None,
        granularity="daily",
        fields=["symbol"],
        include=None,
        limit=5000,
        offset=0,
    )
    jip = FakeJip()
    with structlog.testing.capture_logs() as captured:
        with pytest.raises(UQLError) as exc_info:
            await engine.execute(request, jip=jip)
    assert exc_info.value.code == LIMIT_EXCEEDED
    events = _events_named(captured, "uql.execute")
    assert len(events) == 1
    assert events[0]["error_code"] == LIMIT_EXCEEDED


@pytest.mark.asyncio
async def test_execute_missing_partition_raises_503_and_logs_once() -> None:
    request = UQLRequest(
        entity_type="equity",
        fields=["symbol"],
        limit=5,
    )
    jip = FakeJip(rows=[{"symbol": "X"}], freshness={})

    with structlog.testing.capture_logs() as captured:
        with pytest.raises(UQLError) as exc_info:
            await engine.execute(request, jip=jip)

    assert exc_info.value.code == ENTITY_PARTITION_MISSING
    assert exc_info.value.http_status == 503
    events = _events_named(captured, "uql.execute")
    assert len(events) == 1
    assert events[0]["error_code"] == ENTITY_PARTITION_MISSING


# ---------------------------------------------------------------------------
# build_from_legacy is still a stub at this chunk
# ---------------------------------------------------------------------------


def test_build_from_legacy_is_stub_until_agg_15() -> None:
    with pytest.raises(NotImplementedError):
        engine.build_from_legacy("stocks.universe", {})
