"""v1_3_intel_natural_key_index — unique index for idempotent upsert on atlas_intelligence.

Revision ID: d4e5f6a7b8c9
Revises: c118008a7781
Create Date: 2026-04-13

Adds a unique index on (agent_id, COALESCE(entity, ''), title, data_as_of) to
enable ON CONFLICT DO UPDATE idempotent upserts in the intelligence writer service.
"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c118008a7781"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Functional unique index: handles NULL entity via COALESCE
    # Named so the service can reference it in ON CONFLICT constraint=
    op.execute(
        """
        CREATE UNIQUE INDEX uq_intel_natural_key
        ON atlas_intelligence (agent_id, COALESCE(entity, ''), title, data_as_of)
        WHERE is_deleted = false
        """
    )

    # Additional performance index for vector similarity searches
    # HNSW index on embedding column with cosine_ops
    # Uses pgvector HNSW for sub-linear ANN search
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_intel_embedding_hnsw
        ON atlas_intelligence
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # Supporting filter indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_intel_agent_id ON atlas_intelligence (agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_intel_entity ON atlas_intelligence (entity)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_intel_finding_type ON atlas_intelligence (finding_type)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_intel_data_as_of ON atlas_intelligence (data_as_of)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_intel_confidence ON atlas_intelligence (confidence)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_intel_expires_at ON atlas_intelligence (expires_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_intel_expires_at")
    op.execute("DROP INDEX IF EXISTS idx_intel_confidence")
    op.execute("DROP INDEX IF EXISTS idx_intel_data_as_of")
    op.execute("DROP INDEX IF EXISTS idx_intel_finding_type")
    op.execute("DROP INDEX IF EXISTS idx_intel_entity")
    op.execute("DROP INDEX IF EXISTS idx_intel_agent_id")
    op.execute("DROP INDEX IF EXISTS idx_intel_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS uq_intel_natural_key")
