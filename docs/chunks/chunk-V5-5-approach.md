# Chunk V5-5: Intelligence Memory API — 3 Read-Only Routes

## Data scale
- `atlas_intelligence` table: no production rows yet (V5 is being built). Scale: <1K rows.
- All operations are simple primary-key lookups or small filtered queries. SQL is the right tool.

## Approach
Three changes to make the 3 GET intelligence routes conform to §20 standard envelope:

1. **Schema update** (`backend/models/schemas.py`): Add `_meta` aliases to `IntelligenceSearchResponse` and `IntelligenceListResponse` (via `model_serializer`), and a new `FindingSummaryEnvelope` for the single-finding route. Use the same dual-serialization pattern as `StockDeepDiveResponse`.

2. **Route update** (`backend/routes/intelligence.py`): Wrap single-finding GET in `{"data": ..., "_meta": {...}}`. Update list + search routes to include `_meta` via serializer. Add `data` alias so `check-api-standard.py` `_first_record()` helper can find the array.

3. **Criteria** (`docs/specs/api-standard-criteria.yaml`): Add 3 `http_get` criteria. Search uses a `static_import` check instead of live probe since embedding service may be unavailable.

4. **Tests** (`tests/api/test_intelligence_api.py`): Unit-level tests using `TestClient` + `app.dependency_overrides[get_db]` pattern (FastAPI dependency patch gotcha). Mock service layer via `patch`.

5. **Contracts** (`contracts/v5-api.openapi.yaml`): Create subset OpenAPI documenting the 3 GET routes.

## Wiki patterns checked
- `FastAPI Dependency Patch Gotcha` — must patch `get_db` even when service fully mocked
- `Criteria-as-YAML Executable Gate` — new criteria are YAML data, no code changes to checker
- `Embedding Fault Tolerance in Store Path` — search endpoint needs try/except around embed()

## Existing code being reused
- `StockDeepDiveResponse._serialize_with_dual_meta` pattern — apply same to intelligence responses
- `ResponseMeta` — already has `total_count`, `returned`, `offset`, `limit`, `has_more`, `next_offset`
- `TestClient` + `_override_db` pattern from `test_simulate_page_api.py`

## Edge cases
- Search endpoint: embedding service offline → return empty `data=[]` with correct envelope, not 500
- Single-finding 404: wrap in HTTPException, not envelope (standard HTTP error behavior)
- `data` key required for `_first_record()` in check-api-standard.py
- `_meta` path required for `expect_json_path` in check-api-standard.py
- list/search responses: `data` is the array key, `_meta` has pagination

## Expected runtime
- All routes: <50ms (indexed PK lookup or small filtered scan)
- Tests: <2s (no real DB, all mocked)
