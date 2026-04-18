# Chunk V10-1 Approach: atlas_qlib_features + atlas_qlib_signals + atlas_events

## Data scale
All atlas_* tables currently at 0 rows (brand new). Existing atlas_tv_cache has 3 rows, atlas_portfolios 1527 rows.
No JIP de_* tables touched — this chunk is DB schema only.
Expected runtime: <1s for migration (DDL only), <5s for tests.

## Chosen approach
Hand-written Alembic migration (not autogenerate) per project pattern.
Reason: autogenerate would scan full schema and propose spurious drops on existing tables.
Pattern: Follow j7k8l9m0n1o2 migration (V7-0) exactly — op.create_table + op.create_index.

## Three tables

### atlas_qlib_features
- UUID id PK (project convention overrides spec composite PK)
- UNIQUE constraint on (date, instrument_id) — enforces spec PK semantics
- instrument_id UUID, index=True (FK convention)
- features JSONB (spec DDL)
- Standard: created_at, updated_at (tz-aware), is_deleted, deleted_at

### atlas_qlib_signals
- UUID id PK
- UNIQUE on (date, instrument_id, model_name)
- instrument_id UUID, index=True
- signal_score Numeric(20,4) per "money column convention for numeric"
- features_used JSONB
- Standard audit columns

### atlas_events
- UUID id PK
- event_type VARCHAR(50), indexed
- entity TEXT nullable
- entity_type VARCHAR(20), indexed
- payload JSONB NOT NULL
- severity VARCHAR(20) server_default='medium'
- data_as_of DATE, indexed
- suggested_action TEXT nullable
- related_event_ids JSONB nullable
- is_delivered BOOLEAN server_default false
- Standard audit columns + soft delete

## Wiki patterns checked
- [Alembic Autogenerate Index Drift](bug-patterns/alembic-autogenerate-index-drift.md) — hand-write migration
- [mypy attr-defined on Alembic](bug-patterns/alembic-mypy-attr-defined.md) — type: ignore[attr-defined]
- [AST-Scanned Anti-Pattern Detection](patterns/ast-scanned-anti-pattern-detection.md) — used in tests

## Existing code reused
- ORM Base from backend/db/models.py (DeclarativeBase)
- Pattern: backend/db/gold_rs_models.py (separate file, UUID type, DateTime, Numeric)
- Migration pattern: alembic/versions/j7k8l9m0n1o2_v7_0_atlas_gold_rs_cache.py
- Test pattern: tests/db/test_v5_2_models.py (unit + integration structure)

## Model import strategy
The separate ORM files (tv_models.py, gold_rs_models.py) are NOT imported in env.py —
they are imported at usage sites (services/routes). For hand-written migrations this is fine
since the migration SQL is explicit. The new qlib_models.py follows the same pattern.

## Edge cases
- UUID instrument_id is NOT a FK constraint (de_instrument is JIP read-only) — just a typed UUID column
- Decimal in JSONB (features dict) must be serialized before persistence — documented in tests
- NULL handling: signal_score nullable, all optional fields explicitly nullable
- is_delivered defaulting false — tracked in migration via server_default

## Expected runtime
- Alembic upgrade: <2s (DDL only, 3 CREATE TABLE + ~6 CREATE INDEX)
- pytest tests/db/test_qlib_models.py: <5s (unit tests, integration tests skipped in gate)
