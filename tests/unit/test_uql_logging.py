"""Structured logging guards for the UQL surface (V2-UQL-AGG-26).

These tests are the standing contract for the FR-015 ``uql.execute`` log
event: one event per dispatch, a fixed field set on every path, no
``print()`` in production UQL code, and no PII-shaped keys leaking into
log records.

The FR-015 shape itself is exercised end-to-end in
``tests/unit/test_uql_engine.py``. This file adds the cross-cutting
guards that sit above individual dispatch flows:

1. **Field contract** — every ``uql.execute`` event carries the same
   eight-field envelope regardless of mode, dispatch, or status.
2. **Singleton rule** — one event per request, even when the engine
   raises. ``status`` flips to ``"error"`` and ``error_code`` appears,
   but the event count stays at one.
3. **No ``print()``** — static check over ``backend/routes/query.py``,
   ``backend/routes/mf.py``, and every module under
   ``backend/services/uql/``. Logging goes through ``structlog`` only.
4. **No PII keys** — log fields never contain anything that looks like
   a credential (``password``, ``token``, ``secret``, ``api_key``,
   ``authorization``). Cheap guard, catches future regressions.
5. **Route layer stays thin** — ``backend/routes/query.py`` emits no
   UQL log events of its own; it defers to the engine so request-level
   logs stay de-duplicated.
"""

from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import structlog

from backend.models.schemas import UQLFilter, UQLOperator, UQLRequest
from backend.services.uql import engine
from backend.services.uql.errors import INVALID_ENTITY_TYPE, UQLError
from backend.services.uql.optimizer import SQLPlan


# ---------------------------------------------------------------------------
# Minimal fake JIP (mirrors test_uql_engine.FakeJip without importing it so
# this test file stands alone when run in isolation).
# ---------------------------------------------------------------------------


class _FakeJip:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        freshness: dict[str, Any] | None = None,
    ) -> None:
        self.rows = rows or []
        self.freshness = (
            freshness
            if freshness is not None
            else {
                "technicals_as_of": date(2026, 4, 13),
                "mf_holdings_as_of": date(2026, 4, 13),
            }
        )

    async def execute_sql_plan(self, plan: SQLPlan) -> tuple[list[dict[str, Any]], int]:
        return list(self.rows), len(self.rows)

    async def get_data_freshness(self) -> dict[str, Any]:
        return self.freshness


REQUIRED_FR015_FIELDS: frozenset[str] = frozenset(
    {
        "event",
        "entity_type",
        "mode",
        "filter_count",
        "agg_count",
        "query_ms",
        "record_count",
        "dispatch",
        "status",
    }
)


def _uql_events(captured: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in captured if e.get("event") == "uql.execute"]


# ---------------------------------------------------------------------------
# (1) Field-contract guard — every success path carries the full envelope.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uql_execute_log_carries_full_fr015_envelope() -> None:
    request = UQLRequest(
        entity_type="equity",
        fields=["symbol", "rs_composite"],
        filters=[UQLFilter(field="sector", op=UQLOperator.EQ, value="Banking")],
        limit=5,
    )
    jip = _FakeJip(rows=[{"symbol": "HDFCBANK", "rs_composite": 82.1}])

    with structlog.testing.capture_logs() as captured:
        await engine.execute(request, jip=jip)

    events = _uql_events(captured)
    assert len(events) == 1, events
    fields = events[0]

    missing = REQUIRED_FR015_FIELDS - fields.keys()
    assert not missing, f"uql.execute missing required fields: {missing}"

    assert fields["entity_type"] == "equity"
    assert fields["mode"] == "snapshot"
    assert fields["filter_count"] == 1
    assert fields["agg_count"] == 0
    assert fields["dispatch"] == "raw"
    assert fields["status"] == "ok"
    assert isinstance(fields["query_ms"], int) and fields["query_ms"] >= 0
    assert fields["record_count"] == 1


# ---------------------------------------------------------------------------
# (2) Singleton rule — exactly one event even when the engine raises.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uql_execute_error_path_logs_exactly_once_with_error_code() -> None:
    bad = UQLRequest.model_construct(  # bypass Literal validation
        entity_type="portfolio",  # type: ignore[arg-type]
        filters=[],
        sort=[],
        group_by=None,
        aggregations=[],
        mode="snapshot",
        time_range=None,
        granularity="daily",
        fields=["symbol"],
        include=None,
        limit=10,
        offset=0,
    )
    jip = _FakeJip()

    with structlog.testing.capture_logs() as captured:
        with pytest.raises(UQLError):
            await engine.execute(bad, jip=jip)

    events = _uql_events(captured)
    assert len(events) == 1
    fields = events[0]
    assert fields["status"] == "error"
    assert fields["error_code"] == INVALID_ENTITY_TYPE
    # Envelope is still intact on the error path.
    assert REQUIRED_FR015_FIELDS <= fields.keys()


# ---------------------------------------------------------------------------
# (3) No print() in UQL modules.
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[2]
UQL_SOURCE_FILES: list[Path] = [
    REPO_ROOT / "backend" / "routes" / "query.py",
    REPO_ROOT / "backend" / "routes" / "mf.py",
    *sorted((REPO_ROOT / "backend" / "services" / "uql").glob("*.py")),
]


def _print_calls(source: str) -> list[int]:
    tree = ast.parse(source)
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            lines.append(node.lineno)
    return lines


@pytest.mark.parametrize(
    "path",
    UQL_SOURCE_FILES,
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_uql_modules_never_call_print(path: Path) -> None:
    assert path.exists(), f"missing source file: {path}"
    hits = _print_calls(path.read_text())
    assert not hits, (
        f"{path.relative_to(REPO_ROOT)} calls print() at lines {hits}; "
        "UQL modules must log via structlog only (CLAUDE.md — project conventions)."
    )


# ---------------------------------------------------------------------------
# (4) PII-key guard — log fields must not carry credential-shaped keys.
# ---------------------------------------------------------------------------


_FORBIDDEN_KEY = re.compile(r"password|token|secret|api[_-]?key|authorization", re.I)


@pytest.mark.asyncio
async def test_uql_execute_log_has_no_pii_shaped_keys() -> None:
    request = UQLRequest(
        entity_type="equity",
        fields=["symbol"],
        limit=1,
    )
    jip = _FakeJip(rows=[{"symbol": "X"}])

    with structlog.testing.capture_logs() as captured:
        await engine.execute(request, jip=jip)

    events = _uql_events(captured)
    assert len(events) == 1
    leaked = [k for k in events[0].keys() if _FORBIDDEN_KEY.search(k)]
    assert not leaked, f"uql.execute leaked credential-shaped keys: {leaked}"


# ---------------------------------------------------------------------------
# (5) Route layer stays thin — no direct uql.* log events in query.py.
# ---------------------------------------------------------------------------


def test_query_route_does_not_emit_its_own_uql_log_events() -> None:
    """The query route must defer to the engine for UQL log emission.

    Concretely: no ``log.info("uql.execute", ...)`` call inside
    ``backend/routes/query.py``. If a future change re-adds one, we'd
    double-log every request and break the FR-015 singleton guarantee.
    """

    source = (REPO_ROOT / "backend" / "routes" / "query.py").read_text()
    tree = ast.parse(source)
    offending: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match `log.<level>("uql.execute", ...)` / `logger.<level>(...)`.
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in {"info", "warning", "error", "debug", "exception"}:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            if first.value.startswith("uql."):
                offending.append(node.lineno)
    assert not offending, (
        f"backend/routes/query.py emits uql.* log events directly at lines "
        f"{offending}. Route layer must defer to engine._dispatch."
    )
