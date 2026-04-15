# V5-16 Approach: V5 Polish + Quality Gate

## Data Scale
- atlas_intelligence: 20 columns, HNSW index confirmed (idx_intel_embedding_hnsw + idx_intelligence_embedding)
- atlas_agent_scores: 12 columns (actual: id, agent_id, prediction_date, entity, prediction, evaluation_date, actual_outcome, accuracy_score, is_deleted, deleted_at, created_at, updated_at)
- atlas_cost_ledger: 13 columns (actual: id, agent_id, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, request_type, metadata_json, is_deleted, deleted_at, created_at, updated_at)
- NOTE: actual columns differ from spec - must adjust SQL queries to check columns that actually exist

## Chosen Approach
- Follow exact pattern of v4-criteria.yaml / quality_product_checks_v3.py
- SQL criteria use IN() column checks against information_schema
- python_callable criteria use AST scan (no live DB needed for float/print checks)
- Endpoint checks use urllib.request (stdlib only, no httpx import)
- Accept 200/400/422/501 for endpoint probes, reject 404/5xx

## Wiki Patterns Used
- Criteria-as-YAML Executable Gate (exact pattern)
- AST-Scanned Anti-Pattern Detection (float/print checks)

## Existing Code Reused
- _iter_py_files, _has_float_annotation, _has_print_calls copied from quality_product_checks_v3.py
- dispatch imported from .quality/dimensions/check_types/__init__.py
- _extra_criteria_checks(V5_CRITERIA_PATH) appended in product.py

## Column Adjustments from Spec
- atlas_agent_scores: spec says agent_type/score_type/score_value/metadata/scored_at/data_as_of; actual has prediction_date/entity/prediction/evaluation_date/actual_outcome/accuracy_score — use overlap columns: id, agent_id, accuracy_score, prediction_date, entity, created_at, updated_at, is_deleted (8 overlap); min set to 8
- atlas_cost_ledger: spec says model_id/input_tokens/output_tokens; actual has model/prompt_tokens/completion_tokens/total_tokens — use actual overlap: id, agent_id, model, cost_usd, total_tokens, created_at, updated_at (7 overlap); min set to 7
- atlas_intelligence: has all 18 spec columns + 2 extra (is_deleted, deleted_at), min set to 18

## Edge Cases
- Files may not exist (embedding.py is checked conditionally)
- Backend may not be running (endpoint checks return False gracefully)
- Syntax errors in scanned files handled with try/except

## Expected Runtime
- SQL queries: <100ms each (information_schema)
- AST scans: <500ms (small files)
- Endpoint probes: <10s timeout each
- Total: ~30s on t3.large
