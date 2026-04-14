"""UQL include system — N+1-safe resolvers for compound queries.

Implements ATLAS spec §18.1 ``include`` modules. Each resolver fetches one
related slice (``identity``, ``rs``, ``technicals``, ``conviction``) for a
batch of entity ids in **exactly one** round-trip, so a list query of N
rows still issues ``1 + len(include_modules - {"identity"})`` statements
total — N+1 behavior is a hard-stop defect (FR-022).

The resolver layer is deliberately decoupled from any concrete database
session: callers pass in a :data:`SqlFetcher` (an async callable that
takes ``sql, params`` and returns row mappings). The engine wires it to
``JIPDataService.execute_sql_plan``; unit tests pass an in-memory fake
that counts statements. Wired in V2-UQL-AGG-12 per
``specs/004-uql-aggregations/tasks.md`` (T036).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping, Sequence

from backend.services.uql.errors import INCLUDE_NOT_AVAILABLE, UQLError

__all__ = [
    "SqlFetcher",
    "AVAILABLE_MODULES",
    "DEFERRED_MODULES",
    "resolve",
    "validate_modules",
]

SqlFetcher = Callable[[str, Mapping[str, Any]], Awaitable[Sequence[Mapping[str, Any]]]]

AVAILABLE_MODULES: frozenset[str] = frozenset({"identity", "rs", "technicals", "conviction"})

# Modules deferred to later vertical slices. The value is the slice name
# that will land the module — surfaced verbatim in the §20.5 suggestion so
# callers know exactly when to retry.
DEFERRED_MODULES: dict[str, str] = {
    "intelligence": "V5 (intelligence engine slice)",
    "peers": "V3 (peer-graph slice)",
    "goldilocks": "V4 (goldilocks scoring slice)",
    "tv": "V6 (tradingview integration slice)",
    "holders": "V5 (intelligence engine slice)",
    "holdings": "V7 (portfolio slice)",
    "sectors": "V3 (sector-rotation slice)",
    "chart": "V6 (tradingview integration slice)",
    "qlib": "V8 (quant lab slice)",
    "anomalies": "V5 (intelligence engine slice)",
}


def validate_modules(modules: Sequence[str]) -> list[str]:
    """Return the deduped, identity-prefixed module list or raise.

    ``identity`` is always attached per §18.2, even if the caller omits
    it. Unknown modules raise :class:`UQLError` with
    ``INCLUDE_NOT_AVAILABLE`` and a suggestion that names the future
    slice (FR-022).
    """

    seen: dict[str, None] = {"identity": None}
    for raw in modules:
        if raw == "identity":
            continue
        if raw in AVAILABLE_MODULES:
            seen.setdefault(raw, None)
            continue
        if raw in DEFERRED_MODULES:
            slice_name = DEFERRED_MODULES[raw]
            raise UQLError(
                INCLUDE_NOT_AVAILABLE,
                f"include module '{raw}' is not available in this release",
                f"Module '{raw}' ships with {slice_name}.",
            )
        raise UQLError(
            INCLUDE_NOT_AVAILABLE,
            f"unknown include module '{raw}'",
            "Valid modules in this release: " + ", ".join(sorted(AVAILABLE_MODULES)) + ".",
        )
    return list(seen.keys())


async def _resolve_identity(ids: Sequence[str], _fetcher: SqlFetcher) -> dict[str, dict[str, Any]]:
    """Identity is projected from the base row — zero side-queries."""

    return {entity_id: {"id": entity_id} for entity_id in ids}


async def _resolve_rs(ids: Sequence[str], fetcher: SqlFetcher) -> dict[str, dict[str, Any]]:
    """Batch-fetch the RS slice for every id in a single statement."""

    if not ids:
        return {}
    sql = (
        "SELECT entity_id, rs_composite, rs_1w, rs_1m, rs_3m, rs_6m, rs_12m "
        "FROM de_rs_scores "
        "WHERE entity_type = 'equity' AND entity_id = ANY(:ids)"
    )
    rows = await fetcher(sql, {"ids": list(ids)})
    return {str(row["entity_id"]): dict(row) for row in rows}


async def _resolve_technicals(ids: Sequence[str], fetcher: SqlFetcher) -> dict[str, dict[str, Any]]:
    """Batch-fetch the technicals slice for every id in a single statement."""

    if not ids:
        return {}
    sql = (
        "SELECT instrument_id AS entity_id, close_adj AS close, rsi_14, adx_14, "
        "above_50dma, above_200dma, macd_histogram "
        "FROM de_equity_technical_daily "
        "WHERE instrument_id = ANY(:ids)"
    )
    rows = await fetcher(sql, {"ids": list(ids)})
    return {str(row["entity_id"]): dict(row) for row in rows}


async def _resolve_conviction(ids: Sequence[str], fetcher: SqlFetcher) -> dict[str, dict[str, Any]]:
    """Batch-fetch the conviction slice for every id in a single statement.

    Conviction is a derived score over RS + technicals; the projection
    here matches the §18.1 module contract. We issue our own batch
    statement rather than recomposing inside Python so the resolver
    contract stays uniform: one module = one statement.
    """

    if not ids:
        return {}
    sql = (
        "SELECT entity_id, conviction_score, conviction_band, conviction_reason "
        "FROM atlas_conviction_daily "
        "WHERE entity_id = ANY(:ids)"
    )
    rows = await fetcher(sql, {"ids": list(ids)})
    return {str(row["entity_id"]): dict(row) for row in rows}


_RESOLVERS: dict[
    str,
    Callable[[Sequence[str], SqlFetcher], Awaitable[dict[str, dict[str, Any]]]],
] = {
    "identity": _resolve_identity,
    "rs": _resolve_rs,
    "technicals": _resolve_technicals,
    "conviction": _resolve_conviction,
}


async def resolve(
    ids: Sequence[str],
    modules: Sequence[str],
    fetcher: SqlFetcher,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Resolve every requested ``include`` module for ``ids``.

    Returns a nested mapping ``{entity_id: {module: payload}}``. Missing
    payloads (no row in the side table for an id) yield an empty dict so
    the engine can still attach the module key consistently.

    Issues exactly ``len(modules - {"identity"})`` SQL statements via
    ``fetcher``; ``identity`` is projected in-process. Combined with the
    engine's single base query, this satisfies the FR-022 N+1 ceiling
    (1 + len(modules - {"identity"})).
    """

    resolved_modules = validate_modules(modules)
    out: dict[str, dict[str, dict[str, Any]]] = {entity_id: {} for entity_id in ids}
    for module in resolved_modules:
        payloads = await _RESOLVERS[module](ids, fetcher)
        for entity_id in ids:
            out[entity_id][module] = payloads.get(entity_id, {})
    return out
