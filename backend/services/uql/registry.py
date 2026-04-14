"""UQL entity registry — single source of truth for queryable entities.

Houses ``FieldType``, ``FieldSpec``, ``IndexedColumn``, ``Join``, and
``EntityDef`` frozen dataclasses plus the module-level
``REGISTRY: dict[str, EntityDef]`` for the four supported entity types
(``equity``, ``mf``, ``sector``, ``index``). The registry is the only
place SQL identifiers (table names, column names, join expressions) are
allowed to live; every other UQL module reaches in here for them.

Field whitelists are anchored against
``docs/architecture/critical-schema-facts.md`` (e.g. equity RS field is
``rs_composite``, MF category is ``category_name``). See
``specs/004-uql-aggregations/data-model.md`` §6 and research §3 for the
shape rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional


class FieldType(str, Enum):
    """Canonical field types exposed via UQL."""

    STRING = "string"
    INT = "int"
    DECIMAL = "decimal"
    BOOL = "bool"
    DATE = "date"


@dataclass(frozen=True)
class FieldSpec:
    """One whitelisted field on an entity.

    ``sql`` is the fully-qualified column expression (``alias.column``)
    used inside the optimizer's projection / filter / group_by clauses.
    """

    name: str
    sql: str
    type: FieldType
    filterable: bool = True
    aggregatable: bool = False
    groupable: bool = False
    sortable: bool = True


@dataclass(frozen=True)
class IndexedColumn:
    """An (table, column) pair backed by a database index.

    Used by ``services.uql.safety.validate_full_scan`` to decide whether
    a filter is allowed on a large entity.
    """

    table: str
    column: str


@dataclass(frozen=True)
class Join:
    """One LEFT JOIN clause stitched onto the base table."""

    table: str
    alias: str
    on: str


@dataclass(frozen=True)
class EntityDef:
    """A queryable entity — what UQL knows about one entity_type.

    ``timeseries_joins`` is an optional alternate join tuple used only in
    ``mode='timeseries'``. Snapshot/aggregation modes pin timeseries tables
    to ``date = (SELECT MAX(date)…)`` for performance, but that pin collapses
    history to one row — useless for time-range slicing. When a timeseries
    variant is set the timeseries translator uses it instead so the same
    entity exposes both modes without duplicating the registry entry.
    """

    name: str
    base_table: str
    base_alias: str
    primary_key: str
    joins: tuple[Join, ...]
    fields: dict[str, FieldSpec]
    row_count_estimate: int
    indexed_columns: frozenset[IndexedColumn]
    aggregation_only: bool = False
    timeseries_joins: Optional[tuple[Join, ...]] = None

    def field_names(self) -> frozenset[str]:
        return frozenset(self.fields.keys())

    def is_indexed(self, column: str) -> bool:
        return any(ic.column == column for ic in self.indexed_columns)


# ---------------------------------------------------------------------------
# Equity
# ---------------------------------------------------------------------------

_EQUITY_FIELDS: dict[str, FieldSpec] = {
    "id": FieldSpec("id", "i.id", FieldType.STRING, groupable=True),
    "symbol": FieldSpec("symbol", "i.current_symbol", FieldType.STRING, groupable=True),
    "company_name": FieldSpec("company_name", "i.company_name", FieldType.STRING, groupable=True),
    "sector": FieldSpec("sector", "i.sector", FieldType.STRING, groupable=True),
    "industry": FieldSpec("industry", "i.industry", FieldType.STRING, groupable=True),
    "is_active": FieldSpec("is_active", "i.is_active", FieldType.BOOL, groupable=True),
    "nifty_50": FieldSpec("nifty_50", "i.nifty_50", FieldType.BOOL, groupable=True),
    "nifty_200": FieldSpec("nifty_200", "i.nifty_200", FieldType.BOOL, groupable=True),
    "nifty_500": FieldSpec("nifty_500", "i.nifty_500", FieldType.BOOL, groupable=True),
    "cap_category": FieldSpec("cap_category", "cap.cap_category", FieldType.STRING, groupable=True),
    "rs_composite": FieldSpec(
        "rs_composite", "r.rs_composite", FieldType.DECIMAL, aggregatable=True
    ),
    "rs_1w": FieldSpec("rs_1w", "r.rs_1w", FieldType.DECIMAL, aggregatable=True),
    "rs_1m": FieldSpec("rs_1m", "r.rs_1m", FieldType.DECIMAL, aggregatable=True),
    "rs_3m": FieldSpec("rs_3m", "r.rs_3m", FieldType.DECIMAL, aggregatable=True),
    "rs_6m": FieldSpec("rs_6m", "r.rs_6m", FieldType.DECIMAL, aggregatable=True),
    "rs_12m": FieldSpec("rs_12m", "r.rs_12m", FieldType.DECIMAL, aggregatable=True),
    "close": FieldSpec("close", "t.close_adj", FieldType.DECIMAL, aggregatable=True),
    "rsi_14": FieldSpec("rsi_14", "t.rsi_14", FieldType.DECIMAL, aggregatable=True),
    "adx_14": FieldSpec("adx_14", "t.adx_14", FieldType.DECIMAL, aggregatable=True),
    "above_50dma": FieldSpec(
        "above_50dma", "t.above_50dma", FieldType.BOOL, aggregatable=True, groupable=True
    ),
    "above_200dma": FieldSpec(
        "above_200dma", "t.above_200dma", FieldType.BOOL, aggregatable=True, groupable=True
    ),
    "macd_histogram": FieldSpec(
        "macd_histogram", "t.macd_histogram", FieldType.DECIMAL, aggregatable=True
    ),
    "beta_nifty": FieldSpec("beta_nifty", "t.beta_nifty", FieldType.DECIMAL, aggregatable=True),
    "sharpe_1y": FieldSpec("sharpe_1y", "t.sharpe_1y", FieldType.DECIMAL, aggregatable=True),
    "volatility_20d": FieldSpec(
        "volatility_20d", "t.volatility_20d", FieldType.DECIMAL, aggregatable=True
    ),
    # Timeseries axis — surfaces `t.date` for mode='timeseries'. In
    # snapshot/aggregation mode the `t` join is pinned to the latest
    # partition, so this field collapses to one date per row; in
    # timeseries mode the alternate join tuple below leaves it unpinned.
    "date": FieldSpec("date", "t.date", FieldType.DATE, sortable=True),
}

_EQUITY_TIMESERIES_JOINS: tuple[Join, ...] = (
    # Technicals first — timeseries axis comes from `t.date`, unpinned.
    Join("de_equity_technical_daily", "t", "t.instrument_id = i.id"),
    # RS joined to the same day as the technicals row so rs_composite
    # lines up with close; no MAX(date) pin here.
    Join(
        "de_rs_scores",
        "r",
        "r.entity_id = i.id::text AND r.entity_type = 'equity' "
        "AND r.vs_benchmark = 'NIFTY 500' AND r.date = t.date",
    ),
    Join(
        "de_market_cap_history",
        "cap",
        "cap.instrument_id = i.id AND cap.effective_to IS NULL",
    ),
)

_EQUITY = EntityDef(
    name="equity",
    base_table="de_instrument",
    base_alias="i",
    primary_key="symbol",
    # Snapshot/aggregation joins pin each timeseries table to its latest
    # partition via `t.date = (SELECT MAX(date) ...)`. Postgres folds the
    # scalar subquery into a constant once per query, so the join then
    # rides the (date, …) pkey index — the whole equity sector rollup
    # finishes in ~100ms instead of timing out at 2s. Timeseries mode for
    # equity is intentionally unsupported via this entity (use
    # entity_type='index' for equity timeseries probes).
    joins=(
        Join(
            "de_rs_scores",
            "r",
            "r.entity_id = i.id::text AND r.entity_type = 'equity' "
            "AND r.vs_benchmark = 'NIFTY 500' "
            "AND r.date = (SELECT MAX(date) FROM de_rs_scores "
            "WHERE entity_type = 'equity' AND vs_benchmark = 'NIFTY 500')",
        ),
        Join(
            "de_equity_technical_daily",
            "t",
            "t.instrument_id = i.id AND t.date = (SELECT MAX(date) FROM de_equity_technical_daily)",
        ),
        Join(
            "de_market_cap_history",
            "cap",
            "cap.instrument_id = i.id AND cap.effective_to IS NULL",
        ),
    ),
    fields=_EQUITY_FIELDS,
    timeseries_joins=_EQUITY_TIMESERIES_JOINS,
    row_count_estimate=5_000,
    indexed_columns=frozenset(
        {
            IndexedColumn("de_instrument", "current_symbol"),
            IndexedColumn("de_instrument", "sector"),
            IndexedColumn("de_instrument", "industry"),
            IndexedColumn("de_instrument", "is_active"),
            IndexedColumn("de_instrument", "nifty_50"),
            IndexedColumn("de_instrument", "nifty_200"),
            IndexedColumn("de_instrument", "nifty_500"),
            IndexedColumn("de_market_cap_history", "cap_category"),
        }
    ),
)


# ---------------------------------------------------------------------------
# Mutual Fund
# ---------------------------------------------------------------------------

_MF_FIELDS: dict[str, FieldSpec] = {
    "mstar_id": FieldSpec("mstar_id", "m.mstar_id", FieldType.STRING, groupable=True),
    "fund_name": FieldSpec("fund_name", "m.fund_name", FieldType.STRING, groupable=True),
    "category_name": FieldSpec(
        "category_name", "m.category_name", FieldType.STRING, groupable=True
    ),
    "amc_name": FieldSpec("amc_name", "m.amc_name", FieldType.STRING, groupable=True),
    "is_etf": FieldSpec("is_etf", "m.is_etf", FieldType.BOOL, groupable=True),
    "is_active": FieldSpec("is_active", "m.is_active", FieldType.BOOL, groupable=True),
    "nav": FieldSpec("nav", "n.nav", FieldType.DECIMAL, aggregatable=True),
    "nav_date": FieldSpec("nav_date", "n.nav_date", FieldType.DATE, sortable=True),
    "aum": FieldSpec("aum", "n.aum", FieldType.DECIMAL, aggregatable=True),
    "rs_composite": FieldSpec(
        "rs_composite", "d.rs_composite", FieldType.DECIMAL, aggregatable=True
    ),
    "rs_momentum_28d": FieldSpec(
        "rs_momentum_28d", "d.rs_momentum_28d", FieldType.DECIMAL, aggregatable=True
    ),
    "manager_alpha": FieldSpec(
        "manager_alpha", "d.manager_alpha", FieldType.DECIMAL, aggregatable=True
    ),
}

_MF = EntityDef(
    name="mf",
    base_table="de_mf_master",
    base_alias="m",
    primary_key="mstar_id",
    joins=(
        Join("de_mf_nav_daily", "n", "n.mstar_id = m.mstar_id"),
        Join("de_mf_derived_daily", "d", "d.mstar_id = m.mstar_id"),
    ),
    fields=_MF_FIELDS,
    row_count_estimate=3_000,
    indexed_columns=frozenset(
        {
            IndexedColumn("de_mf_master", "mstar_id"),
            IndexedColumn("de_mf_master", "category_name"),
            IndexedColumn("de_mf_master", "amc_name"),
            IndexedColumn("de_mf_master", "is_etf"),
            IndexedColumn("de_mf_master", "is_active"),
            IndexedColumn("de_mf_nav_daily", "nav_date"),
        }
    ),
)


# ---------------------------------------------------------------------------
# Sector — aggregation-only view derived from equity
# ---------------------------------------------------------------------------

_SECTOR_FIELDS: dict[str, FieldSpec] = {
    "sector": FieldSpec("sector", "i.sector", FieldType.STRING, groupable=True),
    "rs_composite": FieldSpec(
        "rs_composite", "r.rs_composite", FieldType.DECIMAL, aggregatable=True
    ),
    "above_50dma": FieldSpec("above_50dma", "t.above_50dma", FieldType.BOOL, aggregatable=True),
    "above_200dma": FieldSpec("above_200dma", "t.above_200dma", FieldType.BOOL, aggregatable=True),
    "rsi_14": FieldSpec("rsi_14", "t.rsi_14", FieldType.DECIMAL, aggregatable=True),
    "adx_14": FieldSpec("adx_14", "t.adx_14", FieldType.DECIMAL, aggregatable=True),
}

_SECTOR = EntityDef(
    name="sector",
    base_table="de_instrument",
    base_alias="i",
    primary_key="sector",
    joins=(
        Join(
            "de_rs_scores",
            "r",
            "r.entity_id = i.id::text AND r.entity_type = 'equity' "
            "AND r.vs_benchmark = 'NIFTY 500' "
            "AND r.date = (SELECT MAX(date) FROM de_rs_scores "
            "WHERE entity_type = 'equity' AND vs_benchmark = 'NIFTY 500')",
        ),
        Join(
            "de_equity_technical_daily",
            "t",
            "t.instrument_id = i.id AND t.date = (SELECT MAX(date) FROM de_equity_technical_daily)",
        ),
    ),
    fields=_SECTOR_FIELDS,
    row_count_estimate=30,
    indexed_columns=frozenset({IndexedColumn("de_instrument", "sector")}),
    aggregation_only=True,
)


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

_INDEX_FIELDS: dict[str, FieldSpec] = {
    "index_code": FieldSpec("index_code", "x.index_code", FieldType.STRING, groupable=True),
    "index_name": FieldSpec("index_name", "x.index_name", FieldType.STRING, groupable=True),
    "close": FieldSpec("close", "d.close", FieldType.DECIMAL, aggregatable=True),
    "date": FieldSpec("date", "d.date", FieldType.DATE, sortable=True),
}

_INDEX = EntityDef(
    name="index",
    base_table="de_index_master",
    base_alias="x",
    primary_key="index_code",
    joins=(Join("de_index_price_daily", "d", "d.index_code = x.index_code"),),
    fields=_INDEX_FIELDS,
    row_count_estimate=50,
    indexed_columns=frozenset(
        {
            IndexedColumn("de_index_master", "index_code"),
            IndexedColumn("de_index_daily", "date"),
        }
    ),
)


REGISTRY: Final[dict[str, EntityDef]] = {
    "equity": _EQUITY,
    "mf": _MF,
    "sector": _SECTOR,
    "index": _INDEX,
}


def get_entity(entity_type: str) -> EntityDef:
    """Look up an entity by name. Raises ``KeyError`` on miss.

    Callers that need the §20.5 ``INVALID_ENTITY_TYPE`` envelope should
    catch ``KeyError`` and re-raise via ``UQLError``.
    """

    return REGISTRY[entity_type]


__all__ = [
    "FieldType",
    "FieldSpec",
    "IndexedColumn",
    "Join",
    "EntityDef",
    "REGISTRY",
    "get_entity",
]
