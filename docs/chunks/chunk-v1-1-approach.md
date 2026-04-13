# Chunk V1-1 Approach: atlas_intelligence + atlas_decisions Schema Parity

## Data Scale
- atlas_intelligence: 0 rows (empty — no data migration needed)
- atlas_decisions: 0 rows (empty — no data migration needed)
- atlas_watchlists: 0 rows (empty)

Since both tables are empty, we can safely drop and recreate columns without data migration guards. However, we still write proper upgrade/downgrade logic for correctness.

## Chosen Approach

### Why manual migration over autogenerate
Autogenerate would produce DROP+ADD for renamed columns (losing clarity). We write a manual migration using `op.rename_column()` where possible and explicit DDL for new columns. This keeps intent clear and the downgrade reversible.

### atlas_intelligence changes summary
- Rename: `agent_name` → `agent_id` (VARCHAR(100))
- Rename: `entity_id` → `entity` (TEXT)
- Add: `agent_type VARCHAR(50) NOT NULL DEFAULT ''`
- Alter: `entity_type` VARCHAR(30) → VARCHAR(20), make nullable
- Alter: `title` VARCHAR(255) → TEXT
- Alter: `confidence` NUMERIC(5,2) → NUMERIC(5,4)
- Rename: `metadata` → `evidence` (JSONB)
- Add: `tags TEXT[] DEFAULT '{}'`
- Alter: `data_as_of` NOT NULL (safe — 0 rows)
- Add: `expires_at TIMESTAMPTZ`
- Add: `is_validated BOOLEAN NOT NULL DEFAULT FALSE`
- Add: `validation_result JSONB`
- Keep: `is_deleted`, `deleted_at` (project convention)
- Drop old indexes, create spec indexes (including HNSW on embedding)

### atlas_decisions changes summary
- Rename: `symbol` → `entity` (TEXT)
- Drop: `instrument_id`
- Drop: `signal` column + enum
- Add: `decision_type VARCHAR(30) NOT NULL DEFAULT 'HOLD'`
- Add: `entity_type VARCHAR(20) NOT NULL DEFAULT 'equity'`
- Rename: `reason` → `rationale`
- Rename: `pillar_data` → `supporting_data`
- Alter: `supporting_data` NOT NULL DEFAULT '{}'
- Alter: `confidence` NUMERIC(5,2) → NUMERIC(5,4), NOT NULL DEFAULT 0
- Add: `source_agent VARCHAR(100)`
- Drop: `horizon_days`
- Add: `horizon VARCHAR(20) NOT NULL DEFAULT '3m'`
- Add: `horizon_end_date DATE NOT NULL DEFAULT CURRENT_DATE`
- Add: `invalidation_conditions TEXT[]`
- Add: `status VARCHAR(20) NOT NULL DEFAULT 'active'`
- Drop: `quadrant`, `previous_quadrant`
- Add: `invalidated_at TIMESTAMPTZ`
- Add: `invalidation_reason TEXT`
- Add: `outcome JSONB`
- Rename: `action` → `user_action` (VARCHAR, drop SAEnum)
- Rename: `action_at` → `user_action_at`
- Rename: `action_note` → `user_notes`
- Add: `data_as_of DATE NOT NULL DEFAULT CURRENT_DATE`
- Keep: `is_deleted`, `deleted_at`
- Drop old indexes, create spec indexes

## Wiki Patterns Checked
- `alembic-mypy-attr-defined` — use `# type: ignore[attr-defined]` on alembic imports
- `paired-test-commit-law` — must pair test file with every .py source change

## Existing Code Reused
- `pgvector.sqlalchemy.Vector` already imported in models.py
- `JSONB`, `UUID` from `sqlalchemy.dialects.postgresql` already in use
- `DeclarativeBase`, `mapped_column` pattern already established

## Edge Cases
- Both tables empty — no data guards needed but defaults set anyway
- pgvector HNSW index requires `CREATE INDEX ... USING hnsw` with specific ops/params
- `TEXT[]` requires `ARRAY(Text)` from SQLAlchemy
- Drop SAEnum types in downgrade requires `sa.Enum.drop()`
- `action` column currently has SAEnum type — must convert back to VARCHAR first before rename

## Expected Runtime
- Migration: < 5 seconds (empty tables, just DDL)
- Tests: < 30 seconds
- Full test suite: < 2 minutes

## Files Modified
1. `backend/db/models.py` — rewrite AtlasDecision + AtlasIntelligence models
2. `backend/models/schemas.py` — update decision schemas
3. `backend/routes/decisions.py` — update column references
4. `alembic/versions/<rev>_v1_1_schema_parity.py` — new migration
5. `tests/db/test_intelligence_schema.py` — new test file
