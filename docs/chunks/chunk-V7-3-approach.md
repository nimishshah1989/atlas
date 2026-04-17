# Chunk V7-3 Approach — Global Routes

## Data Scale
- `de_global_instrument_master`: 131 rows (small, SQL all fine)
- `de_rs_scores WHERE entity_type='global'`: ~131 entities × N dates (medium, DISTINCT ON handles it)
- `de_macro_values`: small per ticker (9 tickers × ~2K rows = ~18K rows)
- `atlas_gold_rs_cache`: sparse (only precomputed entities)
- DB was unreachable during approach phase; scale estimates from spec + wiki

## Chosen Approach
- SQL in `jip_market_service.py` via `text()` — 3 new methods added to JIPMarketService
- Python grouping in route for rs-heatmap (tiny: 131 rows, collections.defaultdict)
- Python verdict compute per row for indices (pure function, no DB)
- All Decimal via `Decimal(str(v))` pattern
- Route prefix: `/api/global` (NOT `/api/v1/global` which already exists in global_intel.py)

## Wiki Patterns Checked
- `pydantic-v2-meta-serializer` — store as `meta`, emit `_meta` via model_serializer (PROMOTED)
- `conftest-integration-marker-trap` — tests go in `tests/routes/` not `tests/api/` (PROMOTED)
- `FastAPI-dependency-patch-gotcha` — must patch `get_db` even when service fully mocked (bug-pattern)
- `DISTINCT-ON-latest-row-per-key` — DISTINCT ON for latest RS/price per entity (PROMOTED)

## Existing Code Reused
- `backend/models/global_intel.py` — `MacroSparkItem` imported in global_v7.py
- `backend/models/gold_rs.py` — `GoldRSSignalType` (Literal type, not Enum)
- `backend/models/schemas.py` — `ResponseMeta` 
- `backend/clients/jip_market_service.py` — extended with 3 new methods
- `backend/db/session.py` — `get_db` dependency

## Key Decisions
1. `FourBenchVerdict` as `str, Enum` — consistent with other verdict types
2. `GoldRSSignalType` is a Literal, not Enum — use string comparison in verdict compute
3. Router prefix `/api/global` — avoids collision with existing `/api/v1/global` prefix
4. `_safe_decimal()` helper in route module to centralize Decimal conversion
5. `model_serializer(mode="wrap")` for all response models (V7-1/V7-2 pattern)
6. Tests mock `backend.routes.global_v7.JIPMarketService` + override `get_db`

## Edge Cases
- NULL rs_composite/rs_1m/rs_3m → counts as non-positive in verdict (spec explicit)
- NULL gold_rs_signal → counts as non-positive (no AMPLIFIES_BULL → no score)
- Decimal("0") → NOT > 0 → non-positive (spec explicit)
- Short macro series (< 31 datapoints) → mom_change = None
- Instruments with no RS scores → still appear in heatmap (LEFT JOIN from master)
- Empty atlas_gold_rs_cache for global → gold_rs_signal = None in index rows

## Expected Runtime
- `/api/global/ratios`: ~50ms (9 tickers, small table)
- `/api/global/rs-heatmap`: ~100ms (131 rows, LEFT JOINs)
- `/api/global/indices`: ~150ms (subset of 131 + gold_rs join)
- All well within t3.large budget
