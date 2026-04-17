# C-DER-1: Stock Signal Engine — Gold RS + Piotroski + Enriched Deep Dive

**Slice:** V6.5 — Derived Signal Engine
**Depends on:** V6-5 (stocks/{symbol} route exists with conviction pillars), V6T-5 (baseline hardening + validate-v6 green)
**Blocks:** C-DER-2 (four-factor conviction reads gold_rs signal as supporting context)
**Complexity:** M (5–7 hours)
**Quality targets:** code: 82, security: 90, architecture: 85, api: 90

---

## ⛔ NON-NEGOTIABLE — READ FIRST

This chunk is **REJECTED** if the DONE commit does not contain **all** of these
files at or above the stated size floor. A bare `.forge/baseline/*` bump, a
`.quality/` touch, or any commit that does not materially land the
deliverables below is a false-DONE and will be flipped back to PENDING on
audit.

```
PRESENT, net-new:
  backend/services/derived_signals.py            ≥ 230 lines
  tests/services/test_derived_signals.py         ≥ 340 lines, ≥ 22 tests
  tests/routes/test_stock_derived_signals.py     ≥ 60 lines,  ≥ 2 tests

MODIFIED, additive only (do not remove existing fields):
  backend/models/schemas.py                      ≥ 40 lines added
                                                 (GoldRSSignal + GoldRS
                                                 + PiotroskiDetail + Piotroski
                                                 + 2 new fields on StockDeepDive)
  backend/routes/stocks.py                       ≥ 15 lines added
                                                 (asyncio.gather block +
                                                 2 constructor kwargs)
```

**Self-check loop (run before declaring DONE):**

```bash
for f in backend/services/derived_signals.py \
         tests/services/test_derived_signals.py \
         tests/routes/test_stock_derived_signals.py; do
  test -f "$f" || { echo "MISSING: $f"; exit 1; }
  wc -l "$f"
done
grep -c "^class GoldRS\|^class Piotroski\|^class GoldRSSignal\|^class PiotroskiDetail" \
     backend/models/schemas.py
grep -n "asyncio.gather\|compute_gold_rs\|compute_piotroski" backend/routes/stocks.py
pytest tests/services/test_derived_signals.py tests/routes/test_stock_derived_signals.py -v
```

If any line above fails, **DO NOT** stamp DONE. Continue implementing until
every line passes. This block exists because V6T-5 shipped a false-DONE at
commit `6edea85` with only baseline bumps; the hardening is intentional and
mandatory.

---

## Goal

Add two query-time derived signals to the existing `GET /api/v1/stocks/{symbol}` deep-dive response:

1. **Gold RS** — measures whether the stock outperforms or underperforms gold (GLD ETF) over 63 trading days. Produces an enum signal: AMPLIFIES_BULL / NEUTRAL / FRAGILE / AMPLIFIES_BEAR.
2. **Piotroski F-Score** — 9-point fundamentals quality score computed from `de_equity_fundamentals` (point-in-time) and `de_equity_fundamentals_history` (annual deltas). Grades: WEAK / NEUTRAL / GOOD / STRONG.

Both signals are pure query-time derivations — no new `atlas_*` table is
created. They are attached to the existing `StockDeepDive` model as Optional
fields so the response is fully backward-compatible.

---

## Schema reality (verified against live RDS, 2026-04-17)

`de_equity_fundamentals_history` columns (annual & quarterly rows):
```
instrument_id, fiscal_period_end, period_type,
revenue_cr, expenses_cr, operating_profit_cr, opm_pct, net_profit_cr,
equity_capital_cr, reserves_cr, borrowings_cr, total_assets_cr,
cfo_cr, cfi_cr, cff_cr
```

**Critical:** history has `equity_capital_cr` (share capital only) AND
`reserves_cr` (retained earnings). **Total equity = equity_capital_cr +
reserves_cr.** The point-in-time table `de_equity_fundamentals` has
`debt_to_equity` (pre-computed) and `roe_pct` (pre-computed). History does
**not** have `debt_to_equity`, `roe_pct`, `current_assets_cr`,
`current_liabilities_cr`, `fixed_assets_cr`, or `cwip_cr`.

`de_global_price_daily` with `ticker='GLD'` has 2,584 rows from 2016-01-04
through 2026-04-14 — data is present and fresh enough for the 63-day window.

`de_equity_technical_daily` has `close_adj` column. Use this, not `close`.

These facts drive the F3/F5/F6 formulas below. Do **not** use
`net_profit_cr / equity_capital_cr` alone — that computes return on share
capital (an Indian accounting artefact, typically >100%), not ROE.

---

## Files

### New
- `backend/services/derived_signals.py` — `compute_gold_rs()` and `compute_piotroski()` service functions
- `tests/services/test_derived_signals.py` — unit tests for both service functions (22 minimum)
- `tests/routes/test_stock_derived_signals.py` — route-level integration tests (2 minimum) asserting the deep-dive response carries the new fields

### Modified
- `backend/models/schemas.py` — add `GoldRSSignal` enum, `GoldRS` model, `PiotroskiDetail` model, `Piotroski` model; add `gold_rs` and `piotroski` Optional fields to `StockDeepDive`
- `backend/routes/stocks.py` — call both signals concurrently via `asyncio.gather` inside `get_stock_deep_dive`; pass results into the `StockDeepDive` constructor

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
    ratio_3m: Optional[Decimal] = None        # (1 + stock_return_3m) / (1 + gold_return_3m)
    stock_return_3m: Optional[Decimal] = None # (close_today - close_63d) / close_63d
    gold_return_3m: Optional[Decimal] = None  # (gld_today  - gld_63d)  / gld_63d
    as_of: Optional[date] = None              # date of the latest close used


class PiotroskiDetail(BaseModel):
    # Profitability (4 checks)
    f1_net_profit_positive: bool = False      # latest.net_profit_cr > 0
    f2_cfo_positive: bool = False             # latest.cfo_cr > 0
    f3_roe_improving: bool = False            # current roe_pct > prior-year computed ROE
    f4_quality_earnings: bool = False         # latest.cfo_cr > latest.net_profit_cr
    # Leverage / Liquidity (3 checks)
    f5_leverage_falling: bool = False         # current D/E < prior-year computed D/E
    f6_liquidity_improving: bool = False      # latest cfo/borrowings > prior cfo/borrowings (see note)
    f7_no_dilution: bool = False              # latest.equity_capital_cr <= prior.equity_capital_cr
    # Operating Efficiency (2 checks)
    f8_margin_expanding: bool = False         # latest.opm_pct > prior.opm_pct
    f9_asset_turnover_improving: bool = False # (revenue / total_assets) latest > prior


class Piotroski(BaseModel):
    score: int                                # 0–9 count of True checks
    grade: str                                # "WEAK" / "NEUTRAL" / "GOOD" / "STRONG"
    detail: PiotroskiDetail
    as_of: Optional[date] = None              # fiscal_period_end of latest annual used
```

### Modified `StockDeepDive` (add two Optional fields after `mf_holder_count`)

```python
gold_rs: Optional[GoldRS] = None
piotroski: Optional[Piotroski] = None
```

Additive only. Must not break any existing client consumer — the existing
response keys remain a subset of the new response keys.

---

## Implementation notes

### `backend/services/derived_signals.py`

#### `async def compute_gold_rs(instrument_id: UUID, db: AsyncSession, period_days: int = 63) -> Optional[GoldRS]`

Returns `None` (does not raise) when stock data is missing. When **only**
GLD data is missing, returns a `GoldRS(signal=NEUTRAL, ratio_3m=None, ...)`
sentinel so the response field is populated and the UI can render an
"unknown" badge rather than a broken field. Logs a structured warning with
`structlog` in either case.

**SQL to get stock close prices (use `close_adj`):**
```sql
SELECT close_adj, date
FROM de_equity_technical_daily
WHERE instrument_id = :instrument_id
  AND date >= (SELECT MAX(date) FROM de_equity_technical_daily
               WHERE instrument_id = :instrument_id) - INTERVAL '95 days'
ORDER BY date DESC
LIMIT 80
```
- `close_today`, `date_today` = row[0]
- `close_63d` = row at Python index `min(period_days, len(rows) - 1)` (so
  if we have ~65 rows we pick row[63], if we have only 40 rows we pick the
  oldest available row and mark it best-effort).
- If fewer than 30 rows exist, return `None`.

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
- Same indexing.
- If GLD has fewer than 30 rows, return
  `GoldRS(signal=GoldRSSignal.NEUTRAL, ratio_3m=None, stock_return_3m=None, gold_return_3m=None, as_of=date_today)`.

**Formulas (all Decimal arithmetic, never float):**
```python
stock_return = (Decimal(str(close_today)) - Decimal(str(close_63d))) / Decimal(str(close_63d))
gold_return  = (Decimal(str(gld_today))   - Decimal(str(gld_63d)))   / Decimal(str(gld_63d))
denominator  = Decimal("1") + gold_return
if denominator == Decimal("0"):
    return None  # gold fell to zero; refuse to divide by zero
ratio = (Decimal("1") + stock_return) / denominator
```

**Signal thresholds (locked):**
- `ratio > Decimal("1.05")`  → `AMPLIFIES_BULL`
- `ratio >= Decimal("0.95")` → `NEUTRAL`
- `ratio >= Decimal("0.85")` → `FRAGILE`
- `ratio < Decimal("0.85")`  → `AMPLIFIES_BEAR`

Quantize `ratio_3m`, `stock_return_3m`, `gold_return_3m` to 4 decimal places
before returning.

#### `async def compute_piotroski(instrument_id: UUID, db: AsyncSession) -> Optional[Piotroski]`

Returns `None` when zero annual history rows exist. Logs a warning.

**SQL to fetch fundamentals history (annual rows only, DESC):**
```sql
SELECT
    fiscal_period_end,
    net_profit_cr,
    cfo_cr,
    opm_pct,
    revenue_cr,
    total_assets_cr,
    borrowings_cr,
    equity_capital_cr,
    reserves_cr
FROM de_equity_fundamentals_history
WHERE instrument_id = :instrument_id
  AND period_type = 'annual'
ORDER BY fiscal_period_end DESC
LIMIT 3
```
`row[0]` = latest annual, `row[1]` = prior year.

**SQL to fetch point-in-time fundamentals:**
```sql
SELECT roe_pct, debt_to_equity
FROM de_equity_fundamentals
WHERE instrument_id = :instrument_id
LIMIT 1
```

If zero history rows → `return None`.
If exactly one history row → F3, F5, F7, F8, F9 all False (need prior year);
F1, F2, F4 computed normally; build and return `Piotroski` with partial score.

**Check-by-check logic (Decimal throughout; treat missing values as False):**

Helper for "total equity" (fixes F3 and F5):
```python
def _total_equity(row) -> Optional[Decimal]:
    if row.equity_capital_cr is None or row.reserves_cr is None:
        return None
    total = Decimal(str(row.equity_capital_cr)) + Decimal(str(row.reserves_cr))
    return total if total != Decimal("0") else None
```

- **F1** `f1_net_profit_positive`:
  `latest.net_profit_cr is not None and Decimal(str(latest.net_profit_cr)) > Decimal("0")`
- **F2** `f2_cfo_positive`:
  `latest.cfo_cr is not None and Decimal(str(latest.cfo_cr)) > Decimal("0")`
- **F3** `f3_roe_improving`:
  - `current_roe` = `Decimal(str(fundamentals.roe_pct))` if not None else None.
  - `prior_total_equity = _total_equity(row[1])`.
  - `prior_roe = Decimal(str(row[1].net_profit_cr)) / prior_total_equity * Decimal("100")`
    if `row[1].net_profit_cr is not None and prior_total_equity is not None`.
  - `F3 = current_roe is not None and prior_roe is not None and current_roe > prior_roe`.
  - **Do NOT use `net_profit / equity_capital` (share capital only) — that computes return-on-share-capital which is an Indian accounting artefact, typically >100%, and would cause F3 to be trivially False for healthy companies.**
- **F4** `f4_quality_earnings`:
  `latest.cfo_cr and latest.net_profit_cr and Decimal(str(latest.cfo_cr)) > Decimal(str(latest.net_profit_cr))`
- **F5** `f5_leverage_falling`:
  - `current_de` = `Decimal(str(fundamentals.debt_to_equity))` if not None else None.
  - `prior_total_equity = _total_equity(row[1])`.
  - `prior_de = Decimal(str(row[1].borrowings_cr)) / prior_total_equity` if non-None.
  - `F5 = current_de is not None and prior_de is not None and current_de < prior_de`.
  - **Both sides are now true D/E ratios — no unit mismatch with the
    previous draft, which divided a dimensionless D/E by a lakh/crore
    ratio and was always False.**
- **F6** `f6_liquidity_improving`:
  - Indian history schema does not expose `current_assets_cr` or
    `current_liabilities_cr`. Use **cash-flow coverage of debt** as the
    honest proxy: `cfo_cr / borrowings_cr`.
  - `curr_ratio = Decimal(str(latest.cfo_cr)) / Decimal(str(latest.borrowings_cr))`
    if both non-None and `borrowings_cr != 0`.
  - Same for `prior_ratio`.
  - `F6 = curr_ratio is not None and prior_ratio is not None and curr_ratio > prior_ratio`.
  - If either `borrowings_cr == 0` → F6 False (debt-free companies trivially
    pass; we conservatively mark the delta check as False rather than True
    so F6 only rewards improvement in debt-bearing names).
- **F7** `f7_no_dilution`:
  `latest.equity_capital_cr and prior.equity_capital_cr and Decimal(str(latest.equity_capital_cr)) <= Decimal(str(prior.equity_capital_cr))`
- **F8** `f8_margin_expanding`:
  `latest.opm_pct and prior.opm_pct and Decimal(str(latest.opm_pct)) > Decimal(str(prior.opm_pct))`
- **F9** `f9_asset_turnover_improving`:
  `curr = revenue / total_assets` (latest), `prior = revenue / total_assets` (prior).
  Guard `total_assets_cr != 0`. `F9 = curr > prior`.

**Grade thresholds:**
- 0–2 → `"WEAK"`
- 3–5 → `"NEUTRAL"`
- 6–7 → `"GOOD"`
- 8–9 → `"STRONG"`

`as_of = latest.fiscal_period_end`.

### Wiring into `backend/routes/stocks.py`

Inside `get_stock_deep_dive`, after the existing `stock_detail` fetch and
before constructing `StockDeepDive(...)`:

```python
import asyncio
from backend.services.derived_signals import compute_gold_rs, compute_piotroski
from backend.db.session import async_session_factory

async def _gold_rs_task() -> Optional[GoldRS]:
    async with async_session_factory() as s:
        return await compute_gold_rs(stock_detail["id"], s)

async def _piotroski_task() -> Optional[Piotroski]:
    async with async_session_factory() as s:
        return await compute_piotroski(stock_detail["id"], s)

gold_rs_result, piotroski_result = await asyncio.gather(
    _gold_rs_task(), _piotroski_task(), return_exceptions=True
)
gold_rs_val = gold_rs_result if isinstance(gold_rs_result, GoldRS) else None
piotroski_val = piotroski_result if isinstance(piotroski_result, Piotroski) else None
```

Then pass `gold_rs=gold_rs_val, piotroski=piotroski_val` into
`StockDeepDive(...)`. Keep the existing TV TA gather block separate.

### Session isolation

asyncpg cannot multiplex queries on one `AsyncSession`. Each concurrent DB
call in `asyncio.gather` must use its own session from
`async_session_factory`. See wiki
`isolated-session-parallel-gather.md`.

### Edge cases

| Scenario | Behaviour |
|---|---|
| GLD has fewer than 30 rows | `GoldRS(signal=NEUTRAL, ratio_3m=None, ...)` sentinel |
| Stock has no close data | `None` |
| `gold_return == -1` | `None` (division guard) |
| Zero annual history | `None` |
| Exactly 1 annual row | Return `Piotroski` with F3/F5/F7/F8/F9 = False, score reflects only F1/F2/F4 |
| `net_profit_cr` NULL, etc. | That check is False, others unaffected |
| `borrowings_cr == 0` | F5, F6 both False for that period |
| `total_assets_cr == 0` | F9 False |
| `equity_capital_cr + reserves_cr == 0` | F3, F5 False (total equity undefined) |

---

## Points of success (13, all required for DONE)

1. `backend/services/derived_signals.py` exists, ≥230 lines, exports `compute_gold_rs` and `compute_piotroski`.
2. `backend/models/schemas.py` exposes `GoldRSSignal`, `GoldRS`, `PiotroskiDetail`, `Piotroski` and adds `gold_rs` + `piotroski` Optional fields to `StockDeepDive`.
3. `backend/routes/stocks.py` calls `compute_gold_rs` and `compute_piotroski` via `asyncio.gather` with isolated sessions and passes both into the `StockDeepDive` constructor.
4. `GET /api/v1/stocks/RELIANCE` response contains `stock.gold_rs` with `signal`, `ratio_3m`, `stock_return_3m`, `gold_return_3m`, `as_of`.
5. `GET /api/v1/stocks/RELIANCE` response contains `stock.piotroski` with `score` (int 0–9), `grade` ∈ {WEAK, NEUTRAL, GOOD, STRONG}, `detail` (9 bool fields), `as_of`.
6. **Semantic sentinel (F3):** with mocked `prior.net_profit_cr = Decimal("100")`, `prior.equity_capital_cr = Decimal("10")`, `prior.reserves_cr = Decimal("390")`, the computed `prior_roe` equals `Decimal("25")` (not `1000`). A failing test on this line blocks DONE.
7. **Semantic sentinel (F5):** with mocked `current debt_to_equity = Decimal("0.5")`, `prior borrowings_cr = 200`, `prior equity_capital_cr = 10`, `prior reserves_cr = 390`, `F5` is True (prior D/E = 200/400 = 0.5, current 0.5 is not < 0.5 → actually False; flip by using `current = Decimal("0.4")` → True). Regression test covering both directions.
8. **Semantic sentinel (F6):** with mocked `latest cfo_cr = 120, borrowings_cr = 100` and `prior cfo_cr = 80, borrowings_cr = 100`, F6 = True. With `borrowings_cr = 0` in either period, F6 = False.
9. Missing GLD data → `gold_rs.signal == "NEUTRAL"` and Decimal fields are None (sentinel, not crash).
10. Missing stock technical data → `gold_rs` is `None`.
11. Zero annual history rows → `piotroski` is `None`. One annual row → `Piotroski` returned with only F1/F2/F4 possibly True.
12. Neither service function raises; both return `Optional[model]`. `asyncio.gather(..., return_exceptions=True)` is used so one failure does not poison the other.
13. Quality gate passes: `ruff check . --select E,F,W` clean on all new/modified files; `mypy backend/services/derived_signals.py --ignore-missing-imports` clean; `pytest tests/services/test_derived_signals.py tests/routes/test_stock_derived_signals.py -v` shows ≥22 + ≥2 tests passing; full `pytest tests/ -v --tb=short` does not regress (≥ prior passing count).

---

## Tests

### File: `tests/services/test_derived_signals.py` (≥22 tests, ≥340 lines)

All tests use `AsyncMock` for the DB session. Do NOT hit a real database.
Use the pattern `session.execute = AsyncMock(return_value=Mock(...))` or
patch on `AsyncSession.execute`.

**Gold RS tests:**

1. `test_gold_rs_amplifies_bull_when_stock_beats_gold_by_5pct` — stock=+0.20, gold=+0.10 → ratio ≈1.091 → `AMPLIFIES_BULL`.
2. `test_gold_rs_neutral_within_band` — stock=+0.10, gold=+0.10 → ratio=1.00 → `NEUTRAL`.
3. `test_gold_rs_fragile_below_band` — stock=+0.05, gold=+0.15 → ratio ≈0.913 → `FRAGILE`.
4. `test_gold_rs_amplifies_bear_severely_underperforms` — stock=-0.20, gold=+0.10 → ratio ≈0.727 → `AMPLIFIES_BEAR`.
5. `test_gold_rs_handles_missing_gld_data_returns_neutral_sentinel` — GLD=5 rows → returns `GoldRS(signal=NEUTRAL, ratio_3m=None, ...)`, **not** None.
6. `test_gold_rs_handles_missing_stock_data_returns_none` — stock=0 rows → `None`.
7. `test_gold_rs_ratio_uses_3m_period_default` — verify default `period_days=63` and 95-day window in SQL params.
8. `test_gold_rs_uses_close_adj_not_close` — grep the SQL produced for `close_adj`. Regression guard.
9. `test_gold_rs_division_guard_gold_return_minus_one` — mock `gld_today=0, gld_63d=100` → denominator 0 → `None`.

**Piotroski tests:**

10. `test_piotroski_perfect_score_returns_9_strong` — all 9 checks pass → `score==9, grade=="STRONG"`.
11. `test_piotroski_zero_score_returns_0_weak` — all checks fail → `score==0, grade=="WEAK"`.
12. `test_piotroski_handles_missing_history_returns_none` — 0 annual rows → `None`.
13. `test_piotroski_single_annual_row_partial_score` — 1 annual row → `Piotroski` returned; F3/F5/F7/F8/F9 all False.
14. `test_piotroski_f3_uses_total_equity_not_share_capital_only` — **semantic sentinel.** Mock `prior.net_profit_cr=100, equity_capital_cr=10, reserves_cr=390`. Assert computed `prior_roe == Decimal("25")` (not 1000). Also assert `f3_roe_improving` is True when `fundamentals.roe_pct=30` and False when `fundamentals.roe_pct=20`.
15. `test_piotroski_f4_quality_earnings_cfo_gt_profit` — cfo=100, profit=80 → True; cfo=50, profit=80 → False.
16. `test_piotroski_f5_uses_total_equity_denominator` — **semantic sentinel.** Mock `prior borrowings_cr=200, equity_capital_cr=10, reserves_cr=390` → prior D/E = 0.5. With `fundamentals.debt_to_equity=0.4` → True; with `0.6` → False. Verifies the unit-matched D/E comparison.
17. `test_piotroski_f6_uses_cfo_to_borrowings_proxy` — **semantic sentinel.** latest cfo=120, borrowings=100 / prior cfo=80, borrowings=100 → F6=True. With `borrowings_cr=0` in either period → F6=False.
18. `test_piotroski_f7_no_dilution_check` — current 100 / prior 110 → True; current 110 / prior 100 → False.
19. `test_piotroski_f8_margin_expanding` — current opm=15 / prior 12 → True; current 10 / prior 12 → False.
20. `test_piotroski_f9_asset_turnover_improving` — current rev=1000/assets=500 / prior rev=800/assets=500 → True; prior rev=1200 → False.
21. `test_piotroski_grade_thresholds_all_four_bands` — force scores 0,2,3,5,6,7,8,9 → grades match WEAK/WEAK/NEUTRAL/NEUTRAL/GOOD/GOOD/STRONG/STRONG.
22. `test_piotroski_sql_uses_period_type_annual` — verify bound param `period_type == 'annual'`.

### File: `tests/routes/test_stock_derived_signals.py` (≥2 tests, ≥60 lines)

Use `httpx.AsyncClient(transport=ASGITransport(app=app))` and
`app.dependency_overrides[get_db] = ...`. Patch `compute_gold_rs` and
`compute_piotroski` to return known fixtures.

1. `test_stock_deep_dive_includes_gold_rs_and_piotroski` — GET /api/v1/stocks/RELIANCE → `response.stock.gold_rs.signal in GoldRSSignal values`, `response.stock.piotroski.score` ∈ [0,9], `grade` ∈ allowed set. **Non-regression:** assert that every key present in the pre-C-DER-1 `StockDeepDive` response (fetch snapshot from a fixture) is still present.
2. `test_stock_deep_dive_survives_signal_failure` — mock `compute_gold_rs` to raise; assert response still 200, `stock.gold_rs is None`, `stock.piotroski` still populated. Proves `asyncio.gather(..., return_exceptions=True)` correctly isolates failures.

---

## Live smoke (required at DONE)

After the chunk ships and `atlas-backend.service` restarts, run:

```bash
for sym in RELIANCE TCS HDFCBANK; do
  curl -s https://atlas.jslwealth.in/api/v1/stocks/$sym \
    | jq '{sym: .stock.symbol,
           gold: .stock.gold_rs.signal,
           gold_ratio: .stock.gold_rs.ratio_3m,
           piotroski: .stock.piotroski.score,
           grade: .stock.piotroski.grade}'
done
```

Expected:
- Each symbol returns JSON with `gold` ∈ {AMPLIFIES_BULL, NEUTRAL, FRAGILE, AMPLIFIES_BEAR} or null.
- Each returns `piotroski` between 0 and 9 (or null if no history).
- No 5xx. No stack trace.

Capture the output in the chunk's `.forge/last-run.json` or paste into
`docs/decisions/session-log.md` under the C-DER-1 entry.

---

## Post-chunk sync invariant

On DONE, `scripts/post-chunk.sh C-DER-1` MUST run and must green:
(1) git commit + push, (2) atlas-backend.service restart, (3) smoke probe,
(4) /forge-compile wiki update, (5) MEMORY.md + project_v15_chunk_status.md
append with commit hash and gate score.

If any of the 5 fails, the chunk is not DONE. Flip state.db back to PENDING
and escalate.
