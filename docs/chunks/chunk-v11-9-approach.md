# V11-9 Approach: OpenBB + FinanceToolkit Pilot — /api/stocks/{symbol}/analysis

## Data Scale
No new DB writes. Reads from existing JIP tables (de_equity_technical_daily, de_annual_fundamental) via JIPDataService. No table scans needed — endpoint pulls a single stock_detail dict already fetched by JIPDataService.

## Chosen Approach
- New model file `backend/models/analysis.py`: `LegacySignals`, `OpenBBSignals` (strict superset), `AnalysisMeta`, `AnalysisResult` (with `model_serializer` for §20.4 `data+_meta` envelope)
- New service `backend/services/analysis_service.py`: `build_legacy_signals()` (sync) + `build_openbb_signals()` (async, calls `compute_piotroski` via its session)
- Route added to `backend/routes/stocks.py` BEFORE `/{symbol}` (line 331), as `/{symbol}/analysis`
- Tests in `tests/routes/` (not `tests/api/`) — avoids conftest integration marker trap

## Wiki Patterns Checked
- `pydantic-v2-meta-serializer.md` — store as `meta` internally, emit `_meta` via `model_serializer`
- `fastapi-static-route-before-path-param.md` — `/{symbol}/analysis` MUST register before `/{symbol}`
- `conftest-integration-marker-trap.md` — tests go in `tests/routes/` not `tests/api/`
- `fastapi-dependency-patch-gotcha.md` — must patch `get_db` even when service is fully mocked

## Key Corrections vs Spec
- `compute_quadrant()` returns `Optional[Quadrant]` (Enum), not `Optional[str]` — `rs_quadrant` field must be `Optional[Quadrant]` not `Optional[str]`
- `Piotroski` model (in `backend/models/derived.py`) has `score`, `grade`, `detail` — not `profitability/leverage/efficiency`; test fixture adjusted accordingly
- `AnalysisResult.model_serializer` must use `mode="wrap"` per Pydantic v2 API

## Edge Cases
- NULL rs_composite / rs_momentum → `_dec()` returns None → quadrant is None (explicit)
- Piotroski failure → `piotroski_score=None`, engine still returns 200 (graceful degradation)
- `engine=None` → treated as "legacy" (`.lower()` called on `engine or "legacy"`)
- Stock not found → 404 (same as existing deep-dive route)
- Invalid engine string → 400 with structured error

## Expected Runtime
Both legacy and openbb engines are sub-millisecond computation on already-fetched dict data. Piotroski call in openbb adds ~5-50ms DB round-trip. p95 openbb ≤ 1.5× p95 legacy is easily met because piotroski already has its own test infra and can be mocked.

## Files Modified
- `backend/models/analysis.py` (CREATE NEW)
- `backend/services/analysis_service.py` (CREATE NEW)
- `backend/routes/stocks.py` (ADD route before /{symbol})
- `tests/routes/test_stock_analysis.py` (CREATE NEW)
