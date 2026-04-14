"""Unit tests for UQL aggregation SQL builders (V2-UQL-AGG-8).

Covers every one of the 12 functions in ``backend/services/uql/aggregations.py``
plus the threshold-validation rejection path. Pure-string assertions — no
DB, no engine, no schemas wiring.
"""

from __future__ import annotations

import pytest

from backend.models.schemas import UQLAggregation
from backend.services.uql.aggregations import build_aggregation
from backend.services.uql.errors import INVALID_AGGREGATION, UQLError


_FIELD = "r.rs_composite"
_BOOL_FIELD = "t.above_200dma"
_KEY = "thr_0"


def _agg(
    function: str, *, field: str | None = "rs_composite", threshold: float | None = None
) -> UQLAggregation:
    return UQLAggregation.model_construct(
        field=field, function=function, alias=f"a_{function}", threshold=threshold
    )


# --- simple numeric aggregates ---------------------------------------------


@pytest.mark.parametrize("fn", ["avg", "sum", "min", "max"])
def test_simple_numeric_aggregate_emits_cast_fragment(fn: str) -> None:
    sql, params = build_aggregation(_agg(fn), _FIELD, param_key=_KEY)
    assert sql == f"{fn}({_FIELD})::numeric(20, 4)"
    assert params == {}


def test_count_emits_bigint_cast() -> None:
    sql, params = build_aggregation(_agg("count"), _FIELD, param_key=_KEY)
    assert sql == f"count({_FIELD})::bigint"
    assert params == {}


def test_count_all_ignores_field_and_emits_star() -> None:
    sql, params = build_aggregation(_agg("count_all", field=None), None, param_key=_KEY)
    assert sql == "count(*)::bigint"
    assert params == {}


def test_median_uses_percentile_cont_within_group() -> None:
    sql, params = build_aggregation(_agg("median"), _FIELD, param_key=_KEY)
    assert sql == (f"(percentile_cont(0.5) within group (order by {_FIELD}))::numeric(20, 4)")
    assert params == {}


def test_stddev_uses_stddev_samp() -> None:
    sql, params = build_aggregation(_agg("stddev"), _FIELD, param_key=_KEY)
    assert sql == f"stddev_samp({_FIELD})::numeric(20, 4)"
    assert params == {}


# --- percentage aggregates --------------------------------------------------


def test_pct_true_filters_on_boolean_and_excludes_nulls() -> None:
    sql, params = build_aggregation(_agg("pct_true"), _BOOL_FIELD, param_key=_KEY)
    assert sql == (
        f"(100.0 * count(*) filter (where {_BOOL_FIELD}) "
        f"/ nullif(count({_BOOL_FIELD}), 0))::numeric(20, 4)"
    )
    assert params == {}


def test_pct_positive_uses_gt_zero_predicate() -> None:
    sql, params = build_aggregation(_agg("pct_positive"), _FIELD, param_key=_KEY)
    assert sql == (
        f"(100.0 * count(*) filter (where {_FIELD} > 0) "
        f"/ nullif(count({_FIELD}), 0))::numeric(20, 4)"
    )
    assert params == {}


def test_pct_above_binds_threshold_as_named_parameter() -> None:
    sql, params = build_aggregation(_agg("pct_above", threshold=25.0), _FIELD, param_key=_KEY)
    assert sql == (
        f"(100.0 * count(*) filter (where {_FIELD} > :{_KEY}) "
        f"/ nullif(count({_FIELD}), 0))::numeric(20, 4)"
    )
    assert params == {_KEY: 25.0}
    # the threshold must NOT be string-interpolated into the SQL
    assert "25.0" not in sql


def test_pct_below_binds_threshold_as_named_parameter() -> None:
    sql, params = build_aggregation(_agg("pct_below", threshold=-1.5), _FIELD, param_key=_KEY)
    assert sql == (
        f"(100.0 * count(*) filter (where {_FIELD} < :{_KEY}) "
        f"/ nullif(count({_FIELD}), 0))::numeric(20, 4)"
    )
    assert params == {_KEY: -1.5}
    assert "-1.5" not in sql


# --- threshold + field validation -------------------------------------------


@pytest.mark.parametrize("fn", ["pct_above", "pct_below"])
def test_threshold_required_for_threshold_functions(fn: str) -> None:
    bare = _agg(fn, threshold=None)
    with pytest.raises(UQLError) as exc_info:
        build_aggregation(bare, _FIELD, param_key=_KEY)
    assert exc_info.value.code == INVALID_AGGREGATION
    assert "threshold" in exc_info.value.message
    assert exc_info.value.suggestion  # non-empty per §20.5


@pytest.mark.parametrize(
    "fn",
    ["avg", "sum", "min", "max", "count", "median", "stddev", "pct_true", "pct_positive"],
)
def test_field_required_for_non_count_all(fn: str) -> None:
    bare = _agg(fn, field=None)
    with pytest.raises(UQLError) as exc_info:
        build_aggregation(bare, None, param_key=_KEY)
    assert exc_info.value.code == INVALID_AGGREGATION
    assert "field" in exc_info.value.message


def test_count_all_does_not_require_field_sql() -> None:
    # Should not raise even though field_sql is None
    sql, params = build_aggregation(_agg("count_all", field=None), None, param_key=_KEY)
    assert sql == "count(*)::bigint"
    assert params == {}


# --- coverage sanity --------------------------------------------------------


def test_every_uql_aggregation_function_has_a_builder() -> None:
    """Guards against silent additions to ``UQLAggregationFunction``."""
    from typing import get_args

    from backend.models.schemas import UQLAggregationFunction
    from backend.services.uql.aggregations import _BUILDERS

    declared = set(get_args(UQLAggregationFunction))
    assert declared == set(_BUILDERS.keys())
