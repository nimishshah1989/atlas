# C-DER-3: Sector RRG + Sentiment Composite + Regime Enrichment

**Slice:** V6.5 — Derived Signal Engine
**Depends on:** C-DER-1, C-DER-2 (derived signal engine complete), V6-1..V6-9 (existing routes stable)
**Blocks:** Frontend pulse-sectors RRG page, pulse-sentiment page, pulse-breadth signal history table
**Complexity:** L (8–10 hours)
**Quality targets:** code: 82, security: 90, architecture: 85, api: 90

---

## Goal

Three new capabilities delivered as one chunk:

**Part A — Regime Enrichment:** Add `days_in_regime` (integer count of consecutive days in the current regime) and `regime_history` (last 5 regime transitions) to the existing `RegimeSnapshot` / `MarketBreadthResponse`. Pure SQL CTE — no new table.

**Part B — Sector RRG endpoint:** `GET /api/v1/sectors/rrg` returns normalised RS score (100-centred), RS momentum, RRG quadrant, and a 4-point trail for every sector. Powers the Sector Compass / Relative Rotation Graph.

**Part C — Sentiment Composite endpoint:** `GET /api/v1/sentiment/composite` returns a 0–100 composite sentiment score built from 4 components: Price Breadth, Options/PCR, Institutional Flow, Fundamental Revisions. Components with unavailable data (de_fo_summary = 0 rows, de_flow_daily ≈ 5 rows) are marked `available=False` and their weights are redistributed to available components.

---

## Files

### New
- `backend/routes/sectors.py` — `GET /api/v1/sectors/rrg` route
- `backend/routes/sentiment.py` — `GET /api/v1/sentiment/composite` route
- `backend/services/regime_service.py` — `compute_days_in_regime()`, `compute_regime_history()` service functions
- `backend/services/rrg_service.py` — `compute_sector_rrg()` service function
- `backend/services/sentiment_service.py` — `compute_sentiment_composite()` service function
- `tests/services/test_regime_service.py` — regime enrichment tests
- `tests/services/test_rrg_service.py` — RRG computation tests
- `tests/services/test_sentiment_service.py` — sentiment composite tests
- `tests/routes/test_sectors_rrg.py` — route-level test for RRG endpoint
- `tests/routes/test_sentiment_route.py` — route-level test for sentiment endpoint

### Modified
- `backend/models/schemas.py` — add `RegimeTransition`, extend `RegimeSnapshot` with `days_in_regime` and `regime_history`; add `RRGPoint`, `RRGSector`, `RRGResponse`; add `SentimentZone`, `SentimentComponent`, `SentimentResponse`
- `backend/routes/stocks.py` — call `compute_days_in_regime()` and `compute_regime_history()` inside `get_breadth`; inject into `RegimeSnapshot`
- `backend/main.py` — register `sectors.router` and `sentiment.router`

---

## Contracts

### New Pydantic models (add to `backend/models/schemas.py`)

```python
class RegimeTransition(BaseModel):
    regime: str
    started_date: date
    ended_date: Optional[date] = None     # None if this is the current regime
    duration_days: int
    breadth_pct_at_start: Optional[Decimal] = None


class SentimentZone(str, Enum):
    EXTREME_FEAR = "EXTREME_FEAR"
    FEAR = "FEAR"
    NEUTRAL = "NEUTRAL"
    GREED = "GREED"
    EXTREME_GREED = "EXTREME_GREED"


class SentimentComponent(BaseModel):
    name: str
    score: Optional[Decimal] = None       # 0–100, None when unavailable
    weight: Decimal                       # effective weight after redistribution
    available: bool = True
    note: Optional[str] = None            # reason string when not available


class SentimentResponse(BaseModel):
    composite_score: Optional[Decimal] = None   # 0–100 weighted average
    zone: Optional[SentimentZone] = None
    components: list[SentimentComponent]
    weight_redistribution_active: bool = False   # True when PCR/flow weights were redistributed
    as_of: Optional[date] = None
    meta: ResponseMeta


class RRGPoint(BaseModel):
    date: date
    rs_score: Decimal                     # normalised, 100-centred
    rs_momentum: Decimal                  # today_rs_composite - lag_rs_composite


class RRGSector(BaseModel):
    sector: str
    rs_score: Decimal                     # normalised: (rs_composite - mean) / stddev * 10 + 100
    rs_momentum: Decimal                  # raw: rs_composite_today - rs_composite_28d_ago
    quadrant: Quadrant                    # existing Quadrant enum: LEADING/WEAKENING/IMPROVING/LAGGING
    pct_above_50dma: Optional[Decimal] = None
    breadth_regime: Optional[str] = None
    tail: list[RRGPoint] = []             # last 4 weekly (every 7 days) snapshots


class RRGResponse(BaseModel):
    sectors: list[RRGSector]
    mean_rs: Decimal                      # mean of raw rs_composite values across all sectors
    stddev_rs: Decimal                    # stddev of raw rs_composite values
    as_of: date
    meta: ResponseMeta
```

### Modified `RegimeSnapshot` (add two Optional fields)

```python
days_in_regime: Optional[int] = None
regime_history: list[RegimeTransition] = []    # last 5 completed transitions
```

---

## Implementation notes

### Part A — `backend/services/regime_service.py`

#### `async def compute_days_in_regime(db: AsyncSession) -> Optional[int]`

Returns the count of consecutive days the market has been in its current regime (inclusive of today).

**SQL:**
```sql
WITH regime_today AS (
    SELECT regime, date AS today_date
    FROM de_market_regime
    ORDER BY date DESC
    LIMIT 1
),
first_break AS (
    SELECT date AS break_date
    FROM de_market_regime
    WHERE regime != (SELECT regime FROM regime_today)
    ORDER BY date DESC
    LIMIT 1
)
SELECT COUNT(*) AS days_in_regime
FROM de_market_regime
WHERE date > COALESCE(
        (SELECT break_date FROM first_break),
        '2000-01-01'::date
    )
  AND regime = (SELECT regime FROM regime_today)
```

If `de_market_regime` has no rows, return `None`. If the regime has never changed (no first_break row), `COALESCE` falls back to `'2000-01-01'` and counts all rows.

Returns `int` (the count).

#### `async def compute_regime_history(db: AsyncSession) -> list[RegimeTransition]`

Returns the last 5 completed regime periods (not including the current one) ordered from most recent to oldest.

**SQL:**
```sql
WITH numbered AS (
    SELECT
        date,
        regime,
        LAG(regime) OVER (ORDER BY date DESC) AS next_regime,
        LEAD(regime) OVER (ORDER BY date DESC) AS prev_regime
    FROM de_market_regime
),
transitions AS (
    SELECT
        date AS transition_date,
        regime
    FROM numbered
    WHERE next_regime IS DISTINCT FROM regime
       OR next_regime IS NULL
    ORDER BY date DESC
    LIMIT 12
)
SELECT * FROM transitions
```

This is complex in pure SQL — implement in Python using a minimal fetch:

```sql
SELECT date, regime
FROM de_market_regime
ORDER BY date DESC
LIMIT 400
```

Then identify run-length encoding in Python on this small result (max 400 rows):

```python
transitions = []
current_regime = None
current_start = None
prev_row_date = None

for row in rows:  # rows ordered DESC
    if row["regime"] != current_regime:
        if current_regime is not None:
            duration = (current_start - row["date"]).days
            transitions.append(RegimeTransition(
                regime=current_regime,
                started_date=row["date"],   # the day after this row
                ended_date=current_start,
                duration_days=duration,
                breadth_pct_at_start=None,  # breadth join is optional, skip for now
            ))
        current_regime = row["regime"]
        current_start = row["date"]
    prev_row_date = row["date"]

# Return all except first (which is the current regime) and limit to 5
return transitions[1:6]
```

The 400-row fetch is safe: de_market_regime has ~500 rows at most (daily, 2 years). Python RLE on 400 rows is O(n) with negligible memory.

**Wiring into `get_breadth` route:**

Inside `backend/routes/stocks.py`, `get_breadth` function, after building `regime = RegimeSnapshot(...)`:

```python
from backend.services.regime_service import compute_days_in_regime, compute_regime_history
from backend.db.session import async_session_factory

async def _days_task() -> Optional[int]:
    async with async_session_factory() as s:
        return await compute_days_in_regime(s)

async def _history_task() -> list[RegimeTransition]:
    async with async_session_factory() as s:
        return await compute_regime_history(s)

days_result, history_result = await asyncio.gather(
    _days_task(), _history_task(), return_exceptions=True
)
days_val = days_result if isinstance(days_result, int) else None
history_val = history_result if isinstance(history_result, list) else []

regime = RegimeSnapshot(
    ...existing fields...,
    days_in_regime=days_val,
    regime_history=history_val,
)
```

### Part B — `backend/services/rrg_service.py`

#### `async def compute_sector_rrg(benchmark: str, db: AsyncSession) -> RRGResponse`

**Step 1: Fetch latest sector RS scores**
```sql
WITH latest_sector_date AS (
    SELECT MAX(date) AS d
    FROM de_rs_scores
    WHERE entity_type = 'sector'
),
lag_date AS (
    SELECT MAX(date) AS d
    FROM de_rs_scores
    WHERE entity_type = 'sector'
      AND date <= (SELECT d FROM latest_sector_date) - INTERVAL '28 days'
),
today_rs AS (
    SELECT entity_id AS sector, rs_composite
    FROM de_rs_scores
    WHERE entity_type = 'sector'
      AND date = (SELECT d FROM latest_sector_date)
),
lag_rs AS (
    SELECT entity_id AS sector, rs_composite AS rs_composite_lag
    FROM de_rs_scores
    WHERE entity_type = 'sector'
      AND date = (SELECT d FROM lag_date)
),
stats AS (
    SELECT
        AVG(rs_composite) AS mean_rs,
        STDDEV_SAMP(rs_composite) AS stddev_rs
    FROM today_rs
),
breadth_latest AS (
    SELECT DISTINCT ON (sector)
        sector, pct_above_50dma, breadth_regime
    FROM de_sector_breadth_daily
    ORDER BY sector, date DESC
)
SELECT
    t.sector,
    t.rs_composite,
    COALESCE(l.rs_composite_lag, t.rs_composite) AS rs_composite_lag,
    t.rs_composite - COALESCE(l.rs_composite_lag, t.rs_composite) AS raw_momentum,
    s.mean_rs,
    s.stddev_rs,
    b.pct_above_50dma,
    b.breadth_regime,
    (SELECT d FROM latest_sector_date) AS as_of
FROM today_rs t
LEFT JOIN lag_rs l ON l.sector = t.sector
CROSS JOIN stats s
LEFT JOIN breadth_latest b ON b.sector = t.sector
```

**Step 2: Normalise rs_score in Python**

```python
mean_rs = Decimal(str(rows[0]["mean_rs"])) if rows else Decimal("100")
stddev_rs = Decimal(str(rows[0]["stddev_rs"])) if rows else Decimal("1")
if stddev_rs == Decimal("0"):
    stddev_rs = Decimal("1")  # guard: avoid division by zero when all sectors identical

for row in rows:
    rs_raw = Decimal(str(row["rs_composite"]))
    rs_score = (rs_raw - mean_rs) / stddev_rs * Decimal("10") + Decimal("100")
    rs_momentum = Decimal(str(row["raw_momentum"]))
    ...
```

**Step 3: Quadrant classification**

Using EXISTING `compute_quadrant()` from `backend/core/computations.py`:
- `rs_score > 100` and `rs_momentum > 0` → LEADING
- `rs_score < 100` and `rs_momentum > 0` → IMPROVING
- `rs_score > 100` and `rs_momentum < 0` → WEAKENING
- `rs_score < 100` and `rs_momentum < 0` → LAGGING
- If rs_score == 100 exactly, treat as > 100 (tie goes to RS side)

**Important:** The existing `compute_quadrant()` uses sign of rs_composite and rs_momentum (both positive for LEADING). For RRG the threshold is 100 (normalised). Do NOT reuse `compute_quadrant()` directly — implement `_rrg_quadrant(rs_score, rs_momentum)` inline in `rrg_service.py` to avoid semantic mismatch.

**Step 4: Fetch tail (last 4 weekly snapshots)**

Single SQL query for all sectors at 4 dates (today, -7d, -14d, -21d):
```sql
WITH weekly_dates AS (
    SELECT DISTINCT date
    FROM de_rs_scores
    WHERE entity_type = 'sector'
      AND date IN (
          (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector'),
          (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector'
           AND date <= (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector') - INTERVAL '7 days'),
          (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector'
           AND date <= (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector') - INTERVAL '14 days'),
          (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector'
           AND date <= (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector') - INTERVAL '21 days')
      )
)
SELECT r.entity_id AS sector, r.date, r.rs_composite
FROM de_rs_scores r
WHERE r.entity_type = 'sector'
  AND r.date IN (SELECT date FROM weekly_dates)
ORDER BY r.entity_id, r.date DESC
```

Group by sector in Python (O(n) dict) — safe since there are ~31 sectors × 4 dates = ~124 rows. For each weekly point, normalise rs_score using the same mean/stddev (today's). rs_momentum for tail points = rs_composite_that_week - rs_composite_week_before (use adjacent points in the tail). If a weekly date has no row for a sector, skip that tail point (fewer than 4 is acceptable).

**Step 5: Build `RRGResponse`**

```python
return RRGResponse(
    sectors=rrg_sectors,
    mean_rs=mean_rs,
    stddev_rs=stddev_rs,
    as_of=rows[0]["as_of"],
    meta=ResponseMeta(record_count=len(rrg_sectors), query_ms=elapsed_ms),
)
```

If there are 0 sector RS rows: raise `HTTPException(status_code=503, detail="Sector RS data not available")`.

### `backend/routes/sectors.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.services.rrg_service import compute_sector_rrg
from backend.models.schemas import RRGResponse

router = APIRouter(prefix="/api/v1/sectors", tags=["sectors"])


@router.get("/rrg", response_model=RRGResponse)
async def get_sector_rrg(
    benchmark: str = Query("NIFTY 50"),
    db: AsyncSession = Depends(get_db),
) -> RRGResponse:
    return await compute_sector_rrg(benchmark=benchmark, db=db)
```

**Note on route order:** This route (`/api/v1/sectors/rrg`) uses a fixed path. The existing `GET /api/v1/stocks/sectors` route (in `stocks.py`) is prefixed differently — no collision. Register `sectors.router` in `main.py`.

### Part C — `backend/services/sentiment_service.py`

#### `async def compute_sentiment_composite(db: AsyncSession) -> SentimentResponse`

**Component 1: Price Breadth (base weight 0.4)**

```sql
SELECT
    pct_above_200dma,
    pct_above_50dma,
    ad_ratio,
    mcclellan_oscillator,
    mcclellan_summation,
    new_52w_highs,
    new_52w_lows,
    advance + decline + COALESCE(unchanged, 0) AS total_stocks,
    date
FROM de_breadth_daily
ORDER BY date DESC
LIMIT 1
```

If no rows returned → raise `HTTPException(status_code=503, detail="Breadth data not available")`. Breadth is the only hard-fail — all other components degrade gracefully.

Normalise sub-metrics to 0–100:

```python
def _norm_breadth(row) -> Optional[Decimal]:
    scores = []
    # pct_above_200dma already 0-100
    if row["pct_above_200dma"] is not None:
        scores.append(Decimal(str(row["pct_above_200dma"])))
    # pct_above_50dma already 0-100
    if row["pct_above_50dma"] is not None:
        scores.append(Decimal(str(row["pct_above_50dma"])))
    # ad_ratio: clamp(ad_ratio * 50, 0, 100)
    if row["ad_ratio"] is not None:
        raw = Decimal(str(row["ad_ratio"])) * Decimal("50")
        scores.append(max(Decimal("0"), min(Decimal("100"), raw)))
    # mcclellan_oscillator: (oscillator + 150) / 3, clamped 0-100
    if row["mcclellan_oscillator"] is not None:
        raw = (Decimal(str(row["mcclellan_oscillator"])) + Decimal("150")) / Decimal("3")
        scores.append(max(Decimal("0"), min(Decimal("100"), raw)))
    # highs/(highs+lows) * 100; if both 0 → 50 (neutral)
    h = row.get("new_52w_highs") or 0
    l = row.get("new_52w_lows") or 0
    if h + l > 0:
        scores.append(Decimal(str(h)) / Decimal(str(h + l)) * Decimal("100"))
    else:
        scores.append(Decimal("50"))
    if not scores:
        return None
    return sum(scores, Decimal("0")) / Decimal(str(len(scores)))
```

**Component 2: Options/PCR (base weight 0.2)**

```sql
SELECT COUNT(*) AS row_count FROM de_fo_summary
```

If `row_count == 0`:
- `score = None`, `available = False`, `note = "PCR data unavailable — pipeline gap"`

When available (future):
- Fetch `pcr_oi`, `pcr_volume` from latest row
- PCR formula: if pcr_oi < 0.7 → score = 70 + (0.7 - pcr_oi) / 0.7 * 30 (greed territory); pcr_oi 0.7–1.2 → score = 50 (neutral); pcr_oi > 1.5 → score = 20 (extreme fear); interpolate linearly between thresholds

**Component 3: Institutional Flow (base weight 0.2)**

```sql
SELECT COUNT(*) AS row_count FROM de_flow_daily WHERE category = 'FII'
```

If `row_count <= 5` (the known dead-pipeline state):
- `score = None`, `available = False`, `note = "FII flow data unavailable — pipeline gap"`

When available (future):
- Fetch 30 days of net_flow, compute rolling sum
- Normalise to 0–100 via percentile of last 252 days

**Component 4: Fundamental Revisions (base weight 0.2)**

```sql
SELECT
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY revenue_growth_yoy_pct) AS median_rev_growth,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY profit_growth_yoy_pct) AS median_profit_growth,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pe_ratio) AS median_pe
FROM de_equity_fundamentals f
JOIN de_instrument i ON i.id = f.instrument_id
WHERE i.is_active = true
  AND i.nifty_500 = true
```

If all values are NULL (no fundamentals data): `score = None`, `available = False`, `note = "Fundamentals data unavailable"`.

When available:
```python
scores = []
# revenue_growth_pct: 0–30% range → 0–100
if median_rev_growth is not None:
    raw = max(Decimal("0"), min(Decimal("30"), Decimal(str(median_rev_growth))))
    scores.append(raw / Decimal("30") * Decimal("100"))
# profit_growth_pct: same range
if median_profit_growth is not None:
    raw = max(Decimal("0"), min(Decimal("30"), Decimal(str(median_profit_growth))))
    scores.append(raw / Decimal("30") * Decimal("100"))
# pe_ratio: rising PE relative to recent median = greed signal
# if median_pe > 20 → score > 50; cap at 40 → score=100
if median_pe is not None:
    pe_score = max(Decimal("0"), min(Decimal("100"),
        (Decimal(str(median_pe)) - Decimal("10")) / Decimal("30") * Decimal("100")
    ))
    scores.append(pe_score)
component_4_score = sum(scores, Decimal("0")) / Decimal(str(len(scores))) if scores else None
```

**Weight redistribution logic:**

```python
pcr_available = pcr_component.available
flow_available = flow_component.available

if not pcr_available and not flow_available:
    # Redistribute 0.4 total unavailable weight: 0.2 to breadth, 0.2 to fundamentals
    breadth_weight = Decimal("0.6")
    fund_weight = Decimal("0.4")
    pcr_weight = Decimal("0")
    flow_weight = Decimal("0")
    weight_redistribution_active = True
elif not pcr_available:
    breadth_weight = Decimal("0.5")
    fund_weight = Decimal("0.3")
    pcr_weight = Decimal("0")
    flow_weight = Decimal("0.2")
    weight_redistribution_active = True
elif not flow_available:
    breadth_weight = Decimal("0.5")
    fund_weight = Decimal("0.3")
    pcr_weight = Decimal("0.2")
    flow_weight = Decimal("0")
    weight_redistribution_active = True
else:
    breadth_weight = Decimal("0.4")
    fund_weight = Decimal("0.2")
    pcr_weight = Decimal("0.2")
    flow_weight = Decimal("0.2")
    weight_redistribution_active = False
```

**Composite score:**

```python
components_with_score = [
    (breadth_score, breadth_weight),
    (pcr_score, pcr_weight),
    (flow_score, flow_weight),
    (fund_score, fund_weight),
]
numerator = Decimal("0")
denominator = Decimal("0")
for score, weight in components_with_score:
    if score is not None and weight > Decimal("0"):
        numerator += score * weight
        denominator += weight

composite = (numerator / denominator) if denominator > Decimal("0") else None
```

**SentimentZone thresholds:**

```python
def _zone(score: Optional[Decimal]) -> Optional[SentimentZone]:
    if score is None:
        return None
    if score < Decimal("20"):
        return SentimentZone.EXTREME_FEAR
    if score < Decimal("40"):
        return SentimentZone.FEAR
    if score < Decimal("60"):
        return SentimentZone.NEUTRAL
    if score < Decimal("80"):
        return SentimentZone.GREED
    return SentimentZone.EXTREME_GREED
```

### `backend/routes/sentiment.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.services.sentiment_service import compute_sentiment_composite
from backend.models.schemas import SentimentResponse

router = APIRouter(prefix="/api/v1/sentiment", tags=["sentiment"])


@router.get("/composite", response_model=SentimentResponse)
async def get_sentiment_composite(
    db: AsyncSession = Depends(get_db),
) -> SentimentResponse:
    return await compute_sentiment_composite(db=db)
```

### Registration in `backend/main.py`

```python
from backend.routes import sectors, sentiment
...
app.include_router(sectors.router)
app.include_router(sentiment.router)
```

**Route ordering note:** The existing `GET /api/v1/stocks/sectors` route in `stocks.py` is NOT affected. The new `GET /api/v1/sectors/rrg` is under a different prefix (`/api/v1/sectors`). No collision.

### Edge cases

| Scenario | Behaviour |
|---|---|
| de_market_regime is empty | compute_days_in_regime returns None; compute_regime_history returns [] |
| Regime has never changed | days_in_regime = COUNT(*) of all rows; regime_history = [] |
| Sector RS scores are all identical (stddev_rs = 0) | Guard: set stddev_rs = Decimal("1") to avoid division by zero |
| Sector has no lag RS row (new sector) | rs_composite_lag = rs_composite_today; raw_momentum = 0; quadrant based on rs_score vs 100 |
| de_fo_summary = 0 rows | PCR component available=False, note="PCR data unavailable — pipeline gap" |
| de_flow_daily = 5 rows | Flow component available=False, note="FII flow data unavailable — pipeline gap" |
| de_breadth_daily = 0 rows | HTTP 503 from sentiment endpoint |
| Fundamental query returns all NULL medians | Component 4 available=False |
| 503 from breadth is only hard failure | All other missing data → partial score with weight redistribution |
| Tail has fewer than 4 weekly data points | Return as many as available (list shorter than 4 is valid) |

---

## Acceptance criteria

1. `GET /api/v1/stocks/breadth` response contains `regime.days_in_regime` (integer > 0) and `regime.regime_history` (list of up to 5 `RegimeTransition` objects).
2. `RegimeTransition` has `regime`, `started_date`, `ended_date`, `duration_days` fields.
3. `GET /api/v1/sectors/rrg` returns 200 with `sectors` list, each having `sector`, `rs_score`, `rs_momentum`, `quadrant`, and `tail` (up to 4 `RRGPoint`s).
4. All `rs_score` values in RRG response are normalised around 100 (no raw rs_composite values leaked).
5. `GET /api/v1/sectors/rrg` quadrant classification: rs_score > 100 + momentum > 0 → LEADING; rs_score < 100 + momentum > 0 → IMPROVING; rs_score > 100 + momentum < 0 → WEAKENING; rs_score < 100 + momentum < 0 → LAGGING.
6. `GET /api/v1/sentiment/composite` returns 200 with `composite_score`, `zone`, `components`, `weight_redistribution_active`, `as_of`.
7. When de_fo_summary has 0 rows: PCR component in response has `available=false` and `note` containing "pipeline gap".
8. When de_flow_daily has ≤ 5 rows: Flow component in response has `available=false`.
9. When PCR and Flow are both unavailable: `weight_redistribution_active=true`, breadth weight = 0.6, fundamentals weight = 0.4.
10. Sentiment zone: score < 20 → EXTREME_FEAR; 20–40 → FEAR; 40–60 → NEUTRAL; 60–80 → GREED; ≥ 80 → EXTREME_GREED.
11. When de_breadth_daily is empty: sentiment endpoint returns HTTP 503.
12. `ruff check . --select E,F,W` passes on all new/modified files.
13. `pytest tests/services/test_regime_service.py tests/services/test_rrg_service.py tests/services/test_sentiment_service.py -v` shows all 16+ tests passing.

---

## Tests

### `tests/services/test_regime_service.py`

```
test_days_in_regime_counts_consecutive_same_regime
    Mock de_market_regime with last 10 rows all "BULL"
    Assert return value == 10

test_days_in_regime_resets_on_regime_change
    Mock rows: 5 BULL, then 1 BEAR (at the break)
    Assert days_in_regime == 5 (only BULL days after the break)

test_regime_history_returns_last_5_transitions
    Mock rows spanning 3+ regime transitions
    Assert len(result) <= 5
    Assert result[0] is the most recently completed regime

test_days_in_regime_returns_none_when_table_empty
    Mock empty query result
    Assert return value is None
```

### `tests/services/test_rrg_service.py`

```
test_rrg_quadrant_leading_rs_gt_100_mom_positive
    rs_score=105, rs_momentum=2.0 → quadrant=LEADING

test_rrg_quadrant_lagging_rs_lt_100_mom_negative
    rs_score=95, rs_momentum=-1.5 → quadrant=LAGGING

test_rrg_quadrant_improving_rs_lt_100_mom_positive
    rs_score=97, rs_momentum=1.0 → quadrant=IMPROVING

test_rrg_quadrant_weakening_rs_gt_100_mom_negative
    rs_score=103, rs_momentum=-0.5 → quadrant=WEAKENING

test_rrg_normalize_centers_at_100
    Mock 3 sectors with rs_composite values 95, 100, 105
    Assert normalised rs_scores: middle sector ≈ 100, outer sectors ≈ 100 ± 10*stddev

test_rrg_stddev_zero_guard
    Mock all sectors with identical rs_composite (stddev=0)
    Assert no ZeroDivisionError; stddev used in normalisation = 1 (guard value)

test_rrg_tail_returns_4_weekly_points
    Mock 4 weekly date rows for a sector
    Assert RRGSector.tail has 4 RRGPoint objects
```

### `tests/services/test_sentiment_service.py`

```
test_sentiment_composite_redistributes_weight_when_pcr_empty
    Mock de_fo_summary returns 0 rows, de_flow_daily returns 5 rows
    Assert weight_redistribution_active == True
    Assert breadth component weight == Decimal("0.6")
    Assert fundamentals component weight == Decimal("0.4")

test_sentiment_breadth_score_normalizes_pct_above_200dma
    Mock pct_above_200dma=80 → contributes 80 to breadth average
    Mock pct_above_200dma=20 → contributes 20 to breadth average

test_sentiment_zone_extreme_fear_below_20
    Force composite_score = 15 → zone = EXTREME_FEAR

test_sentiment_zone_greed_above_60
    Force composite_score = 65 → zone = GREED

test_sentiment_marks_pcr_unavailable_when_fo_summary_empty
    Mock de_fo_summary COUNT returns 0
    Assert PCR component available == False
    Assert PCR component note contains "pipeline gap"

test_sentiment_marks_flow_unavailable_when_flow_daily_empty
    Mock de_flow_daily COUNT returns 5
    Assert Flow component available == False
    Assert Flow component note contains "pipeline gap"

test_sentiment_composite_returns_503_when_breadth_data_missing
    Mock de_breadth_daily returns 0 rows
    Assert HTTPException with status_code=503 is raised
```

### Route-level tests (in `tests/routes/test_sectors_rrg.py` and `tests/routes/test_sentiment_route.py`)

```
test_sectors_rrg_route_returns_200
    Mock compute_sector_rrg
    GET /api/v1/sectors/rrg → 200, response has "sectors" and "meta"

test_sentiment_route_returns_200
    Mock compute_sentiment_composite
    GET /api/v1/sentiment/composite → 200, response has "composite_score" and "components"
```

**Total: 16 tests minimum across all test files.**

---

## Expected runtime

- `compute_days_in_regime`: single aggregation CTE on ~500-row table → < 5ms
- `compute_regime_history`: fetch 400 rows, O(n) Python RLE → < 10ms total
- `compute_sector_rrg`: 2 SQL queries (~31 sectors × 4 weeks = ~124 rows) → < 30ms
- `compute_sentiment_composite`: 4 queries (breadth, fo_summary count, flow count, fundamentals) → < 50ms total; de_fo_summary and de_flow_daily counts are O(1) metadata queries
- All endpoints target < 200ms on t3.large cold, < 100ms warm
