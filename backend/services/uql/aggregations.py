"""UQL aggregation SQL builders — one builder per ``UQLAggregation``.

Each builder returns ``(sql_expression, params)`` for the SELECT-list body
of a single aggregation, **without** the trailing ``AS alias`` (the optimizer
owns projection assembly). Numeric results are cast to ``numeric(20, 4)`` to
match the wire-format precision of every Decimal column in ATLAS;
``count`` / ``count_all`` are cast to ``bigint``.

Implementation choices anchored in
``specs/004-uql-aggregations/tasks.md`` T012 and §17.5 of the master spec:

* ``median`` is ``percentile_cont(0.5) WITHIN GROUP (ORDER BY ...)``.
* ``stddev`` is ``stddev_samp`` (sample stddev, n-1 denominator).
* ``pct_above`` / ``pct_below`` require a numeric ``threshold`` and raise
  ``UQLError(INVALID_AGGREGATION)`` otherwise. The threshold is bound as a
  parameter (``:<param_key>``) — never string-interpolated — so the
  optimizer can hand the whole plan to asyncpg cleanly.
* Every ``pct_*`` function excludes nulls from both numerator and
  denominator via ``count(<field>)`` (which counts only non-null rows) and
  ``filter (where ...)`` (which evaluates to false on null). All-null input
  yields ``nullif(0, 0) = NULL`` per FR-014.
"""

from __future__ import annotations

from typing import Any, Callable, Final

from backend.models.schemas import UQLAggregation
from backend.services.uql.errors import INVALID_AGGREGATION, UQLError

__all__ = ["build_aggregation"]


_NUMERIC_CAST: Final = "::numeric(20, 4)"
_THRESHOLD_FUNCTIONS: Final = frozenset({"pct_above", "pct_below"})

_Builder = Callable[[str, UQLAggregation, str], tuple[str, dict[str, Any]]]


def _avg(field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return f"avg({field_sql}){_NUMERIC_CAST}", {}


def _sum(field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return f"sum({field_sql}){_NUMERIC_CAST}", {}


def _min(field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return f"min({field_sql}){_NUMERIC_CAST}", {}


def _max(field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return f"max({field_sql}){_NUMERIC_CAST}", {}


def _count(field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return f"count({field_sql})::bigint", {}


def _count_all(_field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return "count(*)::bigint", {}


def _median(field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return (
        f"(percentile_cont(0.5) within group (order by {field_sql})){_NUMERIC_CAST}",
        {},
    )


def _stddev(field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return f"stddev_samp({field_sql}){_NUMERIC_CAST}", {}


def _pct_true(field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return (
        f"(100.0 * count(*) filter (where {field_sql}) "
        f"/ nullif(count({field_sql}), 0)){_NUMERIC_CAST}",
        {},
    )


def _pct_positive(field_sql: str, _agg: UQLAggregation, _key: str) -> tuple[str, dict[str, Any]]:
    return (
        f"(100.0 * count(*) filter (where {field_sql} > 0) "
        f"/ nullif(count({field_sql}), 0)){_NUMERIC_CAST}",
        {},
    )


def _pct_above(field_sql: str, agg: UQLAggregation, key: str) -> tuple[str, dict[str, Any]]:
    return (
        f"(100.0 * count(*) filter (where {field_sql} > :{key}) "
        f"/ nullif(count({field_sql}), 0)){_NUMERIC_CAST}",
        {key: agg.threshold},
    )


def _pct_below(field_sql: str, agg: UQLAggregation, key: str) -> tuple[str, dict[str, Any]]:
    return (
        f"(100.0 * count(*) filter (where {field_sql} < :{key}) "
        f"/ nullif(count({field_sql}), 0)){_NUMERIC_CAST}",
        {key: agg.threshold},
    )


_BUILDERS: Final[dict[str, _Builder]] = {
    "avg": _avg,
    "sum": _sum,
    "min": _min,
    "max": _max,
    "count": _count,
    "count_all": _count_all,
    "median": _median,
    "stddev": _stddev,
    "pct_true": _pct_true,
    "pct_positive": _pct_positive,
    "pct_above": _pct_above,
    "pct_below": _pct_below,
}


def build_aggregation(
    agg: UQLAggregation,
    field_sql: str | None,
    *,
    param_key: str,
) -> tuple[str, dict[str, Any]]:
    """Compile one ``UQLAggregation`` into ``(sql_expression, params)``.

    ``field_sql`` is the fully-qualified column expression looked up from
    the entity registry (e.g. ``r.rs_composite``); it must be ``None`` only
    when ``agg.function == "count_all"``. ``param_key`` is the unique bind
    name the optimizer reserves for this aggregation's threshold; it is
    ignored for non-threshold functions but must be supplied so collisions
    are impossible at the call site.
    """

    fn = agg.function
    if fn != "count_all" and not field_sql:
        raise UQLError(
            INVALID_AGGREGATION,
            f"Aggregation '{fn}' on alias '{agg.alias}' requires a field",
            f"Add a 'field' to the '{agg.alias}' aggregation, "
            "or use 'count_all' if you want a row count.",
        )
    if fn in _THRESHOLD_FUNCTIONS and agg.threshold is None:
        raise UQLError(
            INVALID_AGGREGATION,
            f"Aggregation '{fn}' on alias '{agg.alias}' requires 'threshold'",
            f"Add a numeric 'threshold' to the '{agg.alias}' aggregation "
            f"(required for {sorted(_THRESHOLD_FUNCTIONS)}).",
        )
    builder = _BUILDERS[fn]
    return builder(field_sql or "", agg, param_key)
