# Chunk V6T-5 Approach: V6 Slice Quality Gate + Post-Chunk Sync

## Summary
Quality gate / polish chunk. No new product features. Adds criteria infrastructure
for V6 TradingView slice (mirrors the pattern used in V2/V3/V4/V5).

## Data scale
No database writes. sql_count queries on information_schema — single-row results.
Not applicable for scale decision tree.

## Actual file audit
- `backend/services/tv/bridge.py` — exists
- `backend/services/tv/cache_service.py` — exists
- `backend/models/alert.py` — exists
- `backend/models/watchlist.py` — exists
- `backend/routes/tv.py` — exists
- `backend/routes/alerts.py` — exists
- `backend/routes/watchlists.py` — exists
- `backend/routes/webhooks.py` — exists
- `frontend/src/app/pro/watchlists/page.tsx` — exists
- `frontend/src/app/pro/alerts/page.tsx` — exists
- `frontend/src/lib/tv.ts` — exists
- `frontend/src/components/deepdive/TVConvictionPanel.tsx` — exists

## Wiki patterns checked
- [Criteria-as-YAML Executable Gate](patterns/criteria-as-yaml-quality-gate.md) — exact pattern
- [AST-Scanned Anti-Pattern Detection](patterns/ast-scanned-anti-pattern-detection.md) — check_v6_no_float / check_v6_no_print

## Chosen approach
Direct port of V5 pattern:
1. `docs/specs/v6-criteria.yaml` — 20 criteria (v6-01..v6-20)
2. `.quality/quality_product_checks_v6.py` — 12 callable functions, stdlib only
3. `scripts/validate-v6.py` — thin wrapper over check_types dispatch
4. `.quality/dimensions/product.py` — add V6_CRITERIA_PATH + wire it in
5. `tests/unit/test_v6_criteria.py` — ≥8 tests mirroring test_v5_criteria.py

## Edge cases
- Backend may be offline when checks run → endpoint checks use urllib with 10s timeout, never raise
- Some V6 scan files may not exist → missing_notices path in collect_scan_targets
- check_sync_tv_is_404: uses fake UUID, expects 404 only (not 200/422)
- check_tv_webhook_requires_secret: POST without secret header → expects 403

## Expected runtime
- All stdlib checks: <1ms each
- Live endpoint checks: up to 10s each (timeout bound)
- Total quality gate: <60s on t3.large

## Files created (net-new)
1. docs/specs/v6-criteria.yaml
2. .quality/quality_product_checks_v6.py
3. scripts/validate-v6.py
4. tests/unit/test_v6_criteria.py

## Files edited
5. .quality/dimensions/product.py (add V6_CRITERIA_PATH constant + extend call)
