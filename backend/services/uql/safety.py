"""UQL §17.9 safety enforcement — limits, fields, full-scan rejection.

Two pure functions, both raise :class:`backend.services.uql.errors.UQLError`
on rejection so the engine dispatcher can let the FastAPI exception handler
shape the §20.5 envelope:

* :func:`validate_limits` enforces payload-shape ceilings (limit ≤ 500,
  filters ≤ 10, aggregations ≤ 8) and the snapshot-mode ``fields`` rule
  ("no SELECT *").
* :func:`validate_full_scan` rejects unindexed filters on entities whose
  ``row_count_estimate`` exceeds :data:`LARGE_ENTITY_THRESHOLD`.

These checks duplicate Pydantic ``UQLRequest`` validation on purpose: by
the time an engine call reaches us the request may have been built by an
internal helper (legacy adapter, template builder) that bypasses the
client-facing schema, and we still owe the §20.5 envelope shape.
"""

from __future__ import annotations

from backend.models.schemas import UQLRequest
from backend.services.uql import errors
from backend.services.uql.registry import EntityDef

# §17.9 ceilings — kept here so tests and engine share one source of truth.
MAX_LIMIT: int = 500
MAX_FILTERS: int = 10
MAX_AGGREGATIONS: int = 8
LARGE_ENTITY_THRESHOLD: int = 1_000_000

__all__ = [
    "MAX_LIMIT",
    "MAX_FILTERS",
    "MAX_AGGREGATIONS",
    "LARGE_ENTITY_THRESHOLD",
    "validate_limits",
    "validate_full_scan",
]


def validate_limits(request: UQLRequest) -> None:
    """Enforce §17.9 payload ceilings on a UQL request.

    Raises :class:`errors.UQLError` with one of ``LIMIT_EXCEEDED``,
    ``INVALID_FILTER`` (filter overflow), ``INVALID_AGGREGATION`` (agg
    overflow), or ``FIELDS_REQUIRED`` on the first violation seen.
    """

    if request.limit > MAX_LIMIT:
        raise errors.UQLError(
            errors.LIMIT_EXCEEDED,
            f"limit={request.limit} exceeds maximum {MAX_LIMIT}",
            f"Reduce 'limit' to {MAX_LIMIT} or below, or paginate via 'offset'.",
        )

    if len(request.filters) > MAX_FILTERS:
        raise errors.UQLError(
            errors.INVALID_FILTER,
            f"{len(request.filters)} filters supplied; maximum is {MAX_FILTERS}",
            f"Combine or drop filters so the request carries at most {MAX_FILTERS}.",
        )

    if len(request.aggregations) > MAX_AGGREGATIONS:
        raise errors.UQLError(
            errors.INVALID_AGGREGATION,
            f"{len(request.aggregations)} aggregations supplied; maximum is {MAX_AGGREGATIONS}",
            f"Split the request — at most {MAX_AGGREGATIONS} aggregations per call.",
        )

    if request.mode == "snapshot" and request.group_by is None and not request.fields:
        raise errors.UQLError(
            errors.FIELDS_REQUIRED,
            "'fields' is required for snapshot queries without group_by",
            "List the columns you need under 'fields' — UQL never emits SELECT *.",
        )


def _column_of(sql_expr: str) -> str:
    """Extract the bare column name from an ``alias.column`` SQL fragment."""

    return sql_expr.rsplit(".", 1)[-1]


def validate_full_scan(request: UQLRequest, entity_def: EntityDef) -> None:
    """Reject unindexed filters on entities larger than the threshold.

    Small entities (≤ :data:`LARGE_ENTITY_THRESHOLD` rows) are skipped
    entirely — full table scans there are cheap and safe.
    """

    if entity_def.row_count_estimate <= LARGE_ENTITY_THRESHOLD:
        return

    indexed_field_names = sorted(
        name
        for name, spec in entity_def.fields.items()
        if entity_def.is_indexed(_column_of(spec.sql))
    )

    for flt in request.filters:
        spec = entity_def.fields.get(flt.field)
        if spec is None:
            raise errors.UQLError(
                errors.INVALID_FILTER,
                f"Unknown field '{flt.field}' for entity '{entity_def.name}'",
                f"Use one of: {sorted(entity_def.field_names())}.",
            )
        column = _column_of(spec.sql)
        if not entity_def.is_indexed(column):
            raise errors.UQLError(
                errors.FULL_SCAN_REJECTED,
                f"Filter on '{flt.field}' would force a full scan of "
                f"{entity_def.base_table} (~{entity_def.row_count_estimate:,} rows)",
                f"Filter on an indexed column instead: {indexed_field_names}.",
            )
