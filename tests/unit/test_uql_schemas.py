"""Unit tests for UQL v2 Pydantic schemas (V2-UQL-AGG-2).

Every validator branch in ``backend/models/schemas.py`` UQLRequest /
UQLAggregation / UQLTimeRange must have at least one happy-path and one
rejection-path assertion. Schema shape matches
``specs/004-uql-aggregations/contracts/uql_query.schema.json``.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from backend.models.schemas import (
    UQLAggregation,
    UQLFilter,
    UQLOperator,
    UQLRequest,
    UQLSort,
    UQLTimeRange,
)


# --- UQLAggregation ---------------------------------------------------------


def test_aggregation_basic_avg_with_field_ok() -> None:
    agg = UQLAggregation(field="rs_composite", function="avg", alias="rs_avg")
    assert agg.field == "rs_composite"
    assert agg.threshold is None


def test_aggregation_count_all_field_optional() -> None:
    agg = UQLAggregation(function="count_all", alias="n")
    assert agg.field is None


def test_aggregation_non_count_all_requires_field() -> None:
    with pytest.raises(ValidationError, match="requires a 'field'"):
        UQLAggregation(function="sum", alias="s")


def test_aggregation_pct_above_requires_threshold() -> None:
    with pytest.raises(ValidationError, match="requires a numeric 'threshold'"):
        UQLAggregation(field="rs_composite", function="pct_above", alias="x")


def test_aggregation_pct_below_requires_threshold() -> None:
    with pytest.raises(ValidationError, match="requires a numeric 'threshold'"):
        UQLAggregation(field="rsi_14", function="pct_below", alias="x")


def test_aggregation_pct_above_with_threshold_ok() -> None:
    agg = UQLAggregation(field="rs_composite", function="pct_above", alias="strong", threshold=0.0)
    assert agg.threshold == 0.0


def test_aggregation_threshold_rejected_for_non_pct_function() -> None:
    with pytest.raises(ValidationError, match="'threshold' is only valid"):
        UQLAggregation(field="rs_composite", function="avg", alias="bad", threshold=10.0)


def test_aggregation_invalid_function_rejected() -> None:
    with pytest.raises(ValidationError):
        UQLAggregation(field="x", function="variance", alias="v")  # type: ignore[arg-type]


def test_aggregation_alias_required_non_empty() -> None:
    with pytest.raises(ValidationError):
        UQLAggregation(field="x", function="avg", alias="")


# --- UQLTimeRange -----------------------------------------------------------


def test_time_range_ok() -> None:
    tr = UQLTimeRange(**{"from": date(2026, 1, 1), "to": date(2026, 4, 14)})
    assert tr.from_ == date(2026, 1, 1)
    assert tr.to == date(2026, 4, 14)


def test_time_range_to_before_from_rejected() -> None:
    with pytest.raises(ValidationError, match="'to' must be on or after 'from'"):
        UQLTimeRange(**{"from": date(2026, 4, 14), "to": date(2026, 1, 1)})


def test_time_range_same_day_ok() -> None:
    tr = UQLTimeRange(**{"from": date(2026, 4, 14), "to": date(2026, 4, 14)})
    assert tr.from_ == tr.to


# --- UQLRequest happy paths -------------------------------------------------


def test_request_snapshot_with_fields_ok() -> None:
    req = UQLRequest(entity_type="equity", fields=["symbol", "rs_composite"])
    assert req.entity_type == "equity"
    assert req.mode == "snapshot"
    assert req.granularity == "daily"
    assert req.limit == 50
    assert req.offset == 0


def test_request_aggregation_mode_no_fields_required() -> None:
    req = UQLRequest(
        entity_type="sector",
        group_by=["sector"],
        aggregations=[UQLAggregation(field="rs_composite", function="avg", alias="rs_avg")],
    )
    assert req.fields is None
    assert req.group_by == ["sector"]


def test_request_timeseries_with_range_ok() -> None:
    req = UQLRequest(
        entity_type="equity",
        mode="timeseries",
        time_range=UQLTimeRange(**{"from": date(2026, 1, 1), "to": date(2026, 4, 1)}),
        fields=["close"],
    )
    assert req.mode == "timeseries"


def test_request_include_modules_ok() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["symbol"],
        include=["identity", "rs"],
    )
    assert req.include == ["identity", "rs"]


def test_request_all_four_entity_types_accepted() -> None:
    for et in ("equity", "mf", "sector", "index"):
        req = UQLRequest(entity_type=et, fields=["x"])  # type: ignore[arg-type]
        assert req.entity_type == et


# --- UQLRequest validator branches (rejection paths) -----------------------


def test_request_invalid_entity_type_rejected() -> None:
    with pytest.raises(ValidationError):
        UQLRequest(entity_type="bond", fields=["x"])  # type: ignore[arg-type]


def test_request_invalid_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        UQLRequest(entity_type="equity", mode="batch", fields=["x"])  # type: ignore[arg-type]


def test_request_invalid_granularity_rejected() -> None:
    with pytest.raises(ValidationError):
        UQLRequest(
            entity_type="equity",
            granularity="hourly",  # type: ignore[arg-type]
            fields=["x"],
        )


def test_request_invalid_include_module_rejected() -> None:
    with pytest.raises(ValidationError):
        UQLRequest(
            entity_type="equity",
            fields=["x"],
            include=["identity", "fundamentals"],  # type: ignore[list-item]
        )


def test_request_too_many_filters_rejected() -> None:
    filters = [UQLFilter(field=f"f{i}", op=UQLOperator.EQ, value=i) for i in range(11)]
    with pytest.raises(ValidationError, match="Maximum 10 filters"):
        UQLRequest(entity_type="equity", fields=["x"], filters=filters)


def test_request_exactly_ten_filters_ok() -> None:
    filters = [UQLFilter(field=f"f{i}", op=UQLOperator.EQ, value=i) for i in range(10)]
    req = UQLRequest(entity_type="equity", fields=["x"], filters=filters)
    assert len(req.filters) == 10


def test_request_too_many_aggregations_rejected() -> None:
    aggs = [UQLAggregation(field="rs_composite", function="avg", alias=f"a{i}") for i in range(9)]
    with pytest.raises(ValidationError, match="Maximum 8 aggregations"):
        UQLRequest(entity_type="equity", group_by=["sector"], aggregations=aggs)


def test_request_timeseries_without_time_range_rejected() -> None:
    with pytest.raises(ValidationError, match="'time_range' is required"):
        UQLRequest(entity_type="equity", mode="timeseries", fields=["close"])


def test_request_group_by_without_aggregations_rejected() -> None:
    with pytest.raises(ValidationError, match="'aggregations' is required"):
        UQLRequest(entity_type="equity", group_by=["sector"])


def test_request_snapshot_no_group_by_no_fields_rejected() -> None:
    with pytest.raises(ValidationError, match="'fields' is required for snapshot"):
        UQLRequest(entity_type="equity")


def test_request_snapshot_no_group_by_empty_fields_rejected() -> None:
    with pytest.raises(ValidationError, match="'fields' is required for snapshot"):
        UQLRequest(entity_type="equity", fields=[])


def test_request_duplicate_aggregation_aliases_rejected() -> None:
    aggs = [
        UQLAggregation(field="rs_composite", function="avg", alias="dup"),
        UQLAggregation(field="rsi_14", function="avg", alias="dup"),
    ]
    with pytest.raises(ValidationError, match="aliases must be unique"):
        UQLRequest(entity_type="equity", group_by=["sector"], aggregations=aggs)


def test_request_limit_above_max_rejected() -> None:
    with pytest.raises(ValidationError):
        UQLRequest(entity_type="equity", fields=["x"], limit=501)


def test_request_limit_below_min_rejected() -> None:
    with pytest.raises(ValidationError):
        UQLRequest(entity_type="equity", fields=["x"], limit=0)


def test_request_negative_offset_rejected() -> None:
    with pytest.raises(ValidationError):
        UQLRequest(entity_type="equity", fields=["x"], offset=-1)


def test_request_sort_accepts_alias_in_aggregation_mode() -> None:
    # Sort field validation against group_by/alias is the engine's job
    # (V2-UQL-AGG-13). Schema layer just accepts the shape.
    req = UQLRequest(
        entity_type="sector",
        group_by=["sector"],
        aggregations=[UQLAggregation(field="rs_composite", function="avg", alias="rs_avg")],
        sort=[UQLSort(field="rs_avg")],
    )
    assert req.sort[0].field == "rs_avg"


# --- Schema-contract conformance smoke -------------------------------------


def test_request_serialization_round_trip_with_all_optional_fields() -> None:
    req = UQLRequest(
        entity_type="mf",
        filters=[UQLFilter(field="category_name", op=UQLOperator.EQ, value="Equity")],
        sort=[UQLSort(field="aum_crore")],
        group_by=["category_name"],
        aggregations=[
            UQLAggregation(field="aum_crore", function="sum", alias="total_aum"),
            UQLAggregation(
                field="rs_composite",
                function="pct_above",
                alias="pct_strong",
                threshold=0.0,
            ),
        ],
        mode="timeseries",
        time_range=UQLTimeRange(**{"from": date(2026, 1, 1), "to": date(2026, 4, 1)}),
        granularity="daily",
        include=["identity", "rs"],
        limit=100,
        offset=0,
    )
    dumped = req.model_dump(by_alias=True, mode="json")
    assert dumped["entity_type"] == "mf"
    assert dumped["aggregations"][1]["threshold"] == 0.0
    assert dumped["time_range"]["from"] == "2026-01-01"
    # Round-trip
    UQLRequest.model_validate(dumped)
