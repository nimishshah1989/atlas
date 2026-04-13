# Chunk V1-3 Approach: Intelligence Writer Service + API Routes

## Data Scale
- atlas_intelligence: 0 rows (fresh table, no migration risk)
- atlas_decisions: 0 rows
- de_* tables: read-only JIP data, not touched

## Chosen Approach

### Migration
Add a unique index (not constraint) via `op.execute()` raw SQL for COALESCE expression support:
```sql
CREATE UNIQUE INDEX uq_intel_natural_key 
ON atlas_intelligence (agent_id, COALESCE(entity, ''), title, data_as_of)
WHERE is_deleted = false
```
Since entity is nullable but store_finding always supplies it, a simple non-partial unique index on (agent_id, entity, title, data_as_of) WHERE entity IS NOT NULL is clean. But we use COALESCE to handle the case uniformly.

The ON CONFLICT approach uses pg_insert with index_elements — but with a functional index (COALESCE), SQLAlchemy ON CONFLICT needs the constraint name. We'll use:
- `on_conflict_do_update(constraint='uq_intel_natural_key', set_={...})` 

Wait — SQLAlchemy pg_insert on_conflict_do_update with a named constraint works. We'll name the index so we can reference it.

Actually for functional indexes, pg_insert needs `index_elements` that SQLAlchemy can match OR a named `constraint=`. Since we're using op.execute() raw SQL, the index will be named `uq_intel_natural_key`. We'll reference it by constraint name.

### Service (backend/services/intelligence.py)
- `store_finding()`: embed text, pg_insert ON CONFLICT DO UPDATE with named constraint
- `get_relevant_intelligence()`: embed query, cosine distance ordering via pgvector

### Routes (backend/routes/intelligence.py)
- POST /api/v1/intelligence/findings
- GET /api/v1/intelligence/search
- GET /api/v1/intelligence/findings
- GET /api/v1/intelligence/findings/{finding_id}

### Wiki Patterns Used
- Idempotent Upsert (ON CONFLICT DO UPDATE) — wiki/patterns/idempotent-upsert.md
- pgvector NULL Type Mismatch — avoid ORM embedding=None fallback; pgvector IS installed

### Edge Cases
- entity can be NULL in model; use COALESCE in index
- confidence: always Decimal, never float; stored as Numeric(5,4)
- data_as_of: must be IST-aware datetime
- evidence dict: Decimal values must be serialized before JSONB insert (wiki: decimal-in-jsonb-persist)
- embedding generation failure: raise, don't silently skip
- expires_at: computed from data_as_of + timedelta(hours=expires_hours)
- Expired findings filtered from search results

### Test Strategy
- Unit tests mock DB + embedding service
- Integration tests (skip if DB unreachable) for idempotent upsert + vector ordering
- p95 test: insert 1k rows, time 10 consecutive API calls
- EXPLAIN test: look for "hnsw" in query plan

### Expected Runtime
- store_finding: ~50ms (embedding call + single upsert)
- get_relevant_intelligence: ~20ms warm (HNSW index, 1k rows)
- p95 API: should be well under 300ms for 1k rows

## Existing Code Reused
- backend/db/models.py: AtlasIntelligence ORM
- backend/services/embedding.py: embed() function
- backend/db/session.py: get_db() 
- backend/models/schemas.py: ResponseMeta, extend with intelligence schemas
- backend/routes/decisions.py: pattern reference for route structure
