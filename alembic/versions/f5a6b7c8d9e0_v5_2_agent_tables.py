"""v5_2_agent_tables — V5-2: Create atlas_agent_scores, atlas_agent_weights, atlas_agent_memory.

Also ensures the HNSW index on atlas_intelligence.embedding exists
(idempotent — CREATE INDEX IF NOT EXISTS).

CHECK constraint on atlas_agent_weights.weight enforces range [0.3, 2.5].

Revision ID: f5a6b7c8d9e0
Revises: e5f6a7b8c9d0
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- atlas_agent_scores ---
    op.create_table(
        "atlas_agent_scores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("prediction_date", sa.Date(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=True),
        sa.Column("prediction", sa.Text(), nullable=False),
        sa.Column("evaluation_date", sa.Date(), nullable=True),
        sa.Column("actual_outcome", sa.Text(), nullable=True),
        sa.Column("accuracy_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_atlas_agent_scores_agent_id",
        "atlas_agent_scores",
        ["agent_id"],
    )

    # --- atlas_agent_weights ---
    op.create_table(
        "atlas_agent_weights",
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("weight", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("rolling_accuracy", sa.Numeric(5, 4), nullable=True),
        sa.Column("mutation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_mutation_date", sa.Date(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("weight >= 0.3 AND weight <= 2.5", name="ck_agent_weight_range"),
        sa.PrimaryKeyConstraint("agent_id"),
    )

    # --- atlas_agent_memory ---
    op.create_table(
        "atlas_agent_memory",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("memory_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_atlas_agent_memory_agent_id",
        "atlas_agent_memory",
        ["agent_id"],
    )

    # --- HNSW index on atlas_intelligence (idempotent safety) ---
    # The index idx_intel_embedding_hnsw may already exist from prior migrations.
    # Using raw SQL with IF NOT EXISTS for idempotency.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_intel_embedding_hnsw
        ON atlas_intelligence
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_intel_embedding_hnsw")
    op.drop_index("ix_atlas_agent_memory_agent_id", table_name="atlas_agent_memory")
    op.drop_table("atlas_agent_memory")
    op.drop_table("atlas_agent_weights")
    op.drop_index("ix_atlas_agent_scores_agent_id", table_name="atlas_agent_scores")
    op.drop_table("atlas_agent_scores")
