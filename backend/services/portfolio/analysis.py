"""Portfolio analysis engine — per-holding + portfolio-level computations.

Reads holdings from PortfolioRepo, fetches JIP enrichment via JIPMFService,
computes portfolio-level aggregates in Decimal arithmetic.

Design contract:
- No direct SQL — all data via PortfolioRepo + JIPMFService
- All financial arithmetic in Decimal, never float
- Graceful degradation: JIP failures add to unavailable list, analysis continues
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
    HoldingAnalysis,
    PortfolioFullAnalysisResponse,
    PortfolioLevelAnalysis,
)
from backend.services.portfolio.analysis_provenance import holding_provenance, portfolio_provenance
from backend.services.portfolio.repo import PortfolioRepo

log = structlog.get_logger()

# Minimum mapped holding weight to bother computing pairwise overlap
_OVERLAP_MIN_MAPPED_HOLDINGS = 2
# Max overlap pairs to return (sorted by overlap_pct descending)
_OVERLAP_MAX_PAIRS = 5


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Convert a value to Decimal safely. None stays None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _quadrant_from_rs(
    rs_composite: Optional[Decimal],
    rs_momentum_28d: Optional[Decimal],
) -> Optional[str]:
    """Derive quadrant label from RS composite and momentum.

    Quadrants (RS Composite as proxy for relative strength):
        LEADING:   rs_composite >= 50 AND rs_momentum_28d >= 0
        IMPROVING: rs_composite < 50  AND rs_momentum_28d >= 0
        WEAKENING: rs_composite >= 50 AND rs_momentum_28d < 0
        LAGGING:   rs_composite < 50  AND rs_momentum_28d < 0
    When momentum is None, use composite alone:
        >= 50 → LEADING, < 50 → LAGGING
    """
    if rs_composite is None:
        return None
    fifty = Decimal("50")
    zero = Decimal("0")
    if rs_momentum_28d is not None:
        if rs_composite >= fifty and rs_momentum_28d >= zero:
            return "LEADING"
        if rs_composite < fifty and rs_momentum_28d >= zero:
            return "IMPROVING"
        if rs_composite >= fifty and rs_momentum_28d < zero:
            return "WEAKENING"
        return "LAGGING"
    return "LEADING" if rs_composite >= fifty else "LAGGING"


# ---------------------------------------------------------------------------
# Portfolio-level aggregate helpers (extracted to reduce CC of _compute_portfolio_level)
# ---------------------------------------------------------------------------


def _top_sectors(sectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return top 3 sectors by weight_pct, sorted descending."""
    if not sectors:
        return []
    sorted_s = sorted(sectors, key=lambda s: s.get("weight_pct") or Decimal("0"), reverse=True)
    return [
        {"sector": s.get("sector_name"), "weight_pct": s.get("weight_pct")} for s in sorted_s[:3]
    ]


def _extract_detail_metrics(detail: Optional[dict[str, Any]]) -> dict[str, Optional[Decimal]]:
    """Extract NAV + returns + derived metrics from JIP fund_detail row as a dict."""
    _fields = (
        "nav",
        "return_1m",
        "return_3m",
        "return_6m",
        "return_1y",
        "return_3y",
        "return_5y",
        "sharpe_ratio",
        "sortino_ratio",
        "alpha",
        "beta",
    )
    if detail is None:
        return {f: None for f in _fields}
    return {f: _to_decimal(detail.get(f)) for f in _fields}


def _weighted_rs(
    holding_analyses: list[HoldingAnalysis],
    zero: Decimal,
) -> Optional[Decimal]:
    """Compute value-weighted RS composite across mapped holdings."""
    rs_value_sum = zero
    rs_weight_sum = zero
    for ha in holding_analyses:
        if ha.rs_composite is not None and ha.current_value is not None:
            rs_value_sum += ha.current_value * ha.rs_composite
            rs_weight_sum += ha.current_value
    if rs_weight_sum > zero:
        return (rs_value_sum / rs_weight_sum).quantize(Decimal("0.0001"))
    return None


def _sector_weights(
    holding_analyses: list[HoldingAnalysis],
    total_value: Decimal,
    zero: Decimal,
) -> dict[str, Decimal]:
    """Compute portfolio-level sector weights proportional to holding value share."""
    sector_agg: dict[str, Decimal] = {}
    for ha in holding_analyses:
        if ha.current_value is None or total_value <= zero:
            continue
        holding_share = ha.current_value / total_value
        for sector_item in ha.top_sectors:
            sector_name = sector_item.get("sector")
            sector_pct = _to_decimal(sector_item.get("weight_pct"))
            if sector_name and sector_pct is not None:
                sector_agg[sector_name] = sector_agg.get(sector_name, zero) + (
                    holding_share * sector_pct
                )
    return {k: v.quantize(Decimal("0.01")) for k, v in sector_agg.items()}


def _quadrant_counts(holding_analyses: list[HoldingAnalysis]) -> dict[str, int]:
    """Count holdings per quadrant label."""
    distribution: dict[str, int] = {}
    for ha in holding_analyses:
        q = ha.quadrant or "UNKNOWN"
        distribution[q] = distribution.get(q, 0) + 1
    return distribution


def _weighted_risk_metrics(
    holding_analyses: list[HoldingAnalysis],
    zero: Decimal,
) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    """Compute value-weighted Sharpe, Sortino, and Beta across holdings."""
    sharpe_vs = zero
    sharpe_ws = zero
    sortino_vs = zero
    sortino_ws = zero
    beta_vs = zero
    beta_ws = zero
    for ha in holding_analyses:
        if ha.current_value is None:
            continue
        if ha.sharpe_ratio is not None:
            sharpe_vs += ha.current_value * ha.sharpe_ratio
            sharpe_ws += ha.current_value
        if ha.sortino_ratio is not None:
            sortino_vs += ha.current_value * ha.sortino_ratio
            sortino_ws += ha.current_value
        if ha.beta is not None:
            beta_vs += ha.current_value * ha.beta
            beta_ws += ha.current_value
    sharpe = (sharpe_vs / sharpe_ws).quantize(Decimal("0.0001")) if sharpe_ws > zero else None
    sortino = (sortino_vs / sortino_ws).quantize(Decimal("0.0001")) if sortino_ws > zero else None
    beta = (beta_vs / beta_ws).quantize(Decimal("0.0001")) if beta_ws > zero else None
    return sharpe, sortino, beta


class PortfolioAnalysisService:
    """Compute portfolio analysis from JIP data for a given portfolio."""

    def __init__(self, repo: PortfolioRepo, jip: JIPMFService) -> None:
        self._repo = repo
        self._jip = jip

    async def analyze_portfolio(
        self,
        portfolio_id: uuid.UUID,
        data_as_of: Optional[datetime.date] = None,
    ) -> PortfolioFullAnalysisResponse:
        """Run full analysis for a portfolio.

        Steps:
        1. Load portfolio + holdings from repo
        2. Batch-fetch RS momentum from JIP
        3. Per-holding: fetch fund_detail, sectors, weighted_technicals (parallel)
        4. Compute portfolio-level aggregates
        5. Compute pairwise overlap for mapped holdings (up to _OVERLAP_MAX_PAIRS pairs)

        Returns PortfolioFullAnalysisResponse with unavailable list for any JIP failures.
        """
        if data_as_of is None:
            data_as_of = datetime.date.today()

        portfolio = await self._repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        holdings = await self._repo.get_holdings(portfolio_id)
        log.info(
            "portfolio_analysis_start",
            portfolio_id=str(portfolio_id),
            holdings_count=len(holdings),
            data_as_of=str(data_as_of),
        )

        # --- Step 2: Batch RS fetch (one query, not N+1) ---
        rs_data_available = True
        rs_map: dict[str, dict[str, Any]] = {}
        try:
            rs_map = await self._jip.get_mf_rs_momentum_batch()
        except Exception as exc:
            log.warning(
                "portfolio_analysis_rs_batch_failed",
                portfolio_id=str(portfolio_id),
                error=str(exc),
            )
            rs_data_available = False

        # --- Step 3: Per-holding JIP enrichment (parallel) ---
        mapped_holdings = [h for h in holdings if h.mstar_id is not None]
        unmapped_holdings = [h for h in holdings if h.mstar_id is None]

        if mapped_holdings:
            enrichment_results = await asyncio.gather(
                *[self._enrich_holding(h, rs_map) for h in mapped_holdings],
                return_exceptions=True,
            )
        else:
            enrichment_results = []

        holding_analyses: list[HoldingAnalysis] = []
        unavailable: list[dict[str, Any]] = []

        for holding, enrich_out in zip(mapped_holdings, enrichment_results):
            if isinstance(enrich_out, BaseException):
                log.warning(
                    "portfolio_holding_enrich_failed",
                    holding_id=str(holding.id),
                    mstar_id=holding.mstar_id,
                    error=str(enrich_out),
                )
                unavailable.append(
                    {
                        "holding_id": str(holding.id),
                        "mstar_id": holding.mstar_id,
                        "scheme_name": holding.scheme_name,
                        "reason": str(enrich_out),
                    }
                )
            else:
                holding_analyses.append(enrich_out)

        # Compute total portfolio value (across ALL holdings, including unmapped)
        total_value = sum(
            (h.current_value for h in holdings if h.current_value is not None),
            Decimal("0"),
        )
        total_cost = sum(
            (h.cost_value for h in holdings if h.cost_value is not None),
            Decimal("0"),
        )
        # Use None if no cost data at all
        total_cost_result: Optional[Decimal] = (
            total_cost if any(h.cost_value is not None for h in holdings) else None
        )

        # Attach weight_pct to each holding analysis
        for ha in holding_analyses:
            if total_value > Decimal("0") and ha.current_value is not None:
                ha.weight_pct = (ha.current_value / total_value * Decimal("100")).quantize(
                    Decimal("0.01")
                )

        # --- Step 4: Portfolio-level aggregates ---
        portfolio_level = self._compute_portfolio_level(
            holding_analyses=holding_analyses,
            all_holdings_count=len(holdings),
            mapped_count=len(mapped_holdings),
            unmapped_count=len(unmapped_holdings),
            total_value=total_value,
            total_cost=total_cost_result,
        )

        # --- Step 5: Overlap (only if ≥2 mapped + analysed holdings) ---
        analysed_mstar_ids = [ha.mstar_id for ha in holding_analyses]
        if len(analysed_mstar_ids) >= _OVERLAP_MIN_MAPPED_HOLDINGS:
            overlap_pairs = await self._compute_overlap_pairs(analysed_mstar_ids)
            portfolio_level.overlap_pairs = overlap_pairs

        log.info(
            "portfolio_analysis_complete",
            portfolio_id=str(portfolio_id),
            holdings_analysed=len(holding_analyses),
            unavailable=len(unavailable),
            total_value=str(total_value),
            weighted_rs=str(portfolio_level.weighted_rs),
        )

        return PortfolioFullAnalysisResponse(
            portfolio_id=portfolio_id,
            portfolio_name=portfolio.name,
            data_as_of=data_as_of,
            computed_at=datetime.datetime.now(tz=datetime.timezone.utc),
            holdings=holding_analyses,
            portfolio=portfolio_level,
            unavailable=unavailable,
            rs_data_available=rs_data_available,
        )

    async def _enrich_holding(
        self,
        holding: Any,
        rs_map: dict[str, dict[str, Any]],
    ) -> HoldingAnalysis:
        """Fetch JIP data for a single holding and build HoldingAnalysis.

        Raises on JIP failure (caller handles via asyncio.gather return_exceptions).
        """
        mstar_id: str = holding.mstar_id  # guaranteed non-None by caller

        # Parallel fetch: fund_detail + sectors + weighted_technicals
        detail, sectors, wtechs = await asyncio.gather(
            self._jip.get_fund_detail(mstar_id),
            self._jip.get_fund_sectors(mstar_id),
            self._jip.get_fund_weighted_technicals(mstar_id),
        )

        # Extract RS from batch map (no extra round-trip)
        rs_row = rs_map.get(mstar_id, {})
        rs_composite = _to_decimal(rs_row.get("latest_rs_composite"))
        rs_momentum_28d = _to_decimal(rs_row.get("rs_momentum_28d"))
        quadrant = _quadrant_from_rs(rs_composite, rs_momentum_28d)

        # NAV + returns + derived metrics from JIP detail
        dm = _extract_detail_metrics(detail)
        nav_jip = dm["nav"]
        current_value: Optional[Decimal] = None

        # current_value: use JIP NAV × stored units (most accurate)
        nav_for_value = nav_jip if nav_jip is not None else _to_decimal(holding.nav)
        if nav_for_value is not None and holding.units is not None:
            units_dec = _to_decimal(holding.units)
            if units_dec is not None:
                current_value = units_dec * nav_for_value
        elif holding.current_value is not None:
            current_value = _to_decimal(holding.current_value)

        # Weighted technicals
        weighted_rsi = weighted_breadth = weighted_macd = None
        if wtechs is not None:
            weighted_rsi = _to_decimal(wtechs.get("weighted_rsi"))
            weighted_breadth = _to_decimal(wtechs.get("weighted_breadth_pct_above_200dma"))
            weighted_macd = _to_decimal(wtechs.get("weighted_macd_bullish_pct"))

        top_sectors = _top_sectors(sectors)

        # Provenance (built by helper to keep this file under 500 lines)
        provenance = holding_provenance(detail, rs_composite, wtechs, sectors)

        return HoldingAnalysis(
            holding_id=holding.id,
            mstar_id=mstar_id,
            scheme_name=holding.scheme_name,
            units=_to_decimal(holding.units) or Decimal("0"),
            nav=nav_for_value,
            current_value=current_value,
            weight_pct=None,  # filled in by caller after total_value is known
            return_1m=dm["return_1m"],
            return_3m=dm["return_3m"],
            return_6m=dm["return_6m"],
            return_1y=dm["return_1y"],
            return_3y=dm["return_3y"],
            return_5y=dm["return_5y"],
            rs_composite=rs_composite,
            rs_momentum_28d=rs_momentum_28d,
            quadrant=quadrant,
            sharpe_ratio=dm["sharpe_ratio"],
            sortino_ratio=dm["sortino_ratio"],
            alpha=dm["alpha"],
            beta=dm["beta"],
            weighted_rsi=weighted_rsi,
            weighted_breadth_pct_above_200dma=weighted_breadth,
            weighted_macd_bullish_pct=weighted_macd,
            top_sectors=top_sectors,
            provenance=provenance,
        )

    def _compute_portfolio_level(
        self,
        holding_analyses: list[HoldingAnalysis],
        all_holdings_count: int,
        mapped_count: int,
        unmapped_count: int,
        total_value: Decimal,
        total_cost: Optional[Decimal],
    ) -> PortfolioLevelAnalysis:
        """Aggregate per-holding metrics to portfolio level."""
        zero = Decimal("0")
        weighted_rs = _weighted_rs(holding_analyses, zero)
        sector_weights = _sector_weights(holding_analyses, total_value, zero)
        quadrant_distribution = _quadrant_counts(holding_analyses)
        weighted_sharpe, weighted_sortino, weighted_beta = _weighted_risk_metrics(
            holding_analyses, zero
        )
        return PortfolioLevelAnalysis(
            total_value=total_value,
            total_cost=total_cost,
            holdings_count=all_holdings_count,
            mapped_count=mapped_count,
            unmapped_count=unmapped_count,
            weighted_rs=weighted_rs,
            sector_weights=sector_weights,
            quadrant_distribution=quadrant_distribution,
            weighted_sharpe=weighted_sharpe,
            weighted_sortino=weighted_sortino,
            weighted_beta=weighted_beta,
            overlap_pairs=[],  # filled in by caller
            provenance=portfolio_provenance(),
        )

    async def _compute_overlap_pairs(
        self,
        mstar_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Compute pairwise overlap between all fund pairs.

        Returns up to _OVERLAP_MAX_PAIRS pairs sorted by overlap_pct descending.
        Failures per-pair are silently skipped (not critical).
        """
        pairs: list[tuple[str, str]] = []
        for i, a in enumerate(mstar_ids):
            for b in mstar_ids[i + 1 :]:
                pairs.append((a, b))

        if not pairs:
            return []

        results = await asyncio.gather(
            *[self._jip.get_fund_overlap(a, b) for a, b in pairs],
            return_exceptions=True,
        )

        overlap_list: list[dict[str, Any]] = []
        for (a, b), overlap_out in zip(pairs, results):
            if isinstance(overlap_out, BaseException):
                log.debug(
                    "portfolio_overlap_pair_failed",
                    mstar_id_a=a,
                    mstar_id_b=b,
                    error=str(overlap_out),
                )
                continue
            overlap_list.append(
                {
                    "mstar_id_a": overlap_out["mstar_id_a"],
                    "mstar_id_b": overlap_out["mstar_id_b"],
                    "overlap_pct": overlap_out["overlap_pct"],
                    "common_count": overlap_out["common_count"],
                }
            )

        # Sort by overlap_pct descending, return top N
        overlap_list.sort(key=lambda pair: pair.get("overlap_pct") or Decimal("0"), reverse=True)
        return overlap_list[:_OVERLAP_MAX_PAIRS]
