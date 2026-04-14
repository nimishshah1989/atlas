"""Provenance builders for portfolio analysis metrics.

Each function returns a dict mapping metric name → AnalysisProvenance.
Extracted from analysis.py to keep that module under 500 lines.
"""

from __future__ import annotations

from typing import Any, Optional
from decimal import Decimal

from backend.models.portfolio import AnalysisProvenance


def holding_provenance(
    detail: Optional[dict[str, Any]],
    rs_composite: Optional[Decimal],
    wtechs: Optional[dict[str, Any]],
    sectors: list[dict[str, Any]],
) -> dict[str, AnalysisProvenance]:
    """Build provenance for per-holding metrics."""
    provenance: dict[str, AnalysisProvenance] = {}

    if detail is not None:
        provenance["nav"] = AnalysisProvenance(
            source_table="de_mf_nav_daily",
            formula=(
                "Latest NAV from de_mf_nav_daily"
                " WHERE mstar_id = :mstar_id ORDER BY nav_date DESC LIMIT 1"
            ),
        )
        provenance["returns"] = AnalysisProvenance(
            source_table="de_mf_derived_daily",
            formula="return_Nm = (nav_today / nav_N_months_ago) - 1 from de_mf_derived_daily",
        )
        provenance["sharpe_ratio"] = AnalysisProvenance(
            source_table="de_mf_derived_daily",
            formula=(
                "(annualized_return - risk_free_rate) / annualized_stddev from de_mf_derived_daily"
            ),
        )

    if rs_composite is not None:
        provenance["rs_composite"] = AnalysisProvenance(
            source_table="de_rs_scores",
            formula=(
                "latest_rs_composite from de_rs_scores"
                " WHERE entity_type='MF' AND entity_id=mstar_id"
            ),
        )
        provenance["rs_momentum_28d"] = AnalysisProvenance(
            source_table="de_rs_scores",
            formula="latest_rs_composite - past_rs_composite (28 days ago) from de_rs_scores",
        )

    if wtechs is not None:
        provenance["weighted_technicals"] = AnalysisProvenance(
            source_table="de_mf_weighted_technicals",
            formula="Holdings-weighted RSI/breadth/MACD from de_mf_weighted_technicals",
        )

    if sectors:
        provenance["sectors"] = AnalysisProvenance(
            source_table="de_mf_sector_exposure",
            formula="sector weight_pct from de_mf_sector_exposure at latest as_of_date",
        )

    return provenance


def portfolio_provenance() -> dict[str, AnalysisProvenance]:
    """Build provenance for portfolio-level aggregates."""
    return {
        "weighted_rs": AnalysisProvenance(
            source_table="de_rs_scores",
            formula=(
                "sum(holding_value * rs_composite) / sum(holding_value) across mapped holdings"
            ),
        ),
        "sector_weights": AnalysisProvenance(
            source_table="de_mf_sector_exposure",
            formula=(
                "sum(holding_share * sector_weight_pct) for each sector,"
                " where holding_share = holding_value / total_value"
            ),
        ),
        "quadrant_distribution": AnalysisProvenance(
            source_table="de_rs_scores",
            formula=(
                "count(holdings) per quadrant; quadrant derived from rs_composite + rs_momentum_28d"
            ),
        ),
        "weighted_sharpe": AnalysisProvenance(
            source_table="de_mf_derived_daily",
            formula=(
                "sum(holding_value * sharpe_ratio)"
                " / sum(holding_value) across holdings with sharpe data"
            ),
        ),
    }
