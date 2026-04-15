"""Unit tests for PortfolioOptimizationService.

Tests:
- Mean-variance returns weights summing to 1.0
- HRP returns different weights than MV on same input
- Determinism: same input → same output (byte-equal weights)
- Infeasibility: impossible constraints → structured error (solver_status != optimal)
- Excluded funds: insufficient NAV data → excluded_funds list
- Empty mapped holdings → ValueError
- Portfolio not found → ValueError
- Decimal at boundary: all weights are Decimal, not float
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from backend.models.portfolio import OptimizationModel
from backend.services.portfolio.optimization import (
    PortfolioOptimizationService,
    _build_returns_matrix,
    _run_hrp,
    _run_mean_variance,
    _to_dec4,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _fake_portfolio(portfolio_id: Optional[uuid.UUID] = None) -> MagicMock:
    p = MagicMock()
    p.id = portfolio_id or uuid.uuid4()
    p.name = "Test Portfolio"
    return p


def _fake_holding(
    mstar_id: str,
    scheme_name: str = "Test Scheme",
    current_value: str = "100000",
) -> MagicMock:
    h = MagicMock()
    h.id = uuid.uuid4()
    h.mstar_id = mstar_id
    h.scheme_name = scheme_name
    h.current_value = Decimal(current_value)
    return h


def _fake_nav_rows(mstar_id: str, n: int = 60) -> list[dict[str, Any]]:
    """Generate n synthetic NAV rows for a fund (deterministic)."""
    np.random.seed(hash(mstar_id) % (2**31))
    base = 100.0
    navs = [base]
    for _ in range(n - 1):
        base *= 1 + np.random.randn() * 0.01
        navs.append(base)

    base_date = datetime.date(2025, 1, 2)
    rows = []
    for i, nav in enumerate(navs):
        dt = base_date + datetime.timedelta(days=i)
        rows.append({"nav_date": dt.isoformat(), "nav": Decimal(str(round(nav, 4)))})
    return rows


def _make_mock_repo(
    portfolio: Optional[MagicMock] = None,
    holdings: Optional[list[MagicMock]] = None,
) -> MagicMock:
    repo = MagicMock()
    repo.get_portfolio = AsyncMock(return_value=portfolio)
    repo.get_holdings = AsyncMock(return_value=holdings or [])
    return repo


def _make_mock_jip(nav_map: dict[str, list[dict[str, Any]]]) -> MagicMock:
    """Build a JIPMFService mock that returns nav_map[mstar_id] for get_fund_nav_history."""
    jip = MagicMock()

    async def _nav_history(
        mstar_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return nav_map.get(mstar_id, [])

    jip.get_fund_nav_history = _nav_history
    return jip


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


def test_to_dec4_converts_float_to_decimal() -> None:
    """_to_dec4 converts float to Decimal with 4dp."""
    result = _to_dec4(0.123456789)
    assert isinstance(result, Decimal)
    assert result == Decimal("0.1235")


def test_build_returns_matrix_basic() -> None:
    """_build_returns_matrix builds DataFrame with correct shape."""
    nav_histories = {
        "F1": _fake_nav_rows("F1", 60),
        "F2": _fake_nav_rows("F2", 60),
    }
    df = _build_returns_matrix(nav_histories)
    assert not df.empty
    assert set(df.columns) == {"F1", "F2"}
    # Returns = n - 1 after pct_change
    assert len(df) >= 55  # some rows may be dropped on inner join


def test_build_returns_matrix_excludes_insufficient_data() -> None:
    """_build_returns_matrix excludes funds with fewer than 20 data points."""
    nav_histories = {
        "F1": _fake_nav_rows("F1", 60),
        "F_short": _fake_nav_rows("F_short", 10),  # only 10 points
    }
    df = _build_returns_matrix(nav_histories)
    assert "F1" in df.columns
    assert "F_short" not in df.columns


def test_build_returns_matrix_empty_input() -> None:
    """_build_returns_matrix returns empty DataFrame when no valid funds."""
    df = _build_returns_matrix({})
    assert df.empty


def test_run_mean_variance_returns_weights_summing_to_one() -> None:
    """MV optimization returns weights that sum to ~1.0."""
    np.random.seed(42)
    returns = pd.DataFrame(
        np.random.randn(252, 5) / 100,
        columns=["F1", "F2", "F3", "F4", "F5"],
    )
    weights_df, status, exp_ret, exp_risk, sharpe = _run_mean_variance(
        returns_df=returns,
        max_weight=0.5,
        max_positions=None,
    )
    assert status == "optimal"
    assert weights_df is not None
    col_sum = weights_df.iloc[:, 0].sum() if weights_df.shape[1] == 1 else weights_df.values.sum()
    total = float(col_sum)
    assert abs(total - 1.0) < 1e-4, f"Weights sum to {total}, not 1.0"


def test_run_mean_variance_respects_max_weight() -> None:
    """MV optimization respects the per-fund weight cap."""
    np.random.seed(42)
    n_assets = 12
    returns = pd.DataFrame(
        np.random.randn(252, n_assets) / 100,
        columns=[f"F{i}" for i in range(n_assets)],
    )
    max_w = 0.15
    weights_df, status, _, _, _ = _run_mean_variance(
        returns_df=returns,
        max_weight=max_w,
        max_positions=None,
    )
    assert status == "optimal"
    assert weights_df is not None
    assert float(weights_df.values.max()) <= max_w + 1e-4


def test_run_mean_variance_infeasible_returns_infeasible_status() -> None:
    """MV optimization with impossible constraints returns infeasible status."""
    np.random.seed(42)
    # 3 assets, max_weight=0.10 → impossible (needs ≥10 assets for 10% cap)
    returns = pd.DataFrame(
        np.random.randn(252, 3) / 100,
        columns=["F1", "F2", "F3"],
    )
    weights_df, status, _, _, _ = _run_mean_variance(
        returns_df=returns,
        max_weight=0.10,
        max_positions=None,
    )
    assert weights_df is None
    assert status == "infeasible"


def test_run_hrp_returns_weights_summing_to_one() -> None:
    """HRP optimization returns weights that sum to ~1.0."""
    np.random.seed(42)
    returns = pd.DataFrame(
        np.random.randn(252, 5) / 100,
        columns=["F1", "F2", "F3", "F4", "F5"],
    )
    weights_df, status = _run_hrp(returns_df=returns)
    assert status == "optimal"
    assert weights_df is not None
    col_sum = weights_df.iloc[:, 0].sum() if weights_df.shape[1] == 1 else weights_df.values.sum()
    total = float(col_sum)
    assert abs(total - 1.0) < 1e-4


def test_run_hrp_insufficient_assets() -> None:
    """HRP fails gracefully with fewer than 2 assets."""
    returns = pd.DataFrame(
        np.random.randn(100, 1) / 100,
        columns=["F1"],
    )
    weights_df, status = _run_hrp(returns_df=returns)
    assert weights_df is None
    assert status == "insufficient_assets"


def test_mv_and_hrp_return_distinct_weights_on_same_input() -> None:
    """Mean-variance and HRP return different weight vectors on the same input."""
    np.random.seed(42)
    n_assets = 8
    returns = pd.DataFrame(
        np.random.randn(252, n_assets) / 100,
        columns=[f"F{i}" for i in range(n_assets)],
    )
    mv_weights, mv_status, _, _, _ = _run_mean_variance(
        returns_df=returns, max_weight=0.5, max_positions=None
    )
    hrp_weights, hrp_status = _run_hrp(returns_df=returns)

    assert mv_status == "optimal"
    assert hrp_status == "optimal"
    assert mv_weights is not None
    assert hrp_weights is not None

    # Weights should differ (MV concentrates, HRP diversifies)
    mv_vals = mv_weights.values.flatten()
    hrp_vals = hrp_weights.values.flatten()
    # At least one weight differs by >1%
    assert np.max(np.abs(mv_vals - hrp_vals)) > 0.01, "MV and HRP weights are identical"


def test_determinism_mv_same_input_same_output() -> None:
    """MV produces byte-equal weights on two identical runs."""
    np.random.seed(99)
    returns = pd.DataFrame(
        np.random.randn(252, 6) / 100,
        columns=[f"F{i}" for i in range(6)],
    )

    w1, s1, _, _, _ = _run_mean_variance(returns, 0.5, None)
    w2, s2, _, _, _ = _run_mean_variance(returns, 0.5, None)

    assert s1 == s2 == "optimal"
    assert w1 is not None and w2 is not None
    np.testing.assert_array_equal(w1.values, w2.values)


def test_determinism_hrp_same_input_same_output() -> None:
    """HRP produces byte-equal weights on two identical runs."""
    np.random.seed(99)
    returns = pd.DataFrame(
        np.random.randn(252, 6) / 100,
        columns=[f"F{i}" for i in range(6)],
    )

    w1, s1 = _run_hrp(returns)
    w2, s2 = _run_hrp(returns)

    assert s1 == s2 == "optimal"
    assert w1 is not None and w2 is not None
    np.testing.assert_array_equal(w1.values, w2.values)


# ---------------------------------------------------------------------------
# Service integration tests (with mocked repo + jip)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_optimize_raises_on_portfolio_not_found() -> None:
    """Service raises ValueError when portfolio does not exist."""
    repo = _make_mock_repo(portfolio=None)
    jip = _make_mock_jip({})
    service = PortfolioOptimizationService(repo=repo, jip=jip)

    with pytest.raises(ValueError, match="not found"):
        await service.optimize_portfolio(
            portfolio_id=uuid.uuid4(),
            data_as_of=datetime.date(2026, 1, 1),
            risk_profile="moderate",
            models=["mean_variance"],
            max_weight=Decimal("0.50"),
            max_positions=None,
        )


@pytest.mark.asyncio
async def test_service_optimize_raises_on_no_mapped_holdings() -> None:
    """Service raises ValueError when no holdings have mstar_id."""
    pid = uuid.uuid4()
    h = MagicMock()
    h.mstar_id = None
    h.scheme_name = "Unknown Scheme"
    h.current_value = Decimal("10000")

    repo = _make_mock_repo(portfolio=_fake_portfolio(pid), holdings=[h])
    jip = _make_mock_jip({})
    service = PortfolioOptimizationService(repo=repo, jip=jip)

    with pytest.raises(ValueError, match="no mapped holdings"):
        await service.optimize_portfolio(
            portfolio_id=pid,
            data_as_of=datetime.date(2026, 1, 1),
            risk_profile="moderate",
            models=["mean_variance"],
            max_weight=Decimal("0.50"),
            max_positions=None,
        )


@pytest.mark.asyncio
async def test_service_optimize_excludes_funds_with_insufficient_nav() -> None:
    """Funds with <20 NAV points are excluded and appear in excluded_funds."""
    pid = uuid.uuid4()
    h1 = _fake_holding("F1")
    h2 = _fake_holding("F2")  # will have insufficient data

    repo = _make_mock_repo(portfolio=_fake_portfolio(pid), holdings=[h1, h2])

    # F1 gets 60 rows, F2 gets only 5
    nav_map = {
        "F1": _fake_nav_rows("F1", 60),
        "F2": _fake_nav_rows("F2", 5),
    }
    jip = _make_mock_jip(nav_map)
    service = PortfolioOptimizationService(repo=repo, jip=jip)

    # With only 1 fund, MV may still work (Sharpe maximization with 1 asset)
    # But HRP needs 2 — let's just check excluded_funds
    result = await service.optimize_portfolio(
        portfolio_id=pid,
        data_as_of=datetime.date(2026, 4, 1),
        risk_profile="moderate",
        models=["hrp"],
        max_weight=Decimal("0.50"),
        max_positions=None,
    )

    excluded_ids = [e["mstar_id"] for e in result.excluded_funds]
    assert "F2" in excluded_ids


@pytest.mark.asyncio
async def test_service_optimize_returns_decimal_weights() -> None:
    """All weights in the response are Decimal, not float."""
    pid = uuid.uuid4()
    holdings = [_fake_holding(f"F{i}", f"Scheme {i}") for i in range(6)]

    repo = _make_mock_repo(portfolio=_fake_portfolio(pid), holdings=holdings)
    nav_map = {f"F{i}": _fake_nav_rows(f"F{i}", 100) for i in range(6)}
    jip = _make_mock_jip(nav_map)
    service = PortfolioOptimizationService(repo=repo, jip=jip)

    result = await service.optimize_portfolio(
        portfolio_id=pid,
        data_as_of=datetime.date(2026, 4, 1),
        risk_profile="moderate",
        models=["mean_variance", "hrp"],
        max_weight=Decimal("0.50"),
        max_positions=None,
    )

    for model_result in result.models:
        for w in model_result.weights:
            assert isinstance(w.optimized_weight, Decimal), (
                f"optimized_weight is {type(w.optimized_weight)}, expected Decimal"
            )
            assert isinstance(w.current_weight, Decimal)
            assert isinstance(w.weight_change, Decimal)


@pytest.mark.asyncio
async def test_service_optimize_mv_and_hrp_distinct() -> None:
    """Service returns distinct weight vectors for MV and HRP on same input."""
    pid = uuid.uuid4()
    # Use 8 funds so both models are feasible
    holdings = [_fake_holding(f"F{i}", f"Scheme {i}") for i in range(8)]

    repo = _make_mock_repo(portfolio=_fake_portfolio(pid), holdings=holdings)
    nav_map = {f"F{i}": _fake_nav_rows(f"F{i}", 100) for i in range(8)}
    jip = _make_mock_jip(nav_map)
    service = PortfolioOptimizationService(repo=repo, jip=jip)

    result = await service.optimize_portfolio(
        portfolio_id=pid,
        data_as_of=datetime.date(2026, 4, 1),
        risk_profile="moderate",
        models=["mean_variance", "hrp"],
        max_weight=Decimal("0.50"),
        max_positions=None,
    )

    mv_results = [r for r in result.models if r.model == OptimizationModel.mean_variance]
    hrp_results = [r for r in result.models if r.model == OptimizationModel.hrp]

    assert mv_results and hrp_results
    mv_result = mv_results[0]
    hrp_result = hrp_results[0]

    if mv_result.solver_status == "optimal" and hrp_result.solver_status == "optimal":
        mv_ws = {w.mstar_id: w.optimized_weight for w in mv_result.weights}
        hrp_ws = {w.mstar_id: w.optimized_weight for w in hrp_result.weights}
        # At least one fund should differ
        assert any(
            abs(float(mv_ws.get(mid, 0)) - float(hrp_ws.get(mid, 0))) > 0.001 for mid in mv_ws
        ), "MV and HRP weights are identical — optimization not working"


@pytest.mark.asyncio
async def test_service_optimize_determinism() -> None:
    """Same inputs + same NAV data → identical weights on two runs."""
    pid = uuid.uuid4()
    holdings = [_fake_holding(f"F{i}", f"Scheme {i}") for i in range(6)]

    repo = _make_mock_repo(portfolio=_fake_portfolio(pid), holdings=holdings)
    nav_map = {f"F{i}": _fake_nav_rows(f"F{i}", 100) for i in range(6)}
    jip = _make_mock_jip(nav_map)
    service = PortfolioOptimizationService(repo=repo, jip=jip)

    kwargs: dict[str, Any] = dict(
        portfolio_id=pid,
        data_as_of=datetime.date(2026, 4, 1),
        risk_profile="moderate",
        models=["mean_variance"],
        max_weight=Decimal("0.50"),
        max_positions=None,
    )

    r1 = await service.optimize_portfolio(**kwargs)
    r2 = await service.optimize_portfolio(**kwargs)

    assert len(r1.models) == len(r2.models) == 1
    w1 = {w.mstar_id: w.optimized_weight for w in r1.models[0].weights}
    w2 = {w.mstar_id: w.optimized_weight for w in r2.models[0].weights}
    assert w1 == w2, "Weights differ between runs — not deterministic"


@pytest.mark.asyncio
async def test_service_optimize_infeasible_constraints_returns_structured_error() -> None:
    """Infeasible constraints return OptimizationResult with solver_status != optimal."""
    pid = uuid.uuid4()
    # Only 3 funds but 10% max weight → infeasible for MV
    holdings = [_fake_holding(f"F{i}", f"Scheme {i}") for i in range(3)]

    repo = _make_mock_repo(portfolio=_fake_portfolio(pid), holdings=holdings)
    nav_map = {f"F{i}": _fake_nav_rows(f"F{i}", 100) for i in range(3)}
    jip = _make_mock_jip(nav_map)
    service = PortfolioOptimizationService(repo=repo, jip=jip)

    result = await service.optimize_portfolio(
        portfolio_id=pid,
        data_as_of=datetime.date(2026, 4, 1),
        risk_profile="moderate",
        models=["mean_variance"],
        max_weight=Decimal("0.10"),  # impossible: 3 assets, each limited to 10%
        max_positions=None,
    )

    assert len(result.models) == 1
    mv = result.models[0]
    assert mv.solver_status != "optimal", f"Expected infeasible, got {mv.solver_status}"
    assert mv.weights == []


@pytest.mark.asyncio
async def test_service_optimize_response_has_required_fields() -> None:
    """Response has all required fields: portfolio_id, data_as_of, computed_at, etc."""
    pid = uuid.uuid4()
    holdings = [_fake_holding(f"F{i}", f"Scheme {i}") for i in range(5)]

    repo = _make_mock_repo(portfolio=_fake_portfolio(pid), holdings=holdings)
    nav_map = {f"F{i}": _fake_nav_rows(f"F{i}", 100) for i in range(5)}
    jip = _make_mock_jip(nav_map)
    service = PortfolioOptimizationService(repo=repo, jip=jip)

    result = await service.optimize_portfolio(
        portfolio_id=pid,
        data_as_of=datetime.date(2026, 4, 1),
        risk_profile="moderate",
        models=["hrp"],
        max_weight=Decimal("0.50"),
        max_positions=None,
    )

    assert result.portfolio_id == pid
    assert result.portfolio_name == "Test Portfolio"
    assert result.data_as_of == datetime.date(2026, 4, 1)
    assert result.computed_at is not None
    assert result.candidate_count >= 0
    assert isinstance(result.excluded_funds, list)
    assert "optimization" in result.provenance
