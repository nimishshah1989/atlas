"""v5_1_pgvector_extension — V5-1: Enable pgvector extension.

Ensures the pgvector extension exists in the database so that
vector-type columns (used in V5 semantic search / similarity features)
can be created in subsequent migrations.

Safe to run against production: CREATE EXTENSION IF NOT EXISTS is
idempotent and does nothing when the extension is already present.

Revision ID: e5f6a7b8c9d0
Revises: a1b2c3d4e5f6
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
