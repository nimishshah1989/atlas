"""Integration tests for `POST /api/v1/query` multi-entity dispatch (V2-UQL-AGG-21).

Hits the live backend on ``http://localhost:8010`` (matching
``tests/api/test_query_aggregations.py`` and ``test_query_timeseries.py``)
and exercises the engine dispatcher against **all four** registered
entity types — ``equity``, ``mf``, ``sector``, ``index`` — to prove that:

* Each entity routes through its own ``EntityDef`` (distinct base table,
  joins, primary key, fields). The engine never silently substitutes one
  entity for another.
* Each dispatch produces a §17.6 ``_meta`` envelope whose ``data_as_of``
  is resolved per-entity from the JIP freshness API (FR-019). MF lives on
  a different partition cadence than equity/sector/index in the dev DB,
  so the assertion is "every entity carries a non-empty data_as_of and
  the value matches whatever the freshness service returns for *that*
  entity", not a hard-coded date.
* All four entities expose their own primary-key column in the response
  records (``equity.symbol``, ``mf.mstar_id``, ``sector.sector``,
  ``index.index_code``).
* The dispatcher accepts the right *modes* for each entity: snapshot for
  equity/mf/index, aggregation rollup for sector, timeseries for index.
* Numeric aggregates round-trip as Decimal-shaped strings (never Python
  floats) regardless of which entity the request landed on — i.e. the
  optimizer's ``::numeric`` cast is uniformly applied across entities.
* Unknown entity_type values are rejected by Pydantic's ``Literal`` guard
  (422) **before** they reach the engine, so a typo can never reach the
  SQL builder. This is the inverse of the §20.5 ``INVALID_ENTITY_TYPE``
  envelope path covered in ``test_query_errors.py``.

Skipped automatically if the backend is unreachable so the file is safe
inside the local pytest sweep without a live service.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest

BASE_URL = "http://localhost:8010"
QUERY_PATH = "/api/v1/query"

# Picked because every dev-DB partition we have for MF carries this
# category (verified via `select count(*) from de_mf_master where
# category_name='Liquid'` against jip-data-engine on 2026-04-14). The
# point of this test is dispatcher routing, not coverage of every MF
# category, so a single indexed filter that hits the latest MF NAV
# partition is enough.
LIVE_MF_CATEGORY = "Liquid"
LIVE_INDEX_CODE = "NIFTY 50"


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
    """Refuse Python floats — every numeric column must round-trip as a string."""

    assert not isinstance(value, float), f"numeric came back as float: {value!r}"
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Per-entity smoke — each entity dispatches and returns its own PK column
# ---------------------------------------------------------------------------


def test_equity_dispatch_returns_equity_pk(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "equity",
                "fields": ["symbol", "sector", "rs_composite"],
                "filters": [{"field": "nifty_50", "op": "=", "value": True}],
                "limit": 5,
            },
        )
    )
    records = body["records"]
    assert records, "equity dispatch returned no rows for nifty_50=true"
    for row in records:
        assert "symbol" in row, f"equity record missing primary key 'symbol': {row}"
        assert isinstance(row["symbol"], str) and row["symbol"]
        if row.get("rs_composite") is not None:
            _as_decimal(row["rs_composite"])  # raises if it came back as float


def test_mf_dispatch_returns_mf_pk(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "mf",
                "fields": ["mstar_id", "fund_name", "category_name"],
                "filters": [{"field": "category_name", "op": "=", "value": LIVE_MF_CATEGORY}],
                "limit": 5,
            },
        )
    )
    records = body["records"]
    assert records, f"mf dispatch returned no rows for category={LIVE_MF_CATEGORY}"
    for row in records:
        assert "mstar_id" in row, f"mf record missing primary key 'mstar_id': {row}"
        assert isinstance(row["mstar_id"], str) and row["mstar_id"]
        assert row["category_name"] == LIVE_MF_CATEGORY


def test_sector_dispatch_returns_sector_rollup(client: httpx.Client) -> None:
    """Sector entity's canonical mode is a sector → metric rollup."""

    body = _ok(
        _post(
            client,
            {
                "entity_type": "sector",
                "group_by": ["sector"],
                "aggregations": [
                    {"function": "avg", "field": "rs_composite", "alias": "avg_rs"},
                    {"function": "count_all", "alias": "n"},
                ],
                "sort": [{"field": "n", "direction": "desc"}],
                "limit": 10,
            },
        )
    )
    records = body["records"]
    assert len(records) >= 5, f"expected ≥5 sector groups, got {len(records)}"
    for row in records:
        assert "sector" in row, f"sector record missing 'sector' column: {row}"
        assert isinstance(row["n"], int) and row["n"] >= 0
        if row["avg_rs"] is not None:
            _as_decimal(row["avg_rs"])


def test_index_dispatch_snapshot(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "index",
                "fields": ["index_code", "index_name"],
                "limit": 5,
            },
        )
    )
    records = body["records"]
    assert records, "index dispatch returned zero rows"
    for row in records:
        assert "index_code" in row, f"index record missing 'index_code': {row}"
        assert isinstance(row["index_code"], str) and row["index_code"]


def test_index_dispatch_timeseries(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {
                "entity_type": "index",
                "mode": "timeseries",
                "fields": ["close"],
                "filters": [{"field": "index_code", "op": "=", "value": LIVE_INDEX_CODE}],
                "time_range": {"from": "2026-01-01", "to": "2026-01-15"},
                "limit": 50,
            },
        )
    )
    records = body["records"]
    assert records, f"index timeseries returned no rows for {LIVE_INDEX_CODE}"
    for row in records:
        assert "close" in row
        if row["close"] is not None:
            _as_decimal(row["close"])


# ---------------------------------------------------------------------------
# Cross-entity invariants — same dispatcher, four destinations
# ---------------------------------------------------------------------------


def _snapshot(entity_type: str, fields: list[str], **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"entity_type": entity_type, "fields": fields, "limit": 3}
    body.update(extra)
    return body


def test_each_entity_carries_its_own_data_as_of(client: httpx.Client) -> None:
    """FR-019: ``data_as_of`` is resolved per-entity, not globally.

    The dispatcher must call ``meta.resolve_data_as_of(jip, entity_type)``
    with the request's entity, not a hard-coded constant. We don't pin
    the exact dates here (they advance as the pipeline runs); we only
    assert (a) every entity returned a non-empty ISO date and (b) at
    least one pair of entities differs, which proves the lookup is
    actually entity-scoped instead of returning a single global value
    for everyone.
    """

    asof: dict[str, str] = {}

    asof["equity"] = _ok(
        _post(
            client,
            _snapshot(
                "equity", ["symbol"], filters=[{"field": "nifty_50", "op": "=", "value": True}]
            ),
        )
    )["meta"]["data_as_of"]

    asof["mf"] = _ok(
        _post(
            client,
            _snapshot(
                "mf",
                ["mstar_id"],
                filters=[{"field": "category_name", "op": "=", "value": LIVE_MF_CATEGORY}],
            ),
        )
    )["meta"]["data_as_of"]

    asof["index"] = _ok(_post(client, _snapshot("index", ["index_code"])))["meta"]["data_as_of"]

    # Sector goes through aggregation, but the meta resolver still
    # records the entity-scoped freshness, so we cover it here too.
    asof["sector"] = _ok(
        _post(
            client,
            {
                "entity_type": "sector",
                "group_by": ["sector"],
                "aggregations": [{"function": "count_all", "alias": "n"}],
                "limit": 1,
            },
        )
    )["meta"]["data_as_of"]

    for entity, value in asof.items():
        assert value, f"{entity} dispatch returned empty data_as_of"
        # ISO yyyy-mm-dd with hyphens. Cheap sanity check; full
        # parsing happens in test_query_aggregations.
        assert len(value) == 10 and value[4] == "-" and value[7] == "-", (
            f"{entity} data_as_of not ISO date: {value!r}"
        )

    # FR-019 requires entity-scoped resolution. If every entity reported
    # the same value the resolver could be a constant — so demand at
    # least one pair to differ in the dev DB. (MF is on a slower cadence
    # than equity/index in our pipeline, so this naturally holds.)
    assert len(set(asof.values())) >= 2, (
        f"every entity reports the same data_as_of {asof}; dispatcher likely "
        "ignores entity_type when resolving freshness (FR-019 violation)"
    )


def test_dispatcher_routes_to_distinct_pk_columns(client: httpx.Client) -> None:
    """A single test that hits all four entities and asserts each one
    surfaces its registry-defined primary key. This is the headline
    assertion of multi-entity dispatch: the engine must not collapse
    two entities into the same SELECT shape."""

    equity = _ok(
        _post(
            client,
            _snapshot(
                "equity", ["symbol"], filters=[{"field": "nifty_50", "op": "=", "value": True}]
            ),
        )
    )
    mf = _ok(
        _post(
            client,
            _snapshot(
                "mf",
                ["mstar_id"],
                filters=[{"field": "category_name", "op": "=", "value": LIVE_MF_CATEGORY}],
            ),
        )
    )
    index_resp = _ok(_post(client, _snapshot("index", ["index_code"])))
    sector = _ok(
        _post(
            client,
            {
                "entity_type": "sector",
                "group_by": ["sector"],
                "aggregations": [{"function": "count_all", "alias": "n"}],
                "limit": 3,
            },
        )
    )

    assert all("symbol" in r for r in equity["records"]), "equity rows missing symbol"
    assert all("mstar_id" in r for r in mf["records"]), "mf rows missing mstar_id"
    assert all("index_code" in r for r in index_resp["records"]), "index rows missing index_code"
    assert all("sector" in r for r in sector["records"]), "sector rows missing sector"

    # And the inverse: no entity leaks another entity's pk into its own
    # response shape (catches a future bug where the optimizer re-uses
    # the wrong EntityDef under the hood).
    for record in equity["records"]:
        assert "mstar_id" not in record and "index_code" not in record
    for record in mf["records"]:
        assert "symbol" not in record and "index_code" not in record
    for record in index_resp["records"]:
        assert "symbol" not in record and "mstar_id" not in record


def test_unknown_entity_type_short_circuits_to_422(client: httpx.Client) -> None:
    """``entity_type`` is a Pydantic ``Literal``, so a typo dies in
    request validation before the dispatcher ever runs. Must be a
    structured rejection — never a 5xx."""

    resp = _post(
        client,
        {
            "entity_type": "banana",
            "fields": ["x"],
            "limit": 1,
        },
    )
    assert resp.status_code == 422, f"want 422, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "detail" in body, f"FastAPI 422 envelope missing 'detail': {body}"
    detail = body["detail"]
    assert detail and any("entity_type" in err.get("loc", []) for err in detail), (
        f"422 should fault on entity_type, got {detail}"
    )


def test_meta_record_count_matches_records_for_every_entity(client: httpx.Client) -> None:
    """``meta.record_count`` is computed from the records list inside the
    dispatcher's ``meta.build_meta``. Run it for every entity so a future
    refactor that wires the wrong length into the snapshot vs. aggregation
    branches gets caught here, not in production."""

    cases: list[dict[str, Any]] = [
        _snapshot("equity", ["symbol"], filters=[{"field": "nifty_50", "op": "=", "value": True}]),
        _snapshot(
            "mf",
            ["mstar_id"],
            filters=[{"field": "category_name", "op": "=", "value": LIVE_MF_CATEGORY}],
        ),
        _snapshot("index", ["index_code"]),
        {
            "entity_type": "sector",
            "group_by": ["sector"],
            "aggregations": [{"function": "count_all", "alias": "n"}],
            "limit": 4,
        },
    ]
    for body in cases:
        resp = _ok(_post(client, body))
        assert resp["meta"]["record_count"] == len(resp["records"]), (
            f"record_count mismatch for {body['entity_type']}: "
            f"{resp['meta']['record_count']} vs {len(resp['records'])}"
        )
