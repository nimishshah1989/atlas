# Chunk V5-1 Approach: Pin V5 deps + enable pgvector extension

## Data scale
No data-scale concerns. This chunk adds infrastructure files only.
- No atlas_* table queries needed
- pgvector extension already exists in RDS (confirmed by chunk spec)
- 7 existing alembic migrations, current head: `a1b2c3d4e5f6`

## Approach

### 1. backend/requirements.txt
Simple single-line file that delegates to root requirements.txt via pip's `-r` include syntax.
- `pip install -r backend/requirements.txt` will resolve to root file's packages
- No symlink (avoids cross-platform issues)

### 2. Alembic migration
Revision ID: `e5f6a7b8c9d0` (follows the pattern of existing hex IDs in this project)
Down revision: `a1b2c3d4e5f6` (current head)
- upgrade(): `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` — idempotent, safe to run on existing prod DB
- downgrade(): `op.execute("DROP EXTENSION IF EXISTS vector")` — destructive but correct
- `from alembic import op  # type: ignore[attr-defined]` per wiki pattern

### 3. Test file
`tests/unit/test_v5_1_pgvector_deps.py` — unit tests (no real DB):
- Test pgvector is importable
- Test root requirements.txt contains pgvector line
- Test backend/requirements.txt exists and contains `-r ../requirements.txt`
- Test migration file exists and contains CREATE EXTENSION

## Wiki patterns checked
- [Alembic Mypy attr-defined] — `# type: ignore[attr-defined]` on import line, not broader
- [Alembic Stamp Before Upgrade] — existing DB already has extension; IF NOT EXISTS handles gracefully
- [Two-Phase Vector Write] — noted for future V5 chunks using pgvector columns

## Existing code reused
- Migration pattern from `a1b2c3d4e5f6_v4_1_atlas_portfolios.py` — same structure

## Edge cases
- Extension already exists in prod: `IF NOT EXISTS` makes upgrade idempotent
- Root requirements.txt missing pgvector: already confirmed present (line 11)
- backend/requirements.txt already exists: it does NOT (confirmed)

## Expected runtime
- pip install: ~30 seconds (cached packages)
- alembic upgrade: <1 second (single DDL statement, no-op if extension exists)
- pytest: <2 seconds (all unit tests, no DB calls)
