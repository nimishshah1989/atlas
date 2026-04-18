# S1-PRE-0: Frontend check runner — scripts/check-frontend-criteria.py

**Slice:** V1-Frontend-Stage1
**Depends on:** V11 complete (data manifests + coverage check shipped)
**Blocks:** Every S1-* chunk (nothing ships until the gate runs green)
**Complexity:** L (8–10 hours)
**Quality targets:** code: 90, architecture: 90, api: N/A (no HTTP), security: 90, frontend: N/A

---

## Step 0 — Boot context (read in order, fresh session)

1. `cat CLAUDE.md` — Four Laws, System Guarantees, post-chunk sync invariant
2. `cat ~/.claude/projects/-home-ubuntu-atlas/memory/MEMORY.md` +
   `project_v15_chunk_status.md` + `project_atlas_frontend_pages.md`
3. `cat docs/specs/frontend-v1-criteria.yaml` **in full** — vocabulary of 28
   check types, 113 criteria ids, severity model. This file is the input
   contract for the script you're building.
4. `cat docs/design/frontend-v1-spec.md` — source of truth the YAML encodes
5. `cat docs/design/frontend-inner-loop.md` — CONDUCTOR wiring + how this
   script is invoked by forge_runner per-chunk
6. `cat .quality/standards.md` — how the 7-dimension score interacts with
   this script's output (frontend dim reads `.forge/last-run.json`)

## Goal

One Python script that reads `docs/specs/frontend-v1-criteria.yaml`,
executes every enabled check, emits a deterministic JSON report, and
exits non-zero on any critical failure. This is the gate every S1-*
chunk crosses to reach DONE.

Non-goals: implementing the chunks themselves, writing mockup HTML,
running Playwright in CI (that's S1-11's job — here we make sure the
runner *can* drive Playwright when available).

## Files

### New
- `scripts/check-frontend-criteria.py` (≥ 600 lines)
- `scripts/lib/fe_checks/__init__.py`
- `scripts/lib/fe_checks/dom.py` — dom_required / dom_forbidden / attr_*
- `scripts/lib/fe_checks/fixture.py` — fixture_schema / field_required / etc
- `scripts/lib/fe_checks/playwright_checks.py` — screenshot / a11y / scroll / tap
- `scripts/lib/fe_checks/static.py` — grep_* / kill_list / i18n_indian / html5
- `scripts/lib/fe_checks/meta.py` — rule_coverage / methodology_footer / chart_contract / link_integrity
- `scripts/lib/fe_checks/report.py` — JSON report emitter + severity gate
- `tests/unit/fe_checks/test_dom_checks.py` (≥ 6 cases)
- `tests/unit/fe_checks/test_fixture_checks.py` (≥ 6 cases)
- `tests/unit/fe_checks/test_static_checks.py` (≥ 4 cases)
- `tests/unit/fe_checks/test_report_gate.py` (≥ 3 cases)
- `tests/unit/fe_checks/fixtures/` (synthetic HTML + JSON test fixtures)

### Modified
- `backend/requirements.txt` — add `beautifulsoup4>=4.12`, `jsonschema>=4.21`, `jsonpath-ng>=1.6`, `cssselect>=1.2`, `html5validator>=0.4` (pip) + document `playwright` install as an opt-in extra
- `.quality/checks.py` — frontend dimension reads the `critical_fail_count`
  field from `.forge/frontend-report.json`; fail-closed if file absent

## Entry-point contract

```
python scripts/check-frontend-criteria.py \
    [--criteria docs/specs/frontend-v1-criteria.yaml] \
    [--pages-glob 'frontend/mockups/*.html'] \
    [--only <id,id,...>] \
    [--skip-playwright] \
    [--server-url http://localhost:8080] \
    [--report-out .forge/frontend-report.json] \
    [--fail-on critical|high|medium|low]   (default: critical)
```

Exit codes:
- `0` — zero failures at or above `--fail-on` severity
- `1` — one or more failures at or above `--fail-on` severity
- `2` — runner error (YAML malformed, file missing, network error to Playwright URL)

## Report schema (emitted to `.forge/frontend-report.json`)

```json
{
  "version": 1,
  "criteria_file": "docs/specs/frontend-v1-criteria.yaml",
  "run_ts": "2026-04-18T14:30:00+05:30",
  "elapsed_seconds": 34.12,
  "totals": {
    "critical_fail_count": 0,
    "high_fail_count": 2,
    "medium_fail_count": 1,
    "low_fail_count": 0,
    "pass_count": 110,
    "skipped_count": 0
  },
  "results": [
    {
      "id": "fe-dp-01",
      "title": "regime-banner present on all market-facing pages (DP §12)",
      "severity": "critical",
      "status": "pass|fail|skip|error",
      "elapsed_ms": 42,
      "message": "matched 9/9 pages",
      "details": { "per_file": { "today.html": 1, "lab.html": 1, ... } }
    }
  ]
}
```

Deterministic ordering: results sorted by `id` ascending. No timestamps
inside individual `results[]` entries (keeps the report diffable).

## Check-type implementation map (28 total — must all be implemented)

| Type | Module | Notes |
|---|---|---|
| grep_forbid | static | `rg --json` subprocess; regex from YAML. Zero-tolerance. |
| grep_require | static | Same; assert `>= min_matches_each` per pattern. |
| kill_list | static | Forbidden phrases: BUY, HOLD, SELL, verdict, recommend-ish language. |
| i18n_indian | static | Forbid `$`, ` million`, ` billion`, MM/DD or MM-DD dates. |
| file_exists | static | `pathlib.Path(...).is_file()` + size > 0. |
| url_reachable | static | `httpx.get`, timeout 5s, expect 200. |
| link_integrity | static | Parse hrefs, local → `Path.exists()`, anchor → in-doc id, external → skip unless `allow_external=false`. |
| dom_required | dom | BeautifulSoup + cssselect; enforce `min_count` + `must_include_data_*` enum-coverage clauses. |
| dom_forbidden | dom | Same, must match zero nodes. |
| attr_required | dom | Every matched node must carry attr. |
| attr_enum | dom | Attr value ∈ allowed[]. |
| attr_numeric_range | dom | Parseable number in [min, max]; `integer_only` flag. |
| html5_valid | static | `html5validator --file F` exit 0. |
| design_tokens_only | static | Regex: hex colors / rgb() / font-family declarations outside `tokens.css`. |
| no_inline_style | dom | No `style=` attrs (allow-list per-check). |
| chart_contract | dom | Every `.chart` has legend+axis+source+tooltip+explain slots. |
| methodology_footer | dom | `<footer>` contains "data as of" + "source". |
| playwright_screenshot | playwright_checks | Skip with `--skip-playwright`; baseline in `.baselines/`. |
| playwright_a11y | playwright_checks | `axe-core` injected; WCAG 2 AA violations ≤ 0. |
| playwright_no_horizontal_scroll | playwright_checks | `page.evaluate('document.body.scrollWidth - window.innerWidth')` ≤ tolerance_px. |
| playwright_tap_target | playwright_checks | Every matched selector has `getBoundingClientRect()` ≥ min_width × min_height. |
| fixture_schema | fixture | `jsonschema.validate` per fixture against its sibling `*.schema.json`. |
| fixture_parity | fixture | Every fixture filename maps to a §15 endpoint; new endpoints must be declared in `allow_new_endpoints_list`. |
| fixture_field_required | fixture | `jsonpath_ng.parse(path).find(data)` non-empty; supports `value_type` / `format` / `min_length`. |
| fixture_numeric_range | fixture | Matches are numeric in [min, max]; optional `decimal_places_max`. |
| fixture_array_length | fixture | `len(match.value) >= min_length`. |
| fixture_enum | fixture | Every match ∈ allowed[]. |
| fixture_endpoint_reference | fixture | Each endpoint in `endpoints_must_appear[]` referenced by ≥1 fixture. |
| rule_coverage | meta | Every rule id from V1.1 rule-engine has ≥1 hook slot in spec §14. |

## Determinism + reproducibility

- Sort every directory scan (`sorted(Path(...).glob(...))`).
- No wall-clock values inside individual results; only the top-level `run_ts`.
- BeautifulSoup with `html.parser` (stdlib; no lxml ordering drift).
- Playwright runs with `--trace off --video off`; baseline screenshots
  compared via `pixelmatch` with threshold 0.01. Delta ≤ 1% passes.
- `--skip-playwright` yields `status="skip"` (not `error`) so the rest of
  the gate can still run during local dev.

## Tests (≥ 19 cases total)

1. `test_dom_required_min_count_matches` — selector matches = min_count → pass
2. `test_dom_required_min_count_short` — selector matches < min_count → fail
3. `test_dom_required_enum_coverage` — `must_include_data_chip` missing one → fail with diff message
4. `test_dom_forbidden_zero_match` → pass
5. `test_dom_forbidden_one_match` → fail with selector + line
6. `test_attr_numeric_range_in` / `_out` / `_integer_only_rejects_float`
7. `test_fixture_schema_valid` / `_invalid_missing_field` / `_invalid_wrong_type`
8. `test_fixture_field_required_present` / `_absent` / `_min_length_enforced`
9. `test_fixture_enum_match` / `_mismatch`
10. `test_grep_forbid_zero_tolerance` / `_matches_fail`
11. `test_kill_list_blocks_buy_sell_verdict`
12. `test_i18n_indian_flags_dollar_sign` / `_flags_million`
13. `test_report_gate_exit_0_when_no_critical_fail`
14. `test_report_gate_exit_1_when_one_critical_fail`
15. `test_report_gate_respects_fail_on_flag`

All fixtures synthetic — zero dependency on actual mockup state. This
script must be buildable + testable before any mockup is ever touched.

## Points of success (all required for DONE)

1. `python scripts/check-frontend-criteria.py --criteria docs/specs/frontend-v1-criteria.yaml --skip-playwright` exits deterministically on the current (partially-compliant) mockup tree and emits `.forge/frontend-report.json` matching the schema above.
2. `pytest tests/unit/fe_checks/ -v` — all ≥19 tests green.
3. `ruff check scripts/check-frontend-criteria.py scripts/lib/fe_checks/` clean.
4. `mypy scripts/check-frontend-criteria.py scripts/lib/fe_checks/ --ignore-missing-imports` clean.
5. Every one of the 28 check types listed in the preamble of `frontend-v1-criteria.yaml` has a handler function in `scripts/lib/fe_checks/` (meta-test enforces this).
6. `.quality/checks.py` frontend dimension reads `critical_fail_count` from the report (integration test: mutate report, re-score, confirm propagation).
7. Running with `--only fe-g-01,fe-g-02` executes only those two checks (used for targeted chunk dev loops).

## Post-chunk sync invariant

`scripts/post-chunk.sh S1-PRE-0` green — forge-ship commit, service
restart (no backend impact but still run the probe), smoke probe
(`python scripts/check-frontend-criteria.py --only fe-l-01`), forge-compile
into wiki, MEMORY.md entry: `reference_fe_check_runner.md`.
