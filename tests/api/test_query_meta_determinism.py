"""`_meta` determinism for `POST /api/v1/query` (V2-UQL-AGG-25).

Runs the same aggregation request five times against the dev backend
and asserts that every response is byte-identical, excluding only
``meta.query_ms`` (a wall-clock field).

Why this matters:

* **Guarantee #1 (Deterministic)** from ``CLAUDE.md`` — same
  ``data_as_of`` + same request must produce the same output.
* The UQL engine injects an ``ORDER BY`` when an aggregation request
  has no caller-supplied ``order_by``; if that stability tie-breaker
  regresses, row order will drift across calls. This test catches that
  regression without needing to reach into the SQL plan.
* ``meta.data_as_of``, ``meta.record_count``, ``meta.total``, and
  ``meta.has_more`` must all be stable across identical calls. The
  only permitted variance is the wall-clock ``query_ms``.

Skipped automatically if the backend is unreachable.
"""

from __future__ import annotations

import copy
from typing import Any

import httpx
import pytest

BASE_URL = "http://localhost:8010"
QUERY_PATH = "/api/v1/query"
RUNS = 5


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    try:
        probe = httpx.get(f"{BASE_URL}/api/v1/health", timeout=2.0)
        probe.raise_for_status()
    except (httpx.HTTPError, httpx.RequestError) as exc:
        pytest.skip(f"backend not reachable at {BASE_URL}: {exc}")
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


def _strip_wallclock(body: dict[str, Any]) -> dict[str, Any]:
    stripped = copy.deepcopy(body)
    meta = stripped.get("meta")
    if isinstance(meta, dict):
        meta.pop("query_ms", None)
    return stripped


def _run_n(client: httpx.Client, body: dict[str, Any], n: int = RUNS) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(n):
        resp = client.post(QUERY_PATH, json=body)
        assert resp.status_code == 200, f"run {i}: want 200, got {resp.status_code}: {resp.text}"
        out.append(resp.json())
    return out


# ---------------------------------------------------------------------------
# Aggregation determinism — group_by over sector with multiple aggregates
# ---------------------------------------------------------------------------


def test_sector_group_by_multi_aggregation_is_deterministic(client: httpx.Client) -> None:
    body = {
        "entity_type": "equity",
        "group_by": ["sector"],
        "aggregations": [
            {"function": "avg", "field": "rs_composite", "alias": "avg_rs"},
            {"function": "median", "field": "rs_composite", "alias": "med_rs"},
            {"function": "stddev", "field": "rs_composite", "alias": "sd_rs"},
            {"function": "count_all", "alias": "n"},
        ],
        "limit": 100,
    }
    runs = _run_n(client, body)
    baseline = _strip_wallclock(runs[0])
    for i, run in enumerate(runs[1:], start=1):
        stripped = _strip_wallclock(run)
        assert stripped == baseline, f"run {i} diverged from run 0 (excluding query_ms)"


def test_snapshot_query_is_deterministic(client: httpx.Client) -> None:
    """Snapshot mode (no ``group_by``) must also be byte-stable.

    Uses an explicit ``order_by`` so row order does not depend on the
    engine's implicit tie-breaker (which is tested implicitly by the
    aggregation case above).
    """

    body = {
        "entity_type": "equity",
        "fields": ["symbol", "sector", "rs_composite"],
        "order_by": [{"field": "symbol", "direction": "asc"}],
        "limit": 25,
    }
    runs = _run_n(client, body)
    baseline = _strip_wallclock(runs[0])
    for i, run in enumerate(runs[1:], start=1):
        stripped = _strip_wallclock(run)
        assert stripped == baseline, f"snapshot run {i} diverged from run 0"


def test_meta_envelope_fields_stable_across_runs(client: httpx.Client) -> None:
    """``data_as_of``/``record_count``/``total`` must not drift across runs."""

    body = {
        "entity_type": "equity",
        "group_by": ["sector"],
        "aggregations": [{"function": "count_all", "alias": "n"}],
        "limit": 100,
    }
    runs = _run_n(client, body)
    metas = [r.get("meta", {}) for r in runs]
    keys = ("data_as_of", "record_count", "total", "has_more", "next_offset")
    for key in keys:
        values = [m.get(key) for m in metas]
        assert all(v == values[0] for v in values), f"meta.{key} drifted across runs: {values!r}"
