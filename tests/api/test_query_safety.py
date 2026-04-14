"""Integration tests for `POST /api/v1/query` §17.9 safety enforcement (V2-UQL-AGG-22).

Hits the live backend on ``http://localhost:8010`` (the same target as
``tests/api/test_query_aggregations.py`` and ``test_query_multi_entity.py``)
and exercises every payload-shape ceiling that ``backend/services/uql/safety.py``
+ ``backend/models/uql.py::UQLRequest.validate_constraints`` are meant to
reject. The point of the file is not to re-prove the unit-level branch
coverage in ``tests/unit/test_uql_safety.py`` — it is to assert that:

* the rejection actually surfaces over HTTP (request never reaches the
  SQL builder, never returns a 5xx, never silently truncates),
* the rejection is *structured* — either the §20.5 ``UQLError`` envelope
  (400 with ``error.{code,message,suggestion}``) or a Pydantic
  ``RequestValidationError`` (422 with ``detail``) — but **never** an
  unstructured 5xx,
* the rejection arrives in well under the 2s §17.9 query-timeout budget
  (i.e. the safety check is pre-execution, not post-).

The ceiling values are pulled from
``backend.services.uql.safety`` so the test fails loudly if the limits
shift without the doc + spec being updated in lockstep.

Skipped automatically if the backend is unreachable so the file is safe
inside the local pytest sweep without a live service.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from backend.services.uql.safety import (
    LARGE_ENTITY_THRESHOLD,
    MAX_AGGREGATIONS,
    MAX_FILTERS,
    MAX_LIMIT,
)

BASE_URL = "http://localhost:8010"
QUERY_PATH = "/api/v1/query"

# §17.9 says rejection must arrive in well under the 2s query budget — these
# are pre-execution checks, so anything over a second smells like the request
# is reaching the database before being rejected.
SAFETY_REJECT_BUDGET_S: float = 1.5


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    try:
        probe = httpx.get(f"{BASE_URL}/api/v1/health", timeout=2.0)
        probe.raise_for_status()
    except (httpx.HTTPError, httpx.RequestError) as exc:
        pytest.skip(f"backend not reachable at {BASE_URL}: {exc}")
    return httpx.Client(base_url=BASE_URL, timeout=10.0)


def _post_timed(client: httpx.Client, body: dict[str, Any]) -> tuple[httpx.Response, float]:
    started = time.perf_counter()
    resp = client.post(QUERY_PATH, json=body)
    return resp, time.perf_counter() - started


def _assert_structured_rejection(
    resp: httpx.Response,
    elapsed: float,
    *,
    expect_uql_code: str | None = None,
    expect_pydantic_substring: str | None = None,
) -> None:
    """Assert one of the two legal rejection shapes for a §17.9 violation.

    Either:
    * 400 with §20.5 envelope: ``{"error": {"code", "message", "suggestion"}}``
      — and if ``expect_uql_code`` is provided, the envelope's code matches.
    * 422 with Pydantic envelope: ``{"detail": [...]}`` — and if
      ``expect_pydantic_substring`` is provided, it appears in at least one
      detail's message (case-insensitive).

    Anything else (5xx, 200, 4xx without an envelope) fails. Also asserts
    the rejection landed within the §17.9 pre-execution budget.
    """

    assert resp.status_code < 500, (
        f"safety violation produced a 5xx — pre-execution check did not fire: "
        f"{resp.status_code} {resp.text}"
    )
    assert elapsed < SAFETY_REJECT_BUDGET_S, (
        f"safety rejection took {elapsed:.2f}s (>{SAFETY_REJECT_BUDGET_S}s); "
        f"pre-execution checks must be fast"
    )

    body = resp.json()

    if resp.status_code == 400:
        assert "error" in body, f"§20.5 400 must carry an 'error' envelope: {body}"
        err = body["error"]
        assert err.get("code"), "§20.5 envelope missing 'code'"
        assert err.get("message"), "§20.5 envelope missing 'message'"
        assert err.get("suggestion"), "§20.5 envelope missing 'suggestion' (mandatory)"
        if expect_uql_code is not None:
            assert err["code"] == expect_uql_code, (
                f"want UQL code {expect_uql_code!r}, got {err['code']!r}"
            )
        return

    if resp.status_code == 422:
        assert "detail" in body, f"422 must carry a Pydantic 'detail' envelope: {body}"
        details = body["detail"]
        assert isinstance(details, list) and details, "422 detail must be a non-empty list"
        if expect_pydantic_substring is not None:
            joined = " ".join(str(d.get("msg", "")) for d in details).lower()
            assert expect_pydantic_substring.lower() in joined, (
                f"want substring {expect_pydantic_substring!r} in 422 detail, got {details}"
            )
        return

    pytest.fail(
        f"want a structured 400 (§20.5) or 422 (Pydantic) rejection, "
        f"got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# (a) limit > MAX_LIMIT → structured rejection
# ---------------------------------------------------------------------------


def test_oversize_limit_rejected(client: httpx.Client) -> None:
    resp, elapsed = _post_timed(
        client,
        {
            "entity_type": "equity",
            "fields": ["symbol"],
            "limit": MAX_LIMIT + 4500,  # 5000 by default
        },
    )
    _assert_structured_rejection(
        resp,
        elapsed,
        expect_uql_code="LIMIT_EXCEEDED",
        expect_pydantic_substring="less than or equal to 500",
    )


def test_max_limit_exactly_is_accepted(client: httpx.Client) -> None:
    """Boundary check — `limit == MAX_LIMIT` must NOT be rejected.

    Guards against an off-by-one in the ceiling check that would silently
    cap real workloads one row below the documented contract.
    """
    resp, _ = _post_timed(
        client,
        {
            "entity_type": "equity",
            "fields": ["symbol"],
            "limit": MAX_LIMIT,
        },
    )
    assert resp.status_code == 200, (
        f"limit={MAX_LIMIT} must be accepted (boundary), got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# (b) snapshot mode with no `fields` and no group_by → FIELDS_REQUIRED
# ---------------------------------------------------------------------------


def test_snapshot_without_fields_rejected(client: httpx.Client) -> None:
    resp, elapsed = _post_timed(
        client,
        {
            "entity_type": "equity",
            # mode defaults to snapshot, group_by absent, fields absent
        },
    )
    _assert_structured_rejection(
        resp,
        elapsed,
        expect_uql_code="FIELDS_REQUIRED",
        expect_pydantic_substring="'fields' is required",
    )


# ---------------------------------------------------------------------------
# (c) MAX_FILTERS + 1 filters → structured rejection
# ---------------------------------------------------------------------------


def test_too_many_filters_rejected(client: httpx.Client) -> None:
    filters = [{"field": "sector", "op": "=", "value": f"v{i}"} for i in range(MAX_FILTERS + 1)]
    resp, elapsed = _post_timed(
        client,
        {
            "entity_type": "equity",
            "fields": ["symbol"],
            "filters": filters,
        },
    )
    _assert_structured_rejection(
        resp,
        elapsed,
        expect_uql_code="INVALID_FILTER",
        expect_pydantic_substring=f"maximum {MAX_FILTERS} filters".lower().replace(
            "maximum 10 filters", "maximum 10 filters"
        ),
    )


# ---------------------------------------------------------------------------
# (d) MAX_AGGREGATIONS + 1 aggregations → structured rejection
# ---------------------------------------------------------------------------


def test_too_many_aggregations_rejected(client: httpx.Client) -> None:
    aggregations = [
        {"function": "count_all", "alias": f"a{i}"} for i in range(MAX_AGGREGATIONS + 1)
    ]
    resp, elapsed = _post_timed(
        client,
        {
            "entity_type": "equity",
            "group_by": ["sector"],
            "aggregations": aggregations,
        },
    )
    _assert_structured_rejection(
        resp,
        elapsed,
        expect_uql_code="INVALID_AGGREGATION",
        expect_pydantic_substring=f"maximum {MAX_AGGREGATIONS} aggregations".lower().replace(
            "maximum 8 aggregations", "maximum 8 aggregations"
        ),
    )


# ---------------------------------------------------------------------------
# (e) full-scan rejection on a >1M-row entity
# ---------------------------------------------------------------------------


def test_full_scan_rejected_on_large_entity(client: httpx.Client) -> None:
    """Full-scan rejection only fires for entities above LARGE_ENTITY_THRESHOLD.

    Every entity in the live ``REGISTRY`` (equity ~5k, mf ~3k, sector ~30,
    index ~50) is well under the 1M threshold, so this branch cannot be
    triggered through the live HTTP surface without monkeypatching the
    backend process — which the integration suite refuses to do.

    Branch coverage for ``validate_full_scan`` lives in
    ``tests/unit/test_uql_safety.py::test_full_scan_rejects_unindexed_filter_on_huge_entity``;
    this test exists as a placeholder so the chunk's punch list ((e) in
    the AGG-22 spec) remains visible and the day a real >1M-row entity
    lands in the registry the skip flips into a real assertion.
    """
    largest = 0
    try:
        from backend.services.uql.registry import REGISTRY

        largest = max(e.row_count_estimate for e in REGISTRY.values())
    except Exception as exc:  # pragma: no cover - defensive
        pytest.skip(f"could not introspect registry: {exc}")

    if largest <= LARGE_ENTITY_THRESHOLD:
        pytest.skip(
            f"no live entity exceeds LARGE_ENTITY_THRESHOLD "
            f"(largest={largest:,} ≤ {LARGE_ENTITY_THRESHOLD:,}); "
            f"branch is covered by tests/unit/test_uql_safety.py"
        )

    resp, elapsed = _post_timed(
        client,
        {
            "entity_type": "equity",
            "fields": ["symbol"],
            "filters": [{"field": "rs_composite", "op": ">", "value": 0}],
        },
    )
    _assert_structured_rejection(resp, elapsed, expect_uql_code="FULL_SCAN_REJECTED")


# ---------------------------------------------------------------------------
# Negative control: a fully-legitimate request must NOT trip the safety
# layer. Keeps the file honest by ensuring the rejection assertions above
# are not just rejecting *everything*.
# ---------------------------------------------------------------------------


def test_legit_request_not_rejected_by_safety(client: httpx.Client) -> None:
    resp, _ = _post_timed(
        client,
        {
            "entity_type": "equity",
            "fields": ["symbol", "rs_composite"],
            "filters": [{"field": "sector", "op": "=", "value": "Automobile"}],
            "limit": 10,
        },
    )
    assert resp.status_code == 200, (
        f"legit snapshot request was rejected — safety layer is over-eager: "
        f"{resp.status_code} {resp.text}"
    )
    body = resp.json()
    assert "records" in body and "meta" in body
