"""Tests for backend.services.conviction_engine — C-DER-2.

All tests mock AsyncSession.execute. Do NOT hit real DB.
Covers: four_factor computation, action/urgency derivation, screener bulk,
SQL injection prevention, percentile rank server-side guarantee.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import backend.services.conviction_engine as conviction_engine_module
from backend.models.conviction import (
    ActionSignal,
    ConvictionLevel,
    UrgencyLevel,
)
from backend.services.conviction_engine import (
    _compute_conviction_from_factors,
    compute_four_factor,
    compute_screener_bulk,
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mapping_mock(row_data: dict[str, Any] | None) -> MagicMock:
    """Return a mock result where .mappings().first() returns row_data."""
    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = row_data
    return mock_result


def _make_all_mock(rows: list[dict[str, Any]]) -> MagicMock:
    """Return a mock result where .mappings().all() returns rows."""
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = rows
    return mock_result


async def _make_db_four_factor(row_data: dict[str, Any] | None) -> AsyncMock:
    """Create mock AsyncSession that returns row_data from execute().mappings().first()."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_mapping_mock(row_data))
    return db


async def _make_db_screener(rows: list[dict[str, Any]]) -> AsyncMock:
    """Create mock AsyncSession that returns rows from execute().mappings().all()."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_all_mock(rows))
    return db


def _full_row(
    rs: float = 110.0,
    pct_rank: float = 0.75,
    sector_rs: float = 110.0,
    cmf: float = 0.1,
    mfi: float = 55.0,
    roc_21: float = 5.0,
    roc_5: float = 4.0,
) -> dict[str, Any]:
    """Convenience factory for a fully-aligned technical row."""
    return {
        "roc_21": roc_21,
        "cmf_20": cmf,
        "mfi_14": mfi,
        "roc_5": roc_5,
        "rs_composite": rs,
        "sector_rs_composite": sector_rs,
        "roc_21_pct_rank": pct_rank,
    }


def _screener_row(
    rs: float = 110.0,
    pct_rank: float = 0.75,
    sector_rs: float = 110.0,
    cmf: float = 0.1,
    mfi: float = 55.0,
    roc_21: float = 5.0,
    roc_5: float = 4.0,
    symbol: str = "TEST",
    company_name: str = "Test Co",
    sector: str = "Banking",
) -> dict[str, Any]:
    """Factory for a screener result row."""
    return {
        "symbol": symbol,
        "company_name": company_name,
        "sector": sector,
        "rs_composite": rs,
        "roc_21_pct_rank": pct_rank,
        "sector_rs": sector_rs,
        "cmf_20": cmf,
        "mfi_14": mfi,
        "roc_21": roc_21,
        "roc_5": roc_5,
        "rsi_14": 62.0,
        "above_50dma": True,
        "above_200dma": True,
        "macd_bullish": True,
        "market_cap_cr": 50000.0,
        "pe_ratio": 25.0,
        "nifty_50": True,
        "nifty_500": True,
    }


# ---------------------------------------------------------------------------
# Test 1: All 4 factors true → HIGH+
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_factor_all_true_returns_high_plus() -> None:
    """rs=105, pct_rank=0.75, sector_rs=105, cmf=0.1, mfi=55 → HIGH_PLUS, aligned=4."""
    db = await _make_db_four_factor(_full_row())
    result = await compute_four_factor(uuid4(), "Energy", db)

    assert result is not None
    assert result.conviction_level == ConvictionLevel.HIGH_PLUS
    assert result.factors_aligned == 4
    assert result.factor_volume_rs is True


# ---------------------------------------------------------------------------
# Test 2: All 4 factors false → AVOID
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_factor_zero_returns_avoid() -> None:
    """rs=90, pct_rank=0.3, sector_rs=90, cmf=-0.1, mfi=40 → AVOID, aligned=0."""
    row = _full_row(rs=90.0, pct_rank=0.3, sector_rs=90.0, cmf=-0.1, mfi=40.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db)

    assert result is not None
    assert result.conviction_level == ConvictionLevel.AVOID
    assert result.factors_aligned == 0


# ---------------------------------------------------------------------------
# Test 3: Three factors aligned → HIGH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_factor_three_aligned_returns_high() -> None:
    """3 factors True → HIGH."""
    # volume_rs fails: cmf > 0 but mfi <= 50
    row = _full_row(cmf=0.1, mfi=45.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db)

    assert result is not None
    assert result.conviction_level == ConvictionLevel.HIGH
    assert result.factors_aligned == 3


# ---------------------------------------------------------------------------
# Test 4: Two factors aligned → MEDIUM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_factor_two_aligned_returns_medium() -> None:
    """2 factors True → MEDIUM."""
    # returns_rs and momentum_rs pass, sector_rs and volume_rs fail
    row = _full_row(sector_rs=90.0, cmf=-0.1, mfi=40.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db)

    assert result is not None
    assert result.conviction_level == ConvictionLevel.MEDIUM
    assert result.factors_aligned == 2


# ---------------------------------------------------------------------------
# Test 5: One factor aligned → LOW
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_factor_one_aligned_returns_low() -> None:
    """1 factor True → LOW."""
    # Only returns_rs passes
    row = _full_row(pct_rank=0.3, sector_rs=90.0, cmf=-0.1, mfi=40.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db)

    assert result is not None
    assert result.conviction_level == ConvictionLevel.LOW
    assert result.factors_aligned == 1


# ---------------------------------------------------------------------------
# Test 6: sector_rs factor reads sector table correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_factor_sector_rs_reads_sector_table() -> None:
    """sector_rs_composite=105 → factor_sector_rs=True."""
    row = _full_row(sector_rs=105.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Banking", db)

    assert result is not None
    assert result.factor_sector_rs is True
    assert result.sector_rs_composite == Decimal("105.0")


# ---------------------------------------------------------------------------
# Test 7: volume_rs requires BOTH cmf > 0 AND mfi > 50
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_factor_volume_rs_requires_both() -> None:
    """Test three sub-cases for volume_rs: partial conditions → False."""
    # Case 1: cmf=0.1, mfi=45 → False (mfi too low)
    row1 = _full_row(cmf=0.1, mfi=45.0)
    db1 = await _make_db_four_factor(row1)
    r1 = await compute_four_factor(uuid4(), "Energy", db1)
    assert r1 is not None
    assert r1.factor_volume_rs is False

    # Case 2: cmf=-0.1, mfi=55 → False (cmf non-positive)
    row2 = _full_row(cmf=-0.1, mfi=55.0)
    db2 = await _make_db_four_factor(row2)
    r2 = await compute_four_factor(uuid4(), "Energy", db2)
    assert r2 is not None
    assert r2.factor_volume_rs is False

    # Case 3: cmf=0.1, mfi=55 → True (both conditions met)
    row3 = _full_row(cmf=0.1, mfi=55.0)
    db3 = await _make_db_four_factor(row3)
    r3 = await compute_four_factor(uuid4(), "Energy", db3)
    assert r3 is not None
    assert r3.factor_volume_rs is True


# ---------------------------------------------------------------------------
# Test 8: Missing sector → factor_sector_rs=False, model still returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_factor_handles_missing_sector() -> None:
    """sector_rs_composite=None → factor_sector_rs=False, model not None."""
    row = _full_row()
    row["sector_rs_composite"] = None
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), None, db)

    assert result is not None
    assert result.factor_sector_rs is False
    assert result.sector_rs_composite is None


# ---------------------------------------------------------------------------
# Test 9: No tech row → returns None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_four_factor_handles_missing_tech_row() -> None:
    """execute returns None from first() → returns None."""
    db = await _make_db_four_factor(None)
    result = await compute_four_factor(uuid4(), "Energy", db)

    assert result is None


# ---------------------------------------------------------------------------
# Test 10: BULL regime + HIGH_PLUS → BUY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_bull_regime_high_plus_returns_buy() -> None:
    """factors_aligned=4, regime='BULL' → BUY."""
    db = await _make_db_four_factor(_full_row())
    result = await compute_four_factor(uuid4(), "Energy", db, regime="BULL")

    assert result is not None
    assert result.conviction_level == ConvictionLevel.HIGH_PLUS
    assert result.action_signal == ActionSignal.BUY


# ---------------------------------------------------------------------------
# Test 11: BEAR regime + HIGH → ACCUMULATE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_bear_regime_high_returns_accumulate() -> None:
    """factors_aligned=3, regime='BEAR' → ACCUMULATE (not BUY)."""
    # 3 factors: volume_rs fails
    row = _full_row(cmf=0.1, mfi=45.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db, regime="BEAR")

    assert result is not None
    assert result.conviction_level == ConvictionLevel.HIGH
    assert result.action_signal == ActionSignal.ACCUMULATE


# ---------------------------------------------------------------------------
# Test 12: MEDIUM → WATCH regardless of regime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_medium_returns_watch() -> None:
    """factors_aligned=2 → WATCH regardless of regime."""
    row = _full_row(sector_rs=90.0, cmf=-0.1, mfi=40.0)

    for regime_val in ("BULL", "BEAR", "SIDEWAYS", "RECOVERY"):
        db = await _make_db_four_factor(row)
        result = await compute_four_factor(uuid4(), "Energy", db, regime=regime_val)
        assert result is not None
        assert result.action_signal == ActionSignal.WATCH, (
            f"regime={regime_val}: expected WATCH, got {result.action_signal}"
        )


# ---------------------------------------------------------------------------
# Test 13: LOW + rs_composite < 100 → REDUCE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_low_falling_returns_reduce() -> None:
    """factors_aligned=1, rs_composite=95 → REDUCE."""
    # Only rs_composite factor passes but rs_composite=95 (< 100)
    # Wait — if rs_composite < 100, factor_returns_rs is False.
    # So we need only momentum_rs to be the single passing factor
    row = _full_row(rs=95.0, pct_rank=0.75, sector_rs=90.0, cmf=-0.1, mfi=40.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db, regime="SIDEWAYS")

    assert result is not None
    assert result.conviction_level == ConvictionLevel.LOW
    assert result.factors_aligned == 1
    assert result.rs_composite == Decimal("95.0")
    assert result.action_signal == ActionSignal.REDUCE


# ---------------------------------------------------------------------------
# Test 14: AVOID → EXIT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_avoid_returns_exit() -> None:
    """factors_aligned=0 → EXIT."""
    row = _full_row(rs=90.0, pct_rank=0.3, sector_rs=90.0, cmf=-0.1, mfi=40.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db, regime="BULL")

    assert result is not None
    assert result.conviction_level == ConvictionLevel.AVOID
    assert result.action_signal == ActionSignal.EXIT


# ---------------------------------------------------------------------------
# Test 15: HIGH_PLUS + roc_5 > 3 → IMMEDIATE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_urgency_immediate_strong_momentum() -> None:
    """HIGH_PLUS + roc_5=3.5 → IMMEDIATE."""
    row = _full_row(roc_5=3.5)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db, regime="BULL")

    assert result is not None
    assert result.conviction_level == ConvictionLevel.HIGH_PLUS
    assert result.urgency == UrgencyLevel.IMMEDIATE


# ---------------------------------------------------------------------------
# Test 16: HIGH + roc_21 > 0 → DEVELOPING
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_urgency_developing_positive_roc21() -> None:
    """HIGH + roc_21=2.0 → DEVELOPING (roc_5 <= 3 so not IMMEDIATE)."""
    # 3 factors: volume_rs fails (mfi=45 too low)
    row = _full_row(cmf=0.1, mfi=45.0, roc_5=1.0, roc_21=2.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db, regime="BULL")

    assert result is not None
    assert result.conviction_level == ConvictionLevel.HIGH
    assert result.urgency == UrgencyLevel.DEVELOPING


# ---------------------------------------------------------------------------
# Test 17: MEDIUM → PATIENT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_urgency_patient_default() -> None:
    """MEDIUM conviction → PATIENT urgency."""
    row = _full_row(sector_rs=90.0, cmf=-0.1, mfi=40.0)
    db = await _make_db_four_factor(row)
    result = await compute_four_factor(uuid4(), "Energy", db, regime="SIDEWAYS")

    assert result is not None
    assert result.conviction_level == ConvictionLevel.MEDIUM
    assert result.urgency == UrgencyLevel.PATIENT


# ---------------------------------------------------------------------------
# Test 18: Percentile rank computed in SQL, not Python sorted()
# ---------------------------------------------------------------------------


def test_screener_uses_sql_percentile_not_python() -> None:
    """Module source must contain percent_rank() and must NOT use Python sorted()."""
    source = inspect.getsource(conviction_engine_module)
    assert "percent_rank" in source, (
        "conviction_engine must use SQL percent_rank() for percentile computation"
    )
    # Confirm Python-side sorting is NOT used for percentile rank
    assert "sorted(" not in source.replace("# never sorted in Python", "").replace(
        "# never sort", ""
    ), "conviction_engine must not use Python sorted() for percentile calculation"


# ---------------------------------------------------------------------------
# Test 19: Screener filters by universe (nifty50 → SQL contains nifty_50=true)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_filters_by_nifty50() -> None:
    """filters['universe']='nifty50' → SQL contains 'nifty_50 = true'."""
    captured_sql: list[str] = []

    async def capture_execute(query: Any, params: Any = None) -> Any:
        captured_sql.append(str(query))
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        return mock_result

    db = AsyncMock()
    db.execute = capture_execute

    await compute_screener_bulk({"universe": "nifty50", "limit": 50, "offset": 0}, db)

    assert len(captured_sql) == 1
    assert "nifty_50 = true" in captured_sql[0], (
        f"SQL should contain 'nifty_50 = true' for universe=nifty50. Got:\n{captured_sql[0]}"
    )


# ---------------------------------------------------------------------------
# Test 20: Sector filter uses bind param, not string interpolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_filters_by_sector_param_bound() -> None:
    """filters['sector']='Banking' → SQL uses :sector bind param, not literal."""
    captured_sql: list[str] = []

    async def capture_execute(query: Any, params: Any = None) -> Any:
        captured_sql.append(str(query))
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        return mock_result

    db = AsyncMock()
    db.execute = capture_execute

    await compute_screener_bulk({"sector": "Banking", "limit": 50, "offset": 0}, db)

    assert len(captured_sql) == 1
    sql = captured_sql[0]
    # SQL should have the :sector placeholder (or the bindparams-compiled form)
    # but should NOT have the literal string "Banking" interpolated directly
    assert "Banking" not in sql, (
        "Sector value 'Banking' must not be interpolated into SQL directly — use a bind parameter"
    )
    # The sector filter clause should appear in the SQL
    assert "sector" in sql.lower(), "SQL should contain a sector filter clause"


# ---------------------------------------------------------------------------
# Test 21: Conviction post-filter returns only matching rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_filters_by_conviction_python_side() -> None:
    """5 mocked rows with mixed convictions, conviction_filter='HIGH' → only HIGH."""
    # Row factors:
    # A: rs=110(T), pct_rank=0.75(T), sector=110(T), cmf+mfi=55(T) → 4 → HIGH+
    # B: rs=110(T), pct_rank=0.75(T), sector=110(T), cmf+mfi=45(F) → 3 → HIGH
    # C: rs=110(T), pct_rank=0.75(T), sector=90(F),  cmf=-0.1(F)   → 2 → MEDIUM
    # D: rs=110(T), pct_rank=0.3(F),  sector=90(F),  cmf=-0.1(F)   → 1 → LOW
    # E: rs=90(F),  pct_rank=0.3(F),  sector=90(F),  cmf=-0.1(F)   → 0 → AVOID
    rows = [
        _screener_row(
            rs=110.0, pct_rank=0.75, sector_rs=110.0, cmf=0.1, mfi=55.0, symbol="A"
        ),  # HIGH+ (4)
        _screener_row(
            rs=110.0, pct_rank=0.75, sector_rs=110.0, cmf=0.1, mfi=45.0, symbol="B"
        ),  # HIGH (3)
        _screener_row(
            rs=110.0, pct_rank=0.75, sector_rs=90.0, cmf=-0.1, mfi=40.0, symbol="C"
        ),  # MEDIUM (2)
        _screener_row(
            rs=110.0, pct_rank=0.3, sector_rs=90.0, cmf=-0.1, mfi=40.0, symbol="D"
        ),  # LOW (1)
        _screener_row(
            rs=90.0, pct_rank=0.3, sector_rs=90.0, cmf=-0.1, mfi=40.0, symbol="E"
        ),  # AVOID (0)
    ]
    db = await _make_db_screener(rows)
    result = await compute_screener_bulk({"conviction": "HIGH", "limit": 50, "offset": 0}, db)

    symbols = [r["symbol"] for r in result]
    assert len(result) == 1, f"Expected 1 HIGH row, got {len(result)}: {symbols}"
    assert result[0]["symbol"] == "B"
    assert result[0]["conviction_level"] == ConvictionLevel.HIGH


# ---------------------------------------------------------------------------
# Test 22: Screener returns correct conviction and action for known inputs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_returns_conviction_and_action() -> None:
    """rs=110, pct_rank=0.8, sector_rs=105, cmf=0.2, mfi=60, regime=BULL → HIGH_PLUS, BUY."""
    rows = [
        _screener_row(
            rs=110.0,
            pct_rank=0.8,
            sector_rs=105.0,
            cmf=0.2,
            mfi=60.0,
            roc_5=4.0,
            roc_21=6.0,
            symbol="RELIANCE",
        )
    ]
    db = await _make_db_screener(rows)
    result = await compute_screener_bulk({"regime": "BULL", "limit": 50, "offset": 0}, db)

    assert len(result) == 1
    assert result[0]["conviction_level"] == ConvictionLevel.HIGH_PLUS
    assert result[0]["action_signal"] == ActionSignal.BUY


# ---------------------------------------------------------------------------
# Test 23: Limit and offset are passed as bind params to the SQL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_limit_offset_pagination() -> None:
    """Verify SQL contains LIMIT and OFFSET bind param values."""
    captured_sql: list[str] = []

    async def capture_execute(query: Any, params: Any = None) -> Any:
        captured_sql.append(str(query))
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        return mock_result

    db = AsyncMock()
    db.execute = capture_execute

    await compute_screener_bulk({"limit": 25, "offset": 10}, db)

    assert len(captured_sql) == 1
    sql = captured_sql[0]
    # The SQL template includes LIMIT :limit OFFSET :offset
    assert "LIMIT" in sql.upper()
    assert "OFFSET" in sql.upper()


# ---------------------------------------------------------------------------
# Test 24: _compute_conviction_from_factors is a pure function (no async needed)
# ---------------------------------------------------------------------------


def test_compute_conviction_from_factors_pure_function() -> None:
    """Pure function: same inputs always produce same outputs."""
    c, a, u = _compute_conviction_from_factors(
        factors_aligned=4,
        rs_composite=Decimal("110"),
        roc_5=Decimal("4"),
        roc_21=Decimal("6"),
        regime="BULL",
    )
    assert c == ConvictionLevel.HIGH_PLUS
    assert a == ActionSignal.BUY
    assert u == UrgencyLevel.IMMEDIATE

    # Second call — same result
    c2, a2, u2 = _compute_conviction_from_factors(
        factors_aligned=4,
        rs_composite=Decimal("110"),
        roc_5=Decimal("4"),
        roc_21=Decimal("6"),
        regime="BULL",
    )
    assert c == c2 and a == a2 and u == u2


# ---------------------------------------------------------------------------
# Test 25: RECOVERY regime is treated like BULL for action derivation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_recovery_regime_acts_like_bull() -> None:
    """regime='RECOVERY' + HIGH_PLUS → BUY (RECOVERY is treated as bull)."""
    db = await _make_db_four_factor(_full_row())
    result = await compute_four_factor(uuid4(), "Energy", db, regime="RECOVERY")

    assert result is not None
    assert result.action_signal == ActionSignal.BUY
