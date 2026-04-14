# V4-1 Approach: Portfolio Foundations

## Data scale
- All production tables are de_* (JIP read-only) — 14.7M rows in de_rs_scores
- V4 creates new atlas_* tables — starting at 0 rows
- No query scale concerns: schema/ORM/stub chunk only

## Chosen approach
- Follow V3-1 exactly: mapped_column() ORM, idempotent Alembic migration, Pydantic v2 contracts, FastAPI route stubs
- 4 new tables: atlas_portfolios, atlas_portfolio_holdings, atlas_scheme_mapping_overrides, atlas_portfolio_snapshots
- Route stubs return 501 for complex operations; basic CRUD wired via PortfolioRepo
- AST-scan quality checks (v4) mirror v3 pattern exactly

## Wiki patterns checked
- [Criteria-as-YAML Executable Gate](../wiki/patterns/criteria-as-yaml-quality-gate.md) — schema-locked YAML + check registry
- [AST-Scanned Anti-Pattern Detection](../wiki/patterns/ast-scanned-anti-pattern-detection.md) — ast.parse+walk for float/print
- [FastAPI Static Route Before Path Param](../wiki/bug-patterns/fastapi-static-route-before-path-param.md) — /import-cams and /create must register before /{id}
- [Alembic Mypy attr-defined](../wiki/bug-patterns/alembic-mypy-attr-defined.md) — type: ignore[attr-defined] on alembic.op

## Existing code reused
- ORM pattern: backend/db/models.py (mapped_column, UUID pk, func.now, soft-delete)
- Migration pattern: alembic/versions/2d156b12ed5f_v3_1_atlas_simulations.py (idempotent check, _create_index_if_not_exists)
- Repo pattern: backend/services/simulation/repo.py (AsyncSession, select, flush)
- Quality checks pattern: .quality/quality_product_checks_v3.py (AST scan callables)
- Criteria format: docs/specs/v3-criteria.yaml

## Edge cases
- JSONB fields (analysis_cache, sector_weights, quadrant_distribution): Decimal-in-JSONB bug — sanitize at persist boundary (bug-pattern)
- FK indexes: ALL FKs must have index=True
- Unique partial index for snapshot: one snapshot per portfolio per non-deleted date
- Route ordering: /import-cams, /create before /{id} to avoid path param capture
- down_revision: 64e4b418add2 (add_drift_history_to_atlas_simulations — latest)

## Expected runtime
- Alembic migration: <2s (DDL only, no data migration)
- Tests: <10s (all mocked/unit tests)
- Server startup: unchanged (no new heavy init)
