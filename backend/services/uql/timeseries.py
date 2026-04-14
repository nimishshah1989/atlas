"""UQL timeseries optimizer — single-entity, daily-granularity slices.

Exposes :func:`translate_timeseries` which compiles a ``mode='timeseries'``
:class:`backend.models.schemas.UQLRequest` into a parameterised
:class:`backend.services.uql.optimizer.SQLPlan` of the shape::

    SELECT <fields> FROM <entity> WHERE <pk> = :pk
      AND <date> BETWEEN :_from AND :_to
      ORDER BY <date> ASC LIMIT :_limit OFFSET :_offset

Wired in V2-UQL-AGG-10 per ``specs/004-uql-aggregations/tasks.md`` (T017).

Three invariants enforced here, each surfaced via
:class:`~backend.services.uql.errors.UQLError` so the FastAPI handler can
shape the §20.5 envelope:

* ``granularity`` must be ``"daily"`` (FR-019). Anything else →
  ``INVALID_GRANULARITY``.
* The request must carry exactly one filter, and that filter must
  resolve to the entity's primary-key column (FR-020). Otherwise →
  ``INVALID_FILTER`` with a single, actionable suggestion.
* The entity must expose a :class:`~backend.services.uql.registry.FieldType.DATE`
  column to slice over. Aggregation-only or non-temporal entities (e.g.
  ``sector``) reject timeseries with ``INVALID_MODE``.

Every literal that originates in the request body — the primary-key
filter value, the ``time_range`` bounds, the limit/offset — is bound via
a named parameter. Nothing is interpolated into the SQL text, so the
plan is safe to hand to SQLAlchemy ``text()`` without further escaping.
"""

from __future__ import annotations

from backend.models.schemas import UQLOperator, UQLRequest
from backend.services.uql.errors import (
    INVALID_FILTER,
    INVALID_GRANULARITY,
    INVALID_MODE,
    UQLError,
)
from backend.services.uql.optimizer import SQLPlan, _resolve_field
from backend.services.uql.registry import EntityDef, FieldSpec, FieldType


def _timeseries_from_clause(entity_def: EntityDef) -> str:
    """Build the FROM clause for timeseries mode.

    Uses ``entity_def.timeseries_joins`` when set so entities like equity
    — whose snapshot joins pin each timeseries table to its latest
    partition — can expose an unpinned variant for time-range slicing.
    Falls back to the standard joins for entities with a single mode.
    """

    joins = entity_def.timeseries_joins or entity_def.joins
    parts = [f"{entity_def.base_table} {entity_def.base_alias}"]
    for j in joins:
        parts.append(f"LEFT JOIN {j.table} {j.alias} ON {j.on}")
    return " ".join(parts)


__all__ = ["translate_timeseries"]


def _date_field(entity_def: EntityDef) -> FieldSpec:
    """Return the entity's date column, or raise ``INVALID_MODE``.

    The first :class:`FieldType.DATE` field on the entity is treated as
    the timeseries axis. Entities with no date column (sector, equity in
    the current registry) cannot be sliced over time and must be
    rejected here rather than producing nonsense SQL.
    """

    for spec in entity_def.fields.values():
        if spec.type is FieldType.DATE:
            return spec
    raise UQLError(
        INVALID_MODE,
        f"Entity '{entity_def.name}' does not expose a date column for timeseries",
        "Pick an entity_type whose registry definition includes a DATE field.",
    )


def _single_pk_filter_value(request: UQLRequest, entity_def: EntityDef) -> object:
    """Extract the single primary-key filter value or raise ``INVALID_FILTER``.

    Timeseries is single-entity by contract: the only filter the
    optimizer accepts is an equality on the entity's primary key. This
    keeps result-set sizes proportional to ``time_range`` width, never
    to the entity row count.
    """

    if len(request.filters) != 1:
        raise UQLError(
            INVALID_FILTER,
            f"timeseries requires exactly one filter, got {len(request.filters)}",
            f"Pass a single equality filter on '{entity_def.primary_key}'.",
        )
    flt = request.filters[0]
    spec = _resolve_field(entity_def, flt.field)
    if spec.name != entity_def.primary_key:
        raise UQLError(
            INVALID_FILTER,
            f"timeseries filter '{flt.field}' must target primary key '{entity_def.primary_key}'",
            f"Use op='eq' against '{entity_def.primary_key}'.",
        )
    if flt.op is not UQLOperator.EQ:
        raise UQLError(
            INVALID_FILTER,
            f"timeseries primary-key filter must use op='eq', got '{flt.op.value}'",
            "Equality is the only operator allowed on the timeseries axis filter.",
        )
    return flt.value


def translate_timeseries(request: UQLRequest, entity_def: EntityDef) -> SQLPlan:
    """Compile a ``mode='timeseries'`` :class:`UQLRequest` into a :class:`SQLPlan`.

    The caller (engine dispatcher) is responsible for routing here only
    when ``request.mode == 'timeseries'`` and ``time_range`` is set —
    Pydantic enforces both at the schema layer. We re-check the
    granularity at runtime because the literal can still be widened by
    a future schema bump and the SQL we emit is daily-only.
    """

    if request.granularity != "daily":
        raise UQLError(
            INVALID_GRANULARITY,
            f"granularity '{request.granularity}' is not supported",
            "Only granularity='daily' is supported in V2.",
        )
    if request.time_range is None:
        # Defensive: schema validator already enforces this for timeseries mode.
        raise UQLError(
            INVALID_FILTER,
            "timeseries mode requires 'time_range'",
            "Pass {'from': <date>, 'to': <date>} under 'time_range'.",
        )
    if not request.fields:
        raise UQLError(
            INVALID_FILTER,
            "timeseries mode requires explicit 'fields'",
            "List the columns you need under 'fields' — UQL never emits SELECT *.",
        )

    date_spec = _date_field(entity_def)
    pk_value = _single_pk_filter_value(request, entity_def)
    pk_spec = _resolve_field(entity_def, entity_def.primary_key)

    select_parts: list[str] = []
    for name in request.fields:
        spec = _resolve_field(entity_def, name)
        select_parts.append(f"{spec.sql} AS {name}")

    from_sql = _timeseries_from_clause(entity_def)
    sql = (
        f"SELECT {', '.join(select_parts)} FROM {from_sql}"
        f" WHERE {pk_spec.sql} = :pk"
        f" AND {date_spec.sql} BETWEEN :_from AND :_to"
        f" ORDER BY {date_spec.sql} ASC"
        f" LIMIT :_limit OFFSET :_offset"
    )

    params: dict[str, object] = {
        "pk": pk_value,
        "_from": request.time_range.from_,
        "_to": request.time_range.to,
        "_limit": request.limit,
        "_offset": request.offset,
    }
    return SQLPlan(sql=sql, params=params)
