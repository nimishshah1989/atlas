# Frontend Runner Report Format

## Location

`.forge/frontend-report.json`

Written by `scripts/check-frontend-criteria.py` after every run.

## Schema

```json
{
  "version": "1.0",
  "generated_at": "<ISO 8601 timestamp in IST>",
  "criteria_file": "docs/specs/frontend-v1-criteria.yaml",
  "total": "<integer: total criteria evaluated>",
  "passed": "<integer: criteria that ran and passed>",
  "failed": "<integer: criteria that ran and failed>",
  "skipped": "<integer: criteria skipped (SKIP status)>",
  "critical_fail_count": "<integer: failed criteria with severity=critical>",
  "high_fail_count": "<integer: failed criteria with severity=high>",
  "results": [
    {
      "id": "<string: criterion id, e.g. fe-g-01>",
      "title": "<string: human-readable criterion title>",
      "severity": "<string: critical|high|medium|low>",
      "check_type": "<string: one of the 28 registered check types>",
      "passed": "<boolean>",
      "evidence": "<string: explanation of pass/fail/skip>",
      "status": "<string: RUN|SKIP|ERROR>"
    }
  ]
}
```

## Field semantics

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Schema version, currently "1.0" |
| `generated_at` | string | IST-aware ISO 8601 timestamp when report was written |
| `criteria_file` | string | Relative path to the source YAML file |
| `total` | int | Total criteria rows evaluated (after --only filter) |
| `passed` | int | Criteria with `status=RUN` and `passed=true` |
| `failed` | int | Criteria with `status=RUN` and `passed=false` |
| `skipped` | int | Criteria with `status=SKIP` (missing files, offline, no playwright) |
| `critical_fail_count` | int | Subset of `failed` with `severity=critical` |
| `high_fail_count` | int | Subset of `failed` with `severity=high` |

## `results[]` semantics

| Field | Values | Description |
|-------|--------|-------------|
| `status` | `RUN` | Check executed, `passed` reflects the actual result |
| `status` | `SKIP` | Check could not run (missing files, offline, no playwright). `passed=true` by convention |
| `status` | `ERROR` | Check handler raised an unexpected exception. `passed=false` |

## Invariants

1. `results[]` is sorted by `id` lexicographically
2. Two consecutive runs produce byte-identical output (modulo `generated_at`)
3. Exit code 0 when `critical_fail_count == 0`; exit code 1 otherwise
4. `total == passed + failed + skipped` (within a run)
5. `passed + failed == sum(r.status == "RUN" for r in results)`

## Evidence string conventions

- `SKIP: <reason>` — check was skipped
- `FAIL — <details>` — check failed with details
- Plain text without prefix — check passed, evidence describes what was found
- `ERROR: <exception>` — unexpected handler error
