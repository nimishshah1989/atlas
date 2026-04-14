"""Unit tests for BrinsonAttributionService.

Tests:
- Hand-calculated fixture reconciliation (allocation + selection + interaction)
- Determinism: same inputs → same outputs
- Graceful degradation: NAV returns unavailable → returns_available=False
- Decimal arithmetic: no float contamination
- Empty portfolio edge case
- Category weight computation correctness
- manager_alpha as portfolio return proxy
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.portfolio.attribution import BrinsonAttributionService, _to_decimal


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _fake_portfolio(portfolio_id: Optional[uuid.UUID] = None) -> MagicMock:
    p = MagicMock()
    p.id = portfolio_id or uuid.uuid4()
    p.name = "Test Portfolio"
    return p


def _fake_holding(
    mstar_id: Optional[str],
    units: str = "100",
    nav: str = "50",
    current_value: str = "5000",
) -> MagicMock:
    h = MagicMock()
    h.id = uuid.uuid4()
    h.mstar_id = mstar_id
    h.scheme_name = f"Scheme {mstar_id or 'unmapped'}"
    h.units = Decimal(units)
    h.nav = Decimal(nav)
    h.current_value = Decimal(current_value)
    return h


def _jip_detail(
    category_name: str = "Large Cap",
    manager_alpha: str = "2.5000",
    nav: str = "50",
) -> dict[str, Any]:
    return {
        "category_name": category_name,
        "manager_alpha": Decimal(manager_alpha),
        "nav": Decimal(nav),
    }


def _nav_return_row(
    category_name: str,
    avg_return_1y: str,
    fund_count: int = 30,
    benchmark_weight: str = "0.1000",
) -> dict[str, Any]:
    return {
        "category_name": category_name,
        "fund_count": fund_count,
        "avg_return_1y": Decimal(avg_return_1y),
        "benchmark_weight": Decimal(benchmark_weight),
    }


def _alpha_row(category_name: str, avg_manager_alpha: str = "1.5") -> dict[str, Any]:
    return {
        "category_name": category_name,
        "fund_count": 30,
        "avg_manager_alpha": Decimal(avg_manager_alpha),
    }


def _build_service(
    portfolio: MagicMock,
    holdings: list[MagicMock],
    fund_details: dict[str, Optional[dict[str, Any]]],
    nav_returns: Optional[list[dict[str, Any]]] = None,
    category_alpha: Optional[list[dict[str, Any]]] = None,
) -> BrinsonAttributionService:
    """Build a BrinsonAttributionService with fully mocked dependencies."""
    mock_repo = MagicMock()
    mock_repo.get_portfolio = AsyncMock(return_value=portfolio)
    mock_repo.get_holdings = AsyncMock(return_value=holdings)

    mock_jip = MagicMock()

    async def _get_fund_detail(mstar_id: str) -> Optional[dict[str, Any]]:
        return fund_details.get(mstar_id)

    mock_jip.get_fund_detail = AsyncMock(side_effect=_get_fund_detail)
    mock_jip.get_category_nav_returns = AsyncMock(return_value=nav_returns or [])
    mock_jip.get_category_alpha = AsyncMock(return_value=category_alpha or [])

    return BrinsonAttributionService(repo=mock_repo, jip=mock_jip)


# ---------------------------------------------------------------------------
# Tests: _to_decimal helper
# ---------------------------------------------------------------------------


def test_to_decimal_none_returns_none() -> None:
    assert _to_decimal(None) is None


def test_to_decimal_decimal_passthrough() -> None:
    d = Decimal("12.3456")
    assert _to_decimal(d) == d


def test_to_decimal_float_converts() -> None:
    result = _to_decimal(1.5)
    assert isinstance(result, Decimal)


def test_to_decimal_invalid_returns_none() -> None:
    assert _to_decimal("not-a-number") is None


# ---------------------------------------------------------------------------
# Tests: basic success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attribution_returns_response() -> None:
    """Happy path: single holding → attribution response with category."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")

    fund_details = {"F00001": _jip_detail(category_name="Large Cap", manager_alpha="3.0")}
    nav_returns = [_nav_return_row("Large Cap", avg_return_1y="15.0", benchmark_weight="0.25")]
    category_alpha = [_alpha_row("Large Cap", avg_manager_alpha="1.5")]

    svc = _build_service(portfolio, [h1], fund_details, nav_returns, category_alpha)
    result = await svc.compute_attribution(portfolio.id)

    assert result.portfolio_id == portfolio.id
    assert result.portfolio_name == "Test Portfolio"
    assert result.returns_available is True
    assert len(result.categories) >= 1

    cat = next(c for c in result.categories if c.category_name == "Large Cap")
    assert cat.portfolio_weight is not None
    assert isinstance(cat.portfolio_weight, Decimal), "portfolio_weight must be Decimal"
    assert cat.benchmark_weight == Decimal("0.25")


@pytest.mark.asyncio
async def test_attribution_all_values_are_decimal() -> None:
    """All financial values in response must be Decimal."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    fund_details = {"F00001": _jip_detail(category_name="Large Cap", manager_alpha="2.5")}
    nav_returns = [_nav_return_row("Large Cap", avg_return_1y="12.0", benchmark_weight="0.20")]

    svc = _build_service(portfolio, [h1], fund_details, nav_returns)
    result = await svc.compute_attribution(portfolio.id)

    for cat in result.categories:
        assert isinstance(cat.portfolio_weight, Decimal)
        assert isinstance(cat.benchmark_weight, Decimal)
        if cat.allocation_effect is not None:
            assert isinstance(cat.allocation_effect, Decimal), "allocation_effect must be Decimal"
        if cat.selection_effect is not None:
            assert isinstance(cat.selection_effect, Decimal), "selection_effect must be Decimal"
        if cat.interaction_effect is not None:
            assert isinstance(cat.interaction_effect, Decimal), "interaction_effect must be Decimal"


# ---------------------------------------------------------------------------
# Tests: hand-calculated fixture reconciliation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allocation_effect_formula_matches_fixture() -> None:
    """Allocation effect = (w_p - w_b) * (R_b_sector - R_b_total).

    Hand-calculated fixture:
      Portfolio: single holding in 'Large Cap', w_p = 1.0
      Benchmark: Large Cap w_b = 0.3, R_b_LC = 0.12 (12%)
                 Mid Cap  w_b = 0.7, R_b_MC = 0.08 (8%)
      R_b_total = (0.3*0.12 + 0.7*0.08) / (0.3+0.7) = (0.036 + 0.056) = 0.092

      Large Cap allocation = (1.0 - 0.3) * (0.12 - 0.092) = 0.7 * 0.028 = 0.0196
      Mid Cap allocation   = (0.0 - 0.7) * (0.08 - 0.092) = -0.7 * (-0.012) = 0.0084

      Total allocation = 0.0196 + 0.0084 = 0.028  (within 0.0001 tolerance)
    """
    portfolio = _fake_portfolio()
    # 100% in Large Cap
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="100", current_value="10000")
    fund_details = {
        "F00001": _jip_detail(
            category_name="Large Cap",
            manager_alpha="3.0",
            nav="100",
        )
    }
    # Benchmark: Large Cap 30%, Mid Cap 70%
    # total_weight = 0.3 + 0.7 = 1.0 (already normalized, they sum to 1)
    nav_returns = [
        _nav_return_row("Large Cap", avg_return_1y="0.12", benchmark_weight="0.3"),
        _nav_return_row("Mid Cap", avg_return_1y="0.08", benchmark_weight="0.7"),
    ]

    svc = _build_service(portfolio, [h1], fund_details, nav_returns)
    result = await svc.compute_attribution(portfolio.id)

    # R_b_total = (0.3 * 0.12 + 0.7 * 0.08) / 1.0 = 0.092
    lc = next(c for c in result.categories if c.category_name == "Large Cap")
    mc = next(c for c in result.categories if c.category_name == "Mid Cap")

    # Large Cap: w_p=1.0, w_b=0.3, R_b=0.12, R_b_total=0.092
    # alloc = (1.0 - 0.3) * (0.12 - 0.092) = 0.7 * 0.028 = 0.0196
    assert lc.allocation_effect is not None
    tolerance = Decimal("0.0001")
    expected_lc_alloc = Decimal("0.0196")
    assert abs(lc.allocation_effect - expected_lc_alloc) <= tolerance, (
        f"Large Cap allocation: expected ~{expected_lc_alloc}, got {lc.allocation_effect}"
    )

    # Mid Cap: w_p=0, w_b=0.7, R_b=0.08, R_b_total=0.092
    # alloc = (0.0 - 0.7) * (0.08 - 0.092) = -0.7 * -0.012 = 0.0084
    assert mc.allocation_effect is not None
    expected_mc_alloc = Decimal("0.0084")
    assert abs(mc.allocation_effect - expected_mc_alloc) <= tolerance, (
        f"Mid Cap allocation: expected ~{expected_mc_alloc}, got {mc.allocation_effect}"
    )

    # Total active = sum of effects
    assert result.summary.total_allocation_effect is not None
    expected_total_alloc = Decimal("0.028")
    assert abs(result.summary.total_allocation_effect - expected_total_alloc) <= tolerance, (
        f"Total allocation: expected ~{expected_total_alloc}, "
        f"got {result.summary.total_allocation_effect}"
    )


@pytest.mark.asyncio
async def test_selection_effect_formula_matches_fixture() -> None:
    """Selection effect = w_b * (R_p_sector - R_b_sector).

    R_p_sector = value-weighted manager_alpha for portfolio holdings in category.

    Hand-calculated fixture:
      Single holding in Large Cap, manager_alpha = 4.0 (fund outperforms by 4%)
      Benchmark: Large Cap w_b = 0.3, R_b_LC = 12.0 (returned as %)
      R_p_LC = 4.0 (manager_alpha, used as portfolio return proxy)
      selection = w_b * (R_p - R_b) = 0.3 * (4.0 - 12.0) = 0.3 * (-8.0) = -2.4

    Note: manager_alpha is typically small (e.g. 2-5%). Here we test the formula,
    not the sign interpretation.
    """
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="100", current_value="10000")
    fund_details = {
        "F00001": _jip_detail(
            category_name="Large Cap",
            manager_alpha="4.0",
            nav="100",
        )
    }
    nav_returns = [
        _nav_return_row("Large Cap", avg_return_1y="12.0", benchmark_weight="0.3"),
    ]

    svc = _build_service(portfolio, [h1], fund_details, nav_returns)
    result = await svc.compute_attribution(portfolio.id)

    lc = next(c for c in result.categories if c.category_name == "Large Cap")

    # selection = w_b * (R_p - R_b) = 0.3 * (4.0 - 12.0) = -2.4
    assert lc.selection_effect is not None
    expected_selection = Decimal("-2.4")
    tolerance = Decimal("0.0001")
    assert abs(lc.selection_effect - expected_selection) <= tolerance, (
        f"Expected selection ~{expected_selection}, got {lc.selection_effect}"
    )


@pytest.mark.asyncio
async def test_interaction_effect_formula_matches_fixture() -> None:
    """Interaction effect = (w_p - w_b) * (R_p_sector - R_b_sector).

    Hand-calculated fixture:
      w_p = 1.0, w_b = 0.3, R_p = 4.0, R_b = 12.0
      interaction = (1.0 - 0.3) * (4.0 - 12.0) = 0.7 * (-8.0) = -5.6
    """
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="100", current_value="10000")
    fund_details = {
        "F00001": _jip_detail(category_name="Large Cap", manager_alpha="4.0", nav="100")
    }
    nav_returns = [
        _nav_return_row("Large Cap", avg_return_1y="12.0", benchmark_weight="0.3"),
    ]

    svc = _build_service(portfolio, [h1], fund_details, nav_returns)
    result = await svc.compute_attribution(portfolio.id)

    lc = next(c for c in result.categories if c.category_name == "Large Cap")

    # interaction = (1.0 - 0.3) * (4.0 - 12.0) = 0.7 * -8.0 = -5.6
    assert lc.interaction_effect is not None
    expected_interaction = Decimal("-5.6")
    tolerance = Decimal("0.0001")
    assert abs(lc.interaction_effect - expected_interaction) <= tolerance, (
        f"Expected interaction ~{expected_interaction}, got {lc.interaction_effect}"
    )


@pytest.mark.asyncio
async def test_total_effect_equals_sum_of_components() -> None:
    """total_effect = allocation + selection + interaction for each category."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="100", current_value="10000")
    fund_details = {
        "F00001": _jip_detail(category_name="Large Cap", manager_alpha="3.0", nav="100")
    }
    nav_returns = [
        _nav_return_row("Large Cap", avg_return_1y="0.10", benchmark_weight="0.4"),
    ]

    svc = _build_service(portfolio, [h1], fund_details, nav_returns)
    result = await svc.compute_attribution(portfolio.id)

    lc = next(c for c in result.categories if c.category_name == "Large Cap")

    if lc.total_effect is not None:
        components = (
            (lc.allocation_effect or Decimal("0"))
            + (lc.selection_effect or Decimal("0"))
            + (lc.interaction_effect or Decimal("0"))
        )
        tolerance = Decimal("0.0001")
        assert abs(lc.total_effect - components) <= tolerance, (
            f"total_effect={lc.total_effect} != sum of components={components}"
        )


# ---------------------------------------------------------------------------
# Tests: determinism
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attribution_is_deterministic() -> None:
    """Same inputs → same outputs (byte-equal computed fields)."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    fund_details = {"F00001": _jip_detail(category_name="Large Cap", manager_alpha="2.5")}
    nav_returns = [_nav_return_row("Large Cap", avg_return_1y="0.12", benchmark_weight="0.3")]
    fixed_date = datetime.date(2026, 4, 14)

    svc1 = _build_service(portfolio, [h1], fund_details, nav_returns)
    result1 = await svc1.compute_attribution(portfolio.id, data_as_of=fixed_date)

    svc2 = _build_service(portfolio, [h1], fund_details, nav_returns)
    result2 = await svc2.compute_attribution(portfolio.id, data_as_of=fixed_date)

    assert result1.summary.total_allocation_effect == result2.summary.total_allocation_effect
    assert result1.summary.total_active_return == result2.summary.total_active_return
    assert len(result1.categories) == len(result2.categories)
    for c1, c2 in zip(
        sorted(result1.categories, key=lambda c: c.category_name),
        sorted(result2.categories, key=lambda c: c.category_name),
    ):
        assert c1.allocation_effect == c2.allocation_effect
        assert c1.portfolio_weight == c2.portfolio_weight


# ---------------------------------------------------------------------------
# Tests: graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attribution_no_nav_returns_returns_available_false() -> None:
    """When NAV returns unavailable, returns_available=False but categories still present."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    fund_details = {"F00001": _jip_detail(category_name="Large Cap")}

    svc = _build_service(portfolio, [h1], fund_details, nav_returns=[], category_alpha=[])
    result = await svc.compute_attribution(portfolio.id)

    assert result.returns_available is False
    # Category still present from holdings
    assert len(result.categories) >= 1
    lc = next(c for c in result.categories if c.category_name == "Large Cap")
    # Portfolio weight is computable even without benchmark data
    assert lc.portfolio_weight is not None
    # Effects are None when no benchmark
    assert lc.allocation_effect is None
    assert lc.selection_effect is None


@pytest.mark.asyncio
async def test_attribution_fund_detail_failure_adds_to_unavailable() -> None:
    """When get_fund_detail raises, holding appears in unavailable_holdings."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    h2 = _fake_holding(mstar_id="F00002", units="200", nav="25", current_value="5000")

    mock_repo = MagicMock()
    mock_repo.get_portfolio = AsyncMock(return_value=portfolio)
    mock_repo.get_holdings = AsyncMock(return_value=[h1, h2])

    mock_jip = MagicMock()

    async def _failing_detail(mstar_id: str) -> Optional[dict[str, Any]]:
        if mstar_id == "F00002":
            raise RuntimeError("JIP timeout for F00002")
        return _jip_detail(category_name="Large Cap")

    mock_jip.get_fund_detail = AsyncMock(side_effect=_failing_detail)
    mock_jip.get_category_nav_returns = AsyncMock(return_value=[])
    mock_jip.get_category_alpha = AsyncMock(return_value=[])

    svc = BrinsonAttributionService(repo=mock_repo, jip=mock_jip)
    result = await svc.compute_attribution(portfolio.id)

    assert len(result.unavailable_holdings) == 1
    assert result.unavailable_holdings[0]["mstar_id"] == "F00002"
    assert "JIP timeout" in result.unavailable_holdings[0]["reason"]


@pytest.mark.asyncio
async def test_attribution_empty_portfolio_returns_zero_categories() -> None:
    """Empty portfolio returns response with no categories."""
    portfolio = _fake_portfolio()

    mock_repo = MagicMock()
    mock_repo.get_portfolio = AsyncMock(return_value=portfolio)
    mock_repo.get_holdings = AsyncMock(return_value=[])

    mock_jip = MagicMock()
    mock_jip.get_category_nav_returns = AsyncMock(return_value=[])
    mock_jip.get_category_alpha = AsyncMock(return_value=[])

    svc = BrinsonAttributionService(repo=mock_repo, jip=mock_jip)
    result = await svc.compute_attribution(portfolio.id)

    # No portfolio holdings — only benchmark categories if any
    assert result.summary.total_active_return is None
    assert result.returns_available is False


@pytest.mark.asyncio
async def test_attribution_raises_value_error_when_portfolio_not_found() -> None:
    """compute_attribution raises ValueError when portfolio not found."""
    mock_repo = MagicMock()
    mock_repo.get_portfolio = AsyncMock(return_value=None)
    mock_jip = MagicMock()

    svc = BrinsonAttributionService(repo=mock_repo, jip=mock_jip)
    with pytest.raises(ValueError, match="not found"):
        await svc.compute_attribution(uuid.uuid4())


# ---------------------------------------------------------------------------
# Tests: multi-category portfolio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attribution_two_categories_weights_sum_to_one() -> None:
    """Portfolio weights across categories sum to 1.0."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="100", current_value="10000")
    h2 = _fake_holding(mstar_id="F00002", units="200", nav="25", current_value="5000")

    fund_details = {
        "F00001": _jip_detail(category_name="Large Cap", manager_alpha="2.0", nav="100"),
        "F00002": _jip_detail(category_name="Mid Cap", manager_alpha="1.5", nav="25"),
    }
    nav_returns = [
        _nav_return_row("Large Cap", avg_return_1y="0.12", benchmark_weight="0.4"),
        _nav_return_row("Mid Cap", avg_return_1y="0.15", benchmark_weight="0.3"),
    ]

    svc = _build_service(portfolio, [h1, h2], fund_details, nav_returns)
    result = await svc.compute_attribution(portfolio.id)

    # Portfolio weights for categories present in portfolio must sum to 1.0
    portfolio_cats = [c for c in result.categories if c.holding_count > 0]
    total_w_p = sum(c.portfolio_weight for c in portfolio_cats)
    tolerance = Decimal("0.0001")
    assert abs(total_w_p - Decimal("1.0")) <= tolerance, (
        f"Portfolio weights sum to {total_w_p}, expected 1.0"
    )


@pytest.mark.asyncio
async def test_attribution_summary_totals_match_category_sums() -> None:
    """Summary totals must equal sum of per-category effects."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="100", current_value="10000")
    h2 = _fake_holding(mstar_id="F00002", units="100", nav="50", current_value="5000")

    fund_details = {
        "F00001": _jip_detail(category_name="Large Cap", manager_alpha="3.0", nav="100"),
        "F00002": _jip_detail(category_name="Mid Cap", manager_alpha="2.0", nav="50"),
    }
    nav_returns = [
        _nav_return_row("Large Cap", avg_return_1y="0.10", benchmark_weight="0.4"),
        _nav_return_row("Mid Cap", avg_return_1y="0.12", benchmark_weight="0.3"),
    ]

    svc = _build_service(portfolio, [h1, h2], fund_details, nav_returns)
    result = await svc.compute_attribution(portfolio.id)

    tolerance = Decimal("0.0001")

    if result.summary.total_allocation_effect is not None:
        cat_alloc_sum = sum(
            (c.allocation_effect or Decimal("0"))
            for c in result.categories
            if c.allocation_effect is not None
        )
        assert abs(result.summary.total_allocation_effect - cat_alloc_sum) <= tolerance, (
            f"Summary alloc={result.summary.total_allocation_effect} "
            f"!= sum of categories={cat_alloc_sum}"
        )


# ---------------------------------------------------------------------------
# Tests: provenance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attribution_categories_have_provenance() -> None:
    """Each category must have source_table + formula in provenance."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    fund_details = {"F00001": _jip_detail(category_name="Large Cap", manager_alpha="2.5")}
    nav_returns = [_nav_return_row("Large Cap", avg_return_1y="0.10", benchmark_weight="0.3")]

    svc = _build_service(portfolio, [h1], fund_details, nav_returns)
    result = await svc.compute_attribution(portfolio.id)

    for cat in result.categories:
        assert cat.provenance is not None
        assert cat.provenance.source_table
        assert cat.provenance.formula


@pytest.mark.asyncio
async def test_attribution_response_has_data_as_of_and_formula() -> None:
    """Response must include data_as_of and summary formula + tolerance."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    fund_details = {"F00001": _jip_detail(category_name="Large Cap")}

    svc = _build_service(portfolio, [h1], fund_details, nav_returns=[])
    result = await svc.compute_attribution(portfolio.id)

    assert result.data_as_of is not None
    assert result.computed_at is not None
    assert result.summary.formula
    assert result.summary.tolerance
