"""Unit tests for UQL §17.9 safety enforcement (V2-UQL-AGG-5).

Covers every rejection path documented in
``backend/services/uql/safety.py`` and asserts the legitimate-query
happy paths to guard against false positives.
"""

from __future__ import annotations

import pytest

from backend.models.schemas import (
    UQLAggregation,
    UQLFilter,
    UQLRequest,
)
from backend.services.uql import errors
from backend.services.uql.registry import (
    REGISTRY,
    EntityDef,
    FieldSpec,
    FieldType,
    IndexedColumn,
)
from backend.services.uql.safety import (
    LARGE_ENTITY_THRESHOLD,
    MAX_AGGREGATIONS,
    MAX_FILTERS,
    MAX_LIMIT,
    validate_full_scan,
    validate_limits,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic large entity so full-scan rejection has something to
# bite on. Real entities are all ≤ 5k rows.
# ---------------------------------------------------------------------------


def _huge_entity() -> EntityDef:
    """A fabricated >1M-row entity with one indexed and one unindexed field."""

    fields = {
        "symbol": FieldSpec("symbol", "h.symbol", FieldType.STRING),
        "price": FieldSpec("price", "h.price", FieldType.DECIMAL, aggregatable=True),
    }
    return EntityDef(
        name="huge",
        base_table="de_huge",
        base_alias="h",
        primary_key="symbol",
        joins=(),
        fields=fields,
        row_count_estimate=LARGE_ENTITY_THRESHOLD + 1,
        indexed_columns=frozenset({IndexedColumn("de_huge", "symbol")}),
    )


def _legit_snapshot() -> UQLRequest:
    return UQLRequest(
        entity_type="equity",
        filters=[UQLFilter(field="sector", op="=", value="Financials")],
        fields=["symbol", "rs_composite"],
        limit=50,
    )


# ---------------------------------------------------------------------------
# validate_limits — rejection paths
# ---------------------------------------------------------------------------


def test_validate_limits_rejects_oversized_limit() -> None:
    # Pydantic caps at 500; build via model_construct to bypass and prove
    # safety.py is the second line of defense for internal builders.
    req = UQLRequest.model_construct(
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
        limit=MAX_LIMIT + 1,
        offset=0,
    )
    with pytest.raises(errors.UQLError) as excinfo:
        validate_limits(req)
    assert excinfo.value.code == errors.LIMIT_EXCEEDED
    assert excinfo.value.http_status == 400
    assert excinfo.value.suggestion


def test_validate_limits_rejects_too_many_filters() -> None:
    req = UQLRequest.model_construct(
        entity_type="equity",
        filters=[UQLFilter(field="sector", op="=", value=str(i)) for i in range(MAX_FILTERS + 1)],
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
    with pytest.raises(errors.UQLError) as excinfo:
        validate_limits(req)
    assert excinfo.value.code == errors.INVALID_FILTER


def test_validate_limits_rejects_too_many_aggregations() -> None:
    aggs = [
        UQLAggregation(field="rs_composite", function="avg", alias=f"a{i}")
        for i in range(MAX_AGGREGATIONS + 1)
    ]
    req = UQLRequest.model_construct(
        entity_type="equity",
        filters=[],
        sort=[],
        group_by=["sector"],
        aggregations=aggs,
        mode="snapshot",
        time_range=None,
        granularity="daily",
        fields=None,
        include=None,
        limit=10,
        offset=0,
    )
    with pytest.raises(errors.UQLError) as excinfo:
        validate_limits(req)
    assert excinfo.value.code == errors.INVALID_AGGREGATION


def test_validate_limits_requires_fields_in_snapshot_mode() -> None:
    req = UQLRequest.model_construct(
        entity_type="equity",
        filters=[],
        sort=[],
        group_by=None,
        aggregations=[],
        mode="snapshot",
        time_range=None,
        granularity="daily",
        fields=None,
        include=None,
        limit=10,
        offset=0,
    )
    with pytest.raises(errors.UQLError) as excinfo:
        validate_limits(req)
    assert excinfo.value.code == errors.FIELDS_REQUIRED


# ---------------------------------------------------------------------------
# validate_limits — happy paths (no false positives)
# ---------------------------------------------------------------------------


def test_validate_limits_accepts_legit_snapshot() -> None:
    validate_limits(_legit_snapshot())


def test_validate_limits_accepts_aggregation_without_fields() -> None:
    req = UQLRequest(
        entity_type="equity",
        group_by=["sector"],
        aggregations=[UQLAggregation(field="rs_composite", function="avg", alias="rs_avg")],
    )
    validate_limits(req)


def test_validate_limits_accepts_max_limit_exactly() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["symbol"],
        limit=MAX_LIMIT,
    )
    validate_limits(req)


def test_validate_limits_accepts_max_filters_exactly() -> None:
    req = UQLRequest(
        entity_type="equity",
        filters=[UQLFilter(field="sector", op="=", value=str(i)) for i in range(MAX_FILTERS)],
        fields=["symbol"],
    )
    validate_limits(req)


# ---------------------------------------------------------------------------
# validate_full_scan
# ---------------------------------------------------------------------------


def test_full_scan_skipped_for_small_entity() -> None:
    req = UQLRequest(
        entity_type="equity",
        filters=[UQLFilter(field="rs_composite", op=">", value=0)],
        fields=["symbol"],
    )
    validate_full_scan(req, REGISTRY["equity"])


def test_full_scan_rejects_unindexed_filter_on_huge_entity() -> None:
    huge = _huge_entity()
    req = UQLRequest.model_construct(
        entity_type="equity",
        filters=[UQLFilter(field="price", op=">", value=100)],
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
    with pytest.raises(errors.UQLError) as excinfo:
        validate_full_scan(req, huge)
    assert excinfo.value.code == errors.FULL_SCAN_REJECTED
    assert "indexed" in excinfo.value.suggestion.lower()


def test_full_scan_accepts_indexed_filter_on_huge_entity() -> None:
    huge = _huge_entity()
    req = UQLRequest.model_construct(
        entity_type="equity",
        filters=[UQLFilter(field="symbol", op="=", value="HDFC")],
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
    validate_full_scan(req, huge)


def test_full_scan_unknown_field_raises_invalid_filter() -> None:
    huge = _huge_entity()
    req = UQLRequest.model_construct(
        entity_type="equity",
        filters=[UQLFilter(field="nope", op="=", value="x")],
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
    with pytest.raises(errors.UQLError) as excinfo:
        validate_full_scan(req, huge)
    assert excinfo.value.code == errors.INVALID_FILTER


def test_full_scan_no_op_when_no_filters() -> None:
    huge = _huge_entity()
    req = UQLRequest.model_construct(
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
        limit=10,
        offset=0,
    )
    validate_full_scan(req, huge)
