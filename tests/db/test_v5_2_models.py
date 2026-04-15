"""Tests for V5-2 SQLAlchemy models: AtlasAgentScore, AtlasAgentWeight, AtlasAgentMemory.

Covers:
- Model instantiation (unit tests, no DB required)
- CheckConstraint definition on AtlasAgentWeight (unit)
- Column types, nullability, and Decimal usage (unit)
- Schema introspection via psycopg2 (integration — requires live DB)
- CHECK constraint enforcement (integration — DB rejects out-of-range weight)
- Alembic at head after V5-2 migration (integration)
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint


# ---------------------------------------------------------------------------
# Unit tests — no DB connection required
# ---------------------------------------------------------------------------


class TestAtlasAgentScoreModel:
    def test_instantiation_with_required_fields(self) -> None:
        """AtlasAgentScore can be instantiated with required fields."""
        from backend.db.models import AtlasAgentScore

        score = AtlasAgentScore(
            agent_id="momentum_agent",
            prediction_date=date(2026, 4, 15),
            prediction="BUY RELIANCE",
        )
        assert score.agent_id == "momentum_agent"
        assert score.prediction == "BUY RELIANCE"

    def test_optional_fields_default_to_none(self) -> None:
        """Nullable fields on AtlasAgentScore default to None in Python."""
        from backend.db.models import AtlasAgentScore

        score = AtlasAgentScore(
            agent_id="test_agent",
            prediction_date=date(2026, 4, 1),
            prediction="SELL HDFC",
        )
        assert score.entity is None
        assert score.evaluation_date is None
        assert score.actual_outcome is None
        assert score.accuracy_score is None

    def test_accuracy_score_accepts_decimal(self) -> None:
        """accuracy_score should store Decimal values (Numeric(5,4) column)."""
        from backend.db.models import AtlasAgentScore

        score = AtlasAgentScore(
            agent_id="test_agent",
            prediction_date=date(2026, 4, 1),
            prediction="BUY INFY",
            accuracy_score=Decimal("0.8750"),
        )
        assert score.accuracy_score == Decimal("0.8750")

    def test_tablename(self) -> None:
        from backend.db.models import AtlasAgentScore

        assert AtlasAgentScore.__tablename__ == "atlas_agent_scores"

    def test_agent_id_column_is_indexed(self) -> None:
        """agent_id column on atlas_agent_scores must be indexed."""
        from backend.db.models import AtlasAgentScore

        # Check that there's an index on this column
        indexes = {idx.name for idx in AtlasAgentScore.__table__.indexes}
        # Column-level index=True creates an index named ix_<table>_<col>
        assert any("agent_id" in name for name in indexes), (
            f"Expected index on agent_id, found indexes: {indexes}"
        )


class TestAtlasAgentWeightModel:
    def test_instantiation(self) -> None:
        """AtlasAgentWeight can be instantiated with agent_id."""
        from backend.db.models import AtlasAgentWeight

        w = AtlasAgentWeight(agent_id="momentum_agent", weight=Decimal("1.2"))
        assert w.agent_id == "momentum_agent"
        assert w.weight == Decimal("1.2")

    def test_tablename(self) -> None:
        from backend.db.models import AtlasAgentWeight

        assert AtlasAgentWeight.__tablename__ == "atlas_agent_weights"

    def test_check_constraint_exists(self) -> None:
        """atlas_agent_weights must have ck_agent_weight_range CheckConstraint."""
        from backend.db.models import AtlasAgentWeight

        constraints = AtlasAgentWeight.__table__.constraints
        check_constraints = [c for c in constraints if isinstance(c, CheckConstraint)]
        assert check_constraints, "No CheckConstraint found on atlas_agent_weights"

        constraint_names = [c.name for c in check_constraints]
        assert "ck_agent_weight_range" in constraint_names, (
            f"ck_agent_weight_range not found, got: {constraint_names}"
        )

    def test_check_constraint_expression_covers_bounds(self) -> None:
        """CHECK constraint text must cover both 0.3 lower bound and 2.5 upper bound."""
        from backend.db.models import AtlasAgentWeight

        constraints = AtlasAgentWeight.__table__.constraints
        check_constraints = [
            c
            for c in constraints
            if isinstance(c, CheckConstraint) and c.name == "ck_agent_weight_range"
        ]
        assert check_constraints, "ck_agent_weight_range not found"
        expr_text = str(check_constraints[0].sqltext)
        assert "0.3" in expr_text, f"Lower bound 0.3 not in constraint: {expr_text}"
        assert "2.5" in expr_text, f"Upper bound 2.5 not in constraint: {expr_text}"

    def test_rolling_accuracy_nullable(self) -> None:
        """rolling_accuracy is nullable — no data yet is valid."""
        from backend.db.models import AtlasAgentWeight

        w = AtlasAgentWeight(agent_id="new_agent", weight=Decimal("1.0"))
        assert w.rolling_accuracy is None

    def test_weight_numeric_column_type(self) -> None:
        """weight column must be Numeric (not Float) per financial domain rules."""
        from backend.db.models import AtlasAgentWeight
        from sqlalchemy import Numeric as SANumeric

        weight_col = AtlasAgentWeight.__table__.c["weight"]
        assert isinstance(weight_col.type, SANumeric), (
            f"weight column type is {type(weight_col.type)}, expected Numeric"
        )

    def test_soft_delete_columns_present(self) -> None:
        """is_deleted and deleted_at must be present per project conventions."""
        from backend.db.models import AtlasAgentWeight

        cols = {c.name for c in AtlasAgentWeight.__table__.columns}
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_standard_timestamp_columns_present(self) -> None:
        """created_at and updated_at must be present per database.md conventions."""
        from backend.db.models import AtlasAgentWeight

        cols = {c.name for c in AtlasAgentWeight.__table__.columns}
        assert "created_at" in cols
        assert "updated_at" in cols


class TestAtlasAgentMemoryModel:
    def test_instantiation(self) -> None:
        """AtlasAgentMemory can be instantiated with required fields."""
        from backend.db.models import AtlasAgentMemory

        mem = AtlasAgentMemory(
            agent_id="momentum_agent",
            memory_type="correction",
            content="Avoid FMCG in Q3 monsoon season.",
        )
        assert mem.agent_id == "momentum_agent"
        assert mem.memory_type == "correction"
        assert mem.content == "Avoid FMCG in Q3 monsoon season."

    def test_tablename(self) -> None:
        from backend.db.models import AtlasAgentMemory

        assert AtlasAgentMemory.__tablename__ == "atlas_agent_memory"

    def test_agent_id_column_is_indexed(self) -> None:
        """agent_id column on atlas_agent_memory must be indexed."""
        from backend.db.models import AtlasAgentMemory

        indexes = {idx.name for idx in AtlasAgentMemory.__table__.indexes}
        assert any("agent_id" in name for name in indexes), (
            f"Expected index on agent_id, found indexes: {indexes}"
        )

    def test_soft_delete_and_timestamps_present(self) -> None:
        """Standard columns must be present per database.md conventions."""
        from backend.db.models import AtlasAgentMemory

        cols = {c.name for c in AtlasAgentMemory.__table__.columns}
        assert "is_deleted" in cols
        assert "deleted_at" in cols
        assert "created_at" in cols
        assert "updated_at" in cols


# ---------------------------------------------------------------------------
# Integration tests — require live DB + migrations applied
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_conn():
    """Sync psycopg2 connection for schema introspection tests."""
    raw_url = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://jip_admin:JipDataEngine2026Secure@jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432/data_engine",
    ).replace("postgresql+psycopg2://", "postgresql://")
    import psycopg2  # type: ignore[import-untyped]

    conn = psycopg2.connect(raw_url)
    yield conn
    conn.close()


def _get_columns(conn, table_name: str) -> dict:
    """Return {column_name: (data_type, is_nullable)} for a table."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    rows = cur.fetchall()
    cur.close()
    return {r[0]: (r[1], r[2]) for r in rows}


class TestAtlasAgentScoresSchema:
    def test_table_exists(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_scores")
        assert cols, "atlas_agent_scores table does not exist or has no columns"

    def test_required_columns_exist(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_scores")
        for col in ["id", "agent_id", "prediction_date", "prediction", "created_at", "updated_at"]:
            assert col in cols, f"Missing column: {col}"

    def test_accuracy_score_is_numeric(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_scores")
        assert cols["accuracy_score"][0] == "numeric", (
            f"accuracy_score should be numeric, got: {cols['accuracy_score'][0]}"
        )

    def test_soft_delete_columns(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_scores")
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_no_float_columns(self, pg_conn) -> None:
        """No real/double precision columns — all numeric columns must use Numeric."""
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'atlas_agent_scores'
              AND data_type IN ('real', 'double precision')
            """
        )
        float_cols = cur.fetchall()
        cur.close()
        assert float_cols == [], f"Float columns found: {float_cols}"

    def test_count_starts_at_zero(self, pg_conn) -> None:
        """New table must be empty — no synthetic data (Four Laws)."""
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM atlas_agent_scores")
        count = cur.fetchone()[0]
        cur.close()
        assert count == 0, f"Expected 0 rows, got {count}"


class TestAtlasAgentWeightsSchema:
    def test_table_exists(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_weights")
        assert cols, "atlas_agent_weights table does not exist or has no columns"

    def test_required_columns_exist(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_weights")
        for col in ["agent_id", "weight", "rolling_accuracy", "mutation_count", "updated_at"]:
            assert col in cols, f"Missing column: {col}"

    def test_weight_is_numeric(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_weights")
        assert cols["weight"][0] == "numeric", f"weight should be numeric, got: {cols['weight'][0]}"

    def test_check_constraint_rejects_weight_below_range(self, pg_conn) -> None:
        """weight=0.2 must be rejected by CHECK constraint (below 0.3 minimum)."""
        import psycopg2  # type: ignore[import-untyped]

        cur = pg_conn.cursor()
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                "INSERT INTO atlas_agent_weights (agent_id, weight) VALUES (%s, %s)",
                ("test_reject_low", "0.2"),
            )
            pg_conn.commit()
        pg_conn.rollback()
        cur.close()

    def test_check_constraint_rejects_weight_above_range(self, pg_conn) -> None:
        """weight=3.0 must be rejected by CHECK constraint (above 2.5 maximum)."""
        import psycopg2  # type: ignore[import-untyped]

        cur = pg_conn.cursor()
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                "INSERT INTO atlas_agent_weights (agent_id, weight) VALUES (%s, %s)",
                ("test_reject_high", "3.0"),
            )
            pg_conn.commit()
        pg_conn.rollback()
        cur.close()

    def test_check_constraint_accepts_boundary_values(self, pg_conn) -> None:
        """weight=0.3 and weight=2.5 must be accepted (boundary values are valid)."""
        cur = pg_conn.cursor()
        try:
            cur.execute(
                "INSERT INTO atlas_agent_weights (agent_id, weight) VALUES (%s, %s)",
                ("__test_boundary_low__", "0.3"),
            )
            cur.execute(
                "INSERT INTO atlas_agent_weights (agent_id, weight) VALUES (%s, %s)",
                ("__test_boundary_high__", "2.5"),
            )
            pg_conn.commit()
            # Verify they were inserted
            cur.execute(
                "SELECT COUNT(*) FROM atlas_agent_weights WHERE agent_id IN (%s, %s)",
                ("__test_boundary_low__", "__test_boundary_high__"),
            )
            count = cur.fetchone()[0]
            assert count == 2, f"Expected 2 boundary rows, got {count}"
        finally:
            # Cleanup — remove test rows
            cur.execute(
                "DELETE FROM atlas_agent_weights WHERE agent_id IN (%s, %s)",
                ("__test_boundary_low__", "__test_boundary_high__"),
            )
            pg_conn.commit()
            cur.close()

    def test_count_starts_at_zero(self, pg_conn) -> None:
        """Table should be empty except for any test rows (none persisted)."""
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM atlas_agent_weights WHERE agent_id NOT LIKE '%__test%'")
        count = cur.fetchone()[0]
        cur.close()
        assert count == 0, f"Expected 0 non-test rows, got {count}"


class TestAtlasAgentMemorySchema:
    def test_table_exists(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_memory")
        assert cols, "atlas_agent_memory table does not exist or has no columns"

    def test_required_columns_exist(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_memory")
        for col in ["id", "agent_id", "memory_type", "content", "created_at"]:
            assert col in cols, f"Missing column: {col}"

    def test_soft_delete_columns(self, pg_conn) -> None:
        cols = _get_columns(pg_conn, "atlas_agent_memory")
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_count_starts_at_zero(self, pg_conn) -> None:
        """New table must be empty — no synthetic data."""
        cur = pg_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM atlas_agent_memory")
        count = cur.fetchone()[0]
        cur.close()
        assert count == 0, f"Expected 0 rows, got {count}"


class TestHNSWIndexExists:
    def test_hnsw_index_on_atlas_intelligence(self, pg_conn) -> None:
        """HNSW index must exist on atlas_intelligence.embedding."""
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'atlas_intelligence'
              AND indexname IN ('idx_intel_embedding_hnsw', 'idx_intelligence_embedding')
            """
        )
        rows = cur.fetchall()
        cur.close()
        index_names = {r[0] for r in rows}
        assert index_names, (
            "No HNSW index found on atlas_intelligence — "
            "expected idx_intel_embedding_hnsw or idx_intelligence_embedding"
        )


class TestV52AlembicMigration:
    def test_alembic_at_head_after_v5_2(self, pg_conn) -> None:
        """Atlas alembic version must be at the V5-2 head after migration."""
        from alembic.config import Config  # type: ignore[import-untyped]
        from alembic.script import ScriptDirectory  # type: ignore[import-untyped]

        cfg = Config("/home/ubuntu/atlas/alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        expected_head = script.get_heads()[0]

        cur = pg_conn.cursor()
        cur.execute("SELECT version_num FROM atlas_alembic_version")
        rows = cur.fetchall()
        cur.close()
        versions = [r[0] for r in rows]
        assert expected_head in versions, (
            f"Expected alembic head {expected_head} in versions, got: {versions}"
        )

    def test_v5_2_revision_is_head(self) -> None:
        """Latest alembic revision must be the single head."""
        from alembic.config import Config  # type: ignore[import-untyped]
        from alembic.script import ScriptDirectory  # type: ignore[import-untyped]

        cfg = Config("/home/ubuntu/atlas/alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert len(heads) == 1, f"Expected 1 alembic head, got: {heads}"
        assert heads[0] == "a8b9c0d1e2f3", f"Expected head a8b9c0d1e2f3, got: {heads[0]}"
