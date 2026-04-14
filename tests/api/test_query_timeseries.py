"""Integration tests for `POST /api/v1/query` timeseries mode (V2-UQL-AGG-19).

Hits the live backend on ``http://localhost:8010`` (matching the convention in
``tests/api/test_query_aggregations.py``) and exercises the timeseries
optimizer shipped in V2-UQL-AGG-10 against the dev DB. Validates:

* Happy-path: ``index`` entity returns a strictly ascending date series,
  ``records`` lengths match ``time_range`` filtering, ``close`` arrives as a
  Decimal-shaped string (never Python ``float``), and ``_meta`` carries
  ``data_as_of`` + ``query_ms``.
* Pagination: ``offset`` advances over the same ASC date axis, ``record_count``
  matches the records list, ``limit`` is honoured.
* Date bounds: ``time_range`` is inclusive on both ends and rejects rows
  outside ``[from, to]``.
* §20.5 error envelopes for every rejection path the timeseries optimizer can
  raise — aggregation-only entity, non-PK filter, multi-filter, wrong
  operator, missing ``fields``. Pydantic literal violations on
  ``granularity`` short-circuit to FastAPI's 422 envelope (not §20.5) and we
  assert that explicitly so a future schema bump can't silently widen it.

Skipped automatically if the backend or dev DB is unreachable, so the file
is safe inside the local pytest sweep without a live service.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

BASE_URL = "http://localhost:8010"
QUERY_PATH = "/api/v1/query"

# An index with the longest history in the dev DB (~2469 closes). Picked so
# the time_range slice always has data to validate ordering + pagination
# against. The optimizer is index-agnostic — this id is just a known-good
# discriminator, not part of the contract under test.
LIVE_INDEX_CODE = "NIFTY 50"
TIME_FROM = date(2026, 1, 1)
TIME_TO = date(2026, 1, 31)


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


def _as_decimal(value: Any) -> Decimal:
    """Refuse Python floats — the optimizer must cast numerics via ::numeric."""

    assert not isinstance(value, float), f"numeric came back as float: {value!r}"
    return Decimal(str(value))


def _timeseries_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "entity_type": "index",
        "mode": "timeseries",
        "fields": ["index_code", "date", "close"],
        "filters": [{"field": "index_code", "op": "=", "value": LIVE_INDEX_CODE}],
        "time_range": {"from": TIME_FROM.isoformat(), "to": TIME_TO.isoformat()},
        "limit": 50,
    }
    body.update(overrides)
    return body


def _require_records(records: list[dict[str, Any]], ctx: str) -> None:
    if not records:
        pytest.skip(f"dev DB has no rows for {ctx} — cannot validate timeseries")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_index_timeseries_returns_ascending_dates(client: httpx.Client) -> None:
    body = _ok(_post(client, _timeseries_body()))
    records = body["records"]
    _require_records(records, "index NIFTY 50 in Jan 2026")
    dates = [date.fromisoformat(row["date"]) for row in records]
    assert dates == sorted(dates), f"timeseries must be ASC by date, got {dates}"
    for d in dates:
        assert TIME_FROM <= d <= TIME_TO, f"date {d} outside time_range"
    for row in records:
        assert row["index_code"] == LIVE_INDEX_CODE
        _as_decimal(row["close"])  # raises if a float slipped through


def test_index_timeseries_meta_is_consistent(client: httpx.Client) -> None:
    body = _ok(_post(client, _timeseries_body(limit=5)))
    meta = body["meta"]
    records = body["records"]
    _require_records(records, "index NIFTY 50 (limit=5)")
    assert meta["limit"] == 5
    assert meta["offset"] == 0
    assert meta["record_count"] == len(records)
    assert len(records) <= 5


def test_index_timeseries_pagination_advances(client: httpx.Client) -> None:
    first = _ok(_post(client, _timeseries_body(limit=3, offset=0)))
    second = _ok(_post(client, _timeseries_body(limit=3, offset=3)))
    _require_records(first["records"], "first page")
    _require_records(second["records"], "second page")
    first_dates = [date.fromisoformat(r["date"]) for r in first["records"]]
    second_dates = [date.fromisoformat(r["date"]) for r in second["records"]]
    assert second_dates[0] > first_dates[-1], (
        f"offset must advance ASC date axis: page1={first_dates}, page2={second_dates}"
    )
    assert second["meta"]["offset"] == 3


def test_index_timeseries_close_is_decimal_string(client: httpx.Client) -> None:
    """Wire format guard: ``close`` must round-trip through Decimal cleanly.

    A regression that turned ``::numeric(20,4)`` into ``float`` would surface
    here as a ``float`` JSON value and fail ``_as_decimal``.
    """

    body = _ok(_post(client, _timeseries_body(limit=5)))
    _require_records(body["records"], "decimal-string check")
    for row in body["records"]:
        close = _as_decimal(row["close"])
        assert close > Decimal("0"), f"close should be positive, got {close}"


# ---------------------------------------------------------------------------
# §20.5 error envelopes
# ---------------------------------------------------------------------------


def _assert_error_envelope(resp: httpx.Response, expected_code: str) -> dict[str, Any]:
    assert resp.status_code == 400, f"want 400, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "error" in body, f"missing §20.5 envelope: {body}"
    err = body["error"]
    assert err.get("code") == expected_code, f"want code {expected_code}, got {err}"
    assert err.get("message"), "envelope missing 'message'"
    assert err.get("suggestion"), "envelope missing 'suggestion' (§20.5 mandatory)"
    return err


def test_aggregation_only_entity_rejects_timeseries(client: httpx.Client) -> None:
    resp = _post(
        client,
        {
            "entity_type": "sector",
            "mode": "timeseries",
            "fields": ["sector"],
            "filters": [{"field": "sector", "op": "=", "value": "Automobile"}],
            "time_range": {"from": TIME_FROM.isoformat(), "to": TIME_TO.isoformat()},
        },
    )
    _assert_error_envelope(resp, "INVALID_MODE")


def test_non_pk_filter_rejected(client: httpx.Client) -> None:
    resp = _post(
        client,
        _timeseries_body(filters=[{"field": "index_name", "op": "=", "value": LIVE_INDEX_CODE}]),
    )
    err = _assert_error_envelope(resp, "INVALID_FILTER")
    assert "index_code" in err["suggestion"], (
        "suggestion should name the primary-key column to fix the filter"
    )


def test_multi_filter_rejected(client: httpx.Client) -> None:
    resp = _post(
        client,
        _timeseries_body(
            filters=[
                {"field": "index_code", "op": "=", "value": "NIFTY 50"},
                {"field": "index_code", "op": "=", "value": "NIFTY 200"},
            ]
        ),
    )
    _assert_error_envelope(resp, "INVALID_FILTER")


def test_non_eq_operator_rejected(client: httpx.Client) -> None:
    resp = _post(
        client,
        _timeseries_body(filters=[{"field": "index_code", "op": "in", "value": ["NIFTY 50"]}]),
    )
    _assert_error_envelope(resp, "INVALID_FILTER")


def test_missing_fields_rejected(client: httpx.Client) -> None:
    body = _timeseries_body()
    body.pop("fields")
    resp = _post(client, body)
    _assert_error_envelope(resp, "INVALID_FILTER")


def test_unsupported_granularity_short_circuits_at_pydantic(
    client: httpx.Client,
) -> None:
    """Non-daily granularity is a Literal violation → FastAPI 422, not §20.5.

    The translate_timeseries runtime check still exists as a defence-in-depth
    guard for future schema widenings; this test pins the *current* surface
    contract so any change there is intentional.
    """

    resp = _post(client, _timeseries_body(granularity="weekly"))
    assert resp.status_code == 422, f"want 422, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "detail" in body, f"want FastAPI detail envelope, got {body}"


def test_missing_time_range_rejected_by_schema(client: httpx.Client) -> None:
    body = _timeseries_body()
    body.pop("time_range")
    resp = _post(client, body)
    # Schema validator raises ValueError → FastAPI 422.
    assert resp.status_code == 422, f"want 422, got {resp.status_code}: {resp.text}"
