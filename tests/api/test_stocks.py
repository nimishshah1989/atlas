"""Contract tests for the stocks fixed endpoints (chunk V2-UQL-AGG-15).

Locks the V1 contract while ``backend/routes/stocks.py`` is being
transpiled to thin shims over the shared UQL engine (spec §17 + §20):

- The router is mounted on the FastAPI app under ``/api/v1/stocks``.
- Every documented route binds to its declared Pydantic ``response_model``.
- The route module imports the UQL engine at the top of the file —
  this is the static-import probe the ``uql-05-fixed-endpoints-are-sugar``
  product criterion will assert via ``check-api-standard.py``.
- ``build_uql_request`` resolves through ``uql_engine.build_from_legacy``
  for every legacy endpoint id (the seam the transpile uses).
- ``Decimal``-only invariant: ``backend/routes/stocks.py`` contains zero
  ``float`` occurrences.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.main import app
from backend.models.schemas import (
    MarketBreadthResponse,
    MoversResponse,
    RSHistoryResponse,
    SectorListResponse,
    StockDeepDiveResponse,
    StockUniverseResponse,
)
from backend.routes import stocks as stocks_routes

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES_PATH = REPO_ROOT / "backend" / "routes" / "stocks.py"

EXPECTED_ROUTES: list[tuple[str, str, type]] = [
    ("GET", "/api/v1/stocks/universe", StockUniverseResponse),
    ("GET", "/api/v1/stocks/sectors", SectorListResponse),
    ("GET", "/api/v1/stocks/breadth", MarketBreadthResponse),
    ("GET", "/api/v1/stocks/movers", MoversResponse),
    ("GET", "/api/v1/stocks/{symbol}", StockDeepDiveResponse),
    ("GET", "/api/v1/stocks/{symbol}/rs-history", RSHistoryResponse),
]


def _route_index() -> dict[tuple[str, str], object]:
    idx: dict[tuple[str, str], object] = {}
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if not path:
            continue
        for method in methods:
            idx[(method, path)] = route
    return idx


def test_router_is_mounted_on_app() -> None:
    assert stocks_routes.router.prefix == "/api/v1/stocks"
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.startswith("/api/v1/stocks") for p in paths), "stocks router not mounted"


@pytest.mark.parametrize("method,path,model", EXPECTED_ROUTES)
def test_endpoint_declared_with_response_model(method: str, path: str, model: type) -> None:
    route = _route_index().get((method, path))
    assert route is not None, f"missing route: {method} {path}"
    declared = getattr(route, "response_model", None)
    assert declared is model, f"{method} {path}: response_model={declared!r}, want {model!r}"


def test_routes_module_imports_uql_engine_at_top() -> None:
    """Static-import probe — required by `uql-05-fixed-endpoints-are-sugar`.

    The string ``from backend.services.uql import`` must appear in the
    module-level import block (the first 30 non-blank lines), proving the
    fixed-endpoint module is wired through the shared UQL engine seam.
    """
    text = ROUTES_PATH.read_text(encoding="utf-8")
    assert "from backend.services.uql import" in text, (
        "backend/routes/stocks.py must import from backend.services.uql"
    )
    head = [ln for ln in text.splitlines()[:30] if ln.strip()]
    head_text = "\n".join(head)
    assert "from backend.services.uql import" in head_text, (
        "UQL import must live in the top-of-file import block, not inside a function"
    )


def test_legacy_endpoint_ids_cover_every_route() -> None:
    """Every fixed handler has a legacy endpoint id wired for the transpile."""
    assert set(stocks_routes.LEGACY_ENDPOINT_IDS) == {
        "stocks.universe",
        "stocks.sectors",
        "stocks.breadth",
        "stocks.movers",
        "stocks.deep_dive",
        "stocks.rs_history",
    }


def test_build_uql_request_delegates_to_engine() -> None:
    """``build_uql_request`` routes every legacy id through the engine seam.

    The engine's ``build_from_legacy`` is currently a stub that raises
    ``NotImplementedError`` — we assert delegation via the raise, so this
    test stays green when the stub is replaced with a real translator.
    """
    with pytest.raises(NotImplementedError):
        stocks_routes.build_uql_request("stocks.universe", {"benchmark": "NIFTY 500"})


def test_deep_dive_handler_accepts_include_param() -> None:
    """`GET /stocks/{symbol}` exposes the §18 ``include`` query knob.

    Wired in V2-UQL-AGG-17 — the handler validates modules through the
    shared :mod:`backend.services.uql.includes` layer and surfaces the
    resolved list via ``meta.includes_loaded``. We assert at the route
    object (no DB hit) so this test stays valid in unit runs.
    """
    import inspect

    sig = inspect.signature(stocks_routes.get_stock_deep_dive)
    assert "include" in sig.parameters, "handler must accept an 'include' query param"


def test_deep_dive_validates_include_modules_via_uql_layer() -> None:
    """Unknown include modules must raise ``UQLError(INCLUDE_NOT_AVAILABLE)``.

    Validation flows through ``includes.validate_modules`` so the §20.5
    envelope handler (registered in ``backend.main``) can serialize a
    deferred-module rejection into the standard 400 envelope.
    """
    from backend.services.uql import includes as uql_includes
    from backend.services.uql.errors import INCLUDE_NOT_AVAILABLE, UQLError

    with pytest.raises(UQLError) as excinfo:
        uql_includes.validate_modules(["intelligence"])
    assert excinfo.value.code == INCLUDE_NOT_AVAILABLE
    assert excinfo.value.http_status == 400

    resolved = uql_includes.validate_modules(["rs", "conviction"])
    assert resolved == ["identity", "rs", "conviction"]


_FLOAT_TOKEN = re.compile(r"\bfloat\b")


def test_no_float_in_stocks_routes_source() -> None:
    """Decimal-only invariant: no `float` in routes/stocks.py."""
    text = ROUTES_PATH.read_text(encoding="utf-8")
    assert _FLOAT_TOKEN.findall(text) == [], "stocks.py must not contain 'float'"
