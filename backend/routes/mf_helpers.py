"""MF route helpers — pure functions extracted from mf.py for modularity."""

import datetime
from collections import defaultdict
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.clients.sql_fragments import safe_decimal
from backend.models.mf import (
    BroadCategoryGroup,
    CategoryGroup,
    ConvictionPillarsMF,
    Fund,
    FundDailyMetrics,
    FundIdentity,
    Holding,
    MFLifecycleEvent,
    PillarFlows,
    PillarHoldingsQuality,
    PillarPerformance,
    PillarRSStrength,
    Staleness,
    StalenessFlag,
    WeightedTechnicalsSummary,
)
from backend.services.mf_compute import classify_fund_quadrant
from backend.services.uql import engine as uql_engine

log = structlog.get_logger()

_NOT_IMPL = "MF endpoint not yet wired (V2-1 contract skeleton)"

LEGACY_ENDPOINT_IDS: tuple[str, ...] = (
    "mf.universe",
    "mf.categories",
    "mf.flows",
    "mf.overlap",
    "mf.holding_stock",
    "mf.deep_dive",
    "mf.holdings",
    "mf.sectors",
    "mf.rs_history",
    "mf.weighted_technicals",
    "mf.nav_history",
)


async def rs_momentum_or_empty(svc: JIPDataService, db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Fetch rs_momentum batch; fall back to {} on DB errors."""
    try:
        return await svc.get_mf_rs_momentum_batch()
    except SQLAlchemyError as exc:
        log.warning("mf_rs_momentum_unavailable", error=str(exc)[:200])
        try:
            await db.rollback()
        except SQLAlchemyError:
            pass
        return {}
    except RuntimeError as exc:
        log.info("mf_rs_momentum_unavailable_cached", error=str(exc)[:200])
        return {}


async def gather_universe_data(
    svc: JIPDataService,
    db: AsyncSession,
    *,
    benchmark: Optional[str],
    category: Optional[str],
    broad_category: Optional[str],
    active_only: bool,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch universe rows, RS batch, and freshness sequentially."""
    rows = await svc.get_mf_universe(
        benchmark=benchmark,
        category=category,
        broad_category=broad_category,
        active_only=active_only,
    )
    rs_batch = await rs_momentum_or_empty(svc, db)
    freshness = await svc.get_mf_data_freshness()
    return rows, rs_batch, freshness


def build_uql_request(endpoint_id: str, params: dict[str, Any]) -> Any:
    """Translate a legacy mf endpoint call into a UQLRequest."""
    return uql_engine.build_from_legacy(endpoint_id, params)


def not_implemented() -> HTTPException:
    return HTTPException(status_code=501, detail=_NOT_IMPL)


def compute_staleness(freshness: dict[str, Any], source: str = "jip") -> Staleness:
    """Compute staleness from JIP freshness data."""
    nav_as_of = freshness.get("nav_as_of")
    if nav_as_of is None:
        return Staleness(source=source, age_minutes=99999, flag=StalenessFlag.EXPIRED)

    if isinstance(nav_as_of, datetime.datetime):
        nav_date = nav_as_of.date()
    elif isinstance(nav_as_of, datetime.date):
        nav_date = nav_as_of
    else:
        try:
            nav_date = datetime.date.fromisoformat(str(nav_as_of))
        except (ValueError, TypeError):
            return Staleness(source=source, age_minutes=99999, flag=StalenessFlag.EXPIRED)

    today = datetime.date.today()
    age_days = (today - nav_date).days
    age_minutes = age_days * 24 * 60

    if age_minutes < 1440:
        flag = StalenessFlag.FRESH
    elif age_minutes < 2880:
        flag = StalenessFlag.STALE
    else:
        flag = StalenessFlag.EXPIRED

    return Staleness(source=source, age_minutes=age_minutes, flag=flag)


def data_as_of_from_freshness(freshness: dict[str, Any]) -> datetime.date:
    """Extract data_as_of date from freshness dict, defaulting to today."""
    nav_as_of = freshness.get("nav_as_of")
    if nav_as_of is None:
        return datetime.date.today()
    if isinstance(nav_as_of, datetime.datetime):
        return nav_as_of.date()
    if isinstance(nav_as_of, datetime.date):
        return nav_as_of
    try:
        return datetime.date.fromisoformat(str(nav_as_of))
    except (ValueError, TypeError):
        return datetime.date.today()


def enrich_universe_row_to_fund(
    universe_row: dict[str, Any],
    rs_batch: dict[str, dict[str, Any]],
) -> Fund:
    """Build a Fund model from a JIP universe row, enriched with RS momentum + quadrant."""
    mstar_id = universe_row.get("mstar_id", "")
    momentum_data = rs_batch.get(mstar_id, {})
    rs_composite = safe_decimal(
        universe_row.get("derived_rs_composite") or universe_row.get("rs_composite")
    )
    rs_momentum_28d = momentum_data.get("rs_momentum_28d") if momentum_data else None
    return Fund(
        mstar_id=mstar_id,
        fund_name=universe_row.get("fund_name", ""),
        amc_name=universe_row.get("amc_name", ""),
        category_name=universe_row.get("category_name", ""),
        broad_category=universe_row.get("broad_category", ""),
        nav=safe_decimal(universe_row.get("nav")),
        nav_date=universe_row.get("nav_date"),
        rs_composite=rs_composite,
        rs_momentum_28d=rs_momentum_28d,
        quadrant=classify_fund_quadrant(rs_composite, rs_momentum_28d),
        manager_alpha=safe_decimal(universe_row.get("manager_alpha")),
        expense_ratio=safe_decimal(universe_row.get("expense_ratio")),
        is_index_fund=bool(universe_row.get("is_index_fund", False)),
        primary_benchmark=universe_row.get("primary_benchmark"),
    )


def group_funds_by_broad_category(
    universe_rows: list[dict[str, Any]],
    rs_batch: dict[str, dict[str, Any]],
) -> list[BroadCategoryGroup]:
    """Group flat JIP universe rows into BroadCategoryGroup hierarchy."""
    funds_by_broad: dict[str, dict[str, list[Fund]]] = defaultdict(lambda: defaultdict(list))
    for universe_row in universe_rows:
        fund = enrich_universe_row_to_fund(universe_row, rs_batch)
        bc = universe_row.get("broad_category") or "Unknown"
        cn = universe_row.get("category_name") or "Unknown"
        funds_by_broad[bc][cn].append(fund)
    return [
        BroadCategoryGroup(
            name=bc,
            categories=[CategoryGroup(name=cn, funds=funds) for cn, funds in cat_map.items()],
        )
        for bc, cat_map in funds_by_broad.items()
    ]


def parse_as_of_date(raw: Any) -> datetime.date:
    """Coerce an as_of_date from a DB row to datetime.date."""
    if isinstance(raw, datetime.datetime):
        return raw.date()
    if isinstance(raw, datetime.date):
        return raw
    return datetime.date.today()


def map_holding_row(row: dict[str, Any]) -> Optional[Holding]:
    """Convert a JIP holding row to a Holding model."""
    weight_pct = safe_decimal(row.get("weight_pct"))
    if weight_pct is None:
        return None
    return Holding(
        instrument_id=str(row.get("instrument_id") or ""),
        symbol=str(row.get("current_symbol") or row.get("symbol") or ""),
        holding_name=str(row.get("holding_name") or ""),
        weight_pct=weight_pct,
        shares_held=safe_decimal(row.get("shares_held")),
        market_value=safe_decimal(row.get("market_value")),
        sector=row.get("sector") or row.get("sector_code"),
        rs_composite=safe_decimal(row.get("rs_composite")),
        above_200dma=row.get("above_200dma"),
    )


def build_deep_dive_identity(detail: dict[str, Any]) -> FundIdentity:
    """Extract FundIdentity from JIP fund detail row."""
    return FundIdentity(
        mstar_id=detail["mstar_id"],
        fund_name=detail.get("fund_name", ""),
        amc_name=detail.get("amc_name", ""),
        category_name=detail.get("category_name", ""),
        broad_category=detail.get("broad_category", ""),
        primary_benchmark=detail.get("primary_benchmark"),
        inception_date=detail.get("inception_date"),
        is_index_fund=bool(detail.get("is_index_fund", False)),
    )


def build_deep_dive_daily(detail: dict[str, Any]) -> FundDailyMetrics:
    """Extract FundDailyMetrics from JIP fund detail row."""
    return FundDailyMetrics(
        nav=safe_decimal(detail.get("nav")),
        nav_date=detail.get("nav_date"),
        expense_ratio=safe_decimal(detail.get("expense_ratio")),
    )


def build_deep_dive_pillars(
    detail: dict[str, Any],
    derived_rs: Optional[Decimal],
    rs_momentum_28d: Optional[Decimal],
    quadrant: Optional[Any],
) -> ConvictionPillarsMF:
    """Build conviction pillars from detail + computed RS values."""
    return ConvictionPillarsMF(
        performance=PillarPerformance(
            manager_alpha=safe_decimal(detail.get("manager_alpha")),
            information_ratio=safe_decimal(detail.get("information_ratio")),
        ),
        rs_strength=PillarRSStrength(
            rs_composite=derived_rs,
            rs_momentum_28d=rs_momentum_28d,
            quadrant=quadrant,
        ),
        flows=PillarFlows(),
        holdings_quality=PillarHoldingsQuality(),
    )


def build_weighted_technicals(detail: dict[str, Any]) -> WeightedTechnicalsSummary:
    """Extract weighted technicals summary from JIP fund detail row."""
    weighted_as_of = detail.get("weighted_as_of")
    if isinstance(weighted_as_of, datetime.datetime):
        as_of_date: Optional[datetime.date] = weighted_as_of.date()
    elif isinstance(weighted_as_of, datetime.date):
        as_of_date = weighted_as_of
    else:
        as_of_date = None
    return WeightedTechnicalsSummary(
        weighted_rsi=safe_decimal(detail.get("weighted_rsi")),
        weighted_breadth_pct_above_200dma=safe_decimal(
            detail.get("weighted_breadth_pct_above_200dma")
        ),
        weighted_macd_bullish_pct=safe_decimal(detail.get("weighted_macd_bullish_pct")),
        as_of_date=as_of_date,
    )


def build_lifecycle_event(
    lifecycle_events: list[dict[str, Any]],
) -> Optional[MFLifecycleEvent]:
    """Build MFLifecycleEvent from first lifecycle row, if any."""
    if not lifecycle_events:
        return None
    first = lifecycle_events[0]
    effective_date = first.get("effective_date")
    if isinstance(effective_date, datetime.datetime):
        effective_date = effective_date.date()
    if effective_date is None:
        return None
    return MFLifecycleEvent(
        event_type=str(first.get("event_type", "")),
        effective_date=effective_date,
        detail=first.get("detail"),
    )
