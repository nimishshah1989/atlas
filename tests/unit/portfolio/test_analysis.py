"""Unit tests for PortfolioAnalysisService.

Tests:
- Determinism: same inputs → same outputs
- Graceful degradation: JIP failure → partial result with unavailable list
- Decimal arithmetic: no float contamination
- Correct weighted calculations
- Empty portfolio edge case
- Unmapped holdings don't pollute metrics but are counted
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.portfolio.analysis import (
    PortfolioAnalysisService,
    _quadrant_from_rs,
    _to_decimal,
)


# ---------------------------------------------------------------------------
# Helpers to build fake ORM objects
# ---------------------------------------------------------------------------


def _fake_portfolio(portfolio_id: Optional[uuid.UUID] = None) -> MagicMock:
    p = MagicMock()
    p.id = portfolio_id or uuid.uuid4()
    p.name = "Test Portfolio"
    return p


def _fake_holding(
    mstar_id: Optional[str] = None,
    units: str = "100.0000",
    nav: str = "50.0000",
    current_value: str = "5000.0000",
    cost_value: str = "4000.0000",
) -> MagicMock:
    h = MagicMock()
    h.id = uuid.uuid4()
    h.mstar_id = mstar_id
    h.scheme_name = f"Scheme {mstar_id or 'unmapped'}"
    h.units = Decimal(units)
    h.nav = Decimal(nav)
    h.current_value = Decimal(current_value)
    h.cost_value = Decimal(cost_value)
    return h


def _jip_detail(
    nav: str = "50.0000",
    return_1y: str = "15.5000",
    sharpe_ratio: str = "1.2500",
    sortino_ratio: str = "1.5000",
    alpha: str = "2.0000",
    beta: str = "0.9000",
) -> dict[str, Any]:
    return {
        "nav": Decimal(nav),
        "return_1m": Decimal("1.2"),
        "return_3m": Decimal("3.5"),
        "return_6m": Decimal("7.0"),
        "return_1y": Decimal(return_1y),
        "return_3y": Decimal("45.0"),
        "return_5y": Decimal("80.0"),
        "sharpe_ratio": Decimal(sharpe_ratio),
        "sortino_ratio": Decimal(sortino_ratio),
        "alpha": Decimal(alpha),
        "beta": Decimal(beta),
    }


def _jip_sectors() -> list[dict[str, Any]]:
    return [
        {"sector_name": "Financial Services", "weight_pct": Decimal("35.00")},
        {"sector_name": "Technology", "weight_pct": Decimal("25.00")},
        {"sector_name": "Healthcare", "weight_pct": Decimal("15.00")},
    ]


def _jip_wtechs() -> dict[str, Any]:
    return {
        "weighted_rsi": Decimal("55.00"),
        "weighted_breadth_pct_above_200dma": Decimal("60.00"),
        "weighted_macd_bullish_pct": Decimal("45.00"),
    }


def _build_service(
    portfolio: MagicMock,
    holdings: list[MagicMock],
    fund_details: dict[str, Optional[dict[str, Any]]],
    rs_map: dict[str, dict[str, Any]],
    sectors_map: Optional[dict[str, list[dict[str, Any]]]] = None,
    wtechs_map: Optional[dict[str, Optional[dict[str, Any]]]] = None,
    rs_batch_raises: bool = False,
) -> PortfolioAnalysisService:
    """Build a PortfolioAnalysisService with fully mocked dependencies."""
    mock_repo = MagicMock()
    mock_repo.get_portfolio = AsyncMock(return_value=portfolio)
    mock_repo.get_holdings = AsyncMock(return_value=holdings)

    mock_jip = MagicMock()

    if rs_batch_raises:
        mock_jip.get_mf_rs_momentum_batch = AsyncMock(
            side_effect=RuntimeError("rs_momentum_batch unavailable (negative-cached)")
        )
    else:
        mock_jip.get_mf_rs_momentum_batch = AsyncMock(return_value=rs_map)

    async def _get_fund_detail(mstar_id: str) -> Optional[dict[str, Any]]:
        return fund_details.get(mstar_id)

    async def _get_fund_sectors(mstar_id: str) -> list[dict[str, Any]]:
        if sectors_map is not None:
            return sectors_map.get(mstar_id, [])
        return _jip_sectors()

    async def _get_fund_weighted_technicals(mstar_id: str) -> Optional[dict[str, Any]]:
        if wtechs_map is not None:
            return wtechs_map.get(mstar_id)
        return _jip_wtechs()

    async def _get_fund_overlap(a: str, b: str) -> dict[str, Any]:
        return {
            "mstar_id_a": a,
            "mstar_id_b": b,
            "overlap_pct": Decimal("20.00"),
            "common_count": 5,
            "count_a": 50,
            "count_b": 50,
            "common_holdings": [],
        }

    mock_jip.get_fund_detail = AsyncMock(side_effect=_get_fund_detail)
    mock_jip.get_fund_sectors = AsyncMock(side_effect=_get_fund_sectors)
    mock_jip.get_fund_weighted_technicals = AsyncMock(side_effect=_get_fund_weighted_technicals)
    mock_jip.get_fund_overlap = AsyncMock(side_effect=_get_fund_overlap)

    return PortfolioAnalysisService(repo=mock_repo, jip=mock_jip)


# ---------------------------------------------------------------------------
# Tests: _to_decimal helper
# ---------------------------------------------------------------------------


def test_to_decimal_none_returns_none() -> None:
    assert _to_decimal(None) is None


def test_to_decimal_decimal_passthrough() -> None:
    d = Decimal("123.4567")
    assert _to_decimal(d) == d


def test_to_decimal_float_converts() -> None:
    result = _to_decimal(1.5)
    assert isinstance(result, Decimal)
    assert result == Decimal("1.5")


def test_to_decimal_string_converts() -> None:
    result = _to_decimal("99.99")
    assert isinstance(result, Decimal)
    assert result == Decimal("99.99")


def test_to_decimal_invalid_returns_none() -> None:
    assert _to_decimal("not-a-number") is None


# ---------------------------------------------------------------------------
# Tests: _quadrant_from_rs
# ---------------------------------------------------------------------------


def test_quadrant_leading_when_rs_high_and_momentum_positive() -> None:
    result = _quadrant_from_rs(Decimal("60"), Decimal("5"))
    assert result == "LEADING"


def test_quadrant_improving_when_rs_low_and_momentum_positive() -> None:
    result = _quadrant_from_rs(Decimal("40"), Decimal("5"))
    assert result == "IMPROVING"


def test_quadrant_weakening_when_rs_high_and_momentum_negative() -> None:
    result = _quadrant_from_rs(Decimal("60"), Decimal("-5"))
    assert result == "WEAKENING"


def test_quadrant_lagging_when_rs_low_and_momentum_negative() -> None:
    result = _quadrant_from_rs(Decimal("40"), Decimal("-5"))
    assert result == "LAGGING"


def test_quadrant_none_when_rs_none() -> None:
    result = _quadrant_from_rs(None, Decimal("5"))
    assert result is None


def test_quadrant_no_momentum_uses_composite_only() -> None:
    assert _quadrant_from_rs(Decimal("55"), None) == "LEADING"
    assert _quadrant_from_rs(Decimal("45"), None) == "LAGGING"


# ---------------------------------------------------------------------------
# Tests: analyze_portfolio — basic success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_portfolio_returns_full_response() -> None:
    """Happy path: two mapped holdings → full analysis with weighted RS."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    h2 = _fake_holding(mstar_id="F00002", units="200", nav="25", current_value="5000")
    holdings = [h1, h2]

    rs_map = {
        "F00001": {
            "mstar_id": "F00001",
            "latest_rs_composite": Decimal("65.00"),
            "rs_momentum_28d": Decimal("3.00"),
        },
        "F00002": {
            "mstar_id": "F00002",
            "latest_rs_composite": Decimal("45.00"),
            "rs_momentum_28d": Decimal("-2.00"),
        },
    }
    fund_details = {"F00001": _jip_detail(nav="50"), "F00002": _jip_detail(nav="25")}

    svc = _build_service(portfolio, holdings, fund_details, rs_map)
    result = await svc.analyze_portfolio(portfolio.id)

    assert result.portfolio_id == portfolio.id
    assert result.portfolio.holdings_count == 2
    assert result.portfolio.mapped_count == 2
    assert result.portfolio.unmapped_count == 0
    assert len(result.holdings) == 2
    assert len(result.unavailable) == 0
    assert result.rs_data_available is True

    # Weighted RS = (5000*65 + 5000*45) / 10000 = 55.00
    assert result.portfolio.weighted_rs is not None
    assert result.portfolio.weighted_rs == Decimal("55.0000")


@pytest.mark.asyncio
async def test_analyze_portfolio_weighted_rs_all_decimal() -> None:
    """All financial values in response must be Decimal, not float."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    holdings = [h1]
    rs_map = {
        "F00001": {
            "mstar_id": "F00001",
            "latest_rs_composite": Decimal("70.00"),
            "rs_momentum_28d": Decimal("5.00"),
        }
    }
    fund_details = {"F00001": _jip_detail()}

    svc = _build_service(portfolio, holdings, fund_details, rs_map)
    result = await svc.analyze_portfolio(portfolio.id)

    assert isinstance(result.portfolio.total_value, Decimal), "total_value must be Decimal"
    if result.portfolio.weighted_rs is not None:
        assert isinstance(result.portfolio.weighted_rs, Decimal), "weighted_rs must be Decimal"
    for ha in result.holdings:
        if ha.current_value is not None:
            assert isinstance(ha.current_value, Decimal), "current_value must be Decimal"
        if ha.rs_composite is not None:
            assert isinstance(ha.rs_composite, Decimal), "rs_composite must be Decimal"


# ---------------------------------------------------------------------------
# Tests: determinism
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_portfolio_is_deterministic() -> None:
    """Same inputs → same outputs (byte-equal computed fields)."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    holdings = [h1]
    rs_map = {
        "F00001": {
            "mstar_id": "F00001",
            "latest_rs_composite": Decimal("70.00"),
            "rs_momentum_28d": Decimal("5.00"),
        }
    }
    fund_details = {"F00001": _jip_detail()}
    fixed_date = datetime.date(2026, 4, 14)

    svc1 = _build_service(portfolio, holdings, fund_details, rs_map)
    result1 = await svc1.analyze_portfolio(portfolio.id, data_as_of=fixed_date)

    svc2 = _build_service(portfolio, holdings, fund_details, rs_map)
    result2 = await svc2.analyze_portfolio(portfolio.id, data_as_of=fixed_date)

    # Core computed fields must be identical
    assert result1.portfolio.weighted_rs == result2.portfolio.weighted_rs
    assert result1.portfolio.total_value == result2.portfolio.total_value
    assert result1.portfolio.sector_weights == result2.portfolio.sector_weights
    assert result1.portfolio.quadrant_distribution == result2.portfolio.quadrant_distribution
    assert len(result1.holdings) == len(result2.holdings)
    for ha1, ha2 in zip(result1.holdings, result2.holdings):
        assert ha1.rs_composite == ha2.rs_composite
        assert ha1.current_value == ha2.current_value


# ---------------------------------------------------------------------------
# Tests: graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_portfolio_rs_batch_failure_degrades_gracefully() -> None:
    """When RS batch fails, analysis continues with rs_data_available=False."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    holdings = [h1]
    fund_details = {"F00001": _jip_detail()}

    svc = _build_service(portfolio, holdings, fund_details, rs_map={}, rs_batch_raises=True)
    result = await svc.analyze_portfolio(portfolio.id)

    assert result.rs_data_available is False
    assert result.portfolio.weighted_rs is None
    # Analysis still returns a result
    assert result.portfolio.holdings_count == 1
    # Holdings are still analysed (just without RS data)
    assert len(result.holdings) == 1
    assert result.holdings[0].rs_composite is None


@pytest.mark.asyncio
async def test_analyze_portfolio_jip_fund_detail_failure_adds_to_unavailable() -> None:
    """When get_fund_detail raises for a holding, it appears in unavailable list."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    h2 = _fake_holding(mstar_id="F00002", units="200", nav="25", current_value="5000")
    holdings = [h1, h2]

    rs_map = {
        "F00001": {
            "mstar_id": "F00001",
            "latest_rs_composite": Decimal("65.00"),
            "rs_momentum_28d": Decimal("3.00"),
        }
    }

    # Build service where F00002 causes JIP detail to raise
    mock_repo = MagicMock()
    mock_repo.get_portfolio = AsyncMock(return_value=portfolio)
    mock_repo.get_holdings = AsyncMock(return_value=holdings)

    mock_jip = MagicMock()
    mock_jip.get_mf_rs_momentum_batch = AsyncMock(return_value=rs_map)

    async def _failing_detail(mstar_id: str) -> Optional[dict[str, Any]]:
        if mstar_id == "F00002":
            raise RuntimeError("JIP timeout for F00002")
        return _jip_detail()

    mock_jip.get_fund_detail = AsyncMock(side_effect=_failing_detail)
    mock_jip.get_fund_sectors = AsyncMock(return_value=_jip_sectors())
    mock_jip.get_fund_weighted_technicals = AsyncMock(return_value=_jip_wtechs())
    mock_jip.get_fund_overlap = AsyncMock(
        return_value={
            "mstar_id_a": "F00001",
            "mstar_id_b": "F00002",
            "overlap_pct": Decimal("0"),
            "common_count": 0,
        }
    )

    svc = PortfolioAnalysisService(repo=mock_repo, jip=mock_jip)
    result = await svc.analyze_portfolio(portfolio.id)

    assert len(result.unavailable) == 1
    assert result.unavailable[0]["mstar_id"] == "F00002"
    assert "JIP timeout" in result.unavailable[0]["reason"]
    # Only F00001 is in holdings
    assert len(result.holdings) == 1
    assert result.holdings[0].mstar_id == "F00001"


@pytest.mark.asyncio
async def test_analyze_portfolio_unmapped_holdings_excluded_from_jip_metrics() -> None:
    """Unmapped holdings (no mstar_id) are counted but excluded from JIP metrics."""
    portfolio = _fake_portfolio()
    h_mapped = _fake_holding(mstar_id="F00001", units="100", nav="50", current_value="5000")
    h_unmapped = _fake_holding(mstar_id=None, units="50", nav="100", current_value="5000")
    holdings = [h_mapped, h_unmapped]

    rs_map = {
        "F00001": {
            "mstar_id": "F00001",
            "latest_rs_composite": Decimal("70.00"),
            "rs_momentum_28d": Decimal("5.00"),
        }
    }
    fund_details = {"F00001": _jip_detail()}

    svc = _build_service(portfolio, holdings, fund_details, rs_map)
    result = await svc.analyze_portfolio(portfolio.id)

    # Total count includes unmapped
    assert result.portfolio.holdings_count == 2
    assert result.portfolio.mapped_count == 1
    assert result.portfolio.unmapped_count == 1
    # Only mapped holding appears in holdings analysis
    assert len(result.holdings) == 1
    assert result.holdings[0].mstar_id == "F00001"
    # Total value includes both holdings
    assert result.portfolio.total_value == Decimal("10000.0000")


# ---------------------------------------------------------------------------
# Tests: empty portfolio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_portfolio_empty_portfolio() -> None:
    """Empty portfolio returns zero total_value and no holdings."""
    portfolio = _fake_portfolio()
    holdings: list[MagicMock] = []

    mock_repo = MagicMock()
    mock_repo.get_portfolio = AsyncMock(return_value=portfolio)
    mock_repo.get_holdings = AsyncMock(return_value=holdings)

    mock_jip = MagicMock()
    mock_jip.get_mf_rs_momentum_batch = AsyncMock(return_value={})

    svc = PortfolioAnalysisService(repo=mock_repo, jip=mock_jip)
    result = await svc.analyze_portfolio(portfolio.id)

    assert result.portfolio.total_value == Decimal("0")
    assert result.portfolio.weighted_rs is None
    assert len(result.holdings) == 0
    assert len(result.unavailable) == 0


# ---------------------------------------------------------------------------
# Tests: weighted calculations correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weighted_rs_computed_correctly() -> None:
    """Weighted RS = sum(value * rs) / sum(value) with exact Decimal precision."""
    portfolio = _fake_portfolio()
    # 3000 @ rs=80, 7000 @ rs=20 → weighted = (3000*80 + 7000*20) / 10000 = 38.0
    h1 = _fake_holding(mstar_id="F00001", units="60", nav="50", current_value="3000")
    h2 = _fake_holding(mstar_id="F00002", units="70", nav="100", current_value="7000")
    holdings = [h1, h2]

    rs_map = {
        "F00001": {
            "mstar_id": "F00001",
            "latest_rs_composite": Decimal("80.00"),
            "rs_momentum_28d": Decimal("1.00"),
        },
        "F00002": {
            "mstar_id": "F00002",
            "latest_rs_composite": Decimal("20.00"),
            "rs_momentum_28d": Decimal("-1.00"),
        },
    }
    fund_details = {
        "F00001": _jip_detail(nav="50"),
        "F00002": _jip_detail(nav="100"),
    }

    svc = _build_service(portfolio, holdings, fund_details, rs_map)
    result = await svc.analyze_portfolio(portfolio.id)

    assert result.portfolio.weighted_rs is not None
    expected = Decimal("38.0000")
    assert result.portfolio.weighted_rs == expected, (
        f"Expected {expected}, got {result.portfolio.weighted_rs}"
    )


@pytest.mark.asyncio
async def test_quadrant_distribution_counted_correctly() -> None:
    """Quadrant distribution must count correctly for LEADING/LAGGING holdings."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", current_value="5000")  # LEADING
    h2 = _fake_holding(mstar_id="F00002", current_value="5000")  # LAGGING
    h3 = _fake_holding(mstar_id="F00003", current_value="5000")  # LEADING
    holdings = [h1, h2, h3]

    rs_map = {
        "F00001": {
            "mstar_id": "F00001",
            "latest_rs_composite": Decimal("70"),
            "rs_momentum_28d": Decimal("2"),
        },
        "F00002": {
            "mstar_id": "F00002",
            "latest_rs_composite": Decimal("30"),
            "rs_momentum_28d": Decimal("-2"),
        },
        "F00003": {
            "mstar_id": "F00003",
            "latest_rs_composite": Decimal("60"),
            "rs_momentum_28d": Decimal("1"),
        },
    }
    fund_details = {k: _jip_detail() for k in ["F00001", "F00002", "F00003"]}

    svc = _build_service(portfolio, holdings, fund_details, rs_map)
    result = await svc.analyze_portfolio(portfolio.id)

    qdist = result.portfolio.quadrant_distribution
    assert qdist.get("LEADING", 0) == 2
    assert qdist.get("LAGGING", 0) == 1


# ---------------------------------------------------------------------------
# Tests: provenance traceability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provenance_present_for_all_key_metrics() -> None:
    """Each key metric must have a source_table + formula provenance entry."""
    portfolio = _fake_portfolio()
    h1 = _fake_holding(mstar_id="F00001", current_value="5000")
    rs_map = {
        "F00001": {
            "mstar_id": "F00001",
            "latest_rs_composite": Decimal("65"),
            "rs_momentum_28d": Decimal("3"),
        }
    }
    fund_details = {"F00001": _jip_detail()}

    svc = _build_service(portfolio, [h1], fund_details, rs_map)
    result = await svc.analyze_portfolio(portfolio.id)

    # Portfolio-level provenance
    assert "weighted_rs" in result.portfolio.provenance
    assert "sector_weights" in result.portfolio.provenance
    p = result.portfolio.provenance["weighted_rs"]
    assert p.source_table
    assert p.formula

    # Per-holding provenance
    assert len(result.holdings) == 1
    ha = result.holdings[0]
    assert "rs_composite" in ha.provenance
    assert "nav" in ha.provenance


# ---------------------------------------------------------------------------
# Tests: not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_portfolio_raises_value_error_when_not_found() -> None:
    """analyze_portfolio raises ValueError when portfolio not found."""
    mock_repo = MagicMock()
    mock_repo.get_portfolio = AsyncMock(return_value=None)
    mock_jip = MagicMock()
    svc = PortfolioAnalysisService(repo=mock_repo, jip=mock_jip)

    with pytest.raises(ValueError, match="not found"):
        await svc.analyze_portfolio(uuid.uuid4())
