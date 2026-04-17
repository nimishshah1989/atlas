# C-DER-2: 4-Factor Conviction Engine + Action + Urgency + Screener

**Slice:** V6.5 — Derived Signal Engine
**Depends on:** C-DER-1 (GoldRS/Piotroski wired), V6-5 (stocks/{symbol} deep-dive route)
**Blocks:** C-DER-3 (sentiment uses regime string produced by breadth route; screener is prerequisite for pulse-stocks page)
**Complexity:** L (7–9 hours)
**Quality targets:** code: 82, security: 90, architecture: 85, api: 90

---

## Goal

Compute the 4-factor conviction model (Returns RS × Momentum RS × Sector RS × Volume RS), derive `ActionSignal` and `UrgencyLevel` from conviction + regime context, attach them to the existing deep-dive response, and expose a new paginated `GET /api/v1/screener` endpoint.

The screener must perform percentile-rank computation entirely in SQL using a window function — never load all rows into Python and sort. The conviction engine must be a pure computation module with no HTTP dependencies.

---

## Files

### New
- `backend/services/conviction_engine.py` — `compute_four_factor()`, `compute_screener_bulk()`
- `backend/routes/screener.py` — `GET /api/v1/screener` route
- `tests/services/test_conviction_engine.py` — unit tests for conviction + screener (20 minimum)
- `tests/routes/test_screener_route.py` — route-level tests for screener endpoint

### Modified
- `backend/models/schemas.py` — add `ConvictionLevel`, `ActionSignal`, `UrgencyLevel`, `FourFactorConviction`, `ScreenerRow`, `ScreenerResponse` models; add `four_factor: Optional[FourFactorConviction] = None` field to `StockDeepDive`
- `backend/routes/stocks.py` — call `compute_four_factor()` in `get_stock_deep_dive`, inject into `StockDeepDive`
- `backend/main.py` — register `screener.router`

---

## Contracts

### New Pydantic models (add to `backend/models/schemas.py`)

```python
class ConvictionLevel(str, Enum):
    HIGH_PLUS = "HIGH+"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    AVOID = "AVOID"


class ActionSignal(str, Enum):
    BUY = "BUY"
    ACCUMULATE = "ACCUMULATE"
    WATCH = "WATCH"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class UrgencyLevel(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    DEVELOPING = "DEVELOPING"
    PATIENT = "PATIENT"


class FourFactorConviction(BaseModel):
    conviction_level: ConvictionLevel
    action_signal: ActionSignal
    urgency: UrgencyLevel
    # Individual factor results
    factor_returns_rs: bool = False     # rs_composite > 100
    factor_momentum_rs: bool = False    # roc_21 percent_rank > 0.6
    factor_sector_rs: bool = False      # sector rs_composite (entity_type='sector') > 100
    factor_volume_rs: bool = False      # cmf_20 > 0 AND mfi_14 > 50
    factors_aligned: int = 0            # count of True factors (0–4)
    # Supporting values (for display / audit trail)
    rs_composite: Optional[Decimal] = None
    roc_21_pct_rank: Optional[Decimal] = None   # 0.0–1.0
    sector_rs_composite: Optional[Decimal] = None
    cmf_20: Optional[Decimal] = None
    mfi_14: Optional[Decimal] = None
    regime: Optional[str] = None                # regime string passed in


class ScreenerRow(BaseModel):
    symbol: str
    company_name: str
    sector: Optional[str] = None
    rs_composite: Optional[Decimal] = None
    rsi_14: Optional[Decimal] = None
    above_50dma: Optional[bool] = None
    above_200dma: Optional[bool] = None
    macd_bullish: Optional[bool] = None
    market_cap_cr: Optional[Decimal] = None
    pe_ratio: Optional[Decimal] = None
    conviction_level: Optional[ConvictionLevel] = None
    action_signal: Optional[ActionSignal] = None
    urgency: Optional[UrgencyLevel] = None
    nifty_50: bool = False
    nifty_500: bool = False


class ScreenerResponse(BaseModel):
    rows: list[ScreenerRow]
    meta: ResponseMeta
```

### Add to `StockDeepDive` (after `piotroski` field from C-DER-1)

```python
four_factor: Optional[FourFactorConviction] = None
```

---

## Implementation notes

### `backend/services/conviction_engine.py`

#### `async def compute_four_factor(instrument_id: UUID, sector: Optional[str], db: AsyncSession, regime: Optional[str] = None) -> Optional[FourFactorConviction]`

Returns `None` when the instrument has no technical data. Uses a single SQL query.

**SQL (all in one CTE query — do NOT make 4 separate queries):**

```sql
WITH target_tech AS (
    SELECT
        t.roc_21,
        t.cmf_20,
        t.mfi_14,
        t.roc_5
    FROM de_equity_technical_daily t
    WHERE t.instrument_id = :instrument_id
      AND t.date = (SELECT MAX(date) FROM de_equity_technical_daily)
    LIMIT 1
),
target_rs AS (
    SELECT rs_composite
    FROM de_rs_scores
    WHERE entity_type = 'equity'
      AND vs_benchmark = 'NIFTY 500'
      AND entity_id = :instrument_id_str
      AND date = (SELECT MAX(date) FROM de_rs_scores
                  WHERE entity_type = 'equity' AND vs_benchmark = 'NIFTY 500')
    LIMIT 1
),
sector_rs AS (
    SELECT rs_composite AS sector_rs_composite
    FROM de_rs_scores
    WHERE entity_type = 'sector'
      AND entity_id = :sector
      AND date = (SELECT MAX(date) FROM de_rs_scores
                  WHERE entity_type = 'sector')
    LIMIT 1
),
roc_pct_rank AS (
    SELECT
        percent_rank() OVER (ORDER BY roc_21 ASC NULLS FIRST) AS pct_rank
    FROM de_equity_technical_daily
    WHERE date = (SELECT MAX(date) FROM de_equity_technical_daily)
      AND instrument_id = :instrument_id
    LIMIT 1
)
SELECT
    tt.roc_21,
    tt.cmf_20,
    tt.mfi_14,
    tt.roc_5,
    tr.rs_composite,
    sr.sector_rs_composite,
    rp.pct_rank AS roc_21_pct_rank
FROM target_tech tt
LEFT JOIN target_rs tr ON true
LEFT JOIN sector_rs sr ON true
LEFT JOIN roc_pct_rank rp ON true
```

**IMPORTANT SQL caveat — nested window functions:** PostgreSQL does not allow window functions nested inside aggregate functions or other window functions. The `percent_rank()` must be computed in a subquery/CTE first, then joined. The `roc_pct_rank` CTE computes `percent_rank() OVER (ORDER BY roc_21)` across ALL stocks at the latest date, but only returns the row for `instrument_id`. This is correct — the window evaluates over all rows in the partition before the WHERE-equivalent filter returns only target row.

**Correct CTE for roc_21 percentile rank:**
```sql
roc_pct_rank AS (
    SELECT pct_rank
    FROM (
        SELECT
            instrument_id,
            percent_rank() OVER (ORDER BY roc_21 ASC NULLS FIRST) AS pct_rank
        FROM de_equity_technical_daily
        WHERE date = (SELECT MAX(date) FROM de_equity_technical_daily)
    ) ranked
    WHERE instrument_id = :instrument_id
    LIMIT 1
)
```

**Factor evaluation (pure Python from SQL row results):**

All values converted to `Decimal(str(x))` before comparison. `None` values → factor = `False`.

```python
factor_returns_rs = rs_composite is not None and rs_composite > Decimal("100")
factor_momentum_rs = roc_21_pct_rank is not None and roc_21_pct_rank > Decimal("0.6")
factor_sector_rs = sector_rs_composite is not None and sector_rs_composite > Decimal("100")
factor_volume_rs = (
    cmf_20 is not None and mfi_14 is not None
    and cmf_20 > Decimal("0")
    and mfi_14 > Decimal("50")
)
factors_aligned = sum([factor_returns_rs, factor_momentum_rs, factor_sector_rs, factor_volume_rs])
```

**ConvictionLevel from `factors_aligned`:**
- 4 → HIGH_PLUS
- 3 → HIGH
- 2 → MEDIUM
- 1 → LOW
- 0 → AVOID

**ActionSignal derivation:**

`regime` parameter is a string (e.g. "BULL", "BEAR", "SIDEWAYS", "RECOVERY"). Compare with `.upper()` to be case-insensitive.

```python
bull_regime = regime is not None and regime.upper() in ("BULL", "RECOVERY")

if conviction in (ConvictionLevel.HIGH_PLUS, ConvictionLevel.HIGH) and bull_regime:
    action = ActionSignal.BUY
elif conviction in (ConvictionLevel.HIGH_PLUS, ConvictionLevel.HIGH) and not bull_regime:
    action = ActionSignal.ACCUMULATE
elif conviction == ConvictionLevel.MEDIUM:
    action = ActionSignal.WATCH
elif conviction == ConvictionLevel.LOW and rs_composite is not None and rs_composite < Decimal("100"):
    action = ActionSignal.REDUCE
else:  # AVOID or rs_composite missing
    action = ActionSignal.EXIT
```

**UrgencyLevel derivation (proxy for V7 — no atlas_decisions tracking yet):**

```python
roc_5_val = Decimal(str(roc_5)) if roc_5 is not None else None

if (conviction == ConvictionLevel.HIGH_PLUS
        and roc_5_val is not None
        and roc_5_val > Decimal("3")):
    urgency = UrgencyLevel.IMMEDIATE
elif (conviction in (ConvictionLevel.HIGH_PLUS, ConvictionLevel.HIGH)
        and roc_21 is not None
        and Decimal(str(roc_21)) > Decimal("0")):
    urgency = UrgencyLevel.DEVELOPING
else:
    urgency = UrgencyLevel.PATIENT
```

Note: `roc_5` is already in `de_equity_technical_daily` — include it in the SQL query above.

**Sector RS when sector is None:**

When `sector` parameter is `None`, skip the sector_rs CTE (pass `NULL` for `:sector`), `sector_rs_composite` = `None`, `factor_sector_rs` = `False`. Do not return `None` for the whole function.

#### `async def compute_screener_bulk(filters: dict[str, Any], db: AsyncSession) -> list[dict[str, Any]]`

Returns a list of dicts (one per screener row). All conviction/action/urgency fields are computed in Python after a single bulk SQL fetch. The SQL computes roc_21 percentile rank in-database.

**Screener SQL:**
```sql
WITH latest_tech_date AS (
    SELECT MAX(date) AS d FROM de_equity_technical_daily
),
latest_rs_date AS (
    SELECT MAX(date) AS d FROM de_rs_scores
    WHERE entity_type = 'equity' AND vs_benchmark = 'NIFTY 500'
),
sector_rs_latest AS (
    SELECT entity_id AS sector_name, rs_composite AS sector_rs
    FROM de_rs_scores
    WHERE entity_type = 'sector'
      AND date = (SELECT MAX(date) FROM de_rs_scores WHERE entity_type = 'sector')
),
ranked_tech AS (
    SELECT
        instrument_id,
        roc_21,
        cmf_20,
        mfi_14,
        rsi_14,
        above_50dma,
        above_200dma,
        macd_bullish,
        roc_5,
        percent_rank() OVER (ORDER BY roc_21 ASC NULLS FIRST) AS roc_21_pct_rank
    FROM de_equity_technical_daily
    WHERE date = (SELECT d FROM latest_tech_date)
),
latest_rs AS (
    SELECT entity_id::uuid AS instrument_id, rs_composite
    FROM de_rs_scores
    WHERE entity_type = 'equity'
      AND vs_benchmark = 'NIFTY 500'
      AND date = (SELECT d FROM latest_rs_date)
)
SELECT
    i.current_symbol AS symbol,
    i.company_name,
    i.sector,
    i.nifty_50,
    i.nifty_500,
    t.rsi_14,
    t.above_50dma,
    t.above_200dma,
    t.macd_bullish,
    t.cmf_20,
    t.mfi_14,
    t.roc_21,
    t.roc_5,
    t.roc_21_pct_rank,
    r.rs_composite,
    sr.sector_rs,
    f.market_cap_cr,
    f.pe_ratio
FROM de_instrument i
LEFT JOIN ranked_tech t ON t.instrument_id = i.id
LEFT JOIN latest_rs r ON r.instrument_id = i.id
LEFT JOIN sector_rs_latest sr ON sr.sector_name = i.sector
LEFT JOIN de_equity_fundamentals f ON f.instrument_id = i.id
WHERE i.is_active = true
  {universe_filter}
  {sector_filter}
ORDER BY r.rs_composite DESC NULLS LAST
LIMIT :limit OFFSET :offset
```

`universe_filter` is built conditionally:
- `universe="nifty50"` → `AND i.nifty_50 = true`
- `universe="nifty200"` → `AND i.nifty_200 = true`
- `universe="nifty500"` → `AND i.nifty_500 = true`
- `None` → no filter

`sector_filter` is built conditionally:
- `sector` is not None → `AND i.sector = :sector` (add `:sector` param)

**IMPORTANT:** Use `text()` with named parameters. Never use Python f-strings to interpolate filter values — use SQLAlchemy parameter binding for all user-supplied strings.

After fetching rows into Python, compute `conviction_level`, `action_signal`, `urgency` per row using the same factor logic as `compute_four_factor` (extract to a pure helper function `_compute_conviction_from_row(row: dict, regime: str) -> tuple[ConvictionLevel, ActionSignal, UrgencyLevel]`). Apply optional post-SQL filters:
- `conviction` filter → `if filters.get("conviction") and row_conviction.value != filters["conviction"]: skip`
- `action` filter → `if filters.get("action") and row_action.value != filters["action"]: skip`

These filters are applied in Python after SQL because the conviction/action values are computed in Python (not stored in DB). The SQL limit/offset applies BEFORE Python filtering, so the `ScreenerResponse.meta.total_count` will reflect the SQL count, not the post-filter count. Document this in a code comment.

### `backend/routes/screener.py`

```python
from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.services.conviction_engine import compute_screener_bulk
from backend.clients.jip_market_service import JIPMarketService
from backend.models.schemas import ScreenerResponse, ScreenerRow, ResponseMeta

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])


@router.get("", response_model=ScreenerResponse)
async def get_screener(
    universe: Optional[str] = Query(None, description="nifty50, nifty200, nifty500"),
    sector: Optional[str] = Query(None),
    conviction: Optional[str] = Query(None, description="HIGH+, HIGH, MEDIUM, LOW, AVOID"),
    action: Optional[str] = Query(None, description="BUY, ACCUMULATE, WATCH, REDUCE, EXIT"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ScreenerResponse:
```

Inside the route:
1. Fetch current regime string via `JIPMarketService(db).get_market_regime()` — extract `regime_data["regime"]` (string). Default to `"SIDEWAYS"` if None.
2. Build `filters` dict: `{"universe": universe, "sector": sector, "conviction": conviction, "action": action, "limit": limit, "offset": offset, "regime": regime_str}`.
3. Call `rows = await compute_screener_bulk(filters, db)`.
4. Build `ScreenerRow` objects from rows. All Decimal conversions via `Decimal(str(v))`.
5. Return `ScreenerResponse(rows=screener_rows, meta=ResponseMeta(record_count=len(screener_rows), offset=offset, limit=limit, query_ms=elapsed))`.

### Wiring `compute_four_factor` into deep-dive route

In `backend/routes/stocks.py`, inside `get_stock_deep_dive`, after fetching `stock_detail`:

```python
from backend.services.conviction_engine import compute_four_factor

# Regime needed for action signal — reuse market service
regime_svc = JIPMarketService(db)
regime_data = await regime_svc.get_market_regime()
regime_str = regime_data.get("regime") if regime_data else None

# Use own session per asyncio.gather call (asyncpg cannot multiplex)
async def _four_factor_task() -> Optional[FourFactorConviction]:
    async with async_session_factory() as s:
        return await compute_four_factor(
            instrument_id=stock_detail["id"],
            sector=stock_detail.get("sector"),
            db=s,
            regime=regime_str,
        )
```

Add `_four_factor_task` to the existing `asyncio.gather` that already runs `_gold_rs_task` and `_piotroski_task` (from C-DER-1). All three run concurrently. Extract result safely:

```python
four_factor_val = result if isinstance(result, FourFactorConviction) else None
```

Pass `four_factor=four_factor_val` into `StockDeepDive(...)`.

### Registration in `backend/main.py`

Add after `from backend.routes import ...`:
```python
from backend.routes import screener
```
Add after `app.include_router(stocks.router)`:
```python
app.include_router(screener.router)
```

### Edge cases

| Scenario | Behaviour |
|---|---|
| Sector is None (no sector data) | factor_sector_rs = False, sector_rs_composite = None |
| Stock has no technical row for today | Return None for compute_four_factor |
| roc_21 is NULL in DB | roc_21_pct_rank treated as None, factor_momentum_rs = False |
| Universe filter "nifty50" + sector filter combined | Both applied as SQL AND conditions |
| conviction filter "HIGH+" in query string | Value "HIGH+" matches ConvictionLevel.HIGH_PLUS.value |
| Regime is None (no regime data) | bull_regime = False → action falls to ACCUMULATE or lower |
| GLD data unavailable | gold_rs signal is still computed (NEUTRAL), four_factor is independent |

---

## Acceptance criteria

1. `GET /api/v1/stocks/RELIANCE` response contains `stock.four_factor` with `conviction_level`, `action_signal`, `urgency`, and all 4 `factor_*` booleans.
2. `GET /api/v1/screener` returns 200 with `rows` list and `meta`.
3. `GET /api/v1/screener?universe=nifty50` returns only nifty_50=true stocks.
4. `GET /api/v1/screener?sector=Banking` returns only Banking sector stocks.
5. `GET /api/v1/screener?conviction=HIGH%2B` filters correctly (URL-encodes "+").
6. `GET /api/v1/screener?limit=10&offset=0` respects pagination.
7. Percentile rank for roc_21 is computed in PostgreSQL via `percent_rank()` window function — verified by checking no `sorted()` or `rank` computation in Python in `compute_screener_bulk`.
8. All 4 factors are False → conviction_level == "AVOID", action_signal == "EXIT".
9. All 4 factors are True + regime BULL → conviction_level == "HIGH+", action_signal == "BUY".
10. `ruff check . --select E,F,W` passes on all new/modified files.
11. `pytest tests/services/test_conviction_engine.py tests/routes/test_screener_route.py -v` shows all 20+ tests passing.

---

## Tests

### `tests/services/test_conviction_engine.py`

All tests mock `AsyncSession.execute` to return controlled data. Use `MagicMock` + `AsyncMock` pattern from existing tests (see `tests/routes/test_stock_conviction.py` for patterns). Do NOT hit real DB.

```
test_four_factor_all_true_returns_high_plus
    rs_composite=105, roc_21_pct_rank=0.75, sector_rs=105, cmf_20=0.1, mfi_14=55
    Assert conviction_level == ConvictionLevel.HIGH_PLUS, factors_aligned == 4

test_four_factor_zero_returns_avoid
    rs_composite=90, roc_21_pct_rank=0.3, sector_rs=90, cmf_20=-0.1, mfi_14=40
    Assert conviction_level == ConvictionLevel.AVOID, factors_aligned == 0

test_four_factor_sector_rs_check_uses_sector_table
    Mock entity_type='sector' query to return sector_rs=110 → factor_sector_rs=True
    Mock entity_type='sector' query to return None → factor_sector_rs=False
    Assert both cases correctly

test_four_factor_volume_rs_requires_both_cmf_and_mfi
    cmf_20=0.1, mfi_14=45 → factor_volume_rs=False (mfi_14 not > 50)
    cmf_20=-0.1, mfi_14=55 → factor_volume_rs=False (cmf_20 not > 0)
    cmf_20=0.1, mfi_14=55 → factor_volume_rs=True

test_action_bull_regime_high_plus_returns_buy
    conviction=HIGH_PLUS, regime="BULL" → action=BUY

test_action_correction_high_returns_accumulate
    conviction=HIGH, regime="BEAR" → action=ACCUMULATE

test_action_medium_conviction_returns_watch
    conviction=MEDIUM, any regime → action=WATCH

test_action_low_falling_returns_reduce
    conviction=LOW, rs_composite=95 (< 100) → action=REDUCE

test_action_avoid_returns_exit
    conviction=AVOID → action=EXIT

test_urgency_immediate_strong_momentum
    conviction=HIGH_PLUS, roc_5=3.5 (> 3%) → urgency=IMMEDIATE

test_urgency_developing_positive_roc21
    conviction=HIGH, roc_21=2.0 (> 0) → urgency=DEVELOPING

test_urgency_patient_default
    conviction=MEDIUM, roc_5=1.0 → urgency=PATIENT

test_four_factor_handles_missing_sector_rs
    sector_rs CTE returns no rows → factor_sector_rs=False, sector_rs_composite=None
    Assert full model returned (not None)

test_screener_percentile_rank_sql_not_python
    Call compute_screener_bulk with mocked session
    Assert the SQL string in the captured query contains "percent_rank()"
    Assert no Python sorting of roc_21 values occurs in code

test_screener_filters_by_nifty50
    filters = {"universe": "nifty50", ...}
    Assert generated SQL contains "nifty_50 = true"

test_screener_filters_by_sector
    filters = {"sector": "Banking", ...}
    Assert generated SQL contains sector parameter binding (not f-string injection)

test_screener_filters_by_conviction
    Mock 5 rows returned, 2 with conviction=HIGH, 3 with conviction=MEDIUM
    filters = {"conviction": "HIGH"}
    Assert only 2 rows returned in result

test_screener_returns_conviction_and_action
    Mock row with rs_composite=110, roc_21_pct_rank=0.8, sector_rs=105, cmf_20=0.2, mfi_14=60
    regime="BULL"
    Assert ScreenerRow has conviction_level=HIGH_PLUS, action_signal=BUY

test_screener_limit_offset_pagination
    filters = {"limit": 10, "offset": 20}
    Assert SQL contains LIMIT 10 OFFSET 20
```

### `tests/routes/test_screener_route.py`

Route tests using httpx `AsyncClient` with `app.dependency_overrides[get_db]`.

```
test_screener_route_returns_200
    GET /api/v1/screener → 200, response has "rows" and "meta"

test_screener_route_filters_universe_nifty50
    GET /api/v1/screener?universe=nifty50
    Assert meta.record_count matches mocked filtered count
```

**Total: 20 tests minimum across both test files.**
