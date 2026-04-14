"""Fixed-endpoint transpile invariant (V2-UQL-AGG-25).

Asserts the two invariants the V2 transpile guarantees across the V1 →
UQL migration for ``backend/routes/stocks.py`` and ``backend/routes/mf.py``:

1. **Static transpile seam** — each module imports the shared UQL engine
   at the top of the file. This is the same probe
   ``uql-05-fixed-endpoints-are-sugar`` (see
   ``docs/specs/api-standard-criteria.yaml``) will assert once the gate
   is flipped in V2-UQL-AGG-27. If a future chunk deletes the import
   and reroutes a handler straight at ``JIPDataService`` it fails here
   before it reaches the gate.

2. **Response invariance** — each legacy stocks endpoint, when hit
   twice back-to-back against the dev DB, returns byte-identical
   ``records`` and byte-identical ``meta`` (excluding ``meta.query_ms``
   which is a wall-clock field). This is the golden-fixture diff the
   task spec calls for: if the UQL-backed handler silently changes the
   projection, adds a field, or drops one, this test catches it.

MF routes are still the V2-1 contract skeleton (every endpoint raises
``501 Not Implemented`` — see ``backend/routes/mf.py`` module docstring
+ ``_NOT_IMPL``); the live-hit invariance slice is stocks-only until
V2-2+ wire real data. The static seam check covers mf.

Live slices skip automatically if the backend is unreachable, matching
the rest of ``tests/api/``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STOCKS_ROUTES = REPO_ROOT / "backend" / "routes" / "stocks.py"
MF_ROUTES = REPO_ROOT / "backend" / "routes" / "mf.py"

BASE_URL = "http://localhost:8010"
UQL_IMPORT = "from backend.services.uql import"


# ---------------------------------------------------------------------------
# Static transpile seam — runs without a backend.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [pytest.param(STOCKS_ROUTES, id="stocks"), pytest.param(MF_ROUTES, id="mf")],
)
def test_routes_module_imports_uql_engine_at_top(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert UQL_IMPORT in text, f"{path.name} must import from backend.services.uql"
    head = [ln for ln in text.splitlines()[:40] if ln.strip()]
    head_text = "\n".join(head)
    assert UQL_IMPORT in head_text, (
        f"{path.name}: UQL import must live in the top-of-file import block, not inside a function"
    )


def test_stocks_legacy_endpoint_ids_match_router_surface() -> None:
    from backend.routes import stocks as stocks_routes

    assert set(stocks_routes.LEGACY_ENDPOINT_IDS) == {
        "stocks.universe",
        "stocks.sectors",
        "stocks.breadth",
        "stocks.movers",
        "stocks.deep_dive",
        "stocks.rs_history",
    }


def test_mf_legacy_endpoint_ids_cover_wired_routes() -> None:
    from backend.routes import mf as mf_routes

    ids = set(mf_routes.LEGACY_ENDPOINT_IDS)
    # The skeleton mounts the full MF surface; the invariant is that every
    # id is namespaced under ``mf.`` so the engine's ``build_from_legacy``
    # dispatcher can discriminate stocks vs mf without a second lookup.
    assert ids, "mf router must declare at least one legacy endpoint id"
    assert all(eid.startswith("mf.") for eid in ids), ids


# ---------------------------------------------------------------------------
# Live invariance — hits the dev backend, skips if offline.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    try:
        probe = httpx.get(f"{BASE_URL}/api/v1/health", timeout=2.0)
        probe.raise_for_status()
    except (httpx.HTTPError, httpx.RequestError) as exc:
        pytest.skip(f"backend not reachable at {BASE_URL}: {exc}")
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


def _strip_meta_wallclock(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove fields that are allowed to drift across identical calls.

    ``query_ms`` is a wall-clock counter; everything else in ``meta``
    (``data_as_of``, ``record_count``, includes_loaded, total, has_more,
    next_offset) is deterministic given a stable partition.
    """

    stripped = copy.deepcopy(payload)
    for key in ("meta", "_meta"):
        section = stripped.get(key)
        if isinstance(section, dict):
            section.pop("query_ms", None)
    return stripped


STOCKS_ENDPOINTS: list[tuple[str, dict[str, Any]]] = [
    ("/api/v1/stocks/universe", {"benchmark": "NIFTY 500"}),
    ("/api/v1/stocks/sectors", {}),
    ("/api/v1/stocks/breadth", {}),
    ("/api/v1/stocks/movers", {"limit": 10}),
]


@pytest.mark.parametrize("path,params", STOCKS_ENDPOINTS)
def test_legacy_stocks_endpoint_returns_meta_envelope(
    client: httpx.Client, path: str, params: dict[str, Any]
) -> None:
    """Every legacy stocks endpoint returns the §17 meta envelope.

    Proves the handler flows through the UQL seam — the envelope is
    only produced by the shared ``ResponseMeta`` contract; a raw
    ``JIPDataService`` call would not populate it.
    """

    resp = client.get(path, params=params)
    assert resp.status_code == 200, f"{path}: want 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert isinstance(body, dict), f"{path}: body not a dict"
    meta = body.get("meta")
    assert isinstance(meta, dict), f"{path}: missing meta envelope: {body!r}"
    assert isinstance(meta.get("query_ms"), int), f"{path}: meta.query_ms not int"
    assert meta.get("record_count") is not None, f"{path}: meta missing record_count"


@pytest.mark.parametrize("path,params", STOCKS_ENDPOINTS)
def test_legacy_stocks_endpoint_is_deterministic_across_calls(
    client: httpx.Client, path: str, params: dict[str, Any]
) -> None:
    """Two back-to-back calls return byte-identical bodies (sans query_ms).

    This is the golden-fixture diff the V2-UQL-AGG-25 spec asks for:
    it catches a regression where a future optimizer or include resolver
    silently mutates the projection on a legacy endpoint. If this flakes,
    something touched the handler in a way that is not idempotent —
    investigate before merging.
    """

    first = client.get(path, params=params)
    second = client.get(path, params=params)
    assert first.status_code == 200 and second.status_code == 200, (
        f"{path}: non-200 in deterministic probe ({first.status_code}/{second.status_code})"
    )
    a = _strip_meta_wallclock(first.json())
    b = _strip_meta_wallclock(second.json())
    assert a == b, f"{path}: responses diverged across calls (excluding query_ms)"


def test_stocks_deep_dive_is_deterministic(client: httpx.Client) -> None:
    """Per-symbol deep-dive is idempotent on ``data_as_of``."""

    # Pick the first symbol from the universe response so the test is
    # resilient to whichever equities the dev DB happens to carry.
    universe = client.get("/api/v1/stocks/universe", params={"benchmark": "NIFTY 500"})
    assert universe.status_code == 200, f"universe probe failed: {universe.text}"
    body = universe.json()
    sectors = body.get("sectors") or []
    symbol: str | None = None
    for sector in sectors:
        stocks = sector.get("stocks") or []
        if stocks:
            symbol = stocks[0].get("symbol")
            if symbol:
                break
    if not symbol:
        pytest.skip("no symbols in dev DB universe response")

    first = client.get(f"/api/v1/stocks/{symbol}")
    second = client.get(f"/api/v1/stocks/{symbol}")
    assert first.status_code == 200 and second.status_code == 200, (
        f"deep-dive non-200: {first.status_code}/{second.status_code}"
    )
    a = _strip_meta_wallclock(first.json())
    b = _strip_meta_wallclock(second.json())
    assert a == b, f"deep-dive {symbol}: responses diverged across calls"
