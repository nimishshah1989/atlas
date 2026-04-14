"""UQL optimizer — translates a validated ``UQLRequest`` into a SQL plan.

Houses :func:`translate_snapshot` and :func:`translate_aggregation`. Both
look up entity metadata from ``registry.REGISTRY`` and emit the projection,
joins, WHERE, GROUP BY, ORDER BY, and LIMIT/OFFSET fragments. Wired in
V2-UQL-AGG-9 per ``specs/004-uql-aggregations/tasks.md`` (T012 + T013).

Defines :class:`SQLPlan`, the value object the optimizer produces and
``JIPDataService.execute_sql_plan`` consumes. The plan carries the main
data SQL plus an optional count SQL so the executor can return
``(rows, total_count)`` in a single 2-second-bounded transaction.

Every literal that originates in user input is bound via a named
parameter (``:name``) — never string-interpolated — so the executor hands
the whole plan to SQLAlchemy ``text()`` cleanly and there is no SQL
injection surface even when the field comes from a JSON request body.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.models.schemas import (
    UQLFilter,
    UQLOperator,
    UQLRequest,
    UQLSort,
    SortDirection,
)
from backend.services.uql.aggregations import build_aggregation
from backend.services.uql.errors import (
    INVALID_AGGREGATION,
    INVALID_FILTER,
    INVALID_SORT,
    UQLError,
)
from backend.services.uql.registry import EntityDef, FieldSpec

__all__ = ["SQLPlan", "translate_snapshot", "translate_aggregation"]


@dataclass(frozen=True)
class SQLPlan:
    """Compiled SQL plan handed from the optimizer to the executor.

    ``sql`` is the data query, ``params`` its bound parameters. When
    ``count_sql`` is provided the executor runs it before the data query
    inside the same 2-second transaction to obtain the total row count;
    otherwise the executor reports ``len(rows)`` as the total.
    """

    sql: str
    params: dict[str, Any] = field(default_factory=dict)
    count_sql: str | None = None
    count_params: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Field resolution helpers
# ---------------------------------------------------------------------------


def _resolve_field(entity_def: EntityDef, name: str) -> FieldSpec:
    spec = entity_def.fields.get(name)
    if spec is None:
        raise UQLError(
            INVALID_FILTER,
            f"Unknown field '{name}' for entity '{entity_def.name}'",
            f"Use one of: {sorted(entity_def.field_names())}.",
        )
    return spec


def _from_clause(entity_def: EntityDef) -> str:
    parts = [f"{entity_def.base_table} {entity_def.base_alias}"]
    for j in entity_def.joins:
        parts.append(f"LEFT JOIN {j.table} {j.alias} ON {j.on}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# WHERE builder — every value bound as a named parameter, never interpolated
# ---------------------------------------------------------------------------


_SIMPLE_OPERATORS: dict[UQLOperator, str] = {
    UQLOperator.EQ: "=",
    UQLOperator.NEQ: "!=",
    UQLOperator.GT: ">",
    UQLOperator.GTE: ">=",
    UQLOperator.LT: "<",
    UQLOperator.LTE: "<=",
}


def _build_where(filters: list[UQLFilter], entity_def: EntityDef) -> tuple[str, dict[str, Any]]:
    parts: list[str] = []
    params: dict[str, Any] = {}

    for idx, flt in enumerate(filters):
        spec = _resolve_field(entity_def, flt.field)
        if not spec.filterable:
            raise UQLError(
                INVALID_FILTER,
                f"Field '{flt.field}' is not filterable",
                f"Pick a filterable field from: {sorted(entity_def.field_names())}.",
            )
        col = spec.sql
        key = f"f{idx}"
        op = flt.op

        if op is UQLOperator.IS_NULL:
            parts.append(f"{col} IS NULL")
        elif op is UQLOperator.IS_NOT_NULL:
            parts.append(f"{col} IS NOT NULL")
        elif op is UQLOperator.BETWEEN:
            if not isinstance(flt.value, (list, tuple)) or len(flt.value) != 2:
                raise UQLError(
                    INVALID_FILTER,
                    f"Filter '{flt.field}' with op 'between' requires [low, high]",
                    "Pass a 2-element list under 'value' for between filters.",
                )
            parts.append(f"{col} BETWEEN :{key}_lo AND :{key}_hi")
            params[f"{key}_lo"] = flt.value[0]
            params[f"{key}_hi"] = flt.value[1]
        elif op in (UQLOperator.IN, UQLOperator.NOT_IN):
            if not isinstance(flt.value, (list, tuple)) or len(flt.value) == 0:
                raise UQLError(
                    INVALID_FILTER,
                    f"Filter '{flt.field}' with op '{op.value}' requires a non-empty list",
                    "Pass a non-empty list under 'value' for in/not_in filters.",
                )
            placeholders: list[str] = []
            for j, v in enumerate(flt.value):
                pk = f"{key}_{j}"
                placeholders.append(f":{pk}")
                params[pk] = v
            sql_op = "IN" if op is UQLOperator.IN else "NOT IN"
            parts.append(f"{col} {sql_op} ({', '.join(placeholders)})")
        elif op is UQLOperator.CONTAINS:
            parts.append(f"{col} ILIKE :{key}")
            params[key] = f"%{flt.value}%"
        else:
            sql_op = _SIMPLE_OPERATORS[op]
            parts.append(f"{col} {sql_op} :{key}")
            params[key] = flt.value

    return " AND ".join(parts), params


# ---------------------------------------------------------------------------
# Snapshot translation
# ---------------------------------------------------------------------------


def _snapshot_order(sort: list[UQLSort], entity_def: EntityDef) -> str:
    if not sort:
        return ""
    parts: list[str] = []
    for s in sort:
        spec = entity_def.fields.get(s.field)
        if spec is None:
            raise UQLError(
                INVALID_SORT,
                f"Sort field '{s.field}' is not a known column on '{entity_def.name}'",
                f"Sort by one of: {sorted(entity_def.field_names())}.",
            )
        if not spec.sortable:
            raise UQLError(
                INVALID_SORT,
                f"Sort field '{s.field}' is not sortable",
                "Pick a sortable column from the entity registry.",
            )
        direction = "ASC" if s.direction is SortDirection.ASC else "DESC"
        parts.append(f"{spec.sql} {direction}")
    return ", ".join(parts)


def translate_snapshot(request: UQLRequest, entity_def: EntityDef) -> SQLPlan:
    """Compile a snapshot-mode :class:`UQLRequest` into a :class:`SQLPlan`.

    The projection is driven by ``request.fields`` (always required in
    snapshot mode — enforced upstream by ``safety.validate_limits``). The
    order of the projection matches the order given by the caller so the
    response payload is stable. ``ORDER BY`` resolves against the entity
    field whitelist and rejects anything else with ``INVALID_SORT``.
    """

    if not request.fields:
        # safety.validate_limits should have caught this already; defensive.
        raise UQLError(
            INVALID_FILTER,
            "snapshot mode requires 'fields'",
            "List the columns you need under 'fields' — UQL never emits SELECT *.",
        )

    select_parts: list[str] = []
    for name in request.fields:
        spec = _resolve_field(entity_def, name)
        select_parts.append(f"{spec.sql} AS {name}")

    where_sql, params = _build_where(request.filters, entity_def)
    order_sql = _snapshot_order(request.sort, entity_def)
    from_sql = _from_clause(entity_def)

    sql = f"SELECT {', '.join(select_parts)} FROM {from_sql}"
    count_sql = f"SELECT count(*) FROM {from_sql}"
    if where_sql:
        sql += f" WHERE {where_sql}"
        count_sql += f" WHERE {where_sql}"
    if order_sql:
        sql += f" ORDER BY {order_sql}"

    sql += " LIMIT :_limit OFFSET :_offset"
    data_params = dict(params)
    data_params["_limit"] = request.limit
    data_params["_offset"] = request.offset

    return SQLPlan(
        sql=sql,
        params=data_params,
        count_sql=count_sql,
        count_params=dict(params),
    )


# ---------------------------------------------------------------------------
# Aggregation translation
# ---------------------------------------------------------------------------


def _resolve_groupable(entity_def: EntityDef, name: str) -> FieldSpec:
    spec = _resolve_field(entity_def, name)
    if not spec.groupable:
        raise UQLError(
            INVALID_FILTER,
            f"Field '{name}' is not groupable on '{entity_def.name}'",
            "Pick a groupable column from the entity registry.",
        )
    return spec


def _aggregation_order(
    sort: list[UQLSort],
    group_specs: list[tuple[str, FieldSpec]],
    aggregation_aliases: set[str],
) -> str:
    if not sort:
        return ""
    group_lookup = {name: spec for name, spec in group_specs}
    parts: list[str] = []
    for s in sort:
        direction = "ASC" if s.direction is SortDirection.ASC else "DESC"
        if s.field in aggregation_aliases:
            parts.append(f"{s.field} {direction}")
            continue
        if s.field in group_lookup:
            parts.append(f"{group_lookup[s.field].sql} {direction}")
            continue
        raise UQLError(
            INVALID_SORT,
            f"Sort field '{s.field}' must be a group_by column or aggregation alias",
            f"Sort by one of: group_by={sorted(group_lookup)} "
            f"or aliases={sorted(aggregation_aliases)}.",
        )
    return ", ".join(parts)


def translate_aggregation(request: UQLRequest, entity_def: EntityDef) -> SQLPlan:
    """Compile a ``group_by`` :class:`UQLRequest` into a :class:`SQLPlan`.

    Resolves every ``group_by`` entry against the entity registry,
    delegates each aggregation to :func:`build_aggregation`, and
    enforces that ``ORDER BY`` only references group_by columns or
    aggregation aliases (FR-016) — anything else raises
    ``INVALID_SORT`` so the caller sees the §20.5 envelope.
    """

    if not request.group_by:
        raise UQLError(
            INVALID_AGGREGATION,
            "translate_aggregation called without 'group_by'",
            "Set 'group_by' on the request or route through translate_snapshot.",
        )
    if not request.aggregations:
        raise UQLError(
            INVALID_AGGREGATION,
            "'aggregations' is required when 'group_by' is present",
            "Add at least one aggregation to the request.",
        )

    group_specs: list[tuple[str, FieldSpec]] = [
        (name, _resolve_groupable(entity_def, name)) for name in request.group_by
    ]

    select_parts: list[str] = [f"{spec.sql} AS {name}" for name, spec in group_specs]

    where_sql, where_params = _build_where(request.filters, entity_def)
    params: dict[str, Any] = dict(where_params)

    aggregation_aliases: set[str] = set()
    for idx, agg in enumerate(request.aggregations):
        field_sql: str | None = None
        if agg.field is not None:
            spec = _resolve_field(entity_def, agg.field)
            if not spec.aggregatable:
                raise UQLError(
                    INVALID_AGGREGATION,
                    f"Field '{agg.field}' is not aggregatable on '{entity_def.name}'",
                    "Pick an aggregatable column from the entity registry.",
                )
            field_sql = spec.sql
        param_key = f"thr_{idx}"
        sql_expr, agg_params = build_aggregation(agg, field_sql, param_key=param_key)
        select_parts.append(f"{sql_expr} AS {agg.alias}")
        params.update(agg_params)
        aggregation_aliases.add(agg.alias)

    from_sql = _from_clause(entity_def)
    sql = f"SELECT {', '.join(select_parts)} FROM {from_sql}"
    if where_sql:
        sql += f" WHERE {where_sql}"
    if group_specs:
        sql += " GROUP BY " + ", ".join(spec.sql for _, spec in group_specs)

    order_sql = _aggregation_order(request.sort, group_specs, aggregation_aliases)
    if order_sql:
        sql += f" ORDER BY {order_sql}"

    sql += " LIMIT :_limit OFFSET :_offset"
    params["_limit"] = request.limit
    params["_offset"] = request.offset

    return SQLPlan(sql=sql, params=params)
