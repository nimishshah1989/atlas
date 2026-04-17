---
chunk: C-DER-2
project: atlas
date: 2026-04-17
status: in-progress
---

# C-DER-2 Approach: 4-Factor Conviction Engine + Action + Urgency + Screener

## Data Scale
- de_equity_technical_daily: large table, uses window functions (percent_rank) server-side
- de_rs_scores: large table, filtered by entity_type + vs_benchmark + date
- de_instrument: ~2000 rows, active stocks
- All aggregation done in SQL CTEs — never pandas or Python loops

## Chosen Approach

### Model split pattern (same as C-DER-1)
- `backend/models/conviction.py` — 5 new models: ConvictionLevel, ActionSignal, UrgencyLevel, FourFactorConviction, ScreenerRow
- NO import of ResponseMeta or schemas.py in conviction.py (avoids circular import)
- ScreenerResponse defined locally in `backend/routes/screener.py`
- `backend/models/schemas.py` re-exports via late import block after line 235

### SQL Strategy
- compute_four_factor: single SQL round-trip via CTE (no 4 separate queries)
- compute_screener_bulk: window function percent_rank() in PostgreSQL, not Python
- Universe filter via whitelist dict (SQL injection prevention)
- Sector filter as bind param (never string-interpolated)

### Conviction Logic (pure Python, no DB)
- 4 factors evaluated: returns_rs, momentum_rs, sector_rs, volume_rs
- factors_aligned count determines ConvictionLevel (0→AVOID, 1→LOW, 2→MEDIUM, 3→HIGH, 4→HIGH+)
- Action derived from conviction + regime
- Urgency derived from conviction + roc_5 + roc_21

### Session Isolation
- Parallel gather tasks use async_session_factory() context managers (Isolated-Session pattern)
- four_factor runs in its own isolated session like gold_rs and piotroski

## Wiki Patterns Checked
- [Isolated-Session Parallel Gather](patterns/isolated-session-parallel-gather.md) — asyncpg can't multiplex
- [SQL Window Computation](patterns/sql-window-computation.md) — percent_rank() server-side
- [Zero-Value Truthiness Trap](bug-patterns/zero-value-truthiness-trap.md) — use `is not None`
- [Decimal Not Float](patterns/decimal-not-float.md) — all financial values Decimal
- [FastAPI Static Route Before Path Param](bug-patterns/fastapi-static-route-before-path-param.md)

## Existing Code Reused
- `backend/models/derived.py` — same split pattern applied to conviction.py
- `backend/services/derived_signals.py` — same isolated-session gather pattern
- `backend/clients/jip_data_service.py` — already has get_market_regime(), reuse JIPDataService

## Edge Cases
- NULL rs_composite → factor_returns_rs = False (is not None guard)
- NULL sector → sector_filter not applied, sector_rs_composite = NULL → factor_sector_rs = False
- NULL cmf_20 or mfi_14 → factor_volume_rs = False (both required)
- NULL roc_5 → urgency falls to PATIENT
- No tech row for instrument → compute_four_factor returns None
- compute_screener_bulk post-SQL Python filter for conviction/action (can't filter in SQL without subquery)

## Expected Runtime
- compute_four_factor: ~20-50ms (single CTE, index on instrument_id + date)
- compute_screener_bulk: ~200-500ms cold, ~50-100ms warm (aggregation over large tables)
- Screener route adds ~30ms for JIPMarketService.get_market_regime()
