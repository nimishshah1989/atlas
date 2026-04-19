---
chunk: V2FE-1
project: atlas
date: 2026-04-19
status: in-progress
---

# V2FE-1 Approach: Backend gaps — zone-events, global-events, divergences, flows, UQL templates, conviction_series

## Data scale (actual)
- de_breadth_daily: aggregate table queried by JIPMarketService.get_market_breadth() via SELECT * ORDER BY date DESC LIMIT 1. Zone detector needs time-series, not just latest row.
- de_fii_dii_daily: probed inline (COUNT(*) health gate) before use.
- atlas_gold_rs_cache: existing ORM table used by gold_rs_cache.py; conviction_series extension reads from it.
- atlas_key_events: NEW table (seeded from fixtures/events.json, ~20-30 rows initially).

## Chosen approach

### BreadthZoneDetector
- AsyncSession class accepting session in constructor (matches spec)
- Queries de_breadth_daily time-series with date range filter via text() SQL
- Columns: `above_ema21`, `above_dma50`, `above_dma200` (confirmed via JIPMarketService — SELECT * returns these)
- Zone thresholds for nifty500: OB=400, mid=250, OS=100. nifty50: OB=40, mid=25, OS=10
- Edge-trigger: detect crossing boundaries, emit one event per crossing
- indicator="all" means run for all 3 indicators and merge
- Redis TTL 24h, best-effort (swallow errors)

### EventMarkerService
- Reads atlas_key_events via SQLAlchemy ORM (AtlasKeyEvent model)
- Filters: scope (JSONB @> operator), date range, categories
- Redis TTL 7d, best-effort

### Alembic migration l9m0n1o2p3q4
- Creates atlas_key_events table
- Seeds from events.json fixture
- down_revision = "k8l9m0n1o2p3"

### BreadthDivergenceDetector
- Queries de_breadth_daily for pct above 50-DMA
- Queries de_index_daily for index price (if table exists/has data, else insufficient_data=True)
- Window-based comparison: positive index change + negative breadth change = bearish divergence
- Returns Decimal for financial values

### FlowsService
- Inline COUNT(*) health gate for de_fii_dii_daily
- Filters by scope (csv), range
- Decimal for all financial values

### UQL templates
- top_rs_losers: same as top_rs_gainers but SortDirection.ASC
- fund_1d_movers, mf_rank_composite, mf_rank_history: MF entity templates
- sector_rotation: add rs_gold + conviction aggregations

### Routes
- /breadth/zone-events and /breadth/divergences: added BEFORE /{symbol} routes
- /global/events and /global/flows: added to global_intel.py
- /breadth extended with include=conviction_series

## Wiki patterns used
- [Redis Best-Effort Cache, DB Authority] — swallow Redis errors, DB is truth
- [Inline DB Health Gate] — COUNT(*) probe for de_fii_dii_daily
- [FastAPI Static Route Before Path Param] — zone-events + divergences BEFORE /{symbol}
- [Plain Dict §20.4 Envelope for Near-Realtime Routes] — dict[str, Any] return
- [Gather Return Exceptions Optional Enrichment] — conviction_series best-effort

## Edge cases
- de_breadth_daily empty → return events: []
- de_fii_dii_daily COUNT=0 → return insufficient_data: True
- de_index_daily missing → BreadthDivergenceDetector sets insufficient_data=True
- indicator="all" → merge events from all 3 indicators, sort by date
- NULL values in breadth counts → skip row in zone detection

## Files to modify
- backend/routes/global_intel.py — add /events, /flows
- backend/routes/stocks.py — add /breadth/zone-events, /breadth/divergences, extend /breadth
- backend/services/uql/templates.py — add new templates
- backend/models/schemas.py — add conviction_series to MarketBreadthResponse
- backend/db/models.py — add AtlasKeyEvent

## Files to create
- backend/services/breadth_zone_detector.py
- backend/services/event_marker_service.py
- backend/services/breadth_divergence_detector.py
- backend/services/flows_service.py
- alembic/versions/l9m0n1o2p3q4_v2fe1_atlas_key_events.py
- tests/services/test_breadth_zone_detector.py
- tests/services/test_breadth_divergence_detector.py
- tests/services/test_event_marker_service.py
- tests/services/test_flows_service.py
- tests/routes/test_global_intel.py (extend existing)

## Expected runtime
All services are read-only, single-table queries with date-range filters. Expected <100ms on t3.large with indexes.
