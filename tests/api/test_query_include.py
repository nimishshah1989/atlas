"""Integration tests for `POST /api/v1/query` include system (V2-UQL-AGG-24).

Hits the live backend on ``http://localhost:8010`` and exercises the
spec §18 ``include`` modules end-to-end. The include layer is the
N+1-safe compound-query mechanism: a single list query attaches related
slices (``identity``, ``rs``, ``technicals``, ``conviction``) in one
batch round-trip per module (FR-022).

Coverage:

* ``identity`` is implicitly attached even when the caller omits
  ``include`` entirely (no module key on rows, no ``includes_loaded``
  in meta).
* When the caller passes ``include``, the §18.2 contract guarantees
  ``identity`` is always prefixed in ``meta.includes_loaded`` — even if
  the caller did not list it.
* ``rs`` round-trips: the module key shows up on every record, the
  payload is a dict (possibly empty for ids missing from the side
  table), and ``meta.includes_loaded`` reflects the resolved order
  ``["identity", "rs"]``.
* Empty result set with ``include`` set still produces a valid response
  shape and never 5xx (regression for the include resolver short-circuit
  on ``ids == []``).
* Deferred modules (``peers``, ``intelligence``, ``goldilocks``) and
  unknown modules surface as a structured 4xx rejection (Pydantic
  Literal short-circuit at the route layer) — never a raw 500.
* Repeating the same ``include`` request twice yields identical record
  shape (idempotency probe; the resolver layer must not mutate request
  state across calls).

The ``technicals`` and ``conviction`` modules are *registered* in
:data:`AVAILABLE_MODULES` but their resolvers depend on dev-DB tables
(``de_equity_technical_daily.instrument_id``, ``atlas_conviction_daily``)
that are not populated against the equity ``symbol`` primary key in this
environment. Asserting the wire contract against them would test the
schema gap, not the include system. Their resolver-level safety is
covered by ``tests/unit/test_uql_includes.py``; here we cover only the
``rs`` happy path and the structural envelope.

Tests are skipped automatically if the backend is unreachable, matching
the rest of ``tests/api/``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

BASE_URL = "http://localhost:8010"
QUERY_PATH = "/api/v1/query"


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    try:
        probe = httpx.get(f"{BASE_URL}/api/v1/health", timeout=2.0)
        probe.raise_for_status()
    except (httpx.HTTPError, httpx.RequestError) as exc:
        pytest.skip(f"backend not reachable at {BASE_URL}: {exc}")
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


def _post(client: httpx.Client, body: dict[str, Any]) -> httpx.Response:
    return client.post(QUERY_PATH, json=body)


def _ok(resp: httpx.Response) -> dict[str, Any]:
    assert resp.status_code == 200, f"want 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "records" in body and "meta" in body, f"missing envelope keys: {body}"
    meta = body["meta"]
    assert meta.get("data_as_of"), f"meta missing data_as_of: {meta}"
    assert isinstance(meta.get("query_ms"), int), f"meta.query_ms not int: {meta}"
    return body


# ---------------------------------------------------------------------------
# Default behaviour — no `include` field
# ---------------------------------------------------------------------------


def test_query_without_include_omits_module_keys(client: httpx.Client) -> None:
    """Omitting ``include`` must not attach module keys or set ``includes_loaded``."""

    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "fields": ["symbol", "sector"],
                "limit": 5,
            },
        )
    )
    assert body["meta"]["includes_loaded"] is None
    for row in body["records"]:
        assert set(row.keys()) <= {"symbol", "sector"}, (
            f"unexpected module keys leaked into row: {row}"
        )


# ---------------------------------------------------------------------------
# `identity` — implicitly prefixed by validate_modules (§18.2)
# ---------------------------------------------------------------------------


def test_include_identity_only_records_carry_no_extra_keys(client: httpx.Client) -> None:
    """``identity`` is projected from the base row — no side query, no extra keys."""

    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "fields": ["symbol", "sector"],
                "include": ["identity"],
                "limit": 5,
            },
        )
    )
    assert body["meta"]["includes_loaded"] == ["identity"]
    for row in body["records"]:
        # identity is the projection itself; no separate `identity` key is
        # attached because _attach_includes intentionally skips it.
        assert "identity" not in row, f"identity should not be a row key: {row}"
        assert set(row.keys()) == {"symbol", "sector"}


# ---------------------------------------------------------------------------
# `rs` — single-module batch resolution
# ---------------------------------------------------------------------------


def test_include_rs_attaches_module_key_to_every_row(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "fields": ["symbol", "sector"],
                "include": ["rs"],
                "limit": 10,
            },
        )
    )
    assert body["meta"]["includes_loaded"] == ["identity", "rs"]
    records = body["records"]
    assert records, "expected at least one equity row"
    for row in records:
        assert "rs" in row, f"rs module key missing on row: {row}"
        assert isinstance(row["rs"], dict), f"rs payload must be dict, got {type(row['rs'])}"
        # Per resolver contract, missing side-table rows yield {} so the
        # caller can attach the key consistently. If a payload is present
        # it must contain the canonical RS columns.
        if row["rs"]:
            assert "rs_composite" in row["rs"], f"rs payload missing rs_composite: {row['rs']}"


def test_include_rs_without_listing_identity_still_prefixes_identity(
    client: httpx.Client,
) -> None:
    """§18.2: validate_modules must auto-prefix ``identity`` even if omitted."""

    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "fields": ["symbol"],
                "include": ["rs"],
                "limit": 3,
            },
        )
    )
    loaded = body["meta"]["includes_loaded"]
    assert loaded[0] == "identity", f"identity must be first in includes_loaded: {loaded}"
    assert "rs" in loaded


# ---------------------------------------------------------------------------
# Empty result set — resolver short-circuit on ids=[]
# ---------------------------------------------------------------------------


def test_include_with_empty_result_set_returns_clean_envelope(client: httpx.Client) -> None:
    """A filter that matches no rows must still return a valid envelope.

    Regression for the resolver short-circuit: ``includes.resolve`` with
    ``ids == []`` must not issue a SQL statement and must not 5xx.
    """

    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "fields": ["symbol"],
                "filters": [{"field": "symbol", "op": "=", "value": "__NO_SUCH_SYMBOL_XYZ__"}],
                "include": ["rs"],
                "limit": 5,
            },
        )
    )
    assert body["records"] == []
    assert body["total"] == 0
    # includes_loaded still reports the requested modules so the client
    # knows the request was honoured even though the projection is empty.
    assert body["meta"]["includes_loaded"] == ["identity", "rs"]


# ---------------------------------------------------------------------------
# Idempotency — same request twice → same shape
# ---------------------------------------------------------------------------


def test_include_request_is_idempotent_across_calls(client: httpx.Client) -> None:
    payload = {
        "entity_type": "equity",
        "fields": ["symbol", "sector"],
        "include": ["rs"],
        "sort": [{"field": "symbol", "direction": "asc"}],
        "limit": 5,
    }
    first = _ok(_post(client, payload))
    second = _ok(_post(client, payload))
    assert [r["symbol"] for r in first["records"]] == [r["symbol"] for r in second["records"]]
    assert first["meta"]["includes_loaded"] == second["meta"]["includes_loaded"]
    for a, b in zip(first["records"], second["records"]):
        assert set(a.keys()) == set(b.keys()), (
            f"idempotency violation: row keys differ across calls: {a} vs {b}"
        )


# ---------------------------------------------------------------------------
# Structured rejection — deferred + unknown modules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    ["peers", "intelligence", "goldilocks", "tv", "holders", "holdings", "sectors"],
)
def test_deferred_module_rejected_without_5xx(client: httpx.Client, module: str) -> None:
    """Deferred modules must surface as a structured 4xx, never a raw 500.

    The route layer's Pydantic ``Literal`` constraint short-circuits the
    request at parse time (422). A 400 from
    :class:`UQLError(INCLUDE_NOT_AVAILABLE)` is also acceptable — what
    matters is the rejection arrives as a structured envelope before any
    SQL is issued.
    """

    resp = _post(
        client,
        {
            "entity_type": "equity",
            "fields": ["symbol"],
            "include": [module],
            "limit": 5,
        },
    )
    assert resp.status_code in (400, 422), (
        f"want 400/422 for deferred module '{module}', got {resp.status_code}: {resp.text}"
    )
    assert resp.status_code < 500
    body = resp.json()
    # Either Pydantic's `detail` or the §20.5 `error` envelope — both are
    # structured, both name the offending module somewhere in the payload.
    assert "detail" in body or "error" in body, f"unstructured rejection body: {body}"


def test_unknown_module_rejected_without_5xx(client: httpx.Client) -> None:
    resp = _post(
        client,
        {
            "entity_type": "equity",
            "fields": ["symbol"],
            "include": ["bogus_module"],
            "limit": 5,
        },
    )
    assert resp.status_code in (400, 422), f"want 400/422, got {resp.status_code}: {resp.text}"
    assert resp.status_code < 500
