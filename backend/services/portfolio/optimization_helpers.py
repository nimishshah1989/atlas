"""Pure helpers for portfolio optimization — riskfolio runners + Decimal boundary.

Split out of optimization.py to keep both files under the modularity ceiling.
All numeric work uses float internally (Computation Boundary Pattern); the
service layer converts to Decimal at the API edge.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import numpy as np
import pandas as pd
import structlog

from backend.models.portfolio import (
    AnalysisProvenance,
    OptimizedWeight,
    SEBIConstraint,
)

log = structlog.get_logger()

_Num = type(0.0)
_to_float = _Num

_MIN_NAV_POINTS = 20
_NAV_LOOKBACK_DAYS = 365


def _to_dec4(value: _Num) -> Decimal:  # type: ignore[valid-type]
    return Decimal(str(round(value, 4)))


def _build_returns_matrix(
    nav_histories: dict[str, list[dict[str, Any]]],
) -> pd.DataFrame:
    """DataFrame of daily pct returns; only funds with ≥_MIN_NAV_POINTS rows."""
    series: dict[str, pd.Series] = {}
    for mstar_id, rows in nav_histories.items():
        if not rows:
            continue
        sorted_rows = sorted(rows, key=lambda r: r["nav_date"])
        dates = [r["nav_date"] for r in sorted_rows]
        navs = [_to_float(r["nav"]) for r in sorted_rows]
        s = pd.Series(navs, index=pd.to_datetime(dates), name=mstar_id)
        rets = s.pct_change().dropna()
        if len(rets) >= _MIN_NAV_POINTS:
            series[mstar_id] = rets

    if not series:
        return pd.DataFrame()

    df = pd.DataFrame(series)
    df = df.dropna()
    return df


def _run_mean_variance(
    returns_df: pd.DataFrame,
    max_weight: _Num,  # type: ignore[valid-type]
    max_positions: Optional[int],
) -> tuple[Optional[pd.DataFrame], str, Optional[_Num], Optional[_Num], Optional[_Num]]:  # type: ignore[valid-type]
    """Mean-variance (Sharpe max) via Riskfolio-Lib. None weights ⇒ infeasible."""
    try:
        import riskfolio as rp
    except ImportError:
        return None, "riskfolio_not_installed", None, None, None

    np.random.seed(42)

    # Pre-check: per-fund cap × num assets must be ≥ 1.0, else long-only
    # fully-invested constraint is infeasible. Riskfolio silently relaxes
    # upperlng in this case, so we detect it ourselves.
    n_assets = returns_df.shape[1]
    if n_assets * max_weight < 1.0 - 1e-9:
        return None, "infeasible", None, None, None

    port = rp.Portfolio(returns=returns_df)
    port.assets_stats(method_mu="hist", method_cov="hist")

    port.upperlng = max_weight

    if max_positions is not None and max_positions > 0:
        port.card = max_positions

    weights = port.optimization(model="Classic", rm="MV", obj="Sharpe", rf=0, l=0, hist=True)

    if weights is None:
        return None, "infeasible", None, None, None

    try:
        mu = _to_float(port.mu.values.flatten() @ weights.values.flatten())
        sigma_sq = _to_float(weights.values.flatten() @ port.cov.values @ weights.values.flatten())
        sigma = _to_float(np.sqrt(max(sigma_sq, 0.0)))
        sharpe = _to_float(mu / sigma) if sigma > 1e-10 else None
    except (AttributeError, ValueError, ZeroDivisionError):
        mu = None
        sigma = None
        sharpe = None

    return weights, "optimal", mu, sigma, sharpe


def _run_hrp(
    returns_df: pd.DataFrame,
) -> tuple[Optional[pd.DataFrame], str]:
    """Hierarchical Risk Parity via Riskfolio-Lib. None weights ⇒ failed."""
    try:
        import riskfolio as rp
    except ImportError:
        return None, "riskfolio_not_installed"

    if len(returns_df.columns) < 2:
        return None, "insufficient_assets"

    np.random.seed(42)

    hcp = rp.HCPortfolio(returns=returns_df)
    try:
        weights = hcp.optimization(
            model="HRP",
            rm="MV",
            rf=0,
            linkage="single",
            max_k=10,
            leaf_order=True,
        )
    except Exception as exc:
        log.warning("hrp_optimization_failed", error=str(exc))
        return None, "failed"

    if weights is None:
        return None, "infeasible"

    return weights, "optimal"


def _weights_to_optimized(
    weights_df: pd.DataFrame,
    fund_meta: dict[str, dict[str, Any]],
    current_weights: dict[str, Decimal],
    nav_source: str,
) -> list[OptimizedWeight]:
    """Convert riskfolio weight DataFrame to OptimizedWeight list (Decimal boundary)."""
    optimized: list[OptimizedWeight] = []
    prov = AnalysisProvenance(
        source_table=nav_source,
        formula="Riskfolio-Lib optimization on daily returns from NAV history",
    )

    for mstar_id, row in weights_df.iterrows():
        raw_weight = _to_float(row.iloc[0])
        opt_w = _to_dec4(raw_weight)
        curr_w = current_weights.get(str(mstar_id), Decimal("0"))
        meta = fund_meta.get(str(mstar_id), {})
        optimized.append(
            OptimizedWeight(
                mstar_id=str(mstar_id),
                scheme_name=meta.get("scheme_name", str(mstar_id)),
                current_weight=curr_w,
                optimized_weight=opt_w,
                weight_change=_to_dec4(_to_float(opt_w) - _to_float(curr_w)),
                provenance=prov,
            )
        )
    return optimized


def _build_sebi_constraints(
    max_weight: Decimal,
    max_positions: Optional[int],
    is_mv_binding: bool = False,
) -> list[SEBIConstraint]:
    constraints: list[SEBIConstraint] = [
        SEBIConstraint(
            constraint_id="sebi_pms_max_weight",
            constraint_type="max_weight",
            description="SEBI PMS: maximum weight per fund",
            value=max_weight,
            is_binding=is_mv_binding,
            is_violated=False,
        )
    ]
    if max_positions is not None:
        constraints.append(
            SEBIConstraint(
                constraint_id="user_max_positions",
                constraint_type="cardinality",
                description="Maximum number of positions in portfolio",
                value=Decimal(str(max_positions)),
                is_binding=False,
                is_violated=False,
            )
        )
    return constraints
