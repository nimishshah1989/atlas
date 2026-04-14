"""§20.5 error envelope factory + FastAPI exception handler.

Serializes ``UQLError`` (and unhandled fall-throughs raised from the UQL
service layer) into the structured envelope defined by
``specs/004-uql-aggregations/contracts/error_envelope.schema.json``:

    {"error": {"code", "message", "module", "severity", "timestamp", "suggestion"}}

The handler is registered in ``backend.main`` at app construction time.
``module`` is hard-coded to ``"query_engine"`` (schema ``const``) and
``timestamp`` is an IST (Asia/Kolkata, +05:30) ISO-8601 datetime so the
envelope round-trips through ``date-time`` validators unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.services.uql.errors import UQLError

_INVALID_REQUEST = "INVALID_REQUEST"

_IST = ZoneInfo("Asia/Kolkata")
_MODULE: str = "query_engine"

log = structlog.get_logger(__name__)


def build_error_envelope(
    code: str,
    message: str,
    suggestion: str,
    *,
    severity: str = "error",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a §20.5 envelope dict ready to JSON-encode.

    ``now`` is exposed for deterministic tests; production callers omit it
    and pick up the current IST timestamp.
    """
    ts = (now or datetime.now(timezone.utc)).astimezone(_IST).isoformat(timespec="seconds")
    return {
        "error": {
            "code": code,
            "message": message,
            "module": _MODULE,
            "severity": severity,
            "timestamp": ts,
            "suggestion": suggestion,
        }
    }


async def uql_error_handler(request: Request, exc: UQLError) -> JSONResponse:
    log.warning(
        "uql_error",
        code=exc.code,
        http_status=exc.http_status,
        path=request.url.path,
    )
    envelope = build_error_envelope(
        exc.code,
        exc.message,
        exc.suggestion,
        severity=exc.severity,
    )
    return JSONResponse(status_code=exc.http_status, content=envelope)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Shape Pydantic/FastAPI body-validation failures into the §20.5 envelope.

    FastAPI defaults to 422 with a ``{detail: [...]}`` shape; spec §20.5
    (and ``api-01-error-standard``) requires malformed queries to return
    400 with ``{error: {code, message, suggestion, ...}}`` so FMs and
    agents see a self-explaining failure instead of a bare validator dump.
    We lift the first validator message as ``message`` and the field path
    as the basis for ``suggestion``.
    """
    errors = exc.errors()
    first = errors[0] if errors else {}
    message = str(first.get("msg") or "Request body failed validation")
    loc_parts = [str(p) for p in first.get("loc", []) if p not in ("body",)]
    loc = ".".join(loc_parts) if loc_parts else "body"
    suggestion = (
        f"Fix '{loc}' in the request body and retry — see spec §17 (UQL) for the accepted shape."
    )
    log.warning(
        "uql_validation_error",
        path=request.url.path,
        loc=loc,
        message=message,
    )
    envelope = build_error_envelope(_INVALID_REQUEST, message, suggestion)
    return JSONResponse(status_code=400, content=envelope)


def register(app: FastAPI) -> None:
    """Register the §20.5 exception handlers on a FastAPI app."""
    app.add_exception_handler(UQLError, uql_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        validation_error_handler,  # type: ignore[arg-type]
    )


__all__ = [
    "build_error_envelope",
    "register",
    "uql_error_handler",
    "validation_error_handler",
]
