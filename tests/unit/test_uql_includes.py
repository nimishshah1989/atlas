"""Unit tests for the UQL include system (V2-UQL-AGG-12).

Exercises ``backend.services.uql.includes.resolve`` against a fake
:data:`SqlFetcher` that counts statements. No DB, no engine — pure
logic + the FR-022 N+1 guard.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pytest

from backend.services.uql import includes
from backend.services.uql.errors import INCLUDE_NOT_AVAILABLE, UQLError


class StatementCounter:
    """Async fetcher that records every (sql, params) pair it sees."""

    def __init__(self, rows_for: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []
        self._rows_for = rows_for or {}

    async def __call__(self, sql: str, params: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
        self.calls.append((sql, dict(params)))
        for keyword, rows in self._rows_for.items():
            if keyword in sql:
                return rows
        return []

    @property
    def n(self) -> int:
        return len(self.calls)


# ---------------------------------------------------------------------------
# validate_modules
# ---------------------------------------------------------------------------


def test_validate_modules_always_prefixes_identity() -> None:
    assert includes.validate_modules([]) == ["identity"]
    assert includes.validate_modules(["rs"]) == ["identity", "rs"]


def test_validate_modules_dedupes_in_order() -> None:
    out = includes.validate_modules(["rs", "rs", "technicals", "rs"])
    assert out == ["identity", "rs", "technicals"]


def test_validate_modules_keeps_caller_supplied_identity() -> None:
    out = includes.validate_modules(["identity", "rs"])
    assert out == ["identity", "rs"]


def test_validate_modules_rejects_deferred_with_named_slice() -> None:
    with pytest.raises(UQLError) as excinfo:
        includes.validate_modules(["intelligence"])
    err = excinfo.value
    assert err.code == INCLUDE_NOT_AVAILABLE
    assert err.http_status == 400
    assert "V5" in err.suggestion


def test_validate_modules_rejects_unknown_module_with_valid_set() -> None:
    with pytest.raises(UQLError) as excinfo:
        includes.validate_modules(["does_not_exist"])
    err = excinfo.value
    assert err.code == INCLUDE_NOT_AVAILABLE
    for module in includes.AVAILABLE_MODULES:
        assert module in err.suggestion


# ---------------------------------------------------------------------------
# resolve — payload composition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_identity_only_zero_side_queries() -> None:
    counter = StatementCounter()
    out = await includes.resolve(["A", "B"], ["identity"], counter)

    assert counter.n == 0
    assert out == {
        "A": {"identity": {"id": "A"}},
        "B": {"identity": {"id": "B"}},
    }


@pytest.mark.asyncio
async def test_resolve_rs_attaches_module_payload_per_id() -> None:
    counter = StatementCounter(
        rows_for={
            "de_rs_scores": [
                {
                    "entity_id": "A",
                    "rs_composite": 88,
                    "rs_1w": 1,
                    "rs_1m": 2,
                    "rs_3m": 3,
                    "rs_6m": 4,
                    "rs_12m": 5,
                },
                {
                    "entity_id": "B",
                    "rs_composite": 50,
                    "rs_1w": 0,
                    "rs_1m": 0,
                    "rs_3m": 0,
                    "rs_6m": 0,
                    "rs_12m": 0,
                },
            ]
        }
    )
    out = await includes.resolve(["A", "B", "C"], ["rs"], counter)

    assert counter.n == 1
    assert out["A"]["rs"]["rs_composite"] == 88
    assert out["B"]["rs"]["rs_composite"] == 50
    # C has no row in the side table — empty dict, not missing key.
    assert out["C"]["rs"] == {}
    # identity always attached.
    assert out["A"]["identity"] == {"id": "A"}


@pytest.mark.asyncio
async def test_resolve_unknown_module_raises_400() -> None:
    counter = StatementCounter()
    with pytest.raises(UQLError) as excinfo:
        await includes.resolve(["A"], ["intelligence"], counter)
    assert excinfo.value.code == INCLUDE_NOT_AVAILABLE
    assert counter.n == 0  # no SQL issued before validation rejects


@pytest.mark.asyncio
async def test_resolve_passes_full_id_list_to_each_resolver() -> None:
    counter = StatementCounter()
    ids = [f"ID{i}" for i in range(50)]
    await includes.resolve(ids, ["rs", "technicals"], counter)

    assert counter.n == 2
    for _sql, params in counter.calls:
        assert params["ids"] == ids


# ---------------------------------------------------------------------------
# FR-022 N+1 guard — the headline assertion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_n_plus_1_guard_50_row_list_query() -> None:
    """For a 50-row list query, total statements MUST equal 1 + len(modules - identity).

    The "1" represents the engine's base query (simulated here as a single
    pre-recorded fetch). The remainder represents the include resolvers,
    each of which MUST issue exactly one batched statement regardless of
    row count.
    """

    counter = StatementCounter()
    ids = [f"SYM{i:03d}" for i in range(50)]

    # Simulate the engine's single base query.
    await counter("SELECT id FROM de_instrument LIMIT 50", {})

    requested_modules = ["identity", "rs", "technicals", "conviction"]
    await includes.resolve(ids, requested_modules, counter)

    non_identity = [m for m in requested_modules if m != "identity"]
    expected = 1 + len(non_identity)
    assert counter.n == expected, (
        f"N+1 violation: 50-row list query with includes "
        f"{requested_modules} issued {counter.n} statements "
        f"(expected {expected})"
    )
    assert counter.n == 4
