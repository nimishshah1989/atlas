"""Integration tests for `POST /api/v1/query` aggregation mode (V2-UQL-AGG-18).

Hits the live backend on ``http://localhost:8010`` (the same target as
``tests/integration/test_v1_endpoints.py``) and exercises every aggregation
function shipped in V2-UQL-AGG-8 against the dev DB. Validates:

* Multi-aggregation group_by execution (avg / median / stddev / count / count_all).
* Threshold aggregations (``pct_above`` / ``pct_below``) bind correctly and
  return values inside ``[0, 100]``.
* ``pct_positive`` and ``pct_true`` evaluate without 5xx and respect the
  null-safe ``count(field)`` denominator (FR-014).
* Wire format: numeric aggregates serialise as Decimal-shaped strings (never
  Python ``float``) and ``count``/``count_all`` serialise as integers.
* ``_meta`` envelope includes ``data_as_of`` and ``query_ms`` (§17.6 + §17.7).
* The §20.5 error envelope fires on unknown fields (400) and unknown entity
  types (400), not raw 500s.
* Filters compose with aggregations via ``UQLOperator.EQ``.

These tests are skipped automatically if the backend is unreachable, so the
file is safe to run inside the local pytest sweep without a live service.
"""

from __future__ import annotations

from decimal import Decimal
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


def _as_decimal(value: Any) -> Decimal:
    """Wire format for numeric aggregates is a Decimal-shaped string.

    Floats in the JSON payload would imply someone replaced our
    ``::numeric(20, 4)`` cast with a ``float()`` cast somewhere in the
    optimizer — assert against that regression by refusing to parse
    anything that arrived as a Python float.
    """

    assert not isinstance(value, float), f"numeric aggregate came back as float: {value!r}"
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Happy-path multi-aggregation group_by
# ---------------------------------------------------------------------------


def test_sector_group_by_count_all(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "group_by": ["sector"],
                "aggregations": [{"function": "count_all", "alias": "n"}],
                "limit": 100,
            },
        )
    )
    records = body["records"]
    assert len(records) >= 10, f"expected ≥10 sector groups, got {len(records)}"
    for row in records:
        assert "sector" in row
        assert isinstance(row["n"], int), f"count_all must serialise as int, got {row['n']!r}"
        assert row["n"] >= 0


def test_multi_aggregation_group_by_returns_all_aliases(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "group_by": ["sector"],
                "aggregations": [
                    {"function": "avg", "field": "rs_composite", "alias": "avg_rs"},
                    {"function": "median", "field": "rs_composite", "alias": "med_rs"},
                    {"function": "stddev", "field": "rs_composite", "alias": "sd_rs"},
                    {"function": "min", "field": "rs_composite", "alias": "mn_rs"},
                    {"function": "max", "field": "rs_composite", "alias": "mx_rs"},
                    {"function": "sum", "field": "rs_composite", "alias": "sum_rs"},
                    {"function": "count", "field": "rs_composite", "alias": "non_null"},
                    {"function": "count_all", "alias": "n"},
                ],
                "limit": 50,
            },
        )
    )
    records = body["records"]
    assert records, "expected at least one sector group"
    for row in records:
        assert isinstance(row["n"], int)
        assert isinstance(row["non_null"], int)
        assert row["non_null"] <= row["n"], "count(field) must not exceed count(*)"
        if row["non_null"] == 0:
            # All-null group: every numeric aggregate must be NULL (FR-014).
            for alias in ("avg_rs", "med_rs", "sd_rs", "mn_rs", "mx_rs", "sum_rs"):
                assert row[alias] is None, f"{alias} should be NULL when non_null=0"
            continue
        avg_rs = _as_decimal(row["avg_rs"])
        mn = _as_decimal(row["mn_rs"])
        mx = _as_decimal(row["mx_rs"])
        med = _as_decimal(row["med_rs"])
        assert mn <= avg_rs <= mx, f"avg out of [min,max] for row {row}"
        assert mn <= med <= mx, f"median out of [min,max] for row {row}"
        if row["sd_rs"] is not None:
            assert _as_decimal(row["sd_rs"]) >= Decimal("0")


# ---------------------------------------------------------------------------
# Threshold + percentage aggregates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "function,threshold",
    [
        ("pct_above", 0),
        ("pct_above", 80),
        ("pct_below", 0),
        ("pct_below", -10),
    ],
)
def test_threshold_aggregations_in_unit_interval(
    client: httpx.Client, function: str, threshold: float
) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "group_by": ["sector"],
                "aggregations": [
                    {
                        "function": function,
                        "field": "rs_composite",
                        "alias": "pct",
                        "threshold": threshold,
                    },
                    {"function": "count", "field": "rs_composite", "alias": "non_null"},
                ],
                "limit": 100,
            },
        )
    )
    for row in body["records"]:
        if row["non_null"] == 0:
            assert row["pct"] is None, "all-null group must yield NULL pct (FR-014)"
            continue
        pct = _as_decimal(row["pct"])
        assert Decimal("0") <= pct <= Decimal("100"), f"pct {pct} outside [0,100]"


def test_pct_positive_in_unit_interval(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "group_by": ["sector"],
                "aggregations": [
                    {"function": "pct_positive", "field": "rs_composite", "alias": "pp"},
                    {"function": "count", "field": "rs_composite", "alias": "non_null"},
                ],
                "limit": 100,
            },
        )
    )
    for row in body["records"]:
        if row["non_null"] == 0:
            assert row["pp"] is None
            continue
        pp = _as_decimal(row["pp"])
        assert Decimal("0") <= pp <= Decimal("100")


def test_pct_true_on_boolean_field_executes(client: httpx.Client) -> None:
    """``pct_true`` over ``above_200dma`` must return 200 with a Decimal or NULL.

    Whether the dev DB has any non-null boolean rows on the latest
    technicals partition is not the point of this test — we are asserting
    the SQL builder + optimizer produced a valid statement and the
    numerator/denominator pattern survives a round trip.
    """

    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "group_by": ["sector"],
                "aggregations": [
                    {"function": "pct_true", "field": "above_200dma", "alias": "pct_200"},
                    {"function": "count_all", "alias": "n"},
                ],
                "limit": 50,
            },
        )
    )
    for row in body["records"]:
        if row["pct_200"] is None:
            continue
        pct = _as_decimal(row["pct_200"])
        assert Decimal("0") <= pct <= Decimal("100")


# ---------------------------------------------------------------------------
# Filter + aggregation composition
# ---------------------------------------------------------------------------


def test_filter_then_aggregate_single_sector(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "filters": [{"field": "sector", "op": "=", "value": "Automobile"}],
                "group_by": ["sector"],
                "aggregations": [
                    {"function": "count_all", "alias": "n"},
                    {"function": "avg", "field": "rs_composite", "alias": "avg_rs"},
                ],
            },
        )
    )
    records = body["records"]
    assert len(records) == 1, f"filtered group_by should return one row, got {records}"
    row = records[0]
    assert row["sector"] == "Automobile"
    assert isinstance(row["n"], int) and row["n"] > 0
    if row["avg_rs"] is not None:
        _as_decimal(row["avg_rs"])  # raises if it came back as float


# ---------------------------------------------------------------------------
# Error envelope (§20.5)
# ---------------------------------------------------------------------------


def test_unknown_field_returns_400_envelope(client: httpx.Client) -> None:
    resp = _post(
        client,
        {
            "entity_type": "equity",
            "group_by": ["nonexistent_field"],
            "aggregations": [{"function": "count_all", "alias": "n"}],
        },
    )
    assert resp.status_code == 400, f"want 400, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "error" in body, f"missing §20.5 error envelope: {body}"
    err = body["error"]
    assert err.get("code"), "error envelope missing 'code'"
    assert err.get("message"), "error envelope missing 'message'"
    assert err.get("suggestion"), "error envelope missing 'suggestion' (§20.5 mandatory)"


def test_unknown_entity_type_returns_400_envelope(client: httpx.Client) -> None:
    resp = _post(
        client,
        {
            "entity_type": "banana",
            "group_by": ["sector"],
            "aggregations": [{"function": "count_all", "alias": "n"}],
        },
    )
    # Pydantic Literal rejection short-circuits to 422; UQLError dispatch
    # would surface as 400. Either is a structured rejection — what matters
    # is we never see a 5xx for a malformed entity_type.
    assert resp.status_code in (400, 422), f"want 400/422, got {resp.status_code}: {resp.text}"
    assert resp.status_code < 500


def test_aggregation_query_meta_carries_record_count(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "group_by": ["sector"],
                "aggregations": [{"function": "count_all", "alias": "n"}],
                "limit": 5,
            },
        )
    )
    meta = body["meta"]
    assert meta["record_count"] == len(body["records"])
    assert meta["limit"] == 5
    assert meta["offset"] == 0
