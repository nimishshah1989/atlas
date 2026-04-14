"""Unit tests for the §20.5 error envelope (V2-UQL-AGG-3).

Asserts that:
  1. ``UQLError`` validates code / message / suggestion correctly.
  2. ``build_error_envelope`` emits a payload that matches
     ``specs/004-uql-aggregations/contracts/error_envelope.schema.json``
     for every code in the taxonomy.
  3. ``uql_error_handler`` returns a JSONResponse with the right HTTP
     status and a body that schema-validates.
  4. The handler is wired into the FastAPI app at module load.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from starlette.requests import Request

from backend.main import app
from backend.routes.errors import build_error_envelope, uql_error_handler
from backend.services.uql.errors import (
    ERROR_CODES,
    QUERY_TIMEOUT,
    TEMPLATE_NOT_FOUND,
    UQLError,
)

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "004-uql-aggregations"
    / "contracts"
    / "error_envelope.schema.json"
)


@pytest.fixture(scope="module")
def envelope_validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


# --- UQLError -------------------------------------------------------------


def test_uqlerror_default_http_status_400() -> None:
    err = UQLError("INVALID_FILTER", "bad field x", "use field y")
    assert err.http_status == 400
    assert err.code == "INVALID_FILTER"
    assert err.severity == "error"


def test_uqlerror_query_timeout_defaults_to_504() -> None:
    err = UQLError(QUERY_TIMEOUT, "exceeded 2s budget", "narrow filters")
    assert err.http_status == 504


def test_uqlerror_template_not_found_defaults_to_404() -> None:
    err = UQLError(TEMPLATE_NOT_FOUND, "no such template", "valid: a, b, c")
    assert err.http_status == 404


def test_uqlerror_explicit_http_status_overrides_default() -> None:
    err = UQLError("INVALID_FILTER", "x", "y", http_status=422)
    assert err.http_status == 422


def test_uqlerror_unknown_code_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown UQL error code"):
        UQLError("NOT_A_REAL_CODE", "msg", "suggestion")


def test_uqlerror_blank_message_rejected() -> None:
    with pytest.raises(ValueError, match="message must be non-empty"):
        UQLError("INVALID_FILTER", "", "suggestion")


def test_uqlerror_blank_suggestion_rejected() -> None:
    with pytest.raises(ValueError, match="suggestion must be non-empty"):
        UQLError("INVALID_FILTER", "msg", "")


def test_uqlerror_bad_severity_rejected() -> None:
    with pytest.raises(ValueError, match="severity"):
        UQLError("INVALID_FILTER", "msg", "sugg", severity="critical")


# --- build_error_envelope -------------------------------------------------


@pytest.mark.parametrize("code", sorted(ERROR_CODES))
def test_envelope_validates_for_every_code(
    envelope_validator: Draft202012Validator, code: str
) -> None:
    payload = build_error_envelope(code, f"{code} happened", "try fixing it")
    envelope_validator.validate(payload)
    assert payload["error"]["code"] == code
    assert payload["error"]["module"] == "query_engine"
    assert payload["error"]["severity"] == "error"


def test_envelope_timestamp_is_ist_offset(envelope_validator: Draft202012Validator) -> None:
    fixed = datetime(2026, 4, 14, 4, 45, 0, tzinfo=timezone.utc)
    payload = build_error_envelope("INVALID_FILTER", "x", "y", now=fixed)
    envelope_validator.validate(payload)
    ts = payload["error"]["timestamp"]
    # 04:45 UTC + 5:30 = 10:15 IST
    assert ts == "2026-04-14T10:15:00+05:30"
    # Sanity: matches the ISO 8601 date-time pattern with explicit offset.
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30$", ts)


def test_envelope_rejects_extra_keys_in_schema(
    envelope_validator: Draft202012Validator,
) -> None:
    payload = build_error_envelope("INVALID_FILTER", "x", "y")
    payload["error"]["unexpected"] = "nope"
    with pytest.raises(Exception):
        envelope_validator.validate(payload)


def test_envelope_severity_warning_validates(
    envelope_validator: Draft202012Validator,
) -> None:
    payload = build_error_envelope("INVALID_FILTER", "x", "y", severity="warning")
    envelope_validator.validate(payload)
    assert payload["error"]["severity"] == "warning"


# --- error code <-> JSON Schema enum sync ---------------------------------


def test_error_codes_match_schema_enum() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text())
    enum = set(schema["properties"]["error"]["properties"]["code"]["enum"])
    assert enum == set(ERROR_CODES), (
        "errors.py taxonomy and error_envelope.schema.json enum must stay in sync"
    )


# --- FastAPI handler ------------------------------------------------------


def _make_request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/query",
        "raw_path": b"/api/v1/query",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
        "root_path": "",
        "app": app,
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_handler_serializes_envelope_with_correct_status(
    envelope_validator: Draft202012Validator,
) -> None:
    err = UQLError(QUERY_TIMEOUT, "took too long", "narrow date range")
    response = await uql_error_handler(_make_request(), err)
    assert response.status_code == 504
    body = json.loads(response.body)
    envelope_validator.validate(body)
    assert body["error"]["code"] == QUERY_TIMEOUT
    assert body["error"]["module"] == "query_engine"
    assert body["error"]["suggestion"] == "narrow date range"


def test_handler_registered_on_app() -> None:
    assert UQLError in app.exception_handlers
    assert app.exception_handlers[UQLError] is uql_error_handler
