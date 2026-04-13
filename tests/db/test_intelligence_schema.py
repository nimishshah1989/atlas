"""Schema verification tests for atlas_intelligence and atlas_decisions.

Tests that both tables exist with correct columns, types, and indexes after
the v1_1_schema_parity migration. Uses psycopg2 sync connection — no ORM
dependency so these tests catch ORM/DB divergence.
"""

from __future__ import annotations

import os

import psycopg2
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_conn():
    """Sync psycopg2 connection for schema introspection tests."""
    raw_url = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg2://jip_admin:JipDataEngine2026Secure@jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432/data_engine",
    ).replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(raw_url)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def intel_cols(pg_conn) -> dict:
    """Returns {column_name: (data_type, is_nullable)} for atlas_intelligence."""
    cur = pg_conn.cursor()
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'atlas_intelligence'
        ORDER BY ordinal_position
        """
    )
    rows = cur.fetchall()
    cur.close()
    return {r[0]: (r[1], r[2]) for r in rows}


@pytest.fixture(scope="module")
def decision_cols(pg_conn) -> dict:
    """Returns {column_name: (data_type, is_nullable)} for atlas_decisions."""
    cur = pg_conn.cursor()
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'atlas_decisions'
        ORDER BY ordinal_position
        """
    )
    rows = cur.fetchall()
    cur.close()
    return {r[0]: (r[1], r[2]) for r in rows}


@pytest.fixture(scope="module")
def pg_indexes(pg_conn) -> set:
    """Returns set of index names across both tables."""
    cur = pg_conn.cursor()
    cur.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE tablename IN ('atlas_intelligence', 'atlas_decisions')
        """
    )
    rows = cur.fetchall()
    cur.close()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# atlas_intelligence column tests
# ---------------------------------------------------------------------------


class TestAtlasIntelligenceColumns:
    def test_agent_id_exists_and_not_nullable(self, intel_cols: dict) -> None:
        """agent_name was renamed to agent_id, must be NOT NULL."""
        assert "agent_id" in intel_cols, "agent_id column missing"
        assert intel_cols["agent_id"][1] == "NO", "agent_id must be NOT NULL"

    def test_agent_type_exists_and_not_nullable(self, intel_cols: dict) -> None:
        """New column agent_type must exist and be NOT NULL."""
        assert "agent_type" in intel_cols, "agent_type column missing"
        assert intel_cols["agent_type"][1] == "NO", "agent_type must be NOT NULL"

    def test_entity_column_exists(self, intel_cols: dict) -> None:
        """entity_id was renamed to entity (TEXT, nullable)."""
        assert "entity" in intel_cols, "entity column missing"
        assert intel_cols["entity"][0] == "text", "entity must be TEXT"

    def test_entity_id_column_dropped(self, intel_cols: dict) -> None:
        """Old entity_id column should not exist."""
        assert "entity_id" not in intel_cols, "entity_id was not renamed"

    def test_agent_name_column_dropped(self, intel_cols: dict) -> None:
        """Old agent_name column should not exist."""
        assert "agent_name" not in intel_cols, "agent_name was not renamed"

    def test_evidence_column_exists(self, intel_cols: dict) -> None:
        """metadata was renamed to evidence."""
        assert "evidence" in intel_cols, "evidence column missing"
        assert "metadata" not in intel_cols, "old metadata column still exists"

    def test_title_is_text(self, intel_cols: dict) -> None:
        """title must be TEXT not VARCHAR(255)."""
        assert "title" in intel_cols
        col_type = intel_cols["title"][0]
        assert col_type == "text", f"title type is {col_type}"

    def test_confidence_is_numeric(self, intel_cols: dict) -> None:
        """confidence must be numeric (Decimal), not float."""
        assert "confidence" in intel_cols
        assert intel_cols["confidence"][0] == "numeric", "confidence must be NUMERIC"

    def test_tags_array_exists(self, intel_cols: dict) -> None:
        """New tags TEXT[] column must exist."""
        assert "tags" in intel_cols, "tags column missing"
        assert intel_cols["tags"][0] == "ARRAY", "tags must be ARRAY type"

    def test_data_as_of_not_nullable(self, intel_cols: dict) -> None:
        """data_as_of must be NOT NULL per spec."""
        assert "data_as_of" in intel_cols
        assert intel_cols["data_as_of"][1] == "NO", "data_as_of must be NOT NULL"

    def test_expires_at_exists_nullable(self, intel_cols: dict) -> None:
        """New expires_at column must exist and be nullable."""
        assert "expires_at" in intel_cols, "expires_at column missing"
        assert intel_cols["expires_at"][1] == "YES", "expires_at should be nullable"

    def test_is_validated_not_nullable(self, intel_cols: dict) -> None:
        """New is_validated column must exist and be NOT NULL."""
        assert "is_validated" in intel_cols, "is_validated column missing"
        assert intel_cols["is_validated"][1] == "NO", "is_validated must be NOT NULL"

    def test_validation_result_exists(self, intel_cols: dict) -> None:
        """New validation_result JSONB column must exist."""
        assert "validation_result" in intel_cols, "validation_result column missing"

    def test_soft_delete_columns_present(self, intel_cols: dict) -> None:
        """is_deleted + deleted_at must remain per project convention."""
        assert "is_deleted" in intel_cols
        assert "deleted_at" in intel_cols

    def test_no_float_columns(self, pg_conn) -> None:
        """No real/double precision columns — all financials must be Numeric."""
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'atlas_intelligence'
              AND data_type IN ('real', 'double precision')
            """
        )
        float_cols = cur.fetchall()
        cur.close()
        assert float_cols == [], (
            f"Float columns found in atlas_intelligence: {float_cols}"
        )


# ---------------------------------------------------------------------------
# atlas_decisions column tests
# ---------------------------------------------------------------------------


class TestAtlasDecisionsColumns:
    def test_entity_column_exists(self, decision_cols: dict) -> None:
        """symbol was renamed to entity (TEXT)."""
        assert "entity" in decision_cols
        assert decision_cols["entity"][0] == "text"

    def test_symbol_column_dropped(self, decision_cols: dict) -> None:
        """Old symbol column should not exist."""
        assert "symbol" not in decision_cols, "symbol was not renamed"

    def test_decision_type_not_nullable(self, decision_cols: dict) -> None:
        """decision_type replaces signal and must be NOT NULL."""
        assert "decision_type" in decision_cols
        assert decision_cols["decision_type"][1] == "NO"

    def test_signal_column_dropped(self, decision_cols: dict) -> None:
        """Old signal column should not exist."""
        assert "signal" not in decision_cols, "signal was not renamed"

    def test_entity_type_not_nullable(self, decision_cols: dict) -> None:
        """New entity_type column must be NOT NULL."""
        assert "entity_type" in decision_cols
        assert decision_cols["entity_type"][1] == "NO"

    def test_rationale_not_nullable(self, decision_cols: dict) -> None:
        """reason was renamed to rationale, must be NOT NULL."""
        assert "rationale" in decision_cols
        assert decision_cols["rationale"][1] == "NO"
        assert "reason" not in decision_cols, "old reason column still exists"

    def test_supporting_data_not_nullable(self, decision_cols: dict) -> None:
        """pillar_data renamed to supporting_data, NOT NULL."""
        assert "supporting_data" in decision_cols
        assert decision_cols["supporting_data"][1] == "NO"
        assert "pillar_data" not in decision_cols

    def test_confidence_is_numeric_not_nullable(self, decision_cols: dict) -> None:
        """confidence must be NUMERIC and NOT NULL."""
        assert "confidence" in decision_cols
        assert decision_cols["confidence"][0] == "numeric"
        assert decision_cols["confidence"][1] == "NO"

    def test_horizon_not_nullable(self, decision_cols: dict) -> None:
        """horizon_days was replaced by horizon VARCHAR NOT NULL."""
        assert "horizon" in decision_cols
        assert decision_cols["horizon"][1] == "NO"
        assert "horizon_days" not in decision_cols

    def test_horizon_end_date_not_nullable(self, decision_cols: dict) -> None:
        """horizon_end_date DATE NOT NULL must exist."""
        assert "horizon_end_date" in decision_cols
        assert decision_cols["horizon_end_date"][1] == "NO"
        assert decision_cols["horizon_end_date"][0] == "date"

    def test_status_not_nullable(self, decision_cols: dict) -> None:
        """status must be NOT NULL with default 'active'."""
        assert "status" in decision_cols
        assert decision_cols["status"][1] == "NO"

    def test_dropped_columns_gone(self, decision_cols: dict) -> None:
        """instrument_id, quadrant, previous_quadrant must be dropped."""
        assert "instrument_id" not in decision_cols
        assert "quadrant" not in decision_cols
        assert "previous_quadrant" not in decision_cols

    def test_user_action_columns_renamed(self, decision_cols: dict) -> None:
        """action/action_at/action_note renamed to user_action/user_action_at/user_notes."""  # noqa: E501
        assert "user_action" in decision_cols
        assert "user_action_at" in decision_cols
        assert "user_notes" in decision_cols
        assert "action" not in decision_cols
        assert "action_at" not in decision_cols
        assert "action_note" not in decision_cols

    def test_data_as_of_date_not_nullable(self, decision_cols: dict) -> None:
        """data_as_of DATE NOT NULL must exist on decisions."""
        assert "data_as_of" in decision_cols
        assert decision_cols["data_as_of"][0] == "date"
        assert decision_cols["data_as_of"][1] == "NO"

    def test_soft_delete_columns_present(self, decision_cols: dict) -> None:
        """is_deleted + deleted_at must remain per project convention."""
        assert "is_deleted" in decision_cols
        assert "deleted_at" in decision_cols

    def test_no_float_columns(self, pg_conn) -> None:
        """No real/double precision columns — all financials must be Numeric."""
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'atlas_decisions'
              AND data_type IN ('real', 'double precision')
            """
        )
        float_cols = cur.fetchall()
        cur.close()
        assert float_cols == [], f"Float columns found in atlas_decisions: {float_cols}"


# ---------------------------------------------------------------------------
# Index tests
# ---------------------------------------------------------------------------


class TestIndexes:
    def test_hnsw_embedding_index_exists(self, pg_indexes: set) -> None:
        """HNSW vector index must exist on atlas_intelligence.embedding."""
        assert "idx_intelligence_embedding" in pg_indexes

    def test_intelligence_indexes_exist(self, pg_indexes: set) -> None:
        """All spec-required intelligence indexes must exist."""
        required = {
            "idx_intelligence_entity",
            "idx_intelligence_entity_type",
            "idx_intelligence_agent_type",
            "idx_intelligence_finding_type",
            "idx_intelligence_created",
            "idx_intelligence_tags",
            "idx_intelligence_validated",
            "idx_intelligence_agent_id",
        }
        missing = required - pg_indexes
        assert not missing, f"Missing intelligence indexes: {missing}"

    def test_decisions_indexes_exist(self, pg_indexes: set) -> None:
        """All spec-required decisions indexes must exist."""
        required = {
            "idx_decisions_entity",
            "idx_decisions_status",
            "idx_decisions_horizon",
            "idx_decisions_agent",
        }
        missing = required - pg_indexes
        assert not missing, f"Missing decisions indexes: {missing}"

    def test_hnsw_index_uses_cosine_ops(self, pg_conn) -> None:
        """HNSW index must use vector_cosine_ops (not L2)."""
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT am.amname, opc.opcname
            FROM pg_index idx
            JOIN pg_class c ON c.oid = idx.indexrelid
            JOIN pg_opclass opc ON opc.oid = ANY(idx.indclass::int[])
            JOIN pg_am am ON am.oid = opc.opcmethod
            WHERE c.relname = 'idx_intelligence_embedding'
            """
        )
        rows = cur.fetchall()
        cur.close()
        # Should find hnsw + vector_cosine_ops
        am_names = [r[0] for r in rows]
        opc_names = [r[1] for r in rows]
        assert "hnsw" in am_names, f"Expected hnsw access method, got: {am_names}"
        assert any("cosine" in n for n in opc_names), (
            f"Expected cosine ops, got: {opc_names}"
        )


# ---------------------------------------------------------------------------
# pgvector extension test
# ---------------------------------------------------------------------------


class TestPgvector:
    def test_pgvector_extension_installed(self, pg_conn) -> None:
        """pgvector extension must be installed."""
        cur = pg_conn.cursor()
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
        cur.close()
        assert row is not None, "pgvector extension not installed"

    def test_vector_column_type(self, intel_cols: dict) -> None:
        """embedding column must be USER-DEFINED (vector type)."""
        assert "embedding" in intel_cols
        # psycopg2 reports vector type as USER-DEFINED
        emb_type = intel_cols["embedding"][0]
        assert emb_type == "USER-DEFINED", (
            f"embedding type should be USER-DEFINED (vector), got: {emb_type}"
        )


# ---------------------------------------------------------------------------
# Alembic migration head test
# ---------------------------------------------------------------------------


class TestAlembicMigration:
    def test_alembic_at_head(self, pg_conn) -> None:
        """Atlas alembic version must be at the v1_1_schema_parity revision."""
        cur = pg_conn.cursor()
        cur.execute("SELECT version_num FROM atlas_alembic_version")
        rows = cur.fetchall()
        cur.close()
        versions = [r[0] for r in rows]
        assert "c118008a7781" in versions, (
            f"Expected c118008a7781 in versions, got: {versions}"
        )

    def test_single_head(self) -> None:
        """Alembic script directory must have exactly one head (no branches)."""
        from alembic.config import Config  # type: ignore[import-untyped]
        from alembic.script import ScriptDirectory  # type: ignore[import-untyped]

        cfg = Config("/home/ubuntu/atlas/alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert len(heads) == 1, f"Expected 1 alembic head, got: {heads}"
