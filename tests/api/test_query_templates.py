"""Integration tests for `POST /api/v1/query/template` (V2-UQL-AGG-20).

Hits the live backend on ``http://localhost:8010`` (matching the convention
in ``tests/api/test_query_aggregations.py`` and
``tests/api/test_query_timeseries.py``) and exercises every named template
shipped in V2-UQL-AGG-11 against the dev DB. Validates:

* All four registered templates (``top_rs_gainers``, ``sector_rotation``,
  ``oversold_candidates``, ``breadth_dashboard``) execute end-to-end and
  return the §17.6 envelope (``records`` + ``meta`` with ``data_as_of`` and
  integer ``query_ms``).
* Optional ``limit`` params are honoured and propagated into ``meta.limit``.
* ``top_rs_gainers`` validates ``period`` against the ``rs_*`` whitelist and
  returns rows sorted DESC by that field with no nulls.
* Numeric aggregates serialise as Decimal-shaped strings (never Python
  ``float``), the same wire-format guard the aggregations + timeseries
  suites enforce.
* §20.5 error envelopes fire on the three template-specific failure modes:
  unknown template (``TEMPLATE_NOT_FOUND`` → 404), missing required param
  (``TEMPLATE_PARAM_MISSING`` → 400), and bad-enum required param
  (``TEMPLATE_PARAM_MISSING`` → 400 with an enumerating suggestion).
* Pydantic validation on the ``TemplateRequest`` body short-circuits to 422
  for blank/missing template names — pinned so a future schema bump can't
  silently widen it.

Skipped automatically if the backend is unreachable, so the file is safe
inside the local pytest sweep without a live service.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest

BASE_URL = "http://localhost:8010"
TEMPLATE_PATH = "/api/v1/query/template"


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    try:
        probe = httpx.get(f"{BASE_URL}/api/v1/health", timeout=2.0)
        probe.raise_for_status()
    except (httpx.HTTPError, httpx.RequestError) as exc:
        pytest.skip(f"backend not reachable at {BASE_URL}: {exc}")
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


def _post(client: httpx.Client, body: dict[str, Any]) -> httpx.Response:
    return client.post(TEMPLATE_PATH, json=body)


def _ok(resp: httpx.Response) -> dict[str, Any]:
    assert resp.status_code == 200, f"want 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "records" in body and "meta" in body, f"missing envelope keys: {body}"
    meta = body["meta"]
    assert meta.get("data_as_of"), f"meta missing data_as_of: {meta}"
    assert isinstance(meta.get("query_ms"), int), f"meta.query_ms not int: {meta}"
    assert meta["record_count"] == len(body["records"])
    return body


def _as_decimal(value: Any) -> Decimal:
    """Refuse Python floats — numeric aggregates must round-trip via str."""

    assert not isinstance(value, float), f"numeric came back as float: {value!r}"
    return Decimal(str(value))


def _assert_error_envelope(
    resp: httpx.Response, expected_code: str, expected_status: int
) -> dict[str, Any]:
    assert resp.status_code == expected_status, (
        f"want {expected_status}, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "error" in body, f"missing §20.5 envelope: {body}"
    err = body["error"]
    assert err.get("code") == expected_code, f"want code {expected_code}, got {err}"
    assert err.get("message"), "envelope missing 'message'"
    assert err.get("suggestion"), "envelope missing 'suggestion' (§20.5 mandatory)"
    return err


# ---------------------------------------------------------------------------
# Happy path — every template in REGISTRY executes
# ---------------------------------------------------------------------------


def test_top_rs_gainers_composite_returns_sorted_desc(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {"template": "top_rs_gainers", "params": {"period": "rs_composite", "limit": 10}},
        )
    )
    records = body["records"]
    assert records, "top_rs_gainers should return at least one row on dev DB"
    assert len(records) <= 10
    assert body["meta"]["limit"] == 10
    rs_values = []
    for row in records:
        assert "symbol" in row and "company_name" in row
        assert row["rs_composite"] is not None, "IS_NOT_NULL filter should drop null rows"
        rs_values.append(_as_decimal(row["rs_composite"]))
    assert rs_values == sorted(rs_values, reverse=True), (
        f"top_rs_gainers must be DESC by rs_composite, got {rs_values}"
    )


@pytest.mark.parametrize("period", ["rs_1w", "rs_1m", "rs_3m", "rs_6m", "rs_12m"])
def test_top_rs_gainers_window_periods_execute(client: httpx.Client, period: str) -> None:
    body = _ok(
        _post(
            client,
            {"template": "top_rs_gainers", "params": {"period": period, "limit": 5}},
        )
    )
    for row in body["records"]:
        assert row[period] is not None, f"{period} IS_NOT_NULL filter should drop nulls"
        _as_decimal(row[period])


def test_sector_rotation_returns_sector_rollup(client: httpx.Client) -> None:
    body = _ok(_post(client, {"template": "sector_rotation", "params": {"limit": 5}}))
    records = body["records"]
    assert records, "sector_rotation should return at least one row"
    assert len(records) <= 5
    assert body["meta"]["limit"] == 5
    avg_rs_values = []
    for row in records:
        assert "sector" in row
        assert isinstance(row["constituents"], int) and row["constituents"] >= 0
        if row["avg_rs"] is not None:
            avg_rs_values.append(_as_decimal(row["avg_rs"]))
        # pct_above_50dma may be null on the dev DB if the boolean column
        # has no non-null rows on the latest partition — that is the FR-014
        # null-safe denominator behaviour, not a bug.
        if row["pct_above_50dma"] is not None:
            pct = _as_decimal(row["pct_above_50dma"])
            assert Decimal("0") <= pct <= Decimal("100")
    if len(avg_rs_values) >= 2:
        assert avg_rs_values == sorted(avg_rs_values, reverse=True), (
            f"sector_rotation must be DESC by avg_rs, got {avg_rs_values}"
        )


def test_sector_rotation_default_limit_no_params(client: httpx.Client) -> None:
    """Parameterless template invocation must not 422 on missing params."""

    body = _ok(_post(client, {"template": "sector_rotation"}))
    assert body["meta"]["limit"] == 30  # default in templates.py


def test_oversold_candidates_executes(client: httpx.Client) -> None:
    body = _ok(
        _post(
            client,
            {"template": "oversold_candidates", "params": {"rsi_max": 100, "limit": 5}},
        )
    )
    # rsi_max=100 widens the filter so dev DB always has rows to validate
    # the wire format against; the default rsi_max=30 may legitimately
    # return zero rows on the current partition.
    for row in body["records"]:
        assert "symbol" in row and "rsi_14" in row
        rsi = _as_decimal(row["rsi_14"])
        assert rsi < Decimal("100")
        if row["rs_composite"] is not None:
            _as_decimal(row["rs_composite"])
        if row["close"] is not None:
            _as_decimal(row["close"])


def test_breadth_dashboard_executes(client: httpx.Client) -> None:
    body = _ok(_post(client, {"template": "breadth_dashboard", "params": {"limit": 10}}))
    assert body["meta"]["limit"] == 10
    for row in body["records"]:
        assert "sector" in row
        for alias in ("pct_above_50dma", "pct_above_200dma"):
            if row[alias] is not None:
                pct = _as_decimal(row[alias])
                assert Decimal("0") <= pct <= Decimal("100")
        if row["avg_rs"] is not None:
            _as_decimal(row["avg_rs"])


# ---------------------------------------------------------------------------
# §20.5 error envelopes — template-specific failure modes
# ---------------------------------------------------------------------------


def test_unknown_template_returns_404_envelope(client: httpx.Client) -> None:
    resp = _post(client, {"template": "definitely_not_a_template", "params": {}})
    err = _assert_error_envelope(resp, "TEMPLATE_NOT_FOUND", 404)
    # Suggestion must enumerate every registered template so the client can
    # self-correct without reading docs.
    for name in (
        "top_rs_gainers",
        "sector_rotation",
        "oversold_candidates",
        "breadth_dashboard",
    ):
        assert name in err["suggestion"], (
            f"TEMPLATE_NOT_FOUND suggestion should list {name}, got {err['suggestion']!r}"
        )


def test_missing_required_param_returns_400_envelope(client: httpx.Client) -> None:
    resp = _post(client, {"template": "top_rs_gainers", "params": {}})
    err = _assert_error_envelope(resp, "TEMPLATE_PARAM_MISSING", 400)
    assert "period" in err["message"]
    assert "period" in err["suggestion"]


def test_bad_enum_param_returns_400_envelope(client: httpx.Client) -> None:
    resp = _post(
        client,
        {"template": "top_rs_gainers", "params": {"period": "rs_quarterly"}},
    )
    err = _assert_error_envelope(resp, "TEMPLATE_PARAM_MISSING", 400)
    # Suggestion enumerates the valid period whitelist so the client can fix
    # the call without grepping the registry.
    assert "rs_composite" in err["message"] or "rs_composite" in err["suggestion"]


def test_blank_template_name_rejected_by_pydantic(client: httpx.Client) -> None:
    """``template`` has ``min_length=1`` — a blank value is a 422, not §20.5.

    Pinned so any future schema change to ``TemplateRequest`` is intentional.
    """

    resp = _post(client, {"template": "", "params": {}})
    assert resp.status_code == 422, f"want 422, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "detail" in body, f"want FastAPI detail envelope, got {body}"


def test_missing_template_field_rejected_by_pydantic(client: httpx.Client) -> None:
    resp = _post(client, {"params": {"period": "rs_composite"}})
    assert resp.status_code == 422, f"want 422, got {resp.status_code}: {resp.text}"
