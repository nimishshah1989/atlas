"""Tests for BookService."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.book_service import BookService

_D = Decimal


def _make_session() -> MagicMock:
    """Return a mock AsyncSession."""
    session = MagicMock(spec=AsyncSession)
    return session


def _make_svc(session: MagicMock | None = None) -> BookService:
    return BookService(session or _make_session())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_execute(rows: list) -> AsyncMock:
    """Return a mock session.execute() that yields the given rows via scalars().all()."""
    mock_execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows
    mock_execute.return_value = mock_result
    return mock_execute


# ---------------------------------------------------------------------------
# holdings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_holdings_empty_returns_empty_list():
    svc = _make_svc()
    svc._session.execute = _mock_execute([])

    result = await svc.holdings()
    assert result == []


@pytest.mark.asyncio
async def test_holdings_returns_row_with_hold_when_lens_fails():
    from backend.db.models import AtlasPortfolioHolding

    row = MagicMock(spec=AtlasPortfolioHolding)
    row.id = uuid.uuid4()
    row.portfolio_id = uuid.uuid4()
    row.mstar_id = "F00000TEST"
    row.scheme_name = "Test Fund"
    row.units = _D("100")
    row.nav = _D("50")
    row.current_value = _D("5000")
    row.cost_value = _D("4000")

    svc = _make_svc()
    svc._session.execute = _mock_execute([row])

    with patch.object(svc._lens, "get_lenses", side_effect=Exception("lens failed")):
        result = await svc.holdings()

    assert len(result) == 1
    assert result[0]["composite_action"] == "HOLD"
    assert result[0]["lens_summary"] is None


# ---------------------------------------------------------------------------
# watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchlist_empty_returns_empty_list():
    svc = _make_svc()
    svc._session.execute = _mock_execute([])

    result = await svc.watchlist()
    assert result == []


@pytest.mark.asyncio
async def test_watchlist_returns_symbol_rows():
    from backend.db.models import AtlasWatchlist

    wl = MagicMock(spec=AtlasWatchlist)
    wl.id = uuid.uuid4()
    wl.name = "My Watchlist"
    wl.symbols = ["RELIANCE", "INFY"]

    svc = _make_svc()
    svc._session.execute = _mock_execute([wl])

    with patch.object(svc._lens, "get_lenses", side_effect=Exception("lens error")):
        result = await svc.watchlist()

    assert len(result) == 2
    symbols = [r["symbol"] for r in result]
    assert "RELIANCE" in symbols
    assert "INFY" in symbols


# ---------------------------------------------------------------------------
# action_queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_queue_filters_sell_avoid_watch_only():
    from backend.db.models import AtlasPortfolioHolding

    def _make_holding(action: str) -> MagicMock:
        h = MagicMock(spec=AtlasPortfolioHolding)
        h.id = uuid.uuid4()
        h.portfolio_id = uuid.uuid4()
        h.mstar_id = f"FUND_{action}"
        h.scheme_name = f"Fund {action}"
        h.units = _D("10")
        h.nav = _D("100")
        h.current_value = _D("1000")
        h.cost_value = _D("900")
        return h

    holdings = [_make_holding(a) for a in ["HOLD", "SELL", "WATCH", "BUY", "AVOID"]]
    svc = _make_svc()
    svc._session.execute = _mock_execute(holdings)

    from backend.models.lenses import LensBundle, LensValue

    def _lens_for_action(action: str) -> LensBundle:
        return LensBundle(
            scope="mf",
            entity_id=f"FUND_{action}",
            benchmark="NIFTY 500",
            period="3M",
            lenses={"rs": LensValue(value=_D("50"))},
            composite_action=action,
            reason="test",
        )

    async def _mock_lens(scope: str, entity_id: str, **kwargs) -> LensBundle:
        # entity_id is like "FUND_SELL"
        action = entity_id.replace("FUND_", "")
        return _lens_for_action(action)

    with patch.object(svc._lens, "get_lenses", side_effect=_mock_lens):
        result = await svc.action_queue()

    actions = [r["composite_action"] for r in result]
    assert "HOLD" not in actions
    assert "BUY" not in actions
    assert "SELL" in actions
    assert "AVOID" in actions
    assert "WATCH" in actions
    # Sorted: SELL before AVOID before WATCH
    assert actions.index("SELL") < actions.index("AVOID")


# ---------------------------------------------------------------------------
# performance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_performance_computes_totals():
    from backend.db.models import AtlasPortfolioHolding

    def _make_row(current: str, cost: str) -> MagicMock:
        h = MagicMock(spec=AtlasPortfolioHolding)
        h.id = uuid.uuid4()
        h.current_value = _D(current)
        h.cost_value = _D(cost)
        return h

    rows = [_make_row("1000", "800"), _make_row("2000", "1500")]
    svc = _make_svc()
    svc._session.execute = _mock_execute(rows)

    result = await svc.performance()

    assert result["total_holdings"] == 2
    assert result["total_current_value"] == _D("3000")
    assert result["total_cost_value"] == _D("2300")
    assert result["total_gain"] == _D("700")
    assert result["gain_pct"] is not None
    # 700/2300 * 100
    expected = (_D("700") / _D("2300") * _D("100")).quantize(_D("0.01"))
    assert result["gain_pct"] == expected
