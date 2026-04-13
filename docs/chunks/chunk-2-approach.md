# Chunk FD-2 Approach — Roadmap spine + lint

## Data scale
No database queries needed — this chunk is pure YAML/Python file manipulation.

## Chosen approach
- `orchestrator/roadmap_schema.py` — Pydantic v2 models, defined here first (FD-1 imports from here)
- `orchestrator/roadmap.yaml` — canonical V1–V10 roadmap, C1–C11 from plan.yaml
- `scripts/roadmap-lint.py` — 6-rule lint, exits 0/1, diagnostic table on error
- `scripts/plan-to-roadmap.py` — ruamel.yaml round-trip writer (preserves comments)
- Tests mirror the two scripts

## Wiki patterns checked
- Not applicable (pure scripting, no DB/API patterns needed)

## Existing code reused
- plan.yaml structure read to seed C1–C11 chunk IDs and titles
- tasks-to-plan.py additive-only modification to add --auto-roadmap flag

## Edge cases
- Chunk in roadmap without future:true but not in plan.yaml → lint error
- Chunk in plan.yaml not in any roadmap version → lint error (rule 1)
- Cross-version chunk assignment → plan-to-roadmap.py rejects with exit 1
- command: "string" (not list) → lint error (rule 6) and Pydantic rejection
- demo_gate missing url or empty walkthrough → Pydantic ValidationError
- path with .. → Pydantic rejection

## Expected runtime
- lint on seeded file: <100ms
- tests: <2s total
