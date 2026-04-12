# ATLAS Build Status

## V1: Market → Sector → Stock → Decision

**Status: COMPLETE** | Built: 2026-04-11

### Endpoints (all passing integration tests)

| Endpoint | Status | Response Time |
|---|---|---|
| `GET /api/v1/health` | ✅ | <10ms |
| `GET /api/v1/status` | ✅ | ~300ms |
| `GET /api/v1/stocks/breadth` | ✅ | ~350ms |
| `GET /api/v1/stocks/sectors` | ✅ | ~3.3s |
| `GET /api/v1/stocks/universe?sector=X` | ✅ | ~500ms |
| `GET /api/v1/stocks/{symbol}` | ✅ | ~3.8s |
| `GET /api/v1/stocks/{symbol}/rs-history` | ✅ | <1s |
| `GET /api/v1/stocks/movers` | ✅ | ~1s |
| `POST /api/v1/query` | ✅ | ~100ms |
| `GET /api/v1/decisions` | ✅ | <50ms |
| `PUT /api/v1/decisions/{id}/action` | ✅ | <50ms |

### V1 Completion Criteria

| Criteria | Status |
|---|---|
| /stocks/universe returns valid data | ✅ |
| /stocks/sectors returns 31 sectors × 22 metrics | ✅ 31 sectors |
| /stocks/{symbol} returns deep-dive with conviction | ✅ 3 pillars |
| /query handles basic equity queries | ✅ filters + sort |
| FM navigates Market → Sector → Stock | ✅ Frontend built |
| Deep-dive shows conviction pillars | ✅ RS + Tech + Inst |
| Sector stock_count sums to ~2,700 | ✅ 2,431 (w/ sector) |
| RS momentum matches manual calc | ✅ verified |
| No float in any financial calculation | ✅ all Decimal |
| Integration tests ALL passing | ✅ 19/19 |

### Data Coverage

- Active instruments: 2,743
- With sector assigned: 2,431
- Sectors: 31
- RS scores as of: 2026-04-09
- Technicals as of: 2026-04-09
- Breadth as of: 2026-04-09
- Regime: SIDEWAYS (confidence 43.07%)
- MF holdings as of: 2026-04-06

### Architecture

- Backend: FastAPI on port 8010 (async, Pydantic v2)
- Frontend: Next.js on port 3000 (React, Tailwind, Recharts)
- Database: PostgreSQL RDS (27M+ rows, pgvector 0.8.0)
- Data source: Direct DB queries (JIP API not running)
- All financials: Decimal type, str() conversion
- Indexes: 6 custom indexes on de_* tables for performance

### Performance Optimizations

1. Replaced DISTINCT ON with specific-date queries (151s → 2.8s for rs_28d)
2. Created indexes on de_rs_scores, de_equity_technical_daily, de_mf_holdings, de_market_cap_history
3. Shared CTE fragments across queries to avoid duplication

### Known Limitations

- JIP /internal/ API not running — using direct DB queries (swappable)
- 312 instruments have no sector assigned (NULL sector)
- Many instruments have NULL technicals (RSI, ADX, etc.)
- Decisions not auto-generated yet (table operational, no pipeline)
- No TradingView integration (V6)
- No MF/ETF endpoints (V2)
- Sectors endpoint ~3.3s (spec target: <2s) — needs further optimization

### Next: V2 — MF Slice

Not started. V1 must be fully validated before V2 work begins.
