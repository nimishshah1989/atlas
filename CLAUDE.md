# ATLAS — Market Intelligence Engine

Operational rulebook. Not scope. Scope lives in `ATLAS-DEFINITIVE-SPEC.md`.
This file is the thing every fresh chunk session reads at Step 0 boot, so
it has to be fast to read and impossible to drift. Anything scope-shaped
that you find yourself wanting to paste in here belongs in the spec or in
`docs/architecture/`, not here.

## Four Laws (non-negotiable)

1. **Prove, never claim** — run tests, show output, verify visually
2. **No synthetic data** — ever. No hardcoded mocks in production code
3. **Backend first always** — API working before any frontend touches it
4. **See what you build** — check the browser, confirm the output

## System Guarantees (non-negotiable)

1. **Deterministic** — same `data_as_of` → same outputs for core computations
2. **Explainable** — every number traceable to source table + formula
3. **Fault-tolerant** — partial data > no data, graceful degradation
4. **Traceable** — full provenance on every computed value
5. **Idempotent** — pipelines can be re-run safely without side effects

If a feature violates any of these it MUST NOT deploy.

## Project conventions

- Financial values: `Decimal`, never `float`. Paise internal, rupees at API boundary.
- Indian formatting: lakh/crore, never million/billion. `₹` prefix.
- Dates: IST timezone-aware. Never naive `datetime`.
- API: FastAPI + Pydantic v2, all routes `async def`, all query params `Optional[..] = default`.
- DB: SQLAlchemy 2.0 async + Alembic migrations. No raw DDL. Every FK `index=True`.
- Money columns: `Numeric(20, 4)`, never `Float`.
- Logging: `structlog` with context. No `print()` in production code.
- Tests: pytest + pytest-asyncio. Every bug fix ships with a regression test.

## Test commands

```bash
pytest tests/ -v --tb=short          # backend
ruff check . --select E,F,W          # lint
mypy . --ignore-missing-imports      # type-check
cd frontend && npm test              # frontend
python .quality/checks.py            # full quality gate (7 dims)
```

## Source-of-truth pointers

- Full spec (sacrosanct): `ATLAS-DEFINITIVE-SPEC.md`
- V1 completion criteria: `docs/specs/v1-criteria.yaml` (schema-locked, product dim consumes it)
- Critical schema facts: `docs/architecture/critical-schema-facts.md`
- Data flow (JIP → compute → own): `docs/architecture/data-flow.md`
- Tech stack (fork / pip / build): `docs/architecture/tech-stack.md`
- Chunk ledger: `orchestrator/plan.yaml` + `orchestrator/state.db`
- Chunk specs: `docs/specs/chunks/`
- Quality rubric: `.quality/standards.md` (bidirectionally synced with `.quality/checks.py`)
- Memory (persistent across sessions): `~/.claude/projects/-home-ubuntu-atlas/memory/`

## Hard stop conditions

Halt and log to `BUILD_STATUS.md` immediately if you hit any of these. Do
not try to work around them:

- Attempting to write to a `de_*` table (JIP data is read-only via the client)
- Financial calculation producing `float` instead of `Decimal`
- Non-deterministic test (different result on consecutive runs)
- Schema mismatch between a Pydantic contract and its implementation
- Starting V2+ work before V1 completion criteria pass (see `v1-criteria.yaml`)

## Post-chunk sync invariant (non-negotiable)

Every chunk reaching DONE MUST leave git, EC2, wiki, and MEMORY.md in sync
before the next chunk starts. The orchestrator enforces this via
`scripts/post-chunk.sh`. Order: (1) residual `git commit` + `git push`,
(2) restart `atlas-backend.service` if installed, (3) smoke probe,
(4) `/forge-compile` into `~/.forge/knowledge/wiki/`, (5) memory sync
(`project_v15_chunk_status.md` + `MEMORY.md`). If you run a chunk outside
the orchestrator, invoke `scripts/post-chunk.sh <chunk_id>` manually. A
chunk is not DONE until all five agree.

## Chunk boot-context protocol (Step 0)

Every chunk begins with a **Step 0 — Boot context** block. Before planning
or editing anything, read in order: (1) this `CLAUDE.md`, (2) `MEMORY.md`
plus the relevant memory files (especially `project_v15_chunk_status.md`),
(3) `~/.forge/knowledge/wiki/index.md` and then only the relevant wiki
articles (not end-to-end), (4) only the sections of
`ATLAS-DEFINITIVE-SPEC.md` the punch list actually touches. A chunk that
skips Step 0 is operating on stale context and will be rejected by review.

## Context discipline

- One chunk per session. Fresh context per chunk.
- Subagents always `context: fork`. Main agent sees summaries only.
- Do NOT accumulate state across chunks. Commit, update the status memory,
  move on.
