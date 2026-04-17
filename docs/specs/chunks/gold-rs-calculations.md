---
chunk_id: gold-rs-calculations
title: Gold Relative Strength — Backend Calculations
status: PLANNED
priority: HIGH
depends_on: []
touches: [backend/routes/, backend/services/, de_stock_daily, de_mf_nav_daily, de_etf_daily, de_index_daily]
estimated_effort: M (3–5 days)
created: 2026-04-17
---

# Gold RS Calculations — Backend Chunk Spec

## What this is

A cross-cutting enrichment that adds a **second RS axis (vs Gold)** to every quantitative signal in ATLAS. Gold RS acts as an **amplifier** on top of the primary benchmark RS — it signals whether the instrument is winning not just against its equity benchmark but against the universal store of value.

See `docs/design/design-principles.md §10 (The Gold RS amplifier)` for the full product rationale.

## Why it matters

If an instrument is positive on **both** its benchmark RS and Gold RS → High+ conviction (the "sure shot" state).
If positive on benchmark but negative on Gold → normal conviction (alpha without macro tailwind).
If negative on benchmark but positive on Gold → fragile strength (sector surviving only because real assets are falling).

This is a single calculation that materially improves signal quality and requires **no new tables** — it adds columns to existing tables and a shared service method.

---

## Data source for Gold price

| Universe | Gold series | Source |
|---|---|---|
| India (INR) | MCX Gold Futures continuous (1kg contract, INR/10g) | `de_macro_daily` — confirm column name with `\d de_macro_daily` |
| Global (USD) | LBMA Gold PM Fix (USD/troy oz) | `de_macro_daily` or `de_global_index_daily` — confirm |

**Pre-check required:** Run `SELECT column_name FROM information_schema.columns WHERE table_name = 'de_macro_daily' ORDER BY ordinal_position;` before writing migration to confirm exact gold column names. Do not assume — the JIP schema may store it as `mcx_gold_spot`, `gold_price_inr`, `gold_pm_fix_usd`, etc.

---

## Columns to add (schema changes via Alembic only — no raw DDL)

### On `atlas_stock_daily_technicals` (or equivalent ATLAS-owned table for stock RS)
```
rs_vs_gold_1m     Numeric(8,4)   -- return over 1M vs Gold (same currency)
rs_vs_gold_3m     Numeric(8,4)
rs_vs_gold_6m     Numeric(8,4)
rs_vs_gold_12m    Numeric(8,4)
gold_rs_signal    VARCHAR(20)    -- AMPLIFIES_BULL | AMPLIFIES_BEAR | NEUTRAL_BENCH_ONLY | FRAGILE
gold_rs_updated   TIMESTAMP WITH TIME ZONE
```

### On `atlas_mf_daily_derived` (ATLAS-owned MF signals table)
Same five columns. Gold comparison uses NAV returns vs Gold INR return over same period.

### On `atlas_etf_daily_signals` (ATLAS-owned ETF signals)
Same five columns.

### On `atlas_sector_daily_signals` (ATLAS-owned sector-level signals)
Same five columns. Sector return = index total return (already computed).

### On `atlas_index_global_signals` (global page — new table or extend existing)
```
rs_vs_msci_world  Numeric(8,4)
rs_vs_sp500       Numeric(8,4)
rs_vs_nifty50     Numeric(8,4)
rs_vs_gold_usd    Numeric(8,4)    -- USD gold for global/USD instruments
gold_rs_signal    VARCHAR(20)
```

> **Rule:** India instruments use Gold INR (MCX). Global/USD instruments use Gold USD (LBMA). The API response always labels which gold series was used via `gold_series: "MCX_INR" | "LBMA_USD"`.

---

## Calculation logic

```python
# Gold RS over period T (in days):
#
#   rs_vs_gold_T = instrument_return_T - gold_return_T
#
# Both returns are simple (log returns acceptable for research but simple for display).
#
# instrument_return_T = (price_today / price_T_ago) - 1
# gold_return_T       = (gold_today  / gold_T_ago)  - 1
# rs_vs_gold_T        = instrument_return_T - gold_return_T
#
# Uses Decimal arithmetic throughout. Never float.
# Null if gold price unavailable for the period.

def compute_gold_rs_signal(
    rs_benchmark: Decimal,   # existing benchmark RS (already computed)
    rs_gold:      Decimal,   # new gold RS
) -> str:
    """
    Determine Gold RS amplifier signal.
    Returns one of: AMPLIFIES_BULL | AMPLIFIES_BEAR | NEUTRAL_BENCH_ONLY | FRAGILE
    """
    bench_pos = rs_benchmark > Decimal("0")
    gold_pos  = rs_gold > Decimal("0")

    if bench_pos and gold_pos:
        return "AMPLIFIES_BULL"    # High+ conviction long
    elif not bench_pos and not gold_pos:
        return "AMPLIFIES_BEAR"    # High+ conviction short/avoid
    elif bench_pos and not gold_pos:
        return "NEUTRAL_BENCH_ONLY"  # Normal conviction, no macro tailwind
    else:
        return "FRAGILE"           # Surviving only because real assets falling — suspect
```

---

## Service layer

Add `GoldRSService` in `backend/services/gold_rs_service.py`:

```
class GoldRSService:
    async def get_gold_price_series(
        self,
        session: AsyncSession,
        start_date: date,
        end_date: date,
        currency: Literal["INR", "USD"] = "INR",
    ) -> dict[date, Decimal]:
        """Return {date: price} from de_macro_daily for the gold series."""

    async def compute_rs_vs_gold(
        self,
        price_series: dict[date, Decimal],  # instrument prices
        gold_series:  dict[date, Decimal],  # gold prices
        periods_days: list[int],            # [21, 63, 126, 252] for 1m/3m/6m/12m
    ) -> dict[str, Decimal | None]:
        """Returns {'rs_gold_1m': ..., 'rs_gold_3m': ..., ...}"""
```

This service is injected into the existing daily compute pipeline that already runs benchmark RS. It runs **after** benchmark RS is computed (data is available from the same session).

---

## API surface changes

### Existing endpoints that gain a `gold_rs` block

Every endpoint that returns RS data gains an additional `gold_rs` object with no breaking changes (additive only):

```json
{
  "symbol": "HDFCBANK",
  "rs_score": 4.2,
  "rs_momentum": 1.3,
  ...
  "gold_rs": {
    "rs_1m": -0.8,
    "rs_3m": 2.1,
    "rs_6m": 1.4,
    "rs_12m": 3.8,
    "signal": "NEUTRAL_BENCH_ONLY",
    "gold_series": "MCX_INR"
  }
}
```

Affected routes: `/api/instruments/{symbol}`, `/api/sectors/{key}`, `/api/compass/sectors`, `/api/compass/etfs`, `/api/recommendations/generate`, `/api/mf/{isin}`.

### Global page endpoints (new — no prior equivalent)

`GET /api/global/indices` — returns all global indices with 4-benchmark RS:
```json
{
  "index": "NIFTY_IT",
  "rs_vs_msci_world": -8.2,
  "rs_vs_sp500": -11.4,
  "rs_vs_nifty50": -13.4,
  "rs_vs_gold_usd": -5.1,
  "gold_rs_signal": "AMPLIFIES_BEAR",
  "four_bench_verdict": "AVOID"   // derived: if 3/4 rs < 0 → AVOID; 4/4 rs > 0 → STRONG_BUY; etc.
}
```

---

## Compute pipeline integration

Gold RS runs in the **daily batch** (same scheduler as benchmark RS). Order:

1. Fetch gold price for the day from `de_macro_daily`
2. For each instrument, fetch its price series for the trailing periods
3. Compute `rs_vs_gold_T` for each period
4. Set `gold_rs_signal`
5. Upsert into the ATLAS-owned derived table
6. Invalidate API cache for affected symbols

**Null handling:** If gold price is unavailable for a specific date, `rs_vs_gold_T = NULL` for that period. The API still returns the object but with `null` values and a `"data_gap": true` flag. Never substitute 0.

**Stale check:** If gold price for today is missing and yesterday's price is more than 2 calendar days old, set `gold_rs_signal = "STALE"` and surface a staleness warning in the API.

---

## Tests required (TDD first)

1. `test_compute_gold_rs_basic` — correct RS over a known price series
2. `test_gold_rs_signal_four_states` — all four signal states computed correctly
3. `test_gold_rs_null_on_missing_price` — null returned, not 0 or NaN
4. `test_gold_rs_stale_flag` — stale flag set when gold price &gt;2 days old
5. `test_api_sector_includes_gold_rs` — sector endpoint returns gold_rs block
6. `test_api_global_four_benchmark_rs` — global indices endpoint returns all 4 benchmarks

---

## QA gate (before chunk is DONE)

- [ ] `scripts/check-api-standard.py` passes (§17/§18/§20 compliance)
- [ ] `pytest tests/ -v --tb=short` green including all 6 Gold RS tests
- [ ] All new money columns are `Numeric(20,4)` — no Float anywhere
- [ ] `ruff check . --select E,F,W` clean
- [ ] API responses include `data_as_of` and `staleness_indicator` (§18 of spec)
- [ ] At least one instrument with `AMPLIFIES_BULL` signal visible in staging (sanity check)
- [ ] Breadth and Sector Compass endpoints return `gold_rs` block without breaking existing clients

---

## Not in scope for this chunk

- Front-end rendering (mockups already designed; React implementation is a separate UI chunk)
- Backtesting gold RS signals (Lab / simulation scope)
- Global country-level gold comparisons beyond the index level (will be extended when global page is built)
