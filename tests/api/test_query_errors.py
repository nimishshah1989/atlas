"""Integration tests for §20.5 error envelope (V2-UQL-AGG-23).

Hits the live backend on ``http://localhost:8010`` and walks every
exception path that ``backend.routes.errors.uql_error_handler`` should
serialize into the §20.5 envelope:

    {"error": {"code", "message", "module", "severity", "timestamp", "suggestion"}}

The point of this file is **not** to re-prove the unit-level branch
coverage in ``tests/unit/test_uql_errors.py`` — it is to assert that:

* every UQL-side rejection actually surfaces over HTTP as a structured
  envelope (not a 5xx, not bare text),
* every envelope validates against
  ``specs/004-uql-aggregations/contracts/error_envelope.schema.json`` —
  every field present, ``module == "query_engine"``, ``timestamp`` a
  parseable date-time, ``code`` from the locked enum,
* the envelope's ``code`` matches the specific UQL taxonomy entry the
  request was meant to trip,
* HTTP status mirrors the per-code default in
  ``backend.services.uql.errors._DEFAULT_HTTP_STATUS``.

Skipped automatically if the backend is unreachable so the file is safe
inside the local pytest sweep without a live service.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import pytest

from backend.services.uql.errors import ERROR_CODES

BASE_URL = "http://localhost:8010"
QUERY_PATH = "/api/v1/query"
TEMPLATE_PATH = "/api/v1/query/template"

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "004-uql-aggregations"
    / "contracts"
    / "error_envelope.schema.json"
)


@pytest.fixture(scope="module")
def error_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    try:
        probe = httpx.get(f"{BASE_URL}/api/v1/health", timeout=2.0)
        probe.raise_for_status()
    except (httpx.HTTPError, httpx.RequestError) as exc:
        pytest.skip(f"backend not reachable at {BASE_URL}: {exc}")
    return httpx.Client(base_url=BASE_URL, timeout=10.0)


def _assert_envelope(
    resp: httpx.Response,
    schema: dict[str, Any],
    *,
    expect_code: str,
    expect_status: int,
) -> dict[str, Any]:
    """Assert the response is a valid §20.5 envelope with the expected code.

    Validates against the canonical JSON Schema (single source of truth
    for the envelope shape), then pins the dynamic fields:

    * ``code`` must equal ``expect_code`` (so we know the right exception
      path actually fired),
    * ``http_status`` must match the per-code default (so the handler is
      not silently rewriting it),
    * ``timestamp`` must round-trip through ``datetime.fromisoformat``
      (the schema only checks shape; we want a real parseable value).
    """

    assert resp.status_code == expect_status, (
        f"want HTTP {expect_status} for code {expect_code}, got {resp.status_code}: {resp.text}"
    )

    body = resp.json()
    jsonschema.validate(instance=body, schema=schema)

    err = body["error"]
    assert err["code"] == expect_code, f"want envelope code {expect_code!r}, got {err['code']!r}"
    assert err["code"] in ERROR_CODES, f"envelope code {err['code']!r} not in ERROR_CODES taxonomy"
    assert err["module"] == "query_engine"
    assert err["severity"] in ("error", "warning")
    # round-trip the timestamp — schema's "format: date-time" is advisory
    # in draft 2020-12, so we verify it explicitly.
    parsed = datetime.fromisoformat(err["timestamp"])
    assert parsed.tzinfo is not None, "timestamp must be tz-aware"
    return err


# ---------------------------------------------------------------------------
# Engine-layer codes — these reach the engine *past* Pydantic and must
# surface as §20.5 envelopes, not 422 Pydantic rejections.
# ---------------------------------------------------------------------------


def test_invalid_filter_unknown_field(client: httpx.Client, error_schema: dict[str, Any]) -> None:
    """Filtering on a column the entity registry does not know → INVALID_FILTER."""
    resp = client.post(
        QUERY_PATH,
        json={
            "entity_type": "equity",
            "fields": ["symbol"],
            "filters": [{"field": "definitely_not_a_column", "op": "=", "value": 1}],
            "limit": 10,
        },
    )
    _assert_envelope(resp, error_schema, expect_code="INVALID_FILTER", expect_status=400)


def test_invalid_sort_unknown_field(client: httpx.Client, error_schema: dict[str, Any]) -> None:
    """Sorting on a column the entity registry does not know → INVALID_SORT."""
    resp = client.post(
        QUERY_PATH,
        json={
            "entity_type": "equity",
            "fields": ["symbol"],
            "sort": [{"field": "not_a_column", "direction": "asc"}],
            "limit": 10,
        },
    )
    _assert_envelope(resp, error_schema, expect_code="INVALID_SORT", expect_status=400)


def test_invalid_aggregation_non_aggregatable_field(
    client: httpx.Client, error_schema: dict[str, Any]
) -> None:
    """Aggregating on a non-aggregatable column → INVALID_AGGREGATION."""
    resp = client.post(
        QUERY_PATH,
        json={
            "entity_type": "equity",
            "group_by": ["sector"],
            "aggregations": [{"function": "avg", "field": "symbol", "alias": "avg_symbol"}],
        },
    )
    _assert_envelope(resp, error_schema, expect_code="INVALID_AGGREGATION", expect_status=400)


# ---------------------------------------------------------------------------
# Template codes — both routes through /api/v1/query/template.
# ---------------------------------------------------------------------------


def test_template_not_found(client: httpx.Client, error_schema: dict[str, Any]) -> None:
    """Unknown template name → TEMPLATE_NOT_FOUND with HTTP 404."""
    resp = client.post(
        TEMPLATE_PATH,
        json={"template": "nope_not_a_template", "params": {}},
    )
    _assert_envelope(resp, error_schema, expect_code="TEMPLATE_NOT_FOUND", expect_status=404)


def test_template_param_missing(client: httpx.Client, error_schema: dict[str, Any]) -> None:
    """Calling a template that requires params with an empty body → TEMPLATE_PARAM_MISSING."""
    from backend.services.uql.errors import UQLError
    from backend.services.uql.templates import REGISTRY as TEMPLATE_REGISTRY

    target_name: str | None = None
    for name in TEMPLATE_REGISTRY:
        try:
            TEMPLATE_REGISTRY[name]({})
        except UQLError:
            target_name = name
            break

    if target_name is None:
        pytest.skip("no template in REGISTRY requires params; nothing to exercise")

    resp = client.post(TEMPLATE_PATH, json={"template": target_name, "params": {}})
    _assert_envelope(resp, error_schema, expect_code="TEMPLATE_PARAM_MISSING", expect_status=400)


# ---------------------------------------------------------------------------
# Schema-conformance sanity: every §20.5 response we touch must validate.
# This is an explicit punch-list item ("jsonschema validation passes on
# every response") — ``_assert_envelope`` already runs jsonschema.validate
# on each response above, but we repeat the assertion here as a single
# top-level check that exercises the full taxonomy in one go via direct
# envelope-builder construction. This guards against the case where the
# handler's output drifts from the schema enum.
# ---------------------------------------------------------------------------


def test_every_taxonomy_code_validates_against_schema(
    error_schema: dict[str, Any],
) -> None:
    """Construct an envelope per code and validate each against the schema.

    The handler builds envelopes via ``build_error_envelope``; if a new
    code lands in the taxonomy without being added to the schema enum,
    this test catches it before a live request ever returns 5xx.
    """
    from backend.routes.errors import build_error_envelope

    for code in sorted(ERROR_CODES):
        envelope = build_error_envelope(
            code=code,
            message=f"synthetic message for {code}",
            suggestion=f"synthetic suggestion for {code}",
        )
        jsonschema.validate(instance=envelope, schema=error_schema)
        assert envelope["error"]["code"] == code
        assert envelope["error"]["module"] == "query_engine"
