---
chunk: V3-9
project: atlas
date: 2026-04-14
status: in-progress
---

# V3-9 Approach: Polish — gates, post-chunk sync, smoke probe

## Scope
Four files:
1. `.quality/quality_product_checks_v3.py` — AST callables for v3-criteria.yaml
2. `.quality/dimensions/product.py` — wire V3 criteria in alongside V2
3. `scripts/validate-v3.py` — CLI validator mirroring validate-v2.py
4. `tests/unit/test_product_v3.py` — 5 unit tests

## Data scale
No database writes. No row count queries needed.
Read-only: filesystem AST scans of ~10 Python files in backend/services/simulation/.

## Chosen approach

### quality_product_checks_v3.py
Use `ast` module (not regex) per established AST-Scanned Anti-Pattern Detection
pattern (5x sightings, promoted). Two functions:
- `check_simulation_no_float()`: scan backend/models/simulation.py + all .py in
  backend/services/simulation/ for ast.Name(id='float') in annotations
- `check_simulation_no_print()`: scan all .py in backend/services/simulation/ for
  ast.Call where func is ast.Name(id='print')

V3-6 optimizer had `-> float` annotations fixed via `-> Any`, so scans should pass.

### product.py changes
Add V3_CRITERIA_PATH constant and a helper `_extra_criteria_checks(path)` that
mirrors the v1-criteria dispatch loop but uses the check_types `dispatch()` function.
Call it for both V2 and V3 after `_api_standard_checks()`. The helper returns []
gracefully when the file is missing.

### validate-v3.py
Direct copy of validate-v2.py with path and title string changes.

### tests/unit/test_product_v3.py
Five tests, all pure Python (no DB, no network). Import via sys.path manipulation
per existing test_v2_criteria.py pattern.

## Wiki patterns checked
- AST-Scanned Anti-Pattern Detection (5x) — confirmed approach for float/print scans
- Criteria-as-YAML Executable Gate (2x) — confirmed YAML dispatch pattern
- Seven-Dimension Quality Gate (3x) — context for product dim wiring

## Existing code reused
- `.quality/quality_product_checks_v2.py` — module structure reference
- `.quality/dimensions/product.py` — where to add V3 wiring
- `.quality/dimensions/check_types/python_callable.py` — dispatch mechanism
- `scripts/validate-v2.py` — validate script template

## Edge cases
- `__pycache__` dirs: skip them (glob *.py then filter path.parent.name != '__pycache__')
- AST parse errors: catch and return (False, msg) — never raise
- Missing simulation files: handle gracefully — return evidence listing missing files
- v3-criteria.yaml already exists (5 criteria confirmed)

## Expected runtime
~50ms total. Pure filesystem reads + AST parsing of small files.
