# C-DER-2: 4-Factor Conviction Engine + Action + Urgency + Screener

**Slice:** V6.5 — Derived Signal Engine
**Depends on:** C-DER-1 (GoldRS/Piotroski wired), V6-5 (stocks/{symbol} deep-dive route)
**Blocks:** C-DER-3 (sentiment uses regime string produced by breadth route; screener is prerequisite for pulse-stocks page)
**Complexity:** L (7–9 hours)
**Quality targets:** code: 82, security: 90, architecture: 85, api: 90

---

## ⛔ NON-NEGOTIABLE — READ FIRST

This chunk is **REJECTED** if the DONE commit does not contain **all** of
these files at or above the stated size floor. A bare `.forge/baseline/*`
bump or any commit that does not materially land the deliverables below is
a false-DONE and will be flipped back to PENDING on audit.

```
PRESENT, net-new:
  backend/services/conviction_engine.py        ≥ 260 lines
  backend/routes/screener.py                   ≥ 90 lines
  tests/services/test_conviction_engine.py     ≥ 400 lines, ≥ 20 tests
  tests/routes/test_screener_route.py          ≥ 80 lines,  ≥ 3 tests

MODIFIED, additive only:
  backend/models/schemas.py                    ≥ 60 lines added
                                               (ConvictionLevel + ActionSignal
                                               + UrgencyLevel + FourFactorConviction
                                               + ScreenerRow + ScreenerResponse
                                               + four_factor field on StockDeepDive)
  backend/routes/stocks.py                     ≥ 10 lines added
                                               (compute_four_factor added to
                                               asyncio.gather, constructor kwarg)
  backend/main.py                              ≥ 2 lines added
                                               (import + include_router for screener)
```

**Self-check loop (run before stamping DONE):**

```bash
for f in backend/services/conviction_engine.py \
         backend/routes/screener.py \
         tests/services/test_conviction_engine.py \
         tests/routes/test_screener_route.py; do
  test -f "$f" || { echo "MISSING: $f"; exit 1; }
  wc -l "$f"
done
grep -c "^class ConvictionLevel\|^class ActionSignal\|^class UrgencyLevel\|^class FourFactorConviction\|^class ScreenerRow\|^class ScreenerResponse" backend/models/schemas.py
grep -n "compute_four_factor\|asyncio.gather" backend/routes/stocks.py
grep -n "screener" backend/main.py
pytest tests/services/test_conviction_engine.py tests/routes/test_screener_route.py -v
curl -s http://localhost:8000/api/v1/screener?universe=nifty50 | jq '.rows | length'
```

If any line fails → **DO NOT** stamp DONE.

---

## Goal

Compute the 4-factor conviction model (Returns RS × Momentum RS × Sector RS
× Volume RS), derive `ActionSignal` and `UrgencyLevel` from conviction +
regime context, attach them to the existing deep-dive response, and expose
a new paginated `GET /api/v1/screener` endpoint.

The screener must perform percentile-rank computation entirely in SQL using
a window function — never load all rows into Python and sort. The
conviction engine must be a pure computation module with no HTTP
dependencies.

---

## Schema reality (verified against live RDS, 2026-04-17)

- `de_equity_technical_daily` has: `roc_5, roc_21, cmf_20, mfi_14, rsi_14, above_50dma, above_200dma, macd_bullish, adx_14` — all the columns this chunk uses.
- `de_rs_scores` row layout: `entity_type ∈ {'equity', 'sector'}`, `entity_id` is a STRING (not UUID) — for `entity_type='equity'` it holds the instrument UUID as a string; for `entity_type='sector'` it holds the sector name. `vs_benchmark` is a string like `'NIFTY 500'`.
- `de_instrument` has: `id, current_symbol, company_name, sector, nifty_50, nifty_200, nifty_500, is_active`.
- `de_equity_fundamentals` has: `market_cap_cr, pe_ratio`.

Because `entity_id` in `de_rs_scores` is already a text column, the SQL
must cast `i.id::text = r.entity_id` in join predicates rather than
`entity_id::uuid = i.id`. This guards against "invalid input syntax for
type uuid" errors when a non-UUID sector-row ends up in the join plan.

---

## Files

### New
- `backend/services/conviction_engine.py` — `compute_four_factor()`, `compute_screener_bulk()`, `_compute_conviction_from_row()` pure helper
- `backend/routes/screener.py` — `GET /api/v1/screener` route
- `tests/services/test_conviction_engine.py` — unit tests for conviction + screener (≥20)
- `tests/routes/test_screener_route.py` — route-level tests (≥3)

### Modified
- `backend/models/schemas.py` — add `ConvictionLevel`, `ActionSignal`, `UrgencyLevel`, `FourFactorConviction`, `ScreenerRow`, `ScreenerResponse` models; add `four_factor: Optional[FourFactorConviction] = None` field to `StockDeepDive`
- `backend/routes/stocks.py` — add `compute_four_factor()` call to the existing `asyncio.gather` from C-DER-1, inject into `StockDeepDive`
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
    factor_sector_rs: bool = False      # sector rs_composite > 100
    factor_volume_rs: bool = False      # cmf_20 > 0 AND mfi_14 > 50
    factors_aligned: int = 0            # count of True factors (0–4)
    # Supporting values (for display / audit trail)
    rs_composite: Optional[Decimal] = None
    roc_21_pct_rank: Optional[Decimal] = None   # 0.0–1.0
    sector_rs_composite: Optional[Decimal] = None
    cmf_20: Optional[Decimal] = None
    mfi_14: Optional[Decimal] = None
    regime: Optional[str] = None


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

### Add to `StockDeepDive` (after `piotroski`)

```python
four_factor: Optional[FourFactorConviction] = None
```

Additive only.

---

## Implementation notes

### `backend/services/conviction_engine.py`

#### `async def compute_four_factor(instrument_id: UUID, sector: Optional[str], db: AsyncSession, regime: Optional[str] = None) -> Optional[FourFactorConviction]`

Returns `None` when the instrument has no technical row for the latest
date. One SQL round-trip via CTE — do **not** issue 4 separate queries.

**SQL (single query, note the `ranked` subquery for percent_rank):**

```sql
WITH latest_tech_date AS (
    SELECT MAX(date) AS d FROM de_equity_technical_daily
),
target_tech AS (
    SELECT roc_21, cmf_20, mfi_14, roc_5
    FROM de_equity_technical_daily
    WHERE instrument_id = :instrument_id
      AND date = (SELECT d FROM latest_tech_date)
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
      AND date = (SELECT MAX(date) FROM de_rs_scores WHERE entity_type = 'sector')
    LIMIT 1
),
roc_pct_rank AS (
    SELECT pct_rank
    FROM (
        SELECT
            instrument_id,
            percent_rank() OVER (ORDER BY roc_21 ASC NULLS FIRST) AS pct_rank
        FROM de_equity_technical_daily
        WHERE date = (SELECT d FROM latest_tech_date)
    ) ranked
    WHERE instrument_id = :instrument_id
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

**Important SQL caveat — nested window functions:** PostgreSQL does not
allow window functions nested inside aggregate/window contexts. The
`percent_rank()` computation lives inside a plain subquery `ranked` and
the outer query filters to the target row — correct pattern, do not
try to "optimize" it by merging the ranked subquery with an aggregate.

Bind `:instrument_id` as UUID, `:instrument_id_str` as str(uuid), `:sector`
as str or None.

**Factor evaluation (pure Python):**

All values converted to `Decimal(str(x))` before comparison. `None` →
factor = `False`.

```python
factor_returns_rs = rs_composite is not None and rs_composite > Decimal("100")
factor_momentum_rs = roc_21_pct_rank is not None and roc_21_pct_rank > Decimal("0.6")
factor_sector_rs = sector_rs_composite is not None and sector_rs_composite > Decimal("100")
factor_volume_rs = (
    cmf_20 is not None and mfi_14 is not None
    and cmf_20 > Decimal("0") and mfi_14 > Decimal("50")
)
factors_aligned = sum([factor_returns_rs, factor_momentum_rs,
                       factor_sector_rs, factor_volume_rs])
```

**ConvictionLevel map (pure function, shared with screener):**
- 4 → `HIGH_PLUS`
- 3 → `HIGH`
- 2 → `MEDIUM`
- 1 → `LOW`
- 0 → `AVOID`

**ActionSignal derivation:**

```python
bull_regime = regime is not None and regime.upper() in ("BULL", "RECOVERY")

if conviction in (ConvictionLevel.HIGH_PLUS, ConvictionLevel.HIGH) and bull_regime:
    action = ActionSignal.BUY
elif conviction in (ConvictionLevel.HIGH_PLUS, ConvictionLevel.HIGH):
    action = ActionSignal.ACCUMULATE
elif conviction == ConvictionLevel.MEDIUM:
    action = ActionSignal.WATCH
elif conviction == ConvictionLevel.LOW and rs_composite is not None and rs_composite < Decimal("100"):
    action = ActionSignal.REDUCE
else:
    action = ActionSignal.EXIT
```

**UrgencyLevel derivation (proxy until V7 decision-tracking):**

```python
if (conviction == ConvictionLevel.HIGH_PLUS
        and roc_5 is not None
        and Decimal(str(roc_5)) > Decimal("3")):
    urgency = UrgencyLevel.IMMEDIATE
elif (conviction in (ConvictionLevel.HIGH_PLUS, ConvictionLevel.HIGH)
        and roc_21 is not None
        and Decimal(str(roc_21)) > Decimal("0")):
    urgency = UrgencyLevel.DEVELOPING
else:
    urgency = UrgencyLevel.PATIENT
```

Extract conviction → action → urgency into a shared helper:
```python
def _compute_conviction_from_factors(
    factors_aligned: int,
    rs_composite: Optional[Decimal],
    roc_5: Optional[Decimal],
    roc_21: Optional[Decimal],
    regime: Optional[str],
) -> tuple[ConvictionLevel, ActionSignal, UrgencyLevel]:
    ...
```

`compute_four_factor` and `compute_screener_bulk` both call this helper.

**Sector is None handling:** `factor_sector_rs = False`, `sector_rs_composite
= None`. Do **not** return None for the whole model.

#### `async def compute_screener_bulk(filters: dict[str, Any], db: AsyncSession) -> list[dict[str, Any]]`

Single bulk SQL fetch, then Python-side conviction derivation per row.

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
        roc_21, cmf_20, mfi_14, rsi_14, above_50dma, above_200dma, macd_bullish, roc_5,
        percent_rank() OVER (ORDER BY roc_21 ASC NULLS FIRST) AS roc_21_pct_rank
    FROM de_equity_technical_daily
    WHERE date = (SELECT d FROM latest_tech_date)
),
latest_rs AS (
    SELECT entity_id AS instrument_id_str, rs_composite
    FROM de_rs_scores
    WHERE entity_type = 'equity'
      AND vs_benchmark = 'NIFTY 500'
      AND date = (SELECT d FROM latest_rs_date)
)
SELECT
    i.current_symbol AS symbol,
    i.company_name, i.sector, i.nifty_50, i.nifty_500,
    t.rsi_14, t.above_50dma, t.above_200dma, t.macd_bullish,
    t.cmf_20, t.mfi_14, t.roc_21, t.roc_5, t.roc_21_pct_rank,
    r.rs_composite,
    sr.sector_rs,
    f.market_cap_cr, f.pe_ratio
FROM de_instrument i
LEFT JOIN ranked_tech t ON t.instrument_id = i.id
LEFT JOIN latest_rs r ON r.instrument_id_str = i.id::text
LEFT JOIN sector_rs_latest sr ON sr.sector_name = i.sector
LEFT JOIN de_equity_fundamentals f ON f.instrument_id = i.id
WHERE i.is_active = true
  {universe_filter}
  {sector_filter}
ORDER BY r.rs_composite DESC NULLS LAST
LIMIT :limit OFFSET :offset
```

`universe_filter` is whitelisted — only `nifty_50`, `nifty_200`, `nifty_500`
column names may be injected. Build like:
```python
universe_sql = {
    "nifty50": "AND i.nifty_50 = true",
    "nifty200": "AND i.nifty_200 = true",
    "nifty500": "AND i.nifty_500 = true",
}.get(filters.get("universe"), "")
```

`sector_filter` uses bound param: `AND i.sector = :sector` when `filters["sector"]` is not None; otherwise empty.

**NEVER use Python f-strings to interpolate user-supplied values. Only the
whitelisted universe-column name string is concatenated; all other values
bind via SQLAlchemy `text(...).bindparams(...)`.**

After fetching rows, compute `(conviction, action, urgency)` per row via
`_compute_conviction_from_factors`. Apply optional post-SQL filters for
`conviction` and `action` in Python (these values are not in DB).

### `backend/routes/screener.py`

```python
import time
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.services.conviction_engine import compute_screener_bulk
from backend.clients.jip_market_service import JIPMarketService
from backend.models.schemas import (
    ScreenerResponse, ScreenerRow, ResponseMeta,
    ConvictionLevel, ActionSignal, UrgencyLevel,
)

router = APIRouter(prefix="/api/v1/screener", tags=["screener"])

_VALID_UNIVERSE = {"nifty50", "nifty200", "nifty500"}
_VALID_CONVICTION = {e.value for e in ConvictionLevel}
_VALID_ACTION = {e.value for e in ActionSignal}


@router.get("", response_model=ScreenerResponse)
async def get_screener(
    universe: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    conviction: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ScreenerResponse:
    if universe is not None and universe not in _VALID_UNIVERSE:
        raise HTTPException(422, detail=f"universe must be in {_VALID_UNIVERSE}")
    if conviction is not None and conviction not in _VALID_CONVICTION:
        raise HTTPException(422, detail=f"conviction must be in {_VALID_CONVICTION}")
    if action is not None and action not in _VALID_ACTION:
        raise HTTPException(422, detail=f"action must be in {_VALID_ACTION}")

    t0 = time.perf_counter()
    regime_data = await JIPMarketService(db).get_market_regime()
    regime_str = (regime_data.get("regime") if regime_data else None) or "SIDEWAYS"

    filters = {
        "universe": universe, "sector": sector,
        "conviction": conviction, "action": action,
        "limit": limit, "offset": offset, "regime": regime_str,
    }
    rows = await compute_screener_bulk(filters, db)
    screener_rows = [ScreenerRow(**row) for row in rows]
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return ScreenerResponse(
        rows=screener_rows,
        meta=ResponseMeta(
            record_count=len(screener_rows),
            offset=offset,
            limit=limit,
            query_ms=elapsed_ms,
        ),
    )
```

### Wiring `compute_four_factor` into `backend/routes/stocks.py`

Extend the existing C-DER-1 `asyncio.gather` block to include a third task:

```python
from backend.services.conviction_engine import compute_four_factor

regime_data = await JIPMarketService(db).get_market_regime()
regime_str = (regime_data.get("regime") if regime_data else None) or "SIDEWAYS"

async def _four_factor_task() -> Optional[FourFactorConviction]:
    async with async_session_factory() as s:
        return await compute_four_factor(
            instrument_id=stock_detail["id"],
            sector=stock_detail.get("sector"),
            db=s,
            regime=regime_str,
        )

gold_rs_result, piotroski_result, four_factor_result = await asyncio.gather(
    _gold_rs_task(), _piotroski_task(), _four_factor_task(),
    return_exceptions=True,
)
four_factor_val = four_factor_result if isinstance(four_factor_result, FourFactorConviction) else None
```

Pass `four_factor=four_factor_val` into `StockDeepDive(...)`.

### Registration in `backend/main.py`

```python
from backend.routes import screener
...
app.include_router(screener.router)
```

### Edge cases

| Scenario | Behaviour |
|---|---|
| Sector is None | factor_sector_rs=False, sector_rs_composite=None, model still returned |
| Stock has no tech row | compute_four_factor returns None |
| roc_21 NULL | pct_rank=None, factor_momentum_rs=False |
| universe + sector combined | Both applied as SQL AND |
| conviction="HIGH+" (URL-encoded) | Matches ConvictionLevel.HIGH_PLUS.value |
| regime None | bull_regime=False → action not BUY |
| compute_four_factor raises | gather returns exception → caller sets None |

---

## Points of success (14, all required for DONE)

1. `backend/services/conviction_engine.py` exists, ≥260 lines, exports `compute_four_factor`, `compute_screener_bulk`, `_compute_conviction_from_factors`.
2. `backend/routes/screener.py` exists, ≥90 lines, defines `GET /api/v1/screener`.
3. `backend/models/schemas.py` exposes the 6 new models + `four_factor` on `StockDeepDive`.
4. `backend/routes/stocks.py` runs `compute_four_factor` inside the same `asyncio.gather` as GoldRS / Piotroski.
5. `backend/main.py` registers `screener.router`.
6. `GET /api/v1/stocks/RELIANCE` response contains `stock.four_factor` with all 3 enums + 4 booleans + supporting values + `regime` field.
7. `GET /api/v1/screener` → 200 with `rows: list[ScreenerRow]` and `meta`.
8. `GET /api/v1/screener?universe=nifty50` returns only nifty_50 rows.
9. `GET /api/v1/screener?sector=Banking` returns only Banking rows.
10. `GET /api/v1/screener?conviction=HIGH%2B` filters correctly (URL-encoded "+"). `GET /api/v1/screener?action=BUY` also works.
11. `GET /api/v1/screener?limit=10&offset=0` respects pagination. `limit > 200` → 422.
12. **Percentile rank is computed in PostgreSQL** (`percent_rank()` window function). A grep of `backend/services/conviction_engine.py` must show **zero** calls to `sorted()` or `rank()` or manual `.index()` on roc lists. A test enforces this.
13. **Semantic sentinels:**
    - All 4 factors True + regime BULL → `conviction=HIGH_PLUS, action=BUY, factors_aligned=4`.
    - All 4 factors False → `conviction=AVOID, action=EXIT, factors_aligned=0`.
    - factor_volume_rs requires BOTH cmf_20 > 0 AND mfi_14 > 50 — 3 scenarios covered.
    - Invalid query params (universe="foo") → 422, not 500.
14. Quality gate: `ruff check` clean, `mypy backend/services/conviction_engine.py backend/routes/screener.py --ignore-missing-imports` clean, ≥20 + ≥3 tests pass, full suite does not regress.

---

## Tests

### `tests/services/test_conviction_engine.py` (≥20 tests, ≥400 lines)

All tests mock `AsyncSession.execute`. Do NOT hit real DB.

1. `test_four_factor_all_true_returns_high_plus` — rs=105, pct_rank=0.75, sector_rs=105, cmf=0.1, mfi=55 → HIGH_PLUS, aligned=4.
2. `test_four_factor_zero_returns_avoid` — rs=90, pct_rank=0.3, sector_rs=90, cmf=-0.1, mfi=40 → AVOID, aligned=0.
3. `test_four_factor_three_aligned_returns_high` — exactly 3 True → HIGH.
4. `test_four_factor_two_aligned_returns_medium` — exactly 2 → MEDIUM.
5. `test_four_factor_one_aligned_returns_low` — exactly 1 → LOW.
6. `test_four_factor_sector_rs_reads_sector_table` — entity_type='sector' row → factor_sector_rs=True when >100.
7. `test_four_factor_volume_rs_requires_both` — cmf=0.1/mfi=45 → False; cmf=-0.1/mfi=55 → False; cmf=0.1/mfi=55 → True.
8. `test_four_factor_handles_missing_sector` — sector=None → factor_sector_rs=False, model still returned.
9. `test_four_factor_handles_missing_tech_row` — target_tech empty → returns None.
10. `test_action_bull_regime_high_plus_returns_buy` — HIGH_PLUS + BULL → BUY.
11. `test_action_bear_regime_high_returns_accumulate` — HIGH + BEAR → ACCUMULATE.
12. `test_action_medium_returns_watch` — MEDIUM → WATCH regardless of regime.
13. `test_action_low_falling_returns_reduce` — LOW + rs=95 → REDUCE.
14. `test_action_avoid_returns_exit` — AVOID → EXIT.
15. `test_urgency_immediate_strong_momentum` — HIGH_PLUS + roc_5=3.5 → IMMEDIATE.
16. `test_urgency_developing_positive_roc21` — HIGH + roc_21=2.0 → DEVELOPING.
17. `test_urgency_patient_default` — MEDIUM or low roc → PATIENT.
18. `test_screener_uses_sql_percentile_not_python` — **semantic sentinel.** Import `backend.services.conviction_engine`, read `inspect.getsource`, assert "percent_rank" in source and assert `"sorted(" not in source` for any roc-related list.
19. `test_screener_filters_by_nifty50` — filters["universe"]="nifty50" → generated SQL contains `i.nifty_50 = true`.
20. `test_screener_filters_by_sector_param_bound` — filters["sector"]="Banking" → SQL contains `:sector` binding, not `'Banking'` interpolated.
21. `test_screener_filters_by_conviction_python_side` — 5 mocked rows with mixed convictions, filter="HIGH" → only matching rows returned.
22. `test_screener_returns_conviction_and_action` — row with rs=110, pct_rank=0.8, sector_rs=105, cmf=0.2, mfi=60 + regime=BULL → ScreenerRow has conviction=HIGH_PLUS, action=BUY.
23. `test_screener_limit_offset_pagination` — filters["limit"]=10, offset=20 → SQL contains LIMIT 10 OFFSET 20.

### `tests/routes/test_screener_route.py` (≥3 tests, ≥80 lines)

httpx `AsyncClient` + `app.dependency_overrides[get_db]`.

1. `test_screener_route_returns_200` — GET /api/v1/screener → 200, has `rows` and `meta`.
2. `test_screener_route_rejects_invalid_universe` — GET /api/v1/screener?universe=foo → 422.
3. `test_screener_route_filters_universe_nifty50_passes_through` — mock `compute_screener_bulk` → assert the filters dict passed in includes `universe="nifty50"`.

### Deep-dive non-regression test (append to `tests/routes/test_stock_derived_signals.py` from C-DER-1)

Add one new test `test_stock_deep_dive_includes_four_factor` — assert `response.stock.four_factor.conviction_level` is one of the 5 enum values, `action_signal` one of 5, `urgency` one of 3, and that `gold_rs` + `piotroski` from C-DER-1 are still present (non-regression).

---

## Live smoke (required at DONE)

After the chunk ships and the backend service restarts:

```bash
curl -s https://atlas.jslwealth.in/api/v1/stocks/RELIANCE \
  | jq '{four_factor: .stock.four_factor.conviction_level,
         action: .stock.four_factor.action_signal,
         urgency: .stock.four_factor.urgency,
         aligned: .stock.four_factor.factors_aligned,
         gold: .stock.gold_rs.signal,
         piotroski: .stock.piotroski.score}'

curl -s "https://atlas.jslwealth.in/api/v1/screener?universe=nifty50&limit=5" \
  | jq '.rows | map({symbol, conviction: .conviction_level, action: .action_signal}) | .[]'

# Negative: invalid universe must 422
curl -sS -o /dev/null -w "%{http_code}\n" \
  "https://atlas.jslwealth.in/api/v1/screener?universe=nonsense"
```

Expected:
- RELIANCE: returns `four_factor` populated + C-DER-1 fields intact.
- Screener: 5 rows, all nifty_50 members, each with conviction + action.
- Invalid universe: `422`.

Paste output into `docs/decisions/session-log.md` under the C-DER-2 entry.

---

## Post-chunk sync invariant

`scripts/post-chunk.sh C-DER-2` MUST green: commit+push, service restart,
smoke probe, /forge-compile, MEMORY.md append. All 5 must pass. Otherwise
chunk is not DONE.
