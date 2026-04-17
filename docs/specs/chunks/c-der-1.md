# C-DER-1: Stock Signal Engine — Gold RS + Piotroski + Enriched Deep Dive

**Slice:** V6.5 — Derived Signal Engine
**Depends on:** V6-5 (stocks/{symbol} route exists with conviction pillars), V6-1..V6-7 (TV TA pillar 3 wired)
**Blocks:** C-DER-2 (four-factor conviction reads gold_rs signal as supporting context)
**Complexity:** M (5–7 hours)
**Quality targets:** code: 82, security: 90, architecture: 85, api: 90

---

## Goal

Add two query-time derived signals to the existing `GET /api/v1/stocks/{symbol}` deep-dive response:

1. **Gold RS** — measures whether the stock outperforms or underperforms gold (GLD ETF) over 63 trading days. Produces an enum signal: AMPLIFIES_BULL / NEUTRAL / FRAGILE / AMPLIFIES_BEAR.
2. **Piotroski F-Score** — 9-point fundamentals quality score computed from de_equity_fundamentals and de_equity_fundamentals_history. Grades: WEAK / NEUTRAL / GOOD / STRONG.

Both signals are pure query-time derivations — no new atlas_* table is created. They are attached to the existing `StockDeepDive` model as Optional fields so the response is fully backward-compatible.

---

## Files

### New
- `backend/services/derived_signals.py` — `compute_gold_rs()` and `compute_piotroski()` service functions
- `tests/services/test_derived_signals.py` — unit tests for both service functions (18 minimum)

### Modified
- `backend/models/schemas.py` — add `GoldRSSignal` enum, `GoldRS` model, `PiotroskiDetail` model, `Piotroski` model; add `gold_rs` and `piotroski` Optional fields to `StockDeepDive`
- `backend/routes/stocks.py` — call both signals concurrently via `asyncio.gather` inside `get_stock_deep_dive`; pass results into `StockDeepDive` constructor
- `backend/db/session.py` — no change needed (session factory already exists)

---

## Contracts

### New Pydantic models (add to `backend/models/schemas.py`)

```python
class GoldRSSignal(str, Enum):
    AMPLIFIES_BULL = "AMPLIFIES_BULL"
    NEUTRAL = "NEUTRAL"
    FRAGILE = "FRAGILE"
    AMPLIFIES_BEAR = "AMPLIFIES_BEAR"


class GoldRS(BaseModel):
    signal: GoldRSSignal
    ratio_3m: Optional[Decimal] = None       # (1 + stock_return_3m) / (1 + gold_return_3m)
    stock_return_3m: Optional[Decimal] = None # (close_today - close_63d) / close_63d
    gold_return_3m: Optional[Decimal] = None  # (gld_today - gld_63d) / gld_63d
    as_of: Optional[date] = None             # date of the latest close used


class PiotroskiDetail(BaseModel):
    # Profitability (4 checks)
    f1_net_profit_positive: bool = False      # net_profit_cr > 0 (latest annual)
    f2_cfo_positive: bool = False             # cfo_cr > 0 (latest annual)
    f3_roe_improving: bool = False            # roe_pct this year > roe_pct prior year
    f4_quality_earnings: bool = False         # cfo_cr > net_profit_cr (accrual ratio)
    # Leverage / Liquidity (3 checks)
    f5_leverage_falling: bool = False         # debt_to_equity current < debt_to_equity prior year
    f6_liquidity_improving: bool = False      # equity_capital_cr / borrowings_cr proxy improving
    f7_no_dilution: bool = False              # equity_capital_cr current <= equity_capital_cr prior
    # Operating Efficiency (2 checks)
    f8_margin_expanding: bool = False         # opm_pct current > opm_pct prior year
    f9_asset_turnover_improving: bool = False # (revenue_cr / total_assets_cr) current > prior


class Piotroski(BaseModel):
    score: int                                # 0–9 count of True checks
    grade: str                                # "WEAK" / "NEUTRAL" / "GOOD" / "STRONG"
    detail: PiotroskiDetail
    as_of: Optional[date] = None             # fiscal_period_end of latest annual used
```

### Modified `StockDeepDive` (add two Optional fields after `mf_holder_count`)

```python
gold_rs: Optional[GoldRS] = None
piotroski: Optional[Piotroski] = None
```

---

## Implementation notes

### `backend/services/derived_signals.py`

#### `async def compute_gold_rs(instrument_id: UUID, db: AsyncSession, period_days: int = 63) -> Optional[GoldRS]`

Returns `None` (not raises) when any required data is missing. Logs a warning with structlog.

**SQL to get stock close prices:**
```sql
SELECT close_adj, date
FROM de_equity_technical_daily
WHERE instrument_id = :instrument_id
  AND date >= (SELECT MAX(date) FROM de_equity_technical_daily
               WHERE instrument_id = :instrument_id) - INTERVAL '95 days'
ORDER BY date DESC
LIMIT 80
```
- Take first row as `close_today` and `date_today`
- Take the row at index closest to `period_days` (63rd row by position, or the row whose date is earliest but within 95-day window if fewer rows exist). If fewer than 30 rows exist, return `None`.

**SQL to get GLD prices:**
```sql
SELECT close, date
FROM de_global_price_daily
WHERE ticker = 'GLD'
  AND date >= (SELECT MAX(date) FROM de_global_price_daily WHERE ticker = 'GLD')
              - INTERVAL '95 days'
ORDER BY date DESC
LIMIT 80
```
- Same logic: `gld_today` = first row, `gld_63d` = row at position ~63.
- If GLD has fewer than 30 rows, return `GoldRS(signal=GoldRSSignal.NEUTRAL, ratio_3m=None, stock_return_3m=None, gold_return_3m=None, as_of=None)` with `note` that GLD data is unavailable. Do NOT return hard `None` here — return a neutral signal with empty values so the response field is populated.

**Formulas (all Decimal arithmetic, never float):**
```python
stock_return = (close_today - close_63d) / close_63d
gold_return = (gld_today - gld_63d) / gld_63d
denominator = Decimal("1") + gold_return
if denominator == Decimal("0"):
    return None  # division guard
ratio = (Decimal("1") + stock_return) / denominator
```

**Signal thresholds:**
- ratio > Decimal("1.05") → AMPLIFIES_BULL
- ratio >= Decimal("0.95") → NEUTRAL
- ratio >= Decimal("0.85") → FRAGILE
- ratio < Decimal("0.85") → AMPLIFIES_BEAR

#### `async def compute_piotroski(instrument_id: UUID, db: AsyncSession) -> Optional[Piotroski]`

Returns `None` when no annual history rows exist. Logs a warning.

**SQL to fetch fundamentals history (annual rows only):**
```sql
SELECT
    fiscal_period_end,
    net_profit_cr,
    cfo_cr,
    opm_pct,
    revenue_cr,
    total_assets_cr,
    borrowings_cr,
    equity_capital_cr
FROM de_equity_fundamentals_history
WHERE instrument_id = :instrument_id
  AND period_type = 'annual'
ORDER BY fiscal_period_end DESC
LIMIT 3
```
Rows are ordered DESC so row[0] = latest annual, row[1] = prior year annual.
If fewer than 2 rows exist, compute only checks that don't need a prior-year comparison (F1, F2, F4); set all delta-based checks to `False`. Return partial score.

**SQL to fetch current point-in-time fundamentals (for ROE and D/E):**
```sql
SELECT roe_pct, debt_to_equity
FROM de_equity_fundamentals
WHERE instrument_id = :instrument_id
LIMIT 1
```

**Check-by-check logic:**

All comparisons use `Decimal` conversions via `Decimal(str(value))`. Treat `None` or missing values as check `False` (never skip, never 0-fill).

- **F1** `f1_net_profit_positive`: `latest.net_profit_cr is not None and Decimal(str(latest.net_profit_cr)) > Decimal("0")`
- **F2** `f2_cfo_positive`: `latest.cfo_cr is not None and Decimal(str(latest.cfo_cr)) > Decimal("0")`
- **F3** `f3_roe_improving`: requires `de_equity_fundamentals` (current `roe_pct`) and prior year from history. Proxy: compute implied prior ROE as `(prior.net_profit_cr / prior.equity_capital_cr * 100)` if both non-None and non-zero. Check current `roe_pct > prior_roe`. If either is None → `False`.
- **F4** `f4_quality_earnings`: `latest.cfo_cr is not None and latest.net_profit_cr is not None and Decimal(str(latest.cfo_cr)) > Decimal(str(latest.net_profit_cr))`
- **F5** `f5_leverage_falling`: `de_equity_fundamentals.debt_to_equity` (current) must be < `(prior.borrowings_cr / prior.equity_capital_cr)` proxy. If either None → `False`. Use `de_equity_fundamentals.debt_to_equity` for current; compute prior D/E as `borrowings_cr / equity_capital_cr` from history row[1].
- **F6** `f6_liquidity_improving`: proxy is `(equity_capital_cr / borrowings_cr)`. Current = latest row; prior = row[1]. Check current ratio > prior ratio. Guard: if `borrowings_cr == 0` in either period → `False` (avoid division by zero).
- **F7** `f7_no_dilution`: `latest.equity_capital_cr is not None and prior.equity_capital_cr is not None and Decimal(str(latest.equity_capital_cr)) <= Decimal(str(prior.equity_capital_cr))`
- **F8** `f8_margin_expanding`: `latest.opm_pct is not None and prior.opm_pct is not None and Decimal(str(latest.opm_pct)) > Decimal(str(prior.opm_pct))`
- **F9** `f9_asset_turnover_improving`: asset turnover = revenue_cr / total_assets_cr. Check current ratio > prior ratio. Guard: if `total_assets_cr == 0` in either period → `False`.

**Grade thresholds:**
- score 0–2 → "WEAK"
- score 3–5 → "NEUTRAL"
- score 6–7 → "GOOD"
- score 8–9 → "STRONG"

**`as_of`** = `latest.fiscal_period_end` if available.

### Wiring into `backend/routes/stocks.py`

Inside `get_stock_deep_dive`, AFTER fetching `stock_detail` and BEFORE building `StockDeepDive`:

```python
import asyncio
from backend.services.derived_signals import compute_gold_rs, compute_piotroski
from backend.db.session import async_session_factory

# Each concurrent query needs its own session (asyncpg cannot multiplex).
async def _gold_rs_task() -> Optional[GoldRS]:
    async with async_session_factory() as s:
        return await compute_gold_rs(stock_detail["id"], s)

async def _piotroski_task() -> Optional[Piotroski]:
    async with async_session_factory() as s:
        return await compute_piotroski(stock_detail["id"], s)

gold_rs_result, piotroski_result = await asyncio.gather(
    _gold_rs_task(),
    _piotroski_task(),
    return_exceptions=True,
)

# Safely unwrap — if gather raised, leave as None
gold_rs_val = gold_rs_result if isinstance(gold_rs_result, GoldRS) else None
piotroski_val = piotroski_result if isinstance(piotroski_result, Piotroski) else None
```

Then pass `gold_rs=gold_rs_val, piotroski=piotroski_val` into the `StockDeepDive(...)` constructor.

The existing TV TA gather should NOT be combined into the same gather because it uses a different error handling path (TVBridgeUnavailableError → partial_data=True). Keep the two gather blocks separate.

### Session isolation note

The Isolated-Session Parallel Gather pattern applies here: asyncpg cannot multiplex queries on a single `AsyncSession`. Each concurrent DB call in `asyncio.gather` must use its own session obtained from `async_session_factory`. See wiki article `isolated-session-parallel-gather.md`.

### Edge cases

| Scenario | Behaviour |
|---|---|
| GLD has fewer than 30 rows | Return `GoldRS(signal=NEUTRAL, ratio_3m=None, ...)` — not `None` |
| Stock has no close data at all | Return `None` for gold_rs |
| `gold_return = -1` (GLD fell to 0) | Guard denominator == 0, return `None` |
| Zero annual history rows for Piotroski | Return `None` for piotroski |
| Only one annual row (no prior year) | Compute F1/F2/F4 only; remaining checks = False; score = sum; still return model |
| net_profit_cr or cfo_cr is NULL | Treat check as False |
| borrowings_cr == 0 | Skip F5/F6 for that year (return False for check) |
| total_assets_cr == 0 | Skip F9 (return False for check) |

---

## Acceptance criteria

1. `GET /api/v1/stocks/RELIANCE` response contains `stock.gold_rs` with `signal`, `ratio_3m`, `stock_return_3m`, `gold_return_3m`, `as_of`.
2. `GET /api/v1/stocks/RELIANCE` response contains `stock.piotroski` with `score` (int 0–9), `grade` (one of WEAK/NEUTRAL/GOOD/STRONG), `detail` (9 bool fields).
3. When GLD data has fewer than 30 rows (mocked), `gold_rs.signal == "NEUTRAL"` and all Decimal fields are `None`.
4. When de_equity_fundamentals_history has no annual rows for a stock, `piotroski` is `None` in the response.
5. Piotroski score 8–9 → grade "STRONG"; 6–7 → "GOOD"; 3–5 → "NEUTRAL"; 0–2 → "WEAK".
6. `compute_gold_rs` and `compute_piotroski` run concurrently (asyncio.gather, separate sessions).
7. Neither computation raises an exception when data is missing — always returns `Optional[model]`.
8. All Decimal values in GoldRS and Piotroski come from `Decimal(str(value))`, never from `float()`.
9. `ruff check . --select E,F,W` passes on all new/modified files.
10. `pytest tests/services/test_derived_signals.py -v` shows all 18+ tests passing.

---

## Tests

File: `tests/services/test_derived_signals.py`

All tests use `AsyncMock` for the DB session. Use `unittest.mock.patch` on the `sqlalchemy.ext.asyncio.AsyncSession.execute` method. Do NOT hit a real database.

```
test_gold_rs_amplifies_bull_when_stock_beats_gold_by_5pct
    Mock stock return = 0.20, gold return = 0.10
    ratio = 1.20/1.10 ≈ 1.0909 > 1.05 → AMPLIFIES_BULL
    Assert signal == GoldRSSignal.AMPLIFIES_BULL

test_gold_rs_neutral_within_band
    Mock ratio = 1.00 (stock return = gold return = 0.10)
    0.95 <= 1.00 <= 1.05 → NEUTRAL
    Assert signal == GoldRSSignal.NEUTRAL

test_gold_rs_fragile_below_band
    Mock stock return = 0.05, gold return = 0.15
    ratio = 1.05/1.15 ≈ 0.913 → between 0.85 and 0.95 → FRAGILE
    Assert signal == GoldRSSignal.FRAGILE

test_gold_rs_amplifies_bear_severely_underperforms
    Mock stock return = -0.20, gold return = 0.10
    ratio = 0.80/1.10 ≈ 0.727 < 0.85 → AMPLIFIES_BEAR
    Assert signal == GoldRSSignal.AMPLIFIES_BEAR

test_gold_rs_handles_missing_gld_data_gracefully
    Mock GLD query returns fewer than 30 rows (e.g. 5 rows)
    Assert return value is a GoldRS instance (not None)
    Assert signal == GoldRSSignal.NEUTRAL
    Assert ratio_3m is None

test_gold_rs_handles_missing_stock_data_returns_none
    Mock stock close query returns 0 rows
    Assert return value is None

test_gold_rs_ratio_uses_3m_period_default
    Call with default period_days=63
    Verify the stock price query fetches rows in 95-day window (check SQL params)

test_piotroski_perfect_score_returns_9_strong
    Mock all 9 checks to pass (valid annual data for 2 years)
    Assert score == 9 and grade == "STRONG"

test_piotroski_zero_score_returns_0_weak
    Mock all checks fail (negative profit, negative CFO, dilution, etc.)
    Assert score == 0 and grade == "WEAK"

test_piotroski_handles_missing_history_gracefully
    Mock de_equity_fundamentals_history returns 0 annual rows
    Assert return value is None

test_piotroski_f4_quality_earnings_cfo_gt_profit
    Mock cfo_cr=100, net_profit_cr=80 → F4=True
    Mock cfo_cr=50, net_profit_cr=80 → F4=False
    Assert both cases produce correct F4 value in detail

test_piotroski_f7_no_dilution_check
    Mock equity_capital_cr current=100, prior=110 → F7=True (no new shares)
    Mock equity_capital_cr current=110, prior=100 → F7=False (diluted)
    Assert both cases produce correct F7 value

test_piotroski_grade_thresholds_weak_neutral_good_strong
    Force scores 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
    Assert grades: [0-2]=WEAK, [3-5]=NEUTRAL, [6-7]=GOOD, [8-9]=STRONG

test_piotroski_f9_asset_turnover_improving
    Mock current: revenue=1000, assets=500 (turnover=2.0)
    Mock prior:   revenue=800,  assets=500 (turnover=1.6)
    Assert F9=True
    Mock prior: revenue=1200, assets=500 (turnover=2.4) → F9=False

test_compute_piotroski_uses_annual_period_type
    Verify SQL query contains period_type = 'annual' parameter

test_piotroski_single_annual_row_partial_score
    Mock returns only 1 annual row (no prior year data)
    Assert returns Piotroski model (not None)
    Assert F3=False, F5=False, F7=False, F8=False, F9=False (all delta-checks False)
    Assert F1/F2/F4 are computed normally

test_stock_deep_dive_includes_gold_rs
    Mock get_stock_detail, compute_gold_rs, compute_piotroski
    Call GET /api/v1/stocks/RELIANCE
    Assert response.stock.gold_rs is not None
    Assert response.stock.gold_rs.signal is one of the 4 enum values

test_stock_deep_dive_includes_piotroski
    Same as above
    Assert response.stock.piotroski is not None
    Assert response.stock.piotroski.score is an int between 0 and 9
```

The route-level tests (`test_stock_deep_dive_includes_*`) belong in `tests/routes/test_stock_derived_signals.py` and use httpx `AsyncClient` with `ASGITransport` and `app.dependency_overrides[get_db]`. They mock both the JIPDataService and the derived_signals service functions.

**Total: 18 tests minimum across both test files.**
