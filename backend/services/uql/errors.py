"""UQL §20.5 error envelope — exception class + code taxonomy.

Houses the ``UQLError`` exception (carrying ``code``, ``message``,
``suggestion``, ``http_status``) and the full code taxonomy
(``INVALID_ENTITY_TYPE`` … ``ENTITY_PARTITION_MISSING``). The matching
FastAPI exception handler lives in ``backend/routes/errors.py``. Wired in
V2-UQL-AGG-3 per ``specs/004-uql-aggregations/tasks.md``.

The error code set is the canonical source — it must stay in lockstep
with ``specs/004-uql-aggregations/contracts/error_envelope.schema.json``
(the JSON Schema enum). ``test_uql_errors.py`` asserts both sides match.
"""

from __future__ import annotations

from typing import Final

# §20.5 code taxonomy. Mirrors the enum in
# specs/004-uql-aggregations/contracts/error_envelope.schema.json.
INVALID_ENTITY_TYPE: Final = "INVALID_ENTITY_TYPE"
INVALID_FILTER: Final = "INVALID_FILTER"
INVALID_AGGREGATION: Final = "INVALID_AGGREGATION"
INVALID_SORT: Final = "INVALID_SORT"
INVALID_GRANULARITY: Final = "INVALID_GRANULARITY"
INVALID_MODE: Final = "INVALID_MODE"
LIMIT_EXCEEDED: Final = "LIMIT_EXCEEDED"
FIELDS_REQUIRED: Final = "FIELDS_REQUIRED"
FULL_SCAN_REJECTED: Final = "FULL_SCAN_REJECTED"
QUERY_TIMEOUT: Final = "QUERY_TIMEOUT"
TEMPLATE_NOT_FOUND: Final = "TEMPLATE_NOT_FOUND"
TEMPLATE_PARAM_MISSING: Final = "TEMPLATE_PARAM_MISSING"
INCLUDE_NOT_AVAILABLE: Final = "INCLUDE_NOT_AVAILABLE"
ENTITY_PARTITION_MISSING: Final = "ENTITY_PARTITION_MISSING"

ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        INVALID_ENTITY_TYPE,
        INVALID_FILTER,
        INVALID_AGGREGATION,
        INVALID_SORT,
        INVALID_GRANULARITY,
        INVALID_MODE,
        LIMIT_EXCEEDED,
        FIELDS_REQUIRED,
        FULL_SCAN_REJECTED,
        QUERY_TIMEOUT,
        TEMPLATE_NOT_FOUND,
        TEMPLATE_PARAM_MISSING,
        INCLUDE_NOT_AVAILABLE,
        ENTITY_PARTITION_MISSING,
    }
)

# Default HTTP mapping per §20.5 — overridable per-raise via http_status=.
_DEFAULT_HTTP_STATUS: Final[dict[str, int]] = {
    INVALID_ENTITY_TYPE: 400,
    INVALID_FILTER: 400,
    INVALID_AGGREGATION: 400,
    INVALID_SORT: 400,
    INVALID_GRANULARITY: 400,
    INVALID_MODE: 400,
    LIMIT_EXCEEDED: 400,
    FIELDS_REQUIRED: 400,
    FULL_SCAN_REJECTED: 400,
    QUERY_TIMEOUT: 504,
    TEMPLATE_NOT_FOUND: 404,
    TEMPLATE_PARAM_MISSING: 400,
    INCLUDE_NOT_AVAILABLE: 400,
    ENTITY_PARTITION_MISSING: 503,
}


class UQLError(Exception):
    """Structured error raised anywhere in the UQL pipeline.

    Caught by ``backend.routes.errors.uql_error_handler`` and serialized
    into the §20.5 envelope. ``message`` and ``suggestion`` must both be
    non-empty — the schema rejects blank fields and the handler will not
    paper over a missing suggestion (errors must be helpful, per §20.5).
    """

    def __init__(
        self,
        code: str,
        message: str,
        suggestion: str,
        *,
        http_status: int | None = None,
        severity: str = "error",
    ) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"Unknown UQL error code: {code!r}")
        if not message:
            raise ValueError("UQLError.message must be non-empty")
        if not suggestion:
            raise ValueError("UQLError.suggestion must be non-empty")
        if severity not in ("error", "warning"):
            raise ValueError(f"UQLError.severity must be error|warning, got {severity!r}")
        self.code = code
        self.message = message
        self.suggestion = suggestion
        self.http_status = http_status if http_status is not None else _DEFAULT_HTTP_STATUS[code]
        self.severity = severity
        super().__init__(f"{code}: {message}")


__all__ = [
    "ERROR_CODES",
    "UQLError",
    "INVALID_ENTITY_TYPE",
    "INVALID_FILTER",
    "INVALID_AGGREGATION",
    "INVALID_SORT",
    "INVALID_GRANULARITY",
    "INVALID_MODE",
    "LIMIT_EXCEEDED",
    "FIELDS_REQUIRED",
    "FULL_SCAN_REJECTED",
    "QUERY_TIMEOUT",
    "TEMPLATE_NOT_FOUND",
    "TEMPLATE_PARAM_MISSING",
    "INCLUDE_NOT_AVAILABLE",
    "ENTITY_PARTITION_MISSING",
]
