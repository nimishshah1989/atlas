# Chunk V5-15 Approach — Pro shell /pro/intelligence page

## Summary
Build the `/pro/intelligence` page in the ATLAS frontend Pro shell, plus a backend smoke test that verifies semantic search returns findings with required fields (confidence, evidence, agent, timestamp) and that the empty-state path works when min_confidence=0.99 returns zero findings.

## Data scale
No new DB reads needed for this chunk — intelligence routes already exist. No table scan required. This chunk is purely frontend + test.

## Chosen approach

### Backend smoke test
- Pattern from `tests/api/test_intelligence_api.py`
- Uses `app.dependency_overrides[get_db]` (FastAPI Dependency Patch Gotcha pattern)
- Patches `backend.routes.intelligence.get_relevant_intelligence` at the service boundary
- ORM row mocks via `MagicMock` with all required fields
- Verifies: confidence present, evidence non-empty dict, agent_id/agent_type present, created_at present
- Verifies empty state: `data == []`, `_meta.record_count == 0`
- Verifies `min_confidence=Decimal("0.99")` passed through to service call kwargs

### Frontend API client
- Pattern from `frontend/src/lib/api-portfolio.ts` — same `fetchApi<T>` helper
- Types mirror `FindingSummary` from `backend/models/intelligence.py`
- `IntelligenceSearchResponse` has both `findings` and `data` keys (model_serializer dual-key)
- Two functions: `searchIntelligence` and `listFindings`

### Frontend page
- Pattern from `frontend/src/app/pro/portfolio/page.tsx`
- `"use client"`, sticky header, breadcrumbs, max-width 1600px container
- Two-column layout: 2/3 results left, 1/3 filter sidebar right (sticky)
- Search bar at top with text input + button
- Finding cards with: title, content, agent badge, confidence %, evidence collapsible, timestamp IST, finding_type chip (reuse color scheme from FindingChips.tsx), entity tag, tag badges
- Empty state: `data-testid="empty-state"` message
- Loading skeleton, error banner with retry

## Wiki patterns checked
- `FastAPI Dependency Patch Gotcha` — must patch get_db even when service mocked
- `Decimal Not Float` — confidence displayed as string, parsed with parseFloat
- `Route Schema Change Test Regression` — response shape has both `data` and `findings` keys

## Existing code reused
- `findingTypeColor()` logic from `FindingChips.tsx`
- `api-portfolio.ts` fetchApi pattern
- `portfolio/page.tsx` header/layout pattern
- `test_intelligence_api.py` mock patterns

## Edge cases
- `confidence` may be null → display "—"
- `evidence` may be null or empty → hide section gracefully
- `entity` may be null → omit entity tag
- `tags` may be null → show no tag badges
- Empty results (zero findings) → show empty-state with data-testid
- IST datetime formatting: `toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })`

## Expected runtime
- Tests: < 5 seconds (no real DB, all mocked)
- Page load: < 200ms (depends on existing intelligence API)

## Files to create
1. `frontend/src/lib/api-intelligence.ts`
2. `frontend/src/app/pro/intelligence/page.tsx`
3. `tests/api/test_pro_intelligence_smoke.py`
