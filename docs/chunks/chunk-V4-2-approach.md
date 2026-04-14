# Chunk V4-2 Approach: CAMS Import + Scheme Mapping

## Data scale
- atlas_portfolios: 0 rows (fresh table from V4-1)
- atlas_portfolio_holdings: 0 rows
- atlas_scheme_mapping_overrides: 0 rows
- de_mf_master (JIP): ~2000–5000 active MF funds (read-only via JIP client)

## Approach

### CAMS parsing
casparser + rapidfuzz must be installed in venv. casparser is called per file upload (never stored).
All floats from casparser immediately converted to Decimal(str(value)).

### Scheme mapper
1. Check atlas_scheme_mapping_overrides by exact match on scheme_name_pattern
2. If no override: fetch fund universe from JIP via get_mf_universe() (cached 5min)
3. rapidfuzz.fuzz.token_sort_ratio for fuzzy matching (case-insensitive, whitespace-normalized)
4. Confidence >= 0.70 → mapping_status='mapped', < 0.70 → 'pending' (needs_review)
5. Override matches → confidence=1.0, mapping_status='manual_override'

### Route wiring
POST /import-cams accepts UploadFile + optional password Form field.
Creates portfolio (type=cams_import) + holdings via PortfolioRepo in a single transaction.
Returns PortfolioImportResult with needs_review bucket.

### Decimal boundary
- All casparser floats: Decimal(str(float_val)) at parse boundary
- rapidfuzz scores (0-100 int) normalized to Decimal(score/100) — never float stored

## Wiki patterns checked
- Decimal Not Float: convert at casparser boundary, Decimal(str()) 
- FastAPI Dependency Patch Gotcha: patch get_db in tests even when service mocked
- Contract Stub 501 Sync: update test_import_cams_returns_501 to expect non-501

## Existing code reused
- PortfolioRepo.create_portfolio() for DB writes
- JIPMFService.get_mf_universe() for fund universe (read-only)
- _build_portfolio_response() helper for HoldingResponse construction

## Edge cases
- casparser may return float NAV/units → Decimal(str(v)) conversion
- NULL NAV or missing valuation → stored as None, never 0
- scheme_name_pattern exact match is case-sensitive; normalize before compare
- Empty CAS PDF → return empty portfolio with 0 holdings, no error
- Corrupt PDF → raise HTTPException 422 with clear message
- Unmapped fund (confidence < 0.70) → stored with pending status, shown in needs_review

## Expected runtime
- casparser parse: <1s for typical CAS PDF (<10MB)
- MF universe fetch: <500ms with cache hit, <3s cold
- rapidfuzz matching N schemes against 5000 funds: <200ms
- Total: <5s for a typical CAS import

## No migration needed
V4-1 already created all three tables.

## Files in scope
- CREATE: backend/services/portfolio/cams_import.py
- CREATE: backend/services/portfolio/scheme_mapper.py
- MODIFY: backend/routes/portfolio.py
- MODIFY: backend/models/portfolio.py
- CREATE: tests/unit/portfolio/test_cams_import.py
- CREATE: tests/unit/portfolio/test_scheme_mapper.py
- CREATE: tests/api/test_portfolio_import.py
- MODIFY: tests/api/test_portfolio_stubs.py
- MODIFY: requirements.txt
