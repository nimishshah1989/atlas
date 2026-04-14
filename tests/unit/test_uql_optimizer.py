"""Unit tests for the UQL optimizer (V2-UQL-AGG-9).

Exercises ``translate_snapshot`` and ``translate_aggregation`` against the
real ``equity`` entity definition. No DB, no engine — pure-string
assertions on the compiled :class:`SQLPlan`.

The two non-negotiable invariants under test, taken from the chunk punch
list:

1. Both translation paths bind every user-supplied value as a named
   parameter — never string-interpolated into the SQL text — so the
   plan can be handed to SQLAlchemy ``text()`` without a SQL injection
   surface.
2. Sort field validation rejects anything that does not resolve to a
   known column (snapshot mode) or to a group_by column / aggregation
   alias (aggregation mode), surfacing ``INVALID_SORT``.
"""

from __future__ import annotations

import pytest

from backend.models.schemas import (
    UQLAggregation,
    UQLFilter,
    UQLOperator,
    UQLRequest,
    UQLSort,
    SortDirection,
)
from backend.services.uql.errors import (
    INVALID_AGGREGATION,
    INVALID_FILTER,
    INVALID_SORT,
    UQLError,
)
from backend.services.uql.optimizer import (
    SQLPlan,
    translate_aggregation,
    translate_snapshot,
)
from backend.services.uql.registry import REGISTRY


EQUITY = REGISTRY["equity"]


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def test_snapshot_minimal_projection_emits_named_aliases() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["symbol", "rs_composite"],
    )
    plan = translate_snapshot(req, EQUITY)

    assert isinstance(plan, SQLPlan)
    assert plan.sql.startswith(
        "SELECT i.current_symbol AS symbol, r.rs_composite AS rs_composite FROM"
    )
    assert "de_instrument i" in plan.sql
    assert "LEFT JOIN de_rs_scores r" in plan.sql
    assert "LIMIT :_limit OFFSET :_offset" in plan.sql
    assert plan.params["_limit"] == 50
    assert plan.params["_offset"] == 0
    assert plan.count_sql is not None
    assert plan.count_sql.startswith("SELECT count(*) FROM")
    assert "LIMIT" not in plan.count_sql


def test_snapshot_filters_bind_every_value_as_named_parameter() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["symbol"],
        filters=[
            UQLFilter(field="sector", op=UQLOperator.EQ, value="Banks"),
            UQLFilter(field="rs_composite", op=UQLOperator.GTE, value=70),
            UQLFilter(
                field="cap_category",
                op=UQLOperator.IN,
                value=["LARGE", "MID"],
            ),
            UQLFilter(
                field="rs_1m",
                op=UQLOperator.BETWEEN,
                value=[10, 90],
            ),
            UQLFilter(field="symbol", op=UQLOperator.CONTAINS, value="HDFC"),
            UQLFilter(field="industry", op=UQLOperator.IS_NOT_NULL, value=None),
        ],
    )
    plan = translate_snapshot(req, EQUITY)

    # Every literal must be a bound parameter, not interpolated.
    for forbidden in ("'Banks'", "'HDFC'", "70", "10", "90", "LARGE", "MID"):
        assert forbidden not in plan.sql, f"value {forbidden!r} leaked into SQL"

    # Bind names are all referenced in the SQL with their colon prefix.
    for key in plan.params:
        if key in ("_limit", "_offset"):
            continue
        assert f":{key}" in plan.sql

    assert plan.params["f0"] == "Banks"
    assert plan.params["f1"] == 70
    assert plan.params["f2_0"] == "LARGE"
    assert plan.params["f2_1"] == "MID"
    assert plan.params["f3_lo"] == 10
    assert plan.params["f3_hi"] == 90
    assert plan.params["f4"] == "%HDFC%"
    # is_not_null contributes no params
    assert "f5" not in plan.params

    # WHERE clause structure
    assert "i.sector = :f0" in plan.sql
    assert "r.rs_composite >= :f1" in plan.sql
    assert "cap.cap_category IN (:f2_0, :f2_1)" in plan.sql
    assert "r.rs_1m BETWEEN :f3_lo AND :f3_hi" in plan.sql
    assert "i.current_symbol ILIKE :f4" in plan.sql
    assert "i.industry IS NOT NULL" in plan.sql

    # count_sql shares the WHERE clause but drops LIMIT/OFFSET
    assert plan.count_sql is not None
    assert ":f0" in plan.count_sql
    assert "LIMIT" not in plan.count_sql
    assert plan.count_params is not None
    assert "_limit" not in plan.count_params


def test_snapshot_sort_resolves_known_column() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["symbol", "rs_composite"],
        sort=[UQLSort(field="rs_composite", direction=SortDirection.DESC)],
    )
    plan = translate_snapshot(req, EQUITY)
    assert "ORDER BY r.rs_composite DESC" in plan.sql


def test_snapshot_sort_unknown_column_rejected() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["symbol"],
        sort=[UQLSort(field="not_a_column", direction=SortDirection.ASC)],
    )
    with pytest.raises(UQLError) as exc_info:
        translate_snapshot(req, EQUITY)
    assert exc_info.value.code == INVALID_SORT
    assert "not_a_column" in exc_info.value.message


def test_snapshot_unknown_field_rejected() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["bogus"],
    )
    with pytest.raises(UQLError) as exc_info:
        translate_snapshot(req, EQUITY)
    assert exc_info.value.code == INVALID_FILTER
    assert "bogus" in exc_info.value.message


def test_snapshot_in_requires_non_empty_list() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["symbol"],
        filters=[UQLFilter(field="sector", op=UQLOperator.IN, value=[])],
    )
    with pytest.raises(UQLError) as exc_info:
        translate_snapshot(req, EQUITY)
    assert exc_info.value.code == INVALID_FILTER


def test_snapshot_between_requires_two_element_list() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["symbol"],
        filters=[UQLFilter(field="rs_composite", op=UQLOperator.BETWEEN, value=[10])],
    )
    with pytest.raises(UQLError) as exc_info:
        translate_snapshot(req, EQUITY)
    assert exc_info.value.code == INVALID_FILTER


def test_snapshot_limit_and_offset_round_trip() -> None:
    req = UQLRequest(
        entity_type="equity",
        fields=["symbol"],
        limit=200,
        offset=100,
    )
    plan = translate_snapshot(req, EQUITY)
    assert plan.params["_limit"] == 200
    assert plan.params["_offset"] == 100
    # the literal numbers must NOT be interpolated
    assert " 200 " not in plan.sql
    assert " 100 " not in plan.sql


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def test_aggregation_emits_group_by_and_named_aliases() -> None:
    req = UQLRequest(
        entity_type="equity",
        group_by=["sector"],
        aggregations=[
            UQLAggregation(field="rs_composite", function="avg", alias="avg_rs"),
            UQLAggregation(function="count_all", alias="n"),
        ],
    )
    plan = translate_aggregation(req, EQUITY)

    assert "i.sector AS sector" in plan.sql
    assert "avg(r.rs_composite)::numeric(20, 4) AS avg_rs" in plan.sql
    assert "count(*)::bigint AS n" in plan.sql
    assert "GROUP BY i.sector" in plan.sql
    assert "LIMIT :_limit OFFSET :_offset" in plan.sql
    # No count_sql for aggregation plans — record count == row count.
    assert plan.count_sql is None


def test_aggregation_threshold_bound_as_parameter() -> None:
    req = UQLRequest(
        entity_type="equity",
        group_by=["sector"],
        aggregations=[
            UQLAggregation(
                field="rs_composite",
                function="pct_above",
                alias="pct_strong",
                threshold=70.0,
            ),
        ],
    )
    plan = translate_aggregation(req, EQUITY)

    assert "pct_strong" in plan.sql
    assert ":thr_0" in plan.sql
    assert plan.params["thr_0"] == 70.0
    # the literal threshold must NOT be interpolated anywhere in the SQL
    assert "70.0" not in plan.sql
    assert "70" not in plan.sql.replace(":thr_0", "").replace("(20, 4)", "")


def test_aggregation_filters_bind_values() -> None:
    req = UQLRequest(
        entity_type="equity",
        group_by=["sector"],
        aggregations=[UQLAggregation(function="count_all", alias="n")],
        filters=[
            UQLFilter(field="is_active", op=UQLOperator.EQ, value=True),
        ],
    )
    plan = translate_aggregation(req, EQUITY)
    assert "i.is_active = :f0" in plan.sql
    assert plan.params["f0"] is True


def test_aggregation_sort_by_alias_emits_alias_in_order_by() -> None:
    req = UQLRequest(
        entity_type="equity",
        group_by=["sector"],
        aggregations=[
            UQLAggregation(field="rs_composite", function="avg", alias="avg_rs"),
        ],
        sort=[UQLSort(field="avg_rs", direction=SortDirection.DESC)],
    )
    plan = translate_aggregation(req, EQUITY)
    assert "ORDER BY avg_rs DESC" in plan.sql


def test_aggregation_sort_by_group_by_column_resolved() -> None:
    req = UQLRequest(
        entity_type="equity",
        group_by=["sector"],
        aggregations=[UQLAggregation(function="count_all", alias="n")],
        sort=[UQLSort(field="sector", direction=SortDirection.ASC)],
    )
    plan = translate_aggregation(req, EQUITY)
    assert "ORDER BY i.sector ASC" in plan.sql


def test_aggregation_sort_by_unknown_field_rejected() -> None:
    req = UQLRequest(
        entity_type="equity",
        group_by=["sector"],
        aggregations=[
            UQLAggregation(field="rs_composite", function="avg", alias="avg_rs"),
        ],
        sort=[UQLSort(field="rs_composite", direction=SortDirection.DESC)],
    )
    with pytest.raises(UQLError) as exc_info:
        translate_aggregation(req, EQUITY)
    assert exc_info.value.code == INVALID_SORT
    assert "rs_composite" in exc_info.value.message
    # error suggestion should name both legal sources
    assert "alias" in exc_info.value.suggestion or "group_by" in exc_info.value.suggestion


def test_aggregation_unknown_group_by_column_rejected() -> None:
    req = UQLRequest(
        entity_type="equity",
        group_by=["bogus"],
        aggregations=[UQLAggregation(function="count_all", alias="n")],
    )
    with pytest.raises(UQLError) as exc_info:
        translate_aggregation(req, EQUITY)
    assert exc_info.value.code == INVALID_FILTER


def test_aggregation_non_groupable_field_rejected() -> None:
    # rs_composite is aggregatable, not groupable
    req = UQLRequest(
        entity_type="equity",
        group_by=["rs_composite"],
        aggregations=[UQLAggregation(function="count_all", alias="n")],
    )
    with pytest.raises(UQLError) as exc_info:
        translate_aggregation(req, EQUITY)
    assert exc_info.value.code == INVALID_FILTER
    assert "groupable" in exc_info.value.message


def test_aggregation_non_aggregatable_field_rejected() -> None:
    # symbol is groupable, not aggregatable
    req = UQLRequest(
        entity_type="equity",
        group_by=["sector"],
        aggregations=[
            UQLAggregation(field="symbol", function="avg", alias="bad"),
        ],
    )
    with pytest.raises(UQLError) as exc_info:
        translate_aggregation(req, EQUITY)
    assert exc_info.value.code == INVALID_AGGREGATION
    assert "aggregatable" in exc_info.value.message


def test_aggregation_threshold_collisions_avoided_across_aggregations() -> None:
    req = UQLRequest(
        entity_type="equity",
        group_by=["sector"],
        aggregations=[
            UQLAggregation(
                field="rs_composite",
                function="pct_above",
                alias="pct_strong",
                threshold=70.0,
            ),
            UQLAggregation(
                field="rs_composite",
                function="pct_below",
                alias="pct_weak",
                threshold=30.0,
            ),
        ],
    )
    plan = translate_aggregation(req, EQUITY)
    assert plan.params["thr_0"] == 70.0
    assert plan.params["thr_1"] == 30.0
    assert ":thr_0" in plan.sql
    assert ":thr_1" in plan.sql
