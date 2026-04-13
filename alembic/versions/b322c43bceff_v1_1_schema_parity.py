"""v1_1a_intelligence_parity — atlas_intelligence schema parity with spec §6.

Revision ID: b322c43bceff
Revises: 4fcfc8621e91
Create Date: 2026-04-13

Renames, type changes, and new columns on atlas_intelligence.
Table is empty at migration time; no data migration needed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op  # type: ignore[attr-defined]
from sqlalchemy.dialects import postgresql

revision: str = "b322c43bceff"
down_revision: Union[str, None] = "4fcfc8621e91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old indexes before column renames
    op.drop_index(
        "ix_atlas_intelligence_agent_name",
        table_name="atlas_intelligence",
        if_exists=True,
    )
    op.drop_index(
        "ix_atlas_intelligence_entity_id",
        table_name="atlas_intelligence",
        if_exists=True,
    )
    op.drop_index(
        "ix_atlas_intelligence_entity_type",
        table_name="atlas_intelligence",
        if_exists=True,
    )
    op.drop_index(
        "ix_atlas_intelligence_finding_type",
        table_name="atlas_intelligence",
        if_exists=True,
    )
    op.drop_index(
        "ix_atlas_intel_entity",
        table_name="atlas_intelligence",
        if_exists=True,
    )

    # Rename columns
    op.alter_column(
        "atlas_intelligence",
        "agent_name",
        new_column_name="agent_id",
        existing_type=sa.VARCHAR(50),
        type_=sa.VARCHAR(100),
        nullable=False,
    )
    op.alter_column(
        "atlas_intelligence",
        "entity_id",
        new_column_name="entity",
        existing_type=sa.VARCHAR(100),
        type_=sa.Text(),
        nullable=True,
    )
    op.alter_column(
        "atlas_intelligence",
        "metadata",
        new_column_name="evidence",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )

    # Alter existing columns
    op.alter_column(
        "atlas_intelligence",
        "entity_type",
        existing_type=sa.VARCHAR(30),
        type_=sa.VARCHAR(20),
        nullable=True,
    )
    op.alter_column(
        "atlas_intelligence",
        "title",
        existing_type=sa.VARCHAR(255),
        type_=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "atlas_intelligence",
        "confidence",
        existing_type=sa.Numeric(5, 2),
        type_=sa.Numeric(5, 4),
        nullable=True,
    )
    op.execute(
        "UPDATE atlas_intelligence SET data_as_of = NOW() WHERE data_as_of IS NULL"
    )
    op.alter_column(
        "atlas_intelligence",
        "data_as_of",
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=False,
    )

    # Add new columns
    op.add_column(
        "atlas_intelligence",
        sa.Column("agent_type", sa.VARCHAR(50), nullable=False, server_default=""),
    )
    op.add_column(
        "atlas_intelligence",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            server_default="{}",
        ),
    )
    op.add_column(
        "atlas_intelligence",
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "atlas_intelligence",
        sa.Column(
            "is_validated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "atlas_intelligence",
        sa.Column(
            "validation_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # Create spec indexes
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_intelligence_embedding"
        " ON atlas_intelligence USING hnsw (embedding vector_cosine_ops)"
        " WITH (m = 16, ef_construction = 64)"
    )
    op.create_index("idx_intelligence_entity", "atlas_intelligence", ["entity"])
    op.create_index(
        "idx_intelligence_entity_type", "atlas_intelligence", ["entity_type"]
    )
    op.create_index("idx_intelligence_agent_type", "atlas_intelligence", ["agent_type"])
    op.create_index(
        "idx_intelligence_finding_type", "atlas_intelligence", ["finding_type"]
    )
    op.create_index("idx_intelligence_created", "atlas_intelligence", ["created_at"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_intelligence_tags"
        " ON atlas_intelligence USING gin(tags)"
    )
    op.create_index(
        "idx_intelligence_validated", "atlas_intelligence", ["is_validated"]
    )
    op.create_index("idx_intelligence_agent_id", "atlas_intelligence", ["agent_id"])


def downgrade() -> None:
    # Drop new indexes
    op.execute("DROP INDEX IF EXISTS idx_intelligence_embedding")
    op.execute("DROP INDEX IF EXISTS idx_intelligence_tags")
    op.drop_index(
        "idx_intelligence_agent_id", table_name="atlas_intelligence", if_exists=True
    )
    op.drop_index(
        "idx_intelligence_validated", table_name="atlas_intelligence", if_exists=True
    )
    op.drop_index(
        "idx_intelligence_created", table_name="atlas_intelligence", if_exists=True
    )
    op.drop_index(
        "idx_intelligence_finding_type",
        table_name="atlas_intelligence",
        if_exists=True,
    )
    op.drop_index(
        "idx_intelligence_agent_type", table_name="atlas_intelligence", if_exists=True
    )
    op.drop_index(
        "idx_intelligence_entity_type",
        table_name="atlas_intelligence",
        if_exists=True,
    )
    op.drop_index(
        "idx_intelligence_entity", table_name="atlas_intelligence", if_exists=True
    )

    # Drop new columns
    op.drop_column("atlas_intelligence", "validation_result")
    op.drop_column("atlas_intelligence", "is_validated")
    op.drop_column("atlas_intelligence", "expires_at")
    op.drop_column("atlas_intelligence", "tags")
    op.drop_column("atlas_intelligence", "agent_type")

    # Revert data_as_of to nullable
    op.alter_column(
        "atlas_intelligence",
        "data_as_of",
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=True,
    )

    # Rename columns back
    op.alter_column(
        "atlas_intelligence",
        "evidence",
        new_column_name="metadata",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )
    op.alter_column(
        "atlas_intelligence",
        "entity",
        new_column_name="entity_id",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(100),
        nullable=False,
    )
    op.alter_column(
        "atlas_intelligence",
        "agent_id",
        new_column_name="agent_name",
        existing_type=sa.VARCHAR(100),
        type_=sa.VARCHAR(50),
        nullable=False,
    )
    op.alter_column(
        "atlas_intelligence",
        "entity_type",
        existing_type=sa.VARCHAR(20),
        type_=sa.VARCHAR(30),
        nullable=False,
    )
    op.alter_column(
        "atlas_intelligence",
        "title",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(255),
        nullable=False,
    )
    op.alter_column(
        "atlas_intelligence",
        "confidence",
        existing_type=sa.Numeric(5, 4),
        type_=sa.Numeric(5, 2),
        nullable=True,
    )

    # Restore old indexes
    op.create_index(
        "ix_atlas_intelligence_finding_type",
        "atlas_intelligence",
        ["finding_type"],
        unique=False,
    )
    op.create_index(
        "ix_atlas_intelligence_entity_type",
        "atlas_intelligence",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        "ix_atlas_intelligence_entity_id",
        "atlas_intelligence",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_atlas_intelligence_agent_name",
        "atlas_intelligence",
        ["agent_name"],
        unique=False,
    )
    op.create_index(
        "ix_atlas_intel_entity",
        "atlas_intelligence",
        ["entity_type", "entity_id"],
        unique=False,
    )
