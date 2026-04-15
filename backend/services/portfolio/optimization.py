"""Portfolio optimization service — mean-variance and HRP via Riskfolio-Lib.

Fetches NAV history for each mapped holding, builds a returns matrix,
and runs Riskfolio-Lib optimizations under SEBI constraints.

Design contract:
- No direct SQL — all data via PortfolioRepo + JIPMFService
- float internally for numpy/riskfolio computation (Computation Boundary Pattern)
- Decimal(str(round(val, 4))) at API boundary
- Deterministic: np.random.seed(42) before each solve; same inputs → same outputs
- Graceful degradation: funds with insufficient NAV excluded, not raised
- Infeasibility returns structured error (solver_status != "optimal")
"""

from __future__ import annotations

import datetime
import time
import uuid
from decimal import Decimal
from typing import Any, Optional

import pandas as pd
import structlog

from backend.clients.jip_mf_service import JIPMFService
from backend.models.portfolio import (
    AnalysisProvenance,
    OptimizationModel,
    OptimizationResult,
    PortfolioOptimizationResponse,
)
from backend.services.portfolio.optimization_helpers import (
    _MIN_NAV_POINTS,
    _NAV_LOOKBACK_DAYS,
    _Num,
    _build_returns_matrix,
    _build_sebi_constraints,
    _run_hrp,
    _run_mean_variance,
    _to_dec4,
    _to_float,
    _weights_to_optimized,
)
from backend.services.portfolio.repo import PortfolioRepo

log = structlog.get_logger()


class PortfolioOptimizationService:
    """Portfolio optimization using Riskfolio-Lib.

    Constructor takes repo + jip (same pattern as PortfolioAnalysisService).
    All financial values use Decimal at the API boundary (Computation Boundary Pattern).
    Float is used internally for numpy/riskfolio computation only.
    """

    def __init__(self, repo: PortfolioRepo, jip: JIPMFService) -> None:
        self._repo = repo
        self._jip = jip

    async def optimize_portfolio(
        self,
        portfolio_id: uuid.UUID,
        data_as_of: Optional[datetime.date],
        risk_profile: str,
        models: list[str],
        max_weight: Decimal,
        max_positions: Optional[int],
    ) -> PortfolioOptimizationResponse:
        """Run portfolio optimization for the requested models."""
        if data_as_of is None:
            data_as_of = datetime.date.today()
        computed_at = datetime.datetime.now(tz=datetime.timezone.utc)

        portfolio = await self._repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        current_weights, fund_meta, mstar_ids, mapped_holdings = await self._prepare_holdings(
            portfolio_id
        )
        date_to = data_as_of.isoformat()
        nav_histories, excluded_funds = await self._fetch_nav_histories(
            mapped_holdings,
            mstar_ids,
            data_as_of,
        )
        returns_df = _build_returns_matrix(nav_histories)
        kept_ids = set(returns_df.columns.tolist())
        self._track_dropped_funds(nav_histories, kept_ids, fund_meta, excluded_funds)

        if not kept_ids:
            raise ValueError(
                "No candidate funds with sufficient NAV history for optimization. "
                f"Excluded: {[e['mstar_id'] for e in excluded_funds]}"
            )

        nav_source = "de_mf_nav_daily"
        results = self._run_models(
            models,
            returns_df,
            max_weight,
            max_positions,
            fund_meta,
            current_weights,
            nav_source,
            portfolio_id,
            len(kept_ids),
        )
        return self._build_response(
            portfolio_id,
            portfolio.name,
            data_as_of,
            computed_at,
            results,
            len(kept_ids),
            excluded_funds,
            nav_source,
            date_to,
        )

    @staticmethod
    def _track_dropped_funds(
        nav_histories: dict[str, list[dict[str, Any]]],
        kept_ids: set[str],
        fund_meta: dict[str, dict[str, Any]],
        excluded_funds: list[dict[str, Any]],
    ) -> None:
        """Record funds dropped by the returns matrix (all-NaN columns etc.)."""
        for mid in list(nav_histories.keys()):
            if mid not in kept_ids:
                excluded_funds.append(
                    {
                        "mstar_id": mid,
                        "scheme_name": fund_meta.get(mid, {}).get("scheme_name", mid),
                        "reason": "Returns matrix dropped fund (insufficient aligned dates)",
                    }
                )

    @staticmethod
    def _build_response(
        portfolio_id: uuid.UUID,
        portfolio_name: Optional[str],
        data_as_of: datetime.date,
        computed_at: datetime.datetime,
        results: list[OptimizationResult],
        candidate_count: int,
        excluded_funds: list[dict[str, Any]],
        nav_source: str,
        date_to: str,
    ) -> PortfolioOptimizationResponse:
        """Assemble the final optimization response."""
        prov = AnalysisProvenance(
            source_table=nav_source,
            formula=(
                "Riskfolio-Lib 7.2.1: MV=Classic/MV/Sharpe; HRP=HCPortfolio/HRP/MV. "
                "Returns: daily pct_change on NAV. "
                f"Lookback: {_NAV_LOOKBACK_DAYS}d ending {date_to}."
            ),
        )
        return PortfolioOptimizationResponse(
            portfolio_id=portfolio_id,
            portfolio_name=portfolio_name,
            data_as_of=data_as_of,
            computed_at=computed_at,
            models=results,
            candidate_count=candidate_count,
            excluded_funds=excluded_funds,
            provenance={"optimization": prov},
        )

    async def _prepare_holdings(
        self,
        portfolio_id: uuid.UUID,
    ) -> tuple[dict[str, Decimal], dict[str, dict[str, Any]], list[str], list[Any]]:
        """Load holdings, compute current weights, build metadata map."""
        holdings = await self._repo.get_holdings(portfolio_id)
        mapped_holdings = [h for h in holdings if h.mstar_id]

        if not mapped_holdings:
            raise ValueError(f"Portfolio {portfolio_id} has no mapped holdings — cannot optimize")

        mstar_ids: list[str] = [h.mstar_id for h in mapped_holdings if h.mstar_id is not None]

        total_value = sum(
            _to_float(h.current_value) for h in mapped_holdings if h.current_value is not None
        )
        current_weights: dict[str, Decimal] = {}
        if total_value > 0:
            for h, mid in zip(mapped_holdings, mstar_ids):
                cv = _to_float(h.current_value) if h.current_value is not None else 0.0
                current_weights[mid] = _to_dec4(cv / total_value)

        fund_meta: dict[str, dict[str, Any]] = {
            mid: {"scheme_name": h.scheme_name} for h, mid in zip(mapped_holdings, mstar_ids)
        }
        return current_weights, fund_meta, mstar_ids, mapped_holdings

    async def _fetch_nav_histories(
        self,
        mapped_holdings: list[Any],
        mstar_ids: list[str],
        data_as_of: datetime.date,
    ) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        """Fetch NAV history for each holding; partition into available vs excluded."""
        date_from = (data_as_of - datetime.timedelta(days=_NAV_LOOKBACK_DAYS)).isoformat()
        date_to = data_as_of.isoformat()

        nav_histories: dict[str, list[dict[str, Any]]] = {}
        excluded_funds: list[dict[str, Any]] = []

        for h, mid in zip(mapped_holdings, mstar_ids):
            try:
                rows = await self._jip.get_fund_nav_history(
                    mstar_id=mid,
                    date_from=date_from,
                    date_to=date_to,
                )
                if len(rows) >= _MIN_NAV_POINTS:
                    nav_histories[mid] = rows
                else:
                    excluded_funds.append(
                        {
                            "mstar_id": mid,
                            "scheme_name": h.scheme_name,
                            "reason": (
                                f"Insufficient NAV history"
                                f" ({len(rows)} points, need {_MIN_NAV_POINTS})"
                            ),
                        }
                    )
            except Exception as exc:
                log.warning("nav_history_fetch_failed", mstar_id=mid, error=str(exc))
                excluded_funds.append(
                    {
                        "mstar_id": mid,
                        "scheme_name": h.scheme_name,
                        "reason": f"NAV fetch error: {exc}",
                    }
                )
        return nav_histories, excluded_funds

    def _run_models(
        self,
        models: list[str],
        returns_df: pd.DataFrame,
        max_weight: Decimal,
        max_positions: Optional[int],
        fund_meta: dict[str, dict[str, Any]],
        current_weights: dict[str, Decimal],
        nav_source: str,
        portfolio_id: uuid.UUID,
        candidate_count: int,
    ) -> list[OptimizationResult]:
        """Execute each requested optimization model and collect results."""
        mf_weight = _to_float(max_weight)
        results: list[OptimizationResult] = []

        for model_name in models:
            if model_name == OptimizationModel.mean_variance.value:
                mv_result = self._run_mv_model(
                    returns_df,
                    mf_weight,
                    max_weight,
                    max_positions,
                    fund_meta,
                    current_weights,
                    nav_source,
                    portfolio_id,
                    candidate_count,
                )
                results.append(mv_result)
            elif model_name == OptimizationModel.hrp.value:
                hrp_result = self._run_hrp_model(
                    returns_df,
                    fund_meta,
                    current_weights,
                    nav_source,
                    portfolio_id,
                )
                results.append(hrp_result)
            else:
                log.warning("unknown_optimization_model", model=model_name)

        return results

    def _run_mv_model(
        self,
        returns_df: pd.DataFrame,
        mf_weight: _Num,  # type: ignore[valid-type]
        max_weight: Decimal,
        max_positions: Optional[int],
        fund_meta: dict[str, dict[str, Any]],
        current_weights: dict[str, Decimal],
        nav_source: str,
        portfolio_id: uuid.UUID,
        candidate_count: int,
    ) -> OptimizationResult:
        """Run mean-variance model and return structured result."""
        t0 = time.monotonic()
        weights_df, solver_status, exp_ret, exp_risk, sharpe = _run_mean_variance(
            returns_df=returns_df,
            max_weight=mf_weight,
            max_positions=max_positions,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        constraints = _build_sebi_constraints(
            max_weight=max_weight,
            max_positions=max_positions,
            is_mv_binding=(weights_df is not None and mf_weight < 1.0),
        )

        if weights_df is not None:
            opt_weights = _weights_to_optimized(weights_df, fund_meta, current_weights, nav_source)
            return OptimizationResult(
                model=OptimizationModel.mean_variance,
                weights=opt_weights,
                expected_return=_to_dec4(exp_ret) if exp_ret is not None else None,
                expected_risk=_to_dec4(exp_risk) if exp_risk is not None else None,
                sharpe_ratio=_to_dec4(sharpe) if sharpe is not None else None,
                constraints_applied=constraints,
                solver_status=solver_status,
                computation_time_ms=elapsed_ms,
            )

        log.warning(
            "mean_variance_infeasible",
            portfolio_id=str(portfolio_id),
            solver_status=solver_status,
            candidate_count=candidate_count,
            max_weight=mf_weight,
        )
        return OptimizationResult(
            model=OptimizationModel.mean_variance,
            weights=[],
            constraints_applied=constraints,
            solver_status=solver_status,
            computation_time_ms=elapsed_ms,
        )

    def _run_hrp_model(
        self,
        returns_df: pd.DataFrame,
        fund_meta: dict[str, dict[str, Any]],
        current_weights: dict[str, Decimal],
        nav_source: str,
        portfolio_id: uuid.UUID,
    ) -> OptimizationResult:
        """Run HRP model and return structured result."""
        t0 = time.monotonic()
        weights_df, solver_status = _run_hrp(returns_df=returns_df)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if weights_df is not None:
            opt_weights = _weights_to_optimized(weights_df, fund_meta, current_weights, nav_source)
            return OptimizationResult(
                model=OptimizationModel.hrp,
                weights=opt_weights,
                constraints_applied=[],
                solver_status=solver_status,
                computation_time_ms=elapsed_ms,
            )

        log.warning("hrp_infeasible", portfolio_id=str(portfolio_id), solver_status=solver_status)
        return OptimizationResult(
            model=OptimizationModel.hrp,
            weights=[],
            constraints_applied=[],
            solver_status=solver_status,
            computation_time_ms=elapsed_ms,
        )
