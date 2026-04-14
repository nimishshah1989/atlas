"""Brinson-Fachler attribution service for MF portfolios.

Computes allocation, selection, and interaction effects per MF category.

Brinson-Fachler formulas:
  allocation_effect   = (w_p - w_b) * (R_b_sector - R_b_total)
  selection_effect    = w_b * (R_p_sector - R_b_sector)
  interaction_effect  = (w_p - w_b) * (R_p_sector - R_b_sector)
  total_effect        = allocation + selection + interaction per category
  total_active_return = sum(total_effect) across all categories = R_p - R_b

Where:
  w_p         = portfolio weight in category (value / total_value)
  w_b         = benchmark weight (active_fund_count / total_active_funds)
  R_b_sector  = category average 1Y return from NAV history
  R_b_total   = benchmark total return (w_b-weighted avg of R_b_sector)
  R_p_sector  = portfolio return proxy: value-weighted avg manager_alpha for holdings in category

Design contract:
  - No direct SQL — all data via PortfolioRepo + JIPMFService
  - All financial arithmetic in Decimal, never float
  - Graceful degradation: returns_available=False when NAV returns unavailable
  - Deterministic: same data_as_of + same holdings + same JIP data → same output
"""

from __future__ import annotations

import asyncio
import datetime
import uuid
from decimal import Decimal
from typing import Any, Optional

import structlog

from backend.clients.jip_mf_service import JIPMFService
from backend.models.portfolio import (
    AnalysisProvenance,
    BrinsonAttributionSummary,
    BrinsonCategoryEffect,
    PortfolioAttributionResponse,
)
from backend.services.portfolio.repo import PortfolioRepo

log = structlog.get_logger()

_ZERO = Decimal("0")
_ONE = Decimal("1")
_ROUNDING = Decimal("0.000001")  # 6dp intermediate
_DISPLAY = Decimal("0.0001")  # 4dp for display


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Convert to Decimal safely. None stays None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _safe_dec(value: Any) -> Decimal:
    """Convert to Decimal, defaulting to zero on None."""
    converted = _to_decimal(value)
    return converted if converted is not None else _ZERO


def _round4(value: Decimal) -> Decimal:
    """Round to 4 decimal places for display."""
    return value.quantize(_DISPLAY)


# ---------------------------------------------------------------------------
# Pure computation helpers (no I/O, no self)
# ---------------------------------------------------------------------------


def _compute_holding_values(
    mapped_holdings: list[Any],
    fund_details: dict[str, Optional[dict[str, Any]]],
) -> dict[str, Decimal]:
    """Compute current value for each mapped holding from JIP NAV × units."""
    holding_values: dict[str, Decimal] = {}
    for holding in mapped_holdings:
        if holding.mstar_id not in fund_details:
            continue
        detail = fund_details.get(holding.mstar_id)
        nav_jip = _to_decimal(detail.get("nav") if detail else None)
        nav_for_value = nav_jip if nav_jip is not None else _to_decimal(holding.nav)
        units = _to_decimal(holding.units)
        if nav_for_value is not None and units is not None:
            current_val = units * nav_for_value
        elif holding.current_value is not None:
            current_val = _to_decimal(holding.current_value) or _ZERO
        else:
            current_val = _ZERO
        holding_values[holding.mstar_id] = current_val
    return holding_values


def _group_by_category(
    mapped_holdings: list[Any],
    holding_values: dict[str, Decimal],
    fund_details: dict[str, Optional[dict[str, Any]]],
) -> dict[str, list[str]]:
    """Group holdings by MF category_name → list of mstar_ids."""
    category_holdings: dict[str, list[str]] = {}
    for holding in mapped_holdings:
        if holding.mstar_id not in holding_values:
            continue
        detail = fund_details.get(holding.mstar_id)
        cat = (detail.get("category_name") if detail else None) or "Unknown"
        category_holdings.setdefault(cat, []).append(holding.mstar_id)
    return category_holdings


def _portfolio_weights_and_returns(
    category_holdings: dict[str, list[str]],
    holding_values: dict[str, Decimal],
    fund_details: dict[str, Optional[dict[str, Any]]],
    total_value: Decimal,
) -> tuple[dict[str, Decimal], dict[str, Optional[Decimal]]]:
    """Compute portfolio weight + return proxy per category."""
    weights: dict[str, Decimal] = {}
    returns: dict[str, Optional[Decimal]] = {}

    for cat, mstar_ids in category_holdings.items():
        cat_value = sum((holding_values.get(m, _ZERO) for m in mstar_ids), _ZERO)
        w_p = (cat_value / total_value).quantize(_ROUNDING) if total_value > _ZERO else _ZERO
        weights[cat] = w_p

        alpha_value_sum = _ZERO
        alpha_weight_sum = _ZERO
        for m in mstar_ids:
            detail = fund_details.get(m)
            alpha = _to_decimal(detail.get("manager_alpha") if detail else None)
            holding_val = holding_values.get(m, _ZERO)
            if alpha is not None and holding_val > _ZERO:
                alpha_value_sum += holding_val * alpha
                alpha_weight_sum += holding_val

        if alpha_weight_sum > _ZERO:
            returns[cat] = (alpha_value_sum / alpha_weight_sum).quantize(_ROUNDING)
        else:
            returns[cat] = None

    return weights, returns


def _compute_benchmark_total(
    benchmark_returns: dict[str, Decimal],
    benchmark_weights: dict[str, Decimal],
) -> Optional[Decimal]:
    """Compute overall benchmark return as w_b-weighted average of R_b_sector."""
    total_bw = sum(benchmark_weights.values(), _ZERO)
    if not benchmark_returns or total_bw <= _ZERO:
        return None
    r_b_total = _ZERO
    for cat, ret in benchmark_returns.items():
        bw = benchmark_weights.get(cat, _ZERO)
        r_b_total += bw * ret
    return (r_b_total / total_bw).quantize(_ROUNDING)


def _build_category_effect(
    cat: str,
    w_p: Decimal,
    w_b: Decimal,
    r_p: Optional[Decimal],
    r_b: Optional[Decimal],
    benchmark_total: Optional[Decimal],
    holding_count: int,
) -> BrinsonCategoryEffect:
    """Compute Brinson effects for a single category."""
    alloc: Optional[Decimal] = None
    if r_b is not None and benchmark_total is not None:
        alloc = _round4((w_p - w_b) * (r_b - benchmark_total))

    selec: Optional[Decimal] = None
    if r_p is not None and r_b is not None:
        selec = _round4(w_b * (r_p - r_b))

    inter: Optional[Decimal] = None
    if r_p is not None and r_b is not None:
        inter = _round4((w_p - w_b) * (r_p - r_b))

    total_eff: Optional[Decimal] = None
    if alloc is not None or selec is not None or inter is not None:
        total_eff = _round4(_safe_dec(alloc) + _safe_dec(selec) + _safe_dec(inter))

    prov = AnalysisProvenance(
        source_table="de_mf_nav_daily, de_mf_derived_daily, de_mf_master",
        formula=(
            f"alloc=(w_p-w_b)*(R_b_sector-R_b_total); "
            f"w_p={_round4(w_p)}, w_b={_round4(w_b)}, "
            f"R_b_sector={_round4(r_b) if r_b is not None else 'N/A'}, "
            f"R_b_total={_round4(benchmark_total) if benchmark_total is not None else 'N/A'}; "
            f"selection=w_b*(R_p-R_b) where R_p=value-wtd manager_alpha"
        ),
    )

    return BrinsonCategoryEffect(
        category_name=cat,
        portfolio_weight=_round4(w_p),
        benchmark_weight=_round4(w_b),
        portfolio_return=_round4(r_p) if r_p is not None else None,
        benchmark_return=_round4(r_b) if r_b is not None else None,
        allocation_effect=alloc,
        selection_effect=selec,
        interaction_effect=inter,
        total_effect=total_eff,
        holding_count=holding_count,
        provenance=prov,
    )


def _aggregate_summary(
    effects: list[BrinsonCategoryEffect],
    benchmark_total: Optional[Decimal],
) -> BrinsonAttributionSummary:
    """Aggregate category effects to portfolio-level summary."""
    has_effects = any(e.total_effect is not None for e in effects)
    if not has_effects:
        return BrinsonAttributionSummary(
            total_allocation_effect=None,
            total_selection_effect=None,
            total_interaction_effect=None,
            total_active_return=None,
            benchmark_total_return=_round4(benchmark_total) if benchmark_total else None,
        )

    alloc_effects = [e.allocation_effect for e in effects if e.allocation_effect is not None]
    selec_effects = [e.selection_effect for e in effects if e.selection_effect is not None]
    inter_effects = [e.interaction_effect for e in effects if e.interaction_effect is not None]

    total_alloc = _round4(sum(alloc_effects, _ZERO)) if alloc_effects else None
    total_selec = _round4(sum(selec_effects, _ZERO)) if selec_effects else None
    total_inter = _round4(sum(inter_effects, _ZERO)) if inter_effects else None

    total_active: Optional[Decimal] = None
    if total_alloc is not None or total_selec is not None or total_inter is not None:
        total_active = _round4(
            _safe_dec(total_alloc) + _safe_dec(total_selec) + _safe_dec(total_inter)
        )

    return BrinsonAttributionSummary(
        total_allocation_effect=total_alloc,
        total_selection_effect=total_selec,
        total_interaction_effect=total_inter,
        total_active_return=total_active,
        benchmark_total_return=_round4(benchmark_total) if benchmark_total else None,
    )


# ---------------------------------------------------------------------------
# Service class (I/O orchestration only)
# ---------------------------------------------------------------------------


class BrinsonAttributionService:
    """Compute Brinson-Fachler portfolio attribution by MF category."""

    def __init__(self, repo: PortfolioRepo, jip: JIPMFService) -> None:
        self._repo = repo
        self._jip = jip

    async def compute_attribution(
        self,
        portfolio_id: uuid.UUID,
        data_as_of: Optional[datetime.date] = None,
    ) -> PortfolioAttributionResponse:
        """Compute Brinson-Fachler attribution for a portfolio."""
        if data_as_of is None:
            data_as_of = datetime.date.today()

        portfolio = await self._repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        holdings = await self._repo.get_holdings(portfolio_id)
        mapped_holdings = [h for h in holdings if h.mstar_id is not None]

        log.info(
            "attribution_start",
            portfolio_id=str(portfolio_id),
            holdings_count=len(holdings),
            mapped_count=len(mapped_holdings),
            data_as_of=str(data_as_of),
        )

        fund_details, unavailable = await self._fetch_fund_details(mapped_holdings)
        benchmark_returns, benchmark_weights = await self._fetch_benchmark_data()

        holding_values = _compute_holding_values(mapped_holdings, fund_details)
        total_value = sum(holding_values.values(), _ZERO)
        category_holdings = _group_by_category(mapped_holdings, holding_values, fund_details)

        portfolio_weights, portfolio_returns = _portfolio_weights_and_returns(
            category_holdings,
            holding_values,
            fund_details,
            total_value,
        )

        benchmark_total = _compute_benchmark_total(benchmark_returns, benchmark_weights)
        all_categories = set(category_holdings.keys()) | set(benchmark_returns.keys())

        category_effects = [
            _build_category_effect(
                cat=cat,
                w_p=portfolio_weights.get(cat, _ZERO),
                w_b=benchmark_weights.get(cat, _ZERO),
                r_p=portfolio_returns.get(cat),
                r_b=benchmark_returns.get(cat),
                benchmark_total=benchmark_total,
                holding_count=len(category_holdings.get(cat, [])),
            )
            for cat in sorted(all_categories)
        ]

        summary = _aggregate_summary(category_effects, benchmark_total)

        log.info(
            "attribution_complete",
            portfolio_id=str(portfolio_id),
            categories=len(category_effects),
            returns_available=bool(benchmark_returns),
            total_active_return=str(summary.total_active_return),
        )

        return PortfolioAttributionResponse(
            portfolio_id=portfolio_id,
            portfolio_name=portfolio.name,
            data_as_of=data_as_of,
            computed_at=datetime.datetime.now(tz=datetime.timezone.utc),
            categories=category_effects,
            summary=summary,
            returns_available=bool(benchmark_returns),
            benchmark_description="Equal-weighted by active fund count per category from JIP",
            unavailable_holdings=unavailable,
        )

    async def _fetch_fund_details(
        self,
        mapped_holdings: list[Any],
    ) -> tuple[dict[str, Optional[dict[str, Any]]], list[dict[str, Any]]]:
        """Fetch fund detail for each mapped holding in parallel."""
        fund_details: dict[str, Optional[dict[str, Any]]] = {}
        unavailable: list[dict[str, Any]] = []
        if not mapped_holdings:
            return fund_details, unavailable

        detail_results = await asyncio.gather(
            *[self._jip.get_fund_detail(h.mstar_id) for h in mapped_holdings],
            return_exceptions=True,
        )
        for holding, detail_out in zip(mapped_holdings, detail_results):
            if isinstance(detail_out, BaseException):
                log.warning(
                    "attribution_fund_detail_failed",
                    mstar_id=holding.mstar_id,
                    error=str(detail_out),
                )
                unavailable.append(
                    {
                        "holding_id": str(holding.id),
                        "mstar_id": holding.mstar_id,
                        "scheme_name": holding.scheme_name,
                        "reason": str(detail_out),
                    }
                )
            else:
                fund_details[holding.mstar_id] = detail_out
        return fund_details, unavailable

    async def _fetch_benchmark_data(
        self,
    ) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
        """Fetch category benchmark returns and weights from JIP."""
        nav_returns_raw, category_alpha_raw = await asyncio.gather(
            self._jip.get_category_nav_returns(),
            self._jip.get_category_alpha(),
        )

        benchmark_returns: dict[str, Decimal] = {}
        benchmark_weights: dict[str, Decimal] = {}
        for row in nav_returns_raw:
            cat = row.get("category_name")
            if cat is None:
                continue
            ret = _to_decimal(row.get("avg_return_1y"))
            bw = _to_decimal(row.get("benchmark_weight"))
            if ret is not None:
                benchmark_returns[cat] = ret
            if bw is not None:
                benchmark_weights[cat] = bw

        return benchmark_returns, benchmark_weights
