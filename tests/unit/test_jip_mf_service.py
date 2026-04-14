"""Cassette tests for JIPMFService (V2-2).

Each test mocks AsyncSession with a pre-recorded result set ("cassette")
and verifies:
  1. The method returns the expected shape
  2. session.execute was called (SQL was issued)
  3. Financial values are Decimal (never float)
  4. is_etf=false enforced in get_mf_universe queries

Naming convention: test_<method>_<scenario>_<expected>
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.clients import jip_mf_service as mf_service_module
from backend.clients.jip_mf_service import JIPMFService


@pytest.fixture(autouse=True)
def _clear_mf_caches():
    """Process-local TTL caches must not bleed between tests."""
    mf_service_module._mf_universe_cache.clear()
    mf_service_module._mf_universe_locks.clear()
    mf_service_module._mf_categories_cache.clear()
    mf_service_module._mf_rs_momentum_cache.clear()
    mf_service_module._mf_rs_momentum_last_failure.clear()
    yield
    mf_service_module._mf_universe_cache.clear()
    mf_service_module._mf_universe_locks.clear()
    mf_service_module._mf_categories_cache.clear()
    mf_service_module._mf_rs_momentum_cache.clear()
    mf_service_module._mf_rs_momentum_last_failure.clear()


# ---------------------------------------------------------------------------
# Minimal session / result doubles (reuse the established pattern from
# test_jip_service_timeout.py but lighter — just the MF service path).
# ---------------------------------------------------------------------------


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)

    def scalar_one_or_none(self) -> Any:
        return self._scalar


def _make_session(*responses: Any) -> MagicMock:
    """Build a mock AsyncSession that returns *responses* in order."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(responses))
    return session


def _probe(has_table: bool = True) -> "_Result":
    """Mock response for the to_regclass() table-existence probe."""
    return _Result(rows=[{"has_table": has_table}])


def _freshness_probe(**flags: bool) -> "_Result":
    """Mock response for the bulk freshness existence probe."""
    defaults = {
        "has_nav": True,
        "has_derived": True,
        "has_holdings": True,
        "has_sectors": True,
        "has_flows": True,
        "has_weighted": True,
        "has_master": True,
    }
    defaults.update(flags)
    return _Result(rows=[defaults])


# ---------------------------------------------------------------------------
# get_mf_holders — bug fix: fund_name not scheme_name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mf_holders_returns_fund_name_field():
    """get_mf_holders must return fund_name (not scheme_name — column rename fix)."""
    cassette = [
        {
            "mstar_id": "F00001",
            "fund_name": "HDFC Flexi Cap Fund",
            "weight_pct": "3.45",
            "shares_held": 1000,
            "market_value": "12345678.0000",
        }
    ]
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_mf_holders("HDFCBANK")

    assert session.execute.call_count == 1
    assert len(result) == 1
    row = result[0]
    assert "fund_name" in row
    assert "scheme_name" not in row
    assert isinstance(row["weight_pct"], Decimal)
    assert isinstance(row["market_value"], Decimal)


@pytest.mark.asyncio
async def test_get_mf_holders_empty_returns_empty_list():
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)
    result = await svc.get_mf_holders("UNKNOWN")
    assert result == []


# ---------------------------------------------------------------------------
# get_mf_universe — punch list item 2: is_etf=false
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mf_universe_sql_contains_is_etf_false():
    """get_mf_universe MUST include is_etf = false in the SQL."""
    cassette: list[dict[str, Any]] = []
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    await svc.get_mf_universe()

    assert session.execute.call_count == 1
    executed_sql = str(session.execute.call_args[0][0])
    assert "is_etf = false" in executed_sql.lower() or "is_etf=false" in executed_sql.lower()


@pytest.mark.asyncio
async def test_get_mf_universe_returns_decimal_financial_fields():
    cassette = [
        {
            "mstar_id": "F00001",
            "fund_name": "HDFC Flexi Cap Fund",
            "amc_name": "HDFC AMC",
            "category_name": "Flexi Cap",
            "broad_category": "Equity",
            "is_index_fund": False,
            "is_active": True,
            "inception_date": None,
            "amfi_code": "120503",
            "isin": "INF179K01BB8",
            "nav": "95.4321",
            "nav_date": "2026-04-14",
            "expense_ratio": "0.7500",
            "derived_rs_composite": "72.50",
            "nav_rs_composite": "68.00",
            "manager_alpha": "5.25",
            "sharpe_1y": "1.34",
            "sortino_1y": "1.87",
            "max_drawdown_1y": "-12.50",
            "volatility_1y": "14.20",
            "beta_vs_nifty": "0.95",
        }
    ]
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_mf_universe()

    assert len(result) == 1
    row = result[0]
    assert isinstance(row["nav"], Decimal)
    assert isinstance(row["expense_ratio"], Decimal)
    assert isinstance(row["derived_rs_composite"], Decimal)
    assert isinstance(row["manager_alpha"], Decimal)
    assert isinstance(row["sharpe_1y"], Decimal)
    assert isinstance(row["beta_vs_nifty"], Decimal)


@pytest.mark.asyncio
async def test_get_mf_universe_with_category_filter():
    """Category filter param must be passed to execute."""
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)

    await svc.get_mf_universe(category="Flexi Cap")

    executed_params = session.execute.call_args[0][1]
    assert executed_params.get("category") == "Flexi Cap"


@pytest.mark.asyncio
async def test_get_mf_universe_active_only_default_true():
    """active_only=True must produce is_active=true condition."""
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)

    await svc.get_mf_universe(active_only=True)

    executed_sql = str(session.execute.call_args[0][0])
    assert "is_active = true" in executed_sql.lower()


# ---------------------------------------------------------------------------
# get_mf_categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mf_categories_returns_decimal_flows():
    cassette = [
        {
            "category_name": "Flexi Cap",
            "broad_category": "Equity",
            "active_fund_count": 42,
            "avg_rs_composite": "65.30",
            "avg_manager_alpha": "3.10",
            "latest_flow_date": "2026-03-31",
            "net_flow_cr": "1234.56",
            "gross_inflow_cr": "2500.00",
            "gross_outflow_cr": "1265.44",
            "aum_cr": "98765.00",
            "sip_flow_cr": "800.00",
        }
    ]
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_mf_categories()

    assert len(result) == 1
    row = result[0]
    assert isinstance(row["avg_rs_composite"], Decimal)
    assert isinstance(row["net_flow_cr"], Decimal)
    assert isinstance(row["aum_cr"], Decimal)


@pytest.mark.asyncio
async def test_get_mf_categories_empty_returns_list():
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)
    result = await svc.get_mf_categories()
    assert result == []


# ---------------------------------------------------------------------------
# get_mf_flows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mf_flows_passes_months_param():
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)

    await svc.get_mf_flows(months=6)

    executed_params = session.execute.call_args[0][1]
    assert executed_params.get("months") == 6


@pytest.mark.asyncio
async def test_get_mf_flows_returns_decimal_values():
    cassette = [
        {
            "month_date": "2026-03-31",
            "category": "Flexi Cap",
            "net_flow_cr": "500.25",
            "gross_inflow_cr": "1200.00",
            "gross_outflow_cr": "699.75",
            "aum_cr": "50000.00",
            "sip_flow_cr": "300.00",
            "sip_accounts": 1000000,
            "folios": 2000000,
        }
    ]
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_mf_flows()

    assert len(result) == 1
    row = result[0]
    assert isinstance(row["net_flow_cr"], Decimal)
    assert isinstance(row["gross_inflow_cr"], Decimal)
    assert isinstance(row["aum_cr"], Decimal)


# ---------------------------------------------------------------------------
# get_fund_detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fund_detail_returns_none_when_not_found():
    session = _make_session(_probe(True), _Result(rows=[]))
    svc = JIPMFService(session)

    result = await svc.get_fund_detail("NONEXISTENT")

    assert result is None


@pytest.mark.asyncio
async def test_get_fund_detail_returns_decimal_fields():
    cassette = [
        {
            "mstar_id": "F00001",
            "fund_name": "HDFC Flexi Cap Fund",
            "amc_name": "HDFC AMC",
            "category_name": "Flexi Cap",
            "broad_category": "Equity",
            "is_index_fund": False,
            "is_etf": False,
            "is_active": True,
            "inception_date": None,
            "closure_date": None,
            "merged_into_mstar_id": None,
            "primary_benchmark": "NIFTY 500",
            "investment_strategy": None,
            "amfi_code": "120503",
            "isin": "INF179K01BB8",
            "expense_ratio": "0.7500",
            "nav": "95.4321",
            "nav_date": "2026-04-14",
            "derived_date": "2026-04-14",
            "derived_rs_composite": "72.50",
            "nav_rs_composite": "68.00",
            "manager_alpha": "5.25",
            "coverage_pct": "98.50",
            "sharpe_1y": "1.34",
            "sharpe_3y": "1.12",
            "sharpe_5y": "1.05",
            "sortino_1y": "1.87",
            "sortino_3y": None,
            "sortino_5y": None,
            "max_drawdown_1y": "-12.50",
            "max_drawdown_3y": "-18.20",
            "max_drawdown_5y": "-22.10",
            "volatility_1y": "14.20",
            "volatility_3y": "15.50",
            "stddev_1y": "2.10",
            "stddev_3y": "2.30",
            "stddev_5y": "2.50",
            "beta_vs_nifty": "0.95",
            "information_ratio": "0.45",
            "treynor_ratio": "0.12",
            "sector_count": 12,
            "sector_as_of": "2026-03-31",
            "holding_count": 65,
            "holdings_as_of": "2026-03-31",
            "weighted_as_of": "2026-04-14",
            "weighted_rsi": "58.30",
            "weighted_breadth_pct_above_200dma": "72.10",
            "weighted_macd_bullish_pct": "65.00",
        }
    ]
    session = _make_session(_probe(True), _Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_fund_detail("F00001")

    assert result is not None
    assert isinstance(result["nav"], Decimal)
    assert isinstance(result["expense_ratio"], Decimal)
    assert isinstance(result["derived_rs_composite"], Decimal)
    assert isinstance(result["manager_alpha"], Decimal)
    assert isinstance(result["sharpe_1y"], Decimal)
    assert isinstance(result["beta_vs_nifty"], Decimal)
    assert isinstance(result["weighted_rsi"], Decimal)
    # NULL fields must return None, not 0
    assert result["sortino_3y"] is None
    assert result["sortino_5y"] is None


@pytest.mark.asyncio
async def test_get_fund_detail_passes_mstar_id_param():
    session = _make_session(_probe(True), _Result(rows=[]))
    svc = JIPMFService(session)

    await svc.get_fund_detail("F00001")

    # call_args is the LAST call (the main fund-detail query, after the probe)
    params = session.execute.call_args[0][1]
    assert params.get("mstar_id") == "F00001"


# ---------------------------------------------------------------------------
# get_fund_holdings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fund_holdings_returns_decimal_weight():
    cassette = [
        {
            "mstar_id": "F00001",
            "as_of_date": "2026-03-31",
            "holding_name": "HDFC Bank Ltd",
            "isin": "INE040A01034",
            "instrument_id": 1001,
            "weight_pct": "8.45",
            "shares_held": 50000,
            "market_value": "75000000.0000",
            "sector_code": "FINS",
            "is_mapped": True,
            "current_symbol": "HDFCBANK",
            "sector": "Financials",
            "rs_composite": "78.20",
            "above_200dma": True,
            "rsi_14": "62.30",
        }
    ]
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_fund_holdings("F00001")

    assert len(result) == 1
    row = result[0]
    assert isinstance(row["weight_pct"], Decimal)
    assert isinstance(row["market_value"], Decimal)
    assert isinstance(row["rs_composite"], Decimal)
    assert isinstance(row["rsi_14"], Decimal)


@pytest.mark.asyncio
async def test_get_fund_holdings_empty_returns_list():
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)
    result = await svc.get_fund_holdings("F00001")
    assert result == []


# ---------------------------------------------------------------------------
# get_fund_sectors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fund_sectors_returns_decimal_weight():
    cassette = [
        {
            "sector": "Financials",
            "weight_pct": "35.20",
            "stock_count": 8,
            "as_of_date": "2026-03-31",
        },
        {
            "sector": "Technology",
            "weight_pct": "22.10",
            "stock_count": 6,
            "as_of_date": "2026-03-31",
        },
    ]
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_fund_sectors("F00001")

    assert len(result) == 2
    for row in result:
        assert isinstance(row["weight_pct"], Decimal)


@pytest.mark.asyncio
async def test_get_fund_sectors_empty_returns_list():
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)
    result = await svc.get_fund_sectors("F00001")
    assert result == []


# ---------------------------------------------------------------------------
# get_fund_rs_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fund_rs_history_returns_decimal_scores():
    cassette = [
        {
            "date": "2026-03-31",
            "rs_composite": "72.50",
            "rs_1w": "73.10",
            "rs_1m": "71.80",
            "rs_3m": "70.20",
            "rs_6m": "68.90",
            "rs_12m": "65.00",
            "vs_benchmark": "category",
        }
    ]
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_fund_rs_history("F00001", months=12)

    assert len(result) == 1
    row = result[0]
    assert isinstance(row["rs_composite"], Decimal)
    assert isinstance(row["rs_1w"], Decimal)
    assert isinstance(row["rs_12m"], Decimal)


@pytest.mark.asyncio
async def test_get_fund_rs_history_passes_months_param():
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)

    await svc.get_fund_rs_history("F00001", months=6)

    params = session.execute.call_args[0][1]
    assert params.get("months") == 6
    assert params.get("mstar_id") == "F00001"


@pytest.mark.asyncio
async def test_get_fund_rs_history_empty_returns_list():
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)
    result = await svc.get_fund_rs_history("F00001")
    assert result == []


# ---------------------------------------------------------------------------
# get_fund_weighted_technicals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fund_weighted_technicals_returns_decimal_fields():
    cassette = [
        {
            "mstar_id": "F00001",
            "as_of_date": "2026-04-14",
            "weighted_rsi": "58.30",
            "weighted_breadth_pct_above_200dma": "72.10",
            "weighted_macd_bullish_pct": "65.00",
        }
    ]
    session = _make_session(_probe(True), _Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_fund_weighted_technicals("F00001")

    assert result is not None
    assert isinstance(result["weighted_rsi"], Decimal)
    assert isinstance(result["weighted_breadth_pct_above_200dma"], Decimal)
    assert isinstance(result["weighted_macd_bullish_pct"], Decimal)


@pytest.mark.asyncio
async def test_get_fund_weighted_technicals_returns_none_when_not_found():
    session = _make_session(_probe(True), _Result(rows=[]))
    svc = JIPMFService(session)
    result = await svc.get_fund_weighted_technicals("F00001")
    assert result is None


@pytest.mark.asyncio
async def test_get_fund_weighted_technicals_returns_none_when_table_missing():
    """When JIP source table is not provisioned, return None gracefully."""
    session = _make_session(_probe(False))
    svc = JIPMFService(session)
    result = await svc.get_fund_weighted_technicals("F00001")
    assert result is None
    assert session.execute.call_count == 1


# ---------------------------------------------------------------------------
# get_fund_nav_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fund_nav_history_returns_decimal_nav():
    cassette = [
        {"nav_date": "2026-04-14", "nav": "95.4321"},
        {"nav_date": "2026-04-13", "nav": "94.8100"},
    ]
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_fund_nav_history("F00001")

    assert len(result) == 2
    for row in result:
        assert isinstance(row["nav"], Decimal)


@pytest.mark.asyncio
async def test_get_fund_nav_history_passes_date_range():
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)

    await svc.get_fund_nav_history("F00001", date_from="2026-01-01", date_to="2026-04-14")

    params = session.execute.call_args[0][1]
    assert params.get("date_from") == "2026-01-01"
    assert params.get("date_to") == "2026-04-14"
    assert params.get("mstar_id") == "F00001"


@pytest.mark.asyncio
async def test_get_fund_nav_history_no_date_filter():
    """Without date_from/date_to, params must not include those keys."""
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)

    await svc.get_fund_nav_history("F00001")

    params = session.execute.call_args[0][1]
    assert "date_from" not in params
    assert "date_to" not in params


# ---------------------------------------------------------------------------
# get_fund_overlap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fund_overlap_returns_decimal_overlap_pct():
    # Two execute calls: agg query + detail query
    agg_cassette = [
        {
            "count_a": 65,
            "count_b": 58,
            "common_count": 22,
            "overlap_pct": "31.50",
        }
    ]
    detail_cassette = [
        {
            "instrument_id": 1001,
            "holding_name": "HDFC Bank Ltd",
            "weight_pct_a": "8.45",
            "weight_pct_b": "7.20",
        }
    ]
    session = _make_session(
        _Result(rows=agg_cassette),
        _Result(rows=detail_cassette),
    )
    svc = JIPMFService(session)

    result = await svc.get_fund_overlap("F00001", "F00002")

    assert session.execute.call_count == 2
    assert isinstance(result["overlap_pct"], Decimal)
    assert result["overlap_pct"] == Decimal("31.50")
    assert result["common_count"] == 22
    assert result["mstar_id_a"] == "F00001"
    assert result["mstar_id_b"] == "F00002"
    assert len(result["common_holdings"]) == 1
    holding = result["common_holdings"][0]
    assert isinstance(holding["weight_pct_a"], Decimal)
    assert isinstance(holding["weight_pct_b"], Decimal)


@pytest.mark.asyncio
async def test_get_fund_overlap_zero_common_holdings():
    """No overlap: overlap_pct=0, common_holdings=[]."""
    agg_cassette = [
        {
            "count_a": 65,
            "count_b": 58,
            "common_count": 0,
            "overlap_pct": None,
        }
    ]
    session = _make_session(
        _Result(rows=agg_cassette),
        _Result(rows=[]),
    )
    svc = JIPMFService(session)

    result = await svc.get_fund_overlap("F00001", "F00002")

    assert result["overlap_pct"] == Decimal("0")
    assert result["common_holdings"] == []


# ---------------------------------------------------------------------------
# get_fund_lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_fund_lifecycle_returns_list():
    cassette = [
        {
            "mstar_id": "F00001",
            "event_type": "scheme_merger",
            "effective_date": "2024-09-01",
            "detail": "Merged XYZ Fund into this fund",
        }
    ]
    session = _make_session(_Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_fund_lifecycle("F00001")

    assert len(result) == 1
    assert result[0]["event_type"] == "scheme_merger"


@pytest.mark.asyncio
async def test_get_fund_lifecycle_empty_returns_list():
    session = _make_session(_Result(rows=[]))
    svc = JIPMFService(session)
    result = await svc.get_fund_lifecycle("F00001")
    assert result == []


# ---------------------------------------------------------------------------
# get_mf_data_freshness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_mf_data_freshness_returns_dict():
    cassette = [
        {
            "nav_as_of": "2026-04-14",
            "derived_as_of": "2026-04-14",
            "holdings_as_of": "2026-03-31",
            "sectors_as_of": "2026-03-31",
            "flows_as_of": "2026-03-31",
            "weighted_as_of": "2026-04-14",
            "active_fund_count": 3820,
        }
    ]
    session = _make_session(_freshness_probe(), _Result(rows=cassette))
    svc = JIPMFService(session)

    result = await svc.get_mf_data_freshness()

    assert isinstance(result, dict)
    assert result["active_fund_count"] == 3820


@pytest.mark.asyncio
async def test_get_mf_data_freshness_empty_table_returns_dict():
    session = _make_session(_freshness_probe(), _Result(rows=[]))
    svc = JIPMFService(session)
    result = await svc.get_mf_data_freshness()
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_get_mf_data_freshness_tolerant_of_missing_weighted_table():
    """Missing de_mf_weighted_technicals must not 500 — returns NULL for that key."""
    cassette = [
        {
            "nav_as_of": "2026-04-14",
            "derived_as_of": "2026-04-14",
            "holdings_as_of": "2026-03-31",
            "sectors_as_of": "2026-03-31",
            "flows_as_of": "2026-03-31",
            "active_fund_count": 3820,
        }
    ]
    session = _make_session(
        _freshness_probe(has_weighted=False),
        _Result(rows=cassette),
    )
    svc = JIPMFService(session)
    result = await svc.get_mf_data_freshness()
    assert result["weighted_as_of"] is None
    assert result["nav_as_of"] == "2026-04-14"
    assert result["active_fund_count"] == 3820


# ---------------------------------------------------------------------------
# Pipeline-level punch list item 3: verify no direct de_* SQL in pipeline.py
# ---------------------------------------------------------------------------


def test_pipeline_py_has_no_direct_de_sql():
    """pipeline.py must not contain direct de_* SQL strings (punch list item 3)."""
    import re

    with open("/home/ubuntu/atlas/backend/pipeline.py") as f:
        source = f.read()

    # Check for direct SQL string with de_ table reference outside a string comment
    # The old offender was: text("SELECT MAX(date) FROM de_rs_scores")
    direct_sql_pattern = re.compile(r'text\s*\(\s*["\'].*\bde_\w+\b', re.DOTALL)
    matches = direct_sql_pattern.findall(source)
    assert matches == [], f"pipeline.py still contains direct de_* SQL via text(): {matches}"


# ---------------------------------------------------------------------------
# JIPMarketService.get_latest_rs_date — new method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_rs_date_returns_date_string():
    """JIPMarketService.get_latest_rs_date must return ISO date string."""
    import datetime

    from backend.clients.jip_market_service import JIPMarketService

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = datetime.date(2026, 4, 14)

    session = MagicMock()
    session.execute = AsyncMock(return_value=result_mock)

    svc = JIPMarketService(session)
    result = await svc.get_latest_rs_date()

    assert result == "2026-04-14"


@pytest.mark.asyncio
async def test_get_latest_rs_date_returns_none_when_empty():
    from backend.clients.jip_market_service import JIPMarketService

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None

    session = MagicMock()
    session.execute = AsyncMock(return_value=result_mock)

    svc = JIPMarketService(session)
    result = await svc.get_latest_rs_date()

    assert result is None
