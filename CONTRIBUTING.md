# Contributing to ATLAS

ATLAS is built chunk-by-chunk through the **Forge orchestrator**. Every change
goes through the same pipeline: a fresh Claude session picks up one chunk from
`orchestrator/plan.yaml`, edits files, runs the quality gate, and only then is
the chunk allowed to land. Humans contribute the same way — read this guide
before opening a PR.

For project rules, the Four Laws, and schema facts, read [`CLAUDE.md`](./CLAUDE.md)
**first**. For the architecture, read [`docs/architecture.md`](./docs/architecture.md)
and [`ATLAS-DEFINITIVE-SPEC.md`](./ATLAS-DEFINITIVE-SPEC.md).

---

## 1. Ground rules (non-negotiable)

1. **Prove, never claim.** Run the tests. Show the output. Verify visually.
2. **No synthetic data.** No hardcoded mocks in production code. Ever.
3. **Backend first.** API working end-to-end before any frontend touches it.
4. **See what you build.** Open the browser. Confirm the result.

Violations are rejected at review time regardless of how clean the diff is.

### ATLAS-specific guardrails

- **Decimal, not float**, for every financial value. Money columns are
  `Numeric(20, 4)`. Internally paise; rupees only at the API boundary.
- **Indian formatting** — lakh/crore, never million/billion. IST datetimes,
  never naive.
- **No direct `de_*` queries.** ATLAS reads warehouse data exclusively through
  `backend/clients/jip_client.py`. The quality gate fails the build if a
  module imports a `de_*` table.
- **Async everywhere** in the backend — `async def` routes, SQLAlchemy 2.0
  async sessions, `asyncpg`.
- **Pydantic v2** request/response models live in `contracts/`. They are the
  single source of truth shared with the frontend.
- **Alembic** for every schema change. No raw DDL.
- **structlog** for logging. `print()` is banned in production code.

---

## 2. Repo layout

| Path | What lives here |
|------|-----------------|
| `backend/routes/` | Thin FastAPI routers; delegate to `core/` |
| `backend/core/` | Domain logic — no HTTP, no SQL imports |
| `backend/clients/jip_client.py` | The only path to JIP `/internal/*` |
| `backend/db/` | ATLAS-owned tables (`atlas_*`) |
| `backend/agents/` | Agent definitions and orchestration |
| `contracts/` | Pydantic schemas — frontend consumes these |
| `frontend/` | Next.js app (Pro / Advisor / Retail shells) |
| `alembic/` | Migrations for `atlas_*` only |
| `tests/` | `unit/` and `integration/` (integration needs JIP API up) |
| `orchestrator/` | Forge plan + runner + state DB |
| `.quality/` | Quality gate engine |
| `scripts/post-chunk.sh` | Post-chunk sync hook (commit + push + deploy + compile) |
| `docs/` | Architecture, ADRs, contributor docs |

---

## 3. Local setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn backend.main:app --port 8010 --reload
```

Frontend:
```bash
cd frontend && npm install && npm run dev
```

Tests and lint:
```bash
pytest tests/ -v --tb=short
ruff check . --select E,F,W
mypy . --ignore-missing-imports
cd frontend && npm test
```

---

## 4. The orchestrator workflow

ATLAS is built in **chunks** (`C1`, `C2`, …) defined in
`orchestrator/plan.yaml`. Each chunk has a punch list and quality targets.
The orchestrator (`orchestrator/runner.py`) runs one chunk per fresh Claude
session and persists state in `orchestrator/state.db`.

### Lifecycle of a chunk

1. **Spawn** — runner starts a fresh worker session with the chunk prompt.
2. **Step 0 — Boot context** — worker reads `CLAUDE.md`, `MEMORY.md`,
   relevant wiki articles, and only the spec sections it needs.
3. **Implement** — worker edits files in scope of the punch list. It may
   not edit `orchestrator/plan.yaml` or `.quality/standards.md`.
4. **Self-verify** — worker runs `python .quality/checks.py --gate`.
5. **Sentinel** — worker prints `FORGE_CHUNK_COMPLETE <chunk_id>`.
6. **Gate** — runner re-runs the quality gate. If it fails, the chunk goes
   back to the worker with the failing report.
7. **Post-chunk sync** — `scripts/post-chunk.sh` runs:
   - residual `git commit` of any tracked changes
   - `git push origin HEAD`
   - restart `atlas-backend.service` if installed
   - one headless Claude that runs `/forge-compile` and updates auto-memory
8. **DONE** — chunk row in `state.db` flips to DONE; next chunk may start.

A chunk is **not** DONE until git, EC2, the Forge wiki, and `MEMORY.md` all
agree. If you run a chunk outside the orchestrator, you must invoke
`scripts/post-chunk.sh <chunk_id>` manually before starting the next one.

### Running the orchestrator

```bash
python -m orchestrator.runner            # next pending chunk
python -m orchestrator.runner --chunk C7 # specific chunk
python .quality/checks.py --gate         # gate only (no run)
```

---

## 5. Quality gate

Every chunk must pass:

```bash
python .quality/checks.py --gate
```

Dimensions, weights, and floors are listed in
[`docs/architecture.md`](./docs/architecture.md#5-quality-gate-dimensions).
Per-chunk targets in `orchestrator/plan.yaml` may raise (never lower) the
floor for a specific dimension.

If the gate fails:
1. Read the per-check `evidence` and `fix` columns in the JSON report.
2. Address the root cause — never silence the check.
3. Re-run the gate. Repeat.

---

## 6. Pull requests (for human contributors)

Most changes land via the orchestrator, but humans occasionally open PRs
directly. When you do:

- **Branch** from `main`. Name it `chunk/CXX-short-slug` or
  `fix/short-slug`.
- **Scope** the diff to one chunk's punch list. Resist the urge to drive-by
  refactor — that breaks chunk isolation and confuses the gate.
- **Commit messages**: imperative mood, reference the chunk
  (`forge: C10 — README + architecture.md + CONTRIBUTING.md`).
- **Tests**: every bug fix needs a regression test that fails without the fix.
- **Run locally** before pushing:
  ```bash
  pytest tests/ -v --tb=short
  ruff check . --select E,F,W
  mypy . --ignore-missing-imports
  python .quality/checks.py --gate
  ```
- **PR description**: what changed, why, what gate score it produced,
  screenshots for any UI work.
- **Never** edit `orchestrator/plan.yaml`, `.quality/standards.md`, or
  `de_*` tables.
- **Never** commit secrets, real client data, or `.env` files.

Reviews look for: Four Laws compliance, gate pass, no scope creep,
no float in financial code, contract round-trip integrity, and the
post-chunk sync invariant.

---

## 7. Reporting bugs and security issues

- Functional bugs: open an issue with reproduction steps and the relevant
  log lines (structured logs make this painless).
- Security issues: follow [`SECURITY.md`](./SECURITY.md). Do **not** file
  them in public issues.

---

## 8. Where to ask

- Architecture questions → re-read `ATLAS-DEFINITIVE-SPEC.md` first, then
  the wiki under `~/.forge/knowledge/wiki/`.
- Build status → `BUILD_STATUS.md` and the dashboard at
  `atlas.jslwealth.in/forge`.
- Conventions → `CLAUDE.md` and the rules under `~/.claude/rules/`.

Welcome aboard.
