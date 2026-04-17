# C-DER-3: Sector RRG + Sentiment Composite + Regime Enrichment

**Slice:** V6.5 — Derived Signal Engine
**Depends on:** C-DER-1, C-DER-2 (derived signal engine complete), V6-1..V6-9 (existing routes stable)
**Blocks:** Frontend pulse-sectors RRG page, pulse-sentiment page, pulse-breadth signal history table
**Complexity:** L (8–10 hours)
**Quality targets:** code: 82, security: 90, architecture: 85, api: 90

---

## ⛔ NON-NEGOTIABLE — READ FIRST

This chunk is **REJECTED** if the DONE commit does not contain **all** of
these files at or above the stated size floor. A bare `.forge/baseline/*`
bump or any commit that does not materially land the deliverables below is
a false-DONE and will be flipped back to PENDING on audit.

```
PRESENT, net-new:
  backend/services/regime_service.py            ≥ 120 lines
  backend/services/rrg_service.py               ≥ 170 lines
  backend/services/sentiment_service.py         ≥ 220 lines
  backend/routes/sectors.py                     ≥ 30 lines
  backend/routes/sentiment.py                   ≥ 25 lines
  tests/services/test_regime_service.py         ≥ 120 lines, ≥ 4 tests
  tests/services/test_rrg_service.py            ≥ 180 lines, ≥ 7 tests
  tests/services/test_sentiment_service.py      ≥ 220 lines, ≥ 8 tests
  tests/routes/test_sectors_rrg.py              ≥ 50 lines,  ≥ 2 tests
  tests/routes/test_sentiment_route.py          ≥ 50 lines,  ≥ 2 tests

MODIFIED, additive only:
  backend/models/schemas.py                     ≥ 70 lines added
                                                (RegimeTransition + SentimentZone
                                                + SentimentComponent + SentimentResponse
                                                + RRGPoint + RRGSector + RRGResponse
                                                + 2 new fields on RegimeSnapshot)
  backend/routes/stocks.py                      ≥ 15 lines added
                                                (regime gather in get_breadth)
  backend/main.py                               ≥ 4 lines added
                                                (imports + include_router × 2)
```

**Self-check loop (run before stamping DONE):**

```bash
for f in backend/services/regime_service.py \
         backend/services/rrg_service.py \
         backend/services/sentiment_service.py \
         backend/routes/sectors.py \
         backend/routes/sentiment.py \
         tests/services/test_regime_service.py \
         tests/services/test_rrg_service.py \
         tests/services/test_sentiment_service.py \
         tests/routes/test_sectors_rrg.py \
         tests/routes/test_sentiment_route.py; do
  test -f "$f" || { echo "MISSING: $f"; exit 1; }
  wc -l "$f"
done
grep -c "^class RegimeTransition\|^class SentimentZone\|^class SentimentComponent\|^class SentimentResponse\|^class RRGPoint\|^class RRGSector\|^class RRGResponse" backend/models/schemas.py
grep -n "compute_days_in_regime\|compute_regime_history" backend/routes/stocks.py
grep -c "sectors\.router\|sentiment\.router" backend/main.py
pytest tests/services/test_regime_service.py \
       tests/services/test_rrg_service.py \
       tests/services/test_sentiment_service.py \
       tests/routes/test_sectors_rrg.py \
       tests/routes/test_sentiment_route.py -v
curl -s http://localhost:8000/api/v1/sectors/rrg | jq '.sectors | length'
curl -s http://localhost:8000/api/v1/sentiment/composite | jq '.composite_score, .zone, .weight_redistribution_active'
```

If any line fails → **DO NOT** stamp DONE.

---

## Goal

Three new capabilities delivered as one chunk:

**Part A — Regime Enrichment:** Add `days_in_regime` (int, consecutive days
in current regime) and `regime_history` (last 5 regime transitions) to the
existing `RegimeSnapshot` / `MarketBreadthResponse`. Pure SQL + Python RLE,
no new table.

**Part B — Sector RRG endpoint:** `GET /api/v1/sectors/rrg` returns
normalised RS score (100-centred), RS momentum, RRG quadrant, and a 4-point
weekly trail for every sector.

**Part C — Sentiment Composite endpoint:** `GET /api/v1/sentiment/composite`
returns a 0–100 composite sentiment score built from 4 components: Price
Breadth, Options/PCR, Institutional Flow, Fundamental Revisions. Components
with unavailable data (`de_fo_summary` = 0 rows verified, `de_flow_daily` ≈
5 rows verified) are marked `available=False` and their weights are
redistributed to available components.

---

## Schema reality (verified against live RDS, 2026-04-17)

- `de_market_regime` ≈ 4,396 rows; columns include `date, regime`.
- `de_rs_scores` for `entity_type='sector'`: `entity_id` = sector name (string), `date`, `rs_composite`, `rs_momentum`.
- `de_sector_breadth_daily` ≈ 127,584 rows; `sector, date, pct_above_50dma, breadth_regime`.
- `de_fo_summary`: **0 rows** — PCR pipeline is dead. Component must mark unavailable.
- `de_flow_daily`: **5 rows** — Flow pipeline is dead. Component must mark unavailable.
- `de_breadth_daily`: has `pct_above_200dma, pct_above_50dma, ad_ratio, mcclellan_oscillator, mcclellan_summation, new_52w_highs, new_52w_lows, advance, decline, unchanged`.
- `de_equity_fundamentals` has `revenue_growth_yoy_pct, profit_growth_yoy_pct, pe_ratio`.

---

## Files

### New
- `backend/routes/sectors.py` — `GET /api/v1/sectors/rrg` route
- `backend/routes/sentiment.py` — `GET /api/v1/sentiment/composite` route
- `backend/services/regime_service.py` — `compute_days_in_regime()`, `compute_regime_history()`
- `backend/services/rrg_service.py` — `compute_sector_rrg()`
- `backend/services/sentiment_service.py` — `compute_sentiment_composite()`
- `tests/services/test_regime_service.py` — ≥4 tests
- `tests/services/test_rrg_service.py` — ≥7 tests
- `tests/services/test_sentiment_service.py` — ≥8 tests
- `tests/routes/test_sectors_rrg.py` — ≥2 tests
- `tests/routes/test_sentiment_route.py` — ≥2 tests

### Modified
- `backend/models/schemas.py` — add the 7 new models; extend `RegimeSnapshot`
- `backend/routes/stocks.py` — call `compute_days_in_regime()` and `compute_regime_history()` inside `get_breadth` via `asyncio.gather` with isolated sessions
- `backend/main.py` — register `sectors.router` and `sentiment.router`

---

## Contracts

### New Pydantic models (add to `backend/models/schemas.py`)

```python
class RegimeTransition(BaseModel):
    regime: str
    started_date: date
    ended_date: Optional[date] = None          # None = current regime
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
    score: Optional[Decimal] = None            # 0–100, None when unavailable
    weight: Decimal                            # effective weight after redistribution
    available: bool = True
    note: Optional[str] = None


class SentimentResponse(BaseModel):
    composite_score: Optional[Decimal] = None  # 0–100 weighted average
    zone: Optional[SentimentZone] = None
    components: list[SentimentComponent]
    weight_redistribution_active: bool = False
    as_of: Optional[date] = None
    meta: ResponseMeta


class RRGPoint(BaseModel):
    date: date
    rs_score: Decimal                          # normalised, 100-centred
    rs_momentum: Decimal


class RRGSector(BaseModel):
    sector: str
    rs_score: Decimal                          # (rs_raw - mean) / stddev * 10 + 100
    rs_momentum: Decimal                       # rs_composite_today - rs_composite_28d_ago
    quadrant: Quadrant                         # existing enum
    pct_above_50dma: Optional[Decimal] = None
    breadth_regime: Optional[str] = None
    tail: list[RRGPoint] = []                  # up to 4 weekly points


class RRGResponse(BaseModel):
    sectors: list[RRGSector]
    mean_rs: Decimal
    stddev_rs: Decimal
    as_of: date
    meta: ResponseMeta
```

### Modified `RegimeSnapshot`

```python
days_in_regime: Optional[int] = None
regime_history: list[RegimeTransition] = []    # last 5 completed transitions
```

Additive only; existing clients keep working.

---

## Implementation notes

### Part A — `backend/services/regime_service.py`

#### `async def compute_days_in_regime(db: AsyncSession) -> Optional[int]`

Count consecutive days in the current regime, inclusive of today.

```sql
WITH regime_today AS (
    SELECT regime FROM de_market_regime
    ORDER BY date DESC LIMIT 1
),
first_break AS (
    SELECT date AS break_date FROM de_market_regime
    WHERE regime != (SELECT regime FROM regime_today)
    ORDER BY date DESC LIMIT 1
)
SELECT COUNT(*) AS days_in_regime
FROM de_market_regime
WHERE regime = (SELECT regime FROM regime_today)
  AND date > COALESCE((SELECT break_date FROM first_break), '2000-01-01'::date)
```

Empty table → `None`. Otherwise int.

#### `async def compute_regime_history(db: AsyncSession) -> list[RegimeTransition]`

Fetch 400 most-recent rows and run Python RLE (rows ordered DESC):

```sql
SELECT date, regime
FROM de_market_regime
ORDER BY date DESC
LIMIT 400
```

```python
if not rows:
    return []
transitions: list[RegimeTransition] = []
current_regime = rows[0]["regime"]
current_end = rows[0]["date"]  # most recent date for this regime (current end)

for row in rows[1:]:
    if row["regime"] != current_regime:
        # 'row' is the last day of the PREVIOUS regime; the boundary
        # between previous and current is row["date"] + 1 day.
        started_date = row["date"] + timedelta(days=1) if current_regime is not None else row["date"]
        duration = (current_end - started_date).days + 1
        transitions.append(RegimeTransition(
            regime=current_regime,
            started_date=started_date,
            ended_date=current_end,
            duration_days=max(duration, 1),
            breadth_pct_at_start=None,
        ))
        current_regime = row["regime"]
        current_end = row["date"]

# transitions[0] represents the current-regime segment (still open); return
# the completed ones that follow it, up to 5.
return transitions[1:6]
```

> The current regime (still-open) is **not** in `regime_history` — that
> open segment is represented by `days_in_regime` instead. The history is
> strictly the last 5 completed regimes.

**Wiring into `get_breadth`** in `backend/routes/stocks.py`:

```python
from backend.services.regime_service import (
    compute_days_in_regime, compute_regime_history,
)
from backend.db.session import async_session_factory

async def _days_task():
    async with async_session_factory() as s:
        return await compute_days_in_regime(s)

async def _history_task():
    async with async_session_factory() as s:
        return await compute_regime_history(s)

days_result, history_result = await asyncio.gather(
    _days_task(), _history_task(), return_exceptions=True,
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

**Step 1 — fetch today + lag rows + stats + breadth:**

```sql
WITH latest_sector_date AS (
    SELECT MAX(date) AS d
    FROM de_rs_scores WHERE entity_type = 'sector'
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
    SELECT AVG(rs_composite) AS mean_rs, STDDEV_SAMP(rs_composite) AS stddev_rs
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

If `rows` is empty → `raise HTTPException(status_code=503, detail="Sector RS data not available")`.

**Step 2 — normalise in Python:**

```python
mean_rs = Decimal(str(rows[0]["mean_rs"])) if rows[0]["mean_rs"] is not None else Decimal("100")
stddev_raw = rows[0]["stddev_rs"]
stddev_rs = Decimal(str(stddev_raw)) if stddev_raw is not None else Decimal("1")
if stddev_rs == Decimal("0"):
    stddev_rs = Decimal("1")   # guard: all sectors identical

for row in rows:
    rs_raw = Decimal(str(row["rs_composite"]))
    rs_score = (rs_raw - mean_rs) / stddev_rs * Decimal("10") + Decimal("100")
    rs_momentum = Decimal(str(row["raw_momentum"]))
```

**Step 3 — quadrant (inline, do NOT reuse existing `compute_quadrant` — that one compares against 0, this one compares against 100):**

```python
def _rrg_quadrant(rs_score: Decimal, rs_momentum: Decimal) -> Quadrant:
    if rs_score >= Decimal("100") and rs_momentum >= Decimal("0"):
        return Quadrant.LEADING
    if rs_score < Decimal("100") and rs_momentum >= Decimal("0"):
        return Quadrant.IMPROVING
    if rs_score >= Decimal("100") and rs_momentum < Decimal("0"):
        return Quadrant.WEAKENING
    return Quadrant.LAGGING
```

**Step 4 — tail (4 weekly points):** fetch rs_composite for (today, -7d,
-14d, -21d) across all sectors in one query; group in Python; normalise
using today's mean/stddev. For each tail point, `rs_momentum` = diff from
the next-older tail point (oldest tail point gets momentum = 0).

```sql
WITH target_dates AS (
    SELECT DISTINCT r.date
    FROM de_rs_scores r
    WHERE r.entity_type = 'sector'
      AND r.date IN (
          (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector'),
          (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector' AND date <= (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector') - INTERVAL '7 days'),
          (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector' AND date <= (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector') - INTERVAL '14 days'),
          (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector' AND date <= (SELECT MAX(date) FROM de_rs_scores WHERE entity_type='sector') - INTERVAL '21 days')
      )
)
SELECT entity_id AS sector, date, rs_composite
FROM de_rs_scores
WHERE entity_type = 'sector'
  AND date IN (SELECT date FROM target_dates)
ORDER BY entity_id, date DESC
```

~31 sectors × 4 dates ≈ 124 rows. Skip a tail point if data missing (<4
points is valid).

**Step 5 — build response:**

```python
return RRGResponse(
    sectors=rrg_sectors,
    mean_rs=mean_rs,
    stddev_rs=stddev_rs,
    as_of=rows[0]["as_of"],
    meta=ResponseMeta(record_count=len(rrg_sectors), query_ms=elapsed_ms),
)
```

### `backend/routes/sectors.py`

```python
from fastapi import APIRouter, Depends, Query
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

No collision with `GET /api/v1/stocks/sectors` — different prefix.

### Part C — `backend/services/sentiment_service.py`

#### `async def compute_sentiment_composite(db: AsyncSession) -> SentimentResponse`

**Component 1 — Price Breadth (base weight 0.4):**

```sql
SELECT
    pct_above_200dma, pct_above_50dma, ad_ratio,
    mcclellan_oscillator, mcclellan_summation,
    new_52w_highs, new_52w_lows,
    advance + decline + COALESCE(unchanged, 0) AS total_stocks,
    date
FROM de_breadth_daily
ORDER BY date DESC
LIMIT 1
```

Empty → `raise HTTPException(status_code=503, detail="Breadth data not available")`. Breadth is the **only** hard-fail; all other components degrade gracefully.

Sub-metric normalisation to 0–100:

```python
def _norm_breadth(row) -> Optional[Decimal]:
    scores: list[Decimal] = []
    if row["pct_above_200dma"] is not None:
        scores.append(Decimal(str(row["pct_above_200dma"])))
    if row["pct_above_50dma"] is not None:
        scores.append(Decimal(str(row["pct_above_50dma"])))
    if row["ad_ratio"] is not None:
        raw = Decimal(str(row["ad_ratio"])) * Decimal("50")
        scores.append(max(Decimal("0"), min(Decimal("100"), raw)))
    if row["mcclellan_oscillator"] is not None:
        raw = (Decimal(str(row["mcclellan_oscillator"])) + Decimal("150")) / Decimal("3")
        scores.append(max(Decimal("0"), min(Decimal("100"), raw)))
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

**Component 2 — Options/PCR (base weight 0.2):**

```sql
SELECT COUNT(*) AS row_count FROM de_fo_summary
```

Currently returns `0`. Set `score=None, available=False, note="PCR data unavailable — pipeline gap"`.

Future (when populated): PCR formula — if `pcr_oi < 0.7` → score = `70 + (0.7 - pcr_oi) / 0.7 * 30` (greed); `0.7..1.2` → 50 (neutral); `>1.5` → 20 (extreme fear); interpolate between.

**Component 3 — Institutional Flow (base weight 0.2):**

```sql
SELECT COUNT(*) AS row_count FROM de_flow_daily WHERE category = 'FII'
```

`row_count <= 5` → `score=None, available=False, note="FII flow data unavailable — pipeline gap"`.

**Component 4 — Fundamental Revisions (base weight 0.2):**

```sql
SELECT
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY revenue_growth_yoy_pct) AS median_rev_growth,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY profit_growth_yoy_pct) AS median_profit_growth,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pe_ratio) AS median_pe
FROM de_equity_fundamentals f
JOIN de_instrument i ON i.id = f.instrument_id
WHERE i.is_active = true AND i.nifty_500 = true
```

All NULL → `available=False, note="Fundamentals data unavailable"`. Otherwise:

```python
scores: list[Decimal] = []
if median_rev_growth is not None:
    raw = max(Decimal("0"), min(Decimal("30"), Decimal(str(median_rev_growth))))
    scores.append(raw / Decimal("30") * Decimal("100"))
if median_profit_growth is not None:
    raw = max(Decimal("0"), min(Decimal("30"), Decimal(str(median_profit_growth))))
    scores.append(raw / Decimal("30") * Decimal("100"))
if median_pe is not None:
    pe_score = max(Decimal("0"), min(Decimal("100"),
        (Decimal(str(median_pe)) - Decimal("10")) / Decimal("30") * Decimal("100")
    ))
    scores.append(pe_score)
fund_score = sum(scores, Decimal("0")) / Decimal(str(len(scores))) if scores else None
```

**Weight redistribution (locked, exhaustive):**

| pcr avail | flow avail | breadth | pcr | flow | fund | redistribution_active |
|-----------|------------|---------|-----|------|------|------------------------|
| ✓ | ✓ | 0.4 | 0.2 | 0.2 | 0.2 | False |
| ✓ | ✗ | 0.5 | 0.2 | 0.0 | 0.3 | True |
| ✗ | ✓ | 0.5 | 0.0 | 0.2 | 0.3 | True |
| ✗ | ✗ | 0.6 | 0.0 | 0.0 | 0.4 | True |

If `fund_score` itself is None, the composite is computed from the
remaining available components — weights are re-normalised only across
components with `available=True AND score is not None`:

```python
numerator = Decimal("0"); denominator = Decimal("0")
for score, weight in [(breadth_score, breadth_weight), (pcr_score, pcr_weight),
                      (flow_score, flow_weight), (fund_score, fund_weight)]:
    if score is not None and weight > Decimal("0"):
        numerator += score * weight
        denominator += weight
composite = (numerator / denominator) if denominator > Decimal("0") else None
```

**Zone thresholds:**

```python
def _zone(score: Optional[Decimal]) -> Optional[SentimentZone]:
    if score is None: return None
    if score < Decimal("20"):  return SentimentZone.EXTREME_FEAR
    if score < Decimal("40"):  return SentimentZone.FEAR
    if score < Decimal("60"):  return SentimentZone.NEUTRAL
    if score < Decimal("80"):  return SentimentZone.GREED
    return SentimentZone.EXTREME_GREED
```

### `backend/routes/sentiment.py`

```python
from fastapi import APIRouter, Depends
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

### Edge cases

| Scenario | Behaviour |
|---|---|
| de_market_regime empty | days_in_regime None; regime_history [] |
| Regime never changed | days_in_regime = count of all rows; regime_history [] |
| stddev_rs = 0 (all sectors identical) | stddev_rs set to 1; no ZeroDivisionError |
| Sector has no lag row | rs_composite_lag = rs_composite_today; raw_momentum = 0 |
| de_fo_summary = 0 rows | PCR unavailable, note mentions "pipeline gap" |
| de_flow_daily ≤ 5 rows | Flow unavailable, note mentions "pipeline gap" |
| de_breadth_daily = 0 rows | 503 from sentiment endpoint |
| Fundamentals all NULL | Component 4 unavailable |
| Both PCR + Flow unavailable | weight_redistribution_active=True, breadth=0.6, fund=0.4 |
| Tail <4 points | Return as many as available |

---

## Points of success (17, all required for DONE)

1. `backend/services/regime_service.py`, `rrg_service.py`, `sentiment_service.py` all exist at stated line floors.
2. `backend/routes/sectors.py`, `backend/routes/sentiment.py` exist and are registered in `main.py`.
3. `backend/models/schemas.py` defines all 7 new models and extends `RegimeSnapshot` with `days_in_regime` + `regime_history`.
4. `GET /api/v1/stocks/breadth` response contains `regime.days_in_regime` (int ≥ 1) and `regime.regime_history` (list up to 5 items).
5. Every `RegimeTransition` in `regime_history` has non-None `regime`, `started_date`, `ended_date`, `duration_days ≥ 1`.
6. `GET /api/v1/sectors/rrg` → 200 with `sectors`, `mean_rs`, `stddev_rs`, `as_of`, `meta`.
7. Every `rs_score` is normalised around 100 — assert that abs(mean of returned `rs_score` values − 100) ≤ 1 (small tolerance for rounding; raw rs_composite values from DB would be far outside that range).
8. Quadrant classification correct: rs_score ≥ 100 & momentum ≥ 0 → LEADING; < 100 & ≥ 0 → IMPROVING; ≥ 100 & < 0 → WEAKENING; < 100 & < 0 → LAGGING. 4 tests, one per quadrant.
9. stddev_rs=0 guard: all sectors identical does not raise; response valid; stddev_rs returned as Decimal("1").
10. `GET /api/v1/sentiment/composite` → 200 with `composite_score`, `zone`, `components` (length 4), `weight_redistribution_active`, `as_of`.
11. **Semantic sentinel — PCR unavailable:** with real DB state (`de_fo_summary`=0 rows), PCR component has `available=False`, `note` contains "pipeline gap", `weight=Decimal("0")`.
12. **Semantic sentinel — Flow unavailable:** with real DB state (`de_flow_daily`=5), Flow component has `available=False`, `note` contains "pipeline gap", `weight=Decimal("0")`.
13. **Semantic sentinel — weight redistribution:** both PCR & Flow unavailable → `weight_redistribution_active=True`, breadth weight = `Decimal("0.6")`, fundamentals weight = `Decimal("0.4")`. Exhaustive truth table has one test per row (4 rows → 4 tests).
14. Sentiment zones: score values 10/30/50/70/90 → EXTREME_FEAR/FEAR/NEUTRAL/GREED/EXTREME_GREED. Boundary tests at 19.99 vs 20.00, 39.99 vs 40.00, 79.99 vs 80.00.
15. `de_breadth_daily` empty → sentiment endpoint 503, not 500, not 200-with-null.
16. No collision: `GET /api/v1/stocks/sectors` (existing list route) still 200 after adding `GET /api/v1/sectors/rrg`. Non-regression test in `test_sectors_rrg.py`.
17. Quality gate: `ruff check` clean, `mypy backend/services/*.py --ignore-missing-imports` clean, ≥16 service-level + ≥4 route-level tests pass, full `pytest tests/ -v` does not regress.

---

## Tests

### `tests/services/test_regime_service.py` (≥4 tests, ≥120 lines)

1. `test_days_in_regime_counts_consecutive_same_regime` — 10 BULL rows → 10.
2. `test_days_in_regime_resets_on_regime_change` — 5 BULL then 1 BEAR at break → 5.
3. `test_regime_history_returns_last_5_transitions` — 3+ transitions mocked → ≤5 items, ordered most-recent-first, each with positive `duration_days`.
4. `test_days_in_regime_returns_none_when_table_empty` — 0 rows → None; history → [].

### `tests/services/test_rrg_service.py` (≥7 tests, ≥180 lines)

1. `test_rrg_quadrant_leading` — rs_score=105, mom=2.0 → LEADING.
2. `test_rrg_quadrant_lagging` — rs_score=95, mom=-1.5 → LAGGING.
3. `test_rrg_quadrant_improving` — rs_score=97, mom=1.0 → IMPROVING.
4. `test_rrg_quadrant_weakening` — rs_score=103, mom=-0.5 → WEAKENING.
5. `test_rrg_normalize_centers_at_100` — mock 3 sectors rs_composite=95, 100, 105, stddev_samp ≈ 5 → middle ≈ 100, outer ≈ 100 ± 10.
6. `test_rrg_stddev_zero_guard` — all sectors identical rs_composite=100 → no ZeroDivisionError, stddev used = 1.
7. `test_rrg_tail_returns_up_to_4_weekly_points` — mock 4 weekly rows for a sector → `RRGSector.tail` has 4 `RRGPoint`s; each `rs_score` normalised.
8. `test_rrg_503_when_no_sector_rs` — mock 0 today_rs rows → `HTTPException` status_code=503.

### `tests/services/test_sentiment_service.py` (≥8 tests, ≥220 lines)

1. `test_sentiment_composite_redistributes_weight_when_pcr_and_flow_empty` — **semantic sentinel.** fo_summary=0, flow_daily=5 → `weight_redistribution_active=True`, breadth weight=`Decimal("0.6")`, fund weight=`Decimal("0.4")`.
2. `test_sentiment_pcr_only_unavailable` — fo_summary=0, flow populated → breadth=0.5, flow=0.2, fund=0.3, pcr=0.
3. `test_sentiment_flow_only_unavailable` — flow_daily<=5, pcr populated → breadth=0.5, pcr=0.2, fund=0.3, flow=0.
4. `test_sentiment_all_available_baseline_weights` — all four available → 0.4/0.2/0.2/0.2, redistribution_active=False.
5. `test_sentiment_breadth_score_normalizes_sub_metrics` — mock pct_above_200dma=80, pct_above_50dma=75, ad_ratio=1.5, mcclellan=30, highs=40, lows=10 → breadth score in [50,100], not None.
6. `test_sentiment_zone_boundaries` — scores 10/30/50/70/90 → EXTREME_FEAR/FEAR/NEUTRAL/GREED/EXTREME_GREED; 19.99→EXTREME_FEAR, 20.00→FEAR; 79.99→GREED, 80.00→EXTREME_GREED.
7. `test_sentiment_marks_pcr_unavailable_note_pipeline_gap` — fo_summary count=0 → PCR.available=False, note contains "pipeline gap".
8. `test_sentiment_marks_flow_unavailable_note_pipeline_gap` — flow_daily count=5 → Flow.available=False, note contains "pipeline gap".
9. `test_sentiment_503_when_breadth_missing` — de_breadth_daily empty → HTTPException status_code=503.

### `tests/routes/test_sectors_rrg.py` (≥2 tests, ≥50 lines)

1. `test_sectors_rrg_route_200` — mock `compute_sector_rrg` → GET /api/v1/sectors/rrg → 200; response has `sectors`, `mean_rs`, `stddev_rs`, `as_of`, `meta`.
2. `test_existing_stocks_sectors_route_still_works` — GET /api/v1/stocks/sectors → 200 (non-regression — prove the new sectors router does not shadow the older list route).

### `tests/routes/test_sentiment_route.py` (≥2 tests, ≥50 lines)

1. `test_sentiment_route_200` — mock `compute_sentiment_composite` → GET /api/v1/sentiment/composite → 200; response has `composite_score`, `zone`, `components`, `weight_redistribution_active`.
2. `test_sentiment_route_503_when_breadth_missing` — mock compute to raise HTTPException(503) → route propagates 503.

### Non-regression appended to `tests/routes/test_stock_derived_signals.py`

Add one test `test_breadth_response_includes_regime_enrichment` — GET /api/v1/stocks/breadth returns regime with `days_in_regime` int and `regime_history` list. Also assert the pre-C-DER-3 keys (existing breadth fields) still present.

---

## Live smoke (required at DONE)

```bash
curl -s https://atlas.jslwealth.in/api/v1/stocks/breadth \
  | jq '{regime: .regime.regime,
         days: .regime.days_in_regime,
         history_len: (.regime.regime_history | length)}'

curl -s "https://atlas.jslwealth.in/api/v1/sectors/rrg" \
  | jq '{count: (.sectors | length),
         mean: .mean_rs, stddev: .stddev_rs,
         sample: .sectors[0]}'

curl -s "https://atlas.jslwealth.in/api/v1/sentiment/composite" \
  | jq '{score: .composite_score,
         zone: .zone,
         redistribution: .weight_redistribution_active,
         components: (.components | map({name, available, weight}))}'
```

Expected:
- breadth: `days ≥ 1`, `history_len ≤ 5`, each transition has dates + positive duration.
- rrg: `count ≈ 20–31` sectors; `mean` ≈ 100 of raw composite; every sample has `rs_score`, `rs_momentum`, `quadrant`, `tail`.
- sentiment: `score` 0–100 or null; `zone` matches bin; `components` length 4; PCR + Flow both `available=false` with current DB state; `redistribution: true`.

Paste output into `docs/decisions/session-log.md` under the C-DER-3 entry.

---

## Expected runtime

- `compute_days_in_regime`: single aggregation CTE on ~4,400-row table → < 10ms
- `compute_regime_history`: fetch 400 rows, O(n) Python RLE → < 10ms total
- `compute_sector_rrg`: 2 SQL queries (~124 rows total) → < 30ms
- `compute_sentiment_composite`: 4 queries — breadth, fo_summary count, flow count, fundamentals medians → < 50ms
- All endpoints < 200ms cold, < 100ms warm.

---

## Post-chunk sync invariant

`scripts/post-chunk.sh C-DER-3` MUST green: commit+push, service restart,
smoke probe, /forge-compile, MEMORY.md append. All 5 must pass. Otherwise
chunk is not DONE.
