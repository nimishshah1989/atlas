---
chunk: V2FE-0
project: ATLAS
date: 2026-04-19
status: in_progress
---

## Task

Create criteria YAML + loader skeleton JS assets + §6 states contract for V2FE slice.

## Approach

1. Create `docs/specs/frontend-v2-criteria.yaml` with ≥30 entries across §8.1-§8.5
2. Create `scripts/check-frontend-v2.py` runner following check-frontend-criteria.py pattern
3. Create `frontend/mockups/assets/atlas-data.js` (ES2020 loader)
4. Create `frontend/mockups/assets/atlas-states.js` (ES2020 states contract)
5. Wire script tags into 6 target pages (no other page modifications)
6. Write 8 unit tests using Python structural pattern-matching (node.js available as fallback)

## Data scale

Not applicable — no DB reads. Pure frontend infrastructure.

## Wiki patterns checked

- Criteria-as-YAML Executable Gate (7x PROMOTED): schema-locked YAML + check-type registry
- Runner Report JSON as Gate Contract (1x staged): .forge/<slice>-report.json contract
- Skip-Aware Live API Probe (1x staged): backend probe skips if unreachable

## Edge cases

- Backend unreachable: backend checks emit status=SKIP, not FAIL
- Script tags already present: check before adding (idempotent wiring)
- assets/ directory does not exist: create it
- js2py not available: Python structural tests with grep patterns (Node v22 available)
- STALENESS_THRESHOLDS must match §6.3 exactly (7 keys)
- Known-sparse guard: insufficient_data=true → renderEmpty, never error

## Expected runtime

Under 10 seconds. No DB, no heavy computation.
