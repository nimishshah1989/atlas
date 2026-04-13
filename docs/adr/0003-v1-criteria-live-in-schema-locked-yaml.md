# ADR 0003 — V1 completion criteria live in a schema-locked YAML

**Status:** Accepted (2026-04-13, chunks S3 + S4)
**Depends on:** ADR-0001

## Context

Before S3, "V1 is done when..." existed in three different places:

1. `ATLAS-DEFINITIVE-SPEC.md` §24.3 — 15 criteria, prose checkboxes.
2. `CLAUDE.md` — 13 criteria (had drifted), prose checkboxes.
3. Nowhere executable — no CI check could answer "is V1 done yet?".

The FD chunks exposed the drift: the spec said 15, CLAUDE.md said 13, and
the forge dashboard had no "V1 completion %" because the data didn't
exist.

## Decision

V1 completion criteria live in `docs/specs/v1-criteria.yaml`, locked by
`docs/specs/v1-criteria.schema.json`. Each criterion is one row with an
ID (`v1-01`..`v1-15`), a title, a severity, a source-spec pointer, and a
`check` block that the quality engine's `product` dim dispatches through
one of five declarative check types:

- `http_contract` — GET URL, assert 200 under `max_latency_ms`
- `sql_count` — scalar count, assert `min`/`max`
- `sql_invariant` — scalar query, assert `equals`/`min`/`max`
- `python_callable` — dotted path returning `(bool, str)`
- `file_exists` — path + optional `min_size_bytes`

`CLAUDE.md` now points to the YAML as the single source of truth for V1
criteria. The spec keeps §24.3 as prose for human readers; if the two
disagree, the YAML wins — because it's the one that runs.

V2 will ship `v2-criteria.yaml` with the same shape and IDs `v2-XX`.

## Consequences

- The product dim on the forge dashboard renders a live V1 completion
  progress bar — 87% on the day S3 landed (13/15; `v1-07` and `v1-12`
  both fail until V1.6 R1 writes decisions and findings).
- Drift detection: `.quality/verify_doc_matches_code.py` treats YAML
  criterion IDs as code checks and the architecture dim's check 3.10
  fires if `standards.md` and `checks.py` + `v1-criteria.yaml` disagree.
- Adding a new V1 criterion is a YAML edit, not a code change — which
  means non-engineers can review it.
