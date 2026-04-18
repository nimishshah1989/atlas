# Chunk V1FE-1 Approach — Frontend Criteria Gate

## Data scale
Not applicable — this chunk touches no database tables. Pure Python scripting infrastructure.

## Chosen approach

Build a registry-dispatcher pattern (matching the existing `check_types` pattern in `.quality/dimensions/check_types/`) for frontend-specific checks. Key decisions:

1. **Separate package** `scripts/fe_checks/` mirrors the `.quality/dimensions/check_types/` pattern. Each module handles one category of checks and returns `(passed: bool, evidence: str)`.

2. **Registry in `__init__.py`** maps type names to handlers. `dispatch(spec)` is the single entry point. Preflight validates all types before any check runs.

3. **Graceful degradation**: Missing files → SKIP. Missing playwright → SKIP. Missing html5validator → SKIP. Missing jsonschema → SKIP. Never crash.

4. **Regex-based DOM inspection** for HTML — stdlib html.parser is too low-level for CSS selectors, and external libraries (lxml, cssselect) are not allowed. Implement `find_elements(html, selector)` using regex patterns for the supported selector grammar.

5. **Simple JSONPath** — implement `resolve_jsonpath(data, path)` supporting `$`, `.key`, `[*]` (sufficient for all YAML criteria).

6. **Determinism** — sort results by id, use IST-aware timestamps for generated_at only, no random values.

## Wiki patterns consulted
- `criteria-as-yaml-quality-gate` — YAML spine + tiny dispatcher pattern; each handler returns `(passed, evidence)`, never raises
- `seven-dimension-quality-gate` — frozen 7-dim rubric, per-dim 80% gate

## Existing code being reused
- `.quality/dimensions/check_types/__init__.py` — same `dispatch()` + `HANDLERS` dict pattern
- `.quality/dimensions/__init__.py` — `CheckResult`, `DimensionResult` types
- IST timezone pattern from `checks.py`

## Edge cases
- File glob matches 0 files: SKIP with evidence "no files matched"
- `pages_from` references `settings.all_pages`: resolve during load
- `selector_file_pairs`: check each pair independently
- `slots` list with `selector_template`: interpolate `{id}` in template
- Criteria with `soft: true`: always PASS (informational)
- `min_count: 0` with `soft: true`: always PASS
- kill_list with `exceptions_selectors`: content inside those selectors is excluded from pattern matching
- url_reachable: check `FE_CHECKS_OFFLINE` env var, also catch any network error → SKIP
- fixture_glob: expand glob, check each file independently
- Missing fixture files: SKIP with evidence string
- `files` vs `file` (singular) in check spec: handle both

## 28 check types (counted from criteria YAML header)
Static/grep (4): grep_forbid, grep_require, kill_list, i18n_indian
File system (3): file_exists, url_reachable, link_integrity
DOM/selector (5): dom_required, dom_forbidden, attr_required, attr_enum, attr_numeric_range
HTML/accessibility (4): html5_valid, design_tokens_only, chart_contract, methodology_footer
Playwright (4): playwright_screenshot, playwright_a11y, playwright_no_horizontal_scroll, playwright_tap_target
Fixture/JSON (7): fixture_schema, fixture_parity, fixture_field_required, fixture_numeric_range, fixture_array_length, fixture_enum, fixture_endpoint_reference
Rule engine (1): rule_coverage
Total: 28

## Expected runtime
On t3.large: < 5 seconds for a full run (all checks SKIP due to missing mockup files). Playwright checks will SKIP (not installed). DOM checks will SKIP (no HTML files).

## Test strategy
34 unit tests in `tests/unit/test_fe_checks.py`. Each test creates temp files, calls the handler directly, asserts (passed, evidence). No subprocess, no network, no real browser.
