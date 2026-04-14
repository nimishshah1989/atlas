# Chunk V2-10 Approach: V2 Integration Suite + Completion Criteria Validation

## Data Scale
- `atlas_decisions`: 418 rows (>5 threshold easily met)
- `atlas_intelligence`: 688 rows (>10 threshold easily met)
- `de_mf_derived_daily`: 728,735 rows (MF data is real and substantial)
- `de_mf_holdings`: 230,254 rows
- Real mstar_id available: `F000000CBS` (queried live)

## Chosen Approach

### 1. v2-criteria.yaml
Mirror v1-criteria.yaml format exactly. 9 criteria mapped to SC-001..SC-009. Check types use the existing dispatch system: `http_contract`, `sql_count`, `python_callable`, `file_exists`.

### 2. scripts/validate-v2.py
Copy-paste adapt from `validate-v1-completion.py` — only change the criteria path and title string. No new dependencies.

### 3. .quality/quality_product_checks_v2.py
New file with four callables:
- `check_mf_deep_dive`: queries DB dynamically for a real mstar_id, then hits the endpoint
- `check_mf_no_float`: AST scan of `backend/routes/mf.py` + `backend/services/mf_compute.py`
- `check_v1_criteria_pass`: subprocess `python scripts/validate-v1-completion.py`, check returncode
- `check_mf_response_times`: time `/mf/universe` and `/mf/{mstar_id}`, check budgets

### 4. .quality/dimensions/product.py
Add `V2_CRITERIA_PATH` constant + load v2-criteria.yaml in `dim_product()` if file exists. Combine checks without breaking gating=True logic.

### 5. tests/unit/test_v2_criteria.py
Tests for YAML loading/validation, required fields, SC mapping documentation.

### 6. tests/integration/test_v2_endpoints.py
MF endpoint integration tests marked `@pytest.mark.integration`.

## Wiki Patterns Checked
- `Criteria-as-YAML Executable Gate` — exactly what we're building
- `Seven-Dimension Quality Gate` — confirm gating=True for product dim
- `Importlib Isolation` — pattern used in check-api-standard.py loader (already in product.py)

## Existing Code Being Reused
- `validate-v1-completion.py` → template for validate-v2.py
- `.quality/dimensions/check_types/dispatch` → same dispatch system
- `quality_product_checks.py` → pattern for quality_product_checks_v2.py
- `tests/integration/test_v1_endpoints.py` → pattern for test_v2_endpoints.py

## Edge Cases
- mstar_id may not exist in endpoint if DB unavailable → check returns False gracefully
- v2-criteria.yaml missing → product dim skips v2 block silently (v1 unaffected)
- Backend not running → http checks fail cleanly with error evidence string
- `check_v1_criteria_pass` uses subprocess; if validate-v1 is slow (>10s), that's OK since integration context allows it

## Expected Runtime
- validate-v2.py: ~5-10s total (network-bound on MF endpoints)
- product dim: adds ~3-5s when v2 file present
- Integration tests: 30-60s (hitting live backend)
- Unit tests: <1s (YAML parsing only)

## Files to Create/Modify
- CREATE `docs/specs/v2-criteria.yaml`
- CREATE `scripts/validate-v2.py`
- CREATE `.quality/quality_product_checks_v2.py`
- MODIFY `.quality/dimensions/product.py`
- CREATE `tests/unit/test_v2_criteria.py`
- CREATE `tests/integration/test_v2_endpoints.py`
